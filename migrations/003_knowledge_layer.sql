ALTER TABLE entities ADD COLUMN original_address TEXT NOT NULL DEFAULT '';
ALTER TABLE entities ADD COLUMN created_at TIMESTAMPTZ NOT NULL DEFAULT now();
ALTER TABLE entities ADD COLUMN updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
ALTER TABLE entities DROP CONSTRAINT entities_entity_type_check;
ALTER TABLE entities ADD CONSTRAINT entities_entity_type_check CHECK (entity_type IN ('wallet','contract','token','unknown'));

ALTER TABLE observations ADD COLUMN related_entity_id BIGINT;
ALTER TABLE observations ADD COLUMN source_block_number BIGINT;
ALTER TABLE observations ADD COLUMN source_block_hash TEXT;
ALTER TABLE observations ADD COLUMN source_transaction_hash TEXT;
ALTER TABLE observations ADD COLUMN source_log_index BIGINT;
ALTER TABLE observations ADD COLUMN source_timestamp BIGINT;
ALTER TABLE observations ADD COLUMN derived BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE observations ADD CONSTRAINT observations_related_entity_fk
  FOREIGN KEY(network_id,related_entity_id) REFERENCES entities(network_id,entity_id) ON DELETE CASCADE;
ALTER TABLE observations ADD CONSTRAINT observations_source_block_fk
  FOREIGN KEY(network_id,source_block_number,source_block_hash)
  REFERENCES blocks(network_id,number,hash) ON DELETE CASCADE;
ALTER TABLE observations ADD CONSTRAINT observations_source_tx_fk
  FOREIGN KEY(network_id,source_transaction_hash,source_block_number,source_block_hash)
  REFERENCES transactions(network_id,hash,block_number,block_hash) ON DELETE CASCADE;
ALTER TABLE observations ADD CONSTRAINT observations_source_log_fk
  FOREIGN KEY(network_id,source_transaction_hash,source_log_index)
  REFERENCES logs(network_id,transaction_hash,log_index) ON DELETE CASCADE;
CREATE INDEX observations_entity_block_idx ON observations(network_id,entity_id,source_block_number DESC,observation_id DESC);
CREATE INDEX observations_source_tx_idx ON observations(network_id,source_transaction_hash);
CREATE UNIQUE INDEX observations_derived_fact_uq ON observations
  (network_id,entity_id,observation_type,source_transaction_hash,COALESCE(related_entity_id,0))
  WHERE derived;

CREATE TABLE relationships (
  relationship_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  network_id BIGINT NOT NULL,
  source_entity_id BIGINT NOT NULL,
  relationship_type TEXT NOT NULL,
  target_entity_id BIGINT NOT NULL,
  derivation TEXT NOT NULL CHECK (derivation IN ('observed','aggregated','inferred')),
  first_observed_block BIGINT NOT NULL CHECK(first_observed_block >= 0),
  last_observed_block BIGINT NOT NULL CHECK(last_observed_block >= first_observed_block),
  observation_count BIGINT NOT NULL DEFAULT 1 CHECK(observation_count > 0),
  attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  FOREIGN KEY(network_id,source_entity_id) REFERENCES entities(network_id,entity_id) ON DELETE CASCADE,
  FOREIGN KEY(network_id,target_entity_id) REFERENCES entities(network_id,entity_id) ON DELETE CASCADE,
  UNIQUE(network_id,source_entity_id,relationship_type,target_entity_id,derivation),
  UNIQUE(network_id,relationship_id)
);
CREATE INDEX relationships_source_idx ON relationships(network_id,source_entity_id,relationship_type,last_observed_block DESC);
CREATE INDEX relationships_target_idx ON relationships(network_id,target_entity_id,relationship_type,last_observed_block DESC);

CREATE TABLE relationship_evidence (
  network_id BIGINT NOT NULL,
  relationship_id BIGINT NOT NULL,
  evidence_id BIGINT NOT NULL,
  PRIMARY KEY(network_id,relationship_id,evidence_id),
  FOREIGN KEY(network_id,relationship_id) REFERENCES relationships(network_id,relationship_id) ON DELETE CASCADE,
  FOREIGN KEY(evidence_id) REFERENCES evidence_refs(evidence_id) ON DELETE CASCADE
);
CREATE INDEX relationship_evidence_evidence_idx ON relationship_evidence(evidence_id);

ALTER TABLE evidence_refs ADD CONSTRAINT evidence_identity_source_unique
  UNIQUE(network_id,observation_id,block_number,block_hash,transaction_hash,log_index);
ALTER TABLE evidence_refs ADD CONSTRAINT evidence_network_id_unique UNIQUE(network_id,evidence_id);
ALTER TABLE relationship_evidence DROP CONSTRAINT relationship_evidence_evidence_id_fkey;
ALTER TABLE relationship_evidence ADD CONSTRAINT relationship_evidence_network_evidence_fk
  FOREIGN KEY(network_id,evidence_id) REFERENCES evidence_refs(network_id,evidence_id) ON DELETE CASCADE;
