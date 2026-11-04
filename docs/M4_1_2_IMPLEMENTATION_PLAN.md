# ORBIS M4.1.2 — Evaluation Integrity Hardening Plan

**Status:** Planning only; no code or migration changes are authorized by this document.
**Baseline:** M4.1 implementation, [verification report](M4_1_VERIFICATION_REPORT.md), [final audit](M4_1_FINAL_AUDIT.md), [M4 specification](M4_SPECIFICATION.md), and owner decisions in [M4.2 Rule Decisions](M4_2_RULE_DECISIONS.md).
**Scope:** Harden evaluation identity, rule-aware coverage, finding identity, and adjacent integrity guarantees before M4.2 evaluators are implemented. This milestone does not implement D-01–D-06.

## 1. Executive recommendation

**Ready only after owner decisions.** The changes are additive and can preserve the M4.1 transaction/reorg model, but the owner must approve a canonical network fingerprint policy and the versioned finding-key compatibility approach before new persistence contracts are relied on. The D-01/D-02 semantic decisions in `M4_2_RULE_DECISIONS.md` remain separate prerequisites for evaluator work; M4.1.2 must not decide them implicitly.

This plan introduces no rule evaluators and does not rewrite historical identities. Existing v1 evaluations and findings remain readable and immutable. New evaluations use identity v2 only after the migration and service rollout are complete.

## 2. Audit findings and source locations

The final audit is the point-in-time summary; the following code locations were inspected to ground it:

| Finding | Current implementation | Consequence |
|---|---|---|
| Portable identity omits canonical network identity | `src/orbis/rules/identity.py:evaluation_identity` hashes `orbis-evaluation-v1` and `network.chain_id`; `network_id` is correctly excluded. `migrations/009_m4_rule_evaluation.sql` has `UNIQUE(network_id,evaluation_key)`. | Same chain ID and all other equal inputs can produce the same v1 key across separate installations. Local uniqueness does not disambiguate independent installations. |
| Coverage policy is not independently enforced | `src/orbis/rules/registry.py` stores immutable `coverage_requirements`; `src/orbis/rules/service.py:persist_result` calls `gate_outcome`; `src/orbis/rules/repository.py:create` only checks caller-supplied `coverage.insufficient_dimensions`. | A caller can omit a required dimension or supply coverage inconsistent with the immutable rule version or envelope. The current negative-result gate can then accept an unsupported `not_matched`. |
| Finding default identity excludes evidence | `src/orbis/rules/identity.py:finding_identity(result)` hashes only result; `src/orbis/rules/repository.py:create` accepts caller `finding_key` or derives it from result and inserts under `(network_id,evaluation_id,finding_key)`. | Equal result payloads backed by distinct source evidence can collide within one evaluation. Caller-specific keys do not establish evidence inclusion. |
| Evidence source identity validation is incomplete | `src/orbis/rules/evidence.py:make_item` checks nonnegative block/log indexes and requires a transaction hash for logs, then lowercases hashes. | Malformed widths/prefixes, non-hex values, uppercase `0X`, invalid chain/hash types, and noncanonical input structures can enter the digest. |
| Evidence projections are write-flow checked, not independently database-checked | `make_envelope`/`verify_envelope` validate item/envelope/context digests; repository writes `evaluation_evidence` rows. `migrations/009`–`012` guard projection immutability but do not compare all projection values back to JSONB. | Direct or faulty writes could make query projection disagree with immutable envelope while both remain stored. Retrieval verifies the envelope digest, not full JSONB-to-child agreement. |
| Lifecycle and failure test gaps | `migrations/009` and `012` protect rule definition fields; registry has staged/active/retired operations. `record_failure` persists terminal failed rows and append-only attempts; `011` guards terminal fields. | PostgreSQL mutation/delete and lifecycle-transition behavior lacks focused tests. A duplicate failed key returns the existing row and does not retry; that contract is not directly tested. |
| Range/limit and concurrency coverage is incomplete | `src/orbis/rules/context.py` bounds retrieval; repository uses conflict-safe evaluation creation. Existing PostgreSQL tests cover concurrent duplicate negative evaluations and rollback atomicity. | Add explicit admission limits, duplicate-failure semantics, finding concurrency, and create-vs-rollback tests before relying on all cases. |

Additional audit observations: failures have null analytical outcome, but their diagnostic coverage is caller-provided; `make_item` expects normalized values from callers; M4.1 PostgreSQL tests cover evaluation creation concurrency and rollback failure atomicity, but not every lifecycle guard. See `M4_1_FINAL_AUDIT.md` for the fuller guarantee matrix and exact test run.

## 3. Proposed architecture and data flow

Keep the existing modular-monolith boundary: network/RPC adapter obtains chain identity; a network identity service validates it against configured/indexed canonical data; bounded context retrieval returns canonical source records and coverage; evaluation orchestration loads the immutable rule version, assesses coverage against that version, runs an evaluator only when its policy permits, constructs the immutable envelope, computes identity v2 and evidence-aware finding keys, then persists through the existing repository using the same PostgreSQL connection and transaction discipline.

The repository remains a final application-integrity boundary. It must independently load the referenced immutable rule version and re-check identity algorithm, required dimensions, outcome/coverage consistency, envelope agreement, evidence-to-finding membership, and bounds before inserts. PostgreSQL constraints/triggers protect durable invariants that can be expressed without duplicating complex canonical JSON logic. No UI/API validation is a sufficient enforcement boundary.

Network metadata lookup must not become a separate durability domain. A validated fingerprint is included in the envelope and evaluation metadata before evaluation persistence. Source-block locks and rollback ordering described in §9 remain authoritative.

## 4. Remediation A — network identity v2

### 4.1 Canonical v2 key contract

Keep the v1 function and serialization semantics available for historical interpretation. Introduce a separately named v2 contract:

```json
{
  "algorithm": "orbis-evaluation-v2",
  "network": {
    "chain_id": 1874,
    "fingerprint_scheme": "evm-genesis-sha256-v1",
    "fingerprint": "sha256:<64-lowercase-hex>"
  },
  "subject": {"kind": "address", "key": "<normalized>"},
  "rule_version": {"rule_id": "...", "semantic_version": "...", "definition_digest": "..."},
  "bounds": {"from": 1, "to": 10},
  "parameters": {},
  "context_digest": "...",
  "evaluator_build": "..."
}
```

The key is `sha256:` plus SHA-256 over UTF-8 canonical JSON using the repository canonicalizer: sorted object keys, compact separators, rejected non-finite numbers, normalized scalar encodings, and schema-aware set ordering. Never include database-local `network_id`, row IDs, provider names, or mutable display names. The network fingerprint is the SHA-256 digest of canonical JSON for `{"chain_id": <validated integer>, "genesis_hash": "0x<64 lowercase hex>"}`; the scheme name is part of the identity object so any later scheme requires a new algorithm/scheme version. Genesis hash is normalized to lowercase `0x` plus exactly 64 hex digits. Chain ID must be a positive integer obtained from validated network metadata, with booleans rejected as integers.

The fingerprint, scheme, chain ID, and algorithm string are persisted in evaluation metadata and the immutable evidence envelope. A stored v2 evaluation must have exact agreement among key input, row metadata, envelope metadata, and network row chain ID. A database-local surrogate remains the tenant/FK boundary only.

### 4.2 Validation and unavailable identity behavior

Do not accept a free-form fingerprint from an evaluator request. A network identity component obtains the configured endpoint's chain ID and genesis block hash, validates formats, and compares the chain ID with the configured/indexed `networks.chain_id`. Where the indexed chain has genesis data, compare the endpoint's genesis hash to it. Cache only validated values with explicit provenance and refresh rules; the immutable evaluation records the resolved fingerprint and validation source/time. RPC responses are untrusted and failures are explicit.

If genesis is unavailable, inconsistent, or malformed, do not fall back silently to chain ID. Block new v2 evaluation creation for that network and report identity unavailable. An alternative canonical fingerprint (for example an owner-governed network registry identifier) requires a separately approved scheme, issuer/provenance, uniqueness governance, and lifecycle before use. This plan does not select that fallback.

### 4.3 Migration, rollout, and rollback

Add nullable `identity_algorithm`, `network_fingerprint_scheme`, and `network_fingerprint` metadata to evaluations (or a normalized immutable identity metadata table if schema review prefers it); retain all existing v1 columns and keys. Backfill existing rows as `orbis-evaluation-v1` with fingerprint unavailable/NULL; do not infer genesis identity retroactively and do not recompute keys. Add consistency constraints for new v2 rows after compatibility analysis. Update envelope schema/version additively so old envelopes remain verifiable by the v1 verifier and new envelopes require fingerprint metadata.

Deploy in phases: (1) additive migration and readers recognizing v1/v2; (2) network identity resolver and v2 write path behind a required capability; (3) enable v2 writes only when resolver validation passes; (4) make v2 mandatory for new evaluations. Reads continue to select verifier by stored algorithm/schema. Rollback means rolling application code back only to a reader that understands the new schema or first disabling v2 writes; never downgrade schema destructively, erase v2 metadata, or reissue v1 identities. A database restore retains both historical v1 and new v2 rows.

Required tests: same chain ID/different genesis hashes produce distinct keys; identical canonical network/input tuples produce equal keys in independent installations; mismatch between configured chain ID and RPC identity is rejected; missing/malformed genesis prevents writes; v1 retrieval remains digest-verifiable after migration; v2 metadata/envelope/key mismatch is rejected.

## 5. Remediation B — rule-aware coverage enforcement

### 5.1 Contract semantics

Each immutable rule version declares a validated, nonempty-or-explicitly-empty policy for mandatory dimensions and whether `not_applicable` is permitted per dimension. The policy schema is itself versioned and covered by the existing definition digest. Coverage states mean:

| State | Meaning |
|---|---|
| `complete` | Required data for this dimension was examined and reconciled over the declared bounds/context. |
| `partial` | Some required data was unavailable, unsupported, malformed, or omitted. |
| `unknown` | The assessor cannot establish completeness or incompleteness. |
| `not_applicable` | The dimension does not apply under the immutable rule contract and has an explicit reason. |

Missing mandatory dimensions are synthesized as `unknown` by the assessor; they never default to complete. Optional dimensions may be recorded but cannot satisfy a mandatory dimension by alias. `insufficient_dimensions` is recomputed, not trusted. A definitive `not_matched` requires every mandatory dimension to be complete or explicitly permitted not-applicable. A positive `matched` may be retained if its positive evidence is valid, but the result must carry the coverage assessment and must not imply a complete scan; policy may instead require `insufficient_coverage` where the rule contract says positives cannot be concluded under gaps. This distinction must be explicit per rule policy.

The evaluation row's coverage JSON must be byte/canonical-value equivalent to envelope coverage under canonical JSON, and envelope coverage must contain the recomputed assessment, required dimensions, state and policy digest. Repository validation compares both and obtains policy from the immutable rule-version row. The database can enforce JSONB equality between evaluation coverage and envelope coverage and outcome/state consistency; the service/repository recomputes policy semantics.

Execution failure remains `execution_status=failed`, `analytical_outcome=NULL`. It may preserve diagnostic coverage as observations of data acquisition, but that field must be marked `diagnostic_only` and never be interpreted as a completed analytical sufficiency decision. A failed attempt is not `insufficient_coverage` unless execution completed and the assessment itself determined that outcome. Retry policy remains terminal identity semantics (see §8.2).

### 5.2 Enforcement location and D-01/D-02 examples

The assessor is a deterministic service taking the immutable rule policy, requested bounds/context, and observed dimension facts. Orchestration invokes it before outcome gating. The repository re-fetches the rule version and independently recomputes/validates the supplied assessment before persistence. Database checks enforce structural invariants and row/envelope equality; a trigger need not reimplement coverage policy parsing if repository writes are the only supported boundary and DB privileges are restricted accordingly.

Examples only, with no evaluator implementation:

- **D-01:** mandatory dimensions could include contiguous canonical blocks/hashes, complete transactions and successful receipts, relevant native-transfer or token-transfer log coverage, and token metadata for token mode. If token logs are partially decoded, a zero-findings scan becomes `insufficient_coverage`; a verified positive may be stored only with partial coverage clearly attached and according to the approved D-01 policy.
- **D-02:** mandatory dimensions could include canonical block/log completeness, exact transaction/block/log-index provenance, supported ERC-20 `Transfer` decoder validation, removed-log handling, and emitter allowlist applicability. Unsupported/malformed candidate logs prevent `not_matched`; they do not become negative observations. No D-01/D-02 policy is finalized here; bind exact dimensions after owner decisions in `M4_2_RULE_DECISIONS.md`.

Tests: omitted mandatory dimension becomes unknown; partial/unknown prevent a negative result; allowed versus forbidden `not_applicable`; tampered `insufficient_dimensions` rejected; mismatched envelope/row coverage rejected; altered rule policy digest rejected; successful matched behavior follows explicit positive-under-gap policy; failed diagnostics stay separate and cannot be retrieved as analytical coverage.

## 6. Remediation C — evidence-aware finding identity

### 6.1 Canonical identity

Define `orbis-finding-v2` as a digest over a canonical object with `evaluation_key` (or stable portable evaluation identity), stable rule ID/version/definition digest, canonical result payload, the sorted set of canonical evidence identities, and an optional rule-specific extension object:

```json
{
  "algorithm": "orbis-finding-v2",
  "evaluation_key": "sha256:...",
  "rule_version": {"rule_id": "...", "semantic_version": "...", "definition_digest": "..."},
  "result": {},
  "evidence": ["sha256:<item evidence digest>", "sha256:<item evidence digest>"],
  "extension": {}
}
```

Each evidence identity is the validated canonical item identity/digest, which includes chain fingerprint, block number/hash, transaction hash, nullable exact log index, source kind, normalized consumed input, evidence schema and digest algorithm. De-duplicate identical evidence IDs, sort lexicographically by canonical digest, then serialize and hash. A finding supported by any different evidence item therefore gets a distinct key. Identical result + identical evidence + same evaluation/rule version/extension deterministically deduplicates within that evaluation, including concurrent attempts. The same match under a different evaluation remains a separate finding because it belongs to a separate immutable assessment.

Rule-specific extensions may refine identity (for example a normalized match key) but cannot replace or omit repository-required evidence identities. Repository computes the final identity from persisted evaluation/rule linkage, result, and evidence IDs; callers may supply only the extension, never an arbitrary complete key. PostgreSQL uniqueness remains authoritative.

### 6.2 Compatibility

Preserve existing v1 finding keys and rows as immutable historical identities. Add `finding_identity_algorithm` and retain legacy `finding_key`; new finding inserts use v2. Keep v1 retrieval/display independent of new key derivation; never mass-rekey, delete, or merge historical findings. Migration adds nullable metadata, labels existing rows v1, and introduces a compatible uniqueness strategy for v2. Validate finding evidence links reference evidence items inside that evaluation's immutable envelope/projection. Migration must support any pre-existing findings lacking finding_evidence rows by retaining their original identity without fabricating provenance.

Tests: same result/different evidence yields different IDs; same result/same evidence order permutations yield equal IDs; duplicate evidence input canonicalizes to one identity; cross-process/installation determinism; concurrent identical finding writes yield one row; existing v1 findings retrieve with unchanged key; extension cannot weaken evidence inclusion; child links cannot point outside evaluation evidence.

## 7. Remediation D — additional integrity gaps

| Gap | Planned correction and enforcement boundary | Required tests |
|---|---|---|
| Rule-version mutation/deletion | Keep PostgreSQL trigger as authoritative immutable-definition guard. Allow only lifecycle columns/transitions explicitly enumerated by trigger; disallow delete. Validate transition graph and lifecycle metadata in registry and database trigger. | PostgreSQL attempts to mutate every definition field and delete; permitted staged→active→retired transitions; reject reverse/skip transitions; activation/retirement metadata checks. |
| Duplicate terminal failure/retry | Document current identity as terminal: duplicate key returns existing failed row and appends no new attempt; it never promotes to completed. If retry is needed, it must be an explicit new attempt/identity design with owner-approved semantics, not implicit duplicate replay. Keep attempt ledger append-only. | Concurrent duplicate failures return one evaluation; attempt count/diagnostics unchanged on duplicate; retry through any future explicit contract creates auditable distinct attempt without changing terminal row. |
| Evidence item validation | Validate integer chain/block/log fields excluding bool; nonnegative bounds; `0x` + exact hex widths for EVM block/transaction hashes; canonical lower-case; required tx hash for logs; exact source-kind enum and mapping schema; recursively canonical JSON-compatible normalized input. Validate chain ID/fingerprint against resolved identity. | Malformed hash widths/chars/prefix/case, wrong types, invalid indexes, and noncanonical values reject; normalization fixtures have stable digest. |
| Envelope/projection agreement | Verify envelope digest and every child projection in repository transaction; add DB constraints/triggers only for durable high-value checks feasible in SQL (row/evidence envelope coverage equality, required fields, immutable rows). Prefer one canonical projection builder to prevent drift. Consider storing item ordinal + digest and deriving query identity fields from envelope at insertion. | Deliberate projection mismatch rejected; direct SQL inconsistent insert/update rejected where DB boundary promises it; historical snapshots still retrievable after source deletion. |
| Failed evaluation coverage | Store failure diagnostics under explicitly named diagnostic coverage field or include classification in coverage JSON; do not run analytical gate or label failure coverage sufficient/insufficient. Keep null outcome and attempt append-only semantics. | Failed evaluation cannot have analytical outcome; diagnostics remain retrievable and cannot be mistaken for coverage conclusion; failed identity duplicate behavior tested. |
| Bounded ranges and evidence item caps | Enforce `from <= to`, max inclusive span, max evidence items, max serialized envelope bytes, and per-item payload size before RPC retrieval and again before persistence. Limits should be configurable by service policy but versioned/recorded in evaluation metadata so reproducibility is possible. Oversize requests fail before partial evaluation writes with explicit diagnostic. | Boundary and over-limit unit/PG tests; empty-range policy; high-volume stress fixture within documented limits; ensure truncation never reports complete coverage. |
| Concurrent evaluation/finding persistence | Retain unique `(network_id,evaluation_key)` plus `ON CONFLICT`; add finding v2 unique key. Source locks and rollback transaction ordering stay intact. Require evaluation creation to hold source block locks through commit, and lock evaluation/evidence rows consistently when findings persist. | Concurrent same and distinct evaluation/finding races; same-network duplicate convergence; cross-network isolation; concurrent evaluation versus rollback yields either committed active evaluation later invalidated, or rejected/retried creation, with no active evaluation depending on deleted blocks. |

For item-level relational constraints and lifecycle transitions, combine application validation with database constraints/triggers where direct SQL must be protected. Avoid a trigger that reimplements SHA-256 canonical JSON in PostgreSQL unless a proven SQL canonicalization implementation exists; that would create two competing canonicalizers. Repository is the trusted boundary for cryptographic verification, while database immutability, FKs, uniqueness, enum/check constraints, and transaction atomicity protect persisted state.

## 8. Migration and compatibility design

Plan a new forward-only migration after 012. It should add nullable v2 metadata, envelope schema support, finding identity algorithm metadata, and targeted checks/indexes without changing existing values. Backfill only algorithm labels that are provable from current code/schema (`v1`); do not synthesize missing fingerprints or evidence identities. Add constraints as `NOT VALID` where practical, validate after application compatibility is deployed, then require v2 for new writes at the repository/service boundary and finally via database constraints if reliable algorithm-version signaling is available.

Migration review must include fresh installs and upgrades from a populated M4.1 database. Rollback is application rollback with writes disabled, retaining additive schema and all rows. No destructive down migration is planned. Readers dispatch by identity/envelope schema version and preserve old records. Failure of v2 network identity resolution must fail closed for new evaluations while v1 historical retrieval remains available.

## 9. Transaction and reorg preservation

Do not change `PostgresStore.rollback_from` transaction scope or bypass `_invalidate_m4_for_suffix`. It must continue resolving the network and locking the exact orphaned `(number, hash)` suffix, invalidating dependent active evaluations and appending audit rows before source cleanup/deletion, then repairing checkpoint in the same transaction. Evidence snapshots/projections remain independent of deleted source-table FKs. The current evaluation writer's source-block locks must remain held through evaluation insertion/commit so rollback cannot delete source evidence between validation and persistence.

Fingerprint metadata does not replace `network_id` isolation. All evaluation, evidence and finding links stay network-scoped. Replacement evaluations retain same-network/same-rule/same-subject linkage to an invalidated predecessor; v2 makes changed canonical context/network identity produce a distinct key. M1–M3 rollback and ingestion behavior must remain unchanged.

Add a two-session PostgreSQL race test coordinating evaluation creation and suffix rollback. Accept only serializable outcomes: a committed evaluation is invalidated atomically with audit before orphan deletion, or creation observes missing/noncanonical source and does not persist as active. Verify audit and retained envelope survive; inject rollback failure and confirm all M4/M1–M3 updates roll back together.

## 10. Sequenced implementation tasks

1. **Owner contract approval:** choose genesis-based fingerprint as canonical scheme or approve a governed alternative; approve fail-closed unavailable-genesis policy; approve v2 finding identity and legacy compatibility. Keep D-01/D-02 rule semantics in their separate decision record.
2. **Schema and migration review:** specify additive evaluation/envelope/finding metadata, constraints, indexes, and backfill labels; rehearse fresh and populated upgrades.
3. **Network identity component:** implement RPC/configured identity resolution, genesis validation, provenance, cache invalidation rules, and failure behavior.
4. **Identity v2 and envelope versioning:** add versioned canonical identity functions and readers; add portable network metadata into immutable snapshots; retain v1 read path.
5. **Coverage policy evaluator:** formalize immutable rule policy schema, assessor recomputation, explicit NA policy, outcome gating, and diagnostic-only failed coverage.
6. **Evidence canonicalization and finding v2:** validate source identity and normalized payloads, canonicalize evidence sets, derive final keys in repository, and preserve v1 rows.
7. **Repository/DB integrity:** verify envelope/projection and row/envelope consistency transactionally; add only reviewed constraints/triggers; preserve append-only and unique semantics.
8. **Concurrency/reorg hardening:** add evaluation-versus-rollback race and concurrent finding tests; inspect lock order and deadlock behavior; retain existing transaction hook.
9. **Regression and rollout:** run M1–M3 plus M4 suites on fresh schema and upgrade fixture; enable v2 writes only after v2 reader deployment and network identity validation; document operational rollback by disabling writes.

## 11. Test matrix and acceptance criteria

### Unit tests

- Canonical v2 evaluation object/digest fixtures; same network/input cross-process identity; same chain ID/different genesis differs; invalid chain/genesis rejected.
- v1 identity and envelope retrieval fixtures remain unchanged.
- Coverage policy requires every declared dimension; omitted means unknown; all four states and `not_applicable` policy; outcome gate and failed diagnostics semantics.
- Evidence normalization/validation and digest stability, plus finding evidence ordering/deduplication and extension behavior.
- Range, item-count, payload-size and envelope-size boundaries.

### PostgreSQL tests

- Fresh migration and populated M4.1 upgrade preserve keys, rows, evidence retrieval and constraints.
- Rule definition mutation/delete and lifecycle transitions guarded.
- Evaluation row/envelope coverage and network fingerprint agreement; projection inconsistency rejected.
- Duplicate terminal failure remains terminal and appends no retry attempt.
- Finding v2 uniqueness and evidence membership constraints; legacy v1 finding retrieval.
- Two distinct network fingerprints sharing chain ID tested across independent test schemas/installations; same canonical network/input produces same key across those installations.
- Historical v1 retrieval after source deletion and v2 retrieval after source deletion.

### Concurrency and regression tests

- Concurrent identical evaluations (positive, negative, and failed) converge under unique identity with documented terminal behavior.
- Concurrent identical findings converge; distinct evidence never collides.
- Evaluation-versus-rollback race preserves atomic invalidation/audit and never leaves active evaluations referencing deleted canonical source.
- Existing rollback injected failure still rolls back both M4 and M1–M3 changes.
- Run the full preexisting observer, RPC, M1–M3 and M4.1 regression suite. Tests should assert no D-01/D-02 evaluators were introduced by M4.1.2.

### Acceptance criteria

1. New evaluations cannot be persisted without validated v2 network identity after rollout; v1 rows and keys remain unchanged and retrievable.
2. Coverage is recomputed from immutable rule policy at orchestration and repository boundaries; incomplete mandatory coverage cannot produce a definitive negative; row and envelope agree.
3. Findings derive identity from canonical evidence plus result and rule/evaluation identity; distinct evidence cannot collide; identical inputs deduplicate deterministically.
4. The specified lifecycle, failure, validation, projection, boundedness, concurrency and reorg tests pass on PostgreSQL, with existing M1–M3 behavior preserved.
5. Upgrade and operational rollback procedures are documented and additive; no historical rows are rewritten.
6. No D-01–D-06 evaluator or external interface is included.

## 12. Risks, unresolved decisions, and approvals

- **Owner approval required:** confirm genesis hash plus chain ID as the sole initial canonical fingerprint scheme; approve fail-closed behavior when it cannot be fetched/validated. If an alternative identifier is needed, define governance and provenance before coding.
- **Owner approval required:** approve `orbis-finding-v2` composition and whether finding identity includes portable evaluation key (recommended) versus only rule/result/evidence. It should include evaluation identity to keep scope explicit.
- **Owner decision required:** choose range, evidence-item, per-item payload, and envelope byte ceilings based on expected bounded workloads; defaults must be explicit and recorded.
- **Owner decision required:** determine whether a positive finding with incomplete unrelated coverage may be persisted as `matched` with partial coverage, or must be classified `insufficient_coverage`; rule policies must resolve this before evaluator activation.
- **Schema review required:** select JSONB equality check versus normalized coverage columns, and decide how much projection agreement PostgreSQL itself must enforce. Avoid divergent JSON canonicalization implementations.
- **Operational risk:** unavailable or inconsistent genesis RPC identity will stop new evaluations; monitoring and operator remediation procedures are needed.
- **Historical limitation:** v1 records cannot be retroactively assigned trustworthy fingerprints or evidence-aware finding keys; they remain labeled v1 and may be ambiguous across independent installations.
- **Separate M4.2 gates:** D-01 threshold governance and D-02 boundary/coverage decisions remain open in `M4_2_RULE_DECISIONS.md`; M4.1.2 must not close them by implementation defaults.

No source files, migrations, `.env`, dependencies, or live-validation data are changed by this plan. No existing evaluation/finding is rewritten or deleted.

## 13. Readiness conclusion

**Ready only after owner decisions.** M4.1.2 has a compatible implementation path and no architectural conflict with M4.1 rollback, evidence retention, replacement linkage, network isolation, or M1–M3 behavior. Begin implementation after the fingerprint and finding identity contracts, failure behavior, workload limits, and coverage-on-positive policy are approved. D-01/D-02 evaluators remain gated by their separate owner decisions.
