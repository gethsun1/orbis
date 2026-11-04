"""Provision ORBIS test roles/database only inside a marked loopback disposable cluster."""

from __future__ import annotations

import os
import sys

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo


MARKER = "ORBIS_DISPOSABLE_TEST_DATABASE=1"
BOOTSTRAP_ROLE = "orbis_test_bootstrap"


def main() -> None:
    dsn = os.environ.get("ORBIS_TEST_BOOTSTRAP_DATABASE_URL", "").strip()
    database = os.environ.get("ORBIS_TEST_TARGET_DATABASE", "").strip()
    params = conninfo_to_dict(dsn)
    if not dsn or not database.startswith("orbis_test_"):
        raise ValueError("provide a bootstrap DSN and an orbis_test_ target database name")
    if params.get("host", "") not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("refusing provisioning outside loopback PostgreSQL")
    if params.get("dbname", "") == database:
        raise ValueError("bootstrap database and target database must be distinct")

    with psycopg.connect(dsn, autocommit=True) as db:
        actor = db.execute("SELECT current_user").fetchone()[0]
        if actor != BOOTSTRAP_ROLE:
            raise RuntimeError(f"expected authenticated disposable bootstrap role {BOOTSTRAP_ROLE}")
        marker = db.execute("""SELECT shobj_description(oid,'pg_database')
            FROM pg_database WHERE datname=current_database()""").fetchone()[0]
        if marker != MARKER:
            raise RuntimeError("bootstrap database is not explicitly marked disposable")
        if not db.execute("SELECT rolsuper FROM pg_roles WHERE rolname=current_user").fetchone()[0]:
            raise RuntimeError("bootstrap principal must be superuser in this disposable cluster")

        roles = {
            "orbis_test_migrator": "LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE",
            "orbis_runtime": "LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE",
            "orbis_registry_executor": "NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE",
            "orbis_identity_admin": "LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE",
            "orbis_deployment_fencer": "NOINHERIT LOGIN NOSUPERUSER NOCREATEDB CREATEROLE",
            "orbis_test_runtime": "LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE",
        }
        for name, attributes in roles.items():
            exists = db.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (name,)).fetchone()
            if not exists:
                db.execute(sql.SQL("CREATE ROLE {} " + attributes).format(sql.Identifier(name)))
        db.execute("ALTER ROLE orbis_deployment_fencer NOINHERIT")
        expected = {
            "orbis_test_migrator": (True,True,False,False,False),
            "orbis_runtime": (True,True,False,False,False),
            "orbis_registry_executor": (False,True,False,False,False),
            "orbis_identity_admin": (True,True,False,False,False),
            "orbis_deployment_fencer": (True,False,False,False,True),
            "orbis_test_runtime": (True,True,False,False,False),
        }
        for name, wanted in expected.items():
            role = db.execute("""SELECT rolcanlogin,rolinherit,rolsuper,rolcreatedb,rolcreaterole
                FROM pg_roles WHERE rolname=%s""",(name,)).fetchone()
            if tuple(role) != wanted:
                raise RuntimeError(f"disposable role {name} exists with unexpected attributes")
        db.execute("GRANT orbis_registry_executor TO orbis_test_migrator")
        db.execute("GRANT pg_signal_backend TO orbis_deployment_fencer")
        db.execute("GRANT orbis_runtime TO orbis_deployment_fencer WITH ADMIN OPTION, INHERIT FALSE, SET FALSE")
        exists = db.execute("SELECT 1 FROM pg_database WHERE datname=%s", (database,)).fetchone()
        if exists:
            raise RuntimeError("refusing to modify an existing target database; use a fresh orbis_test_ name")
        db.execute(sql.SQL("CREATE DATABASE {} OWNER orbis_test_migrator").format(sql.Identifier(database)))

    target_dsn = make_conninfo(dsn, dbname=database)
    with psycopg.connect(target_dsn, autocommit=True) as db:
        owner = db.execute("""SELECT pg_get_userbyid(datdba) FROM pg_database
            WHERE datname=current_database()""").fetchone()[0]
        if owner != "orbis_test_migrator":
            raise RuntimeError("target database already exists with unexpected owner")
        db.execute(sql.SQL("COMMENT ON DATABASE {} IS {}").format(
            sql.Identifier(database),sql.Literal(MARKER)))
        db.execute("""CREATE TABLE IF NOT EXISTS public.orbis_deployment_control (
            singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton IS TRUE),
            maintenance BOOLEAN NOT NULL DEFAULT TRUE,
            reason TEXT NOT NULL,
            changed_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            changed_by TEXT NOT NULL DEFAULT session_user
        )""")
        db.execute("ALTER TABLE public.orbis_deployment_control OWNER TO orbis_deployment_fencer")
        db.execute("REVOKE ALL ON public.orbis_deployment_control FROM PUBLIC")
        db.execute("GRANT SELECT,INSERT,UPDATE ON public.orbis_deployment_control TO orbis_test_migrator")
        db.execute("GRANT SELECT ON public.orbis_deployment_control TO orbis_runtime")
        db.execute("""INSERT INTO public.orbis_deployment_control(singleton,maintenance,reason,changed_by)
            VALUES(TRUE,TRUE,'disposable database awaits deployment',session_user)
            ON CONFLICT(singleton) DO NOTHING""")
        control_owner = db.execute("""SELECT pg_get_userbyid(c.relowner) FROM pg_class c
            JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='public' AND c.relname='orbis_deployment_control'""").fetchone()[0]
        if control_owner != "orbis_deployment_fencer":
            raise RuntimeError("deployment control table has unexpected owner")
    print(f"Provisioned disposable database {database}; no passwords or production secrets were set")


if __name__ == "__main__":
    main()
