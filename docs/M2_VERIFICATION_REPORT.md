# M2 verification report

**Verification date:** 3 November 2026 (Africa/Nairobi)  
**Status:** **M2 accepted** for the PostgreSQL knowledge foundation and bounded observer gate. The system is locally operational; production readiness is not claimed.

## Implementation

- PostgreSQL is the authoritative CLI target behind the `ObserverStore` persistence boundary. The M1 RPC adapter and indexing/reorg flow were preserved. SQLite remains an explicit local/test adapter.
- psycopg 3.3.6 with its binary libpq driver is locked in `uv.lock` and installed in the project `.venv`. Database URLs are required environment settings; no credentials are stored in tracked files.
- Ordered, transactional SQL migrations create the schema migration ledger and these tables: `networks`, `blocks`, `transactions`, `receipts`, `logs`, `checkpoints`, `entities`, `observations`, and `evidence_refs`. Migration 002 adds network environment/provider metadata and the initial knowledge records.
- Blockchain facts use network-scoped keys. Transactions, receipts, logs and evidence references have foreign keys to their matching block/source. Checkpoints reference a committed block. Unique constraints protect chain IDs, canonical block heights/hashes, transaction hashes/positions, log identities and entity addresses. Query indexes cover block parents/heights, transaction participants, log address/block, entity address, observations and evidence lookups.
- Each block, its transactions, complete receipt JSONB, receipt logs and checkpoint update commit in one PostgreSQL transaction. Invalid duplicate transaction hashes/positions are rejected before upsert. Replaying a committed block is idempotent and cannot move the checkpoint backwards. Suffix rollback and checkpoint restoration are transactional. A block referenced by evidence is protected from deletion until that evidence is retracted.
- `ORBIS_NETWORK_NAME`, `ORBIS_NETWORK_ENVIRONMENT` and `ORBIS_PROVIDER_NAME` can persist non-secret network/provider identity. RPC URLs and credentials remain external configuration.

## Environment and database

- Provisioning: Ubuntu 26.04.1 native PostgreSQL packages; PostgreSQL server/client **18.6**. Docker was not installed.
- Cluster: `18/main`, service active and enabled; observed listener `127.0.0.1:5432`. No remote listener was observed.
- Databases: `orbis_dev` and `orbis_test`; login role `orbis_app` owns both. PostgreSQL confirmed `orbis_app` is **not a superuser**. Passwords are kept only in the ignored local `.env`; none are recorded here.
- Python: 3.14.4; psycopg **3.3.6**, binary libpq **18.0.6**.
- Migrations `001_initial.sql` and `002_knowledge_records.sql` applied successfully. The migration command was rerun and remained successful; the integration suite also initializes migrations in fresh isolated schemas.
- Direct catalog inspection confirmed **10 tables**, **101 constraints**, and **30 indexes** in `orbis_dev`, including primary keys, unique/check constraints, foreign keys and the deferred checkpoint-to-block relationship.

## Test results

Command: `set -a; source .env; set +a; .venv/bin/python -m unittest discover -s tests -v`

**Result: 18 tests passed, 0 failures, 0 skips.** This includes 11 existing SQLite/RPC unit tests and 7 real PostgreSQL integration tests against `orbis_test`.

PostgreSQL tests covered connection and migration initialization/idempotence, block/transaction/receipt/log/checkpoint persistence, duplicate processing, database uniqueness and foreign-key enforcement, transactional rollback after a mid-block failure, restart recovery, the indexer's reorg rollback/replay over PostgreSQL, entity-observation-evidence relationships, protection against deleting evidence-referenced source blocks, and visibility isolation before commit.

Additional checks passed:

- `uv sync --locked`
- `python -m compileall -q src tests`
- `git diff --check`
- Read-only PostgreSQL catalog inspection of tables, keys, foreign keys and indexes.

## Live Whitechain indexing evidence

- Provider: Ankr Whitechain testnet, configured at run time. No endpoint key was used or logged.
- Fresh RPC check returned chain ID **1874**. The indexed data was within the confirmed/safe range at ingestion.
- Bounded range: blocks **12,057,643–12,057,645** (3 blocks).
- Stored block hashes:
  - 12,057,643 — `0x17c4f6e64ac21f85709c92b3a51d91392f35a65669b442e3bf7d2f991540d81a`
  - 12,057,644 — `0x7e2d355059b3541e9220e9208a5f5c60a1f77f5583051e359a45a36a9eecc7b8`
  - 12,057,645 — `0xcef6005830270167b2d347f2473e29dc2e573740138d9cb08b25d94ff0df9a73`
- Independent PostgreSQL queries confirmed **3 blocks, 4 transactions, 4 receipts, and 2 event logs**. Block 12,057,644 contained two transactions and two receipt logs.
- Persisted checkpoint: block **12,057,645**, hash `0xcef6005830270167b2d347f2473e29dc2e573740138d9cb08b25d94ff0df9a73`.
- Reprocessing the actual final block left counts unchanged at **3 / 4 / 4 / 2** and preserved the checkpoint.
- After closing and reopening the PostgreSQL store, the normal indexer recovered that checkpoint. A restart sync capped at the stored height indexed **0 additional blocks** and retained the same checkpoint.
- Network metadata stored with the records: chain 1874, Whitechain Sepolia, testnet, provider Ankr.

No historical backfill, smart contract call, transaction submission, public deployment, or network exposure was performed.

## Integrity review and limitations

- PostgreSQL FKs prevent orphaned transactions, receipts, logs, checkpoints and evidence references. Atomic tests confirm a failed receipt serialization rolls back both the inserted block and transaction and leaves the checkpoint unchanged.
- Evidence references use restrictive source FKs. If future derived observations refer to a block that reorganizes, the current rollback operation will fail safely until those references are retracted; automatic observation lifecycle invalidation is not part of this milestone.
- Network identity is currently unique by chain ID, which fits the configured Whitechain observer. Provider credentials are deliberately not stored. The existing confirmation-depth reorg policy remains a heuristic pending Whitechain finality confirmation.
- Migrations are forward-only; there is no downgrade script. Backups and restores are documented, but disaster recovery has not been exercised against production-like data.
- The schema covers initial entity/observation/evidence records, but normalized event decoding, assessments, intelligence rules, API, metrics and continuous production operations remain later scope.

## Acceptance

The requested M2 criteria passed: PostgreSQL is installed and healthy; the application connects with a non-superuser role; migrations and constraints are verified; all unit and PostgreSQL integration tests pass; live Whitechain records persist in PostgreSQL; restart, duplicate replay, transactional rollback and reorg handling were verified. **M2 is accepted for this bounded persistence milestone.** The limitations above remain explicit and do not represent completion of M3 or production readiness.
