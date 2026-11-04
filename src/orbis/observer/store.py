"""Durable local observer store. PostgreSQL becomes the authoritative store in M2."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any
from orbis.observer.integrity import validate_block_transactions


class SqliteStore:
    """SQLite is the M1 single-node checkpoint/evidence store, not a scale target."""

    supports_unresolved_single_profile = True

    def __init__(self, path: str) -> None:
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS blocks (
                chain_id INTEGER NOT NULL, number INTEGER NOT NULL, hash TEXT NOT NULL,
                parent_hash TEXT NOT NULL, timestamp INTEGER NOT NULL, canonical INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (chain_id, number)
            );
            CREATE TABLE IF NOT EXISTS transactions (
                chain_id INTEGER NOT NULL, hash TEXT NOT NULL, block_number INTEGER NOT NULL,
                block_hash TEXT NOT NULL, tx_index INTEGER NOT NULL, sender TEXT, recipient TEXT,
                value TEXT NOT NULL, input_data TEXT NOT NULL, PRIMARY KEY (chain_id, hash),
                FOREIGN KEY (chain_id, block_number) REFERENCES blocks(chain_id, number) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS logs (
                chain_id INTEGER NOT NULL, tx_hash TEXT NOT NULL, log_index INTEGER NOT NULL,
                block_number INTEGER NOT NULL, block_hash TEXT NOT NULL, address TEXT NOT NULL,
                topics_json TEXT NOT NULL, data TEXT NOT NULL, removed INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (chain_id, tx_hash, log_index),
                FOREIGN KEY (chain_id, block_number) REFERENCES blocks(chain_id, number) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS checkpoints (
                chain_id INTEGER PRIMARY KEY, block_number INTEGER NOT NULL, block_hash TEXT NOT NULL
            );
        """)
        self.db.commit()

    def checkpoint(self, chain_id: int) -> tuple[int, str] | None:
        row = self.db.execute("SELECT block_number, block_hash FROM checkpoints WHERE chain_id=?", (chain_id,)).fetchone()
        return (row["block_number"], row["block_hash"]) if row else None

    def block_hash(self, chain_id: int, number: int) -> str | None:
        row = self.db.execute("SELECT hash FROM blocks WHERE chain_id=? AND number=?", (chain_id, number)).fetchone()
        return row["hash"] if row else None

    def commit_block(self, chain_id: int, block: dict[str, Any], receipts: list[dict[str, Any]], logs: list[dict[str, Any]]) -> None:
        validate_block_transactions(block)
        number = int(block["number"], 16)
        with self.db:
            self.db.execute("""INSERT INTO blocks(chain_id,number,hash,parent_hash,timestamp,canonical)
                VALUES(?,?,?,?,?,1) ON CONFLICT(chain_id,number) DO UPDATE SET
                hash=excluded.hash,parent_hash=excluded.parent_hash,timestamp=excluded.timestamp,canonical=1""",
                (chain_id, number, block["hash"], block["parentHash"], int(block["timestamp"], 16)))
            self.db.execute("DELETE FROM transactions WHERE chain_id=? AND block_number=?", (chain_id, number))
            self.db.execute("DELETE FROM logs WHERE chain_id=? AND block_number=?", (chain_id, number))
            for index, tx in enumerate(block.get("transactions", [])):
                self.db.execute("""INSERT INTO transactions VALUES(?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(chain_id,hash) DO UPDATE SET block_number=excluded.block_number,
                    block_hash=excluded.block_hash,tx_index=excluded.tx_index,sender=excluded.sender,
                    recipient=excluded.recipient,value=excluded.value,input_data=excluded.input_data""",
                    (chain_id, tx["hash"], number, block["hash"], int(tx.get("transactionIndex", hex(index)), 16),
                     tx.get("from"), tx.get("to"), tx.get("value", "0x0"), tx.get("input", "0x")))
            by_tx = {receipt["transactionHash"]: receipt for receipt in receipts}
            receipt_logs = [log for receipt in receipts for log in receipt.get("logs", [])]
            # Use receipts as the authoritative source for transaction logs.
            selected_logs = receipt_logs if by_tx else logs
            for log in selected_logs:
                self.db.execute("INSERT OR REPLACE INTO logs VALUES(?,?,?,?,?,?,?,?,?)", (
                    chain_id, log["transactionHash"], int(log["logIndex"], 16), number,
                    log["blockHash"], log["address"], json.dumps(log.get("topics", [])),
                    log.get("data", "0x"), int(bool(log.get("removed", False)))))
            self.db.execute("""INSERT INTO checkpoints VALUES(?,?,?) ON CONFLICT(chain_id)
                DO UPDATE SET block_number=excluded.block_number,block_hash=excluded.block_hash
                WHERE checkpoints.block_number <= excluded.block_number""",
                (chain_id, number, block["hash"]))

    def rollback_from(self, chain_id: int, number: int) -> None:
        with self.db:
            self.db.execute("DELETE FROM blocks WHERE chain_id=? AND number>=?", (chain_id, number))
            previous = self.db.execute("SELECT number,hash FROM blocks WHERE chain_id=? AND number<? ORDER BY number DESC LIMIT 1",
                                       (chain_id, number)).fetchone()
            if previous:
                self.db.execute("UPDATE checkpoints SET block_number=?, block_hash=? WHERE chain_id=?",
                                (previous["number"], previous["hash"], chain_id))
            else:
                self.db.execute("DELETE FROM checkpoints WHERE chain_id=?", (chain_id,))

    def count(self, table: str, chain_id: int) -> int:
        if table not in {"blocks", "transactions", "logs"}:
            raise ValueError("unsupported table")
        return self.db.execute(f"SELECT COUNT(*) FROM {table} WHERE chain_id=?", (chain_id,)).fetchone()[0]

    def close(self) -> None:
        self.db.close()
