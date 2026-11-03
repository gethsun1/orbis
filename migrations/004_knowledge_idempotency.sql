WITH ranked AS (
  SELECT evidence_id,row_number() OVER (PARTITION BY network_id,observation_id,block_number,block_hash,
    transaction_hash,COALESCE(log_index,-1) ORDER BY evidence_id) AS ordinal
  FROM evidence_refs WHERE transaction_hash IS NOT NULL
)
DELETE FROM evidence_refs e USING ranked r WHERE e.evidence_id=r.evidence_id AND r.ordinal>1;
CREATE UNIQUE INDEX evidence_transaction_identity_uq ON evidence_refs
  (network_id,observation_id,block_number,block_hash,transaction_hash,COALESCE(log_index,-1));
UPDATE relationships r SET observation_count=GREATEST(1,(SELECT count(DISTINCT e.transaction_hash)
  FROM relationship_evidence re JOIN evidence_refs e USING(network_id,evidence_id)
  WHERE re.network_id=r.network_id AND re.relationship_id=r.relationship_id));
