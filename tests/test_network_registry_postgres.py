"""Network registry acceptance tests against an explicitly disposable PostgreSQL DB."""
from __future__ import annotations

import os
import unittest
import hashlib
from pathlib import Path
import psycopg
from psycopg.errors import RaiseException
from psycopg.errors import InsufficientPrivilege, UndefinedFunction, UniqueViolation
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import dict_row
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from orbis.network import NetworkContext, TrustState, verified_context
from tests.postgres_test_support import require_disposable_database


def setUpModule():
    require_disposable_database()


class NetworkRegistryPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from orbis.observer.postgres import PostgresStore
        from psycopg import sql
        cls.schema = "orbis_identity_" + uuid4().hex
        with psycopg.connect(os.environ["ORBIS_TEST_DATABASE_URL"]) as db:
            db.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(cls.schema)))
        cls.store = PostgresStore(os.environ["ORBIS_TEST_DATABASE_URL"], schema=cls.schema, runtime_fenced=False)
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
        with self.assertRaises(ValueError):
            self.store.checkpoint(1874)
        with self.assertRaises(ValueError):
            self.store.commit_block(NetworkContext.unverified(1874),
                {"number":"0x1","hash":"0xuntrusted","parentHash":"0x0",
                 "timestamp":"0x1","transactions":[]}, [], [])
        with self.assertRaises(ValueError):
            verified_context(1874, "0xmalformed")
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
            store = PostgresStore(uri, schema=schema, runtime_fenced=False)
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

    def test_same_chain_knowledge_reads_are_isolated_by_fingerprint(self):
        from orbis.knowledge import KnowledgeService
        one = self.store.resolve_network(self.context(chain=1882, fill="21"))
        two = self.store.resolve_network(self.context(chain=1882, fill="22"))
        knowledge = KnowledgeService(self.store)
        entity = knowledge.resolve_entity(one, "0x" + "ab" * 20)
        self.assertEqual(knowledge.get_entity(one, entity["address"])["network_id"], one.network_id)
        self.assertIsNone(knowledge.get_entity(two, entity["address"]))


    def test_identityless_and_conflicting_registry_inserts_are_rejected(self):
        context = self.store.resolve_network(self.context(chain=1878, fill="33"))
        with self.assertRaises(RaiseException):
            self.store.db.execute(
                "INSERT INTO networks(chain_id,name) VALUES (%s,'legacy-writer')", (1878,)
            )
        self.store.db.rollback()
        with self.assertRaises(UniqueViolation):
            self.store.db.execute("""INSERT INTO networks(chain_id,name,environment,provider_name,
                fingerprint_scheme,network_fingerprint,genesis_hash)
                VALUES (%s,'conflict','unknown','',%s,%s,%s)""",
                (context.chain_id,context.fingerprint_scheme,context.network_fingerprint,
                 "0x" + "99" * 32))
        self.store.db.rollback()
        self.assertEqual(self.store.resolve_network(self.context(chain=1878, fill="33")).network_id,
                         context.network_id)

    def test_runtime_principal_has_no_ddl_or_registry_grants(self):
        context = self.store.resolve_network(self.context(chain=1879, fill="44"))
        self.store.db.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO orbis_test_runtime")
                              .format(sql.Identifier(self.schema)))
        runtime_dsn = make_conninfo(**{
            **conninfo_to_dict(os.environ["ORBIS_TEST_DATABASE_URL"]),
            "user": "orbis_runtime",
        })
        admin_privileges = self.store.db.execute("""SELECT
            has_table_privilege('orbis_identity_admin',%s,'UPDATE') AS registry_update""",
            (f"{self.schema}.networks",)).fetchone()
        self.assertFalse(admin_privileges["registry_update"])
        admin_functions = self.store.db.execute("""SELECT count(*) AS n FROM pg_proc p
            JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname=%s
            AND p.proname IN ('orbis_register_network_identity',
                              'orbis_backfill_network_identity',
                              'orbis_repair_network_identity')""", (self.schema,)).fetchone()["n"]
        self.assertEqual(admin_functions, 1)
        function_security = self.store.db.execute("""SELECT p.prosecdef,
            pg_get_userbyid(p.proowner) AS owner,p.proconfig,
            has_function_privilege('public',p.oid,'EXECUTE') AS public_execute
            FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
            WHERE n.nspname=%s AND p.proname='orbis_register_network_identity'""", (self.schema,)).fetchone()
        self.assertTrue(function_security["prosecdef"])
        self.assertEqual(function_security["owner"], "orbis_registry_executor")
        self.assertFalse(function_security["public_execute"])
        self.assertTrue(any(str(value).startswith("search_path=pg_catalog,") for value in function_security["proconfig"]))
        with psycopg.connect(runtime_dsn, row_factory=dict_row) as runtime:
            grants = runtime.execute("""SELECT
                has_database_privilege(current_user,current_database(),'CREATE') AS database_ddl,
                has_table_privilege(current_user,%s,'SELECT') AS registry_read,
                has_table_privilege(current_user,%s,'INSERT') AS registry_insert,
                has_table_privilege(current_user,%s,'UPDATE') AS registry_update,
                has_function_privilege(current_user,%s,'EXECUTE') AS registry_register""",
                (f"{self.schema}.networks",)*3 +
                (f"{self.schema}.orbis_register_network_identity(bigint,text,text,text,text,text,text)",)).fetchone()
            self.assertFalse(grants["database_ddl"])
            self.assertTrue(grants["registry_read"])
            self.assertFalse(grants["registry_insert"])
            self.assertFalse(grants["registry_update"])
            self.assertTrue(grants["registry_register"])
            with self.assertRaises(InsufficientPrivilege):
                runtime.execute(sql.SQL("UPDATE {}.networks SET name='tampered' WHERE network_id=%s")
                                .format(sql.Identifier(self.schema)), (context.network_id,))
        from orbis.observer.postgres import PostgresStore
        runtime_store = PostgresStore(runtime_dsn, schema=self.schema, runtime_fenced=True)
        try:
            runtime_store.verify_runtime_principals(runtime_dsn, os.environ["ORBIS_TEST_DATABASE_URL"])
            with self.assertRaisesRegex(RuntimeError, "distinct principals"):
                runtime_store.verify_runtime_principals(runtime_dsn, runtime_dsn)
            registered = runtime_store.resolve_network(self.context(chain=1879, fill="45"))
            self.assertIsNotNone(registered.network_id)
            with self.assertRaises(InsufficientPrivilege):
                runtime_store.migrate()
            with self.assertRaises(InsufficientPrivilege):
                runtime_store.db.execute(sql.SQL("INSERT INTO {}.networks(chain_id,name) VALUES(99001,'direct')").format(sql.Identifier(self.schema)))
            runtime_store.db.rollback()
            with self.assertRaises(InsufficientPrivilege):
                runtime_store.db.execute(sql.SQL("DELETE FROM {}.networks WHERE network_id=%s").format(sql.Identifier(self.schema)), (context.network_id,))
            runtime_store.db.rollback()
            with self.assertRaises(InsufficientPrivilege):
                runtime_store.db.execute(sql.SQL("DELETE FROM {}.network_identity_audit").format(sql.Identifier(self.schema)))
            runtime_store.db.rollback()
            with self.assertRaises(InsufficientPrivilege):
                runtime_store.db.execute(sql.SQL("SELECT * FROM {}.network_identity_audit").format(sql.Identifier(self.schema)))
            runtime_store.db.rollback()
            event = self.store.db.execute(sql.SQL("SELECT actor,outcome,network_id FROM {}.network_identity_audit WHERE network_id=%s").format(sql.Identifier(self.schema)), (registered.network_id,)).fetchone()
            self.assertEqual((event["actor"], event["outcome"], event["network_id"]), ("orbis_runtime", "success", registered.network_id))
            rejected = runtime_store.db.execute(sql.SQL("SELECT {}.orbis_register_network_identity(%s,%s,%s,%s,%s,%s,%s) AS network_id").format(sql.Identifier(self.schema)),
                (1889,"invalid-scheme","sha256:"+"00"*32,"0x"+"00"*32,"","","" )).fetchone()
            self.assertIsNone(rejected["network_id"])
            rejected_event = self.store.db.execute(sql.SQL("SELECT actor,outcome,reason FROM {}.network_identity_audit WHERE chain_id=1889 ORDER BY event_id DESC LIMIT 1").format(sql.Identifier(self.schema))).fetchone()
            self.assertEqual((rejected_event["actor"], rejected_event["outcome"]), ("orbis_runtime", "rejected"))
            self.assertEqual(rejected_event["reason"], "invalid canonical identity tuple")
            with self.assertRaisesRegex(RuntimeError, "rollback denial event"):
                with runtime_store.db.transaction():
                    runtime_store.db.execute(sql.SQL("SELECT {}.orbis_register_network_identity(%s,%s,%s,%s,%s,%s,%s)").format(sql.Identifier(self.schema)),
                        (1890,"invalid-scheme","sha256:"+"00"*32,"0x"+"00"*32,"","",""))
                    raise RuntimeError("rollback denial event")
            rolled_back_event = self.store.db.execute(sql.SQL("SELECT count(*) AS n FROM {}.network_identity_audit WHERE chain_id=1890").format(sql.Identifier(self.schema))).fetchone()["n"]
            self.assertEqual(rolled_back_event, 0)
        finally:
            runtime_store.close()
        admin_dsn = make_conninfo(**{
            **conninfo_to_dict(os.environ["ORBIS_TEST_DATABASE_URL"]),
            "user": "orbis_identity_admin",
        })
        with psycopg.connect(admin_dsn, row_factory=dict_row) as admin:
            self.assertGreaterEqual(admin.execute(sql.SQL("SELECT count(*) AS n FROM {}.network_identity_audit").format(sql.Identifier(self.schema))).fetchone()["n"], 1)
            with self.assertRaises(InsufficientPrivilege):
                admin.execute(sql.SQL("UPDATE {}.networks SET genesis_hash=%s WHERE network_id=%s").format(sql.Identifier(self.schema)), ("0x"+"ab"*32, context.network_id))
            admin.rollback()
            with self.assertRaises(UndefinedFunction):
                admin.execute(sql.SQL("SELECT {}.orbis_repair_network_identity(%s)").format(sql.Identifier(self.schema)), (context.network_id,))
            admin.rollback()
        absent_schema = "runtime_must_not_create_" + uuid4().hex
        runtime_schema_store = PostgresStore(runtime_dsn, schema=absent_schema, runtime_fenced=True)
        try:
            with self.assertRaisesRegex(RuntimeError, "not migrated"):
                runtime_schema_store.check_compatibility()
            self.assertIsNone(runtime_schema_store.db.execute(
                "SELECT 1 FROM pg_namespace WHERE nspname=%s", (absent_schema,)
            ).fetchone())
        finally:
            runtime_schema_store.close()

    def test_interrupted_registry_transaction_leaves_no_partial_row(self):
        context = self.context(chain=1880, fill="55")
        with self.assertRaisesRegex(RuntimeError, "injected interruption"):
            with self.store.db.transaction():
                self.store.resolve_network(context)
                raise RuntimeError("injected interruption")
        rows = self.store.db.execute("""SELECT network_id FROM networks
            WHERE chain_id=%s AND network_fingerprint=%s""",
            (context.chain_id,context.network_fingerprint)).fetchall()
        self.assertEqual(rows, [])
        self.assertIsNotNone(self.store.resolve_network(context).network_id)

    def test_concurrent_distinct_fingerprints_sharing_chain_id(self):
        contexts = [self.context(chain=1881, fill=value) for value in ("66", "77")]
        uri = os.environ["ORBIS_TEST_DATABASE_URL"]
        schema = self.schema

        def register(context):
            from orbis.observer.postgres import PostgresStore
            store = PostgresStore(uri, schema=schema, runtime_fenced=False)
            try:
                return store.resolve_network(context).network_id
            finally:
                store.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            ids = list(pool.map(register, contexts))
        self.assertNotEqual(ids[0], ids[1])
        rows = self.store.db.execute(
            "SELECT count(*) AS n FROM networks WHERE chain_id=1881"
        ).fetchone()["n"]
        self.assertEqual(rows, 2)

    def test_startup_rejects_unmigrated_schema(self):
        from orbis.observer.postgres import PostgresStore
        schema = "orbis_unmigrated_" + uuid4().hex
        self.store.db.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        store = PostgresStore(os.environ["ORBIS_TEST_DATABASE_URL"], schema=schema, runtime_fenced=False)
        try:
            with self.assertRaisesRegex(RuntimeError, "not migrated"):
                store.check_compatibility()
        finally:
            self.store.db.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
            store.close()

    def test_startup_accepts_schema_and_rejects_checksum_drift(self):
        self.store.check_compatibility()
        path = Path(__file__).resolve().parents[1] / "migrations" / "001_initial.sql"
        correct = hashlib.sha256(path.read_bytes()).hexdigest()
        self.store.db.execute("UPDATE schema_migrations SET checksum=%s WHERE version=%s",
                              ("0" * 64, path.name))
        with self.assertRaisesRegex(RuntimeError, "checksum mismatch"):
            self.store.check_compatibility()
        self.store.db.execute("UPDATE schema_migrations SET checksum=%s WHERE version=%s",
                              (correct,path.name))
        self.store.check_compatibility()

    def test_startup_rejects_partial_and_unknown_newer_schema(self):
        with self.assertRaisesRegex(RuntimeError, "partial database schema"):
            with self.store.db.transaction():
                self.store.db.execute("DELETE FROM schema_migrations WHERE version='014_runtime_identity_security.sql'")
                self.store.check_compatibility()
        with self.assertRaisesRegex(RuntimeError, "partial database schema"):
            with self.store.db.transaction():
                self.store.db.execute("INSERT INTO schema_migrations(version,checksum) VALUES('016_unknown.sql','sha256:unknown')")
                self.store.check_compatibility()

    def test_new_runtime_rejects_014_only_schema(self):
        from orbis.observer.postgres import PostgresStore
        schema = "orbis_old_schema_" + uuid4().hex
        self.store.db.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        old_dir = Path(__file__).resolve().parents[1] / "migrations"
        store = PostgresStore(os.environ["ORBIS_TEST_DATABASE_URL"], schema=schema, runtime_fenced=False)
        try:
            with store.db.transaction():
                store.db.execute("CREATE TABLE schema_migrations(version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now(), checksum TEXT)")
                for migration in sorted(old_dir.glob("*.sql")):
                    if migration.name.startswith("015_"):
                        continue
                    store.db.execute("INSERT INTO schema_migrations(version,checksum) VALUES(%s,%s)",
                                     (migration.name,hashlib.sha256(migration.read_bytes()).hexdigest()))
            with self.assertRaisesRegex(RuntimeError, "partial database schema"):
                store.check_compatibility()
        finally:
            self.store.db.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
            store.close()

    def test_upgrade_migration_preserves_existing_network_id_and_block_rows(self):
        from pathlib import Path
        from orbis.observer.postgres import PostgresStore
        schema = "orbis_upgrade_" + uuid4().hex
        self.store.db.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        upgrade = PostgresStore(os.environ["ORBIS_TEST_DATABASE_URL"], schema=schema, runtime_fenced=False)
        migration_dir = Path(__file__).resolve().parents[1] / "migrations"
        try:
            for migration in sorted(migration_dir.glob("*.sql")):
                if migration.name == "013_network_identity.sql":
                    break
                with upgrade.db.transaction():
                    upgrade.db.execute(migration.read_text())
            inserted = upgrade.db.execute("""INSERT INTO networks(chain_id,name)
                VALUES (1991,'preserved') RETURNING network_id""").fetchone()
            original_id = inserted["network_id"]
            upgrade.db.execute("""INSERT INTO blocks(network_id,number,hash,parent_hash,timestamp,canonical)
                VALUES (%s,0,'0xpreserved','0xparent',1,TRUE)""", (original_id,))
            with upgrade.db.transaction():
                upgrade.db.execute((migration_dir / "013_network_identity.sql").read_text())
            preserved = upgrade.db.execute("""SELECT network_id,network_fingerprint
                FROM networks WHERE chain_id=1991""").fetchone()
            self.assertEqual(preserved["network_id"], original_id)
            self.assertIsNone(preserved["network_fingerprint"])
            self.assertEqual(upgrade.db.execute(
                "SELECT count(*) AS n FROM blocks WHERE network_id=%s", (original_id,)
            ).fetchone()["n"], 1)
        finally:
            upgrade.db.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
            upgrade.close()
