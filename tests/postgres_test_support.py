"""Fail-closed guard for the explicitly marked disposable PostgreSQL test database."""
from __future__ import annotations

import os

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row

MARKER = "ORBIS_DISPOSABLE_TEST_DATABASE=1"


def require_disposable_database() -> str:
    dsn = os.environ.get("ORBIS_TEST_DATABASE_URL", "").strip()
    if not dsn:
        raise RuntimeError("PostgreSQL integration tests require ORBIS_TEST_DATABASE_URL; tests do not skip")
    params = conninfo_to_dict(dsn)
    dbname = params.get("dbname", "")
    host = params.get("host", "")
    if not dbname.startswith("orbis_test_"):
        raise RuntimeError("refusing PostgreSQL tests: database name must start with orbis_test_")
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("refusing PostgreSQL tests: disposable database must use loopback TCP")
    try:
        with psycopg.connect(dsn, connect_timeout=3, row_factory=dict_row) as db:
            row = db.execute("""SELECT current_database() AS name,current_user AS role,
                (SELECT rolsuper FROM pg_roles WHERE rolname=current_user) AS superuser,
                shobj_description(oid,'pg_database') AS marker,
                current_setting('server_version') AS version
                FROM pg_database WHERE datname=current_database()""").fetchone()
    except Exception as exc:
        raise RuntimeError("cannot connect to explicitly configured disposable PostgreSQL test database") from exc
    if row["name"] != dbname or row["marker"] != MARKER:
        raise RuntimeError("refusing PostgreSQL tests: database lacks the disposable-test marker")
    if row["role"] != "orbis_test_migrator" or row["superuser"]:
        raise RuntimeError("PostgreSQL integration tests must connect as non-superuser orbis_test_migrator")
    return row["version"]
