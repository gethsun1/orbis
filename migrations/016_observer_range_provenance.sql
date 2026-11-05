-- Persist source-manifest counts so bounded coverage can distinguish a truly
-- empty block from transaction rows that are missing or were never indexed.
ALTER TABLE blocks ADD COLUMN expected_transaction_count BIGINT
  CHECK (expected_transaction_count IS NULL OR expected_transaction_count >= 0);
