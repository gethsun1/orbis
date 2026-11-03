"""PostgreSQL implementation of the observer persistence boundary."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row
from orbis.observer.integrity import validate_block_transactions


class PostgresStore:
    """Authoritative observer store. Each block and cursor update share a transaction."""

    def __init__(self, dsn: str, migration_dir: str | Path | None = None, schema: str | None = None,
                 network_name: str = "", network_environment: str = "", provider_name: str = "") -> None:
        self.db = psycopg.connect(dsn, row_factory=dict_row, autocommit=True)
        self.network_name = network_name
        self.network_environment = network_environment
        self.provider_name = provider_name
        if schema:
            # Identifiers cannot be bound as values; quote via psycopg's Identifier.
            from psycopg import sql
            self.db.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema)))
            self.db.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
        self.migration_dir = Path(migration_dir) if migration_dir else Path(__file__).resolve().parents[3] / "migrations"

    def migrate(self) -> None:
        with self.db.transaction():
            self.db.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())")
            for path in sorted(self.migration_dir.glob("*.sql")):
                found = self.db.execute("SELECT 1 FROM schema_migrations WHERE version=%s", (path.name,)).fetchone()
                if found:
                    continue
                self.db.execute(path.read_text())
                self.db.execute("INSERT INTO schema_migrations(version) VALUES (%s)", (path.name,))

    def _network_id(self, chain_id: int) -> int:
        row = self.db.execute("""INSERT INTO networks(chain_id,name,environment,provider_name)
            VALUES (%s,%s,COALESCE(NULLIF(%s,''),'unknown'),%s) ON CONFLICT(chain_id) DO UPDATE SET
            name=CASE WHEN EXCLUDED.name<>'' THEN EXCLUDED.name ELSE networks.name END,
            environment=CASE WHEN EXCLUDED.environment<>'unknown' THEN EXCLUDED.environment ELSE networks.environment END,
            provider_name=CASE WHEN EXCLUDED.provider_name<>'' THEN EXCLUDED.provider_name ELSE networks.provider_name END
            RETURNING network_id""",
            (chain_id, self.network_name, self.network_environment, self.provider_name)).fetchone()
        return int(row["network_id"])

    def checkpoint(self, chain_id: int) -> tuple[int, str] | None:
        row = self.db.execute("SELECT c.block_number,c.block_hash FROM checkpoints c JOIN networks n USING(network_id) WHERE n.chain_id=%s", (chain_id,)).fetchone()
        return (row["block_number"], row["block_hash"]) if row else None

    def block_hash(self, chain_id: int, number: int) -> str | None:
        row = self.db.execute("SELECT b.hash FROM blocks b JOIN networks n USING(network_id) WHERE n.chain_id=%s AND b.number=%s AND b.canonical", (chain_id, number)).fetchone()
        return row["hash"] if row else None

    def commit_block(self, chain_id: int, block: dict[str, Any], receipts: list[dict[str, Any]], logs: list[dict[str, Any]]) -> None:
        validate_block_transactions(block)
        number = int(block["number"], 16)
        with self.db.transaction():
            network_id = self._network_id(chain_id)
            # A canonical height has one block. Evidence references restrict removal of source
            # data; the deferred checkpoint FK permits safe replacement before cursor update.
            self.db.execute("DELETE FROM blocks WHERE network_id=%s AND number=%s AND hash<>%s", (network_id, number, block["hash"]))
            self.db.execute("""INSERT INTO blocks(network_id,number,hash,parent_hash,timestamp,canonical)
                VALUES(%s,%s,%s,%s,%s,TRUE) ON CONFLICT(network_id,hash) DO UPDATE SET
                number=EXCLUDED.number,parent_hash=EXCLUDED.parent_hash,timestamp=EXCLUDED.timestamp,canonical=TRUE""",
                (network_id, number, block["hash"], block["parentHash"], int(block["timestamp"], 16)))
            self.db.execute("DELETE FROM transactions WHERE network_id=%s AND block_number=%s", (network_id, number))
            for index, tx in enumerate(block.get("transactions", [])):
                sender = tx.get("from")
                recipient = tx.get("to")
                self.db.execute("""INSERT INTO transactions VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT(network_id,hash) DO UPDATE SET block_number=EXCLUDED.block_number,
                    block_hash=EXCLUDED.block_hash,tx_index=EXCLUDED.tx_index,sender=EXCLUDED.sender,
                    recipient=EXCLUDED.recipient,value=EXCLUDED.value,input_data=EXCLUDED.input_data""",
                    (network_id, tx["hash"], number, block["hash"], int(tx.get("transactionIndex", hex(index)), 16),
                     sender.lower() if sender else None, recipient.lower() if recipient else None,
                     tx.get("value", "0x0"), tx.get("input", "0x")))
            receipt_by_hash = {r["transactionHash"].lower(): r for r in receipts}
            for receipt in receipts:
                status = int(receipt["status"], 16) if isinstance(receipt.get("status"), str) else receipt.get("status")
                self.db.execute("""INSERT INTO receipts(network_id,transaction_hash,block_hash,status,gas_used,raw)
                    VALUES(%s,%s,%s,%s,%s,%s::jsonb) ON CONFLICT(network_id,transaction_hash) DO UPDATE SET
                    block_hash=EXCLUDED.block_hash,status=EXCLUDED.status,gas_used=EXCLUDED.gas_used,raw=EXCLUDED.raw""",
                    (network_id, receipt["transactionHash"], block["hash"], status, receipt.get("gasUsed"), json.dumps(receipt)))
            selected_logs = [log for receipt in receipts for log in receipt.get("logs", [])] if receipt_by_hash else logs
            for log in selected_logs:
                self.db.execute("""INSERT INTO logs VALUES(%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s)
                    ON CONFLICT(network_id,transaction_hash,log_index) DO UPDATE SET block_number=EXCLUDED.block_number,
                    block_hash=EXCLUDED.block_hash,address=EXCLUDED.address,topics=EXCLUDED.topics,data=EXCLUDED.data,removed=EXCLUDED.removed""",
                    (network_id, log["transactionHash"], int(log["logIndex"], 16), number,
                     log["blockHash"], log["address"].lower(), json.dumps(log.get("topics", [])), log.get("data", "0x"), bool(log.get("removed", False))))
            self.db.execute("""INSERT INTO checkpoints VALUES(%s,%s,%s) ON CONFLICT(network_id) DO UPDATE SET
                block_number=EXCLUDED.block_number,block_hash=EXCLUDED.block_hash
                WHERE checkpoints.block_number <= EXCLUDED.block_number""", (network_id, number, block["hash"]))

    def rollback_from(self, chain_id: int, number: int) -> None:
        with self.db.transaction():
            row = self.db.execute("SELECT network_id FROM networks WHERE chain_id=%s", (chain_id,)).fetchone()
            if not row:
                return
            network_id = row["network_id"]
            # Retract derived knowledge before deleting its source suffix. Replayed
            # canonical records will be enriched again by the independent pipeline.
            evidence = self.db.execute("""SELECT e.evidence_id FROM evidence_refs e JOIN observations o
                USING(network_id,observation_id) WHERE e.network_id=%s AND e.block_number >= %s AND o.derived""",
                                       (network_id, number)).fetchall()
            evidence_ids = [r["evidence_id"] for r in evidence]
            if evidence_ids:
                self.db.execute("DELETE FROM relationship_evidence WHERE network_id=%s AND evidence_id = ANY(%s)",
                                 (network_id, evidence_ids))
                self.db.execute("DELETE FROM evidence_refs WHERE network_id=%s AND evidence_id = ANY(%s)",
                                 (network_id, evidence_ids))
            self.db.execute("DELETE FROM observations WHERE network_id=%s AND derived AND source_block_number >= %s",
                            (network_id, number))
            # Rebuild summaries from the evidence that survived invalidation. Incremental
            # LEAST/GREATEST leaves stale endpoints when the first/last supporting block
            # is removed, and counting evidence rows overcounts repeated logs per tx.
            self.db.execute("""UPDATE relationships r SET
                first_observed_block=a.first_block,last_observed_block=a.last_block,
                observation_count=a.tx_count,updated_at=now()
                FROM (SELECT re.network_id,re.relationship_id,
                    min(e.block_number) AS first_block,max(e.block_number) AS last_block,
                    count(DISTINCT e.transaction_hash) AS tx_count
                    FROM relationship_evidence re JOIN evidence_refs e
                      USING(network_id,evidence_id)
                    JOIN blocks b ON (b.network_id,b.number,b.hash)=
                      (e.network_id,e.block_number,e.block_hash)
                    WHERE re.network_id=%s AND b.canonical AND e.transaction_hash IS NOT NULL
                    GROUP BY re.network_id,re.relationship_id) a
                WHERE r.network_id=a.network_id AND r.relationship_id=a.relationship_id""", (network_id,))
            self.db.execute("""DELETE FROM relationships r WHERE r.network_id=%s AND NOT EXISTS
                (SELECT 1 FROM relationship_evidence re JOIN evidence_refs e
                  USING(network_id,evidence_id) JOIN blocks b ON
                  (b.network_id,b.number,b.hash)=(e.network_id,e.block_number,e.block_hash)
                 WHERE re.network_id=r.network_id AND re.relationship_id=r.relationship_id AND b.canonical)""",
                (network_id,))
            self.db.execute("""DELETE FROM entities e WHERE network_id=%s AND metadata ? 'discovery'
                AND NOT EXISTS (SELECT 1 FROM observations o WHERE o.network_id=e.network_id AND o.entity_id=e.entity_id)
                AND NOT EXISTS (SELECT 1 FROM relationships r WHERE r.network_id=e.network_id
                  AND (r.source_entity_id=e.entity_id OR r.target_entity_id=e.entity_id))""", (network_id,))
            self.db.execute("DELETE FROM blocks WHERE network_id=%s AND number >= %s", (network_id, number))
            previous = self.db.execute("SELECT number,hash FROM blocks WHERE network_id=%s AND number<%s ORDER BY number DESC LIMIT 1", (network_id, number)).fetchone()
            if previous:
                self.db.execute("INSERT INTO checkpoints VALUES(%s,%s,%s) ON CONFLICT(network_id) DO UPDATE SET block_number=EXCLUDED.block_number,block_hash=EXCLUDED.block_hash", (network_id, previous["number"], previous["hash"]))
            else:
                self.db.execute("DELETE FROM checkpoints WHERE network_id=%s", (network_id,))

    def count(self, table: str, chain_id: int) -> int:
        if table not in {"blocks", "transactions", "receipts", "logs"}:
            raise ValueError("unsupported table")
        row = self.db.execute(f"SELECT count(*) AS n FROM {table} t JOIN networks n USING(network_id) WHERE n.chain_id=%s", (chain_id,)).fetchone()
        return int(row["n"])

    def close(self) -> None:
        self.db.close()
