"""Real PostgreSQL tests. Set ORBIS_TEST_DATABASE_URL to a disposable database."""

from __future__ import annotations

import os
import unittest
from uuid import uuid4


@unittest.skipUnless(os.environ.get("ORBIS_TEST_DATABASE_URL"), "requires ORBIS_TEST_DATABASE_URL and a running PostgreSQL server")
class PostgresIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        cls.psycopg = psycopg
        cls.schema = "orbis_test_" + uuid4().hex
        with psycopg.connect(os.environ["ORBIS_TEST_DATABASE_URL"]) as db:
            db.execute(psycopg.sql.SQL("CREATE SCHEMA {}").format(psycopg.sql.Identifier(cls.schema)))
        from orbis.observer.postgres import PostgresStore
        cls.store = PostgresStore(os.environ["ORBIS_TEST_DATABASE_URL"], schema=cls.schema)
        cls.store.migrate()

    @classmethod
    def tearDownClass(cls):
        cls.store.close()
        with cls.psycopg.connect(os.environ["ORBIS_TEST_DATABASE_URL"]) as db:
            db.execute(cls.psycopg.sql.SQL("DROP SCHEMA {} CASCADE").format(cls.psycopg.sql.Identifier(cls.schema)))

    def test_block_facts_receipts_logs_checkpoint_replay_and_rollback(self):
        block = {"number": "0x1", "hash": "0xblock1", "parentHash": "0xparent", "timestamp": "0x10",
                 "transactions": [{"hash": "0xtx1", "from": "0xa", "to": "0xb", "value": "0x2", "input": "0x", "transactionIndex": "0x0"}]}
        receipt = {"transactionHash": "0xtx1", "blockNumber": "0x1", "blockHash": "0xblock1", "status": "0x1", "gasUsed": "0x5208",
                   "logs": [{"transactionHash": "0xtx1", "blockNumber": "0x1", "blockHash": "0xblock1", "logIndex": "0x0", "address": "0xc", "topics": [], "data": "0x"}]}
        self.store.commit_block(1874, block, [receipt], [])
        self.store.commit_block(1874, block, [receipt], [])
        self.assertEqual(self.store.checkpoint(1874), (1, "0xblock1"))
        for table in ("blocks", "transactions", "receipts", "logs"):
            self.assertEqual(self.store.count(table, 1874), 1)
        self.assertEqual(
            self.store.db.execute("SELECT value FROM transactions WHERE hash='0xtx1'").fetchone()["value"],
            "0x2",
        )
        receipt_row = self.store.db.execute("SELECT status,raw->>'transactionHash' AS tx_hash FROM receipts WHERE transaction_hash='0xtx1'").fetchone()
        self.assertEqual((receipt_row["status"], receipt_row["tx_hash"]), (1, "0xtx1"))
        self.assertEqual(self.store.db.execute("SELECT address FROM logs WHERE transaction_hash='0xtx1'").fetchone()["address"], "0xc")
        with self.assertRaises(self.psycopg.errors.ForeignKeyViolation):
            with self.store.db.transaction():
                self.store.db.execute("INSERT INTO transactions VALUES(999,'0xbad',1,'0xmissing',0,NULL,NULL,'0x0','0x')")
        self.store.rollback_from(1874, 1)
        self.assertIsNone(self.store.checkpoint(1874))
        for table in ("blocks", "transactions", "receipts", "logs"):
            self.assertEqual(self.store.count(table, 1874), 0)

    def test_reopen_recovers_checkpoint_and_reorg_can_replay(self):
        genesis = {"number": "0x0", "hash": "0xgenesis", "parentHash": "0xzero", "timestamp": "0x10", "transactions": []}
        old = {"number": "0x1", "hash": "0xold", "parentHash": "0xgenesis", "timestamp": "0x11", "transactions": []}
        new = {"number": "0x1", "hash": "0xnew", "parentHash": "0xgenesis", "timestamp": "0x12", "transactions": []}
        self.store.commit_block(1875, genesis, [], [])
        self.store.commit_block(1875, old, [], [])
        schema = self.schema
        self.store.close()
        from orbis.observer.postgres import PostgresStore
        type(self).store = PostgresStore(os.environ["ORBIS_TEST_DATABASE_URL"], schema=schema)
        self.store.migrate()  # migration startup is idempotent
        self.assertEqual(self.store.checkpoint(1875), (1, "0xold"))
        self.store.rollback_from(1875, 1)
        self.store.commit_block(1875, new, [], [])
        self.assertEqual(self.store.checkpoint(1875), (1, "0xnew"))
        self.store.commit_block(1875, genesis, [], [])  # replaying older data cannot regress cursor
        self.assertEqual(self.store.checkpoint(1875), (1, "0xnew"))
        self.assertEqual(self.store.count("blocks", 1875), 2)

    def test_indexer_reorganization_replay_with_postgres_store(self):
        from orbis.observer.indexer import Indexer

        def block(number, block_hash, parent_hash):
            return {"number": hex(number), "hash": block_hash, "parentHash": parent_hash,
                    "timestamp": hex(100 + number), "transactions": []}

        genesis = block(0, "0xg", "0x0")
        old1, old2 = block(1, "0xold1", "0xg"), block(2, "0xold2", "0xold1")
        new1, new2 = block(1, "0xnew1", "0xg"), block(2, "0xnew2", "0xnew1")

        class RpcFixture:
            def __init__(self, blocks): self.blocks = blocks
            def chain_id(self): return 1880
            def block_number(self): return max(self.blocks)
            def block(self, number): return self.blocks.get(number)
            def receipt(self, tx_hash): raise AssertionError("empty test blocks have no receipts")

        rpc = RpcFixture({0: genesis, 1: old1, 2: old2})
        indexer = Indexer(rpc, self.store, 1880, confirmation_depth=0, batch_size=3)
        indexer.sync(start_block=0)
        rpc.blocks = {0: genesis, 1: new1, 2: new2}
        result = indexer.sync()
        self.assertEqual(result["indexed_blocks"], 2)
        self.assertEqual(self.store.checkpoint(1880), (2, "0xnew2"))
        self.assertEqual(self.store.block_hash(1880, 1), "0xnew1")
        self.assertEqual(self.store.count("blocks", 1880), 3)

    def test_unique_constraints_reject_duplicate_transaction_hash(self):
        block = {"number": "0x3", "hash": "0xblock3", "parentHash": "0xparent", "timestamp": "0x10",
                 "transactions": [{"hash": "0xtx3", "transactionIndex": "0x0"},
                                  {"hash": "0xtx3", "transactionIndex": "0x1"}]}
        with self.assertRaisesRegex(ValueError, "duplicate transaction hash"):
            self.store.commit_block(1876, block, [], [])
        self.assertIsNone(self.store.checkpoint(1876))
        self.assertEqual(self.store.count("blocks", 1876), 0)
        block["transactions"] = [block["transactions"][0]]
        self.store.commit_block(1876, block, [], [])
        network_id = self.store.db.execute("SELECT network_id FROM networks WHERE chain_id=1876").fetchone()["network_id"]
        with self.assertRaises(self.psycopg.errors.UniqueViolation):
            with self.store.db.transaction():
                self.store.db.execute("""INSERT INTO transactions VALUES(%s,%s,%s,%s,%s,NULL,NULL,'0x0','0x')""",
                                      (network_id, "0xtx3", 3, "0xblock3", 1))

    def test_entity_observation_evidence_relationships_and_reorg_guard(self):
        block = {"number": "0x9", "hash": "0xevidence-block", "parentHash": "0xparent", "timestamp": "0x19",
                 "transactions": [{"hash": "0xevidence-tx", "transactionIndex": "0x0"}]}
        log = {"transactionHash": "0xevidence-tx", "blockNumber": "0x9", "blockHash": "0xevidence-block",
               "logIndex": "0x0", "address": "0xcontract", "topics": [], "data": "0x"}
        receipt = {"transactionHash": "0xevidence-tx", "blockNumber": "0x9", "blockHash": "0xevidence-block",
                   "status": "0x1", "logs": [log]}
        self.store.commit_block(1878, block, [receipt], [])
        network_id = self.store.db.execute("SELECT network_id FROM networks WHERE chain_id=1878").fetchone()["network_id"]
        entity = self.store.db.execute("""INSERT INTO entities(network_id,address,entity_type,confidence)
            VALUES(%s,'0xcontract','contract',0.75) RETURNING entity_id""", (network_id,)).fetchone()
        observation = self.store.db.execute("""INSERT INTO observations(network_id,entity_id,observation_type,severity,rule_id,rule_version)
            VALUES(%s,%s,'sample_event','low','test-rule','1.0.0') RETURNING observation_id""",
            (network_id, entity["entity_id"])).fetchone()
        self.store.db.execute("""INSERT INTO evidence_refs(network_id,observation_id,block_number,block_hash,transaction_hash,log_index)
            VALUES(%s,%s,9,'0xevidence-block','0xevidence-tx',0)""", (network_id, observation["observation_id"]))
        self.assertEqual(self.store.db.execute("SELECT count(*) AS n FROM evidence_refs WHERE observation_id=%s",
                                               (observation["observation_id"],)).fetchone()["n"], 1)
        # Source evidence constrains rollback; it cannot be silently orphaned by reorg deletion.
        with self.assertRaises(self.psycopg.errors.RestrictViolation):
            self.store.rollback_from(1878, 9)
        self.assertEqual(self.store.checkpoint(1878), (9, "0xevidence-block"))
        self.store.db.execute("DELETE FROM observations WHERE observation_id=%s", (observation["observation_id"],))
        self.store.rollback_from(1878, 9)
        self.assertIsNone(self.store.checkpoint(1878))

    def test_uncommitted_block_and_checkpoint_are_invisible_until_commit(self):
        reader = self.psycopg.connect(os.environ["ORBIS_TEST_DATABASE_URL"], options=f"-c search_path={self.schema}", autocommit=True)
        try:
            with self.store.db.transaction():
                network_id = self.store._network_id(1879)
                self.store.db.execute("INSERT INTO blocks(network_id,number,hash,parent_hash,timestamp) VALUES(%s,4,'0xisolated','0xparent',20)", (network_id,))
                self.store.db.execute("INSERT INTO checkpoints VALUES(%s,4,'0xisolated')", (network_id,))
                visible = reader.execute("SELECT count(*) FROM networks WHERE chain_id=1879").fetchone()[0]
                self.assertEqual(visible, 0)
            self.assertEqual(reader.execute("SELECT count(*) FROM blocks WHERE hash='0xisolated'").fetchone()[0], 1)
            self.assertEqual(self.store.checkpoint(1879), (4, "0xisolated"))
        finally:
            reader.close()
        self.store.rollback_from(1879, 0)

    def test_knowledge_ingestion_normalization_idempotency_queries_and_reorg(self):
        from orbis.knowledge import KnowledgeService, normalize_address
        address_a = "0x" + "a" * 40
        address_b = "0x" + "b" * 40
        self.store.commit_block(1881, {"number":"0x1","hash":"0xk1","parentHash":"0x0","timestamp":"0x64",
            "transactions":[{"hash":"0xktx","from":address_a.upper().replace("0X","0x"),"to":address_b,
            "transactionIndex":"0x0"},{"hash":"0xktx2","from":address_a,"to":address_b,
            "transactionIndex":"0x1"}]}, [{"transactionHash":"0xktx","blockNumber":"0x1","blockHash":"0xk1",
            "status":"0x1","logs":[]},{"transactionHash":"0xktx2","blockNumber":"0x1","blockHash":"0xk1",
            "status":"0x1","logs":[]}], [])
        knowledge = KnowledgeService(self.store)
        self.assertEqual(normalize_address(address_a.upper().replace("0X","0x")),address_a)
        self.assertEqual(knowledge.ingest(1881),2)
        self.assertEqual(knowledge.ingest(1881),2)
        self.assertEqual(knowledge.get_entity(1881,address_a.upper().replace("0X","0x"))["address"],address_a)
        self.assertEqual(len(knowledge.observations(1881,address_a)),2)
        self.assertEqual(len(knowledge.observations(1881,address_a,limit=1,offset=1)),1)
        rels=knowledge.relationships(1881,address_a)
        self.assertEqual(len(rels),1)
        self.assertEqual(len(knowledge.relationship_evidence(1881,rels[0]["relationship_id"])),2)
        self.assertIsNone(knowledge.get_entity(1882,address_a))
        with self.assertRaises(ValueError): normalize_address("0xnot-an-address")
        self.store.rollback_from(1881,1)
        self.assertEqual(knowledge.observations(1881,address_a),[])
        self.assertEqual(knowledge.relationships(1881,address_a),[])
        self.store.commit_block(1881,{"number":"0x1","hash":"0xk1new","parentHash":"0x0","timestamp":"0x65",
            "transactions":[{"hash":"0xktnew","from":address_a,"to":address_b,"transactionIndex":"0x0"}]},
            [{"transactionHash":"0xktnew","blockNumber":"0x1","blockHash":"0xk1new","status":"0x1","logs":[]}],[])
        self.assertEqual(knowledge.ingest(1881),1)
        self.assertEqual(len(knowledge.observations(1881,address_a)),1)

    def test_failed_knowledge_batch_rolls_back_all_enrichment(self):
        from orbis.knowledge import KnowledgeService
        good="0x"+"c"*40
        bad="0xnot-valid"
        self.store.commit_block(1883,{"number":"0x1","hash":"0xkb1","parentHash":"0x0","timestamp":"0x1",
            "transactions":[{"hash":"0xktbad","from":good,"to":bad,"transactionIndex":"0x0"}]},
            [{"transactionHash":"0xktbad","blockNumber":"0x1","blockHash":"0xkb1","status":"0x1","logs":[]}],[])
        knowledge=KnowledgeService(self.store)
        with self.assertRaises(ValueError): knowledge.ingest(1883)
        net=self.store.db.execute("SELECT network_id FROM networks WHERE chain_id=1883").fetchone()["network_id"]
        self.assertEqual(self.store.db.execute("SELECT count(*) c FROM entities WHERE network_id=%s",(net,)).fetchone()["c"],0)
        self.assertEqual(self.store.db.execute("SELECT count(*) c FROM observations WHERE network_id=%s",(net,)).fetchone()["c"],0)

    def test_failed_block_write_does_not_advance_checkpoint(self):
        block = {"number": "0x2", "hash": "0xblock2", "parentHash": "0xparent", "timestamp": "0x10",
                 "transactions": [{"hash": "0xtx-bad", "transactionIndex": "0x0"}]}
        invalid_receipt = {"transactionHash": "0xtx-bad", "blockHash": "0xblock2", "unexpected": object(), "logs": []}
        with self.assertRaises(TypeError):
            self.store.commit_block(1877, block, [invalid_receipt], [])
        self.assertIsNone(self.store.checkpoint(1877))
        self.assertEqual(self.store.count("blocks", 1877), 0)
        self.assertEqual(self.store.count("transactions", 1877), 0)


if __name__ == "__main__":
    unittest.main()
