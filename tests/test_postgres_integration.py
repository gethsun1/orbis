"""Real PostgreSQL tests. Set ORBIS_TEST_DATABASE_URL to a disposable database."""

from __future__ import annotations

import os
import unittest
from uuid import uuid4
import hashlib
from tests.postgres_test_support import require_disposable_database
from orbis.network import verified_context


def setUpModule():
    require_disposable_database()


class PostgresIntegrationTests(unittest.TestCase):
    def _ctx(self, chain_id):
        contexts = getattr(self.store, "_test_network_contexts", None)
        if contexts is None:
            contexts = {}
            self.store._test_network_contexts = contexts
        if chain_id not in contexts:
            genesis = "0x" + hashlib.sha256(f"postgres-fixture:{chain_id}".encode()).hexdigest()
            contexts[chain_id] = self.store.resolve_network(verified_context(chain_id, genesis))
        return contexts[chain_id]
    @classmethod
    def setUpClass(cls):
        import psycopg
        cls.psycopg = psycopg
        cls.schema = "orbis_test_" + uuid4().hex
        with psycopg.connect(os.environ["ORBIS_TEST_DATABASE_URL"]) as db:
            db.execute(psycopg.sql.SQL("CREATE SCHEMA {}").format(psycopg.sql.Identifier(cls.schema)))
        from orbis.observer.postgres import PostgresStore
        cls.store = PostgresStore(os.environ["ORBIS_TEST_DATABASE_URL"], schema=cls.schema, runtime_fenced=False)
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
        self.store.commit_block(self._ctx(1874), block, [receipt], [])
        self.store.commit_block(self._ctx(1874), block, [receipt], [])
        self.assertEqual(self.store.checkpoint(self._ctx(1874)), (1, "0xblock1"))
        for table in ("blocks", "transactions", "receipts", "logs"):
            self.assertEqual(self.store.count(table, self._ctx(1874)), 1)
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
        self.store.rollback_from(self._ctx(1874), 1)
        self.assertIsNone(self.store.checkpoint(self._ctx(1874)))
        for table in ("blocks", "transactions", "receipts", "logs"):
            self.assertEqual(self.store.count(table, self._ctx(1874)), 0)

    def test_m4_evaluation_evidence_and_rollback_invalidation(self):
        from orbis.rules.registry import RuleRegistry
        from orbis.rules.evidence import make_item, make_envelope
        from orbis.rules.identity import evaluation_identity
        from orbis.rules.repository import EvaluationRepository
        from orbis.rules.normalization import digest
        chain=1981
        genesis={"number":"0x0","hash":"0xunrelated","parentHash":"0xparent","timestamp":"0x0","transactions":[]}
        self.store.commit_block(self._ctx(chain),genesis,[],[])
        block={"number":"0x1","hash":"0xevblock","parentHash":"0xparent","timestamp":"0x1","transactions":[]}
        self.store.commit_block(self._ctx(chain),block,[],[])
        version=RuleRegistry(self.store.db).register(rule_id="T-01",semantic_version="1.0.0",input_schema={},parameter_schema={},coverage_requirements={"required":[]})
        item=make_item(network_chain_id=chain,block_number=1,block_hash="0xevblock",source_kind="block",normalized_input={"timestamp":"1"})
        rule_doc={"rule_id":"T-01","semantic_version":"1.0.0","definition_digest":version["definition_digest"]}
        envelope=make_envelope(network_chain_id=chain,bounds={"from":1,"to":1},rule=rule_doc,parameters={},evaluator_build="test-build",coverage={},items=[item])
        context=envelope["context_digest"]
        key=evaluation_identity(chain_id=chain,subject_kind="address",subject_key="0x"+"ab"*20,rule_id=version["rule_id"],semantic_version=version["semantic_version"],definition_digest=version["definition_digest"],from_block=1,to_block=1,parameters={},context_digest=context,evaluator_build="test-build")
        network=self._ctx(chain).network_id
        repo=EvaluationRepository(self.store.db)
        evaluation=repo.create(context=self._ctx(chain), network_id=network,rule_version=version,subject_kind="address",subject_key="0x"+"ab"*20,
            from_block=1,to_block=1,parameters={},context_digest=context,evaluator_build="test-build",evaluation_key=key,
            coverage={},envelope=envelope,outcome="matched",findings=[{"result":{"kind":"test"}}])
        foreign=self.store.resolve_network(verified_context(chain,"0x"+"99"*32))
        with self.assertRaises(LookupError):
            repo.get(foreign,evaluation["evaluation_id"])
        other_item=make_item(network_chain_id=chain,block_number=0,block_hash="0xunrelated",source_kind="block",normalized_input={"timestamp":"0"})
        other_envelope=make_envelope(network_chain_id=chain,bounds={"from":0,"to":0},rule=rule_doc,parameters={},evaluator_build="test-build",coverage={},items=[other_item])
        other_key=evaluation_identity(chain_id=chain,subject_kind="address",subject_key="0x"+"ef"*20,rule_id=version["rule_id"],semantic_version=version["semantic_version"],definition_digest=version["definition_digest"],from_block=0,to_block=0,parameters={},context_digest=other_envelope["context_digest"],evaluator_build="test-build")
        unaffected=repo.create(context=self._ctx(chain), network_id=network,rule_version=version,subject_kind="address",subject_key="0x"+"ef"*20,from_block=0,to_block=0,parameters={},context_digest=other_envelope["context_digest"],evaluator_build="test-build",evaluation_key=other_key,coverage={},envelope=other_envelope,outcome="not_matched")
        self.store.rollback_from(self._ctx(chain),1)
        historical=repo.get(self._ctx(chain),evaluation["evaluation_id"])
        self.assertEqual(historical["canonicality"],"invalidated")
        self.assertEqual(len(historical["findings"]),1)
        self.assertEqual(self.store.db.execute("SELECT canonicality FROM evaluations WHERE evaluation_id=%s",(unaffected["evaluation_id"],)).fetchone()["canonicality"],"active")
        self.assertEqual(self.store.db.execute("SELECT count(*) AS n FROM evaluation_invalidations WHERE evaluation_id=%s",(evaluation["evaluation_id"],)).fetchone()["n"],1)
        self.store.rollback_from(self._ctx(chain),1)
        self.assertEqual(self.store.db.execute("SELECT count(*) AS n FROM evaluation_invalidations WHERE evaluation_id=%s",(evaluation["evaluation_id"],)).fetchone()["n"],1)
        replacement_item=make_item(network_chain_id=chain,block_number=1,block_hash="0xreplacement",source_kind="block",normalized_input={"timestamp":"2"})
        self.store.commit_block(self._ctx(chain),{"number":"0x1","hash":"0xreplacement","parentHash":"0xunrelated","timestamp":"0x2","transactions":[]},[],[])
        replacement_envelope=make_envelope(network_chain_id=chain,bounds={"from":1,"to":1},rule=rule_doc,parameters={},evaluator_build="test-build",coverage={},items=[replacement_item])
        replacement_key=evaluation_identity(chain_id=chain,subject_kind="address",subject_key="0x"+"ab"*20,rule_id=version["rule_id"],semantic_version=version["semantic_version"],definition_digest=version["definition_digest"],from_block=1,to_block=1,parameters={},context_digest=replacement_envelope["context_digest"],evaluator_build="test-build")
        self.assertNotEqual(key,replacement_key)
        replacement=repo.create(context=self._ctx(chain), network_id=network,rule_version=version,subject_kind="address",subject_key="0x"+"ab"*20,from_block=1,to_block=1,parameters={},context_digest=replacement_envelope["context_digest"],evaluator_build="test-build",evaluation_key=replacement_key,coverage={},envelope=replacement_envelope,outcome="not_matched",supersedes_evaluation_id=evaluation["evaluation_id"])
        self.assertEqual(replacement["supersedes_evaluation_id"],evaluation["evaluation_id"])

    def test_m4_invalidation_rolls_back_with_source_delete_failure(self):
        from orbis.rules.registry import RuleRegistry
        from orbis.rules.evidence import make_item, make_envelope
        from orbis.rules.identity import evaluation_identity
        from orbis.rules.repository import EvaluationRepository
        chain=1982
        block={"number":"0x1","hash":"0xfailblock","parentHash":"0xparent","timestamp":"0x1","transactions":[]}
        self.store.commit_block(self._ctx(chain),block,[],[])
        version=RuleRegistry(self.store.db).register(rule_id="T-02",semantic_version="1.0.0",input_schema={},parameter_schema={})
        item=make_item(network_chain_id=chain,block_number=1,block_hash="0xfailblock",source_kind="block",normalized_input={})
        env=make_envelope(network_chain_id=chain,bounds={"from":1,"to":1},rule={"rule_id":"T-02","semantic_version":"1.0.0","definition_digest":version["definition_digest"]},parameters={},evaluator_build="test",coverage={},items=[item])
        subject="0x"+"cd"*20
        key=evaluation_identity(chain_id=chain,subject_kind="address",subject_key=subject,rule_id=version["rule_id"],semantic_version=version["semantic_version"],definition_digest=version["definition_digest"],from_block=1,to_block=1,parameters={},context_digest=env["context_digest"],evaluator_build="test")
        network=self._ctx(chain).network_id
        ev=EvaluationRepository(self.store.db).create(context=self._ctx(chain), network_id=network,rule_version=version,subject_kind="address",subject_key=subject,from_block=1,to_block=1,parameters={},context_digest=env["context_digest"],evaluator_build="test",evaluation_key=key,coverage={},envelope=env,outcome="not_matched")
        self.store.db.execute("CREATE FUNCTION fail_m4_delete() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'injected m4 rollback failure'; END $$")
        self.store.db.execute("CREATE TRIGGER fail_m4_delete BEFORE DELETE ON blocks FOR EACH ROW EXECUTE FUNCTION fail_m4_delete()")
        try:
            with self.assertRaisesRegex(self.psycopg.Error,"injected m4 rollback failure"):
                self.store.rollback_from(self._ctx(chain),1)
        finally:
            self.store.db.execute("DROP TRIGGER fail_m4_delete ON blocks")
            self.store.db.execute("DROP FUNCTION fail_m4_delete()")
        state=self.store.db.execute("SELECT canonicality FROM evaluations WHERE evaluation_id=%s",(ev["evaluation_id"],)).fetchone()["canonicality"]
        self.assertEqual(state,"active")
        self.assertEqual(self.store.db.execute("SELECT count(*) AS n FROM evaluation_invalidations WHERE evaluation_id=%s",(ev["evaluation_id"],)).fetchone()["n"],0)
        self.assertEqual(self.store.count("blocks", self._ctx(chain)),1)

    def test_m4_concurrent_idempotent_negative_evaluation(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from psycopg.rows import dict_row
        from orbis.rules.registry import RuleRegistry
        from orbis.rules.evidence import make_envelope
        from orbis.rules.identity import evaluation_identity
        from orbis.rules.repository import EvaluationRepository
        chain=1983
        version=RuleRegistry(self.store.db).register(rule_id="T-03",semantic_version="1.0.0",input_schema={},parameter_schema={})
        envelope=make_envelope(network_chain_id=chain,bounds={"from":3,"to":3},rule={"rule_id":"T-03","semantic_version":"1.0.0","definition_digest":version["definition_digest"]},parameters={},evaluator_build="build",coverage={},items=[])
        network=self._ctx(chain).network_id
        key=evaluation_identity(chain_id=chain,subject_kind="wallet",subject_key="subject-1",rule_id=version["rule_id"],semantic_version=version["semantic_version"],definition_digest=version["definition_digest"],from_block=3,to_block=3,parameters={},context_digest=envelope["context_digest"],evaluator_build="build")
        barrier=Barrier(2)
        def create_one():
            with self.psycopg.connect(os.environ["ORBIS_TEST_DATABASE_URL"],row_factory=dict_row) as db:
                db.execute(self.psycopg.sql.SQL("SET search_path TO {}").format(self.psycopg.sql.Identifier(self.schema)))
                dbrow=db.execute("SELECT * FROM rule_versions WHERE rule_version_id=%s",(version["rule_version_id"],)).fetchone()
                barrier.wait()
                return EvaluationRepository(db).create(context=self._ctx(chain), network_id=network,rule_version=dbrow,subject_kind="wallet",subject_key="subject-1",from_block=3,to_block=3,parameters={},context_digest=envelope["context_digest"],evaluator_build="build",evaluation_key=key,coverage={},envelope=envelope,outcome="not_matched")["evaluation_id"]
        with ThreadPoolExecutor(max_workers=2) as pool:
            ids=list(pool.map(lambda _:create_one(),range(2)))
        self.assertEqual(ids[0],ids[1])
        self.assertEqual(self.store.db.execute("SELECT count(*) AS n FROM evaluations WHERE network_id=%s AND evaluation_key=%s",(network,key)).fetchone()["n"],1)
        self.assertEqual(self.store.db.execute("SELECT count(*) AS n FROM findings WHERE network_id=%s AND evaluation_id=%s",(network,ids[0])).fetchone()["n"],0)

    def test_m4_failed_execution_persists_without_findings(self):
        from orbis.rules.registry import RuleRegistry
        from orbis.rules.evidence import make_envelope
        from orbis.rules.identity import evaluation_identity
        from orbis.rules.repository import EvaluationRepository
        chain=1984
        version=RuleRegistry(self.store.db).register(rule_id="T-04",semantic_version="1.0.0",input_schema={},parameter_schema={})
        envelope=make_envelope(network_chain_id=chain,bounds={"from":7,"to":7},rule={"rule_id":"T-04","semantic_version":"1.0.0","definition_digest":version["definition_digest"]},parameters={},evaluator_build="build",coverage={},items=[])
        network=self._ctx(chain).network_id
        key=evaluation_identity(chain_id=chain,subject_kind="wallet",subject_key="subject",rule_id=version["rule_id"],semantic_version=version["semantic_version"],definition_digest=version["definition_digest"],from_block=7,to_block=7,parameters={},context_digest=envelope["context_digest"],evaluator_build="build")
        ev=EvaluationRepository(self.store.db).record_failure(context=self._ctx(chain), network_id=network,rule_version=version,subject_kind="wallet",subject_key="subject",from_block=7,to_block=7,parameters={},context_digest=envelope["context_digest"],evaluator_build="build",evaluation_key=key,coverage={},envelope=envelope,diagnostics={"error":"fixture failure"})
        self.assertEqual(ev["execution_status"],"failed")
        self.assertIsNone(ev["analytical_outcome"])
        self.assertEqual(self.store.db.execute("SELECT count(*) AS n FROM findings WHERE network_id=%s AND evaluation_id=%s",(network,ev["evaluation_id"])).fetchone()["n"],0)

    def test_reopen_recovers_checkpoint_and_reorg_can_replay(self):
        genesis = {"number": "0x0", "hash": "0xgenesis", "parentHash": "0xzero", "timestamp": "0x10", "transactions": []}
        old = {"number": "0x1", "hash": "0xold", "parentHash": "0xgenesis", "timestamp": "0x11", "transactions": []}
        new = {"number": "0x1", "hash": "0xnew", "parentHash": "0xgenesis", "timestamp": "0x12", "transactions": []}
        self.store.commit_block(self._ctx(1875), genesis, [], [])
        self.store.commit_block(self._ctx(1875), old, [], [])
        schema = self.schema
        self.store.close()
        from orbis.observer.postgres import PostgresStore
        type(self).store = PostgresStore(os.environ["ORBIS_TEST_DATABASE_URL"], schema=schema, runtime_fenced=False)
        self.store.migrate()  # migration startup is idempotent
        self.assertEqual(self.store.checkpoint(self._ctx(1875)), (1, "0xold"))
        self.store.rollback_from(self._ctx(1875), 1)
        self.store.commit_block(self._ctx(1875), new, [], [])
        self.assertEqual(self.store.checkpoint(self._ctx(1875)), (1, "0xnew"))
        self.store.commit_block(self._ctx(1875), genesis, [], [])  # replaying older data cannot regress cursor
        self.assertEqual(self.store.checkpoint(self._ctx(1875)), (1, "0xnew"))
        self.assertEqual(self.store.count("blocks", self._ctx(1875)), 2)

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
            def genesis_hash(self): return "0x" + hashlib.sha256(b"postgres-fixture:1880").hexdigest()
            def block_number(self): return max(self.blocks)
            def block(self, number): return self.blocks.get(number)
            def receipt(self, tx_hash): raise AssertionError("empty test blocks have no receipts")

        rpc = RpcFixture({0: genesis, 1: old1, 2: old2})
        indexer = Indexer(rpc, self.store, 1880, confirmation_depth=0, batch_size=3)
        indexer.sync(start_block=0)
        rpc.blocks = {0: genesis, 1: new1, 2: new2}
        result = indexer.sync()
        self.assertEqual(result["indexed_blocks"], 2)
        self.assertEqual(self.store.checkpoint(self._ctx(1880)), (2, "0xnew2"))
        self.assertEqual(self.store.block_hash(self._ctx(1880), 1), "0xnew1")
        self.assertEqual(self.store.count("blocks", self._ctx(1880)), 3)

    def test_unique_constraints_reject_duplicate_transaction_hash(self):
        block = {"number": "0x3", "hash": "0xblock3", "parentHash": "0xparent", "timestamp": "0x10",
                 "transactions": [{"hash": "0xtx3", "transactionIndex": "0x0"},
                                  {"hash": "0xtx3", "transactionIndex": "0x1"}]}
        with self.assertRaisesRegex(ValueError, "duplicate transaction hash"):
            self.store.commit_block(self._ctx(1876), block, [], [])
        self.assertIsNone(self.store.checkpoint(self._ctx(1876)))
        self.assertEqual(self.store.count("blocks", self._ctx(1876)), 0)
        block["transactions"] = [block["transactions"][0]]
        self.store.commit_block(self._ctx(1876), block, [], [])
        network_id = self._ctx(1876).network_id
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
        self.store.commit_block(self._ctx(1878), block, [receipt], [])
        network_id = self._ctx(1878).network_id
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
            self.store.rollback_from(self._ctx(1878), 9)
        self.assertEqual(self.store.checkpoint(self._ctx(1878)), (9, "0xevidence-block"))
        self.store.db.execute("DELETE FROM observations WHERE observation_id=%s", (observation["observation_id"],))
        self.store.rollback_from(self._ctx(1878), 9)
        self.assertIsNone(self.store.checkpoint(self._ctx(1878)))

    def test_uncommitted_block_and_checkpoint_are_invisible_until_commit(self):
        reader = self.psycopg.connect(os.environ["ORBIS_TEST_DATABASE_URL"], options=f"-c search_path={self.schema}", autocommit=True)
        try:
            with self.store.db.transaction():
                network_id = self._ctx(1879).network_id
                self.store.db.execute("INSERT INTO blocks(network_id,number,hash,parent_hash,timestamp) VALUES(%s,4,'0xisolated','0xparent',20)", (network_id,))
                self.store.db.execute("INSERT INTO checkpoints VALUES(%s,4,'0xisolated')", (network_id,))
                visible = reader.execute("SELECT count(*) FROM networks WHERE chain_id=1879").fetchone()[0]
                self.assertEqual(visible, 0)
            self.assertEqual(reader.execute("SELECT count(*) FROM blocks WHERE hash='0xisolated'").fetchone()[0], 1)
            self.assertEqual(self.store.checkpoint(self._ctx(1879)), (4, "0xisolated"))
        finally:
            reader.close()
        self.store.rollback_from(self._ctx(1879), 0)

    def test_knowledge_ingestion_normalization_idempotency_queries_and_reorg(self):
        from orbis.knowledge import KnowledgeService, normalize_address
        address_a = "0x" + "a" * 40
        address_b = "0x" + "b" * 40
        self.store.commit_block(self._ctx(1881), {"number":"0x1","hash":"0xk1","parentHash":"0x0","timestamp":"0x64",
            "transactions":[{"hash":"0xktx","from":address_a.upper().replace("0X","0x"),"to":address_b,
            "transactionIndex":"0x0"},{"hash":"0xktx2","from":address_a,"to":address_b,
            "transactionIndex":"0x1"}]}, [{"transactionHash":"0xktx","blockNumber":"0x1","blockHash":"0xk1",
            "status":"0x1","logs":[]},{"transactionHash":"0xktx2","blockNumber":"0x1","blockHash":"0xk1",
            "status":"0x1","logs":[]}], [])
        knowledge = KnowledgeService(self.store)
        self.assertEqual(normalize_address(address_a.upper().replace("0X","0x")),address_a)
        self.assertEqual(knowledge.ingest(self._ctx(1881)),2)
        self.assertEqual(knowledge.ingest(self._ctx(1881)),0)
        self.assertEqual(knowledge.ingestion_status(self._ctx(1881)),{"eligible":2,"processed":2,"remaining":0})
        self.assertEqual(knowledge.get_entity(self._ctx(1881),address_a.upper().replace("0X","0x"))["address"],address_a)
        self.assertEqual(len(knowledge.observations(self._ctx(1881),address_a)),2)
        self.assertEqual(len(knowledge.observations(self._ctx(1881),address_a,limit=1,offset=1)),1)
        rels=knowledge.relationships(self._ctx(1881),address_a)
        self.assertEqual(len(rels),1)
        self.assertEqual(len(knowledge.relationship_evidence(self._ctx(1881),rels[0]["relationship_id"])),2)
        self.assertIsNone(knowledge.get_entity(self._ctx(1882),address_a))
        with self.assertRaises(ValueError): normalize_address("0xnot-an-address")
        self.store.rollback_from(self._ctx(1881),1)
        self.assertEqual(knowledge.observations(self._ctx(1881),address_a),[])
        self.assertEqual(knowledge.relationships(self._ctx(1881),address_a),[])
        self.store.commit_block(self._ctx(1881),{"number":"0x1","hash":"0xk1new","parentHash":"0x0","timestamp":"0x65",
            "transactions":[{"hash":"0xktnew","from":address_a,"to":address_b,"transactionIndex":"0x0"}]},
            [{"transactionHash":"0xktnew","blockNumber":"0x1","blockHash":"0xk1new","status":"0x1","logs":[]}],[])
        self.assertEqual(knowledge.ingest(self._ctx(1881)),1)
        self.assertEqual(len(knowledge.observations(self._ctx(1881),address_a)),1)

    def test_failed_knowledge_batch_rolls_back_all_enrichment(self):
        from orbis.knowledge import KnowledgeService
        good="0x"+"c"*40
        bad="0xnot-valid"
        self.store.commit_block(self._ctx(1883),{"number":"0x1","hash":"0xkb1","parentHash":"0x0","timestamp":"0x1",
            "transactions":[{"hash":"0xktbad","from":good,"to":bad,"transactionIndex":"0x0"}]},
            [{"transactionHash":"0xktbad","blockNumber":"0x1","blockHash":"0xkb1","status":"0x1","logs":[]}],[])
        knowledge=KnowledgeService(self.store)
        with self.assertRaises(ValueError): knowledge.ingest(self._ctx(1883))
        net=self._ctx(1883).network_id
        self.assertEqual(self.store.db.execute("SELECT count(*) c FROM entities WHERE network_id=%s",(net,)).fetchone()["c"],0)
        self.assertEqual(self.store.db.execute("SELECT count(*) c FROM observations WHERE network_id=%s",(net,)).fetchone()["c"],0)

    def _knowledge_blocks(self, chain_id, start, count, sender, recipient, prefix="agg"):
        for height in range(start, start + count):
            tx_hash = f"0x{prefix}-tx-{height}"
            block_hash = f"0x{prefix}-block-{height}"
            block = {"number":hex(height),"hash":block_hash,"parentHash":f"0x{prefix}-parent-{height}",
                     "timestamp":hex(100+height),"transactions":[{"hash":tx_hash,"from":sender,"to":recipient,"transactionIndex":"0x0"}]}
            receipt = {"transactionHash":tx_hash,"blockNumber":hex(height),"blockHash":block_hash,"status":"0x1","logs":[]}
            self.store.commit_block(self._ctx(chain_id),block,[receipt],[])

    def test_reorg_recomputes_partial_relationship_aggregates_and_replay(self):
        from orbis.knowledge import KnowledgeService
        a,b="0x"+"a"*40,"0x"+"b"*40
        for chain_id in (1901,1902,1903):
            self._knowledge_blocks(chain_id,1,3,a,b,str(chain_id))
            k=KnowledgeService(self.store); self.assertEqual(k.ingest(self._ctx(chain_id),10),3)
            rel=k.relationships(self._ctx(chain_id),a)[0]
            self.assertEqual((rel["first_observed_block"],rel["last_observed_block"],rel["observation_count"]),(1,3,3))
            # A suffix reorg removes the selected endpoint or middle-and-later support.
            invalid_from={1901:3,1902:2,1903:1}[chain_id]
            self.store.rollback_from(self._ctx(chain_id),invalid_from)
            remaining=k.relationships(self._ctx(chain_id),a)
            if invalid_from == 1:
                self.assertEqual(remaining,[])
            else:
                rel=remaining[0]
                last=invalid_from-1
                self.assertEqual((rel["first_observed_block"],rel["last_observed_block"],rel["observation_count"]),(1,last,last))
            # Repeated invalidation is idempotent; replacement evidence rebuilds the summary.
            self.store.rollback_from(self._ctx(chain_id),invalid_from)
            if invalid_from == 1:
                self._knowledge_blocks(chain_id,1,2,a,b,"replacement")
                self.assertEqual(k.ingest(self._ctx(chain_id)),2)
                rel=k.relationships(self._ctx(chain_id),a)[0]
                self.assertEqual((rel["first_observed_block"],rel["last_observed_block"],rel["observation_count"]),(1,2,2))

    def test_replacement_block_can_omit_earliest_middle_or_latest_support(self):
        from orbis.knowledge import KnowledgeService
        sender,recipient="0x"+"a7"*20,"0x"+"a8"*20
        original=[{"hash":f"0xreplace-{i}","from":sender,"to":recipient,"transactionIndex":hex(i)} for i in range(3)]
        for chain,omitted in ((1920,0),(1921,1),(1922,2)):
            old_hash=f"0xreplace-old-{chain}"
            self.store.commit_block(self._ctx(chain),{"number":"0x1","hash":old_hash,"parentHash":"0x0","timestamp":"0x1","transactions":original},
                [{"transactionHash":t["hash"],"blockNumber":"0x1","blockHash":old_hash,"status":"0x1","logs":[]} for t in original],[])
            k=KnowledgeService(self.store); self.assertEqual(k.ingest(self._ctx(chain)),3)
            self.assertEqual(k.relationships(self._ctx(chain),sender)[0]["observation_count"],3)
            self.store.rollback_from(self._ctx(chain),1)
            new_hash=f"0xreplace-new-{chain}"
            replacement=[t for i,t in enumerate(original) if i!=omitted]
            self.store.commit_block(self._ctx(chain),{"number":"0x1","hash":new_hash,"parentHash":"0x0","timestamp":"0x2","transactions":replacement},
                [{"transactionHash":t["hash"],"blockNumber":"0x1","blockHash":new_hash,"status":"0x1","logs":[]} for t in replacement],[])
            self.assertEqual(k.ingest(self._ctx(chain)),2)
            rel=k.relationships(self._ctx(chain),sender)[0]
            self.assertEqual((rel["first_observed_block"],rel["last_observed_block"],rel["observation_count"]),(1,1,2))

    def test_rollback_failure_is_atomic_for_knowledge_and_chain_state(self):
        from orbis.knowledge import KnowledgeService
        a,b="0x"+"c"*40,"0x"+"d"*40
        self._knowledge_blocks(1904,1,2,a,b,"atomic")
        k=KnowledgeService(self.store); k.ingest(self._ctx(1904))
        net=self._ctx(1904).network_id
        self.store.db.execute("""CREATE FUNCTION fail_block_delete() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'injected rollback failure'; END $$""")
        self.store.db.execute("CREATE TRIGGER fail_block_delete BEFORE DELETE ON blocks FOR EACH ROW EXECUTE FUNCTION fail_block_delete()")
        try:
            with self.assertRaisesRegex(self.psycopg.Error,"injected rollback failure"):
                self.store.rollback_from(self._ctx(1904),2)
        finally:
            self.store.db.execute("DROP TRIGGER fail_block_delete ON blocks")
            self.store.db.execute("DROP FUNCTION fail_block_delete()")
        self.assertEqual(self.store.count("blocks", self._ctx(1904)),2)
        self.assertEqual(k.ingestion_status(self._ctx(1904)),{"eligible":2,"processed":2,"remaining":0})
        self.assertEqual(k.relationships(self._ctx(1904),a)[0]["observation_count"],2)

    def test_enrichment_processes_multiple_batches_and_empty_fact_transactions_once(self):
        from orbis.knowledge import KnowledgeService
        a,b="0x"+"e"*40,"0x"+"f"*40
        chain=1905
        txs=[{"hash":f"0xbatch-{i}","from":a if i%2==0 else None,"to":b if i%2==0 else None,"transactionIndex":hex(i)} for i in range(7)]
        block={"number":"0x1","hash":"0xbatch-block","parentHash":"0x0","timestamp":"0x1","transactions":txs}
        receipts=[{"transactionHash":t["hash"],"blockNumber":"0x1","blockHash":"0xbatch-block","status":"0x1","logs":[]} for t in txs]
        self.store.commit_block(self._ctx(chain),block,receipts,[]); k=KnowledgeService(self.store)
        self.assertEqual(k.ingestion_status(self._ctx(chain)),{"eligible":7,"processed":0,"remaining":7})
        counts=[k.ingest(self._ctx(chain),3),k.ingest(self._ctx(chain),3),k.ingest(self._ctx(chain),3),k.ingest(self._ctx(chain),3)]
        self.assertEqual(counts,[3,3,1,0])
        self.assertEqual(k.ingestion_status(self._ctx(chain)),{"eligible":7,"processed":7,"remaining":0})
        # Successful pages survive a service restart; failed pages never write progress.
        self.assertEqual(KnowledgeService(self.store).ingest(self._ctx(chain),3),0)

    def test_exact_batch_boundary_and_failure_in_middle_do_not_mark_partial_work(self):
        from orbis.knowledge import KnowledgeService
        for chain,number in ((1906,2),(1907,3)):
            txs=[{"hash":f"0xexact-{chain}-{i}","from":"0x"+"7"*40,"to":"0x"+"8"*40,"transactionIndex":hex(i)} for i in range(number)]
            block={"number":"0x1","hash":f"0xexact-block-{chain}","parentHash":"0x0","timestamp":"0x1","transactions":txs}
            receipts=[{"transactionHash":t["hash"],"blockNumber":"0x1","blockHash":block["hash"],"status":"0x1","logs":[]} for t in txs]
            self.store.commit_block(self._ctx(chain),block,receipts,[]); k=KnowledgeService(self.store)
            self.assertEqual(k.ingest(self._ctx(chain),3),number)
            self.assertEqual(k.ingestion_status(self._ctx(chain)),{"eligible":number,"processed":number,"remaining":0})
        chain=1908
        good="0x"+"9"*40
        txs=[{"hash":"0xfail-1","from":good,"to":good,"transactionIndex":"0x0"},
             {"hash":"0xfail-2","from":good,"to":"0xmalformed","transactionIndex":"0x1"},
             {"hash":"0xfail-3","from":good,"to":good,"transactionIndex":"0x2"}]
        block={"number":"0x1","hash":"0xfail-block","parentHash":"0x0","timestamp":"0x1","transactions":txs}
        self.store.commit_block(self._ctx(chain),block,[{"transactionHash":t["hash"],"blockNumber":"0x1","blockHash":block["hash"],"status":"0x1","logs":[]} for t in txs],[])
        k=KnowledgeService(self.store)
        with self.assertRaises(ValueError): k.ingest(self._ctx(chain),3)
        self.assertEqual(k.ingestion_status(self._ctx(chain)),{"eligible":3,"processed":0,"remaining":3})

    def test_concurrent_enrichment_claims_each_transaction_once(self):
        from concurrent.futures import ThreadPoolExecutor
        from orbis.knowledge import KnowledgeService
        chain=1909; a,b="0x"+"c1"*20,"0x"+"c2"*20
        txs=[{"hash":f"0xconcurrent-{i}","from":a,"to":b,"transactionIndex":hex(i)} for i in range(10)]
        block={"number":"0x1","hash":"0xconcurrent-block","parentHash":"0x0","timestamp":"0x1","transactions":txs}
        receipts=[{"transactionHash":t["hash"],"blockNumber":"0x1","blockHash":block["hash"],"status":"0x1","logs":[]} for t in txs]
        self.store.commit_block(self._ctx(chain),block,receipts,[])
        from orbis.observer.postgres import PostgresStore
        other=PostgresStore(os.environ["ORBIS_TEST_DATABASE_URL"],schema=self.schema,runtime_fenced=False)
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                results=list(pool.map(lambda store:KnowledgeService(store).ingest(self._ctx(chain),5),(self.store,other)))
            self.assertEqual(sorted(results),[5,5])
            self.assertEqual(KnowledgeService(self.store).ingestion_status(self._ctx(chain)),{"eligible":10,"processed":10,"remaining":0})
        finally:
            other.close()

    def test_network_identity_and_evidence_are_isolated(self):
        from orbis.knowledge import KnowledgeService
        addr="0x"+"1"*40
        for chain,height in ((1910,1),(1911,2)):
            tx=f"0xnetwork-{chain}"; blockhash=f"0xnetwork-block-{chain}"
            self.store.commit_block(self._ctx(chain),{"number":hex(height),"hash":blockhash,"parentHash":"0xparent","timestamp":"0x1",
                "transactions":[{"hash":tx,"from":addr,"to":None,"transactionIndex":"0x0"}]},
                [{"transactionHash":tx,"blockNumber":hex(height),"blockHash":blockhash,"status":"0x1","logs":[]}],[])
            KnowledgeService(self.store).ingest(self._ctx(chain))
        one,two=KnowledgeService(self.store).get_entity(self._ctx(1910),addr),KnowledgeService(self.store).get_entity(self._ctx(1911),addr)
        self.assertNotEqual(one["entity_id"],two["entity_id"])
        self.assertNotEqual(one["network_id"],two["network_id"])
        observation_networks={row["network_id"] for row in self.store.db.execute("SELECT network_id FROM observations WHERE entity_id IN (%s,%s)",(one["entity_id"],two["entity_id"])).fetchall()}
        self.assertEqual(observation_networks,{one["network_id"],two["network_id"]})
        with self.assertRaises(self.psycopg.errors.ForeignKeyViolation):
            self.store.db.execute("INSERT INTO observations(network_id,entity_id,observation_type,source_block_number,source_block_hash,source_transaction_hash,derived) VALUES(%s,%s,'cross-network',2,'0xnetwork-block-1911','0xnetwork-1911',TRUE)",
                                  (one["network_id"],one["entity_id"]))

    def test_receipt_log_provenance_and_multiple_logs(self):
        from orbis.knowledge import KnowledgeService
        sender,recipient,emitter="0x"+"2"*40,"0x"+"3"*40,"0x"+"4"*40
        chain=1912; tx="0xprovtx"; blockhash="0xprovblock"
        logs=[{"transactionHash":tx,"blockNumber":"0x1","blockHash":blockhash,"logIndex":hex(i),
               "address":emitter,"topics":[],"data":"0x"} for i in range(3)]
        self.store.commit_block(self._ctx(chain),{"number":"0x1","hash":blockhash,"parentHash":"0x0","timestamp":"0x1",
            "transactions":[{"hash":tx,"from":sender,"to":recipient,"transactionIndex":"0x0"}]},
            [{"transactionHash":tx,"blockNumber":"0x1","blockHash":blockhash,"status":"0x1","logs":logs}],[])
        k=KnowledgeService(self.store); self.assertEqual(k.ingest(self._ctx(chain)),1)
        emitter_entity=k.get_entity(self._ctx(chain),emitter)
        events=k.observations(self._ctx(chain),emitter)
        self.assertEqual(len(events),3)
        self.assertEqual({e["source_log_index"] for e in events},{0,1,2})
        self.assertNotIn(emitter,{r["target_address"] for r in k.relationships(self._ctx(chain),sender)})
        net=emitter_entity["network_id"]
        observation=events[0]["observation_id"]
        with self.assertRaises(self.psycopg.errors.ForeignKeyViolation):
            self.store.db.execute("INSERT INTO evidence_refs(network_id,observation_id,block_number,block_hash,transaction_hash) VALUES(%s,%s,1,%s,'0xmissing-receipt')",
                                  (net,observation,blockhash))
        with self.assertRaises(self.psycopg.errors.ForeignKeyViolation):
            self.store.db.execute("UPDATE receipts SET block_hash='0xwrong-block' WHERE network_id=%s AND transaction_hash=%s",(net,tx))
        with self.assertRaises(self.psycopg.errors.ForeignKeyViolation):
            self.store.db.execute("INSERT INTO evidence_refs(network_id,observation_id,block_number,block_hash,transaction_hash,log_index) VALUES(%s,%s,1,%s,%s,99)",
                                  (net,observation,blockhash,tx))
        tx_observation=k.observations(self._ctx(chain),sender)[0]
        self.assertIsNone(self.store.db.execute("SELECT log_index FROM evidence_refs WHERE observation_id=%s",(tx_observation["observation_id"],)).fetchone()["log_index"])

    def test_relationship_kinds_use_direct_recipient_and_valid_transfer_signature(self):
        from orbis.knowledge import KnowledgeService
        sender="0x"+"a1"*20; recipient="0x"+"a2"*20; other="0x"+"a3"*20; emitter="0x"+"a4"*20
        chain=1914; blockhash="0xsem-block"
        txs=[{"hash":"0xsem-direct","from":sender,"to":emitter,"transactionIndex":"0x0"},
             {"hash":"0xsem-indirect","from":sender,"to":recipient,"transactionIndex":"0x1"}]
        topic=lambda a:"0x"+"0"*24+a[2:]
        transfer="0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
        emitter2="0x"+"a5"*20
        logs=[{"transactionHash":"0xsem-direct","blockNumber":"0x1","blockHash":blockhash,"logIndex":"0x0","address":emitter,"topics":[],"data":"0x"},
              {"transactionHash":"0xsem-indirect","blockNumber":"0x1","blockHash":blockhash,"logIndex":"0x1","address":emitter,"topics":[transfer,topic(sender),topic(other)],"data":"0x"+format(55,"064x")},
              {"transactionHash":"0xsem-indirect","blockNumber":"0x1","blockHash":blockhash,"logIndex":"0x2","address":emitter,"topics":["0x"+"f"*64,topic(sender),topic(other)],"data":"0x"+format(56,"064x")},
              {"transactionHash":"0xsem-indirect","blockNumber":"0x1","blockHash":blockhash,"logIndex":"0x3","address":emitter2,"topics":[],"data":"0x"}]
        self.store.commit_block(self._ctx(chain),{"number":"0x1","hash":blockhash,"parentHash":"0x0","timestamp":"0x1","transactions":txs},
            [{"transactionHash":t["hash"],"blockNumber":"0x1","blockHash":blockhash,"status":"0x1","logs":[l for l in logs if l["transactionHash"]==t["hash"]]} for t in txs],[])
        k=KnowledgeService(self.store); self.assertEqual(k.ingest(self._ctx(chain)),2)
        rels=k.relationships(self._ctx(chain),sender)
        typed={(r["relationship_type"],r["target_address"]) for r in rels}
        self.assertIn(("interacted_with_contract",emitter),typed)
        self.assertNotIn(("interacted_with_contract",recipient),typed)
        self.assertIn(("transacted_with",recipient),typed)
        self.assertIn(("transferred_to",other),typed)
        transfer_observations=k.observations(self._ctx(chain),other)
        self.assertEqual(len(transfer_observations),1)
        self.assertEqual(transfer_observations[0]["payload"]["amount"],"55")
        self.assertEqual(transfer_observations[0]["payload"]["token"],emitter)

    def test_cross_network_relationship_endpoints_are_rejected(self):
        from orbis.knowledge import KnowledgeService
        addr1,addr2="0x"+"b1"*20,"0x"+"b2"*20
        for chain,height in ((1915,1),(1916,2)):
            tx=f"0xcross-{chain}"; blockhash=f"0xcross-block-{chain}"
            self.store.commit_block(self._ctx(chain),{"number":hex(height),"hash":blockhash,"parentHash":"0xparent","timestamp":"0x1","transactions":[{"hash":tx,"from":addr1,"to":addr2,"transactionIndex":"0x0"}]},
                [{"transactionHash":tx,"blockNumber":hex(height),"blockHash":blockhash,"status":"0x1","logs":[]}],[])
            KnowledgeService(self.store).ingest(self._ctx(chain))
        e1=KnowledgeService(self.store).get_entity(self._ctx(1915),addr1); e2=KnowledgeService(self.store).get_entity(self._ctx(1916),addr2)
        with self.assertRaises(self.psycopg.errors.ForeignKeyViolation):
            self.store.db.execute("INSERT INTO relationships(network_id,source_entity_id,relationship_type,target_entity_id,derivation,first_observed_block,last_observed_block) VALUES(%s,%s,'cross',%s,'observed',1,1)",
                                  (e1["network_id"],e1["entity_id"],e2["entity_id"]))

    def test_relationship_and_evidence_pages_are_bounded_and_ordered(self):
        from orbis.knowledge import KnowledgeService
        a,b="0x"+"5"*40,"0x"+"6"*40; chain=1913
        self._knowledge_blocks(chain,1,5,a,b,"pages")
        k=KnowledgeService(self.store); k.ingest(self._ctx(chain),10)
        page1=k.relationships(self._ctx(chain),a,limit=1,offset=0)
        page2=k.relationships(self._ctx(chain),a,limit=1,offset=1)
        self.assertEqual(len(page1),1); self.assertEqual(len(page2),0)
        evidence1=k.relationship_evidence(self._ctx(chain),page1[0]["relationship_id"],limit=2)
        evidence2=k.relationship_evidence(self._ctx(chain),page1[0]["relationship_id"],limit=2,offset=2)
        self.assertEqual((len(evidence1),len(evidence2)),(2,2))
        plan=self.store.db.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) SELECT * FROM transactions WHERE network_id=%s AND sender=%s ORDER BY block_number DESC,tx_index DESC LIMIT 20",
                                   (page1[0]["network_id"],a)).fetchall()
        self.assertTrue(any("transaction_history_sender_idx" in row["QUERY PLAN"] for row in plan))

    def test_failed_block_write_does_not_advance_checkpoint(self):
        block = {"number": "0x2", "hash": "0xblock2", "parentHash": "0xparent", "timestamp": "0x10",
                 "transactions": [{"hash": "0xtx-bad", "transactionIndex": "0x0"}]}
        invalid_receipt = {"transactionHash": "0xtx-bad", "blockHash": "0xblock2", "unexpected": object(), "logs": []}
        with self.assertRaises(TypeError):
            self.store.commit_block(self._ctx(1877), block, [invalid_receipt], [])
        self.assertIsNone(self.store.checkpoint(self._ctx(1877)))
        self.assertEqual(self.store.count("blocks", self._ctx(1877)), 0)
        self.assertEqual(self.store.count("transactions", self._ctx(1877)), 0)


if __name__ == "__main__":
    unittest.main()
