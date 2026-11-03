-- Evaluation records are immutable terminal results. A failure remains historical
-- under its deterministic identity; callers cannot promote or rewrite it in place.
CREATE OR REPLACE FUNCTION orbis_guard_evaluation() RETURNS trigger LANGUAGE plpgsql AS $$
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
  IF OLD.canonicality='invalidated' AND NEW.canonicality<>'invalidated' THEN
    RAISE EXCEPTION 'invalidated evaluations cannot be reactivated';
  END IF;
  RETURN NEW;
END $$;
