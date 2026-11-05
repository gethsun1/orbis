# ORBIS M5.0.2 — D-02 Owner Decision Record

**Purpose:** Record the owner's decisions on the seven M4.2 D-02 policy questions and track the remaining implementation inputs. The owner-approved P01–P07 policy positions below are binding; actual emitter addresses still require separate review. D-02 remains inactive until all implementation prerequisites are met.

**Decision status:** P01–P07 policy positions are **OWNER-APPROVED** as recorded in the decision table below. These approvals do not approve a particular emitter address or activate D-02.

## Governing event contract and implementation evidence

M4 §3 defines D-02 over validated standard-shaped ERC-20 `Transfer(address,address,uint256)` logs. The specified shape is topic0 `0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef`, exactly two correctly padded indexed addresses and one 32-byte amount. Mint is zero `from`/nonzero `to`; burn is nonzero `from`/zero `to`; both-zero is invalid/unsupported; ordinary transfers do not match. The spec requires emitter, network, block/transaction identity and exact log index to be retained. These semantics are the existing contract, not new owner choices. [M4 spec §3](M4_SPECIFICATION.md#3-rule-contracts); [M4.2 D-02 contract](M4_2_RULE_DECISIONS.md#d-02--erc-20-mintburn-detection).

There is no D-02 decoder or concrete evaluator: [evaluator.py](../src/orbis/rules/evaluator.py) defines only a protocol. [ContextRepository](../src/orbis/rules/context.py) reads canonical block manifests/logs but does not itself prove complete transaction/receipt coverage and its log query does not filter the stored `removed` flag. [Indexer](../src/orbis/observer/indexer.py) verifies block/receipt/log identity and commits receipts/logs with the checkpoint, but its receipt validator does not validate receipt status; [PostgresStore](../src/orbis/observer/postgres.py) stores that status and atomically rolls back source suffixes and invalidates dependent M4 evaluations. [EvaluationService](../src/orbis/rules/service.py) requires a trusted exact `NetworkContext` and applies the coverage gate; [coverage.py](../src/orbis/rules/coverage.py) changes an insufficiently covered negative to `insufficient_coverage`. [RuleRegistry](../src/orbis/rules/registry.py) stages immutable version definitions. [EvaluationRepository](../src/orbis/rules/repository.py) persists findings and evidence links, currently de-duplicating findings by `(network_id, evaluation_id, finding_key)`, so stable exact-log keys must be supplied by the caller. [Evidence helpers](../src/orbis/rules/evidence.py) digest and verify retained snapshots.

## Decisions

### D02-P01 — Emitter scope

- **Original unresolved question (M4.2):** “Confirm scan of all indexed emitters versus an approved token allowlist/registry.”
- **Semantics and sources:** A matching signature and standard-shaped payload establish only an encoded event shape; M4.2 says this does not establish ERC-20 behavior. `log.address` is the emitting contract and part of evidence. There is no token-verification/allowlist implementation. Sources: M4 §3; M4.2 §D-02 owner decisions; `src/orbis/rules/context.py`.
- **Alternatives:** All emitters with a valid shape; explicit immutable token-address allowlist; another named, governed verification registry/process.
- **Recommendation:** Use an explicit immutable per-version address allowlist. Describe only a validated event-shaped log from an in-scope emitter; do not label it a verified token without separate evidence.
- **Technical consequence:** Pin scope and provenance in rule parameters/identity; disclose out-of-scope events separately from accepted detections.
- **Detection accuracy:** All-emitter mode risks false positives from arbitrary contracts; an allowlist reduces that risk but misses unlisted genuine tokens.
- **Evidence/auditability:** Retain emitter and observed raw event fields even when not accepted; retain the allowlist and approval provenance used by the evaluation.
- **Reorg/replay:** Replay the same immutable scope against replacement canonical input; a scope change requires a new version/evaluation identity.
- **Missing information:** Owner has not supplied Sepolia addresses or an authoritative source/approval provenance for them. Therefore no live allowlist evaluation can be configured yet.
- **Approval status:** **APPROVED** (policy position only; each address needs separate review)

### D02-P02 — Zero-amount handling

- **Original unresolved question (M4.2):** “Confirm whether zero-amount mint/burn events count (proposed: event classification still counts, because D-02 detects the standard event's endpoints; amount is evidence, not a threshold).”
- **Semantics and sources:** The M4 predicate classifies by one-sided zero-address endpoints and specifies a uint256 amount, with no D-02 threshold. M4.0's exclusion of zero values applies to D-01, not D-02. Sources: M4 §3; M4.2 §D-02; M5.0.1 §3.
- **Alternatives:** Count a valid one-sided endpoint event at zero; exclude it; introduce a separately approved threshold.
- **Recommendation:** Count it as an event-shaped mint/burn observation, retaining amount `0`; do not claim nonzero supply change.
- **Technical consequence:** Endpoint predicate remains independent of amount; persist canonical decimal amount.
- **Detection accuracy:** Counting follows the stated event definition and avoids a newly invented threshold; it may report an event with no quantity increase/decrease.
- **Evidence/auditability:** Raw data and decoded zero remain reproducible; text must describe encoded event only.
- **Reorg/replay:** Apply the same deterministic rule to each canonical replay input.
- **Approval status:** **APPROVED**

### D02-P03 — Both-zero endpoints

- **Original unresolved question (M4.2):** “Confirm both-zero `from` and `to` endpoints are unsupported/malformed, not mint or burn (proposed).”
- **Semantics and sources:** M4 explicitly calls both-zero invalid/unsupported and only defines one-sided zero endpoints as mint/burn. Sources: M4 §3; M4.2 §D-02.
- **Alternatives:** Unsupported diagnostic/no finding; classify as mint or burn; define a separate event class.
- **Recommendation:** Preserve as unsupported diagnostic; never create a D-02 mint/burn finding.
- **Technical consequence:** Decoder emits a stable unsupported reason and source identity; coverage outcome follows P05/P06.
- **Detection accuracy:** Avoids ambiguous directional classification and false positives; gating may make the range insufficient.
- **Evidence/auditability:** Preserve raw topics/data and decoder result as diagnostic evidence, without treating it as an accepted detection.
- **Reorg/replay:** Keep diagnostic with historical evaluation; invalidate that evaluation if its block is orphaned and recompute against canonical replacement input.
- **Approval status:** **APPROVED**

### D02-P04 — Reorganization and removed logs

- **Original unresolved question (M4.2):** “Confirm removed/reorg-marked logs are excluded from active positives and reflected in coverage/invalidation (proposed).”
- **Semantics and sources:** M4 §6 requires suffix rollback to invalidate dependent evaluations atomically, retain their snapshots/audit and evaluate replacement evidence as a new identity. Observer rollback/invalidation is implemented in `src/orbis/observer/postgres.py`; the observer stores a log `removed` flag, while `ContextRepository.logs()` currently does not filter it. Sources: M4 §6; M4.2 §D-02; `src/orbis/observer/indexer.py`; `src/orbis/observer/postgres.py`; `src/orbis/rules/context.py`.
- **Alternatives:** Exclude noncanonical/removed input and invalidate/replay; leave findings active; mark only partial without invalidation.
- **Recommendation:** Only canonical, non-removed evidence may support an active finding. Reuse atomic invalidation, preserve historical evidence/audit, and evaluate replacement canonical input as a new evaluation.
- **Technical consequence:** Integration must explicitly filter/classify removed records and verify evaluation evidence indexes every consumed source block hash so rollback finds affected evaluations.
- **Detection accuracy:** Prevents fork-only positives from appearing current; replay may temporarily leave results unavailable until replacement evaluation completes.
- **Evidence/auditability:** Retain old source snapshot and invalidation reason/hashes; distinguish historical observation from current canonical result.
- **Reorg/replay:** This is the policy: never rewrite the old evaluation into a replacement result.
- **Approval status:** **APPROVED**

### D02-P05 — Malformed/unsupported event coverage

- **Original unresolved question (M4.2):** “Confirm evaluation behavior: record decoder coverage as partial/unknown and do not count as a negative; preserve bounded diagnostics and source identity where valid (proposed).”
- **Semantics and sources:** M4 says malformed, removed, unsupported or undecodable logs are not negative matches; report coverage limitations. The coverage gate only gates a proposed negative when required dimensions are insufficient. Sources: M4 §3 and §5; M4.2 §D-02; `src/orbis/rules/coverage.py`; `src/orbis/rules/evaluator.py`.
- **Alternatives:** Fail execution; retain diagnostics and make mandatory coverage partial/unknown; ignore malformed candidates; treat them as ordinary non-matches.
- **Recommendation:** Never match malformed input. Preserve bounded diagnostics and source identity where valid. If a malformed/unsupported item could hide an in-scope candidate, mark required decoder coverage incomplete and return `insufficient_coverage`, never `not_matched`.
- **Technical consequence:** Define stable diagnostic codes, counts and scoped coverage dimensions; distinguish valid ordinary transfers from undecodable candidate logs; avoid unbounded RPC error strings.
- **Detection accuracy:** Fail-closed coverage avoids false negatives; emitter-scoped gating avoids unrelated malformed emitters blocking a declared scope.
- **Evidence/auditability:** Preserve raw source fields and validation result when available; diagnostic preservation does not accept the event as a detection.
- **Reorg/replay:** Keep diagnostics for audit but mark associated evaluation invalidated if its source becomes noncanonical; replay recomputes coverage.
- **Missing information:** M4.2 does not settle whether any malformed candidate blocks the full range or only an in-scope emitter. Recommendation is scoped gating, contingent on an approved scope definition under P01.
- **Approval status:** **APPROVED**

### D02-P06 — Range completeness

- **Original unresolved question (M4.2):** “Specify what indexed range is considered available and how missing/pruned receipts/logs are represented.”
- **Semantics and sources:** M4 §5 requires complete requested range, canonical hashes, transaction/receipt and log provenance; bounded range is not chain-wide coverage. `Indexer` fetches one receipt per transaction and validates its source identity before atomic block commit, but `ContextRepository` currently returns only block manifest/log rows and does not expose a completeness manifest. No source establishes provider archive/retention guarantees. Sources: M4 §5; M4.2 §D-02; `src/orbis/observer/indexer.py`; `src/orbis/rules/context.py`; `src/orbis/rules/coverage.py`.
- **Alternatives:** Claim only explicitly requested locally indexed range; re-fetch/verify receipts for that range; accept gaps; require a named archive/completeness guarantee.
- **Recommendation:** Claim only the requested inclusive range; require contiguous canonical blocks plus full transaction, receipt and receipt-log provenance for every block in it. Any mandatory gap means `insufficient_coverage`; never imply chain-wide/history-wide absence.
- **Technical consequence:** Build range manifest with expected/observed counts and missing block/transaction/receipt/log identities; validate receipt status and fail closed before reporting `not_matched`.
- **Detection accuracy:** Prevents false negatives caused by missing/pruned inputs and confines negative outcomes to verifiable bounds.
- **Evidence/auditability:** Persist requested bounds, canonical hashes, counts, gaps and provenance in the immutable coverage/evidence envelope.
- **Reorg/replay:** Check canonical hashes at evaluation; rollback invalidates dependent evaluations and replay creates a new context identity.
- **Missing information:** The selected RPC endpoint's historical receipt/log availability and any completeness guarantee are unknown. Current observer validation does not require a receipt status value, and the range reader does not compare expected transactions/receipts/logs; implementation must close these gaps. Repository code cannot promise archive completeness; the policy can only fail closed when source material is unavailable.
- **Approval status:** **APPROVED**

### D02-P07 — Finding granularity

- **Original unresolved question (M4.2):** “Confirm one finding per qualifying log (proposed), with zero/nonzero value retained and no transaction-level collapse.”
- **Semantics and sources:** M4.2 specifies exact log identity and says multiple qualifying logs in one transaction are separate events. Repository uniqueness is per evaluation plus caller-supplied `finding_key`; it does not enforce protocol-level log keys itself. Sources: M4 §4; M4.2 §D-02; `src/orbis/rules/repository.py`; `src/orbis/rules/evidence.py`.
- **Alternatives:** One per exact log; one per transaction; aggregate by emitter/range.
- **Recommendation:** One finding per qualifying log, keyed by network fingerprint, rule version, block hash, transaction hash and exact log index.
- **Technical consequence:** Supply deterministic per-log keys; confirm active-result query semantics and uniqueness during integration. Preserve multiple logs within one transaction.
- **Detection accuracy:** Avoids collapsing distinct event evidence; aggregation could hide separate endpoints/events.
- **Evidence/auditability:** Link each finding to exact raw topics/data and independently verifiable log evidence.
- **Reorg/replay:** Same canonical evidence/version deduplicates deterministically; a replacement block hash is new evidence and old results are invalidated, not overwritten.
- **Approval status:** **APPROVED**

## Implementation readiness

### A. Approved semantics and remaining implementation gates

P01–P07 settle the policy semantics and must be implemented exactly as approved. The deployable rule remains staged until there is an address-specific P01 review, authoritative provenance, complete evaluator integration, and acceptance evidence. The exact ABI shape and one-sided endpoint classes already specified by M4 must not be broadened.

### B. Decisions/integration contracts that can be resolved during composition

P04 canonical-only active results, invalidation, retained audit and replay; P06 bounded range completeness and fail-closed negative result. Their conservative direction is already prescribed by M4. They still require integration work and acceptance verification, but do not block pure decoder/fixture work.

### M5.1 work that can proceed independently

- Complete and verify the exact-ABI decoder and fixtures under the approved zero-value, both-zero, malformed-input, and per-log policies.
- Implement trusted `NetworkContext` propagation and a bounded canonical source reader; no chain-ID-only resolution.
- Complete coverage/evidence-envelope plumbing and operator orchestration while keeping D-02 inactive until implementation gates pass.
- Review exact finding identity and rollback invalidation/replay integration against M4 tables/code.
- Prepare read DTO/query-service contracts and a static frontend shell with honest loading, unavailable and empty states; connect only to real backend data when available.

**Approval record:** P01–P07 policy positions are owner-approved. Approval is limited to the policy semantics in the table; it is not approval of a future emitter address, a deployable rule, or D-02 activation.

## Owner Position — Approved



| Decision | Recommendation and rationale | Unresolved input | Approval status |
|---|---|---|---|
| P01 | Use an immutable per-version emitter allowlist. Matching the event ABI does not establish token identity. | Actual Whitechain Sepolia addresses and authoritative provenance are outstanding. | APPROVED |
| P02 | Count valid one-sided mint/burn events even when the encoded amount is zero; do not claim a zero-amount event changes supply. | Confirm the evaluator and evidence output preserve amount zero without a supply-change claim. | APPROVED |
| P03 | Both-zero endpoints are unsupported diagnostics, never findings. | Implement and verify the unsupported diagnostic path. | APPROVED |
| P04 | Only canonical evidence supports active findings. Reorganizations invalidate affected evidence and require replay while preserving historical records. | Complete and verify invalidation, retained audit, and replay integration. | APPROVED |
| P05 | Preserve bounded malformed/unsupported diagnostics. Gate coverage only where malformed or unidentified input could conceal an in-scope event. | Implement scoped coverage gating using the approved P01 allowlist. | APPROVED |
| P06 | Require complete canonical provenance for the requested inclusive range. Any mandatory gap prevents a negative conclusion. | Verify provider receipt/log availability for requested ranges; fail closed when unavailable. | APPROVED |
| P07 | One finding per qualifying log, with stable identity incorporating network fingerprint, rule version, block hash, transaction hash and exact log index. | Implement and verify stable per-log keys and active-result uniqueness. | APPROVED |

### P01 address and provenance inputs — pending evidence and address-specific review

| Field | Current value/status |
|---|---|
| Approved emitter policy | Immutable per-version allowlist (**approved**) |
| Candidate contract address | `0x0dDb9ed0C4795b5Ed29c600e0Ade784973Cde1EC` on verified Whitechain Sepolia |
| Verified contract identity | `ORBIS Test Token` / `ORBT`, 18 decimals; owner and zero initial supply verified on-chain |
| Deployment provenance | Verified receipt `0xae70a5c1e71a381802e3e2762ba29aaf8561afc2a18acb98d1e936d03a749780`; mint and burn receipts recorded in [P01 provenance](M5_1_3_P01_EMITTER_PROVENANCE.md) |
| Source verification status | Not submitted; no source is represented as verified |
| Evidence references | Pending deployment, mint, burn, and ordinary-transfer receipts |
| Address-specific approval status | **PENDING OWNER APPROVAL**; policy approval does not approve this address |

### M5.1.3 evidence update (6 November 2026)

The deployment and controlled mint/burn are verified through Ankr Whitechain Testnet RPC. See the [deployment report](M5_1_3_WHITECHAIN_TEST_TOKEN_DEPLOYMENT_REPORT.md) and [PostgreSQL verification report](M5_1_3_POSTGRESQL_RECOVERY_AND_VERIFICATION_REPORT.md). This evidence does not approve the emitter address or activate D-02. The address-specific P01 decision and all remaining evaluator/coverage/activation prerequisites remain open; D-02 remains inactive.
