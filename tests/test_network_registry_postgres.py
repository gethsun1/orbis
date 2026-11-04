"""Network registry acceptance tests against an explicitly disposable PostgreSQL DB."""
from __future__ import annotations

import os
import unittest
from psycopg.errors import RaiseException
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from orbis.network import NetworkContext, TrustState, verified_context


@unittest.skipUnless(os.environ.get("ORBIS_TEST_DATABASE_URL"),
                     "requires an isolated disposable ORBIS_TEST_DATABASE_URL")
class NetworkRegistryPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from orbis.observer.postgres import PostgresStore
        cls.schema = "orbis_identity_" + uuid4().hex
        cls.store = PostgresStore(os.environ["ORBIS_TEST_DATABASE_URL"], schema=cls.schema)
        cls.store.migrate()

    @classmethod
    def tearDownClass(cls):
        cls.store.db.execute(f'DROP SCHEMA "{cls.schema}" CASCADE')
        cls.store.close()

    @staticmethod
    def context(chain=1874, fill="11"):
        return verified_context(chain, "0x" + fill * 32)

    def test_same_chain_distinct_genesis_and_endpoint_independent_resolution(self):
        one = self.store.resolve_network(self.context(fill="11"))
        two = self.store.resolve_network(self.context(fill="22"))
        again = self.store.resolve_network(self.context(fill="11"))
        self.assertNotEqual(one.network_id, two.network_id)
        self.assertEqual(one.network_id, again.network_id)
        self.assertEqual(one.network_fingerprint, again.network_fingerprint)

    def test_context_rejection_and_immutable_identity(self):
        context = self.store.resolve_network(self.context(fill="33"))
        with self.assertRaises(ValueError):
            self.store.checkpoint(NetworkContext.unverified(1874))
        with self.assertRaises(RaiseException):
            self.store.db.execute(
                "UPDATE networks SET genesis_hash=%s WHERE network_id=%s",
                ("0x" + "44" * 32, context.network_id),
            )
        self.store.db.rollback()

    def test_concurrent_registration_converges(self):
        uri = os.environ["ORBIS_TEST_DATABASE_URL"]
        schema = self.schema
        context = self.context(chain=1875, fill="55")

        def register(_):
            from orbis.observer.postgres import PostgresStore
            store = PostgresStore(uri, schema=schema)
            try:
                return store.resolve_network(context).network_id
            finally:
                store.close()

        with ThreadPoolExecutor(max_workers=8) as pool:
            ids = list(pool.map(register, range(16)))
        self.assertEqual(len(set(ids)), 1)

    def test_ingestion_and_selector_isolation(self):
        one = self.store.resolve_network(self.context(chain=1877, fill="77"))
        two = self.store.resolve_network(self.context(chain=1877, fill="88"))
        for context, suffix in ((one, "a"), (two, "b")):
            block = {"number":"0x1","hash":"0xblock"+suffix,"parentHash":"0xparent",
                     "timestamp":"0x1","transactions":[]}
            self.store.commit_block(context, block, [], [])
        self.assertEqual(self.store.checkpoint(one), (1, "0xblocka"))
        self.assertEqual(self.store.checkpoint(two), (1, "0xblockb"))
        self.assertEqual(self.store.count("blocks", one), 1)
        self.assertEqual(self.store.count("blocks", two), 1)
        self.store.rollback_from(one, 1)
        self.assertIsNone(self.store.checkpoint(one))
        self.assertEqual(self.store.checkpoint(two), (1, "0xblockb"))
