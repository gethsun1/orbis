-- Runtime identity registration is mediated by a narrow definer function.
-- Deployment provisioning must create the NOLOGIN executor before applying this
-- migration; it must not be a member of the runtime login role.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'orbis_registry_executor') THEN
    RAISE EXCEPTION 'required NOLOGIN role orbis_registry_executor is missing';
  END IF;
  IF (SELECT rolcanlogin FROM pg_roles WHERE rolname = 'orbis_registry_executor') THEN
    RAISE EXCEPTION 'orbis_registry_executor must be NOLOGIN';
  END IF;
END $$;

CREATE TABLE network_identity_audit (
  event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  occurred_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  event_type TEXT NOT NULL,
  outcome TEXT NOT NULL CHECK (outcome IN ('success','denied','rejected')),
  actor TEXT NOT NULL,
  effective_role TEXT NOT NULL,
  network_id BIGINT,
  chain_id BIGINT,
  fingerprint_scheme TEXT,
  network_fingerprint TEXT,
  reason TEXT NOT NULL DEFAULT '',
  details JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE OR REPLACE FUNCTION orbis_register_network_identity(
  p_chain_id BIGINT, p_scheme TEXT, p_fingerprint TEXT, p_genesis_hash TEXT,
  p_name TEXT DEFAULT '', p_environment TEXT DEFAULT '', p_provider TEXT DEFAULT ''
) RETURNS BIGINT
LANGUAGE plpgsql SECURITY DEFINER
AS $$
DECLARE v_id BIGINT;
BEGIN
  IF p_chain_id IS NULL OR p_chain_id <= 0 OR p_scheme IS DISTINCT FROM 'evm-genesis-sha256-v1'
     OR p_fingerprint IS NULL OR p_fingerprint !~ '^sha256:[0-9a-f]{64}$'
     OR p_genesis_hash IS NULL OR p_genesis_hash !~ '^0x[0-9a-f]{64}$'
     OR p_fingerprint <> 'sha256:' || encode(sha256(convert_to('{"chain_id":' || p_chain_id::text || ',"genesis_hash":"' || p_genesis_hash || '"}', 'UTF8')), 'hex')
  THEN
    INSERT INTO network_identity_audit(event_type,outcome,actor,effective_role,chain_id,reason)
      VALUES('registration','rejected',session_user,current_user,p_chain_id,'invalid canonical identity tuple');
    RETURN NULL;
  END IF;
  INSERT INTO networks(chain_id,name,environment,provider_name,fingerprint_scheme,network_fingerprint,genesis_hash)
  VALUES(p_chain_id,coalesce(p_name,''),coalesce(nullif(p_environment,''),'unknown'),coalesce(p_provider,''),p_scheme,p_fingerprint,p_genesis_hash)
  ON CONFLICT (chain_id,fingerprint_scheme,network_fingerprint)
    WHERE network_fingerprint IS NOT NULL DO NOTHING;
  SELECT network_id INTO v_id FROM networks
    WHERE chain_id=p_chain_id AND fingerprint_scheme=p_scheme AND network_fingerprint=p_fingerprint
      AND genesis_hash=p_genesis_hash;
  IF v_id IS NULL THEN
    INSERT INTO network_identity_audit(event_type,outcome,actor,effective_role,chain_id,
        fingerprint_scheme,network_fingerprint,reason)
      VALUES('registration','rejected',session_user,current_user,p_chain_id,p_scheme,p_fingerprint,'identity tuple conflicts with existing registry row');
    RETURN NULL;
  END IF;
  INSERT INTO network_identity_audit(event_type,outcome,actor,effective_role,network_id,chain_id,
      fingerprint_scheme,network_fingerprint,reason)
    VALUES('registration','success',session_user,current_user,v_id,p_chain_id,p_scheme,p_fingerprint,'verified runtime registration');
  RETURN v_id;
END $$;

REVOKE ALL ON FUNCTION orbis_register_network_identity(BIGINT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT) FROM PUBLIC;
REVOKE ALL ON network_identity_audit FROM PUBLIC;
REVOKE UPDATE, DELETE, TRUNCATE ON network_identity_audit FROM PUBLIC;
GRANT SELECT, INSERT ON network_identity_audit TO orbis_registry_executor;
GRANT USAGE, SELECT ON SEQUENCE network_identity_audit_event_id_seq TO orbis_registry_executor;
GRANT SELECT, INSERT ON networks TO orbis_registry_executor;
DO $$ BEGIN
  EXECUTE format('GRANT USAGE, CREATE ON SCHEMA %I TO orbis_registry_executor', current_schema());
END $$;
ALTER FUNCTION orbis_register_network_identity(BIGINT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT) OWNER TO orbis_registry_executor;
DO $$ BEGIN
  EXECUTE format('ALTER FUNCTION %I.orbis_register_network_identity(BIGINT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT) SET search_path = pg_catalog, %I', current_schema(), current_schema());
  EXECUTE format('REVOKE CREATE ON SCHEMA %I FROM orbis_registry_executor', current_schema());
END $$;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='orbis_runtime') THEN
    EXECUTE format('GRANT USAGE ON SCHEMA %I TO orbis_runtime', current_schema());
    GRANT EXECUTE ON FUNCTION orbis_register_network_identity(BIGINT,TEXT,TEXT,TEXT,TEXT,TEXT,TEXT) TO orbis_runtime;
    REVOKE INSERT, UPDATE, DELETE ON networks FROM orbis_runtime;
    GRANT SELECT ON networks TO orbis_runtime;
    GRANT SELECT ON schema_migrations TO orbis_runtime;
    EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA %I TO orbis_runtime', current_schema());
    EXECUTE format('REVOKE INSERT, UPDATE, DELETE ON networks, network_identity_audit FROM orbis_runtime');
    REVOKE ALL ON SEQUENCE network_identity_audit_event_id_seq FROM orbis_runtime;
    EXECUTE format('GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA %I TO orbis_runtime', current_schema());
    REVOKE ALL ON network_identity_audit FROM orbis_runtime;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='orbis_identity_admin') THEN
    EXECUTE format('GRANT USAGE ON SCHEMA %I TO orbis_identity_admin', current_schema());
    GRANT SELECT ON network_identity_audit TO orbis_identity_admin;
  END IF;
END $$;

CREATE OR REPLACE FUNCTION orbis_deny_identity_audit_mutation() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $$
BEGIN RAISE EXCEPTION 'network identity audit is append-only'; END $$;
CREATE TRIGGER network_identity_audit_immutable BEFORE UPDATE OR DELETE OR TRUNCATE ON network_identity_audit
  FOR EACH STATEMENT EXECUTE FUNCTION orbis_deny_identity_audit_mutation();
