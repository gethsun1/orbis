# ORBIS M4.1.2A — Network Identity and Selection Plan

**Status:** Planning only; no implementation is authorized here.
**Repository state audited:** branch `main`, commit `163a97dddebeee57aa894009c7333dcf180dd0fe`.
**Scope:** Safe representation and selection of networks that share an EVM chain ID but have different genesis hashes. This is a prerequisite to M4.1.2; it does not implement evaluation identity or finding identity changes, or D-01–D-06 evaluators.

## 1. Executive summary

The PostgreSQL schema already uses the internal `network_id` to scope blocks, transactions, receipts, logs, checkpoints, knowledge, evidence, and evaluations. The unsafe boundary is how application operations obtain that ID: the registry and several runtime entry points resolve by `chain_id` alone. `networks.chain_id` is currently unique, so the ambiguity is hidden. Removing that constraint by itself would turn currently single-row lookups and writes into ambiguous or arbitrary selections.

Adopt a verified, immutable runtime `NetworkContext` containing chain ID, normalized genesis hash, fingerprint scheme, derived portable fingerprint, and (after exact registry resolution) internal `network_id`. Build it from the selected RPC endpoint by fetching `eth_chainId` and block zero, validating both, and deriving the fingerprint locally. Do not accept caller-supplied fingerprints as proof. All database operations that select a network must receive this context or its resolved internal ID; none may resolve on chain ID alone.

For PostgreSQL, add nullable identity columns to `networks`, retain all existing IDs and dependent rows, and add uniqueness for `(chain_id, fingerprint_scheme, network_fingerprint)`. Existing rows must remain explicitly unresolved until an operator obtains verified genesis information from the intended network. Do not guess or rewrite IDs. New fingerprint-aware operations fail closed for unresolved rows. The migration can therefore be additive and data-preserving without pretending historical records have an identity they never stored.

**Readiness conclusion:** the approved policies for unresolved historical rows and SQLite are settled in §13. The plan identifies deployment controls still to close in `M4_1_2A_DEPLOYMENT_READINESS_CLOSURE.md`. The current registry writer depends on `ON CONFLICT(chain_id)`, so the registry migration cannot ship independently or before compatible A+B runtime code under a write gate. Documenting the path does not make deployment ready.

## 2. Current architecture and root cause

### Verified repository facts

- `Settings` has one `rpc_url` and one `chain_id`, loaded from `ORBIS_RPC_URL` and `ORBIS_CHAIN_ID`. It has no network profile or genesis identity.
- `Indexer.verify_network()` checks configured chain ID against `eth_chainId`, then reads head height. It never fetches block zero.
- `PostgresStore._network_id(chain_id)` inserts/upserts into `networks` with `ON CONFLICT(chain_id)` and returns that row's ID. Direct callers can invoke `commit_block()` without RPC verification.
- `checkpoint()`, `block_hash()`, `rollback_from()`, and `count()` select through `networks.chain_id`; `rollback_from()` uses `fetchone()` after a chain-only query.
- `KnowledgeService._network(chain_id)` uses `SELECT network_id FROM networks WHERE chain_id=%s` followed by `fetchone()`. Knowledge APIs route through it.
- Evaluation persistence is predominantly scoped by `network_id`. However, the evidence envelope carries only `network_chain_id`; `EvaluationRepository._verify_request()` checks the chain ID, and `EvaluationService.identity()` calls v1 identity with chain ID only. This is relevant to M4.1.2 but does not turn the database surrogate into portable identity.
- PostgreSQL blocks, transactions, receipts, logs and checkpoints use `network_id` keys/FKs. Knowledge and M4 tables likewise use network-scoped keys and foreign keys. These relationships are the data-preservation boundary and should remain intact.
- SQLite `SqliteStore` is not just an alternate connection: its tables, primary keys, checkpoints, and operations are keyed by `chain_id`. It has no registry or genesis data. Two networks with the same chain ID cannot be isolated there.
- Current tests use direct `_network_id(chain_id)` calls and chain-ID-only methods, and PostgreSQL fixtures query `networks` by chain ID. These assumptions must be migrated with the runtime API.

### Root cause

The code treats the EVM-reported chain ID as a globally unique network key. It is only metadata shared by distinct networks in the scenario this milestone addresses. PostgreSQL's `UNIQUE(chain_id)` currently enforces the assumption at registration. Once relaxed, `fetchone()` on these selectors is not a selection policy: it either returns an arbitrary match, raises due to an unexpected multi-row result, or makes a write target unclear. Changing the constraint without changing the runtime selection contract is unsafe.

## 3. Complete network-selector inventory

“Required change” below means the selector used by a runtime operation, not every appropriately network-scoped SQL expression after the ID has already been established.

| Component | Current selector | Database scope | Required change | Risk |
|---|---|---|---|---|
| `PostgresStore._network_id` registry upsert | `chain_id`; `ON CONFLICT(chain_id)`; `fetchone()` | Creates/updates one `networks` row; its ID scopes all later ingest writes | Replace with exact fingerprint tuple resolution from verified `NetworkContext`; make identity fields immutable after registration | Wrong network can be merged into an existing row; metadata may be updated on the wrong registry entry |
| `PostgresStore.commit_block` | Calls `_network_id(chain_id)` | Blocks, transactions, receipts, logs, checkpoint are correctly scoped by returned `network_id` | Accept resolved context/ID; do not perform implicit registry selection inside persistence | Same chain ID can route incoming block data to the wrong network |
| `PostgresStore.checkpoint` | Join to `networks` on `n.chain_id`; `fetchone()` | Checkpoint itself is keyed by internal `network_id` | Select using exact context or `network_id` | Can resume from another same-ID network's height/hash |
| `PostgresStore.block_hash` | Join to `networks` on `chain_id`; `fetchone()` | Blocks keyed by `(network_id, hash/number)` | Select by context/ID | Common-ancestor discovery may compare against the wrong chain |
| `PostgresStore.rollback_from` | `SELECT network_id FROM networks WHERE chain_id=%s`; `fetchone()` | All suffix cleanup is scoped by selected `network_id`; M4 invalidation is in the same transaction | Require exact context/ID before entering the transaction; retain atomic invalidation and cleanup | Wrong-chain deletion, evidence retraction and evaluation invalidation |
| `PostgresStore.count` | Join to `networks` on `chain_id`; `fetchone()` | Counts source rows by selected network | Require exact context/ID; keep table allowlist | Misleading counts or arbitrary row scope |
| `KnowledgeService._network` | `SELECT network_id … WHERE chain_id`; `fetchone()` | Returned ID scopes entities, observations, relationships, evidence and enrichment ledger | Accept a `NetworkContext` (or resolved ID at internal layer); remove chain-only resolver | Writes/retrieval/enrichment can cross network identity boundary |
| `KnowledgeService.resolve_entity`, `ingest`, status and retrieval APIs | Public argument is `chain_id`, then `_network()` | SQL after resolver is network-ID scoped | Propagate context through entity resolution, nested ingestion, history, and paged retrieval | Nested helper calls may accidentally re-resolve from chain ID even if outer method selected correctly |
| `Indexer` startup / `sync` | Configured chain ID; verifies only RPC `eth_chainId` | Passes chain ID to every store operation | Verify chain ID and genesis hash from selected endpoint; resolve context before reading checkpoint; carry same context through sync/reorg/commit | A same-ID endpoint can attach to a different registry row/checkpoint |
| `EvaluationService.identity` | `chain_id` only; `orbis-evaluation-v1` | Portable key excludes DB ID; DB uniqueness is `(network_id,evaluation_key)` | M4.1.2 v2 input receives validated fingerprint and scheme; preserve v1 reader and historical rows | Different same-ID networks can produce equal portable v1 keys across installations |
| `EvaluationRepository._verify_request` | Resolves by exact `network_id`, then checks envelope `network_chain_id` only | Evidence sources are canonical blocks by `network_id`; evaluations/evidence/findings are network-scoped | Check fingerprint/scheme in context, envelope, and registry row; keep internal ID as tenant/FK scope | Chain-ID match alone cannot establish that envelope/source identity matches the selected network |
| `ContextRepository` and repository get/create methods | Caller supplies `network_id` | All context, evaluation, finding, and evidence SQL is correctly network-scoped | Keep ID-based private repository scope, but only obtain ID from verified context; public boundary must not accept an unverified ID as identity proof | An upstream caller can pass a valid ID without demonstrating endpoint identity |
| `SqliteStore` checkpoint/hash/write/rollback/count | `chain_id` is both identity and table key | SQLite schema is entirely chain-ID scoped | Preserve single-network local/fixture operation and reject multi-network configuration; no SQLite redesign in this milestone | Same-ID networks cannot be isolated; explicit rejection prevents ambiguous use |
| Tests and fixtures | `_network_id(chain_id)`, store methods with integer chain ID, `WHERE chain_id=…` | PostgreSQL fixture rows and SQLite test records | Convert production-facing tests to verified contexts; direct SQL lookups in tests use captured `network_id` or full fingerprint; preserve explicit legacy compatibility tests | Tests can continue to codify chain-ID uniqueness or conceal arbitrary selectors |

### Selector search result

Repository-wide source search found runtime chain-only selectors in `src/orbis/observer/postgres.py` (`_network_id`, checkpoint, block hash, rollback, count), `src/orbis/knowledge.py` (`_network`), and the chain-ID keyed SQLite implementation in `src/orbis/observer/store.py`. `src/orbis/rules/repository.py` selects a network by `network_id`, which is correct internally, but validates only its chain ID against the v1 envelope. Other network-scoped query paths in knowledge, context, and rule repositories use the resolved `network_id` and do not independently resolve by chain ID.

The chain-only selectors that currently pair with `fetchone()` are PostgreSQL `_network_id`'s insert/upsert, `checkpoint`, `block_hash`, `rollback_from`, `count`, and `KnowledgeService._network`. The insert path is the most consequential because it creates the mapping; the other selectors would become ambiguous after relaxing uniqueness. `fetchone()` calls for schema migration state, per-row inserts, source records, evaluations, rules, and checkpoints already scoped by network ID are not chain-only network selectors.

## 4. Proposed network identity contract

### A. Chain ID

The positive EVM integer returned by the selected RPC endpoint's `eth_chainId`, also compared with the explicitly configured expected chain ID. It is useful metadata and part of the fingerprint input, but is not a globally unique network identifier. Reject booleans/non-integers at Python boundaries and reject non-positive values unless the project explicitly decides to support them.

### B. Portable fingerprint

Initial scheme: `evm-genesis-sha256-v1`.

1. Fetch block zero (`eth_getBlockByNumber("0x0", false or true)`) from the configured RPC endpoint during network verification.
2. Require a syntactically valid 32-byte hexadecimal genesis hash (`0x` followed by 64 hex digits); normalize to lowercase. Missing, null, malformed, or wrong-height genesis data fails closed for new fingerprint-aware operations.
3. Form the canonical object `{"chain_id": <integer>, "genesis_hash": "0x<lowercase 64 hex>"}`.
4. Serialize with deterministic UTF-8 JSON: sorted object keys, compact separators, no non-finite values; this matches the repository canonical JSON rules. Hash those bytes with SHA-256 and represent the digest as `sha256:<64 lowercase hex>`.
5. Record the scheme separately. The registry uniqueness key is `(chain_id, fingerprint_scheme, network_fingerprint)`. The scheme is not inferred from the hash string and future schemes require explicit versioning.

Do not accept a request-provided fingerprint as evidence. Construct it only after querying and validating the configured RPC. If RPC chain ID differs from the configured ID, or genesis differs from a previously resolved registry identity for that selected profile, abort before any persistence/retrieval/rollback action.

**Known limitation:** two deliberately distinct networks that share both chain ID and genesis hash are indistinguishable under this scheme. Supporting them requires a future governed identity extension with an agreed authority, provenance, validation and migration policy; do not add display name/provider name as an implicit identity workaround.

### C. Internal database ID

`network_id` remains the database-local surrogate, FK target, and scope for every data table and transaction. It is not portable, must not enter evaluation identity v2, and must never be treated as proof that a configured RPC is the same network. The registry maps a validated fingerprint tuple to exactly one preserved `network_id`.

## 5. Runtime propagation design

An immutable frozen `NetworkContext` is appropriate and proportionate: this identity crosses RPC verification, the indexer, and multiple repositories, and a bag of unrelated integers/strings permits accidental partial identity. Put it in a small network identity module (or next to the RPC/network boundary if that fits package conventions). Suggested fields:

```text
chain_id: int
genesis_hash: normalized 32-byte hex
fingerprint_scheme: "evm-genesis-sha256-v1"
network_fingerprint: "sha256:<hex>"
network_id: int | None  # None only before exact registry resolution
```

Construct the pre-registration context through a factory that derives the fingerprint from validated RPC values; do not expose an initializer that encourages caller-supplied fingerprint trust. Registry resolution returns a new context (or an immutable resolved wrapper) with the `network_id` set. Validate consistency at boundaries and keep identity fields immutable.

Propagation sequence:

1. **RPC initialization and verification:** create `RpcClient` for explicitly selected endpoint; fetch chain ID and block zero; validate formats and expected chain ID; derive fingerprint. Do this before any store selection or mutation.
2. **Registry:** resolve by exact `(chain_id, scheme, fingerprint)`. On an existing row verify all identity columns agree. On a new row insert the tuple and metadata atomically. Descriptive name/environment/provider can update under documented policy, but identity columns cannot. Return resolved context.
3. **Ingestion:** `Indexer` owns one resolved context for the full `sync`; no method re-derives it from chain ID. Context is passed to checkpoint/hash/commit/rollback and result metadata.
4. **Block, transaction, receipt and log persistence:** `commit_block(context, ...)` requires `context.network_id`; all existing SQL continues to use that ID. A separate persistence primitive accepting a raw chain ID should not remain as a production path.
5. **Checkpoint operations:** `checkpoint(context)` and `block_hash(context, number)` resolve/read only through context ID. Checkpoint independence follows from its existing primary key `network_id`.
6. **Knowledge:** public service calls receive explicit context (or an explicit selected-network handle that contains it). Internal helpers accept the already-resolved context/ID to avoid nested re-resolution. All SQL remains `network_id` scoped.
7. **Rules/evidence:** evaluation orchestration gets the context; v2 evaluation identity and evidence envelope carry chain ID, scheme, fingerprint. Repository resolves/validates those fields against the registry row by context's internal ID. Context/block/finding queries keep network ID as DB scope. Historical v1 records remain readable using their historical schema and identity semantics.
8. **Reorg and rollback:** indexer detects mismatches using that same context and calls `rollback_from(context, height)`. Invalidation, knowledge cleanup, block deletion and checkpoint repair remain one transaction and use only the selected `network_id`.
9. **Replay/restart:** startup reconstructs and verifies context from RPC every process run, resolves the exact registry row, then reads only its checkpoint. Do not infer a context from whichever checkpoint happens to exist for the configured chain ID.

### Signature impact

The following integer `chain_id` inputs should become a context or explicitly selected network reference: `Indexer`; `ObserverStore` protocol methods `checkpoint`, `block_hash`, `commit_block`, `rollback_from`; PostgreSQL equivalents and `count`; `KnowledgeService` network-facing methods; and `EvaluationService.identity`/evaluation orchestration. Repository methods that operate entirely inside a transaction with a resolved `network_id` can remain ID-scoped private APIs, with verified context validation at the service boundary. This is a source-level API change for internal callers and tests. Keep compatibility only through an explicit deprecated single-network adapter that itself requires a verified context; never preserve a chain-ID-only fallback once same-ID networks are supported.

## 6. Configuration compatibility strategy

Current configuration and CLI represent exactly one RPC URL/chain ID pair. Preserve that path as the default single-network form: legacy `ORBIS_RPC_URL` and `ORBIS_CHAIN_ID` produce one selected profile, now augmented by runtime genesis verification. Existing `ORBIS_START_BLOCK`, database, confirmations, timeout, retries, and batch settings remain usable.

For multi-network deployments, add an explicit profile collection and selection rather than changing singular variables' meaning. A minimal first step is an optional structured `ORBIS_NETWORKS_JSON` (each profile has a stable local selection name, RPC URL, expected chain ID, and existing per-network descriptive metadata), plus a required explicit `ORBIS_NETWORK` selector when the collection has more than one entry. If both profile collection and legacy singular settings are present, define deterministic validation/error behavior; never silently merge conflicting values. Keep secrets in environment injection/secret management and do not log URLs. The CLI can initially run one selected network per process; multiple workers/processes can ingest separate selected profiles concurrently against one PostgreSQL DB, each with independent context and checkpoint. An all-networks scheduler, dynamic endpoint failover, profile reload, and API-level selection/authentication are future work, not prerequisites.

The context is the runtime selection token for internal/API callers: callers choose a configured profile by explicit local name, then the program derives and validates the portable identity. A caller cannot select a network by raw chain ID when more than one configured profile matches it.

SQLite currently keys data by chain ID and cannot safely support same-ID profiles. Approved policy is to keep SQLite supported for single-network local development and fixtures, reject multi-network configuration whenever SQLite is selected, preserve existing single-network behavior, and exclude a SQLite schema redesign from this milestone.

## 7. Database migration design

Add a new forward-only migration; do not modify migration 001 or drop/recreate `networks`. Proposed shape (names to be finalized in migration review):

- Add nullable `genesis_hash`, `fingerprint_scheme`, and `network_fingerprint` columns. Nullability is necessary during safe migration of historical rows; do not fabricate values or assign a guessed identity.
- Add format checks for non-null genesis hash and digest/scheme values. Ensure either all three identity fields are null (legacy unresolved) or all are non-null (fingerprinted); reject partially populated tuples.
- Drop only the existing unique constraint/index on `networks.chain_id` after checking its actual catalog name and dependencies. Preserve `network_id`, all metadata, and every dependent FK.
- Add unique constraint/index on `(chain_id, fingerprint_scheme, network_fingerprint)`. PostgreSQL permits multiple null tuples in a normal unique constraint, so unresolved legacy rows can coexist temporarily. Add a partial index if needed to make that intent explicit and document exact behavior.
- Add a non-unique `chain_id` index if operational query needs justify it; runtime identity lookup uses the composite unique key, not this index.
- Keep every dependent table FK on `network_id`; do not change its primary keys or migrate child rows to portable fingerprints.
- Consider an explicit `identity_status`/provenance column only if operationally needed. It must distinguish verified v1 identity from legacy unresolved and must not make a false cryptographic claim. Avoid adding a second source of truth when null identity columns suffice.

This preserves old IDs and all current FK relationships. The registry lookup is exact on all three identity tuple fields. Same chain ID with different genesis yields different fingerprints and separate registry rows. Same chain ID plus same genesis maps to the same identity under this scheme, subject to the limitation above.

### Safe backfill

1. Apply the additive schema only in the coordinated maintenance window in §13, with network writes gated and compatible A+B code prepared. Do not remove the old conflict constraint while an old writer can run, and do not enable same-ID registration before compatible selectors are active.
2. Inventory existing `networks` rows by `network_id`, chain ID, creation/environment/name/provider metadata, and associated data counts. Do not expose credentials or infer genesis from latest indexed blocks.
3. For each unresolved row, an operator explicitly selects the intended configured RPC profile and verifies its `eth_chainId` equals the row's chain ID and obtains a valid genesis hash. Record the operator/profile/provenance in an operational backfill record or reviewed audit log; the resulting database value is the locally derived fingerprint, not a supplied token.
4. Update identity columns on that same existing `network_id` only when the association is unambiguous. Never delete/recreate the row, move child rows, merge rows, or assign a fingerprint based on name/provider.
5. If no trusted RPC can be associated, leave the row null/unresolved. All normal network-dependent runtime operations fail closed until resolved. Historical rows remain in place and may be inspected only by an explicitly supplied existing `network_id`.
6. If operator evidence indicates existing data may represent more than one same-ID network already mixed into one historical row, stop backfill for that row. No safe automatic split exists because child data may be interleaved and the current schema has only one registry entry. Require an owner-led recovery decision/reindex from verified source; do not attempt an inferred split.

An unresolved row does not block the additive schema migration and does not receive an invented hash. Under the approved policy in §13, it cannot participate in runtime operations until verified backfill succeeds.

## 8. Data-preservation and migration safety

- Preserve every `network_id`; `IDENTITY` sequence values need not be reset or renumbered.
- Preserve all M1–M3/M4 table rows and their FK links. Existing child FKs already point to `networks(network_id)`, so removing chain-ID uniqueness does not require child-table rewrites.
- Keep the existing `network_id` constraints, unique keys, and network-scoped lookup indexes in source tables unchanged.
- Make registry identity columns write-once after they are established; a correction requires an explicit reviewed migration/repair procedure, never an ordinary upsert.
- Deploy as a coordinated sequence: verified backup/recovery, write gate, compatible A+B runtime/schema change in one window, selector checks, verified backfill, PostgreSQL acceptance tests, fingerprint-aware enablement, then ingestion restart. Rollback must use compatible fingerprint-aware code or keep writes disabled; never restore chain-only selection.
- Take and verify a database backup before production migration and rehearse both empty-schema install and populated upgrade. Do not apply this migration as part of this audit.

## 9. Test matrix

All persistence/isolation acceptance tests must run against actual PostgreSQL with isolated test schemas or disposable databases and real migration application. Mocks may cover RPC response validation but are not proof of PostgreSQL selector or FK behavior.

| Area | Concrete acceptance test |
|---|---|
| Same chain ID, distinct genesis | Register two contexts with equal chain ID and different valid genesis hashes; PostgreSQL creates two rows with distinct `network_id` values and unique fingerprint tuples |
| Exact resolution | Resolve each context repeatedly/concurrently and prove it returns its own stable `network_id`; duplicate same-fingerprint registration converges on one row |
| RPC chain mismatch | Configured chain ID differs from `eth_chainId`; fail before registry mutation, checkpoint read, or block write |
| RPC genesis mismatch | Endpoint identity does not match already selected/registered profile; fail before persistence/retrieval/rollback |
| Genesis validation | Missing block zero/hash, wrong block number, malformed width/prefix/non-hex hash all fail closed; no registry row is inserted |
| Checkpoint isolation | Write different heights/hashes for both contexts; each restart reads only its own checkpoint |
| Block and knowledge isolation | Persist blocks, transactions and enrichment for both same-ID networks; entity, observation, relationship, evidence, status, and history retrieval return only selected context data |
| Rule evaluation/evidence isolation | Persist evaluations/evidence for each context; same chain ID does not allow envelope from network A to validate under network B; retrieval by context and ID remains isolated |
| Rollback isolation | Roll back a suffix for A and assert B's blocks, checkpoint, knowledge, evaluations, findings and invalidation audit are unchanged |
| Reorg/replay/restart | Trigger reorg on A, restart both indexers, replay A, and prove B's checkpoint and canonical records are unchanged |
| Concurrency | Run two indexers/services concurrently for same-ID distinct fingerprints; assert exact registry rows, commits, and checkpoints; no chain-only query or cross-context mutation |
| Single-network regression | Legacy singular environment configuration selects one profile, verifies genesis, and preserves expected startup/resume semantics |
| Existing data preservation | Upgrade populated M1–M4 fixture; compare every `network_id`, row count/key set, and FK relationship before/after; unresolved rows remain null and unchanged |
| No selector regression | Static/source-level guard or SQL trace assertion rejects runtime `WHERE chain_id` network selection and chain-only `fetchone()`; allow legitimate metadata validation and test-only SQL where explicitly noted |
| SQLite boundary | Multi-profile selection is rejected for SQLite; existing one-profile local/fixture behavior remains covered |

## 10. M4.1.2 integration requirements

The pending [M4.1.2 implementation plan](M4_1_2_IMPLEMENTATION_PLAN.md) already recommends a genesis-derived portable fingerprint for evaluation identity v2, retaining v1 records, immutable evidence envelopes, evidence-aware finding v2, coverage enforcement, and atomic rollback invalidation. This plan supplies the necessary network selection and persistence prerequisites; it does not implement those changes.

Required revisions to that plan:

1. Make M4.1.2A a hard predecessor: its current “network identity component” must produce a verified `NetworkContext` and resolved DB ID; it must not be described as a standalone fingerprint lookup while storage still resolves by chain ID.
2. Specify the exact fingerprint input serialization and hash output from §4 here, rather than leaving “canonical JSON” implicit. Include the `fingerprint_scheme` with the digest in v2 identity and envelope.
3. Ensure `EvaluationService.identity()` receives the resolved context and emits portable v2 identity from chain ID + scheme + fingerprint. Never hash `network_id`. Keep v1 identity and historical envelope readers unchanged for v1 records.
4. Extend immutable evidence envelopes with portable network metadata. `EvaluationRepository._verify_request()` must compare envelope chain ID, scheme and fingerprint to the exact registry row selected by `network_id`, in addition to canonical source block checks.
5. Keep evaluation/evidence/finding tables and unique constraints internally scoped by `network_id`. Portable evaluation identity does not replace DB scope. Preserve immutable snapshots so later source rollback can invalidate the evaluation atomically while retaining evidence.
6. Keep `PostgresStore.rollback_from()`'s single transaction and invalidation-before-source-deletion ordering. Change only how it gets its selected network ID; it must receive the same verified context used for reorg detection. Include same-chain/different-genesis rollback isolation in M4.1.2's test prerequisites.
7. Distinguish historical v1 rows with no fingerprint from new v2 rows. Do not backfill v1 evaluation keys or rewrite old evidence/envelopes from current RPC identity; such attribution is not historically proven.
8. Update rollout sequence: network schema/runtime/backfill and PostgreSQL selector tests first; then evaluation metadata/envelope migration and v2 readers; only then enable v2 writes. Existing coverage and finding-key decisions remain as specified in M4.1.2 and its owner decisions; this audit does not approve unresolved choices in that plan.

## 11. Approved policies, remaining risks and acceptance criteria

### Remaining risks and implementation prerequisites

- **Approved policy — unresolved legacy operation:** no chain-ID-only runtime operation. Unresolved rows are preserved but excluded from ingestion, checkpoint selection, knowledge, evaluation and rollback. Administrative inspection is by explicit existing `network_id`. Backfill requires verified RPC identity and auditable association; ambiguous history is quarantined for explicit recovery.
- **Approved policy — SQLite:** single-network local development/fixtures only; reject multi-network configuration; preserve current single-network behavior; no SQLite redesign in this milestone.
- **Deployment blockers:** role/grant ownership, audit owner/retention, acceptable historical RPC-to-row evidence, and maintenance/rollback rehearsal remain open. Track owners and closure evidence in [M4_1_2A_DEPLOYMENT_READINESS_CLOSURE.md](M4_1_2A_DEPLOYMENT_READINESS_CLOSURE.md).
- **Configuration implementation detail:** define profile schema, size limits and precedence/error behavior for `ORBIS_NETWORKS_JSON` versus legacy singular variables. Profile ID is local tracing metadata, not portable identity.
- **Fingerprint limitation:** same chain ID and genesis hash are a collision at the identity-model level for deliberately cloned networks; governance is needed before any extension.
- **API compatibility:** context-based signatures are source incompatible with tests and internal callers that pass integers. Provide a deliberate transition, not a permissive ambiguous overload.
- **Concurrency:** registry insert-or-select and backfill need transaction/locking review; identity fields must not race with ordinary metadata updates.

### Acceptance criteria

1. Every runtime path listed in §3 selects one configured network from a verified context and no persistence/retrieval/checkpoint/rollback path resolves on chain ID alone.
2. Same-chain-ID/different-genesis PostgreSQL rows resolve to distinct preserved internal IDs; same fingerprint tuple resolves deterministically to one ID.
3. The migration is additive, preserves all existing IDs, rows, and FK links, leaves unverifiable rows unresolved, and does not invent or silently assign genesis identity.
4. Ingestion, knowledge, rule evidence, checkpoints, reorg rollback, replay, restart, and concurrent operation are isolated, demonstrated with PostgreSQL tests.
5. Single-network configuration remains explicit and functional after runtime genesis verification; multi-network mode requires named selection; SQLite capability is accurately bounded.
6. M4.1.2 uses fingerprint for portable evaluation identity v2, retains historical v1 semantics, and keeps database IDs as internal scope only.

## 12. Recommended implementation order

1. Implement the approved policies in §13 and close deployment blockers in [M4_1_2A_DEPLOYMENT_READINESS_CLOSURE.md](M4_1_2A_DEPLOYMENT_READINESS_CLOSURE.md) before production migration.
2. Add unit-level fingerprint parsing/canonicalization validation and `NetworkContext` construction from verified RPC responses.
3. Design and review the forward-only additive registry migration, catalog constraint-drop identification, unique tuple, consistency checks, and pre/post-upgrade preservation queries.
4. Add explicit configuration profiles and selected-profile validation while preserving singular environment configuration.
5. Change registry resolution and all PostgreSQL store/indexer selectors to require resolved context; preserve transaction and rollback ordering.
6. Propagate context through knowledge enrichment/retrieval and rule/evidence service boundaries; update envelopes and evaluation identity only in the separately authorized M4.1.2 implementation.
7. Execute operator-assisted backfill for verified existing rows; leave unresolved/ambiguous records unchanged and disabled for new context-dependent operations.
8. Add and run PostgreSQL same-ID isolation, migration-preservation, concurrent operation, rollback/replay, rule/evidence, and regression tests; separately exercise SQLite's declared single-profile behavior.
9. Enable multiple configured same-ID networks only after all runtime selectors and tests pass; update operating/configuration docs and M4.1.2 plan sequencing.

## 13. Implementation Readiness and Approved Owner Decisions

This section is planning policy, not implementation authorization.

### Approved owner decisions

- **Historical unresolved rows:** preserve their existing `network_id` and dependent data; permit no chain-ID-only runtime operation. Unresolved rows cannot enter ingestion, checkpoint selection, knowledge, evaluation or rollback. Backfill requires verified RPC identity and an auditable operator association. Ambiguous rows remain quarantined for an explicit recovery decision. Administrative inspection may use only an explicitly supplied existing `network_id`.
- **SQLite:** support single-network local development and fixtures; reject multi-network configuration when SQLite is selected; preserve current single-network behavior; do not redesign SQLite in M4.1.2A/B.
- **A+B deployment:** keep A (identity foundation/registry) and B (runtime propagation/isolation) as separate engineering workstreams but release them together under a maintenance window. The migration must never ship independently or ahead of compatible runtime code.
- **M4.1.2C:** evaluation identity v2, evidence envelope and finding identity integration remain downstream; historical v1 rows are not retroactively attributed.

### Deployment and migration sequence

**Preparation:** implement and review A identity construction/registry functions and B context-aware selectors; rehearse fresh and populated migrations in disposable PostgreSQL; test role grants, triggers, audit, evidence and recovery; verify the backup restore; and approve the runbook. Do not remove the current `UNIQUE(chain_id)` constraint during preparation.

**Controlled maintenance window:** (1) take and verify backup/recovery; (2) stop and fence all network-dependent writers; (3) apply the reviewed migration with the separate migrator role and deploy/start compatible A+B code with writes disabled; (4) verify schema, version compatibility, and all selectors while writes remain gated; (5) backfill only accepted historical rows; (6) run migration and cross-network acceptance tests in isolated schemas/disposable databases and read-only production invariant checks; (7) enable fingerprint-aware operations; (8) resume ingestion by explicit profile and confirm independent checkpoints.

No old writer may execute after removal of the conflict constraint it requires. If deployment is interrupted, keep writes gated and either complete the compatible rollout or restore the pre-change state only when no migration/backfill/new writes make that unsafe. After fingerprint-aware writes resume, prefer a compatible forward fix; restoring a pre-change backup requires explicit accounting for post-backup data loss. Never roll back to chain-ID-only selection or routinely re-add `UNIQUE(chain_id)`.

### NetworkContext trust states

1. **Unverified:** configuration/profile has loaded, but RPC identity has not. No network-dependent database operation is allowed.
2. **Verified but unresolved:** trusted verifier has queried the selected RPC's `eth_chainId` and block zero, validated configured chain ID, block number zero and 32-byte genesis hash, normalized the hash, and derived the fingerprint locally. Only exact registry lookup/registration and non-persistent diagnostics are permitted.
3. **Resolved:** exact registry lookup/registration matched `(chain_id, fingerprint_scheme, network_fingerprint)` and confirmed the stored genesis tuple. This state carries the existing `network_id` and is required for persistence, retrieval, knowledge, evaluation, checkpoint, rollback, replay and restart. Only verifier/resolver factories create trusted states; arbitrary fingerprint and `network_id` arguments cannot establish trust. A local profile ID may support logs, metrics and traceability but is not portable identity or proof.

### Frozen fingerprint bytes and vectors

For `evm-genesis-sha256-v1`, serialize exactly `{"chain_id":<positive JSON integer>,"genesis_hash":"0x<64 lowercase hex>"}` as sorted-key compact UTF-8 JSON, with no non-finite values, extra properties, or trailing newline. Hash those exact bytes with SHA-256; represent the result as `sha256:` plus 64 lowercase hex digits. Scheme remains separately stored.

| Chain ID | Input hash | Normalized hash | Exact canonical UTF-8 bytes | SHA-256 hex | Fingerprint |
|---:|---|---|---|---|---|
| 1 | `0x0000000000000000000000000000000000000000000000000000000000000000` | `0x0000000000000000000000000000000000000000000000000000000000000000` | `{"chain_id":1,"genesis_hash":"0x0000000000000000000000000000000000000000000000000000000000000000"}` | `22017b203407838f9fe2101dcc049d475cbbe06de31271d96daa0248766c2d2b` | `sha256:22017b203407838f9fe2101dcc049d475cbbe06de31271d96daa0248766c2d2b` |
| 1874 | `0xABABABABABABABABABABABABABABABABABABABABABABABABABABABABABABABAB` | `0xabababababababababababababababababababababababababababababababab` | `{"chain_id":1874,"genesis_hash":"0xabababababababababababababababababababababababababababababababab"}` | `2857c5f6e4afba63c90bdc4c9bd1bf86dae54ad9b5b6778c6a7ba8a6b9572923` | `sha256:2857c5f6e4afba63c90bdc4c9bd1bf86dae54ad9b5b6778c6a7ba8a6b9572923` |

These vectors were independently calculated using Python 3 (`json.dumps`/`hashlib`) and Node.js (`JSON.stringify`/`crypto`); both produced identical canonical bytes and digests.

The role/grant matrix, identity audit ownership and retention, evidence classification, maintenance rehearsal and recovery checklist are specified in [M4_1_2A_DEPLOYMENT_READINESS_CLOSURE.md](M4_1_2A_DEPLOYMENT_READINESS_CLOSURE.md). Until those blockers are closed, this plan does not declare production migration readiness.

**Audit boundary:** this document records architecture facts, approved policies and proposed design. It does not authorize source changes, migrations, database access, tests, or deployment.
