ALTER TABLE networks
    ADD COLUMN environment TEXT NOT NULL DEFAULT 'unknown',
    ADD COLUMN provider_name TEXT NOT NULL DEFAULT '';

CREATE TABLE entities (
    entity_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    network_id BIGINT NOT NULL REFERENCES networks(network_id) ON DELETE CASCADE,
    address TEXT NOT NULL,
    entity_type TEXT NOT NULL CHECK (entity_type IN ('wallet', 'contract', 'unknown')),
    labels JSONB NOT NULL DEFAULT '[]'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata_source TEXT,
    confidence NUMERIC(5,4) CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
    UNIQUE (network_id, address),
    UNIQUE (network_id, entity_id)
);
CREATE INDEX entities_address_idx ON entities(network_id, address);

CREATE TABLE observations (
    observation_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    network_id BIGINT NOT NULL,
    entity_id BIGINT NOT NULL,
    observation_type TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'unknown'
      CHECK (severity IN ('unknown', 'low', 'medium', 'high', 'critical')),
    status TEXT NOT NULL DEFAULT 'open'
      CHECK (status IN ('open', 'resolved', 'retracted')),
    rule_id TEXT,
    rule_version TEXT,
    observed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    window_from_block BIGINT,
    window_to_block BIGINT,
    coverage JSONB NOT NULL DEFAULT '{}'::jsonb,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    CHECK (window_from_block IS NULL OR window_from_block >= 0),
    CHECK (window_to_block IS NULL OR window_to_block >= 0),
    CHECK (window_from_block IS NULL OR window_to_block IS NULL OR window_from_block <= window_to_block),
    FOREIGN KEY (network_id, entity_id)
      REFERENCES entities(network_id, entity_id) ON DELETE CASCADE,
    UNIQUE (network_id, observation_id)
);
CREATE INDEX observations_entity_time_idx ON observations(network_id, entity_id, observed_at DESC);
CREATE INDEX observations_type_time_idx ON observations(network_id, observation_type, observed_at DESC);

CREATE TABLE evidence_refs (
    evidence_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    network_id BIGINT NOT NULL,
    observation_id BIGINT NOT NULL,
    block_number BIGINT NOT NULL,
    block_hash TEXT NOT NULL,
    transaction_hash TEXT,
    log_index BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (block_number >= 0),
    CHECK (log_index IS NULL OR log_index >= 0),
    CHECK (log_index IS NULL OR transaction_hash IS NOT NULL),
    FOREIGN KEY (network_id, observation_id)
      REFERENCES observations(network_id, observation_id) ON DELETE CASCADE,
    FOREIGN KEY (network_id, block_number, block_hash)
      REFERENCES blocks(network_id, number, hash) ON DELETE RESTRICT,
    FOREIGN KEY (network_id, transaction_hash, block_number, block_hash)
      REFERENCES transactions(network_id, hash, block_number, block_hash) ON DELETE RESTRICT,
    FOREIGN KEY (network_id, transaction_hash, log_index)
      REFERENCES logs(network_id, transaction_hash, log_index) ON DELETE RESTRICT
);
CREATE INDEX evidence_observation_idx ON evidence_refs(network_id, observation_id);
CREATE INDEX evidence_source_block_idx ON evidence_refs(network_id, block_number, block_hash);
