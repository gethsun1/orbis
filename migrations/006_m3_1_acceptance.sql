-- M3.1: durable enrichment completion, per-log fact identity, and receipt provenance.
-- All changes are additive to existing M1-M3 data and roll back by dropping the
-- newly added table/constraints/indexes (no existing data is rewritten or removed).
CREATE TABLE knowledge_enrichment_progress (
  network_id BIGINT NOT NULL,
  transaction_hash TEXT NOT NULL,
  completed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY(network_id, transaction_hash),
  FOREIGN KEY(network_id, transaction_hash)
    REFERENCES transactions(network_id, hash) ON DELETE CASCADE
);

CREATE UNIQUE INDEX receipts_network_tx_block_uq
  ON receipts(network_id, transaction_hash, block_hash);
ALTER TABLE evidence_refs ADD CONSTRAINT evidence_receipt_source_fk
  FOREIGN KEY(network_id, transaction_hash, block_hash)
  REFERENCES receipts(network_id, transaction_hash, block_hash) ON DELETE RESTRICT;

DROP INDEX observations_derived_fact_uq;
CREATE UNIQUE INDEX observations_derived_fact_uq ON observations
  (network_id,entity_id,observation_type,source_transaction_hash,
   COALESCE(source_log_index,-1),COALESCE(related_entity_id,0))
  WHERE derived;

CREATE INDEX transactions_enrichment_order_idx
  ON transactions(network_id,block_number,tx_index,hash);
CREATE INDEX transaction_history_sender_idx
  ON transactions(network_id,sender,block_number DESC,tx_index DESC);
CREATE INDEX transaction_history_recipient_idx
  ON transactions(network_id,recipient,block_number DESC,tx_index DESC);
