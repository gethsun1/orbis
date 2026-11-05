# Development guide

## Local setup

The observer requires Python 3.11+, PostgreSQL for authoritative runs, and the project psycopg driver. Create an isolated environment and install the package:

```bash
uv sync --locked
```

SQLite fixture tests need no live database. The indexed chain endpoint must be explicitly configured; do not copy an unverified candidate into a shared or production environment.

For Ubuntu local PostgreSQL, install the distro packages and start its service. Create separate local development and disposable test databases. Set `ORBIS_DATABASE_URL` and `ORBIS_TEST_DATABASE_URL` in ignored `.env`; use loopback host `127.0.0.1`. The PostgreSQL integration guard requires the test database name to start with `orbis_test_`, the database comment to equal `ORBIS_DISPOSABLE_TEST_DATABASE=1`, and the test connection role to be the non-superuser `orbis_test_migrator`. Configure those safeguards explicitly before running integration tests; ownership by an application role is not sufficient. Keep the service bound to localhost and credentials out of tracked files. The verified local setup and exact test commands are in the [M2 verification report](M2_VERIFICATION_REPORT.md).

## Configuration

See [`.env.example`](../.env.example). Required values are `ORBIS_RPC_URL`, `ORBIS_CHAIN_ID` and `ORBIS_DATABASE_URL`; a fresh index also requires `ORBIS_START_BLOCK`. Set `ORBIS_DATABASE_URL` to PostgreSQL for authoritative runs, or a `sqlite:///...` URL only for fixture/local development. Do not store RPC or database credentials in source control. `.env` is ignored by Git.

## Verification

```bash
uv run --frozen python -m unittest discover -s tests -v
uv run --frozen python -m compileall -q src tests
```

The suite uses deterministic fixtures and a fake RPC adapter. PostgreSQL integration and deployment-fencing tests require explicitly configured, marked disposable PostgreSQL databases; the tests fail closed when those safeguards are absent. Follow the disposable setup and test procedure in the [M4.1.2A.4 staging rehearsal](M4_1_2A_4_STAGING_DEPLOYMENT_REHEARSAL.md). Do not point these tests at an application or production database. The latest full-suite and focused PostgreSQL results are recorded in the [M4.1.2A.6 acceptance report](M4_1_2A_6_FINAL_ACCEPTANCE_AND_CLOSURE.md).

## Observer operations

Run a pass with `PYTHONPATH=src python -m orbis.cli`. The process verifies chain ID, determines a safe head, indexes sequentially and exits. A failed block does not commit that block's checkpoint. The next run resumes from the latest committed block.

For a bounded persisted range and provenance report, provide both inclusive bounds: `uv run --frozen orbis-index --start-block 100 --end-block 120`. The command uses the selected configured profile, verifies and resolves its exact `NetworkContext`, and reports `success` only for complete PostgreSQL range provenance. It does not evaluate or activate D-02. SQLite returns unknown range coverage.

Use a separate database per environment. Data keys include network identity and chain-scoped blockchain identifiers. PostgreSQL migrations do not run at CLI startup. Use the deployment fencing sequence documented in `docs/M4_1_2A_4B_OPERATIONAL_READINESS_REPORT.md`: fence and drain the runtime, take a verified recovery point, run `orbis-db-migrate` with the migration identity, then run `orbis-db-activate` only after schema, checksums, roles, and grants pass validation. Back up PostgreSQL with `pg_dump` and validate restoration with `pg_restore` before production use.

Knowledge enrichment is a separate bounded operation. Initialize `PostgresStore`, resolve the selected network from a verified `NetworkContext`, then call `KnowledgeService(store).ingest(context, limit=500)`; each call processes only newly claimed canonical transactions and returns the number completed. A database completion ledger makes retries, process restarts, empty-fact transactions, and concurrent workers safe. Use `ingestion_status(context)` to inspect eligible, processed, and remaining records. Do not call the service against a SQLite observer store. Relationship and evidence retrieval accept bounded `limit`/`offset` pages. Reorg rollback retracts derived evidence, recomputes surviving relationship aggregates, and removes completion rows through transaction deletion; replayed transactions become eligible again.

The frontend foundation is in `frontend/`. From that directory, run `npm ci`, `npm run dev`, `npm run test`, `npm run typecheck`, or `npm run build`. `package-lock.json` is authoritative. The current React/Vite application is a static read-only shell; its typed API boundary reports the API as unavailable until a same-boundary backend read API is implemented. No HTTP API/query service or connected frontend sections are currently available. Do not treat its empty states as network observations.

The isolated test-token workspace is in `contracts/orbt/`. Run `npm ci`, `npm test`, or `npm run compile` there. It uses pinned Hardhat/OpenZeppelin dependencies and Solidity 0.8.19. Its Whitechain Sepolia profile uses Ankr (`https://rpc.ankr.com/whitechain_testnet`); the deploy script checks chain ID 1874, the verified genesis hash, the configured signer against the expected test wallet, and a nonzero gas balance. The M5.1.3 deployment, metadata, mint/burn receipts, and Transfer logs are documented in [the deployment report](M5_1_3_WHITECHAIN_TEST_TOKEN_DEPLOYMENT_REPORT.md). The deployed address remains **PENDING OWNER APPROVAL** for P01. P01 policy approval is not address approval, and D-02 remains inactive pending address review and its other implementation/activation gates.

The latest M5.1.3 backend run passed **73 tests and 21 subtests** against the disposable PostgreSQL 18.6 database `orbis_test_m5_1_4` on port 55432, with zero skips. The focused registry/fencing run passed 16 tests. See the [PostgreSQL recovery and verification report](M5_1_3_POSTGRESQL_RECOVERY_AND_VERIFICATION_REPORT.md). These are disposable integration results, not production readiness or disaster-recovery certification. The main PostgreSQL cluster and `orbis_dev` were not targeted.

Migrations 006–008 add the M3.1 work ledger, receipt provenance, per-log observation identity, retrieval indexes, normalized participant addresses, and cleanup of legacy emitter-as-recipient edges. The production migration procedure requires the deployment fencer and explicit migration URL; see the 4B runbook. The test suite also validates migrations in isolated schemas. Do not reset either database to apply migrations.

Migration 016 stores each indexed block's observed transaction count. This is needed to distinguish a source-complete empty block from missing transaction provenance when assessing a bounded range. Existing blocks retain `NULL` and are deliberately insufficient for negative range claims; the migration does not backfill or repair historical data. `ContextRepository.range_completeness` assesses persisted receipt/log provenance over explicit inclusive bounds. `orbis.rules.canonical_evidence.compose_canonical_evidence` composes canonical non-removed source logs with the exact decoder and existing digest envelope; it is decoder-only and does not persist evaluations or create findings. Do not treat its returned envelope as an activated D-02 result.

## Contribution and milestone discipline

Keep chain RPC behavior behind `src/orbis/chain`, indexing/reorg logic in `src/orbis/observer`, and configuration environment-driven. Keep deterministic fixtures separate from live evidence. Update `DECISIONS.md` when an open architectural item is resolved. Do not claim live network acceptance until the endpoint returns the expected chain ID and actual indexed block/receipt evidence can be inspected.
