# ORBIS M5.0.2 — Frontend Implementation Plan

**Status:** Incremental frontend foundation plan. No frontend, HTTP API, or API framework currently exists in the repository.

## Architecture recommendation

Keep the existing Python/PostgreSQL ORBIS application as the only backend and source of truth. Add a small static HTML/CSS/JavaScript frontend (ES modules, no build tool initially) under a dedicated `frontend/` directory. Serve it from the same ORBIS process/deployment boundary as a future read-only API, once API hosting and authorization are implemented. The browser must not connect directly to PostgreSQL, RPC, or a second data service.

Repository evidence: `pyproject.toml` packages Python 3.11 code and depends on psycopg; existing entry points are CLI/database tools. There is no web framework, API route, frontend package, build configuration, or API DTO convention. Therefore an API framework decision belongs with backend integration; avoid adding a framework solely to support a placeholder page. This is compatible with M5.0.1 §6–7's same-process read API direction, while preparing the requested incremental frontend.

## Initial page structure

One operator overview page, with a persistent selected configured network profile and these sections:

1. **Network status:** configured profile; verification/connection state; chain ID; genesis hash and fingerprint; exact identity resolution state; RPC head and last verification time. Render unresolved/mismatched identity as blocked. A client-supplied fingerprint is never proof.
2. **Observer synchronization:** sync state, last successful run, requested/processed inclusive range, canonical checkpoint number/hash and freshness. Show recent indexed activity as persisted block/transaction rows with source detail links.
3. **Detection and evaluation:** D-02 lifecycle state as returned by backend (staged/active/retired), immutable version and policy readiness; recent evaluations with range, execution status, analytical outcome, coverage and canonicality/invalidation. Do not infer activation or completeness in the client.
4. **Evidence-backed findings:** paginated findings with mint/burn event classification, emitter, block/transaction/log identity, canonical/invalidation state and evidence link. Detail view presents retained raw topics/data, decoded fields, validation result, provenance and evidence digest.

## API integration contract

Implement read DTOs and a query service over existing PostgreSQL observer and M4 repositories first. Add versioned same-origin read endpoints in the existing ORBIS backend. Initial routes can follow M5.0.1 §6: network status, observer status, recent blocks/transactions, D-02 rule status, evaluations, findings and finding evidence. Use bounded pagination and explicit configured-profile selection; resolve that profile server-side through verified `NetworkContext` and scope all reads by its internal network ID. Never accept chain ID alone or a caller-supplied fingerprint as authority. Responses expose DTOs, not database rows or secrets.

Every response must distinguish unavailable/error, stale, no persisted data, incomplete coverage, failed execution, `matched`, `not_matched`, `insufficient_coverage`, and invalidated historical result as applicable. An empty list is “no records returned for this query,” not proof of no chain events. The API may report only values backed by persisted records; findings must link to retained evidence snapshots.

## Honest states before API readiness

The first frontend increment may be a static shell with explicit “API not connected”/“status unavailable” states and empty tables labeled “No persisted records returned.” It must contain no seeded live metrics, fabricated findings, pretend health indicators, or synthetic chart values. If synthetic fixtures are ever displayed during development, label fixture mode visibly and isolate it from live mode.

## Delivery order

1. Define DTOs and a read-only query service using existing repositories; document freshness and canonicality fields.
2. Select an HTTP layer consistent with the existing backend process and deployment/authorization boundary; do not add a second backend.
3. Add the static page shell, responsive styles and accessible loading/error/empty states.
4. Connect sections incrementally as real API records become available; keep unsupported sections explicitly unavailable.
5. Verify network isolation, bounded pagination, stale/error/empty states, invalidated finding display and evidence provenance before presenting live data.

No activation controls, write endpoints, historical backfill, fabricated data, or production infrastructure changes are part of this frontend foundation.
