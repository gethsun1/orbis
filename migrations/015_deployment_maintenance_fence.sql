-- Persistent maintenance state for the coordinated runtime/migration fence.
-- The migration command sets this state before applying the migration chain and
-- only the explicit deployment activation command may clear it.
CREATE TABLE IF NOT EXISTS orbis_deployment_control (
  singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton IS TRUE),
  maintenance BOOLEAN NOT NULL DEFAULT TRUE,
  reason TEXT NOT NULL,
  changed_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  changed_by TEXT NOT NULL DEFAULT session_user
);

INSERT INTO orbis_deployment_control(singleton,maintenance,reason,changed_by)
VALUES(TRUE,TRUE,'deployment activation required',session_user)
ON CONFLICT(singleton) DO NOTHING;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='orbis_runtime')
     AND NOT has_table_privilege('orbis_runtime','orbis_deployment_control','SELECT') THEN
    EXECUTE format('GRANT SELECT ON orbis_deployment_control TO %I','orbis_runtime');
  END IF;
END $$;
