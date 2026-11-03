WITH ranked AS (
  SELECT re.network_id,re.relationship_id,re.evidence_id,
    row_number() OVER (PARTITION BY re.network_id,re.relationship_id,e.transaction_hash
      ORDER BY re.evidence_id) AS ordinal
  FROM relationship_evidence re JOIN evidence_refs e USING(network_id,evidence_id)
)
DELETE FROM relationship_evidence re USING ranked r
WHERE re.network_id=r.network_id AND re.relationship_id=r.relationship_id
  AND re.evidence_id=r.evidence_id AND r.ordinal>1;
