# ORBIS M4.1 Verification Report

**Date:** 4 November 2026 (Africa/Nairobi)
**Scope:** rule contracts, deterministic identity, persistence, evidence, coverage and PostgreSQL rollback invalidation. No D-01–D-05 evaluators were implemented.

## Preflight

Preflight passed before source changes. The approved M4 specification and plan, decision register, roadmap, architecture, approved PRD PDF, M1–M3 verification reports, migrations, persistence code and tests were inspected. The existing `git status --short` contained user changes in `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`, `docs/IMPLEMENTATION_ROADMAP.md`, `docs/M3_VERIFICATION_REPORT.md`, and untracked `docs/M4_1_IMPLEMENTATION_PLAN.md` and `docs/M4_SPECIFICATION.md`; these were preserved.

Branch was `main`, HEAD `ff04bfc` (`Complete M3 knowledge and live validation`), preceded by `cac0206` (`Implement ORBIS knowledge layer`). `PostgresStore.rollback_from` uses one `self.db.transaction()` covering network lookup, M3 evidence cleanup, block deletion and checkpoint repair. The M4 hook runs after network lookup and before M3/source deletion. Its input is the exact network-scoped `(number, hash)` suffix read from `blocks`; evaluations are selected through an indexed evidence projection. M4 snapshots and evidence rows do not reference rollback-deleted source tables. Network-scoped composite constraints and a unique `(network_id,evaluation_key)` support isolation and duplicate prevention. Completed negative results have no findings.

The target databases were inspected without displaying credentials: `orbis_dev` and `orbis_test`, PostgreSQL 18.6, role `orbis_app`, public schema, migrations 001–008. Both were confirmed as the configured development/test targets before migration. No database was reset or recreated.

## Implementation

Additive migrations:

- `009_m4_rule_evaluation.sql`: immutable rule definitions, evaluations, attempt records, findings, retained evaluation and finding evidence, append-only invalidation audit, uniqueness, checks, network-scoped FKs and indexes.
- `010_m4_integrity_guards.sql`: supersession compatibility, invalidation audit enforcement, finding eligibility and retained evidence/attempt immutability triggers.
- `011_m4_terminal_failures.sql`: locks evaluation rows as terminal records while allowing only canonicality invalidation.
- `012_m4_lifecycle_hardening.sql`: guards lifecycle timestamps/reasons and all immutable evaluation metadata.

The M4 tables are `rule_versions`, `evaluations`, `evaluation_attempts`, `findings`, `evaluation_evidence`, `finding_evidence`, and `evaluation_invalidations`. Evaluation rows retain the full canonical JSON evidence envelope and its SHA-256 digest. The child evidence table is a queryable identity projection indexed by `(network_id, block_hash)`; it intentionally has no source-table FKs. Invalidation rows preserve affected finding IDs, orphaned hashes, suffix boundary, reason, timestamp and rollback UUID. Replacement evaluation linkage is a same-network self-reference validated against an invalidated predecessor with the same rule and subject.

Python modules under `src/orbis/rules/` provide rule version registration/lifecycle, canonical JSON and parameter/subject normalization, deterministic evaluation/finding identities, machine-readable coverage gates, evidence snapshot creation and verification, bounded canonical block/log retrieval, PostgreSQL repository methods and the evaluator protocol. The service package contains no D-rule implementations.

Evaluation identity is `SHA256(canonical_json(tuple))`, prefixed `sha256:`. The tuple includes chain ID, normalized subject kind/key, stable rule ID + semantic version + definition digest (not database-local surrogate IDs), explicit inclusive bounds, normalized parameters, canonical context digest and evaluator build identity. JSON is UTF-8, sorted by key, compact, with non-finite numbers rejected; integer and decimal parameters use canonical base-10 strings, address/hash values lowercase, null is retained, omission is distinct, and set arrays are sorted/deduplicated only when the parameter schema declares `x-collection: set`. PostgreSQL uniqueness is authoritative under concurrent inserts.

Evidence item digests cover the complete normalized item (network chain ID, block/hash, transaction hash, optional log index, source kind, normalized consumed input, digest algorithm and schema version). The envelope digest covers the complete envelope including pinned rule, parameters, evaluator build, bounds, coverage, all items and context digest. Retrieval verifies item, envelope and context digests without source-table joins. These digests detect mutation; they do not prove the upstream RPC provider was truthful.

`rollback_from` invokes `_invalidate_m4_for_suffix` inside its existing transaction. It first locks the orphan block suffix for update, then locks active dependent evaluations, updates canonicality, and records finding IDs and exact orphan hashes before the M3 retraction and block deletion. Evaluation creation holds key-share locks on all snapshotted canonical source blocks until its insert transaction commits, serializing new evaluations against rollback. The audit and evaluation source constraints ensure the full rollback aborts if any step fails.

## Verification

- Full command: `set -a; source .env; set +a; PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v`
- Result: **39 tests passed**, including all existing M1–M3 observer, RPC and PostgreSQL regression tests; new tests cover normalization, coverage gating, digest tamper detection, concurrent duplicate negative evaluations, failed evaluations, retained history after source deletion, replacement linkage, repeated rollback idempotency and injected rollback failure atomicity.
- Fresh-schema verification: the PostgreSQL integration harness creates a generated isolated schema, applies all migrations 001–012, and drops only that schema after tests.
- Development/test migration verification: existing `orbis_dev` and `orbis_test` each applied migrations 009–012 through `orbis.db_migrate`; rerunning the migration runner completed without error. Catalog checks found all seven M4 tables and ledger version `012_m4_lifecycle_hardening.sql` in both targets.
- `compileall` and `git diff --check` passed.

## Limitations and remaining work

- A failed evaluation identity is terminal and idempotently returns the existing failure; automatic retry promotion to success is not implemented. Attempt records retain the initial execution diagnostics. The owner must select a retry/generation contract before retryable execution is enabled.
- Maximum evaluation range/item limits need a rule or service policy; `ContextRepository` validates explicit bounds but does not yet impose a configured cap.
- Rule parameter schema validation covers the normalized JSON types and declared formats/defaults; it is not a complete JSON Schema implementation. Rule contracts can add stricter validators when approved.
- Exact executable replay requires retaining the evaluator artifact identified by `evaluator_build`; artifact retention is outside this milestone. Snapshots retain the normalized consumed inputs and original outcome.
- PostgreSQL is the only supported M4 persistence backend. SQLite behavior is unchanged.
- No actual D-rule contracts, thresholds, allowlists, severity mappings, API, queues, or AI components were added. M4.2 can begin only with separate owner authorization and the relevant rule decisions.

No commits, pushes or deployments occurred. `.env` and dependencies were not changed.
