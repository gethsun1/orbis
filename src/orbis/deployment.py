"""PostgreSQL deployment fencing shared by runtime and deployment commands."""

from __future__ import annotations

# Stable database-wide lock key. Shared locks are held for each runtime session;
# migrations and activation require the exclusive form.
DEPLOYMENT_LOCK_KEY = 5715703759783740750
CONTROL_TABLE = "public.orbis_deployment_control"


def _bounded_lock_wait(db, timeout_ms: int) -> None:
    if timeout_ms < 1:
        raise ValueError("deployment lock timeout must be positive")
    db.execute("SELECT set_config('statement_timeout', %s, false)", (f"{timeout_ms}ms",))


def acquire_runtime_lock(db, timeout_ms: int = 15000) -> None:
    """Hold a shared session lock and reject startup while maintenance is active."""
    _bounded_lock_wait(db, timeout_ms)
    try:
        db.execute("SELECT pg_advisory_lock_shared(%s)", (DEPLOYMENT_LOCK_KEY,))
    finally:
        db.execute("SELECT set_config('statement_timeout', '0', false)")
    try:
        if db.execute("SELECT to_regclass(%s) AS relation", (CONTROL_TABLE,)).fetchone()["relation"]:
            row = db.execute(
                "SELECT maintenance,reason FROM public.orbis_deployment_control WHERE singleton"
            ).fetchone()
            if not row or row["maintenance"]:
                reason = row["reason"] if row else "deployment state is missing"
                raise RuntimeError(f"runtime startup blocked by deployment maintenance: {reason}")
    except Exception:
        db.execute("SELECT pg_advisory_unlock_shared(%s)", (DEPLOYMENT_LOCK_KEY,))
        raise


def acquire_deployment_lock(db, timeout_ms: int = 60000) -> None:
    """Drain shared runtime sessions and hold the exclusive deployment lock."""
    _bounded_lock_wait(db, timeout_ms)
    try:
        db.execute("SELECT pg_advisory_lock(%s)", (DEPLOYMENT_LOCK_KEY,))
    finally:
        db.execute("SELECT set_config('statement_timeout', '0', false)")


def mark_maintenance(db, reason: str, migration_role: str | None = None) -> None:
    """Persist a fail-closed maintenance state in the security-provisioned control table."""
    if not db.execute("SELECT to_regclass(%s) AS relation", (CONTROL_TABLE,)).fetchone()["relation"]:
        raise RuntimeError("deployment control table is missing; security provisioning is incomplete")
    db.execute("REVOKE ALL ON public.orbis_deployment_control FROM PUBLIC")
    if migration_role:
        from psycopg import sql
        db.execute(sql.SQL("GRANT SELECT,INSERT,UPDATE ON public.orbis_deployment_control TO {}").format(
            sql.Identifier(migration_role)))
    if db.execute(
        "SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='orbis_runtime') AS present"
    ).fetchone()["present"]:
        db.execute("GRANT SELECT ON public.orbis_deployment_control TO orbis_runtime")
        db.execute("REVOKE INSERT,UPDATE,DELETE,TRUNCATE ON public.orbis_deployment_control FROM orbis_runtime")
    db.execute("""INSERT INTO public.orbis_deployment_control(singleton,maintenance,reason,changed_by)
        VALUES(TRUE,TRUE,%s,session_user)
        ON CONFLICT(singleton) DO UPDATE SET maintenance=TRUE,reason=EXCLUDED.reason,
          changed_at=clock_timestamp(),changed_by=session_user""", (reason,))


def release_deployment_lock(db) -> None:
    db.execute("SELECT pg_advisory_unlock(%s)", (DEPLOYMENT_LOCK_KEY,))


def runtime_role_is_privileged(db, runtime_role: str) -> bool:
    row = db.execute(
        """SELECT pg_has_role(%s,'orbis_registry_executor','MEMBER') AS executor,
                  CASE WHEN EXISTS(SELECT 1 FROM pg_roles WHERE rolname='orbis_identity_admin')
                    THEN pg_has_role(%s,'orbis_identity_admin','MEMBER') ELSE FALSE END AS identity_admin""",
        (runtime_role, runtime_role),
    ).fetchone()
    return bool(row["executor"] or row["identity_admin"])


def validate_runtime_grants(db, runtime_role: str) -> None:
    row = db.execute("""SELECT
        has_table_privilege(%s,'public.networks','SELECT') AS registry_select,
        has_table_privilege(%s,'public.networks','INSERT') AS registry_insert,
        has_table_privilege(%s,'public.networks','UPDATE') AS registry_update,
        has_table_privilege(%s,'public.networks','DELETE') AS registry_delete,
        has_table_privilege(%s,'public.network_identity_audit','UPDATE') AS audit_update,
        has_table_privilege(%s,'public.network_identity_audit','SELECT') AS audit_select,
        has_function_privilege(%s,
          'public.orbis_register_network_identity(bigint,text,text,text,text,text,text)','EXECUTE') AS register""",
        (runtime_role,runtime_role,runtime_role,runtime_role,runtime_role,runtime_role,runtime_role)).fetchone()
    if not row["registry_select"] or row["registry_insert"] or row["registry_update"] \
            or row["registry_delete"] or row["audit_update"] or row["audit_select"] or not row["register"]:
        raise RuntimeError("runtime registry or audit grants do not match the restricted permission policy")


def validate_registry_function(db) -> None:
    row = db.execute("""SELECT p.prosecdef,pg_get_userbyid(p.proowner) AS owner,
        p.proconfig,has_function_privilege('public',p.oid,'EXECUTE') AS public_execute
        FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
        WHERE n.nspname='public' AND p.proname='orbis_register_network_identity'""").fetchone()
    if not row or not row["prosecdef"] or row["owner"] != "orbis_registry_executor" \
            or row["public_execute"] or not row["proconfig"] \
            or not any(value.startswith("search_path=pg_catalog, public") for value in row["proconfig"]):
        raise RuntimeError("restricted registry function ownership or search_path validation failed")
    admin_ops = db.execute("""SELECT count(*) AS n FROM pg_proc p
        JOIN pg_namespace n ON n.oid=p.pronamespace
        WHERE n.nspname='public' AND p.proname IN
          ('orbis_backfill_network_identity','orbis_repair_network_identity')""").fetchone()["n"]
    if admin_ops:
        raise RuntimeError("administrative identity functions must remain unavailable")
