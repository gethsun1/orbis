# ORBIS implementation roadmap

**Status:** M0 review complete; M1 and M2 accepted. The current owner-authorized M3 brief defines this milestone as the knowledge layer, advancing deterministic rules to a later gate; see [M3 verification report](M3_VERIFICATION_REPORT.md). Dates are unset pending capacity planning.

## M0 — Product and architecture review (complete)

- Read the supplied PRD, audit the local environment, extract scope and produce this architecture, decision register, environment audit and roadmap.
- Owner confirmed the PDF is approved as-is despite stale discussion-draft wording. Environment audit, requirements extraction, architecture proposal, decision register and milestone plan are recorded.
- Exit: owner clarification recorded; initial stack and modular boundaries proposed; remaining open decisions assigned or sequenced. Live ingestion is verified through Ankr; first-party endpoint confirmation and policy remain a DevRel follow-up.

## M1 — Whitechain observer (accepted)

- Implement configurable provider adapter, startup chain verification, head/block/log retrieval, provider health, bounded incremental ingestion, persistent cursor, retry/backoff and reorg-safe replay.
- Exit: actual confirmed testnet block/log evidence, restart-safe cursor, duplicate-safe behavior and reorg test. No fabricated live data.
- The implementation requires explicit chain ID and RPC URL. Both Whitechain-hosted candidates returned HTTP 403; Ankr's Whitechain Sepolia endpoint returned chain ID 1874 and passed block/receipt/log calls. A bounded live index was stored in disposable SQLite and independently counted; fixture tests cover restart, replay and reorg rollback.
- M1 accepted for bounded observer behavior. Ankr is the currently verified endpoint; DevRel confirmation of first-party endpoint canonicality and limits remains open. SQLite is temporary; PostgreSQL is M2 work, not an M1 acceptance dependency.

## M2 — Knowledge foundation (accepted)

- Implemented PostgreSQL migrations for networks, blocks, transactions, receipts, logs, checkpoints, entities, observations and evidence references; SQLite remains a development adapter.
- PostgreSQL 18.6 local verification passed with a non-superuser ORBIS role. All 11 unit tests and 7 PostgreSQL integration tests passed.
- Three real Whitechain Sepolia blocks, four transactions, four receipts and two event logs persisted into PostgreSQL. Duplicate replay, checkpoint restart recovery and reorg rollback/replay passed; see the M2 verification report.
- M2 accepted for this bounded persistence milestone. Production operations and the M3 intelligence engine remain out of scope.

## M3 — Knowledge layer (current authorized scope)

- Implement network-aware entities, reproducible direct observations, evidence-backed relationships, transactional idempotent enrichment, retrieval and reorg invalidation.
- Exit: PostgreSQL integration checks and a bounded live Whitechain knowledge demonstration; see M3 report.

## M3b — Deterministic intelligence (PRD sequence deferred)

- Select five feasible PRD detections; implement immutable rule versions, findings, severity/coverage and known limitations after the knowledge layer is reviewed.
- Exit: unit/integration tests with fixtures and documented limitations; fixture outputs are clearly test-only.

## M4 — Reasoning and investigations

- Build evidence/context retrieval and complete assessment workflow; add constrained optional explanation only if justified. Evaluate MeTTa behind adapter, not as a prerequisite.
- Exit: reproducible golden workflow with evidence links, facts/hypotheses separation and deterministic operation during AI outage.

## M5 — REST API

- Authentication/tenant scope, versioned endpoints, OpenAPI, pagination, quotas/rate limits, async assessment semantics and integration tests.
- Exit: external developer completes assessment flow using docs/API key; consistent errors and access-control tests.

## M6 — TypeScript SDK

- Typed client, configuration, auth, timeout/retry behavior, pagination, errors, tests and integration example.
- Exit: TypeScript build/tests and successful API integration; publish only with separate approval.

## M7 — Dashboard and MCP

- Operator views of real system/indexer state and investigations; read-only MCP tools over shared service methods with validated schemas and permissions.
- Exit: end-to-end use through dashboard and compatible MCP client; clear live/cached/unavailable state.

## M8 — Whitechain contracts

- Registry and evidence anchor only after contract scope review; deployment/verification, event indexing and digest verification. Subscription settlement remains deferred pending legal/commercial validation.
- Exit: tests, verified deployment and independent evidence hash verification.

## M9 — Pilot and production readiness

- Security and dependency review, performance baseline, backup/restore, operational runbook, pilot onboarding and reproducible demo.
- Exit: pilot feedback, measured reliability, recovery evidence and honest production-readiness assessment.

## Cross-cutting gates

- At each gate: state objective, implementation, architecture changes, actual verification, limitations and next milestone.
- Do not claim acceptance without recorded evidence. Do not commit, push, deploy or publish without explicit authorization.
- No milestone date, numeric SLO, pricing, traction or adoption target is asserted; the PRD leaves these for measurement or validation.
