# ORBIS

**Observe. Understand. Reason. Verify.**

ORBIS is Whitechain-first on-chain intelligence infrastructure. It indexes real chain evidence, applies deterministic and explainable analysis, and exposes traceable results to applications and operators. M3.1 engineering remediation and final bounded live validation passed. The repository does not yet provide an assessment API, deterministic intelligence rules, SDK, MCP server, or dashboard.

## Current milestone: M3 — PostgreSQL knowledge layer (M3.1 remediation implemented)

The observer verifies the configured RPC chain ID, indexes bounded blocks with receipts/logs, and stores its checkpoint atomically. The M3 knowledge service separately enriches canonical transactions with network-scoped entities, transaction participation, individual log-emitter evidence, and validated relationships. Reorg rollback recomputes relationship summaries from surviving evidence. PostgreSQL is authoritative; SQLite remains a lightweight observer adapter. The final live validation indexed 150 Whitechain Sepolia blocks in an isolated PostgreSQL schema. See the [M3 engineering report](docs/M3_VERIFICATION_REPORT.md), [M3 live validation report](docs/M3_LIVE_VALIDATION_REPORT.md), and [M2 verification report](docs/M2_VERIFICATION_REPORT.md).

The approved PRD's Whitechain testnet references list conflicting configurations. The earlier M1 report records HTTP 403 responses on 3 November and an Ankr testnet validation. On 4 November, the configured `rpc.testnet.whitechain.io` endpoint responded with chain ID 1874 and supported safe/finalized block tags for the bounded M3 validation. Endpoint behavior and first-party configuration confirmation can vary over time; `.env.example` intentionally supplies no endpoint default. See the [M1 verification report](docs/M1_VERIFICATION_REPORT.md) and [M3 live validation report](docs/M3_LIVE_VALIDATION_REPORT.md). Sources: [Whitechain wallet configuration](https://docs.whitechain.io/general/wallet-configuration), [Whitechain developer guide](https://whitechain.io/blog/start-building-on-whitechain).

## Requirements

- Python 3.11 or newer and PostgreSQL 14 or newer.
- `uv` is recommended for an isolated environment. The PostgreSQL driver is installed from project dependencies. SQLite fixture tests do not require a running database.

## Run the tests

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

The PostgreSQL integration tests are skipped unless `ORBIS_TEST_DATABASE_URL` points to a disposable PostgreSQL database. They create and remove an isolated test schema. To run only those tests, load the ignored `.env` and use `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -p 'test_postgres_integration.py' -v`. The M3.1 verification run executed all 31 tests with 0 skips.

To run the complete suite against the configured local PostgreSQL test database:

```bash
set -a
source .env
set +a
.venv/bin/python -m unittest discover -s tests -v
```

## PostgreSQL setup and migrations

On Ubuntu, install and start PostgreSQL with `sudo apt-get install -y postgresql postgresql-client` and `sudo systemctl enable --now postgresql`. The packaged cluster should listen on loopback only; verify with `ss -ltn | grep 5432`. Create a dedicated role and databases:

```bash
sudo -u postgres createuser --login --pwprompt orbis_app
sudo -u postgres createdb --owner=orbis_app orbis_dev
sudo -u postgres createdb --owner=orbis_app orbis_test
```

Use a URL-safe password (or percent-encode reserved characters in the connection URL). Copy `.env.example` to `.env` and set `ORBIS_DATABASE_URL` and `ORBIS_TEST_DATABASE_URL` there, pointing to `127.0.0.1` and their respective databases. Copy only placeholders into Git. Install the locked dependencies with `uv sync --locked`. Migrations in `migrations/` run automatically when the observer CLI starts; they can also be applied explicitly with `PYTHONPATH=src python -m orbis.db_migrate`. The database owner role can create the schema objects required by first-time migration.

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

## Project documents

- [Architecture proposal](docs/ARCHITECTURE.md)
- [Environment audit](docs/ENVIRONMENT_AUDIT.md)
- [Decision register](docs/DECISIONS.md)
- [Implementation roadmap](docs/IMPLEMENTATION_ROADMAP.md)
- [Development guide](docs/DEVELOPMENT_GUIDE.md)
- [Approved PRD source](docs/ORBIS_PRD_Architecture_Specification_v0.1.pdf)
