CREATE FUNCTION orbis_validate_supersession() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE predecessor evaluations%ROWTYPE;
BEGIN
  IF NEW.supersedes_evaluation_id IS NULL THEN RETURN NEW; END IF;
  SELECT * INTO predecessor FROM evaluations WHERE network_id=NEW.network_id AND evaluation_id=NEW.supersedes_evaluation_id;
  IF predecessor.evaluation_id IS NULL OR predecessor.canonicality<>'invalidated' OR
     predecessor.rule_id<>NEW.rule_id OR predecessor.subject_kind<>NEW.subject_kind OR predecessor.subject_key<>NEW.subject_key
  THEN RAISE EXCEPTION 'replacement must supersede a compatible invalidated evaluation'; END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER evaluations_supersession_guard BEFORE INSERT ON evaluations
FOR EACH ROW EXECUTE FUNCTION orbis_validate_supersession();

CREATE FUNCTION orbis_check_invalidation_audit() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.canonicality='invalidated' AND OLD.canonicality='active' AND NOT EXISTS(
    SELECT 1 FROM evaluation_invalidations i WHERE i.network_id=NEW.network_id AND i.evaluation_id=NEW.evaluation_id)
  THEN RAISE EXCEPTION 'invalidated evaluation requires audit record'; END IF;
  RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER evaluations_require_invalidation_audit AFTER UPDATE OF canonicality ON evaluations
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION orbis_check_invalidation_audit();

CREATE FUNCTION orbis_guard_attempt() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'evaluation attempts are append-only'; END $$;
CREATE TRIGGER evaluation_attempts_append_only BEFORE UPDATE OR DELETE ON evaluation_attempts
FOR EACH ROW EXECUTE FUNCTION orbis_guard_attempt();

CREATE FUNCTION orbis_validate_finding() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS(SELECT 1 FROM evaluations e WHERE e.network_id=NEW.network_id AND e.evaluation_id=NEW.evaluation_id
                AND e.rule_version_id=NEW.rule_version_id AND e.execution_status='completed' AND e.analytical_outcome='matched')
  THEN RAISE EXCEPTION 'finding requires a completed matched evaluation'; END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER findings_require_match BEFORE INSERT ON findings
FOR EACH ROW EXECUTE FUNCTION orbis_validate_finding();

CREATE FUNCTION orbis_guard_evidence() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'retained evidence is immutable'; END $$;
CREATE TRIGGER evaluation_evidence_immutable BEFORE UPDATE OR DELETE ON evaluation_evidence
FOR EACH ROW EXECUTE FUNCTION orbis_guard_evidence();
CREATE TRIGGER finding_evidence_immutable BEFORE UPDATE OR DELETE ON finding_evidence
FOR EACH ROW EXECUTE FUNCTION orbis_guard_evidence();
