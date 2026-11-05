from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from orbis.observer.indexer import Indexer
from orbis.observer.store import SqliteStore
from orbis.network import TrustState


def hx(value: int) -> str:
    return hex(value)


def make_block(number: int, parent: str, suffix: str = "a", transactions=None):
    return {"number": hx(number), "hash": f"0x{number:02x}{suffix}", "parentHash": parent,
            "timestamp": hx(1_700_000_000 + number), "transactions": transactions or []}


class FakeRpc:
    def __init__(self, blocks, chain_id=1874):
        self.blocks = blocks
        self.expected_chain_id = chain_id
        self.receipts = {}

    def chain_id(self):
        return self.expected_chain_id

    def block_number(self):
        return max(self.blocks)

    def genesis_hash(self):
        return "0x" + "ab" * 32

    def block(self, number):
        return self.blocks.get(number)

    def receipt(self, tx_hash):
        return self.receipts.get(tx_hash)


class ObserverTests(unittest.TestCase):
    def setUp(self):
        self.store = SqliteStore(":memory:")

    def tearDown(self):
        self.store.close()

    def test_verifies_chain_and_indexes_with_durable_checkpoint(self):
        genesis = make_block(0, "0x00")
        one = make_block(1, genesis["hash"])
        rpc = FakeRpc({0: genesis, 1: one})
        indexer = Indexer(rpc, self.store, 1874, confirmation_depth=0, batch_size=1)
        result = indexer.sync(start_block=0)
        self.assertEqual(result["indexed_blocks"], 2)
        self.assertEqual(indexer.network_context.state, TrustState.UNRESOLVED)
        self.assertEqual(result["provider_status"], "healthy")
        self.assertEqual(self.store.checkpoint(1874), (1, one["hash"]))
        self.assertEqual(self.store.count("blocks", 1874), 2)
        replay = indexer.sync(start_block=0)
        self.assertEqual(replay["indexed_blocks"], 0)
        self.assertEqual(self.store.count("blocks", 1874), 2)

    def test_rejects_wrong_chain(self):
        rpc = FakeRpc({0: make_block(0, "0x00")}, chain_id=2625)
        with self.assertRaisesRegex(ValueError, "does not match"):
            Indexer(rpc, self.store, 1874).sync(start_block=0)

    def test_refuses_registry_backed_operations_without_exact_resolution(self):
        class RegistryRequiredStore:
            def checkpoint(self, chain_id):
                raise AssertionError("must refuse before selecting a checkpoint")

        rpc = FakeRpc({0: make_block(0, "0x00")})
        with self.assertRaisesRegex(RuntimeError, "lacks exact NetworkContext resolution"):
            Indexer(rpc, RegistryRequiredStore(), 1874).sync(start_block=0)

    def test_does_not_advance_checkpoint_when_receipt_is_missing(self):
        genesis = make_block(0, "0x00")
        tx = {"hash": "0xtx", "from": "0xa", "to": "0xb", "value": "0x1", "input": "0x"}
        one = make_block(1, genesis["hash"], transactions=[tx])
        rpc = FakeRpc({0: genesis, 1: one})
        with self.assertRaisesRegex(RuntimeError, "no receipt"):
            Indexer(rpc, self.store, 1874, confirmation_depth=0).sync(start_block=0)
        self.assertEqual(self.store.checkpoint(1874), (0, genesis["hash"]))

    def test_rejects_receipt_for_wrong_transaction_before_persisting_block(self):
        genesis = make_block(0, "0x00")
        tx = {"hash": "0xtx", "from": "0xa", "to": "0xb", "value": "0x1", "input": "0x"}
        one = make_block(1, genesis["hash"], transactions=[tx])
        rpc = FakeRpc({0: genesis, 1: one})
        rpc.receipts[tx["hash"]] = {
            "transactionHash": "0xother", "blockNumber": "0x1", "blockHash": one["hash"], "logs": []
        }
        indexer = Indexer(rpc, self.store, 1874, confirmation_depth=0)
        with self.assertRaisesRegex(RuntimeError, "mismatched receipt"):
            indexer.sync(start_block=0)
        self.assertEqual(self.store.checkpoint(1874), (0, genesis["hash"]))
        self.assertEqual(self.store.count("transactions", 1874), 0)

    def test_whitechain_requires_receipt_status_without_changing_other_profile_contract(self):
        block = make_block(1, "0x00")
        tx = {"hash": "0xtx"}
        receipt = {"transactionHash": "0xtx", "blockNumber": "0x1", "blockHash": block["hash"], "logs": []}
        Indexer._validate_receipt(Indexer(FakeRpc({1: block}), self.store, 1), receipt, tx, block, 1)
        with self.assertRaisesRegex(RuntimeError, "lacks required status"):
            Indexer(FakeRpc({1: block}), self.store, 1874)._validate_receipt(receipt, tx, block, 1)
        receipt["status"] = "0x2"
        with self.assertRaisesRegex(RuntimeError, "invalid receipt status"):
            Indexer(FakeRpc({1: block}), self.store, 1874)._validate_receipt(receipt, tx, block, 1)

    def test_missing_whitechain_receipt_status_cannot_advance_checkpoint(self):
        genesis = make_block(0, "0x00")
        tx = {"hash": "0x01", "from": "0x11", "to": "0x22", "value": "0x0", "input": "0x"}
        block = make_block(1, genesis["hash"], transactions=[tx])
        rpc = FakeRpc({0: genesis, 1: block})
        rpc.receipts[tx["hash"]] = {"transactionHash": tx["hash"], "blockNumber": "0x1",
                                     "blockHash": block["hash"], "logs": []}
        with self.assertRaisesRegex(RuntimeError, "lacks required status"):
            Indexer(rpc, self.store, 1874, confirmation_depth=0).sync(start_block=0)
        self.assertEqual(self.store.checkpoint(1874), (0, genesis["hash"]))

    def test_rejects_block_at_wrong_height_before_persistence(self):
        wrong = make_block(1, "0x00")
        rpc = FakeRpc({1: make_block(2, wrong["hash"])})
        with self.assertRaisesRegex(RuntimeError, "wrong block number"):
            Indexer(rpc, self.store, 1874, confirmation_depth=0).sync(start_block=1)
        self.assertIsNone(self.store.checkpoint(1874))

    def test_checkpoint_survives_store_close_and_reopen(self):
        genesis = make_block(0, "0x00")
        with TemporaryDirectory() as directory:
            path = str(Path(directory) / "observer.sqlite3")
            first = SqliteStore(path)
            first.commit_block(1874, genesis, [], [])
            first.close()
            reopened = SqliteStore(path)
            try:
                self.assertEqual(reopened.checkpoint(1874), (0, genesis["hash"]))
            finally:
                reopened.close()

    def test_rollback_removes_transactions_and_logs_with_their_block(self):
        genesis = make_block(0, "0x00")
        tx_hash = "0xtx"
        block = make_block(1, genesis["hash"], transactions=[
            {"hash": tx_hash, "from": "0xa", "to": "0xb", "value": "0x1", "input": "0x"}
        ])
        receipt = {"transactionHash": tx_hash, "blockNumber": "0x1", "blockHash": block["hash"],
                   "logs": [{"transactionHash": tx_hash, "blockNumber": "0x1", "blockHash": block["hash"],
                             "logIndex": "0x0", "address": "0xc", "topics": [], "data": "0x"}]}
        self.store.commit_block(1874, genesis, [], [])
        self.store.commit_block(1874, block, [receipt], [])
        self.assertEqual(self.store.count("transactions", 1874), 1)
        self.assertEqual(self.store.count("logs", 1874), 1)
        self.store.rollback_from(1874, 1)
        self.assertEqual(self.store.count("transactions", 1874), 0)
        self.assertEqual(self.store.count("logs", 1874), 0)
        self.assertEqual(self.store.checkpoint(1874), (0, genesis["hash"]))

    def test_rolls_back_and_replays_reorganized_suffix(self):
        genesis = make_block(0, "0x00")
        old_one = make_block(1, genesis["hash"], "old")
        old_two = make_block(2, old_one["hash"], "old")
        rpc = FakeRpc({0: genesis, 1: old_one, 2: old_two})
        indexer = Indexer(rpc, self.store, 1874, confirmation_depth=0)
        indexer.sync(start_block=0)

        new_one = make_block(1, genesis["hash"], "new")
        new_two = make_block(2, new_one["hash"], "new")
        rpc.blocks = {0: genesis, 1: new_one, 2: new_two}
        result = indexer.sync(start_block=0)
        self.assertEqual(result["indexed_blocks"], 2)
        self.assertEqual(self.store.checkpoint(1874), (2, new_two["hash"]))
        self.assertEqual(self.store.count("blocks", 1874), 3)


if __name__ == "__main__":
    unittest.main()
