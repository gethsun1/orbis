"""Persistence-boundary validation for block records."""

from __future__ import annotations

from typing import Any


def validate_block_transactions(block: dict[str, Any]) -> None:
    """Reject ambiguous transactions before an idempotent upsert can hide them."""
    seen_hashes: set[str] = set()
    seen_indices: set[int] = set()
    for position, tx in enumerate(block.get("transactions", [])):
        tx_hash = tx.get("hash") if isinstance(tx, dict) else None
        if not isinstance(tx_hash, str) or not tx_hash.startswith("0x"):
            raise ValueError("block contains a transaction with an invalid hash")
        normalized_hash = tx_hash.lower()
        if normalized_hash in seen_hashes:
            raise ValueError(f"block contains duplicate transaction hash {tx_hash}")
        seen_hashes.add(normalized_hash)
        raw_index = tx.get("transactionIndex", hex(position))
        try:
            tx_index = int(raw_index, 16) if isinstance(raw_index, str) else int(raw_index)
        except (TypeError, ValueError) as exc:
            raise ValueError("block contains an invalid transaction index") from exc
        if tx_index in seen_indices:
            raise ValueError(f"block contains duplicate transaction index {tx_index}")
        seen_indices.add(tx_index)
