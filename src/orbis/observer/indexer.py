"""Bounded, restart-safe incremental block ingestion."""

from __future__ import annotations

import logging
from typing import Any, Protocol

from orbis.chain.rpc import RpcClient
from orbis.network import NetworkContext, TrustState, verified_context


class ObserverStore(Protocol):
    """Persistence boundary used by the indexer; implementations own atomic commits."""

    def checkpoint(self, context: NetworkContext) -> tuple[int, str] | None: ...
    def block_hash(self, context: NetworkContext, number: int) -> str | None: ...
    def commit_block(self, context: NetworkContext, block: dict[str, Any], receipts: list[dict[str, Any]],
                     logs: list[dict[str, Any]]) -> None: ...
    def rollback_from(self, context: NetworkContext, number: int) -> None: ...

logger = logging.getLogger(__name__)


class Indexer:
    def __init__(self, rpc: RpcClient, store: ObserverStore, chain_id: int,
                 confirmation_depth: int = 0, batch_size: int = 10) -> None:
        self.rpc = rpc
        self.store = store
        self.chain_id = chain_id
        self.network_context: NetworkContext | None = None
        self.confirmation_depth = confirmation_depth
        self.batch_size = batch_size

    def verify_network(self) -> dict[str, int | str]:
        actual = self.rpc.chain_id()
        if actual != self.chain_id:
            raise ValueError(f"Configured chain ID {self.chain_id} does not match RPC chain ID {actual}")
        # This verification runs before the first checkpoint lookup or write.
        self.network_context = verified_context(actual, self.rpc.genesis_hash())
        head = self.rpc.block_number()
        return {"chain_id": actual, "head_block": head, "provider_status": "healthy",
                "network_fingerprint": self.network_context.network_fingerprint}

    def _repair_checkpoint(self, checkpoint: tuple[int, str]) -> tuple[int, str] | None:
        network = self._store_network()
        number, expected_hash = checkpoint
        remote = self.rpc.block(number)
        if remote and remote.get("hash", "").lower() == expected_hash.lower():
            return checkpoint
        logger.warning("Reorg detected at checkpoint %s", number)
        ancestor = self._common_ancestor(number - 1)
        self.store.rollback_from(network, ancestor + 1)
        return self.store.checkpoint(network)

    def _common_ancestor(self, from_number: int) -> int:
        network = self._store_network()
        for number in range(from_number, -1, -1):
            local_hash = self.store.block_hash(network, number)
            remote = self.rpc.block(number)
            if local_hash and remote and local_hash.lower() == remote.get("hash", "").lower():
                return number
        return -1

    def _store_network(self):
        if self.network_context is None:
            raise RuntimeError("network context has not been verified")
        if getattr(self.store, "supports_unresolved_single_profile", False):
            return self.chain_id
        if self.network_context.state is not TrustState.TRUSTED:
            raise RuntimeError("network context has not been resolved")
        return self.network_context

    def sync(self, start_block: int | None = None, end_block: int | None = None) -> dict[str, int]:
        network = self.verify_network()
        if self.network_context is None or self.network_context.state is TrustState.UNTRUSTED:
            raise ValueError("network identity has not been verified")
        if not getattr(self.store, "supports_unresolved_single_profile", False):
            if not callable(getattr(self.store, "resolve_network", None)):
                raise RuntimeError("registry-backed store lacks exact NetworkContext resolution")
            self.network_context = self.store.resolve_network(self.network_context)
        network_context = self._store_network()
        safe_head = max(0, network["head_block"] - self.confirmation_depth)
        target = min(safe_head, end_block) if end_block is not None else safe_head
        checkpoint = self.store.checkpoint(network_context)
        if checkpoint:
            checkpoint = self._repair_checkpoint(checkpoint)
        if checkpoint:
            next_block = checkpoint[0] + 1
        elif start_block is not None:
            next_block = start_block
        else:
            raise ValueError("A start block is required when this chain has no stored checkpoint")
        if next_block < 0:
            raise ValueError("start block must be non-negative")

        processed = 0
        while next_block <= target:
            batch_end = min(target, next_block + self.batch_size - 1)
            for number in range(next_block, batch_end + 1):
                block = self.rpc.block(number)
                if block is None:
                    raise RuntimeError(f"RPC returned no block for height {number}")
                self._validate_block(block, number)
                prior = self.store.checkpoint(network_context)
                if prior and block.get("parentHash", "").lower() != prior[1].lower():
                    # Discard the forked suffix and replay this height.
                    ancestor = self._common_ancestor(prior[0])
                    if ancestor < 0:
                        raise RuntimeError(f"No common ancestor found before block {number}; refusing cursor advance")
                    self.store.rollback_from(network_context, ancestor + 1)
                    prior = self.store.checkpoint(network_context)
                    if prior and block.get("parentHash", "").lower() != prior[1].lower():
                        raise RuntimeError(f"Cannot find canonical parent for block {number}; refusing cursor advance")
                transactions = block.get("transactions", [])
                if transactions and not isinstance(transactions[0], dict):
                    raise RuntimeError("RPC block omitted full transaction objects")
                receipts = []
                for tx in transactions:
                    receipt = self.rpc.receipt(tx["hash"])
                    if receipt is None:
                        raise RuntimeError(f"RPC returned no receipt for transaction {tx['hash']}")
                    self._validate_receipt(receipt, tx, block, number)
                    receipts.append(receipt)
                # Block facts, transactions, receipt logs and checkpoint commit atomically.
                self.store.commit_block(network_context, block, receipts, [])
                processed += 1
                logger.info("Indexed block %s (%s transactions)", number, len(transactions))
            next_block = batch_end + 1
        checkpoint = self.store.checkpoint(network_context)
        return {"chain_id": self.chain_id, "head_block": network["head_block"],
                "provider_status": network["provider_status"],
                "safe_head": safe_head, "indexed_blocks": processed,
                "checkpoint_block": checkpoint[0] if checkpoint else -1}

    @staticmethod
    def _quantity(value: Any, field: str) -> int:
        if not isinstance(value, str) or not value.startswith("0x"):
            raise RuntimeError(f"RPC returned invalid {field}")
        try:
            return int(value, 16)
        except ValueError as exc:
            raise RuntimeError(f"RPC returned invalid {field}") from exc

    @classmethod
    def _validate_block(cls, block: dict[str, Any], expected_number: int) -> None:
        if not isinstance(block, dict):
            raise RuntimeError("RPC returned malformed block")
        if cls._quantity(block.get("number"), "block number") != expected_number:
            raise RuntimeError(f"RPC returned wrong block number for height {expected_number}")
        for field in ("hash", "parentHash"):
            if not isinstance(block.get(field), str) or not block[field].startswith("0x"):
                raise RuntimeError(f"RPC returned invalid block {field}")
        cls._quantity(block.get("timestamp"), "block timestamp")
        txs = block.get("transactions")
        if not isinstance(txs, list) or any(
            not isinstance(tx, dict) or not isinstance(tx.get("hash"), str)
            or not tx["hash"].startswith("0x") for tx in txs
        ):
            raise RuntimeError("RPC block omitted complete transaction objects")

    @classmethod
    def _validate_receipt(cls, receipt: dict[str, Any], tx: dict[str, Any],
                          block: dict[str, Any], number: int) -> None:
        if not isinstance(receipt, dict):
            raise RuntimeError(f"RPC returned malformed receipt for transaction {tx['hash']}")
        receipt_tx_hash = receipt.get("transactionHash")
        if not isinstance(receipt_tx_hash, str) or receipt_tx_hash.lower() != tx["hash"].lower():
            raise RuntimeError(f"RPC returned mismatched receipt for transaction {tx['hash']}")
        if cls._quantity(receipt.get("blockNumber"), "receipt block number") != number:
            raise RuntimeError(f"RPC returned receipt for wrong block: transaction {tx['hash']}")
        receipt_block_hash = receipt.get("blockHash")
        if not isinstance(receipt_block_hash, str) or receipt_block_hash.lower() != block["hash"].lower():
            raise RuntimeError(f"RPC returned receipt with wrong block hash: transaction {tx['hash']}")
        logs = receipt.get("logs")
        if not isinstance(logs, list):
            raise RuntimeError(f"RPC returned invalid receipt logs for transaction {tx['hash']}")
        for log in logs:
            log_tx_hash = log.get("transactionHash") if isinstance(log, dict) else None
            log_block_hash = log.get("blockHash") if isinstance(log, dict) else None
            if (not isinstance(log, dict)
                    or not isinstance(log_tx_hash, str) or log_tx_hash.lower() != tx["hash"].lower()
                    or not isinstance(log_block_hash, str) or log_block_hash.lower() != block["hash"].lower()
                    or cls._quantity(log.get("blockNumber"), "log block number") != number
                    or not isinstance(log.get("logIndex"), str)
                    or not isinstance(log.get("address"), str)
                    or not isinstance(log.get("topics"), list)
                    or not isinstance(log.get("data"), str)):
                raise RuntimeError(f"RPC returned malformed or mismatched log for transaction {tx['hash']}")
