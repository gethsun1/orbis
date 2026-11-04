# ORBIS M4.1 Final Audit

**Date:** 4 November 2026 (Africa/Nairobi)
**Scope:** identity review and M4.1 lifecycle verification. No M4.1 identities were rewritten, no migrations were applied, and no rule evaluator was implemented.

## Workspace preservation

At audit start, `git status --short` showed modifications in `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`, `docs/IMPLEMENTATION_ROADMAP.md`, and `docs/M3_VERIFICATION_REPORT.md`. These existing changes were preserved. `.env` was not read or modified. No reset, clean, stash, commit, push, or deployment was performed.

## Verified identity behavior

`src/orbis/rules/identity.py:evaluation_identity` uses `orbis-evaluation-v1` and hashes a canonical JSON object containing `network.chain_id`, normalized subject, stable rule ID/version/definition digest, block bounds, parameters, context digest and evaluator build.

The database adds a second scope: `UNIQUE(network_id,evaluation_key)`. Within one database, `networks.chain_id` is itself unique, so rows with equal chain IDs cannot be represented as two networks there. Across independent installations, however, the same chain ID and otherwise identical tuple produce the same v1 key even if the installations represent separate chains. `network_id` is a database-local surrogate and is deliberately absent from the hash; including it would make identities installation-dependent. No genesis hash or other stable network fingerprint is persisted in the M4 request/envelope contract or supplied to `evaluation_identity`.

Therefore:

- The evaluation key includes a chain ID, but does not include a sufficient canonical network identity.
- Distinct networks with the same chain ID can produce identical v1 keys across installations.
- Database uniqueness and application identity agree only within the local network row. The database constraint prevents duplicate keys per local network; it cannot correct the cross-installation collision.
- Identity is stable across installations for equal inputs when chain ID is treated as the whole network identity. That is insufficient for networks sharing a chain ID, so the requested stronger portability guarantee is not met.

`tests/test_rules.py` now records this as a regression reproducer and has an expected-failure test for a fingerprint-aware v2 identity. This makes the defect executable and visible without changing persisted behavior. The v2 assertion will become an ordinary passing regression when the correction is authorized and implemented.

## Recommended backward-compatible correction

Add a stable `network_fingerprint` to the evaluation identity request. Prefer the genesis block hash, normalized as lowercase 32-byte hex, combined with chain ID under a documented fingerprint scheme. For example:

```text
network_fingerprint = sha256(canonical_json({"chain_id": chain_id, "genesis_hash": genesis_hash}))
evaluation_key_v2 = sha256(canonical_json({"algorithm": "orbis-evaluation-v2",
    "network": {"chain_id": chain_id, "fingerprint": network_fingerprint}, ...existing fields...}))
```

The caller must obtain and validate genesis identity from the configured/indexed network, rather than accept an arbitrary caller-supplied label. The fingerprint belongs in the immutable evidence envelope and persisted evaluation metadata so it can be audited independently. If a network cannot provide a trustworthy genesis hash, require an explicitly governed canonical identifier and record its provenance; do not silently fall back to chain ID alone.

Keep v1 rows and keys immutable. Roll out v2 as a new identity algorithm version and new evaluations. Do not update existing `evaluation_key` values or recompute old evaluation rows in place. Add an `identity_algorithm`/fingerprint field through an additive migration, make new service writes require v2, and retain read/retrieval compatibility for v1. The existing `(network_id,evaluation_key)` unique constraint remains valid; application identity and database uniqueness stay aligned. V2 yields portable equal keys for the same canonical network inputs across installations and different keys for networks with different fingerprints, even when chain IDs match.

This is a recommendation, not an implemented correction. It should be approved before any externally relied upon cross-installation identity contract. No roadmap change is needed because M4.2 is not yet implemented and evaluation identities are internal persistence keys.

## M4.1 lifecycle audit

| Guarantee | Actual implementation and test evidence | Audit result |
|---|---|---|
| Rule-version immutability | `rule_versions` definition fields are protected by a trigger; lifecycle transitions are staged → active → retired. `RuleRegistry` verifies definition digest and provides retrieval/activation/retirement. Database guard behavior is installed by migrations 009/012. | Implemented. No M4.1-specific PostgreSQL test exercises attempted mutation/delete or lifecycle transitions; the verification report overstates this test coverage. |
| Failed evaluation behavior | `record_failure` inserts a failed evaluation with null outcome and an append-only attempt. Migration 011 makes evaluation result fields terminal. Duplicate identity returns the existing row and does not retry/promote it. | Implemented as a terminal failure policy. Test covers initial failed persistence, but not duplicate failure/retry behavior. |
| Concurrent creation | Unique `(network_id,evaluation_key)` and `INSERT ... ON CONFLICT DO NOTHING` serialize same-network duplicates. A PostgreSQL thread test confirms identical negative requests return one ID and create no findings. | Implemented and integration tested. Cross-installation collision remains as above. |
| Evidence integrity | Item/envelope/context SHA-256 verification lives in `evidence.py`; retrieval verifies envelope digest after source deletion. Identity projection and finding-evidence rows are guarded against mutation/deletion. | Implemented; unit tamper detection and integration retrieval after block deletion are covered. PostgreSQL does not independently verify JSONB-to-projection agreement after insertion; the projection is checked against the envelope at write time by repository flow, not by a database trigger. |
| Atomic reorg invalidation | `PostgresStore.rollback_from` calls `_invalidate_m4_for_suffix` inside its transaction before source cleanup. It locks orphan blocks, updates affected active evaluations and inserts audit. Injected block-delete failure test confirms both state domains roll back. | Implemented and integration tested. |
| Replacement linkage | Composite self-FK and trigger require a same-network, same-rule, same-subject invalidated predecessor. Integration test replaces evidence with a new context/key and links the new evaluation. | Implemented and integration tested. |
| Historical evidence survival | Evaluation snapshots, child projections, findings and audits have no FK to blocks/logs. Retrieval test reads invalidated evaluation and finding after block deletion. | Implemented and integration tested. |
| Coverage | Assessor validates known states, missing mandatory dimensions default to unknown, and `gate_outcome` maps negative results with `insufficient_dimensions` to insufficient coverage. | Partially enforced. The repository independently checks the supplied coverage object's `insufficient_dimensions` field, but does not recompute coverage against the immutable rule-version policy or verify that coverage in the envelope equals the separate evaluation coverage. Callers can omit mandatory dimensions unless orchestration supplies a correct assessor result. The report's claim that coverage is rule-aware is stronger than this enforcement. |

Additional implementation discrepancies found:

- `finding_identity` and the repository's default finding key hash only the result payload. Evidence identity is not part of the default match key, so two otherwise identical results supported by distinct evidence can collide within one evaluation. Rule-specific finding identity remains caller-controlled but the repository does not enforce evidence inclusion. This should be corrected before D-01/D-02 persistence is relied on.
- `make_item` validates block number/log index presence but does not validate block/transaction hash format or canonicalize/check normalized input types; callers must supply already-normalized values.
- `record_failure` bypasses the same outcome/coverage gate used in successful result orchestration, which is acceptable for null analytical outcome but means diagnostic coverage is caller-assessed.
- The integration test count in the earlier M4.1 report is now stale because this audit adds two identity tests (one expected failure). The audit run result is recorded below.

These findings are limited to audit/documentation and a test reproducer. No source or migration correction was made in this task.

## Verification run

Command: `set -a; source .env; set +a; PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v`

Result: **40 passed, 1 expected failure** (41 tests total). The expected failure is the pending fingerprint-aware v2 identity assertion; it fails because the current API has no fingerprint input. Existing M1–M3 and PostgreSQL integration cases passed. `compileall` and `git diff --check` passed.

## Decisions and readiness

Verified facts, defect, recommended correction and D-01/D-02 owner decisions are separated in [M4.2 Rule Decisions](M4_2_RULE_DECISIONS.md). M4.2 contract decisions are ready for owner review. M4.2 implementation is **not ready to start** until the owner resolves the listed D-01/D-02 decisions and approves a handling plan for the identity and finding-key gaps. No D-01/D-02 behavior is implemented here.
