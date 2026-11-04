"""Validate a migrated PostgreSQL database and explicitly release runtime fencing."""

from __future__ import annotations

import os

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

from orbis.deployment import (
    acquire_deployment_lock,
    release_deployment_lock,
    runtime_role_is_privileged,
    validate_registry_function,
    validate_runtime_grants,
)
from orbis.observer.postgres import PostgresStore


def main() -> None:
    dsn = os.environ.get("ORBIS_MIGRATION_DATABASE_URL", "").strip()
    runtime_dsn = os.environ.get("ORBIS_DATABASE_URL", "").strip()
    migration_user = conninfo_to_dict(dsn).get("user", "").strip()
    runtime_user = conninfo_to_dict(runtime_dsn).get("user", "").strip()
    if not dsn or not runtime_user or not migration_user or migration_user == runtime_user:
        raise ValueError("activation requires distinct explicit runtime and migration PostgreSQL principals")
    security_dsn = os.environ.get("ORBIS_FENCING_DATABASE_URL", "").strip()
    security_user = conninfo_to_dict(security_dsn).get("user", "").strip()
    if not security_user or security_user in {runtime_user,migration_user}:
        raise ValueError("activation requires a separate deployment security principal")
    dsn_databases = {conninfo_to_dict(value).get("dbname", "").strip()
                     for value in (dsn,runtime_dsn,security_dsn)}
    if len(dsn_databases) != 1 or not next(iter(dsn_databases)):
        raise ValueError("activation DSNs must name the same PostgreSQL database")

    store = PostgresStore(dsn, runtime_fenced=False)
    try:
        actual_user = store.db.execute("SELECT current_user AS role").fetchone()["role"]
        if actual_user != migration_user:
            raise RuntimeError("activation connection does not match the migration principal")
        migration_role = store.db.execute("SELECT rolsuper,rolcanlogin FROM pg_roles WHERE rolname=%s",
                                          (migration_user,)).fetchone()
        if not migration_role or migration_role["rolsuper"] or not migration_role["rolcanlogin"]:
            raise RuntimeError("activation migration principal must be a non-superuser login")
        acquire_deployment_lock(store.db, int(os.environ.get("ORBIS_DEPLOYMENT_LOCK_TIMEOUT_MS", "60000")))
        try:
            store.check_compatibility()
            if runtime_role_is_privileged(store.db, runtime_user):
                raise RuntimeError("runtime principal inherits executor/admin privileges")
            if store.db.execute(
                "SELECT pg_has_role(%s,'orbis_registry_executor','MEMBER') AS member", (migration_user,)
            ).fetchone()["member"]:
                raise RuntimeError(
                    "migration principal still has temporary registry executor membership; security provisioning must revoke it"
                )
            validate_runtime_grants(store.db, runtime_user)
            validate_registry_function(store.db)
            if not store.db.execute(
                "SELECT has_table_privilege(%s,'public.orbis_deployment_control','SELECT') AS allowed",
                (runtime_user,),
            ).fetchone()["allowed"]:
                raise RuntimeError("runtime cannot read deployment maintenance state")
            control_writable = store.db.execute("""SELECT
                has_table_privilege(%s,'public.orbis_deployment_control','INSERT') OR
                has_table_privilege(%s,'public.orbis_deployment_control','UPDATE') OR
                has_table_privilege(%s,'public.orbis_deployment_control','DELETE') AS writable""",
                (runtime_user,runtime_user,runtime_user)).fetchone()["writable"]
            if control_writable:
                raise RuntimeError("runtime must not alter deployment maintenance state")
            state = store.db.execute(
                "SELECT maintenance FROM public.orbis_deployment_control WHERE singleton"
            ).fetchone()
            if not state:
                raise RuntimeError("deployment maintenance state is missing")
            sessions = store.db.execute("""SELECT count(*) AS n FROM pg_stat_activity
                WHERE datname=current_database() AND usename=%s AND pid<>pg_backend_pid()""",
                (runtime_user,)).fetchone()["n"]
            if sessions:
                raise RuntimeError("runtime sessions exist while deployment activation is being validated")
            if not state["maintenance"]:
                runtime_can_login = store.db.execute(
                    "SELECT rolcanlogin FROM pg_roles WHERE rolname=%s", (runtime_user,)
                ).fetchone()["rolcanlogin"]
                if runtime_can_login:
                    raise RuntimeError("deployment is already active; no activation change was made")
            store.db.execute("""UPDATE public.orbis_deployment_control
                SET maintenance=FALSE,reason='schema and runtime security checks passed',
                    changed_at=clock_timestamp(),changed_by=session_user WHERE singleton""")
            with psycopg.connect(security_dsn, autocommit=True, row_factory=dict_row) as security:
                actor = security.execute("SELECT current_user AS role").fetchone()["role"]
                if actor != security_user:
                    raise RuntimeError("fencing DSN does not match the authenticated security principal")
                from orbis.db_fence import _require_security_principal
                _require_security_principal(security, security_user, runtime_user)
                security.execute(sql.SQL("ALTER ROLE {} LOGIN").format(sql.Identifier(runtime_user)))
            print("Deployment validation passed; runtime fencing released")
        finally:
            release_deployment_lock(store.db)
    finally:
        store.close()


if __name__ == "__main__":
    main()
