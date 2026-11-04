"""Evidence-backed entity enrichment and network-scoped retrieval."""
from __future__ import annotations

import re
from typing import Any

from psycopg.types.json import Jsonb
from orbis.network import NetworkContext


_ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")
_TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
_ZERO_ADDRESS = "0x" + "0" * 40


def normalize_address(address: str) -> str:
    if not isinstance(address, str) or not _ADDRESS.fullmatch(address):
        raise ValueError(f"invalid EVM address: {address!r}")
    return address.lower()


class KnowledgeService:
    """PostgreSQL knowledge operations; caller supplies an initialized PostgresStore."""

    def __init__(self, store):
        self.store = store
        self.db = store.db

    def _network(self, context: NetworkContext) -> int:
        from orbis.observer.postgres import PostgresStore
        return PostgresStore._network_id(context)

    def resolve_entity(self, context: NetworkContext, address: str, entity_type: str = "unknown",
                      metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        normalized = normalize_address(address)
        if entity_type not in {"wallet", "contract", "token", "unknown"}:
            raise ValueError("unsupported entity type")
        net = self._network(context)
        row = self.db.execute("""INSERT INTO entities(network_id,address,original_address,entity_type,metadata)
            VALUES(%s,%s,%s,%s,%s) ON CONFLICT(network_id,address) DO UPDATE SET
            entity_type=CASE WHEN entities.entity_type='unknown' AND EXCLUDED.entity_type<>'unknown'
              THEN EXCLUDED.entity_type ELSE entities.entity_type END,
            metadata=entities.metadata || EXCLUDED.metadata, updated_at=now()
            RETURNING entity_id,network_id,address,original_address,entity_type,metadata,created_at""",
            (net, normalized, address, entity_type, Jsonb(metadata or {}))).fetchone()
        return dict(row)

    def ingest(self, context: NetworkContext, limit: int = 500) -> int:
        """Enrich one bounded, deterministic page of not-yet-completed transactions."""
        if not 1 <= limit <= 5000:
            raise ValueError("limit must be between 1 and 5000")
        net = self._network(context)
        with self.db.transaction():
            txs = self.db.execute("""SELECT t.hash,t.sender,t.recipient,t.block_number,t.block_hash,
                    b.timestamp,t.tx_index FROM transactions t JOIN blocks b
                  ON b.network_id=t.network_id AND b.number=t.block_number AND b.hash=t.block_hash
                WHERE t.network_id=%s AND b.canonical AND NOT EXISTS (
                  SELECT 1 FROM knowledge_enrichment_progress p
                  WHERE (p.network_id,p.transaction_hash)=(t.network_id,t.hash))
                ORDER BY t.block_number,t.tx_index,t.hash LIMIT %s FOR UPDATE OF t SKIP LOCKED""",
                (net, limit)).fetchall()
            processed = 0
            for tx in txs:
                sender = self.resolve_entity(context, tx["sender"], "unknown", {"discovery":"transaction_index"}) if tx["sender"] else None
                recipient = self.resolve_entity(context, tx["recipient"], "unknown", {"discovery":"transaction_index"}) if tx["recipient"] else None
                participants = [(sender, "transaction_initiated"), (recipient, "transaction_received")]
                tx_evidence = {}
                for entity, kind in participants:
                    if not entity:
                        continue
                    obs = self.db.execute("""INSERT INTO observations(network_id,entity_id,related_entity_id,
                        observation_type,status,source_block_number,source_block_hash,source_transaction_hash,
                        source_timestamp,derived,payload) VALUES(%s,%s,%s,%s,'open',%s,%s,%s,%s,TRUE,%s)
                        ON CONFLICT DO NOTHING RETURNING observation_id""",
                        (net, entity["entity_id"], ((recipient or {}) if kind == "transaction_initiated" else (sender or {})).get("entity_id"),
                         kind, tx["block_number"],tx["block_hash"],tx["hash"],tx["timestamp"],
                         Jsonb({"transaction_index": tx["tx_index"]}))).fetchone()
                    if not obs:
                        obs = self.db.execute("""SELECT observation_id FROM observations WHERE network_id=%s AND
                            entity_id=%s AND observation_type=%s AND source_transaction_hash=%s AND derived""",
                            (net,entity["entity_id"],kind,tx["hash"])).fetchone()
                    if not obs:
                        continue
                    ev = self.db.execute("""INSERT INTO evidence_refs(network_id,observation_id,block_number,block_hash,transaction_hash)
                        VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING evidence_id""",
                        (net,obs["observation_id"],tx["block_number"],tx["block_hash"],tx["hash"])).fetchone()
                    if not ev:
                        ev = self.db.execute("SELECT evidence_id FROM evidence_refs WHERE network_id=%s AND observation_id=%s AND transaction_hash=%s AND log_index IS NULL",
                                              (net,obs["observation_id"],tx["hash"])).fetchone()
                    if ev:
                        tx_evidence[kind] = ev["evidence_id"]
                    if ev and kind == "transaction_initiated" and sender and recipient and sender["entity_id"] != recipient["entity_id"]:
                        rel = self.db.execute("""INSERT INTO relationships(network_id,source_entity_id,relationship_type,
                            target_entity_id,derivation,first_observed_block,last_observed_block,observation_count)
                            VALUES(%s,%s,'transacted_with',%s,'aggregated',%s,%s,1)
                            ON CONFLICT(network_id,source_entity_id,relationship_type,target_entity_id,derivation)
                            DO UPDATE SET first_observed_block=LEAST(relationships.first_observed_block,EXCLUDED.first_observed_block),
                              last_observed_block=GREATEST(relationships.last_observed_block,EXCLUDED.last_observed_block),
                              observation_count=relationships.observation_count+1,updated_at=now()
                            RETURNING relationship_id""",
                            (net,sender["entity_id"],recipient["entity_id"],tx["block_number"],tx["block_number"])).fetchone()
                        self.db.execute("""INSERT INTO relationship_evidence(network_id,relationship_id,evidence_id)
                            VALUES(%s,%s,%s) ON CONFLICT DO NOTHING RETURNING evidence_id""",
                            (net,rel["relationship_id"],ev["evidence_id"])).fetchone()
                        self.db.execute("""UPDATE relationships SET observation_count=GREATEST(1,
                            (SELECT count(DISTINCT er.transaction_hash) FROM relationship_evidence re
                             JOIN evidence_refs er USING(network_id,evidence_id)
                             WHERE re.network_id=%s AND re.relationship_id=%s)),updated_at=now()
                            WHERE network_id=%s AND relationship_id=%s""",
                            (net,rel["relationship_id"],net,rel["relationship_id"]))
                processed += 1
                # Log emission is independent of transaction sender attribution.
                logs = self.db.execute("""SELECT log_index,address,block_number,block_hash,topics,data FROM logs
                    WHERE network_id=%s AND transaction_hash=%s AND NOT removed ORDER BY log_index""",
                    (net,tx["hash"])).fetchall()
                for log in logs:
                    contract = self.resolve_entity(context,log["address"],"contract",{"discovery":"receipt_log"})
                    obs = self.db.execute("""INSERT INTO observations(network_id,entity_id,related_entity_id,
                        observation_type,status,source_block_number,source_block_hash,source_transaction_hash,
                        source_log_index,source_timestamp,derived,payload)
                    VALUES(%s,%s,NULL,'emitted_event_during','open',%s,%s,%s,%s,%s,TRUE,'{}'::jsonb)
                        ON CONFLICT DO NOTHING RETURNING observation_id""",
                        (net,contract["entity_id"],log["block_number"],log["block_hash"],
                         tx["hash"],log["log_index"],tx["timestamp"])).fetchone()
                    if not obs:
                        obs=self.db.execute("""SELECT observation_id FROM observations WHERE network_id=%s AND
                            entity_id=%s AND observation_type='emitted_event_during' AND source_transaction_hash=%s
                            AND source_log_index=%s AND derived""",(net,contract["entity_id"],tx["hash"],log["log_index"])).fetchone()
                    if not obs:
                        continue
                    ev=self.db.execute("""INSERT INTO evidence_refs(network_id,observation_id,block_number,
                        block_hash,transaction_hash,log_index) VALUES(%s,%s,%s,%s,%s,%s)
                        ON CONFLICT DO NOTHING RETURNING evidence_id""",
                        (net,obs["observation_id"],log["block_number"],log["block_hash"],tx["hash"],log["log_index"])).fetchone()
                    if not ev:
                        ev=self.db.execute("SELECT evidence_id FROM evidence_refs WHERE network_id=%s AND observation_id=%s AND transaction_hash=%s AND log_index=%s",
                                           (net,obs["observation_id"],tx["hash"],log["log_index"])).fetchone()
                    topics = log["topics"] if isinstance(log["topics"], list) else []
                    data = log["data"] or ""
                    if (ev and len(topics) == 3 and str(topics[0]).lower() == _TRANSFER_TOPIC
                            and all(re.fullmatch(r"0x0{24}[0-9a-fA-F]{40}", str(item)) for item in topics[1:])
                            and re.fullmatch(r"0x[0-9a-fA-F]{64}", data)):
                        from_address = "0x" + str(topics[1])[-40:].lower()
                        to_address = "0x" + str(topics[2])[-40:].lower()
                        from_entity = None if from_address == _ZERO_ADDRESS else self.resolve_entity(context,from_address)
                        to_entity = None if to_address == _ZERO_ADDRESS else self.resolve_entity(context,to_address)
                        amount = str(int(data,16))
                        if to_entity:
                            transfer_observation = self.db.execute("""INSERT INTO observations(network_id,entity_id,
                                related_entity_id,observation_type,source_block_number,source_block_hash,
                                source_transaction_hash,source_log_index,source_timestamp,derived,payload)
                                VALUES(%s,%s,%s,'token_transfer_received',%s,%s,%s,%s,%s,TRUE,%s)
                                ON CONFLICT DO NOTHING RETURNING observation_id""",
                                (net,to_entity["entity_id"],from_entity["entity_id"] if from_entity else None,
                                 log["block_number"],log["block_hash"],tx["hash"],log["log_index"],tx["timestamp"],
                                 Jsonb({"token":contract["address"],"amount":amount,"mint":from_entity is None}))).fetchone()
                            if transfer_observation:
                                self.db.execute("""INSERT INTO evidence_refs(network_id,observation_id,block_number,
                                    block_hash,transaction_hash,log_index) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                                    (net,transfer_observation["observation_id"],log["block_number"],log["block_hash"],tx["hash"],log["log_index"]))
                        if from_entity and to_entity and from_entity["entity_id"] != to_entity["entity_id"]:
                            transfer = self.db.execute("""INSERT INTO relationships(network_id,source_entity_id,
                                relationship_type,target_entity_id,derivation,first_observed_block,last_observed_block,observation_count)
                                VALUES(%s,%s,'transferred_to',%s,'aggregated',%s,%s,1)
                                ON CONFLICT(network_id,source_entity_id,relationship_type,target_entity_id,derivation)
                                DO UPDATE SET updated_at=now() RETURNING relationship_id""",
                                (net,from_entity["entity_id"],to_entity["entity_id"],log["block_number"],
                                 log["block_number"])).fetchone()
                            self.db.execute("INSERT INTO relationship_evidence VALUES(%s,%s,%s) ON CONFLICT DO NOTHING",
                                            (net,transfer["relationship_id"],ev["evidence_id"]))
                if tx_evidence.get("transaction_initiated") and sender and recipient and sender["entity_id"] != recipient["entity_id"]:
                    current_type = self.db.execute("SELECT entity_type FROM entities WHERE network_id=%s AND entity_id=%s",
                                                   (net,recipient["entity_id"])).fetchone()["entity_type"]
                    if current_type in {"contract","token"}:
                        rel=self.db.execute("""INSERT INTO relationships(network_id,source_entity_id,relationship_type,
                            target_entity_id,derivation,first_observed_block,last_observed_block,observation_count)
                            VALUES(%s,%s,'interacted_with_contract',%s,'aggregated',%s,%s,1)
                            ON CONFLICT(network_id,source_entity_id,relationship_type,target_entity_id,derivation)
                            DO UPDATE SET updated_at=now() RETURNING relationship_id""",
                            (net,sender["entity_id"],recipient["entity_id"],tx["block_number"],tx["block_number"])).fetchone()
                        self.db.execute("INSERT INTO relationship_evidence VALUES(%s,%s,%s) ON CONFLICT DO NOTHING",
                                        (net,rel["relationship_id"],tx_evidence["transaction_initiated"]))
                # A completion row also records transactions with no qualifying facts.
                self.db.execute("INSERT INTO knowledge_enrichment_progress(network_id,transaction_hash) VALUES(%s,%s)",
                                (net,tx["hash"]))
            return processed

    def ingestion_status(self, context: NetworkContext) -> dict[str, int]:
        """Return eligible, completed and remaining canonical transaction counts."""
        net = self._network(context)
        row = self.db.execute("""SELECT count(*) AS eligible,count(p.transaction_hash) AS processed,
            count(*)-count(p.transaction_hash) AS remaining FROM transactions t JOIN blocks b ON
            (b.network_id,b.number,b.hash)=(t.network_id,t.block_number,t.block_hash)
            LEFT JOIN knowledge_enrichment_progress p ON (p.network_id,p.transaction_hash)=(t.network_id,t.hash)
            WHERE t.network_id=%s AND b.canonical""", (net,)).fetchone()
        return {key:int(row[key]) for key in ("eligible","processed","remaining")}

    def get_entity(self, context: NetworkContext, address: str) -> dict[str, Any] | None:
        try: net = self._network(context)
        except LookupError: return None
        row = self.db.execute("SELECT * FROM entities WHERE network_id=%s AND address=%s", (net,normalize_address(address))).fetchone()
        return dict(row) if row else None

    def observations(self, context: NetworkContext, address: str, limit: int = 50, offset: int = 0,
                     from_block: int | None = None, to_block: int | None = None) -> list[dict[str, Any]]:
        if not 1 <= limit <= 500 or offset < 0: raise ValueError("invalid pagination")
        net=self._network(context); entity=self.get_entity(context,address)
        if not entity: return []
        return [dict(r) for r in self.db.execute("""SELECT * FROM observations WHERE network_id=%s AND entity_id=%s
            AND (%s::bigint IS NULL OR source_block_number >= %s) AND (%s::bigint IS NULL OR source_block_number <= %s)
            ORDER BY source_block_number DESC,observation_id DESC LIMIT %s OFFSET %s""",
            (net,entity["entity_id"],from_block,from_block,to_block,to_block,limit,offset)).fetchall()]

    def relationships(self, context: NetworkContext, address: str, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        if not 1 <= limit <= 500 or offset < 0: raise ValueError("invalid pagination")
        net=self._network(context); entity=self.get_entity(context,address)
        if not entity: return []
        return [dict(r) for r in self.db.execute("""SELECT r.*,s.address AS source_address,t.address AS target_address
            FROM relationships r JOIN entities s ON (s.network_id,s.entity_id)=(r.network_id,r.source_entity_id)
            JOIN entities t ON (t.network_id,t.entity_id)=(r.network_id,r.target_entity_id)
            WHERE r.network_id=%s AND (r.source_entity_id=%s OR r.target_entity_id=%s)
            ORDER BY r.last_observed_block DESC,r.relationship_id DESC LIMIT %s OFFSET %s""",
            (net,entity["entity_id"],entity["entity_id"],limit,offset)).fetchall()]

    def relationship_evidence(self, context: NetworkContext, relationship_id: int, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        if not 1 <= limit <= 500 or offset < 0: raise ValueError("invalid pagination")
        net=self._network(context)
        return [dict(r) for r in self.db.execute("""SELECT e.* FROM relationship_evidence re JOIN evidence_refs e USING(evidence_id,network_id)
            JOIN relationships r USING(network_id,relationship_id) WHERE r.network_id=%s AND r.relationship_id=%s
            ORDER BY e.block_number,e.transaction_hash,e.log_index NULLS FIRST,e.evidence_id LIMIT %s OFFSET %s""",
            (net,relationship_id,limit,offset)).fetchall()]

    def relationships_between(self, context: NetworkContext, source: str, target: str, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        if not 1 <= limit <= 500 or offset < 0: raise ValueError("invalid pagination")
        net=self._network(context)
        a=normalize_address(source); b=normalize_address(target)
        return [dict(r) for r in self.db.execute("""SELECT r.* FROM relationships r
            JOIN entities s ON (s.network_id,s.entity_id)=(r.network_id,r.source_entity_id)
            JOIN entities t ON (t.network_id,t.entity_id)=(r.network_id,r.target_entity_id)
            WHERE r.network_id=%s AND s.address=%s AND t.address=%s ORDER BY r.last_observed_block DESC,r.relationship_id DESC LIMIT %s OFFSET %s""",
            (net,a,b,limit,offset)).fetchall()]

    def transaction_history(self, context: NetworkContext, address: str, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        if not 1 <= limit <= 500 or offset < 0: raise ValueError("invalid pagination")
        net=self._network(context); addr=normalize_address(address)
        return [dict(r) for r in self.db.execute("""SELECT t.*,b.timestamp,r.status,r.raw AS receipt
            FROM transactions t JOIN blocks b ON (b.network_id,b.number,b.hash)=(t.network_id,t.block_number,t.block_hash)
            LEFT JOIN receipts r ON (r.network_id,r.transaction_hash)=(t.network_id,t.hash) WHERE t.network_id=%s AND b.canonical
              AND (t.sender=%s OR t.recipient=%s)
            ORDER BY t.block_number DESC,t.tx_index DESC,t.hash DESC LIMIT %s OFFSET %s""",
            (net,addr,addr,limit,offset)).fetchall()]
