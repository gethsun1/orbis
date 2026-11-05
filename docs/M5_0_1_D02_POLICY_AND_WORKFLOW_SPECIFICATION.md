# ORBIS M5.0.1 — D-02 Policy Closure and Functional Workflow Specification

**Status:** Implementation specification with explicit owner approval gates; no D-02 policy is treated as approved merely because it was proposed in an earlier brief.
**Date:** 4 November 2026
**Scope:** Whitechain Sepolia (chain ID 1874), one bounded, deterministic D-02 workflow. This document does not implement the workflow.

## 1. Executive summary

The existing approved rule contract defines D-02 as detection of ERC-20-shaped `Transfer(address,address,uint256)` logs whose `from` or `to` endpoint is the zero address. It specifies ABI shape validation, exact log identity, and that findings describe observed event evidence rather than intent or verified supply change. `docs/M4_2_RULE_DECISIONS.md` leaves the emitter support policy and several boundary/coverage choices explicitly open. Those remain owner decisions and must be resolved before a deployable D-02 version is activated.

The recommended first workflow reuses the verified `NetworkContext`, PostgreSQL observer, canonical block/transaction/receipt/log tables, and M4 rules persistence. A single process performs identity verification, bounded sync, complete-range checks, deterministic event decoding, evaluation persistence, and read-only reporting. The observer already commits blocks and checkpoints atomically and handles restart/idempotency and reorganization rollback. No new worker, broker, service, or database schema is indicated for this bounded demonstration.

No HTTP API or frontend exists in this repository. The first acceptance surface should be the existing operator CLI extended with a structured report. If a browser demonstration is required, add a thin read-only API and small operator UI after its contract below is agreed; do not fabricate dashboard data.

## 2. D-02 decision register

The canonical proposed semantics are in `docs/M4_SPECIFICATION.md` §3 and `docs/M4_2_RULE_DECISIONS.md` §D-02. The latter labels its table “Owner decisions required.” “Recommended” below means a technical recommendation for owner review, not an approved default.

| ID | Exact question | Existing evidence / prior decision | Alternatives | Recommendation | Technical consequence | Security / correctness implication | Owner approval? |
|---|---|---|---|---|---|---|---|
| D02-P01 | Which emitters are in scope: every indexed log emitter, or only an approved token allowlist/registry? | M4.2 says matching signature alone does not establish ERC-20 behavior. M3 classifies log emitters as contracts, not as verified tokens. | All emitters with standard-shaped logs; explicitly configured token allowlist/registry; another governed token-verification process. | **Owner decision required.** For the smallest safe first release, use an explicit immutable emitter allowlist, possibly containing only fixture emitters until owner supplies live token addresses. | Scope is part of immutable rule definition/parameters and evaluation identity. Coverage must distinguish in-scope emitters from out-of-scope emitters. | Prevents arbitrary contracts from being described as tokens or unsupported logs from silently becoming a complete negative. | **Yes** |
| D02-P02 | Do zero-amount mint/burn-shaped events count as findings? | Proposed M4.2 default counts by endpoint shape; amount is retained as evidence, not thresholded. No approval is recorded. | Count all valid endpoint events; exclude amount zero; define another threshold. | Recommend count: D-02 is event classification; no amount threshold is specified. | Decoder retains canonical decimal amount; predicate depends on endpoints only. | Avoids inventing a materiality threshold; finding wording must say event observed, not supply changed. | **Yes** |
| D02-P03 | Are both-zero `from` and `to` endpoints unsupported/malformed rather than a mint or burn? | M4.2 proposes unsupported; M4 spec classifies only one-sided zero endpoint events. | Unsupported; classify as mint; classify as burn; separate category. | Recommend unsupported with a coverage diagnostic, never a finding. | Increments unsupported/malformed count and may gate outcome per D02-P06. | Avoids asserting direction where neither side identifies a one-sided endpoint. | **Yes** |
| D02-P04 | How should removed or reorg-marked logs affect active findings and evaluation coverage? | Observer performs canonical suffix rollback; M4 stores evaluation invalidation audit. M4.2 proposes removed logs excluded from active positives. | Exclude and invalidate/replay; retain active; treat as partial without invalidation. | Recommend exclude from active canonical inputs; rollback atomically invalidates dependent evaluation/findings; re-evaluate replacement canonical range. | Must preserve invalidated historical evidence/audit and assign a distinct evaluation identity to changed canonical inputs. | Prevents orphaned fork observations being presented as current canonical findings. | **Yes** |
| D02-P05 | What result/diagnostic treatment applies to malformed or unsupported layouts and emitters? | M4.2 proposes partial/unknown decoder coverage; malformed items are not negative matches and do not produce findings. | Fail whole execution; complete with diagnostics; partial/unknown; ignore. | Recommend retain bounded source identities and diagnostics, produce no finding for invalid item, and mark mandatory coverage unresolved when it can hide an in-scope event. | Diagnostics and counts enter coverage and immutable envelope; avoid storing unbounded raw error text. | An invalid item must never be interpreted as evidence of absence. | **Yes** |
| D02-P06 | What indexed history is considered available, and when do missing/pruned receipts or logs make a result insufficient? | M4.2 requires complete requested range, canonical blocks, transaction/receipt-log provenance; bounded scans do not imply chain-wide coverage. Observer has bounded indexing/checkpoints, not an archive guarantee. | Requested indexed range only; require live RPC re-fetch; allow receipt gaps; define archive-provider guarantee. | Recommend claim only the explicit requested range; require continuous canonical block manifest and complete transaction/receipt/log provenance for all transactions in that range. Missing provenance means `insufficient_coverage`. | Range manifest and expected/observed counts drive coverage; avoid implying historical completeness outside indexed interval. | Prevents false `not_matched` from pruned or missing sources. | **Yes** |
| D02-P07 | Should each qualifying event produce one finding per exact log, or aggregate/collapse by transaction or token? | M4.2 proposes one finding per qualifying log; exact `(fingerprint, block hash, tx hash, log index)` evidence identity; no contrary decision found. | Per log; per transaction; aggregate by token/range. | Recommend per exact qualifying log. | Stable finding key includes fingerprint, block hash, transaction hash, log index and rule version; repeated event in a transaction stays distinct. | Avoids dropped events and makes each finding directly reproducible. | **Yes** |
| D02-T01 | Which topic/data encodings qualify as a standard-shaped Transfer log? | M4.2 specifies topic0 hash, exactly two 32-byte indexed addresses with zero padding, exactly one 32-byte uint256 data word; canonical provenance. | Use the stated exact ABI contract; permissive decoding; additional proxy/token checks. | Adopt exact stated decoder contract as the implementation interpretation. | Pure decoder validates topic count/width, signature, address padding, data width, canonical log identity and integer representation. | Strict parsing avoids malformed event-shaped data being promoted to a detection. | No separate approval if the existing M4 rule contract is accepted; record any change as policy approval. |
| D02-T02 | What can a finding claim about the event? | M4 says positive findings do not establish intent, fraud, maliciousness, ownership or verified supply change. D-021 prohibits inferred ownership. | Event observation only; stronger verified-token/supply claim under added policy. | State only that a standard-shaped event from the declared emitter scope encoded a zero-address endpoint. | Finding classification `mint` or `burn` is the event endpoint classification; no unsupported severity. | Avoids converting ABI shape into claims about implementation behavior/economic effect. | No, constrained by approved existing policy. |

### 2.1 Owner decision request

Before activating D-02, please explicitly approve or amend: **(1)** emitter scope (prefer an initial explicit allowlist), **(2)** whether zero-amount events count (recommend count), **(3)** both-zero handling (recommend unsupported), **(4)** removed/reorg handling (recommend invalidate and replay canonical inputs), **(5)** malformed/unsupported coverage behavior (recommend unresolved mandatory coverage yields `insufficient_coverage`), **(6)** range completeness requirements (recommend complete canonical blocks and all transaction receipt/log provenance within the declared range), and **(7)** one finding per qualifying log (recommend exact log granularity). Until these choices are recorded, the deployable D-02 rule version remains staged. The proposed decoder shape and claim limits above come from the existing M4 contract and can be implemented without adding detection semantics.

## 3. Approved or recommended detection semantics

The following event shape and classification are specified by M4; they are not a claim that an emitter is a verified ERC-20 implementation:

- Signature: `Transfer(address,address,uint256)`, topic0 `0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef`.
- Exactly three topics: topic0 plus two 32-byte address words; the leading 12 bytes of each indexed address word must be zero.
- Data is exactly one 32-byte unsigned ABI word.
- Mint-shaped: zero `from`, nonzero `to`. Burn-shaped: nonzero `from`, zero `to`. Neither zero: ordinary transfer and no D-02 finding. Both zero or malformed encoding: unsupported, not a finding.
- The emitter is part of the event evidence and scope decision. Event amount is unsigned raw token units; do not compare it across tokens or infer decimals/fiat value.
- Candidate detection class is `mint` or `burn`; **severity is unspecified** and must not be invented. Display the rule classification without severity until an approved severity policy exists.
- A finding asserts only that a validated event-shaped log from the configured scope encodes the corresponding endpoint. It does not establish actual token supply change, intent, fraud, maliciousness, or ownership.

Only D02-P01–P07 need owner choice to make the currently proposed boundaries deployable. If owner changes any stated M4 semantics, version a new immutable rule definition rather than silently editing an active version.

## 4. End-to-end workflow specification

### 4.1 Network identity and onboarding

1. Operator configures an explicit Whitechain Sepolia RPC URL and profile metadata. Do not check in or silently fall back to a provider URL.
2. `RpcClient` reads `eth_chainId` and genesis block hash. Require chain ID 1874 and derive the canonical fingerprint locally using the existing fingerprint scheme.
3. Resolve/register only the exact `(chain_id, fingerprint scheme, fingerprint)` tuple through the PostgreSQL network registry. Construct a trusted `NetworkContext` carrying the resolved internal `network_id`.
4. Before any persistence, evaluation, or retrieval, require trusted context and exact registry match. Reject wrong chain, changed genesis, malformed fingerprint, unresolved registry identity, or mismatched stored tuple. Never fall back to chain-ID-only lookup. SQLite remains a single-profile observer fixture and is not an evaluation persistence target.
5. Report configured profile, chain ID, genesis hash/fingerprint, resolved network identity, RPC head and verification time. Do not expose endpoint credentials.

### 4.2 Observation and checkpoints

1. The operator supplies an explicit inclusive `from_block`/`to_block` or uses the existing bounded sync policy to a chosen safe head. The report records the exact bounds and confirmation-depth policy. The first MVP is an operator-triggered bounded run, not an always-on daemon.
2. Reuse `Indexer` and the PostgreSQL observer to fetch blocks with complete transaction objects, receipts and receipt logs. Existing observer validation and per-block transaction/checkpoint commit are authoritative.
3. Advance checkpoint only with the atomic canonical block commit. Re-running the same range is idempotent. On restart, resume from the persisted checkpoint according to current indexer behavior; report requested range, actual processed range, checkpoint and counts.
4. Validate contiguous block numbers, parent/hash linkage, transaction/receipt correspondence, receipt status, and log provenance before declaring coverage. A failed RPC call or failed block commit does not advance the checkpoint; retry follows the existing bounded RPC retry behavior, then surfaces a failed run for operator retry.
5. Reconcile the saved checkpoint against the current canonical chain. Reuse existing common-ancestor rollback and replay. Rollback source rows and M4 invalidation must remain atomic as implemented. Re-evaluation of replacement canonical inputs creates a new identity; it never overwrites invalidated history.
6. No backfill, repair, or new finality mechanism is included. The indexed requested range is the claim boundary; the UI/CLI must not imply full-chain coverage.

### 4.3 Evidence contract

Each consumed D-02 log snapshot must be immutable and reproducible after source rollback/deletion. Required fields:

| Group | Required fields |
|---|---|
| Rule/run | rule ID `D-02`, immutable semantic version and definition digest, parameter digest/normalized emitter scope, evaluator build ID, decoder/schema version, evaluation bounds and context digest |
| Network | chain ID, fingerprint scheme, network fingerprint; internal `network_id` is DB scope only and not portable proof |
| Source identity | block number/hash, transaction hash, transaction index where known, exact log index, emitting address, canonicality at evaluation time |
| Raw log | topic0, full topics array, data, normalized lowercase address/hash hex; preserve exact normalized fields consumed |
| Decoded values | `from`, `to`, canonical base-10 `uint256` string, event class/result, validation result |
| Provenance | source kind (`canonical_receipt_log`), source block/transaction/receipt relationship, observed counts and coverage diagnostics; digest algorithm and evidence digest |

Raw source material plus normalized consumed values are retained in the evidence envelope, not just a digest. Do not attach restrictive foreign keys from retained M4 snapshots to source rows deleted by reorg rollback. Findings link to retained evidence by internal evidence reference and exact portable source identity. Retrieval must show invalidation/canonical status and preserve prior evidence for audit. Retention is at least the linked evaluation lifetime under the existing M4 rule; longer retention, archival, and retirement remain the separately documented owner decision in `docs/M4_SPECIFICATION.md` §9.

Reproducibility means a deterministic decoder and evaluator build can recompute the classification and outcome from the retained envelope, rule version, parameters, and coverage; it does not require current RPC availability.

### 4.4 Evaluation contract

- **Inputs:** trusted `NetworkContext`; explicit bounded range; exact indexed canonical manifest; transaction/receipt status and log provenance; immutable D-02 definition/version; approved emitter scope; decoder version/build; coverage policy.
- **Parameters:** required declared emitter scope (allowlist or the explicitly owner-approved alternative); no amount threshold, decimals conversion, fiat conversion, or additional contract heuristics. Policy decisions are embedded in immutable definition/parameter identity.
- **Trigger:** after successful bounded sync and complete source read for the range, operator invokes evaluation. New observations do not trigger a separate service; the composed command calls the evaluator after ingestion. Re-running a range is safe via deterministic identity.
- **Determinism:** pure decoder/evaluator over ordered canonical input. Stable order is block number, transaction index, log index. No wall-clock values or RPC fetches enter classification. Context digest includes canonical source identities, normalized consumed values and coverage.
- **Duplicate prevention:** fingerprint-aware evaluation identity using existing `EvaluationService.identity`; exact log finding uniqueness includes network scope, rule version and log identity. Confirm existing repository constraints support the exact key before deployment; never deduplicate by transaction hash alone.
- **Outcomes:** completed `matched` with one or more findings; completed `not_matched` with zero findings only when all required coverage is sufficient; completed `insufficient_coverage` when required source/decoder coverage is incomplete. Execution exceptions persist `failed` diagnostics without analytical outcome, using existing repository lifecycle. Do not synthesize negative findings.
- **Failure/retry:** transient observation errors retry using existing RPC retry; permanent sync/source validation errors stop evaluation. Evaluation persistence runs transactionally/idempotently. A retry with the same context returns/reuses the same evaluation; changed canonical inputs or policy/version produce a distinct identity. Persist bounded diagnostics and attempt history through existing M4 contracts.
- **No unsupported capabilities:** no D-01 threshold, token price, supply state, D-03/D-04 rules, AI-generated detections, or inferred ownership.

Coverage dimensions required for `not_matched`: exact requested range; contiguous canonical blocks/hashes; full transaction set; receipt for every transaction and valid receipt status; complete log provenance for those receipts; declared scope; all in-scope candidate `Transfer` logs either validated or treated according to owner-approved unsupported policy; no unresolved gaps. Coverage records expected/observed counts and gap/unsupported/malformed/removed counts. An out-of-scope emitter is not silently counted as scanned if policy requires allowlist-scoped coverage.

### 4.5 Finding contract

Each positive finding is one qualifying log (pending D02-P07 approval), with rule/version, classification (`mint`/`burn`), immutable evaluation reference, exact evidence reference, network fingerprint, block/hash, transaction hash, emitter, log index, decoded endpoints and amount, evaluator/decoder version, coverage summary, and canonical/invalidation status. Store an explanatory sentence limited to the encoded observation. Do not set severity absent an approved severity policy. Retrieval supports deterministic pagination/order and filters by range, class and active/invalidated status; every result remains network-context scoped and auditable. No fabricated findings or aggregate metrics.

## 5. Workflow orchestration architecture

Use a single-process command composition over current libraries:

```text
explicit settings
  → RpcClient verifies chain + genesis
  → PostgreSQL registry resolves trusted NetworkContext
  → Indexer syncs bounded range and advances checkpoint
  → ContextRepository loads canonical manifest/log provenance
  → pure D-02 decoder + coverage gate
  → EvaluationService / EvaluationRepository persist result and findings
  → structured run report / read-only query service
```

`Indexer` is the observation trigger; the bounded command is the workflow orchestrator. A post-sync evaluation call carries the same resolved `NetworkContext` object through all services. PostgreSQL remains source of truth. Reuse RPC retry, block-atomic checkpoints, reorg rollback/invalidation, rule registry, coverage gate, evidence envelope and evaluation repository. Do not add a broker, microservice, scheduler, new schema, or a frontend-specific persistence path. If continuous observation becomes a later requirement, it can repeatedly invoke the same idempotent bounded operation under a worker already justified by that requirement.

## 6. Minimum API contract

No HTTP framework, route set, OpenAPI definition, or API authorization mechanism was found. Therefore the first runnable demo should expose these records through a structured CLI output/query command; if M5 acceptance mandates browser access, implement a versioned read-only API over the same query service. API is local/operator-only until an auth mechanism and deployment boundary are explicitly selected. No endpoint may accept a caller-provided fingerprint as proof; it selects a configured profile resolved from verified RPC identity.

Proposed `GET /api/v1` read contract (all response data scoped to the selected trusted profile; pagination bounded):

| Endpoint | Response purpose |
|---|---|
| `GET /networks/{profile}/status` | Configured profile, chain ID, genesis/fingerprint, resolved status, RPC connectivity/head, verification timestamp. Secrets excluded. |
| `GET /networks/{profile}/observer` | Last run, requested/processed range, canonical checkpoint/hash, sync state, indexed counts, last error summary, freshness. |
| `GET /networks/{profile}/blocks?from=&to=&limit=&cursor=` | Recent canonical block number/hash/parent/timestamp and transaction/log counts. |
| `GET /networks/{profile}/transactions/{tx_hash}` | Relevant indexed transaction with block identity, status, and bounded logs/evidence references. |
| `GET /networks/{profile}/rules/D-02` | Rule metadata, immutable versions, staged/active status, decoder version, required approved parameters, and policy approval state. Never expose write/activation controls in read API. |
| `GET /networks/{profile}/evaluations?from=&to=&status=&cursor=` | Evaluation identity, rule version, bounds, execution status/outcome, coverage summary, timestamps and invalidation state. |
| `GET /networks/{profile}/findings?from=&to=&class=&state=&cursor=` | Paginated findings, class, source identities, evaluation reference, evidence reference, canonicality. |
| `GET /networks/{profile}/findings/{finding_id}/evidence` | Retained immutable envelope fields needed to explain and reproduce that finding, digest verification metadata, source provenance and invalidation audit. |

Use established SQL/repository conventions and response DTOs, not table-shaped dumps. Enforce profile resolution and authorization at the API boundary; cap page sizes and evidence payload sizes. API contract may not claim data not backed by persisted observer/rule records. This is a proposed minimal contract, not a claim that these endpoints already exist.

## 7. Frontend architecture recommendation

Repository inventory shows Python package/CLI and PostgreSQL migrations only: no web frontend, static app, JS/TS package, or HTTP API. Do not select or install a framework as part of this specification. For M5 MVP, extend the operator CLI first; it is the lowest-friction real-data presentation already present. If owner acceptance requires a browser, build a small read-only operator page against the API contract above, in the same deployment boundary and without a separate backend. Choose framework only after that requirement is confirmed and existing API conventions are established. Required views map to network identity/connection, observer checkpoint/recent blocks, rule/evaluation status, and findings/evidence. Empty results and unavailable coverage must display as such, never as invented metrics.

## 8. Implementation sequence

1. **Record owner policy decisions:** resolve D02-P01–P07 in `docs/DECISIONS.md` and create immutable rule definition inputs. Keep D-02 staged until then.
2. **Confirm exact identity/finding constraints:** verify current fingerprint-aware evaluation identity and exact log-level finding key/uniqueness behavior against M4 migrations and repository. Any required identity migration is separately scoped; no chain-only fallback.
3. **Pure decoder and fixtures:** implement the exact M4 ABI decoder and deterministic classifier. Fixtures cover valid mint/burn, ordinary transfer, malformed topics/data/padding, both-zero, zero amount, multiple logs in one tx, unsupported scope and removed/reorg case; fixtures are labeled synthetic.
4. **Coverage and range reader:** compose canonical manifest, transaction/receipt/log provenance, declared scope and coverage gate. A complete no-match is impossible if mandatory coverage is unresolved.
5. **Persistence composition:** call existing evaluation service/repository; retain snapshots, failure diagnostics, exact findings and idempotency; validate rollback invalidation/replay.
6. **Bounded operator workflow:** add command/subcommand to verify identity, sync range, evaluate, and emit structured report; no continuous service required.
7. **Read-only query/API and UI if required:** first add query DTO/service, then API routes; add minimal browser view only if acceptance requires it. Do not expose unauthenticated network data beyond a local/operator boundary.
8. **Acceptance rehearsal:** verify fixture end-to-end, restart/idempotency, incomplete coverage, failure/retry, reorg invalidation/replay, and one explicitly labeled bounded live Sepolia run if endpoint access is available.

## 9. M5 acceptance criteria

- Wrong-chain, wrong-genesis, unresolved, or mismatched registry identities are rejected before persistence/evaluation; all operations share a verified trusted context.
- Bounded observation reports exact range and durable checkpoint; restart repeats without duplicate canonical rows; reorg rollback invalidates affected results and replay creates a new canonical evaluation.
- D-02 decoder matches only the approved standard shape and approved emitter scope; classifications are deterministic, one per exact log if D02-P07 is approved, and claims stay within event evidence.
- Evaluations record immutable rule/evaluator identity, normalized parameters, portable network identity, range/context digest, coverage, execution status and reproducible evidence envelope.
- `not_matched` occurs only with sufficient complete coverage; missing receipt/log provenance or unresolved mandatory decoder coverage cannot be reported as a negative.
- Positive findings link to retrievable immutable evidence and exact network/block/transaction/log identities; no unsupported severity or fraudulent-intent language appears.
- Duplicate runs are idempotent; failed execution has diagnostics but no analytical outcome; retry does not duplicate work; reorg invalidation remains auditable.
- CLI/API/UI display only persisted real data, label fixture and bounded live data correctly, and show network/observer/rule/evaluation/findings/evidence state.
- No new broker, microservice, multi-network expansion, historical repair/backfill, production deployment infrastructure, AI detection, or chain-ID-only resolution is introduced.
- D-02 activation has a recorded owner approval for every approval-gated policy choice.

## 10. Reused components and blockers

**Reuse:** `RpcClient` and fingerprint verifier; `NetworkContext` and exact registry resolver; PostgreSQL `Indexer`/store, block/receipt/log persistence, checkpoint and reorg rollback; `KnowledgeService` only where entity context adds value to presentation; M4 `ContextRepository`, `RuleRegistry`, `EvaluationService`, `EvaluationRepository`, evidence envelope and coverage lifecycle; current CLI conventions.

**Genuine blockers:** owner approval of D02-P01–P07 blocks activation of a deployable D-02 version. The current repository also lacks a concrete evaluator/composed workflow and any HTTP/API/frontend surface; these are implementation tasks, not blockers to starting the technical work after policy is recorded. The acceptance target's browser requirement is not established in the repo; CLI is the specification's default first presentation.

**M5.1 readiness:** M5.1 technical scaffolding, exact decoder, fixtures, range/coverage composition, identity verification, and CLI orchestration design can begin. A deployable/active D-02 policy and any user-facing assertion about token coverage cannot begin until the owner records the policy choices. M5.2 read-only API/UI can be sequenced after the API contract and acceptance need are confirmed; no separate backend is warranted.
