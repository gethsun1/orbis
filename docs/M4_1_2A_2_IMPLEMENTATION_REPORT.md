# ORBIS M4.1.2A.2 Implementation Report

**Status:** source and migration implementation completed; PostgreSQL acceptance and privilege-boundary verification are pending. This report does not claim production readiness.

## Files changed for this milestone

- migrations/013_network_identity.sql
- src/orbis/observer/postgres.py
- src/orbis/observer/indexer.py
- src/orbis/knowledge.py
- src/orbis/rules/identity.py
- src/orbis/rules/repository.py
- src/orbis/rules/service.py
- src/orbis/cli.py
- src/orbis/db_migrate.py
- tests/test_network_registry_postgres.py
- tests/test_observer.py
- tests/test_rules.py

Earlier uncommitted M4.1.2A.1 files and unrelated workspace changes were preserved. No .env file was read or modified.

## Registry schema and behavior

Migration 013 adds nullable fingerprint_scheme, network_fingerprint, and genesis_hash fields. Check constraints require either all three to be null or a supported scheme, lowercase SHA-256 fingerprint, and normalized 32-byte genesis hash. A partial unique index enforces (chain_id, fingerprint_scheme, network_fingerprint) for identified rows. The old unique constraint on chain_id is removed; existing network_id values and dependent rows are retained with null identity fields.

The registry resolves only a verified NetworkContext, inserts the exact tuple with ON CONFLICT DO NOTHING, then reads it back under a key-share lock and validates every stored identity field before returning a trusted context. Concurrent identical registrations converge on one row. A different genesis under the same chain ID receives a separate row. Unresolved historical rows are never selected or silently assigned.

The migration rejects new network rows without identity and prevents identity reassignment or assignment by ordinary UPDATE. Historical unresolved rows remain intact. Application registration is performed only through PostgresStore.resolve_network; direct table insert permissions still require production role provisioning and verification, detailed under limitations.

## Context propagation

- **Observer/indexer:** RPC chain ID and block-zero genesis are verified first. PostgreSQL sync resolves the context before reading a checkpoint. The resolved context flows through checkpoint, block-hash, commit, rollback, and count selectors. SQLite keeps its approved single-profile chain-ID API.
- **Knowledge:** entity resolution, ingestion, status, and retrieval methods now require NetworkContext. The service validates trusted state and uses only the resolved network_id, including nested enrichment calls.
- **Rules/evaluation:** EvaluationService.identity and persistence require trusted context; evaluation identity v2 includes the portable network fingerprint. Repository create, failure, and retrieval boundaries validate the context against the registry row. Internal records remain scoped by network_id. Historical identity v1 helper calls remain available for historical compatibility.

Source search finds no PostgreSQL runtime selector that resolves networks by chain ID alone. Remaining chain-ID-keyed operations are confined to SqliteStore, which remains single-network by policy.

## Runtime/schema compatibility and database credentials

The CLI no longer applies migrations at startup. It checks the complete migration filename set, SHA-256 checksums, and identity columns before sync. Migration records now store checksums; legacy records without checksums are populated when the migration command runs. Old writers are fenced by the database trigger that rejects identity-less network inserts. New runtime rejects missing, partial, extra, or checksum-mismatched migration states before network operations.

Runtime uses ORBIS_DATABASE_URL; the separate migration command now requires ORBIS_MIGRATION_DATABASE_URL. This creates an actual credential boundary in application configuration. Production must provision separate least-privilege principals and deliver the two credentials independently. The current migration does not create production roles, grant registration through a hardened function, or implement protected historical backfill/repair operations. Those decisions require the database/security owner and remain blockers.

Compatibility boundary: legacy runtime is rejected by the identity-required insert trigger after migration 013; identity-aware runtime requires the full checksummed migration set. No production migration or backfill was performed.

## Verification

Test runner: Python unittest via the project's frozen uv environment.

- uv run --frozen python -m compileall -q src tests — passed.
- uv run --frozen python -m unittest tests.test_network_identity tests.test_rpc tests.test_observer tests.test_rules tests.test_network_registry_postgres — 31 tests, passed; 4 PostgreSQL registry tests skipped because ORBIS_TEST_DATABASE_URL is not configured.
- uv run --frozen python -m unittest discover -s tests — 55 tests, passed; 28 PostgreSQL integration tests skipped because no isolated test database is configured.
- git diff --check — passed.

pg_isready reports a local PostgreSQL server, but no disposable test database is configured. The server's default database was not accessed. As required, SQLite was not used to substitute for PostgreSQL acceptance. Migration 013 was therefore not applied or validated against PostgreSQL in this run.

The previously reported expected failure was test_v2_distinguishes_networks_sharing_chain_id in tests/test_rules.py. It predated this milestone and captured the v1 chain-ID-only evaluation identity limitation. This milestone adds fingerprint-aware v2 identity, removes the expected-failure marker, and the test now passes.

## Remaining limitations and deployment blockers

- PostgreSQL acceptance remains unverified: migration execution, concurrent registration, constraints, rollback isolation, interrupted transactions, and runtime permissions need an isolated PostgreSQL database.
- Database role grants and hardened registration/backfill/repair functions are not implemented. The migration principal must be able to migrate; runtime must be proven unable to mutate established identity or perform unauthorized administrative operations.
- Rule evidence envelopes retain their historical chain-ID field for compatibility. Repository source blocks are still checked under the exact context's internal network_id, but an envelope schema update coordinated with downstream rule work remains outstanding.
- Existing unresolved rows are deliberately unusable until separately reviewed evidence justifies an administrative association. No backfill is included.
- SQLite remains single-network. No production credentials, database, or deployment was used.

## Recommended next milestone

Provision an isolated disposable PostgreSQL database and separate runtime/migration principals; validate the migration and role grants there; add PostgreSQL tests for context rejection, conflicts, concurrency, isolation, schema compatibility, transaction interruption, and least privilege. Then complete the deployment-readiness closure evidence and a separate coordinated A+B staging rehearsal. Production backfill and deployment remain outside this milestone.
