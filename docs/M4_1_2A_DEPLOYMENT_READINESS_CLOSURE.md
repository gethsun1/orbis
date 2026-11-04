# ORBIS M4.1.2A — Deployment Readiness Closure

**Status:** Planning and repository inspection only. No database permissions, migrations, runtime code, or deployment procedures were changed or executed.
**Baseline:** `main` at `163a97dddebeee57aa894009c7333dcf180dd0fe`; workspace changes were preserved.
**Related plan:** [M4.1.2A Network Identity and Selection Plan](M4_1_2A_NETWORK_IDENTITY_PLAN.md).

## 1. Executive assessment

The approved policies are retained: unresolved historical rows stay preserved but runtime-ineligible pending verified backfill; SQLite is single-network and rejects multi-network configuration; identity comes from a verified `NetworkContext`; established identity is immutable except for tightly controlled, audited administrative repair; and A+B ship as a coordinated release with the compatible runtime in place before the chain-ID uniqueness constraint is removed. M4.1.2C remains downstream.

The repository does **not** currently provide the deployment controls needed to safely run that release. README instructions create `orbis_app` as the database owner and use it for both the CLI and migration command. The CLI applies migrations at startup; `db_migrate` uses the same `ORBIS_DATABASE_URL`. The migration set contains no role/grant separation for identity operations, and no network identity audit table, retention policy, or historical RPC-to-`network_id` evidence store was found. Existing M4 invalidation audit is narrower: it records evaluation invalidation during rollback and is not a general identity audit facility.

The closure path is concrete, but production readiness remains **blocked** on owner assignments and deployment-specific decisions listed in §8. No production permissions, audit guarantees, historical associations, or backup/recovery readiness are claimed as verified.

## 2. Inspection boundary and verified repository facts

Inspected the repository status, `README.md`, `docs/DEVELOPMENT_GUIDE.md`, `docs/M4_1_2A_NETWORK_IDENTITY_PLAN.md`, `src/orbis/config.py`, `src/orbis/cli.py`, `src/orbis/db_migrate.py`, `src/orbis/observer/postgres.py`, and migrations `001`, `009`–`012`, along with repository searches for PostgreSQL role/grant/audit definitions and deployment/backup files. `.env` was not inspected. No database connection or database command was used.

Verified facts:

- `README.md` instructs local setup to create `orbis_app` as a login and as owner of `orbis_dev` and `orbis_test`. It says the database owner role can create migration objects.
- `PostgresStore.migrate()` applies pending SQL using the same open connection as the store. `src/orbis/cli.py` calls `store.migrate()` at observer startup. `src/orbis/db_migrate.py` also constructs `PostgresStore` from `ORBIS_DATABASE_URL` and invokes `migrate()`.
- There is no distinct migration DSN or database role in the inspected settings/CLI path. The current topology therefore does not demonstrate separation between runtime and migration permissions.
- `migrations/001_initial.sql` defines `networks.chain_id BIGINT NOT NULL UNIQUE`; `PostgresStore._network_id()` uses `ON CONFLICT(chain_id)`. This validates the maintenance-window compatibility concern.
- Repository-wide search found no application migration containing `CREATE ROLE`, `GRANT`, `REVOKE`, or `SECURITY DEFINER` for network identity. No identity-specific trigger or audit table exists in the current schema.
- Migrations 009–012 contain rule/evaluation lifecycle guards and evaluation invalidation audit behavior. In particular, evaluation invalidation auditing is transaction-coupled to reorg invalidation; it does not audit network identity creation, RPC verification, backfill, trust failures, or administrative interventions.
- README documents local `pg_dump`/`pg_restore` commands and advises testing a restore against a separate database. It also states production monitoring, managed backup retention, and recovery require deployment-specific validation. No production backup-retention or rehearsal evidence was found in tracked documentation.
- No tracked deployment manifest, orchestration file, or infrastructure-as-code artifact was found in the inspected file inventory. Thus process fencing, credential rotation, external audit sink, and production role topology cannot be verified from this repository.

These are repository observations only. They do not establish the live database's role memberships, grants, backup state, or production configuration.

## 3. Database role and grant matrix

The following is a proposed target model, not a description of permissions currently installed. Use separate non-login group roles and narrowly scoped login principals. Exact names and deployment mappings remain for the database/security owner to approve. The application must not connect as the database/schema owner, and migration execution must be removed from ordinary runtime startup before production adoption.

| Principal / role | Intended duties | Network identity access | Other database access | Restrictions |
|---|---|---|---|---|
| `orbis_db_owner` (NOLOGIN owner) | Own database objects and schema | Owns registry, functions, triggers and audit tables; no routine interactive use | Object ownership only | No application login; membership not granted to runtime principals; privileged actions independently logged |
| `orbis_migrator` (short-lived deployment login) | Apply reviewed, versioned migrations | DDL only during change window; installs/replaces approved constraints, triggers and functions | DDL/object ownership through controlled `SET ROLE` or equivalent | No ingestion/evaluation workload; credentials available only to deployment job; revoke/disable after migration; all executions recorded |
| `orbis_ingest` (runtime login) | Ingest canonical blocks and advance checkpoints | `SELECT` verified registry rows; `EXECUTE` exact resolve/register operation after application RPC verification; no direct identity-column `INSERT/UPDATE/DELETE` | Minimum DML required for blocks, transactions, receipts, logs and checkpoints | No DDL, no table ownership, no identity backfill/repair, no evaluation writes; no `SET ROLE` into privileged roles |
| `orbis_knowledge` (runtime login) | Enrich and retrieve knowledge | `SELECT` registry identity; no registry identity mutation or backfill/repair function execution | Only required knowledge tables and source reads; split read/write grants if API supports separate roles | No DDL; no identity update; cannot impersonate ingest/evaluation/migrator |
| `orbis_evaluation` (runtime login; M4.1.2C) | Read canonical context and persist evaluations/evidence/findings | `SELECT` registry identity; no registration, backfill, repair, or identity update | Evaluation/rule/evidence tables and required canonical source reads | No DDL or source/registry mutation; not enabled until M4.1.2C authorization review |
| `orbis_identity_backfill` (restricted operator login or controlled role assumption) | Associate a specific unresolved legacy row with verified identity | `EXECUTE` the one-time unresolved-to-verified function; no direct registry identity DML | Read-only evidence and audit views as needed | Human approval/change reference; row lock and unresolved-state check; use only in gated maintenance; each call audited |
| `orbis_identity_repair` (restricted break-glass operator role) | Correct an established identity only after approved recovery review | `EXECUTE` exact one-row repair function that requires expected old tuple and one-use authorization; cannot directly update identity table or authorization rows | Read-only registry/audit access | Explicit owner approval, evidence reference, write gate, two-person review, time-bounded access, external privileged-action logging; no general-purpose repair endpoint |
| `orbis_audit_reader` (read-only login) | Review registry and identity event history | `SELECT` narrowly scoped registry/audit views; explicit `network_id` for unresolved record inspection | Read-only inspection views only | No writes, function execution that mutates, DDL, role membership changes, or secret/config access |

### Grant invariants

- Revoke unnecessary `PUBLIC` privileges, especially function execution and schema creation; grant function execution explicitly. Set default privileges so future migration-created objects do not silently become runtime-accessible.
- Runtime logins must not own the database, schema, tables, sequences, or security-definer functions. Do not grant them membership in owner, migrator, backfill, repair, or audit-writer roles.
- Runtime code must not execute migrations. Migrations run via a separately credentialed deployment job after the write gate is active. The current CLI auto-migration behavior must be removed or made impossible for the production runtime principal before the coordinated release.
- The registry resolver/registrar may enforce tuple format, uniqueness, and immutable state transitions, but PostgreSQL cannot independently prove what an arbitrary RPC returned. The trusted application verifier must construct the context from RPC; the database function constrains who can persist and what transitions are legal. A caller-supplied fingerprint is not RPC proof.
- A normal runtime role may read identity but cannot set, change, clear, or repair it. Backfill and repair are different, separately granted operations. A failure to meet those privilege boundaries blocks migration rollout.
- Read-only administration of an unresolved row is by explicit existing `network_id`, never by ambiguous chain ID. It grants no write capability.

## 4. Audit ownership, write authority and retention

### Proposed operating model

| Audit domain | Accountable owner | Write authority | Read authority | Required record/integrity |
|---|---|---|---|---|
| Identity creation and registry resolution | ORBIS service owner; DB/security owner implements controls | Registry function/trigger only, called by authorized ingestion/runtime principal | Audit reader and authorized service/security reviewers | Profile ID, observed chain ID/genesis, derived scheme/fingerprint, result, `network_id`, actor/service version, timestamp/correlation ID |
| RPC identity verification and trust failures | ORBIS service owner | Application emits structured event to protected audit sink; successful identity can also be recorded transactionally | Security/operations reviewers | Endpoint profile ID (not URL), observed/mismatched fields, failure code, timestamp, caller/service version; never credential material |
| Historical backfill | Data/network owner approves association; DB/security operator executes | Restricted backfill function; audit row and tuple update in same transaction | Auditor, data owner, DB/security owner | Existing `network_id`, old/new tuple, independent evidence references, operator `session_user`, approver/change ID, RPC profile ID, verification time, result |
| Identity repair / rejected reassignment | Data owner approval plus DB/security custodian | Restricted one-use repair function; attempted denial logged by external audit sink or committed denial event | Security/audit reviewer and data owner | Exact old/new tuple, reason, approval, evidence, actor, target row, success/denial; append-only history |
| Administrative intervention / migration | Change owner and DB/security custodian | `orbis_migrator` or controlled DBA action | Audit reader; external privileged-activity log reviewer | Migration hash/version, operator, approval/change ID, start/end, outcome, affected objects and verification report |

The accountable audit owner should be the designated ORBIS service/data owner, with the database/security owner responsible for database enforcement and custody. The actual people/teams are not named in this repository and must be assigned before production.

### Integrity and retention requirements

- Add a network identity event ledger or equivalent protected sink; the repository currently has no such general mechanism. Identity writes should produce append-only events in the same transaction as registry changes. Denied SQL statements that abort a transaction cannot leave a durable audit insert in that transaction; capture rejected reassignment and RPC trust failures through an external protected logger or a denial API that commits a denial event before returning failure.
- Database triggers should reject `UPDATE`/`DELETE` on identity event rows, and runtime principals should have no direct insert/update/delete rights. Security-definer writers should use fixed `search_path`, strict argument validation, narrow `EXECUTE` grants, and transactionally consistent records.
- Triggers and grants do not protect against a superuser/object owner disabling controls. Privileged DDL, role changes, trigger disablement, and audit retention changes therefore require a separate PostgreSQL administrative log and external log custody. Export audit events to an independently administered append-only store or equivalent tamper-evident custody; periodic backups alone do not prove append-only integrity.
- Retain identity creation/verification/backfill/repair events for at least as long as the corresponding registry row and dependent data are retained, plus the applicable incident/audit period. This is a minimum relationship, not a numeric duration. The data owner and security/legal owner must set the exact retention duration, deletion/hold policy, and external sink before rollout; no existing repository policy was found.
- Do not log RPC URLs, API keys, database DSNs, or credentials. Use stable local profile IDs, change IDs, and evidence references.

### Existing versus proposed

**Verified existing:** M4 evaluation invalidation has database-side audit requirements and append-only protections in its own lifecycle. README has local backup commands. **Not verified/absent for this work:** network identity audit events, retention duration, external tamper-evident log custody, role separation, function grants, production backup retention, and a privileged DB activity review process.

## 5. Historical RPC association evidence classification

Backfill requires proof of both (a) the network's chain ID/genesis identity and (b) that the existing historical `network_id` represented that network. A current RPC response alone proves only the endpoint's current identity; it does not prove which endpoint populated a historical row. Chain ID alone is never sufficient when same-ID ambiguity exists.

| Class | Evidence | Backfill disposition |
|---|---|---|
| **A — independently verified and historically bound** | Current endpoint returns configured chain ID and valid block-zero hash; identity is corroborated by an independent trusted RPC/source or retained block-zero artifact; a contemporaneous, integrity-protected deployment/config/operations record ties the endpoint profile to this exact database/environment and existing `network_id`; no contradictory evidence | Accept after two-person review and recorded evidence references |
| **B — trusted historical configuration bound** | Versioned/archived configuration or secret-manager history identifies endpoint profile and expected chain ID for the deployment period; a change record, deployment record, or operator log ties that profile to the database and `network_id`; current RPC verification confirms the same chain ID/genesis; evidence owner attests provenance | Conditionally accept after designated data owner and independent reviewer approve and document why independent corroboration is unavailable |
| **C — supporting, insufficient alone** | Current RPC chain ID/genesis without historical row binding; chain ID; network name/environment/provider; a present-day `.env` or unversioned config; endpoint URL without dated provenance; block height/latest block hash; transaction/address patterns; operator memory | Do not backfill from this class alone. Seek A/B evidence; otherwise quarantine |
| **D — missing or contradictory** | No trustworthy profile-to-row link; RPC chain mismatch; conflicting archived endpoints or genesis values; evidence that one row may contain records from multiple same-ID networks; unverifiable/malformed genesis data | Preserve row unchanged and runtime-ineligible; quarantine for explicit recovery/reindex decision |

**Examples:**

- **Accept:** archived signed deployment record maps database `orbis_dev` and `network_id=17` to profile `staging-east` at a dated release; current RPC verifies the same configured chain ID and genesis; an independent trusted endpoint agrees; reviewers attach both references and approve backfill.
- **Conditional accept:** protected configuration history plus deployment change ticket and operator attestation link the exact database/row to a profile, and the current RPC confirms chain/genesis. Two authorized reviewers approve the evidence gap and record it.
- **Reject:** a current endpoint reports chain ID 1, and the unresolved row has `chain_id=1`, but no record links that endpoint to the row. This is not enough even if the row name says “mainnet”.
- **Quarantine:** archived config points to two different providers that now report different genesis hashes for a row, or evidence indicates the chain endpoint changed during the row's history. Do not select the “most likely” network or split child records automatically.

### Backfill acceptance criteria

For each row, require all of the following before the restricted function may run:

1. Existing `network_id` and chain ID are captured from an authorized read-only inventory; no row is recreated or re-keyed.
2. RPC chain ID matches the stored chain ID; block zero exists; hash format is valid; fingerprint is derived locally using the frozen scheme.
3. Historical evidence meets Class A or approved Class B and explicitly binds this row/database/environment to the endpoint profile. At least two reviewers approve Class B.
4. Evidence references, profile ID, operator/approver, change ID, timestamp, fingerprint, and decision are recorded before or atomically with the tuple update.
5. No contradictory evidence, duplicate fingerprint assignment, or mixed-network warning exists. A uniqueness conflict or partial prior attempt stops the batch for review; never merge network IDs.
6. Update is per-row transactional and idempotent: unresolved-to-complete is one commit; retry seeing the identical already-resolved tuple records/returns “already applied”; a different tuple or stale expected state fails and quarantines.
7. Rows failing any criterion remain untouched and runtime-ineligible. Administrative inspection remains by explicit `network_id` only.

## 6. Maintenance and rollback rehearsal

### Rehearsal before production window

Perform these steps in disposable PostgreSQL environments, never against production data:

- Apply all migrations to an empty database and upgrade a populated backup copy; compare `network_id` values, registry counts, child row counts/key checks, constraints and foreign keys.
- Run role tests with the proposed runtime, migration, backfill, repair, and read-only roles. Prove runtime cannot execute DDL or mutate established identity, migration role is unavailable to service processes, and repair/backfill controls are restricted/audited.
- Run A+B code against both old schema (with new writes disabled) and migrated schema in explicit compatibility modes; verify startup refuses incompatible schema/code combinations before any write.
- Inject failures before migration, during transactional migration, during each row backfill, during selector verification, and during startup. Confirm gates remain closed and restart behavior is deterministic.
- Test backup restoration into an isolated target, then run row/key/FK checks and start a compatible binary in read-only/disabled-write mode. Document restore time, data-loss point, and responsible operator.
- Run the full PostgreSQL migration/isolation acceptance suite against isolated schemas or disposable databases, including same-chain/different-genesis registration and concurrent operations.
- Validate all audit event types, failed-attempt capture, access control, append-only behavior, external export, and retention configuration with the audit/security owner.

### Production maintenance-window checklist

1. **Preflight:** release/change ID approved; exact app image/commit and migration checksum pinned; schema compatibility matrix reviewed; all four owner assignments complete; RPC profile/evidence inputs reviewed without logging secrets; operators on call.
2. **Backup and recovery:** create consistent backup; record timestamp/version; verify checksum/readability; restore to a separate target; verify registry IDs, representative dependent keys/FKs and application read-only startup. Do not proceed if recovery check fails or restore time exceeds the approved window.
3. **Gate writes:** stop ingestion, knowledge, evaluation, scheduled jobs and all network-dependent writers. Fence old runtime credentials/processes, confirm no old writer can reconnect, and verify active sessions through approved read-only operations. Keep gates in place through schema, backfill and acceptance checks.
4. **Deploy compatible A+B/schema:** ensure no old code is writing; run migration using `orbis_migrator`, not the runtime principal; install identity-aware runtime with network writes disabled; never allow an old `ON CONFLICT(chain_id)` writer to execute after removing that constraint.
5. **Verify schema and selectors:** read-only catalog checks confirm all-or-null checks, composite uniqueness, immutability trigger, restricted functions/grants and expected migration version. Runtime smoke checks prove only verified/resolved contexts reach data services and no chain-only selectors remain. Confirm SQLite rejects multiple profiles.
6. **Backfill:** process only approved Class A/B rows. Record per-row success/skip/quarantine. Stop on identity conflict, missing audit write, inconsistent state, or unexpected row count. Partial completed rows remain intact; do not clear or reassign them automatically.
7. **Acceptance checks:** run PostgreSQL migration and cross-network isolation suites on staging/disposable schemas. On the production database, perform only approved read-only invariant checks during the window; do not run destructive test cases there.
8. **Enable:** verify all planned identities and unresolved-row quarantine report; enable fingerprint-aware operations behind the approved gate. Start one selected network worker, observe context/fingerprint/checkpoint behavior, then enable remaining configured workers.
9. **Resume ingestion:** confirm each worker reports the selected local profile, chain ID, fingerprint, resolved `network_id`, and independent checkpoint without exposing endpoint secrets. Monitor for registry conflicts, trust failures, rejected identity mutation, checkpoint anomalies, and audit sink health.
10. **Closeout:** capture migration checksum, binary version, role membership/grant report, backfill ledger, audit export receipt, test report, exceptions/quarantines, and operator approvals in the change record.

### What can and cannot be rehearsed

- **No production writes required:** code/schema compatibility checks on a clone; migration dry run on a clone; role/trigger/function tests in disposable PostgreSQL; vector/RPC response tests with controlled fixtures; backup restore rehearsal; audit-sink and retention validation; failure injection; rollout/rollback tabletop; selector source review.
- **Requires controlled staging:** real multi-process A+B runtime against migrated PostgreSQL; concurrency and reorg isolation; staged backfill with representative evidence; disabling/re-enabling runtime principals; interruption/restart testing.
- **Production-window only:** stop/fence actual workers, take production backup, execute approved migration, perform approved row backfill, run read-only invariants, and enable/resume production ingestion. Production acceptance tests that mutate/delete data are prohibited; execute them on isolated copies.

## 7. Rollback scenarios and recovery verification

There is no routine down migration after same-ID rows can be registered. Keep the new schema and fingerprint tuple uniqueness. Never restore the old application as a writer while it depends on `ON CONFLICT(chain_id)` or chain-only selection.

| Scenario | Required action | Data/recovery rule |
|---|---|---|
| Backup or restore rehearsal fails | Abort before maintenance; do not gate/migrate production | Repair backup procedure and repeat rehearsal |
| Write gate cannot fence an old process/session | Abort migration | Do not remove `UNIQUE(chain_id)` while any old writer may reconnect |
| Migration fails before commit | Keep all writes disabled; inspect migration transaction/error; correct forward or restore pre-change backup if schema state is uncertain | Never start old code until schema/constraint state is verified compatible |
| Partial application deployment | Keep gate closed; deploy the matching A+B binary or restore pre-migration schema only if no migration/backfill/new writes committed and recovery is verified | Do not run mixed versions with writes enabled |
| Backfill interrupted | Leave committed per-row updates and audit events intact; restart by inventorying each row; retry only unresolved rows or exact already-applied tuple; quarantine tuple conflicts | Do not roll back completed rows wholesale or infer missing associations |
| Backfill identity mismatch/audit sink unavailable | Stop batch and keep the row/runtime operation disabled; restore audit service/evidence and review | No identity update without complete verified evidence and durable audit record |
| Runtime selector check fails after migration | Keep write gate closed; roll forward compatible code or restore pre-change backup if no post-migration writes exist | Do not reopen old writer path |
| Failure after fingerprint-aware ingestion resumes | Stop/gate affected writers; preserve schema and audit; diagnose/forward-fix with compatible code | If restore is necessary, explicitly reconcile or accept loss of all post-backup writes; do not silently restore over them |
| Same-ID row resolves to wrong internal ID or cross-network contamination suspected | Immediately stop all affected network writes; preserve DB/audit state; incident review and data quarantine | No automated reassignment/merge. Use approved repair or reindex/recovery plan |

### Recovery verification before reopening

- Confirm one compatible application version is active and old writer credentials/processes are fenced.
- Confirm migration state and registry constraints/triggers/functions from catalogs; run read-only selector/context probes.
- Compare registry IDs and selected data counts/keys against the pre-change manifest or restored backup; account for every permitted backfill and post-backup write.
- Verify audit ledger continuity and external export for creation, verification, backfill, repair, denials, and migration activity.
- Confirm unresolved/quarantined rows remain blocked, SQLite profile validation is correct, and each enabled worker's resolved context matches its registry tuple.
- Obtain release owner and DB/security owner sign-off before reopening the write gate.

## 8. Outstanding decisions, owners, and closure evidence

Approved policies are not reopened here. These deployment-specific decisions remain genuinely open because the repository does not identify the relevant people, managed services, or production configuration.

| Blocker / decision | Owner to assign | Required decision/evidence to close | Status |
|---|---|---|---|
| Role names, grants, login/NOLOGIN mapping, and removal of runtime auto-migration | DB/security owner + application release owner | Approved grant matrix applied in staging; role tests prove least privilege; runtime cannot migrate; migration job uses separate identity | Open; no grants verified |
| Identity audit owner, sink, write/read authority and retention duration | ORBIS data/service owner + security/compliance owner | Named accountable owners; numeric retention/hold policy; append-only/external custody design; test/export evidence | Open; no identity audit mechanism/policy found |
| Historical RPC-to-row evidence standard and approval authority | Network operations/data owner | Approved Class A/B evidence rules, named reviewers, sample evidence packet, quarantine/reporting workflow | Open; no historical association evidence inspected or assumed |
| Maintenance window, credential/process fencing and rollback objectives | Release owner + DB operator | Approved runbook; compatible version matrix; backup restore rehearsal; maintenance duration/RPO/RTO; rollback tabletop and sign-offs | Open; README has local commands only, no production rehearsal evidence |
| Profile config precedence/limits (if JSON profiles are implemented) | Application owner | Schema/size/precedence/error contract and secret handling | Open for implementation; must not weaken explicit profile selection |
| PostgreSQL controlled repair function details | DB/security owner + data owner | Review one-use authorization design, function ownership/search path, role grants, audit and actual-PostgreSQL positive/negative tests | Proposed controls only; not implemented or validated |

No historical records were inspected against live RPCs, and no identity associations are claimed. No current database grants or external audit controls were verified.

## 9. Final consistency and readiness determination

The actual plan contained more stale material than the prior report indicated: the executive summary still reopened unresolved-row and SQLite policy; the SQLite configuration paragraph allowed a future schema redesign; inventory and test rows framed single-network SQLite as undecided; migration/data-preservation sequencing could be read as schema-first; §11 and §12 reopened approved decisions; and the file had a prior terminal report appended after its audit boundary. These are genuine consistency defects. They have been corrected: approved policies are stated in §13, conflicting sequence/test language is aligned to the maintenance window, and the appended conversational report was removed. The policy itself was not changed.

The critical safety ordering is now explicit: old writers stop first; migration runs only through a separate deployment principal; compatible A+B code is activated with writes gated; selectors/schema/backfill/audit are verified; only then are fingerprint-aware writes enabled. There is no old-code write window after removal of `UNIQUE(chain_id)`. Interrupted backfill and rollback after ingestion resumes preserve completed history and require forward-compatible recovery rather than chain-ID fallback.

**Final readiness:** M4.1.2A is **not yet ready for coordinated A+B production implementation/deployment**. The technical path is specified, but role/grant assignments, audit ownership/retention, row-association evidence approval, and a rehearsed maintenance/rollback runbook remain open. Engineering may prepare the implementation and staging rehearsal, but do not execute production backfill or remove the constraint until each blocker in §8 has owner-approved closure evidence. M4.1.2C remains downstream.

## 10. Evidence register and files inspected

Repository files inspected for this closure:

- `README.md` — local role/database setup, migration startup, backup/restore commands, and explicit lack of production readiness/managed retention.
- `docs/DEVELOPMENT_GUIDE.md` — single RPC configuration and operations guidance.
- `docs/M4_1_2A_NETWORK_IDENTITY_PLAN.md` — approved identity policies, fingerprint/context design, stages, and migration sequence.
- `src/orbis/config.py`, `src/orbis/cli.py`, `src/orbis/db_migrate.py`, `src/orbis/observer/postgres.py` — current configuration, automatic migration path, same-DSN migration entry point, and chain-only registry writer.
- `migrations/001_initial.sql` — `networks.chain_id UNIQUE` and dependent internal-ID keys.
- `migrations/009_m4_rule_evaluation.sql`, `010_m4_integrity_guards.sql`, `011_m4_terminal_failures.sql`, `012_m4_lifecycle_hardening.sql` — M4 evaluation guards and invalidation audit scope.
- Repository-wide filename/search inspection for deployment artifacts, PostgreSQL grants/roles, identity audit, retention, and backup configuration.

No `.env` content, database state, credentials, or production configuration were inspected. No migrations, tests, database writes, source edits, commits, pushes, or deployments were performed. Workspace changes for this task are limited to this closure document and consistency corrections in the existing M4.1.2A planning document; all pre-existing modifications and untracked files were preserved.
