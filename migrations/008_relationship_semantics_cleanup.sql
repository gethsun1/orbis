-- Remove legacy emitter-as-recipient edges and give retained per-log facts the
-- explicit emitter meaning. Their evidence stays attached to its original log.
DELETE FROM relationships r USING relationship_evidence re, evidence_refs e, observations o
WHERE r.network_id=re.network_id AND r.relationship_id=re.relationship_id
  AND e.network_id=re.network_id AND e.evidence_id=re.evidence_id
  AND o.network_id=e.network_id AND o.observation_id=e.observation_id
  AND r.relationship_type='interacted_with_contract' AND r.derivation='aggregated'
  AND o.observation_type='contract_emitted_log' AND o.derived;

UPDATE observations SET observation_type='emitted_event_during', related_entity_id=NULL
WHERE observation_type='contract_emitted_log' AND derived;
