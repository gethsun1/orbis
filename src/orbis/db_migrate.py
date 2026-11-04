"""Apply pending PostgreSQL schema migrations."""

from __future__ import annotations

import os
import psycopg
from psycopg.conninfo import conninfo_to_dict

from orbis.deployment import acquire_deployment_lock, release_deployment_lock
from orbis.observer.postgres import PostgresStore


def main() -> None:
    dsn = os.environ.get("ORBIS_MIGRATION_DATABASE_URL", "").strip()
    if not dsn:
        raise ValueError("ORBIS_MIGRATION_DATABASE_URL must be set; migrations use a separate principal from runtime")
    runtime_dsn = os.environ.get("ORBIS_DATABASE_URL", "").strip()
    runtime_user = conninfo_to_dict(runtime_dsn).get("user", "").strip()
    migration_user = conninfo_to_dict(dsn).get("user", "").strip()
    if not runtime_user or not migration_user or runtime_user == migration_user:
        raise ValueError("ORBIS_DATABASE_URL and ORBIS_MIGRATION_DATABASE_URL must name distinct PostgreSQL principals")
    with psycopg.connect(dsn) as connection:
        identity = connection.execute("""SELECT current_user AS role,r.rolsuper,r.rolcanlogin
            FROM pg_roles r WHERE r.rolname=current_user""").fetchone()
        if identity[0] != migration_user:
            raise ValueError("migration DSN role does not match its authenticated PostgreSQL principal")
        if identity[1] or not identity[2]:
            raise ValueError("migration principal must be a non-superuser login")
    store = PostgresStore(dsn, runtime_fenced=False)
    try:
        acquire_deployment_lock(store.db, int(os.environ.get("ORBIS_DEPLOYMENT_LOCK_TIMEOUT_MS", "60000")))
        try:
            actual = store.db.execute("SELECT current_user AS role").fetchone()["role"]
            runtime_state = store.db.execute(
                "SELECT rolcanlogin FROM pg_roles WHERE rolname=%s", (runtime_user,)
            ).fetchone()
            if not runtime_state or runtime_state["rolcanlogin"]:
                raise RuntimeError("runtime login must be fenced before migrations")
            if store.db.execute("""SELECT count(*) AS n FROM pg_stat_activity
                WHERE datname=current_database() AND usename=%s AND pid<>pg_backend_pid()""",
                (runtime_user,)).fetchone()["n"]:
                raise RuntimeError("runtime sessions remain; refusing to migrate")
            if not store.db.execute(
                "SELECT to_regclass('public.orbis_deployment_control') IS NOT NULL AS present"
            ).fetchone()["present"]:
                raise RuntimeError("runtime maintenance fence is missing; run orbis-db-fence first")
            state = store.db.execute(
                "SELECT maintenance FROM public.orbis_deployment_control WHERE singleton"
            ).fetchone()
            if not state or not state["maintenance"]:
                raise RuntimeError("deployment is not fenced; refusing to migrate")
            executor_exists = store.db.execute(
                "SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='orbis_registry_executor') AS present"
            ).fetchone()["present"]
            if executor_exists:
                is_member = store.db.execute(
                    "SELECT pg_has_role(%s,'orbis_registry_executor','MEMBER') AS member", (actual,)
                ).fetchone()["member"]
                has_014 = store.db.execute(
                    "SELECT to_regclass('schema_migrations') IS NOT NULL AS present"
                ).fetchone()["present"]
                applied_014 = False
                if has_014:
                    applied_014 = bool(store.db.execute(
                        "SELECT EXISTS(SELECT 1 FROM schema_migrations WHERE version='014_runtime_identity_security.sql') AS applied"
                    ).fetchone()["applied"])
                if applied_014 and is_member:
                    raise RuntimeError(
                        "migration principal retains unnecessary orbis_registry_executor membership; revoke it before migration"
                    )
                if not applied_014 and not is_member:
                    raise RuntimeError(
                        "migration 014 requires temporary orbis_registry_executor membership to transfer function ownership"
                    )
            if store.db.execute(
                "SELECT CASE WHEN EXISTS(SELECT 1 FROM pg_roles WHERE rolname='orbis_identity_admin') "
                "THEN pg_has_role(%s,'orbis_identity_admin','MEMBER') ELSE FALSE END AS member", (actual,)
            ).fetchone()["member"]:
                raise RuntimeError("migration principal must not inherit identity admin membership")
            store.migrate()
            print("PostgreSQL migrations applied; runtime remains fenced pending orbis-db-activate")
        finally:
            release_deployment_lock(store.db)
    finally:
        store.close()


if __name__ == "__main__":
    main()
