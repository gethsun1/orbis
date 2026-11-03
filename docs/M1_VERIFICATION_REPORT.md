# M1 verification report

**Verification date:** 3 November 2026 (Africa/Nairobi)  
**Scope:** M0/M1 baseline, observer code audit, live Whitechain RPC checks, and local persistence architecture. No M2 capabilities were started.

## Executive result

**M1 — Whitechain observer: accepted for the scoped M1 gate.** The configured-chain guard, bounded block/receipt ingestion, durable SQLite cursor, duplicate replay, rollback/replay, and provider health result are implemented and tested. A live bounded run against Whitechain Sepolia through Ankr persisted actual blocks, transactions, and receipt logs into disposable SQLite databases. The checked-in default remains unset; use the verified endpoint and chain ID only when explicitly configured.

This acceptance does not accept the wider MVP. PostgreSQL, source-provider provenance on stored rows, sustained ingestion, operational monitoring and the later API/intelligence requirements remain future work. Candidate A and B remain inaccessible from this environment. The currently usable configuration is Ankr Whitechain Sepolia, chain ID **1874**, at `https://rpc.ankr.com/whitechain_testnet`.

## Source PRD and milestone mapping

The source is `ORBIS_PRD_Architecture_Specification_v0.1.pdf`, version 0.1 dated 1 November 2026. Its front matter still calls itself a discussion draft and says M0 approval is required. The local decision register records the owner's 3 November approval of this PDF as-is and as authoritative (D-001); this verification preserves that decision and does not revise the PDF.

| Gate / requirement | PRD requirement and acceptance evidence | Implementation and verification | Result |
|---|---|---|---|
| M0 | Section 13.1: approve product/scope, confirm endpoint and chain ID with DevRel/live RPC, approve architecture/schema/security, assign remaining assumptions, define M1 tasks and repository ownership. | The owner approval is recorded in D-001 and the roadmap. Endpoint was live-verified here, but DevRel confirmation and several non-M1 decisions in D-017 remain open. | **M0 approval recorded; listed follow-up decisions remain assigned/open.** |
| FR-01 / M1 provider | Configured Whitechain RPC; health check returns chain ID, head and provider status. M1 gate: RPC adapter and chain verification. | Environment-only URL and expected chain ID; `eth_chainId` comparison; `eth_blockNumber`; CLI result reports `provider_status=healthy` after both calls succeed. Live Ankr run succeeded. | **Pass** |
| FR-02 / M1 ingestion | Incremental blocks/logs; cursor advances after durable processing; safe replay. M1 exit also calls for real testnet block/log evidence and restart-safe cursor. | Full block objects and every transaction receipt are required. Block, transactions, receipt logs and checkpoint commit in one SQLite transaction. Live block 12,057,644 stored with 2 transactions and 2 logs; file-backed reopen and repeated-sync tests pass. | **Pass** |
| FR-03 | Normalize transactions, logs, addresses and token events; preserve canonical source identifiers and raw evidence references. | Transactions and receipt logs persist with chain, block/hash, transaction and log index. Token event normalization and provider metadata are not implemented. | **Partial; beyond M1 observer scope.** |
| FR-04 / M1 reorg | Roll back/replay changed canonical suffix without duplicates. | Checkpoint hash and parent links are compared with remote blocks; common ancestor search; foreign-key cascades remove dependent rows. Reorg replay and transaction/log cleanup tests pass. | **Pass for current confirmation-depth observer.** |
| FR-05–09 | Persist intelligence records; deterministic rules; grounded explanations; REST API; auth/quotas. | Not implemented. | **Not M1 scope; later gates.** |
| M2 | PostgreSQL schemas, entities, observations, evidence references, migrations, validation and idempotency. | Current store is SQLite behind the indexer's `ObserverStore` protocol; PostgreSQL backend/migrations do not exist. | **Not started, correctly deferred.** |

### Scope and roadmap alignment

The roadmap's M1 boundary (adapter, chain verification, bounded ingestion, persistent cursor and reorg replay) aligns with PRD M1. The roadmap had described the two Whitechain-hosted endpoints as the only live candidates and stated both returned 403. This audit also tested Ankr, identified in the request and PRD reference notes, and verified it. The roadmap and D-008 now record that result; the project has not silently changed M1/M2 boundaries. SQLite remains interim; PostgreSQL remains the M2 foundation per approved architecture.

## Code audit

- **RPC/configuration:** standard-library JSON-RPC over HTTP(S); environment-required endpoint and expected chain ID; no chain ID fallback. Chain mismatch fails before indexing. HTTP 403 is not retried; HTTP 429/5xx and transport errors use bounded retries. Error messages omit endpoint credentials.
- **Block and transaction extraction:** blocks must match the requested height and include valid hash, parent hash, timestamp and full transaction objects. Receipt transaction hash, block number/hash and each log's transaction/block identity and required fields are validated before persistence.
- **Receipts/logs:** every block transaction needs a receipt. Missing, mismatched or malformed receipt/log data fails the block before commit. Receipt logs are the persisted log source; there is no separate `eth_getLogs` ingestion path yet.
- **Atomicity/restart/idempotency:** SQLite's transaction context groups block, transaction, receipt-log and checkpoint writes. Failed validation leaves the affected block uncommitted. A file-backed close/reopen test verifies durable checkpoint recovery. Replaying already indexed height does not duplicate rows.
- **Reorg/rollback:** local checkpoint hash is rechecked remotely; parent hash mismatch initiates common-ancestor search. Block deletion cascades to transaction/log rows and checkpoint is restored in the same transaction. Tests assert dependent rows are removed. This is a confirmation-depth heuristic; Whitechain finality policy has not been confirmed with DevRel.
- **Persistence abstraction:** indexer depends on a small `ObserverStore` protocol; `SqliteStore` is the only implementation. SQL schema/DDL and conflict syntax are SQLite-specific.
- **CLI/logging:** explicit environment configuration; bounded pass; JSON result reports chain, head, safe head, number of blocks, checkpoint and provider status. No credentials are logged. Logs cover retries, reorgs and indexed heights. No ongoing metrics/health endpoint exists.
- **Coverage limits:** fixtures cover wrong chain/height, missing and mismatched receipts, safe checkpointing, reopen, duplicate replay, reorg replay, rollback cascade, RPC 403 no-retry and 429 retry. There is no PostgreSQL contract test, provider-health endpoint, sustained-run test, or separate logs-query integration test.

## Test results

Command: `PYTHONPATH=src python3 -m unittest discover -s tests -v`  
Result: **11 tests passed**, 0 failures (3 November 2026).

The test suite uses deterministic fixtures. Live verification is separately evidenced below; it is not represented by fixture tests.

## Whitechain RPC investigation

Probes were run 3 November 2026 (Africa/Nairobi) using valid JSON-RPC POSTs with JSON content type. DNS resolution and TLS 1.3 succeeded for all three hosts. RTTs below are observed single-request timings, not service-level measurements.

| Candidate | DNS / TLS | `eth_chainId` | Further checks | Finding |
|---|---|---|---|---|
| A `https://rpc.testnet.whitechain.io` | DNS resolved; TLS 1.3 succeeded | HTTP 403, body `error code: 1010` (~0.73 s) | `eth_blockNumber` and `eth_getBlockByNumber` also HTTP 403 (~0.58 s each). | Network path reaches a TLS endpoint; RPC access denied. No evidence distinguishes endpoint policy from IP/network filtering. |
| B `https://rpc-testnet.whitechain.io` | DNS resolved; TLS 1.3 succeeded | HTTP 403, body `error code: 1010` (~0.57 s) | `eth_blockNumber` and `eth_getBlockByNumber` also HTTP 403 (~0.60 s each). | Same limitation as A. Repeated retries were not made. |
| C `https://rpc.ankr.com/whitechain_testnet` | DNS resolved; TLS 1.3 succeeded | HTTP 200, result `0x752` = **1874** (~1.02 s) | `eth_blockNumber` HTTP 200, head 12,058,607 at first probe (~0.93 s). Full latest block returned structured transaction objects (~0.84 s). Receipt lookup succeeded for a transaction; transaction hash matched and its receipt had 0 logs. `eth_getLogs` over 1,001 blocks returned 113 logs; sampled receipt matched and had 2 logs. | Usable for tested public read calls without an API key. |

**Live indexer evidence:** using a disposable temporary SQLite database and the repo's `RpcClient`/`Indexer`, chain ID 1874, confirmation depth 12 and batch size 3, the indexer stored three actual blocks and three transactions, then checkpointed block 12,058,620. A second disposable run at block 12,057,644 stored one actual block, two transactions and two receipt logs; its checkpoint hash was `0x7e2d355059b3541e9220e9208a5f5c60a1f77f5583051e359a45a36a9eecc7b8`. Temporary data was removed after each run. No transaction was submitted.

**Status page:** [Whitechain status page](https://status.whitechain.io/) showed mainnet and testnet RPC API listed as “today” and no recent notifications / reports in the last 7 days when checked. This is aggregate status-page information; it does not explain the 403 responses from A/B.

**Authentication and limits:** Ankr's current docs recommend an API-key URL for project use; its 7 October 2026 Whitechain note says basic public calls work without a key, while some `debug_*` / `trace_*` calls require a key and plan. The successful probe used no key, and no credentials were supplied or exposed. Ankr documents an unauthenticated `eth_getLogs` range of about 1,000 blocks per call, blocked filter methods, and no WSS endpoint for this chain. A numeric general request rate limit was not established during this audit. The PRD's July guide says Whitechain's public endpoint limit is 20 requests/sec/IP, but this is dated and should be reconfirmed. Sources: [Ankr Whitechain endpoint notes](https://www.ankr.com/docs/changelog/whitechain-testnet/), [Ankr Whitechain API reference](https://www.ankr.com/docs/rpc-service/chains/chains-api/whitechain/), [Whitechain status page](https://status.whitechain.io/).

**Interpretation:** the 403 is not caused by malformed JSON-RPC: the same valid request shape succeeds on Ankr. DNS/TLS succeed, but this does not determine whether A/B block this source IP, require a policy exception, or are misconfigured. Ask Whitechain DevRel to confirm endpoint A vs B canonicality and chain ID, whether anonymous RPC access should be allowed, any IP/WAF allowlisting, public limits, historical access, finality depth, and the canonical explorer/faucet. Use Ankr as the verified current provider; do not automatically fail over or mix networks.

## Network configuration record

- **Selected verified endpoint:** `https://rpc.ankr.com/whitechain_testnet`
- **Observed chain ID:** 1874 (decimal), `0x752`
- **Verification timestamp:** 3 November 2026, approximately 00:20–00:30 EAT (Africa/Nairobi)
- **Evidence:** live chain-ID/head/full-block/receipt/log probes plus two bounded indexer runs described above; 403 observations for A/B.
- **Runtime policy:** set both `ORBIS_RPC_URL` and `ORBIS_CHAIN_ID` explicitly. `.env.example` stays blank; no automatic fallback. Reverify before shared/production use.

## SQLite and PostgreSQL

PostgreSQL, `psql`, `postgres`, and Docker were not available in the environment at this audit, so no installation recommendation is made. SQLite is acceptable for this bounded single-process observer. The indexer now consumes a persistence protocol, and its critical per-block operation can map to one PostgreSQL transaction containing block upsert, transaction/log writes, and checkpoint upsert; rollback can likewise delete/reconcile the suffix and update the checkpoint in one transaction. Use PostgreSQL constraints and `ON CONFLICT`, SQLAlchemy/Alembic migrations if retained as the chosen stack, and integration tests against a disposable PostgreSQL service before M2 acceptance. Lowest-complexity route: implement a PostgreSQL store behind the existing protocol in M2, migrate an empty/new development database, and keep SQLite fixtures for fast unit tests; do not build generic multi-database abstractions now.

## Outstanding issues and next milestone

- Get Whitechain DevRel confirmation on canonical first-party testnet endpoint/configuration and the observed 403 policy; Ankr currently verifies chain ID 1874 and works.
- Confirm provider limits/finality and add a sustained/restart operational run before relying on continuous indexing.
- Add source-provider provenance to persisted evidence as part of the canonical M2 schema; support a dedicated `eth_getLogs` path only when needed by selected event coverage.
- Implement PostgreSQL schema/backend/migrations and contract tests in **M2 — Knowledge foundation**. Do not expand into M3 or later until the owner starts that milestone.

## Acceptance decision

**M1 is accepted for the Whitechain observer gate.** Its stated exit evidence—real testnet blocks/logs, durable restart-safe cursor, duplicate-safe processing and reorg replay—is present in live runs and tests. The selected provider and chain identity are verified; the implementation refuses a configured chain mismatch. Acceptance is limited to bounded observer behavior and does not certify continuous production reliability, first-party endpoint access, or the wider MVP. Recommended next milestone: **M2 — Knowledge foundation (PostgreSQL and canonical evidence schema)**, after DevRel follow-up is recorded.
