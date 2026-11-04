# ORBIS M3.1 — Knowledge Layer Acceptance Report

**Date:** 4 November 2026 (Africa/Nairobi)
**Status:** M3.1 engineering remediation and final live validation passed. See [M3 live validation report](M3_LIVE_VALIDATION_REPORT.md) for the bounded Whitechain Sepolia evidence. **M4 has not started.**

## Scope and outcome

This remediation follows the owner-authorized M3 Knowledge Layer brief and the independent M3 audit. It preserves the approved PRD's milestone requirements and records the sequencing change in D-020/D-023: the knowledge layer is implementation M3 and deterministic intelligence is implementation M4. The definitive M4 contracts are in [M4 specification](M4_SPECIFICATION.md). No M4 implementation, AI/LLM, MeTTa, REST, SDK, MCP, dashboard, deployment, or full historical synchronization work was started.

The verified M3.1 defects were addressed across R1–R6. PostgreSQL migrations and the complete test suite passed. A separate final live validation then used the explicitly configured Whitechain Sepolia endpoint and an isolated PostgreSQL schema; see the live report for current RPC health, range hashes, counts, restart, enrichment, and transaction evidence.

## R1 — Reorg relationship aggregates

`PostgresStore.rollback_from` now removes affected derived evidence and observations, then recomputes `first_observed_block`, `last_observed_block`, and distinct supporting transaction count from surviving canonical evidence inside the same transaction. A relationship is deleted when no canonical supporting evidence remains. Evidence links and aggregate changes roll back together if source-block deletion fails. Repeated rollback is safe; replacement evidence is enriched from the durable unprocessed queue.

PostgreSQL tests cover replacement blocks omitting the earliest, middle, or latest supporting transaction; latest-only and middle-plus-later suffix removal; full invalidation and replacement replay; repeated invalidation; and injected failure during rollback. The tests verify relationship deletion and repaired summary values. EVM reorg rollback is suffix-based; a standalone non-contiguous block invalidation is not an operation supported by the observer.

## R2 — Enrichment progression

`knowledge_enrichment_progress` is a database-backed completion ledger keyed to network and transaction. Canonical work is ordered by network, block, transaction index, then transaction hash; PostgreSQL row locks with `SKIP LOCKED` allow concurrent workers to claim disjoint work. A page and its completion rows commit atomically. Transactions with no derived facts are marked complete. Rollback removes progress through the transaction foreign key, so replacement canonical transactions are eligible again.

The integration suite covers datasets below, at, and above the batch size; consecutive batches; repeat invocation; a mid-batch failure; service reconstruction after successful work; empty-fact transactions; and concurrent duplicate invocation. Under-size and exact-size cases processed **2/2** and **3/3** records. In the seven-record scenario, successive calls processed **3, 3, 1, 0** transactions. Final status was **eligible 7, processed 7, remaining 0**, over **3 non-empty batches**. The concurrent ten-record scenario completed as **5 + 5**, with no remaining records.

## R3 — Relationship semantics

- `transacted_with` uses the actual transaction sender and recipient.
- `emitted_event_during` records each log emitter and its individual log evidence; it does not label the emitter as the transaction recipient.
- `interacted_with_contract` requires `tx.to` to identify an independently established contract/token entity.
- `transferred_to` is derived only from the standard ERC-20 `Transfer(address,address,uint256)` signature, exactly two 32-byte indexed fields with ABI address padding, and one 32-byte amount word. Zero-address mint/burn endpoints are not fabricated as wallet entities or relationship endpoints.

PostgreSQL tests exercise a recipient differing from the emitter, recipient-contract logs, other-contract emitters, multiple emitters and repeated logs, valid transfer decoding, and invalid event signatures.

## R4 — Evidence identity and receipt provenance

Migration 006 changes derived observation identity to include the optional source log index. Transaction-level observations retain a null log index and their transaction-level identity. Evidence already identifies network, block, transaction and optional log; a composite foreign key now also requires that transaction and block to match the stored receipt. Existing receipt storage is reused; receipt payloads are not duplicated.

PostgreSQL verifies receipt-to-transaction/block consistency, evidence rejection for a missing receipt, rejection of a missing log/invalid log index, individual evidence for multiple logs from one transaction, and valid transaction-level evidence without a log. Receipt association is enforced by the composite transaction/block receipt foreign key rather than a duplicated receipt identifier. This is the documented provenance-model choice.

## R5 — Bounded retrieval and indexes

Relationship, pairwise relationship, and relationship-evidence retrieval now accept bounded `limit`/`offset` pagination, deterministic tie-breaking, and a maximum page size of 500. Transaction history uses normalized address equality rather than `lower(sender)`/`lower(recipient)`. Migration 007 normalizes existing indexed participant/log addresses. Participant-history and deterministic enrichment indexes match those predicates and ordering.

The PostgreSQL integration test uses `EXPLAIN (ANALYZE, BUFFERS)` for participant history and confirms `transaction_history_sender_idx` is selected. This is an index-plan check on the local test schema, not a production-scale performance benchmark.

## R6 — Network isolation

PostgreSQL integration tests create the same normalized address on two indexed networks and verify distinct entity/network identities and network-attached observations. Composite foreign keys reject cross-network observation sources and relationship endpoints. No entity, relationship, or evidence can be reassigned across network identities.

## Migrations and verification

Additive migrations 006–008 add the enrichment ledger, receipt provenance constraint, per-log observation uniqueness, retrieval/enrichment indexes, historical address normalization, and cleanup of legacy emitter-as-recipient edges while retaining log evidence. They do not reset databases or recreate M1–M3 tables. The configured development and test PostgreSQL databases both applied migrations successfully. Integration tests additionally apply all migrations in fresh isolated schemas and rerun migration startup for idempotence. SQLite observer support remains intact.

Full suite, with PostgreSQL integration tests enabled:

```text
set -a; source .env; set +a
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
Ran 31 tests — OK (0 failures, 0 skips)
```

This is 11 unit/regression tests and 20 PostgreSQL integration tests. PostgreSQL coverage includes observer persistence, constraints, block transactions, reorg/replay, knowledge pagination, batch progression, provenance, relationship semantics, and network isolation. M1 observer and RPC regressions passed. M2 persistence/replay and referential-integrity regressions passed.

`python -m orbis.db_migrate` completed against both configured development and test database URLs. PostgreSQL checks ran using isolated schemas; no database reset was performed. `git diff --check` and Python compilation are recorded in the completion summary.

## RPC configuration and limitations

The ignored local `.env` contains the explicitly configured `https://rpc.testnet.whitechain.io/` endpoint and chain ID 1874. The endpoint passed the 4 November live validation; no endpoint substitution occurred. The earlier M1 report's HTTP 403 result is retained as historical evidence because endpoint availability may vary.

The enrichment service remains an internal service with no CLI/API entry point. ERC-20 is the only decoded event. Relationship aggregation counts distinct supporting transactions, not log count. The local query plan does not establish throughput or production readiness. Deterministic intelligence rules are sequenced to implementation M4; they are not implemented here.

## Acceptance verdict

**PASS.** All audited database and retrieval defects have PostgreSQL integration coverage, all 31 tests pass with no skipped integrations, dev/test migrations apply, and the final bounded live validation is recorded separately. M4 remains unstarted.
