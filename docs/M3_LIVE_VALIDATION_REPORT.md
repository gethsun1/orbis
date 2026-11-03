# ORBIS M3 — Live Whitechain Sepolia Validation Report

**Date:** 4 November 2026 (Africa/Nairobi)
**Verdict:** **PASS** — live and engineering acceptance requirements demonstrated.
**Scope:** M3 final validation only. M4 was not started.

## RPC configuration and health

`Settings.from_env()` loaded the ignored `.env` values without altering them. The configured RPC URL parsed as HTTPS host `rpc.testnet.whitechain.io`, path `/`, with no embedded credentials, whitespace, or backslashes. `ORBIS_CHAIN_ID` parsed as decimal **1874**, matching **0x752**. `.env` remains Git-ignored; the existing database URL was preserved.

The configured endpoint returned:

- `eth_chainId`: **1874 (0x752)**.
- `eth_blockNumber`: **12,148,688** during the probe; the subsequent latest-block response was **12,148,689** as the chain advanced.
- `safe` tag: **12,148,074**; `finalized` tag: **12,146,299**. Both tags were supported. The selected range ends at `safe`; no assumed confirmation depth was needed.
- Latest block parent hash matched the preceding block hash. A sampled live receipt matched its transaction hash, block hash, and block number.

No provider substitution was made. This records the endpoint behavior observed on 4 November; the earlier M1 report's 3 November HTTP 403 observation is historical and may reflect endpoint availability at that time.

## Bounded live range

The selected range contains **150 consecutive blocks**, inclusive:

| Item | Value |
|---|---|
| Chain ID | 1874 (0x752) |
| Start block | 12,147,925 |
| Start block hash | `0x76dbbaeca1b9f663045bac2f83a21816dcde9f09d4bba2b5b6a9543327bed7af` |
| Start parent hash | `0x995dfe012923157e33a02f5941601c14e4faaedbcc6a8b40f9fe8e00ac793138` |
| End block (`safe`) | 12,148,074 |
| End block hash | `0x1ae303ba58b1e94d9730fd1bbbb31d7a061c5adad0721a234e11cd5b9459bb7c` |
| End parent hash | `0x3d083b94d10b7bc4f013354545b4572d18132bf7ddfca30e2b836887b69ef722` |

The live observer persisted all 150 selected blocks, **160 transactions**, **160 receipts**, and **13 logs**. Every transaction had a receipt; receipt log payloads totaled 13 and matched the stored logs. There were zero inconsistent parent links. The isolated checkpoint advanced to block 12,148,074 with the recorded end hash.

## Isolation and restart verification

The validation used PostgreSQL database `orbis_dev`, schema `orbis_m3_live_validation`, and the existing local database role. PostgreSQL listened on localhost. The schema was new and isolated; no existing development checkpoint or M1–M3 demonstration rows were changed, and the test database was not used for live data. Current migrations were applied only inside this validation schema.

After closing and reopening the store, the observer replayed the same range and indexed **0** additional blocks. The checkpoint remained at 12,148,074. No database reset, destructive operation, commit, push, or deployment occurred.

## M3 enrichment results

The range contained **160 eligible transactions**. Enrichment completed in four non-empty batches of **50, 50, 50, and 10**. The store was reopened after the first batch; processing resumed successfully. Final status was **eligible 160, processed 160, remaining 0**. A repeat invocation processed **0** transactions and left all generated counts unchanged. All 160 transactions had derived observations; **0 empty-fact transactions** occurred in this sample.

| Live validation schema count | Total |
|---|---:|
| Entities | 12 (3 contract, 9 unknown) |
| Observations | 340 |
| Relationships | 22 |
| Evidence references | 340 |

Relationship types were 10 `transacted_with`, 8 `interacted_with_contract`, and 4 `transferred_to`. Observation types were 160 `transaction_initiated`, 160 `transaction_received`, 13 `emitted_event_during`, and 7 `token_transfer_received`.

## Representative on-chain evidence

The examples below were read from the isolated PostgreSQL schema and rechecked against the configured live RPC. The observer also validated every receipt against its transaction and block before persistence.

- **Repeated direct participant pair:** `0x2071ce18e0d9c7a3059a7a2ddd82aebb8e20e609` → `0x5de04c3fe89d7fd6cdcf2a12724179d843f41629` has two `transacted_with` evidence records: transaction `0x6a5499a807d71bacdb1ae2d96aadf8d07301b264cc1ec107b4f263c9abc5ad1c` at block 12,147,975 and transaction `0x12b5704109641fda8c43a511a507af50b183ea73bd976afd6424be623aecca1e` at block 12,148,034. Both receipts matched their live transactions and blocks. The addresses remain `unknown` entities, so this is not asserted to be wallet-to-wallet activity.
- **Direct contract interaction and event emission:** transaction `0x6a5499a807d71bacdb1ae2d96aadf8d07301b264cc1ec107b4f263c9abc5ad1c` has `tx.to` equal to `0x5de04c3fe89d7fd6cdcf2a12724179d843f41629`; its receipt's log index 0 is emitted by that same contract. The `interacted_with_contract` relation is supported by the transaction-level evidence, while the event observation references the receipt log.
- **ERC-20 Transfer and multiple emitters:** transaction `0xa9524c0b4b86150b74d1c9b290d3f9ef0d82c9530423decac3bba8e44621719b` at block 12,147,981 has `tx.to` `0x0ac538e15e4c7a27e6e38025bed911b8975044f0`. Its receipt contains log indices 0 and 1 from two different emitters. Log 0 is emitted by `0x2e652a62314c4b51480e54fc55954f51bf20d2b7` and has the standard Transfer signature, two correctly padded indexed addresses, and one 32-byte amount word. The decoded raw amount is **146,880,000**; the resulting `transferred_to` evidence points to log index 0. Log 1 is emitted by the actual transaction recipient. The first log emitter was not substituted for `tx.to`.
- **Repeated aggregate:** the pair above has support at blocks 12,147,975 and 12,148,034; its relationship count is 2 and its first/last observed blocks match those evidence records. Another repeated pair has 150 supports across the selected range.

No entity ownership, user intent, or maliciousness is inferred. No wallet-to-wallet classification was observed because participant entities are not proven wallets. No mint/burn example occurred in the selected sample. ERC-20 decoding claims apply only to the implemented standard Transfer layout; other event signatures remain raw log evidence.

## Reorg, regressions, and limits

No live canonical data was altered to test reorg behavior. Controlled PostgreSQL fixture tests remain authoritative for suffix rollback, partial aggregate recomputation, omission of earliest/middle/latest support on replacement, full relationship deletion, replay, repeated rollback, and failure atomicity. Specific cases include `test_reorg_recomputes_partial_relationship_aggregates_and_replay`, `test_replacement_block_can_omit_earliest_middle_or_latest_support`, and `test_rollback_failure_is_atomic_for_knowledge_and_chain_state` in `tests/test_postgres_integration.py`. The full project suite passed with PostgreSQL integration tests enabled: **31 tests, 0 failures, 0 skips**. Python compilation and `git diff --check` passed; M1 observer/RPC and M2 persistence/replay regressions passed.

The validation demonstrates a bounded testnet sample, not full history or production throughput. The 150-block sample contains no proven wallet entity classifications. ERC-20 is the only decoded event standard. The validation schema is retained in the local development database for owner review; it is separate from the main development and test schemas.

## Final acceptance

**PASS.** The configured live RPC matched chain ID 1874, provided safe/finalized tags, and supplied a contiguous bounded range with matching transactions, receipts, and logs. The isolated observer and M3.1 enrichment completed, restarted, and replayed idempotently. Engineering regressions passed without skipped integration tests. The approved PRD remains unchanged, and M4 remains unstarted.
