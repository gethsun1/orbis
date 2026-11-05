"""Bounded canonical source retrieval for PostgreSQL-backed evaluation callers."""


class ContextRepository:
    def __init__(self, connection): self.db = connection

    def block_manifest(self, network_id: int, from_block: int, to_block: int) -> list[dict]:
        if from_block < 0 or to_block < from_block: raise ValueError("invalid explicit block bounds")
        rows = self.db.execute("""SELECT number,hash,parent_hash,timestamp,expected_transaction_count FROM blocks
            WHERE network_id=%s AND number BETWEEN %s AND %s AND canonical ORDER BY number""",
            (network_id,from_block,to_block)).fetchall()
        return [dict(row) for row in rows]

    def logs(self, network_id: int, from_block: int, to_block: int) -> list[dict]:
        if from_block < 0 or to_block < from_block: raise ValueError("invalid explicit block bounds")
        rows = self.db.execute("""SELECT l.block_number,l.block_hash,l.transaction_hash,l.log_index,l.address,l.topics,l.data
            FROM logs l JOIN blocks b ON (b.network_id,b.number,b.hash)=(l.network_id,l.block_number,l.block_hash)
            WHERE l.network_id=%s AND l.block_number BETWEEN %s AND %s AND b.canonical AND NOT l.removed
            ORDER BY l.block_number,l.transaction_hash,l.log_index""",(network_id,from_block,to_block)).fetchall()
        return [dict(row) for row in rows]

    def range_completeness(self, network_id: int, from_block: int, to_block: int) -> dict:
        """Assess persisted provenance for an inclusive range; never infer absent history."""
        manifest = self.block_manifest(network_id, from_block, to_block)
        expected_numbers = list(range(from_block, to_block + 1))
        by_number = {row["number"]: row for row in manifest}
        missing_blocks = [n for n in expected_numbers if n not in by_number]
        discontinuities = []
        prior = None
        for row in manifest:
            if prior is not None and row["parent_hash"].lower() != prior["hash"].lower():
                discontinuities.append(row["number"])
            prior = row
        tx_rows = self.db.execute("""SELECT t.hash,t.block_number,t.block_hash,r.transaction_hash AS receipt_hash,
                r.block_hash AS receipt_block_hash,r.status,r.raw
            FROM transactions t JOIN blocks b ON (b.network_id,b.number,b.hash)=(t.network_id,t.block_number,t.block_hash)
            LEFT JOIN receipts r ON (r.network_id,r.transaction_hash)=(t.network_id,t.hash)
            WHERE t.network_id=%s AND t.block_number BETWEEN %s AND %s AND b.canonical
            ORDER BY t.block_number,t.tx_index""", (network_id, from_block, to_block)).fetchall()
        expected_tx = sum(row["expected_transaction_count"] or 0 for row in manifest)
        unknown_tx_counts = [row["number"] for row in manifest if row["expected_transaction_count"] is None]
        observed_tx = len(tx_rows)
        missing_receipts = [row["hash"] for row in tx_rows if row["receipt_hash"] is None]
        inconsistent_receipts = [row["hash"] for row in tx_rows if row["receipt_hash"] is not None and
                                 (row["receipt_hash"] != row["hash"] or row["receipt_block_hash"] != row["block_hash"])]
        missing_status = [row["hash"] for row in tx_rows if row["receipt_hash"] is not None and row["status"] not in (0, 1)]
        receipt_logs = []
        failed_receipts = []
        for row in tx_rows:
            if row["receipt_hash"] is None:
                continue
            if row["status"] == 0:
                failed_receipts.append(row["hash"])
            receipt_logs.extend((row["hash"], item) for item in
                                (row["raw"] or {}).get("logs", []) if isinstance(item, dict))
        expected_logs = len(receipt_logs)
        transaction_hashes = {row["hash"] for row in tx_rows}
        logs = self.db.execute("""SELECT l.transaction_hash,l.log_index,l.block_number,l.block_hash,l.removed
            FROM logs l JOIN blocks b ON (b.network_id,b.number,b.hash)=(l.network_id,l.block_number,l.block_hash)
            WHERE l.network_id=%s AND l.block_number BETWEEN %s AND %s AND b.canonical
            ORDER BY l.block_number,l.transaction_hash,l.log_index""", (network_id, from_block, to_block)).fetchall()
        orphan_logs = [dict(row) for row in logs if row["transaction_hash"] not in transaction_hashes]
        receipt_log_keys = set()
        malformed_receipt_logs = 0
        for tx_hash, log in receipt_logs:
            try:
                idx = log["logIndex"]
                idx = int(idx, 16) if isinstance(idx, str) else idx
                number = log["blockNumber"]
                number = int(number, 16) if isinstance(number, str) else number
                receipt_log_keys.add((tx_hash, idx, number, log["blockHash"].lower()))
            except (KeyError, TypeError, ValueError, AttributeError):
                malformed_receipt_logs += 1
        persisted_log_keys = {(r["transaction_hash"], r["log_index"], r["block_number"], r["block_hash"].lower()) for r in logs}
        missing_receipt_logs = sorted(receipt_log_keys - persisted_log_keys)
        logs_without_receipt_provenance = sorted(persisted_log_keys - receipt_log_keys)
        issues = {"missing_blocks": missing_blocks, "parent_discontinuities": discontinuities,
                  "missing_receipts": missing_receipts, "inconsistent_receipts": inconsistent_receipts,
                  "receipts_without_valid_status": missing_status, "logs_without_transaction": orphan_logs,
                  "unsuccessful_receipts": failed_receipts,
                  "missing_receipt_logs": missing_receipt_logs[:100],
                  "logs_without_receipt_provenance": logs_without_receipt_provenance[:100],
                  "malformed_receipt_logs": malformed_receipt_logs,
                  "removed_logs": sum(bool(row["removed"]) for row in logs),
                  "unknown_transaction_counts": unknown_tx_counts,
                  "transaction_count_mismatches": [] if expected_tx == observed_tx else [{"expected": expected_tx, "observed": observed_tx}],
                  "log_count_mismatches": [] if missing_receipts or expected_logs == len(logs) else [{"expected": expected_logs, "observed": len(logs)}]}
        complete = not any((missing_blocks, discontinuities, missing_receipts, inconsistent_receipts,
                            missing_status, failed_receipts, orphan_logs, missing_receipt_logs,
                            logs_without_receipt_provenance, malformed_receipt_logs, issues["removed_logs"], unknown_tx_counts, expected_tx != observed_tx,
                            issues["log_count_mismatches"]))
        return {"requested_start": from_block, "requested_end": to_block,
                "expected_blocks": len(expected_numbers), "observed_blocks": len(manifest),
                "expected_transactions": expected_tx, "observed_transactions": observed_tx,
                "expected_logs": expected_logs, "observed_logs": len(logs) - issues["removed_logs"],
                "canonical_block_hashes": [row["hash"] for row in manifest],
                "canonicality_gap_detected": bool(missing_blocks or discontinuities),
                "observed_receipts": sum(row["receipt_hash"] is not None for row in tx_rows),
                "state": "complete" if complete else "partial", "issues": issues}
