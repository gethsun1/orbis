"""Fence runtime logins and sessions before a coordinated schema deployment."""

from __future__ import annotations

import os
import time

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

from orbis.deployment import acquire_deployment_lock, mark_maintenance, release_deployment_lock


def _require_security_principal(db, actor: str, runtime_role: str) -> None:
    row = db.execute("""SELECT r.rolsuper,r.rolcreaterole,
        pg_has_role(%s,'pg_signal_backend','MEMBER') AS signal_backend
        FROM pg_roles r WHERE r.rolname=%s""", (actor, actor)).fetchone()
    if not row or not (row["rolsuper"] or row["rolcreaterole"]) \
            or not (row["rolsuper"] or row["signal_backend"]):
        raise RuntimeError("fencing principal requires CREATEROLE and pg_signal_backend capability")
    if not row["rolsuper"]:
        membership = db.execute("""SELECT m.admin_option,m.inherit_option,m.set_option
            FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.roleid
            JOIN pg_roles u ON u.oid=m.member
            WHERE r.rolname=%s AND u.rolname=%s""", (runtime_role,actor)).fetchone()
        if not membership or not membership["admin_option"] or membership["inherit_option"] or membership["set_option"]:
            raise RuntimeError("fencing principal needs non-inheriting, non-settable ADMIN OPTION on runtime role")


def fence_runtime(db, runtime_role: str, migration_role: str, timeout_seconds: int = 60) -> int:
    """Drain cooperative sessions, deny future login, kill legacy sessions, persist maintenance."""
    if timeout_seconds < 1:
        raise ValueError("fence timeout must be positive")
    acquire_deployment_lock(db, timeout_seconds * 1000)
    try:
        mark_maintenance(db, "runtime fenced; deployment activation required", migration_role)
        db.execute(sql.SQL("ALTER ROLE {} NOLOGIN").format(sql.Identifier(runtime_role)))
        rows = db.execute("""SELECT pid FROM pg_stat_activity
            WHERE datname=current_database() AND usename=%s AND pid<>pg_backend_pid()""",
            (runtime_role,)).fetchall()
        pids = [row["pid"] for row in rows]
        if pids:
            db.execute("SELECT pg_terminate_backend(pid) FROM unnest(%s::int[]) AS pid", (pids,))
        deadline = time.monotonic() + timeout_seconds
        while True:
            count = db.execute("""SELECT count(*) AS n FROM pg_stat_activity
                WHERE datname=current_database() AND usename=%s AND pid<>pg_backend_pid()""",
                (runtime_role,)).fetchone()["n"]
            if not count:
                return len(pids)
            if time.monotonic() >= deadline:
                raise RuntimeError(f"runtime fencing incomplete: {count} database sessions remain")
            time.sleep(0.1)
    finally:
        release_deployment_lock(db)


def main() -> None:
    runtime_dsn = os.environ.get("ORBIS_DATABASE_URL", "").strip()
    migration_dsn = os.environ.get("ORBIS_MIGRATION_DATABASE_URL", "").strip()
    security_dsn = os.environ.get("ORBIS_FENCING_DATABASE_URL", "").strip()
    runtime_role = conninfo_to_dict(runtime_dsn).get("user", "").strip()
    migration_role = conninfo_to_dict(migration_dsn).get("user", "").strip()
    security_role = conninfo_to_dict(security_dsn).get("user", "").strip()
    dbnames = {conninfo_to_dict(dsn).get("dbname", "").strip()
               for dsn in (runtime_dsn, migration_dsn, security_dsn) if dsn}
    if not runtime_role or not migration_role or not security_role or len(dbnames) != 1:
        raise ValueError("fencing requires runtime, migration, and security DSNs naming one database")
    if len([dsn for dsn in (runtime_dsn,migration_dsn,security_dsn) if dsn]) != 3:
        raise ValueError("fencing requires all three database connection strings")
    if len({runtime_role, migration_role, security_role}) != 3:
        raise ValueError("runtime, migration, and fencing principals must be distinct")
    with psycopg.connect(security_dsn, autocommit=True, row_factory=dict_row) as db:
        actor = db.execute("SELECT current_user AS role").fetchone()["role"]
        if actor != security_role:
            raise RuntimeError("fencing DSN does not match the authenticated security principal")
        _require_security_principal(db, actor, runtime_role)
        if db.execute("SELECT current_database() AS dbname").fetchone()["dbname"] != next(iter(dbnames)):
            raise RuntimeError("fencing connection database does not match the runtime DSN")
        sessions = fence_runtime(db, runtime_role, migration_role,
            int(os.environ.get("ORBIS_DEPLOYMENT_LOCK_TIMEOUT_SECONDS", "60")))
        print(f"Runtime fenced; terminated {sessions} pre-existing runtime session(s)")


if __name__ == "__main__":
    main()
