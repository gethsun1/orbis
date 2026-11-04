# ORBIS initial architecture proposal

**Status:** M1–M3 accepted; M3.1 remediation and bounded live validation passed; M4.0 specification finalized. PostgreSQL is authoritative. Deterministic intelligence is M4; reasoning and investigations are M5 under owner sequencing decision D-023. See the [M3 engineering report](M3_VERIFICATION_REPORT.md), [M3 live validation report](M3_LIVE_VALIDATION_REPORT.md), [decisions](DECISIONS.md) and [M4 specification](M4_SPECIFICATION.md).

## Product requirements distilled from the PRD

ORBIS is Whitechain-first on-chain intelligence infrastructure. Its first golden workflow is a user submitting a wallet or contract for a bounded assessment: verify the chain and available coverage; retrieve real blocks, transactions and supported logs; normalize and persist provenance; run deterministic versioned detections; create an evidence-linked observation and report; optionally explain retrieved facts while separating hypotheses and uncertainty; and serve the result through a versioned API. The same core is intended to support a typed SDK, read-only MCP tools, alerts and a minimal operator dashboard.

Must-have foundations include incremental, replay-safe ingestion; durable checkpoints; duplicate-safe persistence; reorg reconciliation; normalized chain facts; evidence provenance; deterministic rules; authentication, quotas and rate limits; API/OpenAPI; observability; secret protection; tenant isolation; and explicit coverage/freshness. The original five PRD detection identities D-01–D-05 remain mandatory and are specified in M4. D-03/D-04 allowlists and D-05 parameters are deferred owner decisions, so those rules remain staged pending approval. D-06 liquidity movement remains outside the initial five and requires a selected protocol adapter.

The PRD excludes custody/signing/trading, guaranteed fraud detection, a general-purpose explorer, a proprietary token, full multichain identity, and a custom foundation model. MCP is later MVP, Whitechain registry/evidence contracts are later (M8), and subscription settlement is deferred. AI explanations are non-authoritative and must not override deterministic findings. Synthetic fixtures are for tests only, never represented as live results.

## Proposed boundaries and data flow

```text
Whitechain RPC -> provider/chain adapter -> observer & reorg reconciler
               -> normalizer -> PostgreSQL canonical source and knowledge store
                                      -> M4 versioned deterministic evaluation service
                                      -> retained evaluation/finding/evidence store
                                      -> M5 reasoning and investigation services
                                      -> later REST API / SDK / MCP / dashboard / alerts
```

Start as a modular monolith with explicit interfaces. The chain adapter owns RPC and provider health but makes no risk decisions. The normalizer converts raw payloads to canonical facts without losing source identifiers. PostgreSQL is authoritative for canonical M1–M3 source/knowledge data and, in future M4 implementation, network-scoped rule versions, evaluations, positive findings, coverage, immutable normalized evidence snapshots and invalidation audits. M4 execution/outcome/canonicality are three independent lifecycle dimensions; negative completed evaluations have no synthetic finding. M5 reasoning/investigations consume deterministic results and evidence but cannot mutate findings or turn hypotheses into facts. Later interfaces call shared application services and enforce tenant scope.

The implemented schema has networks, blocks, transactions, receipts, receipt logs, durable checkpoints, entities, observations, evidence references, relationships, relationship evidence and a durable enrichment completion ledger. M4.1 adds immutable rule versions, evaluations, findings, evaluation evidence projections, finding evidence and invalidation audit tables through migrations 009–012. Full normalized evidence envelopes live on evaluation rows; indexed evidence identities have no FK to source blocks/logs, so they remain available after rollback. PostgreSQL suffix rollback invalidates only evaluations that reference exact orphaned hashes and writes affected finding IDs to append-only audit in the existing source transaction. The selected implementation supports a single terminal evaluation record per identity; failed identities remain failed on repeated idempotent submissions. Replacement linkage is same-network, same-rule and same-subject, and requires an invalidated predecessor. SQLite implements observer fixtures and does not carry M4 records.

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

## Open decisions and implementation risks

1. The owner confirmed the supplied PDF is approved as-is; its draft wording remains unchanged. See D-001.
2. Select primary persona, subject type, bounded assessment window, and what “contract assessment” means at first release.
3. Confirm canonical testnet RPC, chain ID, explorer, faucet, rate limits, history/log limits and finality/reorg expectations with Whitechain DevRel.
4. Implement the five retained D-01–D-05 contracts under M4. Approve D-03/D-04 allowlists, D-05 parameters/minimum data and D-01 threshold governance before affected behavior is activated; see `M4_SPECIFICATION.md`.
5. Define API key issuance, tenant boundaries, data retention, authentication scopes, quotas and whether pilot users are external.
6. Approve evidence retention duration and archival/retirement behavior; M4 snapshots must at minimum live as long as evaluations.
7. Decide whether MeTTa or an LLM is needed for M5 investigations; preserve deterministic M4 results.
8. Choose a database/dev-services installation path compatible with the audited environment.
9. Confirm repository ownership, license/open-source scope, collaborator role/IP, and working name/trademark review.
10. Define threat model acceptance, data handling/AI-provider policy, and production boundary.

Key risks are incorrect network configuration, public RPC limits, reorg inconsistency, false positives or misleading risk language, tenant data leakage, prompt injection through on-chain metadata, scope overload for a solo builder, and assuming unavailable local infrastructure. Mitigations are captured in this document and `DECISIONS.md`; they require owner review.
