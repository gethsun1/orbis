CREATE TABLE networks (
    network_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    chain_id BIGINT NOT NULL UNIQUE,
    name TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE blocks (
    network_id BIGINT NOT NULL REFERENCES networks(network_id),
    number BIGINT NOT NULL CHECK (number >= 0),
    hash TEXT NOT NULL,
    parent_hash TEXT NOT NULL,
    timestamp BIGINT NOT NULL CHECK (timestamp >= 0),
    canonical BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (network_id, hash),
    UNIQUE (network_id, number),
    UNIQUE (network_id, number, hash)
);
CREATE INDEX blocks_parent_idx ON blocks(network_id, parent_hash);

CREATE TABLE transactions (
    network_id BIGINT NOT NULL,
    hash TEXT NOT NULL,
    block_number BIGINT NOT NULL,
    block_hash TEXT NOT NULL,
    tx_index BIGINT NOT NULL,
    sender TEXT,
    recipient TEXT,
    value TEXT NOT NULL,
    input_data TEXT NOT NULL,
    PRIMARY KEY (network_id, hash),
    UNIQUE (network_id, block_hash, tx_index),
    UNIQUE (network_id, hash, block_hash),
    UNIQUE (network_id, hash, block_number, block_hash),
    FOREIGN KEY (network_id, block_number, block_hash)
      REFERENCES blocks(network_id, number, hash) ON DELETE CASCADE
);
CREATE INDEX transactions_block_idx ON transactions(network_id, block_number);
CREATE INDEX transactions_sender_idx ON transactions(network_id, sender, block_number);
CREATE INDEX transactions_recipient_idx ON transactions(network_id, recipient, block_number);

CREATE TABLE receipts (
    network_id BIGINT NOT NULL,
    transaction_hash TEXT NOT NULL,
    block_hash TEXT NOT NULL,
    status BIGINT,
    gas_used TEXT,
    raw JSONB NOT NULL,
    PRIMARY KEY (network_id, transaction_hash),
    FOREIGN KEY (network_id, transaction_hash, block_hash)
      REFERENCES transactions(network_id, hash, block_hash) ON DELETE CASCADE
);

CREATE TABLE logs (
    network_id BIGINT NOT NULL,
    transaction_hash TEXT NOT NULL,
    log_index BIGINT NOT NULL,
    block_number BIGINT NOT NULL,
    block_hash TEXT NOT NULL,
    address TEXT NOT NULL,
    topics JSONB NOT NULL,
    data TEXT NOT NULL,
    removed BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (network_id, transaction_hash, log_index),
    FOREIGN KEY (network_id, transaction_hash, block_number, block_hash)
      REFERENCES transactions(network_id, hash, block_number, block_hash) ON DELETE CASCADE
);
CREATE INDEX logs_address_idx ON logs(network_id, address, block_number);
CREATE INDEX logs_block_idx ON logs(network_id, block_number);

CREATE TABLE checkpoints (
    network_id BIGINT PRIMARY KEY REFERENCES networks(network_id),
    block_number BIGINT NOT NULL,
    block_hash TEXT NOT NULL,
    FOREIGN KEY (network_id, block_number, block_hash)
      REFERENCES blocks(network_id, number, hash) DEFERRABLE INITIALLY DEFERRED
);
