"""Multi-process deployment fencing tests against a marked disposable PostgreSQL DB."""
from __future__ import annotations

import os
import select
import subprocess
import sys
import unittest
from uuid import uuid4

import psycopg
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import dict_row

from orbis.network import verified_context
from orbis.observer.postgres import PostgresStore
from tests.postgres_test_support import require_disposable_database


def setUpModule() -> None:
    require_disposable_database()
    if not os.environ.get("ORBIS_TEST_FENCING_DATABASE_URL", "").strip():
        raise RuntimeError("deployment fencing tests require ORBIS_TEST_FENCING_DATABASE_URL")


class DeploymentFencingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.migration_dsn = os.environ["ORBIS_TEST_DATABASE_URL"]
        cls.runtime_dsn = make_conninfo(**{
            **conninfo_to_dict(cls.migration_dsn), "user": "orbis_runtime",
        })
        cls.security_dsn = os.environ["ORBIS_TEST_FENCING_DATABASE_URL"]
        cls.bootstrap_user = conninfo_to_dict(cls.security_dsn).get("user", "")
        cls.dbname = conninfo_to_dict(cls.migration_dsn).get("dbname", "")
        with psycopg.connect(cls.security_dsn, row_factory=dict_row) as db:
            row = db.execute("""SELECT current_database() AS db,
                shobj_description(oid,'pg_database') AS marker FROM pg_database
                WHERE datname=current_database()""").fetchone()
            if row["db"] != cls.dbname or row["marker"] != "ORBIS_DISPOSABLE_TEST_DATABASE=1":
                raise RuntimeError("fencing tests require the explicitly marked disposable database")
            if not db.execute("SELECT rolsuper FROM pg_roles WHERE rolname=current_user").fetchone()["rolsuper"]:
                raise RuntimeError("fencing test security DSN must be disposable-cluster bootstrap principal")
            db.execute("ALTER ROLE orbis_runtime LOGIN")
        migrator = PostgresStore(cls.migration_dsn, runtime_fenced=False)
        migrator.migrate()
        migrator.db.execute("""UPDATE public.orbis_deployment_control SET maintenance=FALSE,
            reason='fencing test setup',changed_at=clock_timestamp(),changed_by=session_user WHERE singleton""")
        migrator.close()

    @classmethod
    def tearDownClass(cls) -> None:
        with psycopg.connect(cls.security_dsn, autocommit=True) as db:
            db.execute("ALTER ROLE orbis_runtime LOGIN")
        with psycopg.connect(cls.migration_dsn, autocommit=True) as db:
            db.execute("""UPDATE public.orbis_deployment_control SET maintenance=FALSE,
                reason='fencing test cleanup',changed_at=clock_timestamp(),changed_by=session_user WHERE singleton""")

    @staticmethod
    def _child(code: str, dsn: str) -> subprocess.Popen[str]:
        env = dict(os.environ)
        env["FENCE_TEST_DSN"] = dsn
        env["PYTHONPATH"] = os.pathsep.join(filter(None, ["src", env.get("PYTHONPATH", "")]))
        return subprocess.Popen([sys.executable, "-c", code], stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, env=env, bufsize=1)

    def _stop_child(self, child: subprocess.Popen[str]) -> None:
        if child.poll() is None and child.stdin:
            child.stdin.write("stop\n")
            child.stdin.flush()
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=5)
        for stream in (child.stdin, child.stdout, child.stderr):
            if stream:
                stream.close()

    def test_multiple_runtime_processes_drain_and_persist_maintenance(self) -> None:
        runtime_code = """import os,sys
from orbis.observer.postgres import PostgresStore
s=PostgresStore(os.environ['FENCE_TEST_DSN'],runtime_fenced=True)
print('READY',flush=True)
sys.stdin.readline()
s.close()
"""
        deploy_code = """import os,sys
import psycopg
from psycopg.rows import dict_row
from orbis.deployment import acquire_deployment_lock,mark_maintenance,release_deployment_lock
d=psycopg.connect(os.environ['FENCE_TEST_DSN'],autocommit=True,row_factory=dict_row)
acquire_deployment_lock(d,10000)
mark_maintenance(d,'multi-process fencing test','orbis_test_migrator')
print('FENCED',flush=True)
sys.stdin.readline()
release_deployment_lock(d)
d.close()
"""
        children: list[subprocess.Popen[str]] = []
        deploy: subprocess.Popen[str] | None = None
        try:
            for _ in range(2):
                child = self._child(runtime_code, self.runtime_dsn)
                children.append(child)
                line = child.stdout.readline().strip()
                if line != "READY":
                    _, error = child.communicate(timeout=5)
                    self.fail(f"runtime child failed before acquiring its lock: {error}")
            deploy = self._child(deploy_code, self.migration_dsn)
            ready, _, _ = select.select([deploy.stdout], [], [], 0.4)
            self.assertFalse(ready, "exclusive deployment lock must wait for both runtime sessions")
            self._stop_child(children.pop(0))
            ready, _, _ = select.select([deploy.stdout], [], [], 0.2)
            self.assertFalse(ready, "one remaining runtime session must keep the deployment lock blocked")
            self._stop_child(children.pop(0))
            line = deploy.stdout.readline().strip()
            if line != "FENCED":
                _, error = deploy.communicate(timeout=5)
                self.fail(f"deployment child failed to fence: {error}")
            self._stop_child(deploy)
            deploy = None

            rejected = self._child(runtime_code, self.runtime_dsn)
            _, stderr = rejected.communicate(timeout=5)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn("runtime startup blocked by deployment maintenance", stderr)
        finally:
            for child in children:
                self._stop_child(child)
            if deploy:
                self._stop_child(deploy)
            with psycopg.connect(self.migration_dsn, autocommit=True) as db:
                db.execute("""UPDATE public.orbis_deployment_control SET maintenance=FALSE,
                    reason='fencing test reset',changed_at=clock_timestamp(),changed_by=session_user WHERE singleton""")

    def test_fencer_terminates_legacy_session_and_disables_new_login(self) -> None:
        context_store = PostgresStore(self.runtime_dsn)
        context = context_store.resolve_network(verified_context(993304, "0x" + "34" * 32))
        context_store.close()
        block_hash = "0xlegacy-" + uuid4().hex
        block_number = 1_000_000 + uuid4().int % 1_000_000_000
        legacy_code = """import os,sys,psycopg
d=psycopg.connect(os.environ['FENCE_TEST_DSN'],autocommit=True)
n=int(os.environ['FENCE_TEST_NETWORK_ID'])
d.execute("INSERT INTO blocks(network_id,number,hash,parent_hash,timestamp,canonical) VALUES(%s,%s,%s,%s,1,true)",(n,int(os.environ['FENCE_TEST_BLOCK_NUMBER']),os.environ['FENCE_TEST_BLOCK_HASH'],'0xparent'))
print('LEGACY_READY',flush=True)
sys.stdin.readline()
try:
 d.execute("INSERT INTO blocks(network_id,number,hash,parent_hash,timestamp,canonical) VALUES(%s,%s,%s,%s,1,true)",(n,int(os.environ['FENCE_TEST_BLOCK_NUMBER'])+1,'0xlegacy-after-fence','0xparent'))
 print('LEGACY_STILL_CONNECTED',flush=True)
except psycopg.OperationalError:
 print('LEGACY_SESSION_TERMINATED',flush=True)
"""
        legacy_env = dict(os.environ)
        legacy_env.update(PYTHONPATH=os.pathsep.join(filter(None,["src",os.environ.get("PYTHONPATH","")])),
                          FENCE_TEST_DSN=self.runtime_dsn,
                          FENCE_TEST_NETWORK_ID=str(context.network_id),
                          FENCE_TEST_BLOCK_NUMBER=str(block_number),
                          FENCE_TEST_BLOCK_HASH=block_hash)
        legacy = subprocess.Popen([sys.executable,"-c",legacy_code],stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=legacy_env)
        try:
            line = legacy.stdout.readline().strip()
            if line != "LEGACY_READY":
                _, error = legacy.communicate(timeout=5)
                self.fail(f"legacy child failed before session termination: {error}")
            from orbis.db_fence import fence_runtime
            with psycopg.connect(self.security_dsn, autocommit=True, row_factory=dict_row) as security:
                terminated = fence_runtime(security, "orbis_runtime", "orbis_test_migrator", 10)
                self.assertGreaterEqual(terminated, 1)
            legacy.stdin.write("check\n")
            legacy.stdin.flush()
            self.assertEqual(legacy.stdout.readline().strip(), "LEGACY_SESSION_TERMINATED")
            self.assertEqual(legacy.wait(timeout=5), 0)
            with psycopg.connect(self.security_dsn, row_factory=dict_row) as security:
                self.assertFalse(security.execute(
                    "SELECT rolcanlogin FROM pg_roles WHERE rolname='orbis_runtime'"
                ).fetchone()["rolcanlogin"])
                self.assertEqual(security.execute("""SELECT count(*) AS n FROM pg_stat_activity
                    WHERE datname=current_database() AND usename='orbis_runtime'""").fetchone()["n"], 0)
                self.assertEqual(security.execute("SELECT count(*) AS n FROM blocks WHERE network_id=%s AND number=%s AND hash=%s",
                    (context.network_id,block_number,block_hash)).fetchone()["n"], 1)
            with self.assertRaises(psycopg.OperationalError):
                psycopg.connect(self.runtime_dsn, connect_timeout=1)
            with self.assertRaises(psycopg.OperationalError):
                PostgresStore(self.runtime_dsn, runtime_fenced=True)
        finally:
            self._stop_child(legacy)
            with psycopg.connect(self.security_dsn, autocommit=True) as security:
                security.execute("ALTER ROLE orbis_runtime LOGIN")
            with psycopg.connect(self.migration_dsn, autocommit=True) as db:
                db.execute("""UPDATE public.orbis_deployment_control SET maintenance=FALSE,
                    reason='legacy fence test reset',changed_at=clock_timestamp(),changed_by=session_user WHERE singleton""")


if __name__ == "__main__":
    unittest.main()
