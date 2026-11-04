-- Preserve every historical network_id while making identity explicitly unresolved.
ALTER TABLE networks ADD COLUMN fingerprint_scheme TEXT;
ALTER TABLE networks ADD COLUMN network_fingerprint TEXT;
ALTER TABLE networks ADD COLUMN genesis_hash TEXT;
ALTER TABLE networks ADD CONSTRAINT networks_identity_all_or_none CHECK (
  (fingerprint_scheme IS NULL AND network_fingerprint IS NULL AND genesis_hash IS NULL)
  OR (fingerprint_scheme IS NOT NULL AND network_fingerprint IS NOT NULL AND genesis_hash IS NOT NULL)
);
ALTER TABLE networks ADD CONSTRAINT networks_identity_format CHECK (
  (fingerprint_scheme IS NULL AND network_fingerprint IS NULL AND genesis_hash IS NULL)
  OR (fingerprint_scheme = 'evm-genesis-sha256-v1'
      AND network_fingerprint ~ '^sha256:[0-9a-f]{64}$'
      AND genesis_hash ~ '^0x[0-9a-f]{64}$')
);
ALTER TABLE networks DROP CONSTRAINT networks_chain_id_key;
CREATE UNIQUE INDEX networks_fingerprint_unique
  ON networks(chain_id, fingerprint_scheme, network_fingerprint)
  WHERE network_fingerprint IS NOT NULL;

CREATE OR REPLACE FUNCTION orbis_guard_network_identity() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
BEGIN
  IF TG_OP = 'INSERT' THEN
    IF NEW.network_fingerprint IS NULL THEN
      RAISE EXCEPTION 'network registration requires verified identity';
    END IF;
    RETURN NEW;
  END IF;
  IF OLD.network_fingerprint IS NOT NULL AND
     (NEW.chain_id, NEW.fingerprint_scheme, NEW.network_fingerprint, NEW.genesis_hash)
       IS DISTINCT FROM
     (OLD.chain_id, OLD.fingerprint_scheme, OLD.network_fingerprint, OLD.genesis_hash)
  THEN RAISE EXCEPTION 'established network identity is immutable'; END IF;
  IF OLD.network_fingerprint IS NULL AND NEW.network_fingerprint IS NOT NULL
  THEN RAISE EXCEPTION 'network identity assignment requires controlled registry operation'; END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER networks_identity_immutable BEFORE UPDATE ON networks
  FOR EACH ROW EXECUTE FUNCTION orbis_guard_network_identity();
CREATE TRIGGER networks_identity_required BEFORE INSERT ON networks
  FOR EACH ROW EXECUTE FUNCTION orbis_guard_network_identity();

-- Production registry/admin principals and controlled identity assignment need
-- deployment-owned role decisions; this migration does not invent credentials.
