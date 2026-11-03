# ORBIS initial architecture proposal

**Status:** M2 accepted for the observer and initial knowledge schema, based on the owner-approved PRD v0.1 (D-001). PostgreSQL is the authoritative persistence target. See the M2 verification report for evidence and remaining operational limits.

## Product requirements distilled from the PRD

ORBIS is Whitechain-first on-chain intelligence infrastructure. Its first golden workflow is a user submitting a wallet or contract for a bounded assessment: verify the chain and available coverage; retrieve real blocks, transactions and supported logs; normalize and persist provenance; run deterministic versioned detections; create an evidence-linked observation and report; optionally explain retrieved facts while separating hypotheses and uncertainty; and serve the result through a versioned API. The same core is intended to support a typed SDK, read-only MCP tools, alerts and a minimal operator dashboard.

Must-have foundations include incremental, replay-safe ingestion; durable checkpoints; duplicate-safe persistence; reorg reconciliation; normalized chain facts; evidence provenance; deterministic rules; authentication, quotas and rate limits; API/OpenAPI; observability; secret protection; tenant isolation; and explicit coverage/freshness. The PRD's initial detection catalogue proposes large transfers, mint/burn, privileged role changes, pause/upgrade events, and concentration/accumulation. The five-rule selection remains open and depends on verified event coverage and fixtures. Liquidity movement is a candidate requiring a selected protocol adapter.

The PRD excludes custody/signing/trading, guaranteed fraud detection, a general-purpose explorer, a proprietary token, full multichain identity, and a custom foundation model. MCP is later MVP, Whitechain registry/evidence contracts are later (M8), and subscription settlement is deferred. AI explanations are non-authoritative and must not override deterministic findings. Synthetic fixtures are for tests only, never represented as live results.

## Proposed boundaries and data flow

```text
Whitechain RPC -> provider/chain adapter -> observer & reorg reconciler
               -> normalizer -> PostgreSQL evidence/knowledge store
                                      -> versioned deterministic rules
                                      -> assessment/orchestration service
                                      -> REST API / SDK / MCP / dashboard / alerts
```

Start as a modular monolith with explicit interfaces, not a fleet of microservices. The chain adapter owns RPC and provider health but makes no risk decisions. The normalizer converts raw payloads to canonical facts without losing source identifiers. PostgreSQL is the authoritative store for blocks, transactions, logs, entities, observations, assessment state and provenance. The rule engine is deterministic, versioned and reproducible. An assessment service composes retrieval, rules, coverage and evidence; an optional reasoning adapter can phrase grounded results but cannot invent facts or mutate findings. All user-facing interfaces call the same application services and enforce tenant scope.

The implemented schema has networks, blocks, transactions, full receipts, receipt logs, durable checkpoints, entities, observations, evidence references, relationships and relationship-evidence links. EVM addresses are validated and stored lowercase, with original observed spelling retained. Chain identity scopes entity keys. The independent knowledge service derives direct transaction participation and contract log emission/interaction facts from persisted canonical records; unknown transaction participants remain unknown, and only log-emitting addresses are classified as contracts. Relationships distinguish observed, aggregated and inferred provenance; the current pipeline emits aggregated direct interactions and no identity or maliciousness inference. Every generated fact references its block, transaction and log where applicable. PostgreSQL transactions make each block's facts and checkpoint atomic. Reorg rollback retracts derived knowledge backed by the affected suffix before deleting blocks; independently authored observations remain protected by restrictive evidence FKs. SQLite implements the observer protocol for local fixtures only and does not carry the PostgreSQL knowledge tables.

## Proposed stack

- Python + FastAPI for API and worker/application services; Pydantic for validated contracts.
- `web3.py` behind a provider interface as the single canonical ingestion client.
- PostgreSQL as source of truth, psycopg for persistence, and ordered repository-owned SQL migrations (no ORM or migration framework).
- Pytest and Ruff for verification and code quality, subject to dependency/runtime compatibility checks.
- TypeScript SDK after API stabilization; Next.js dashboard and official MCP SDK at the relevant gates.
- Optional LLM/MeTTa adapters only when reproducibility, security and dependency value are demonstrated.
- Redis/Celery/RQ are not an initial hard dependency. Add a queue only when durable job volume or latency needs justify it.

## Chain configuration and boundary

Externalize chain ID, network label, RPC URL(s), explorer URL, confirmation/finality policy, provider limits and decoder support. Verify `eth_chainId` at startup and compare it with explicit configuration; record provider identity/timestamps and expose failures. M1 live verification selected Ankr Whitechain Sepolia with explicit chain ID 1874 after both first-party candidates returned HTTP 403; this is a verified current test configuration, not a hardcoded assumption. DevRel confirmation of the first-party endpoint and provider policy remains open. The brief's mainnet reference (chain ID 1875 and `https://rpc.whitechain.io`) is not verified and is not a fallback.

## API and security principles

Treat REST as the primary contract; version routes, publish OpenAPI, use typed request/response schemas, consistent errors, pagination, request limits, idempotency where writes/jobs need it, and tenant-scoped API credentials with hashing, rotation and revocation. Keep the database inaccessible to interface code. MCP tools are read-only initially, explicitly allowlisted, validated and permission-scoped. Validate and bound RPC-facing queries; use timeouts, backoff with jitter and provider rate awareness. Never require private keys for read-only use. Treat chain metadata and retrieved content as untrusted input. Protect webhook delivery against SSRF. Record coverage and freshness; never label incomplete data complete. Establish backup/restore, key management and audit controls before production claims.

## M0 questions / implementation risks

1. Resolve the PRD's status mismatch: the brief calls it approved, but the PDF calls itself a discussion draft and says it is not an implementation contract until approved.
2. Select primary persona, subject type, bounded assessment window, and what “contract assessment” means at first release.
3. Confirm canonical testnet RPC, chain ID, explorer, faucet, rate limits, history/log limits and finality/reorg expectations with Whitechain DevRel.
4. Select and document five detection rules, supported standards/ABIs, thresholds, limitations and labeled test fixtures.
5. Define API key issuance, tenant boundaries, data retention, authentication scopes, quotas and whether pilot users are external.
6. Agree canonical schema, assessment coverage semantics, observation lifecycle on reorg, and reproducibility requirements.
7. Decide whether MeTTa or an LLM is needed at all for initial investigations; preserve a deterministic no-AI path.
8. Choose a database/dev-services installation path compatible with the audited environment.
9. Confirm repository ownership, license/open-source scope, collaborator role/IP, and working name/trademark review.
10. Define threat model acceptance, data handling/AI-provider policy, and production boundary.

Key risks are incorrect network configuration, public RPC limits, reorg inconsistency, false positives or misleading risk language, tenant data leakage, prompt injection through on-chain metadata, scope overload for a solo builder, and assuming unavailable local infrastructure. Mitigations are captured in this document and `DECISIONS.md`; they require owner review.
