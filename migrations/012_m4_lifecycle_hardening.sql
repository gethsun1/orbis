CREATE OR REPLACE FUNCTION orbis_guard_rule_version() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP='DELETE' THEN RAISE EXCEPTION 'rule versions cannot be deleted'; END IF;
  IF ROW(NEW.rule_id,NEW.semantic_version,NEW.definition_digest,NEW.input_schema,
         NEW.parameter_schema,NEW.decoder_requirements,NEW.coverage_requirements,NEW.created_at,NEW.created_by)
     IS DISTINCT FROM
     ROW(OLD.rule_id,OLD.semantic_version,OLD.definition_digest,OLD.input_schema,
         OLD.parameter_schema,OLD.decoder_requirements,OLD.coverage_requirements,OLD.created_at,OLD.created_by)
  THEN RAISE EXCEPTION 'rule version definition is immutable'; END IF;
  IF OLD.lifecycle_state='staged' AND NEW.lifecycle_state='active' THEN
    IF NEW.activated_at IS NULL OR NEW.retired_at IS NOT NULL THEN RAISE EXCEPTION 'invalid activation metadata'; END IF;
  ELSIF OLD.lifecycle_state='active' AND NEW.lifecycle_state='retired' THEN
    IF NEW.activated_at IS DISTINCT FROM OLD.activated_at OR NEW.retired_at IS NULL THEN RAISE EXCEPTION 'invalid retirement metadata'; END IF;
  ELSIF OLD.lifecycle_state=NEW.lifecycle_state AND
        ROW(NEW.activated_at,NEW.retired_at,NEW.lifecycle_reason) IS DISTINCT FROM
        ROW(OLD.activated_at,OLD.retired_at,OLD.lifecycle_reason) THEN
    RAISE EXCEPTION 'lifecycle metadata is immutable outside a transition';
  ELSIF OLD.lifecycle_state<>NEW.lifecycle_state THEN
    RAISE EXCEPTION 'invalid rule lifecycle transition';
  END IF;
  RETURN NEW;
END $$;

CREATE OR REPLACE FUNCTION orbis_guard_evaluation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP='DELETE' THEN RAISE EXCEPTION 'evaluation history cannot be deleted'; END IF;
  IF ROW(NEW.network_id,NEW.rule_version_id,NEW.rule_id,NEW.subject_kind,NEW.subject_key,
         NEW.from_block,NEW.to_block,NEW.normalized_parameters,NEW.parameter_digest,NEW.context_digest,
         NEW.evaluator_build,NEW.evaluation_key,NEW.execution_status,NEW.analytical_outcome,NEW.coverage,
         NEW.evidence_envelope,NEW.evidence_digest,NEW.digest_algorithm,NEW.evidence_schema_version,
         NEW.diagnostics,NEW.started_at,NEW.completed_at,NEW.created_at,NEW.supersedes_evaluation_id)
     IS DISTINCT FROM
     ROW(OLD.network_id,OLD.rule_version_id,OLD.rule_id,OLD.subject_kind,OLD.subject_key,
         OLD.from_block,OLD.to_block,OLD.normalized_parameters,OLD.parameter_digest,OLD.context_digest,
         OLD.evaluator_build,OLD.evaluation_key,OLD.execution_status,OLD.analytical_outcome,OLD.coverage,
         OLD.evidence_envelope,OLD.evidence_digest,OLD.digest_algorithm,OLD.evidence_schema_version,
         OLD.diagnostics,OLD.started_at,OLD.completed_at,OLD.created_at,OLD.supersedes_evaluation_id)
  THEN RAISE EXCEPTION 'evaluation result is immutable'; END IF;
  IF OLD.canonicality='active' AND NEW.canonicality='active' AND NEW.invalidated_at IS NOT NULL THEN
    RAISE EXCEPTION 'active evaluation cannot have an invalidation timestamp';
  END IF;
  IF OLD.canonicality='invalidated' AND (NEW.canonicality<>'invalidated' OR NEW.invalidated_at IS DISTINCT FROM OLD.invalidated_at) THEN
    RAISE EXCEPTION 'invalidated evaluations are immutable';
  END IF;
  IF NOT (OLD.canonicality='active' AND NEW.canonicality IN ('active','invalidated')) THEN
    RAISE EXCEPTION 'invalid canonicality transition';
  END IF;
  RETURN NEW;
END $$;
