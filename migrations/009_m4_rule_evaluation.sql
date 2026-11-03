CREATE TABLE rule_versions (
    rule_version_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    rule_id TEXT NOT NULL,
    semantic_version TEXT NOT NULL,
    definition_digest TEXT NOT NULL CHECK (definition_digest ~ '^sha256:[0-9a-f]{64}$'),
    input_schema JSONB NOT NULL,
    parameter_schema JSONB NOT NULL,
    decoder_requirements JSONB NOT NULL DEFAULT '[]'::jsonb,
    coverage_requirements JSONB NOT NULL DEFAULT '{}'::jsonb,
    lifecycle_state TEXT NOT NULL CHECK (lifecycle_state IN ('staged','active','retired')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    activated_at TIMESTAMPTZ,
    retired_at TIMESTAMPTZ,
    created_by TEXT,
    lifecycle_reason TEXT,
    UNIQUE(rule_id, semantic_version),
    UNIQUE(rule_version_id, rule_id),
    CHECK (semantic_version ~ '^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?$'),
    CHECK ((lifecycle_state='staged' AND activated_at IS NULL AND retired_at IS NULL) OR
           (lifecycle_state='active' AND activated_at IS NOT NULL AND retired_at IS NULL) OR
           (lifecycle_state='retired' AND activated_at IS NOT NULL AND retired_at IS NOT NULL))
);
CREATE INDEX rule_versions_state_idx ON rule_versions(rule_id, lifecycle_state);

CREATE FUNCTION orbis_guard_rule_version() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP='DELETE' THEN RAISE EXCEPTION 'rule versions cannot be deleted'; END IF;
  IF ROW(NEW.rule_id,NEW.semantic_version,NEW.definition_digest,NEW.input_schema,
         NEW.parameter_schema,NEW.decoder_requirements,NEW.coverage_requirements,NEW.created_at,NEW.created_by)
     IS DISTINCT FROM
     ROW(OLD.rule_id,OLD.semantic_version,OLD.definition_digest,OLD.input_schema,
         OLD.parameter_schema,OLD.decoder_requirements,OLD.coverage_requirements,OLD.created_at,OLD.created_by)
  THEN RAISE EXCEPTION 'rule version definition is immutable'; END IF;
  IF NOT ((OLD.lifecycle_state='staged' AND NEW.lifecycle_state IN ('staged','active')) OR
          (OLD.lifecycle_state='active' AND NEW.lifecycle_state IN ('active','retired')) OR
          (OLD.lifecycle_state='retired' AND NEW.lifecycle_state='retired'))
  THEN RAISE EXCEPTION 'invalid rule lifecycle transition'; END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER rule_versions_immutable BEFORE UPDATE OR DELETE ON rule_versions
FOR EACH ROW EXECUTE FUNCTION orbis_guard_rule_version();

CREATE TABLE evaluations (
    evaluation_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    network_id BIGINT NOT NULL REFERENCES networks(network_id) ON DELETE RESTRICT,
    rule_version_id BIGINT NOT NULL,
    rule_id TEXT NOT NULL,
    subject_kind TEXT NOT NULL,
    subject_key TEXT NOT NULL,
    from_block BIGINT NOT NULL CHECK(from_block>=0),
    to_block BIGINT NOT NULL CHECK(to_block>=from_block),
    normalized_parameters JSONB NOT NULL,
    parameter_digest TEXT NOT NULL CHECK(parameter_digest ~ '^sha256:[0-9a-f]{64}$'),
    context_digest TEXT NOT NULL CHECK(context_digest ~ '^sha256:[0-9a-f]{64}$'),
    evaluator_build TEXT NOT NULL,
    evaluation_key TEXT NOT NULL CHECK(evaluation_key ~ '^sha256:[0-9a-f]{64}$'),
    execution_status TEXT NOT NULL CHECK(execution_status IN ('completed','failed')),
    analytical_outcome TEXT CHECK(analytical_outcome IN ('matched','not_matched','insufficient_coverage')),
    canonicality TEXT NOT NULL DEFAULT 'active' CHECK(canonicality IN ('active','invalidated')),
    coverage JSONB NOT NULL,
    evidence_envelope JSONB NOT NULL,
    evidence_digest TEXT NOT NULL CHECK(evidence_digest ~ '^sha256:[0-9a-f]{64}$'),
    digest_algorithm TEXT NOT NULL CHECK(digest_algorithm='sha256'),
    evidence_schema_version INTEGER NOT NULL CHECK(evidence_schema_version>0),
    diagnostics JSONB NOT NULL DEFAULT '{}'::jsonb,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    invalidated_at TIMESTAMPTZ,
    supersedes_evaluation_id BIGINT,
    UNIQUE(network_id,evaluation_key),
    UNIQUE(network_id,evaluation_id),
    UNIQUE(network_id,evaluation_id,rule_version_id),
    FOREIGN KEY(rule_version_id,rule_id) REFERENCES rule_versions(rule_version_id,rule_id) ON DELETE RESTRICT,
    FOREIGN KEY(network_id,supersedes_evaluation_id) REFERENCES evaluations(network_id,evaluation_id) ON DELETE RESTRICT,
    CHECK ((execution_status='failed' AND analytical_outcome IS NULL) OR
           (execution_status='completed' AND analytical_outcome IS NOT NULL AND completed_at IS NOT NULL)),
    CHECK ((canonicality='active' AND invalidated_at IS NULL) OR (canonicality='invalidated' AND invalidated_at IS NOT NULL))
);
CREATE INDEX evaluations_subject_idx ON evaluations(network_id,rule_id,subject_kind,subject_key,to_block DESC);
CREATE INDEX evaluations_canonicality_idx ON evaluations(network_id,canonicality,created_at DESC);

CREATE FUNCTION orbis_guard_evaluation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP='DELETE' THEN RAISE EXCEPTION 'evaluation history cannot be deleted'; END IF;
  IF ROW(NEW.network_id,NEW.rule_version_id,NEW.rule_id,NEW.subject_kind,NEW.subject_key,
         NEW.from_block,NEW.to_block,NEW.normalized_parameters,NEW.parameter_digest,NEW.context_digest,
         NEW.evaluator_build,NEW.evaluation_key,NEW.execution_status,NEW.analytical_outcome,NEW.coverage,
         NEW.evidence_envelope,NEW.evidence_digest,NEW.digest_algorithm,NEW.evidence_schema_version,NEW.completed_at,
         NEW.supersedes_evaluation_id)
     IS DISTINCT FROM
     ROW(OLD.network_id,OLD.rule_version_id,OLD.rule_id,OLD.subject_kind,OLD.subject_key,
         OLD.from_block,OLD.to_block,OLD.normalized_parameters,OLD.parameter_digest,OLD.context_digest,
         OLD.evaluator_build,OLD.evaluation_key,OLD.execution_status,OLD.analytical_outcome,OLD.coverage,
         OLD.evidence_envelope,OLD.evidence_digest,OLD.digest_algorithm,OLD.evidence_schema_version,OLD.completed_at,
         OLD.supersedes_evaluation_id)
  THEN RAISE EXCEPTION 'evaluation result is immutable'; END IF;
  IF OLD.canonicality='invalidated' AND NEW.canonicality<>'invalidated' THEN RAISE EXCEPTION 'invalidated evaluations cannot be reactivated'; END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER evaluations_immutable BEFORE UPDATE OR DELETE ON evaluations
FOR EACH ROW EXECUTE FUNCTION orbis_guard_evaluation();

CREATE TABLE evaluation_attempts (
    network_id BIGINT NOT NULL,
    evaluation_id BIGINT NOT NULL,
    attempt_no INTEGER NOT NULL CHECK(attempt_no>0),
    execution_status TEXT NOT NULL CHECK(execution_status IN ('completed','failed')),
    diagnostics JSONB NOT NULL DEFAULT '{}'::jsonb,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY(network_id,evaluation_id,attempt_no),
    FOREIGN KEY(network_id,evaluation_id) REFERENCES evaluations(network_id,evaluation_id) ON DELETE RESTRICT
);

CREATE TABLE findings (
    finding_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    network_id BIGINT NOT NULL,
    evaluation_id BIGINT NOT NULL,
    rule_version_id BIGINT NOT NULL,
    finding_key TEXT NOT NULL,
    result JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(network_id,evaluation_id,finding_key),
    UNIQUE(network_id,finding_id),
    FOREIGN KEY(network_id,evaluation_id,rule_version_id) REFERENCES evaluations(network_id,evaluation_id,rule_version_id) ON DELETE RESTRICT
);
CREATE INDEX findings_evaluation_idx ON findings(network_id,evaluation_id,finding_id);
CREATE FUNCTION orbis_guard_finding() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'findings are immutable'; END $$;
CREATE TRIGGER findings_immutable BEFORE UPDATE OR DELETE ON findings FOR EACH ROW EXECUTE FUNCTION orbis_guard_finding();

CREATE TABLE evaluation_evidence (
    network_id BIGINT NOT NULL,
    evaluation_id BIGINT NOT NULL,
    evidence_ordinal INTEGER NOT NULL CHECK(evidence_ordinal>=0),
    evidence_digest TEXT NOT NULL CHECK(evidence_digest ~ '^sha256:[0-9a-f]{64}$'),
    block_number BIGINT NOT NULL CHECK(block_number>=0),
    block_hash TEXT NOT NULL,
    transaction_hash TEXT,
    log_index BIGINT CHECK(log_index>=0),
    source_kind TEXT NOT NULL,
    normalized_input JSONB NOT NULL,
    digest_algorithm TEXT NOT NULL CHECK(digest_algorithm='sha256'),
    evidence_schema_version INTEGER NOT NULL CHECK(evidence_schema_version>0),
    PRIMARY KEY(network_id,evaluation_id,evidence_ordinal),
    UNIQUE(network_id,evaluation_id,evidence_digest),
    FOREIGN KEY(network_id,evaluation_id) REFERENCES evaluations(network_id,evaluation_id) ON DELETE RESTRICT,
    CHECK(log_index IS NULL OR transaction_hash IS NOT NULL)
);
CREATE INDEX evaluation_evidence_block_hash_idx ON evaluation_evidence(network_id,block_hash);

CREATE TABLE finding_evidence (
    network_id BIGINT NOT NULL,
    finding_id BIGINT NOT NULL,
    evidence_ordinal INTEGER NOT NULL CHECK(evidence_ordinal>=0),
    evidence_digest TEXT NOT NULL CHECK(evidence_digest ~ '^sha256:[0-9a-f]{64}$'),
    source_kind TEXT NOT NULL,
    block_number BIGINT NOT NULL CHECK(block_number>=0),
    block_hash TEXT NOT NULL,
    transaction_hash TEXT,
    log_index BIGINT CHECK(log_index>=0),
    normalized_input JSONB NOT NULL,
    digest_algorithm TEXT NOT NULL CHECK(digest_algorithm='sha256'),
    evidence_schema_version INTEGER NOT NULL CHECK(evidence_schema_version>0),
    PRIMARY KEY(network_id,finding_id,evidence_ordinal),
    UNIQUE(network_id,finding_id,evidence_digest),
    FOREIGN KEY(network_id,finding_id) REFERENCES findings(network_id,finding_id) ON DELETE RESTRICT,
    CHECK(log_index IS NULL OR transaction_hash IS NOT NULL)
);
CREATE INDEX finding_evidence_block_hash_idx ON finding_evidence(network_id,block_hash);

CREATE TABLE evaluation_invalidations (
    invalidation_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    network_id BIGINT NOT NULL,
    evaluation_id BIGINT NOT NULL,
    affected_finding_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    rollback_from_block BIGINT NOT NULL CHECK(rollback_from_block>=0),
    orphaned_block_hashes JSONB NOT NULL,
    reason TEXT NOT NULL,
    invalidated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    rollback_id UUID NOT NULL,
    prior_canonicality TEXT NOT NULL CHECK(prior_canonicality='active'),
    UNIQUE(network_id,evaluation_id),
    FOREIGN KEY(network_id,evaluation_id) REFERENCES evaluations(network_id,evaluation_id) ON DELETE RESTRICT
);
CREATE INDEX evaluation_invalidations_time_idx ON evaluation_invalidations(network_id,invalidated_at DESC);
CREATE FUNCTION orbis_guard_invalidation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'invalidation audit is append-only'; END $$;
CREATE TRIGGER evaluation_invalidations_append_only BEFORE UPDATE OR DELETE ON evaluation_invalidations FOR EACH ROW EXECUTE FUNCTION orbis_guard_invalidation();
