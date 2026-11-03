-- Normalize existing indexed addresses so direct equality predicates can use
-- participant indexes (new writes are normalized by PostgresStore).
UPDATE transactions SET sender=lower(sender) WHERE sender IS NOT NULL;
UPDATE transactions SET recipient=lower(recipient) WHERE recipient IS NOT NULL;
UPDATE logs SET address=lower(address);
DROP INDEX IF EXISTS relationship_evidence_page_idx;
