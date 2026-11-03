# Development guide

## Local setup

The observer requires Python 3.11+, PostgreSQL for authoritative runs, and the project psycopg driver. Create an isolated environment and install the package:

```bash
uv sync --locked
```

SQLite fixture tests need no live database. The indexed chain endpoint must be explicitly configured; do not copy an unverified candidate into a shared or production environment.

For Ubuntu local PostgreSQL, install the distro packages and start its service. Create a local-only application role with `sudo -u postgres createuser --login --pwprompt orbis_app`, then create `orbis_dev` and `orbis_test` owned by that role. Set `ORBIS_DATABASE_URL` and `ORBIS_TEST_DATABASE_URL` in ignored `.env`; use loopback host `127.0.0.1`. Keep the service bound to localhost and credentials out of tracked files. The verified local setup and exact test commands are in the [M2 verification report](M2_VERIFICATION_REPORT.md).

## Configuration

See [`.env.example`](../.env.example). Required values are `ORBIS_RPC_URL`, `ORBIS_CHAIN_ID` and `ORBIS_DATABASE_URL`; a fresh index also requires `ORBIS_START_BLOCK`. Set `ORBIS_DATABASE_URL` to PostgreSQL for authoritative runs, or a `sqlite:///...` URL only for fixture/local development. Do not store RPC or database credentials in source control. `.env` is ignored by Git.

## Verification

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
python -m compileall -q src tests
set -a; source .env; set +a
.venv/bin/python -m unittest discover -s tests -v
```

The regular suite uses deterministic fixtures, primarily SQLite, and a fake RPC adapter. PostgreSQL integration tests are a separate test class and require an explicitly configured disposable database; skipped tests do not count as PostgreSQL verification.

## Observer operations

Run a pass with `PYTHONPATH=src python -m orbis.cli`. The process verifies chain ID, determines a safe head, indexes sequentially and exits. A failed block does not commit that block's checkpoint. The next run resumes from the latest committed block.

Use a separate database per environment. Data keys include network identity and chain-scoped blockchain identifiers. PostgreSQL migrations run at CLI startup and are also available as a command. Back up PostgreSQL with `pg_dump` after stopping the indexer and validate restoration with `pg_restore` before production use.

Knowledge enrichment is a separate bounded operation. Initialize `PostgresStore`, then call `KnowledgeService(store).ingest(chain_id, limit=500)`; it reads persisted canonical records and is safe to retry. Do not call it against a SQLite observer store. Retrieval methods take a chain ID and address, and observations/history accept bounded page sizes. Reorg rollback retracts derived evidence and generated observations; rerun enrichment after the observer replays replacement blocks.

## Contribution and milestone discipline

Keep chain RPC behavior behind `src/orbis/chain`, indexing/reorg logic in `src/orbis/observer`, and configuration environment-driven. Keep deterministic fixtures separate from live evidence. Update `DECISIONS.md` when an open architectural item is resolved. Do not claim live network acceptance until the endpoint returns the expected chain ID and actual indexed block/receipt evidence can be inspected.
