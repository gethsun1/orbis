# ORBIS implementation roadmap

**Status:** M0 review complete; M1 and M2 accepted; M3 Knowledge Layer and M3.1 remediation/live validation passed. M4.0 specification finalized. M4.1 implementation has not started. See the [M3 engineering report](M3_VERIFICATION_REPORT.md), [M3 live report](M3_LIVE_VALIDATION_REPORT.md), [decisions](DECISIONS.md) and [M4 specification](M4_SPECIFICATION.md). Dates are unset pending capacity planning.

## M0 — Product and architecture review (complete)

- Approved baseline is the supplied PRD PDF v0.1, retained unchanged. Environment, architecture, decisions and initial sequencing are recorded.
- Exit: owner clarification recorded; initial stack/modular boundaries proposed; remaining decisions assigned or sequenced. Live ingestion was verified through Ankr; first-party endpoint confirmation and policy remain a DevRel follow-up.

## M1 — Whitechain observer (accepted)

- Configurable provider adapter, startup chain verification, head/block/log retrieval, provider health, bounded incremental ingestion, persistent cursor, retry/backoff and reorg-safe replay.
- Exit: actual confirmed testnet evidence, restart-safe cursor, duplicate-safe behavior and reorg test. No fabricated live data.
- The implementation requires explicit chain ID and RPC URL. Endpoint observations are historical and recorded in M1/M3 reports; no automatic fallback is claimed. SQLite was the initial observer store; PostgreSQL followed in M2.

## M2 — PostgreSQL persistence foundation (accepted)

- PostgreSQL migrations persist networks, blocks, transactions, receipts, logs, checkpoints, entities, observations and evidence references; SQLite remains a development adapter.
- PostgreSQL verification and bounded live persistence passed; see [M2 report](M2_VERIFICATION_REPORT.md). Production operations remain out of scope.

## M3 — Knowledge layer (accepted; M3.1 remediation complete)

- Network-aware entities, reproducible direct observations, evidence-backed relationships, transactional idempotent enrichment, retrieval and reorg invalidation.
- Exit: PostgreSQL integration checks and bounded live Whitechain knowledge demonstration; see M3 reports. M3 does not include deterministic intelligence.
- M3.1 addressed partial-reorg relationship summaries, durable multi-batch enrichment, relationship semantics, receipt/log provenance, bounded retrieval and network isolation. Final bounded validation recorded 150 blocks; its counts are historical sample results, not current database counts or full network coverage.

## M4 — Deterministic intelligence (sequenced from PRD M3 by owner decision D-023)

The original PRD remains authoritative; all original D-01–D-05 rules remain mandatory. D-06 liquidity movement remains outside the initial five. See [M4 specification](M4_SPECIFICATION.md) for rule contracts, coverage, lifecycle, versioning, evidence preservation, schema design and owner decisions.

### M4.0 — Specification and architecture approval (complete)

- Finalize M4 documentation and record the sequencing decision. No implementation or migration is included.

### M4.1 — Rule contracts and persistence

- Implement rule registry/versioning, independent evaluation lifecycle dimensions, findings, retained evidence snapshots, coverage contracts and idempotency.
- Exit: approved persistence design implemented with network isolation, immutability, constraints and reproducibility. Requires separate authorization after M4.0.

### M4.2 — D-01 and D-02

- Implement native/token-specific large transfer and validated ERC-20 mint/burn detection with provenance and required coverage.
- Exit: deterministic fixtures cover match, non-match, failure, malformed/unsupported input and boundary semantics.

### M4.3 — D-05

- Implement concentration analysis only after owner approval of cohort, metric parameters, eligible transfer semantics and minimum-data requirements.
- Exit: bounded, single-network/window, per-asset results with exact evidence; insufficient denominator/data is not represented as zero concentration.

### M4.4 — D-03 and D-04

- Implement event-only role and pause/upgrade detections after owner approval of standards/event allowlists.
- Exit: supported event fixtures and explicit unsupported-standard coverage; no claims about current effective state.

### M4.5 — Integration and reorganization lifecycle

- Validate immutable evidence preservation, atomic invalidation/audit alongside existing suffix rollback, distinct replacement evaluations, reproducibility and bounded live-data demonstration.
- M4 exit requires all five original rules implemented and verified, unless an outstanding change is explicitly approved and documented.

## M5 — Reasoning and investigations (sequenced from original PRD M4)

- Context retrieval, explainable investigations, facts/hypotheses separation and constrained optional explanation only if justified. Evaluate MeTTa behind an adapter, not as a prerequisite.
- Exit: reproducible golden workflow with evidence links and deterministic operation during AI outage.

## M6 — REST API

- Authentication/tenant scope, versioned endpoints, OpenAPI, pagination, quotas/rate limits, async assessment semantics and integration evidence.
- Exit: external developer completes assessment flow using docs/API key; consistent errors and access-control checks.

## M7 — TypeScript SDK

- Typed client, configuration, auth, timeout/retry behavior, pagination, errors, tests and integration example.
- Exit: build and integration verification; publish only at the relevant release gate.

## M8 — Dashboard and MCP

- Operator views of real system/indexer state and investigations; read-only MCP tools over shared service methods with validated schemas and permissions.
- Exit: end-to-end use through dashboard and compatible MCP client; clear live/cached/unavailable state.

## M9 — Whitechain contracts

- Registry and evidence anchor only after contract scope review; deployment/verification, event indexing and digest verification. Subscription settlement remains deferred pending legal/commercial validation.
- Exit: tests, verified deployment and independent evidence hash verification.

## M10 — Pilot and production readiness

- Security and dependency review, performance baseline, backup/restore, operational runbook, pilot onboarding and reproducible demo.
- Exit: pilot feedback, measured reliability, recovery evidence and honest production-readiness assessment.

## Cross-cutting gates

- At each gate record objective, implementation, architecture changes, actual verification, limitations and next milestone. Do not claim acceptance without evidence.
- Do not commit, push, deploy or publish without explicit authorization.
- No milestone date, numeric SLO, pricing, traction or adoption target is asserted; the PRD leaves these for measurement or validation.
