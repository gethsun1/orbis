# ORBIS

**Observe. Understand. Reason. Verify.**

ORBIS is Whitechain-first on-chain intelligence infrastructure. It indexes real chain evidence, applies deterministic and explainable analysis, and exposes traceable results to applications and operators. The M4.1.2A network identity and infrastructure foundation is accepted for functional MVP development. Production deployment is not yet approved; production operations, an assessment API, SDK, MCP server and dashboard remain future work.

## Current milestone: M5 — Functional MVP workflow

The next milestone is one complete, demonstrable workflow on an explicitly selected network: verify its chain ID and genesis fingerprint, ingest a bounded canonical range, enrich network-scoped evidence, run an approved deterministic detection, and present results with coverage and freshness. PostgreSQL is authoritative; SQLite remains a single-network development adapter. Unresolved historical network records remain inaccessible to fingerprint-aware runtime operations.

Network identity is derived from the selected RPC's verified chain ID and genesis hash. Configure endpoint values explicitly; `.env.example` intentionally supplies no endpoint default. Production credentials, supervisor integration, disaster recovery, external audit custody and production deployment approval remain outstanding.

## Requirements

- Python 3.11 or newer and PostgreSQL 14 or newer.
- `uv` is recommended for an isolated environment. The PostgreSQL driver is installed from project dependencies. SQLite fixture tests do not require a running database.

## Run the tests

```bash
uv run --frozen python -m unittest tests.test_network_identity tests.test_observer tests.test_rpc tests.test_rules -v
```

PostgreSQL integration and deployment tests require an explicitly configured loopback disposable database marked `ORBIS_DISPOSABLE_TEST_DATABASE=1`; they fail closed instead of skipping when that setup is missing. Never point the test variables at an application or production database. `scripts/provision_disposable_postgres.py` provisions roles and a fresh database inside a separately initialized disposable PostgreSQL cluster.

With `ORBIS_TEST_DATABASE_URL` and `ORBIS_TEST_FENCING_DATABASE_URL` set to that disposable database, run the full suite:

```bash
uv run --frozen python -m unittest discover -s tests -v
uv run --frozen python -m compileall -q src tests scripts
```

## PostgreSQL setup and migrations

On Ubuntu, install and start PostgreSQL with `sudo apt-get install -y postgresql postgresql-client` and `sudo systemctl enable --now postgresql`. The packaged cluster should listen on loopback only; verify with `ss -ltn | grep 5432`. Create a dedicated role and databases:

```bash
sudo -u postgres createuser --login --pwprompt orbis_app
sudo -u postgres createdb --owner=orbis_app orbis_dev
sudo -u postgres createdb --owner=orbis_app orbis_test
```

Use a URL-safe password (or percent-encode reserved characters in the connection URL). Copy `.env.example` to `.env` and set local application configuration there. Copy only placeholders into Git. Install the locked dependencies with `uv sync --locked`. PostgreSQL migrations do not run at CLI startup; use the separate migration identity and coordinated fencing/activation procedure for deployments.

For a PostgreSQL backup and restore, stop the indexer, then use `pg_dump --format=custom "$ORBIS_DATABASE_URL" --file=orbis.dump` and `pg_restore --clean --if-exists --dbname="$ORBIS_DATABASE_URL" orbis.dump`. Validate restores against a separate database before relying on them.

For fixture-only local work, set `ORBIS_DATABASE_URL=sqlite:///./data/orbis.sqlite3`. This is a development adapter and is not the authoritative deployment configuration.

## Run a bounded indexing pass

Copy `.env.example` to `.env`, then set `ORBIS_RPC_URL`, `ORBIS_CHAIN_ID`, and `ORBIS_START_BLOCK` using a verified network configuration. The program reads environment variables directly; load `.env` with your preferred local environment tool or export the values in your shell.

```bash
export ORBIS_RPC_URL='https://your-confirmed-rpc'
export ORBIS_CHAIN_ID='1874' # replace with the verified chain ID for that endpoint
export ORBIS_START_BLOCK='0'
PYTHONPATH=src python -m orbis.cli
```

The indexer processes only through `head - ORBIS_CONFIRMATION_DEPTH`. `ORBIS_BATCH_SIZE` bounds each pass. A later run resumes from the durable PostgreSQL checkpoint. Set `ORBIS_DATABASE_URL` explicitly; use the SQLite URL only for local development. Set `ORBIS_TEST_DATABASE_URL` to a disposable PostgreSQL database when running integration tests. Do not point either URL at unrelated data.

## Current limitations

- PostgreSQL is the authoritative target; this local environment uses PostgreSQL 18.6 bound to loopback. Production operations, monitoring, and managed backup retention still require deployment-specific setup.
- The worker performs receipt retrieval sequentially and is intended for bounded testnet validation, not high-throughput production indexing. It rejects incomplete/mismatched blocks, receipts and receipt logs before committing.
- RPC endpoints can restrict access, historical calls, or rate. Failures stop the pass without advancing the affected block checkpoint.
- Reorg replay uses stored block hashes to find a common ancestor. Its confirmation-depth policy needs calibration against verified Whitechain finality behavior.
- This is not a production-ready service. Authentication, REST API, metrics and deployment are later milestones. Local backup/restore commands are documented; production retention and recovery procedures still need deployment-specific validation.

## Local documentation

The workspace's `docs/` directory is intentionally excluded from version control. Repository behavior and setup instructions are summarized here; local milestone notes and reports stay in the working copy.
