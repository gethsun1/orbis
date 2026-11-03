# ORBIS M4.0 — Deterministic Intelligence Specification

**Status:** Final approved M4.0 specification. M4.1 persistence implementation is recorded in `docs/M4_1_VERIFICATION_REPORT.md`; this does not mark M4 intelligence complete.
**Approved sequencing decision:** 4 November 2026; see [D-023](DECISIONS.md#d-023-milestone-sequencing).

## 1. Purpose and traceability

The approved product baseline remains `ORBIS_PRD_Architecture_Specification_v0.1.pdf`. This specification finalizes implementation contracts for its five initial detections (PRD §5.2, D-01–D-05), the deterministic rule/finding requirements (FR-06 and PRD §9), and milestone sequencing. It does not amend the PRD. The PRD's five rules remain mandatory; its D-06 liquidity candidate is outside the initial five.

Completed M1–M3 evidence is historical and bounded. The M3 live report records chain 1874, 150 blocks, 160 transactions/receipts, 13 logs, 12 entities, 340 observations, 22 relationships and 340 evidence references; enrichment processed 160 transactions and replay introduced no duplicates. These are not current database counts or a claim of complete network coverage.

## 2. Scope and milestone boundary

M3 is the evidence-backed knowledge layer. M4 delivers deterministic intelligence in M4.1–M4.5 below. Reasoning, investigations and later constrained explanation move to M5. AI/LLM, MeTTa, REST, TypeScript SDK, MCP, dashboard, deployment and database migrations are outside M4. M4 is complete only after D-01–D-05 are implemented and verified, or an explicit documented owner-approved scope change.

## 3. Rule contracts

All rules consume network-scoped canonical evidence over explicit bounded inputs. A positive finding is deterministic and evidence-linked; it does not establish intent, fraud, maliciousness or ownership. Failed transactions cannot generate successful transfer findings. If required coverage is not sufficient, the evaluation is `insufficient_coverage`, not a negative result.

### D-01 — Large Transfer

Two independent modes:

1. Native WBT transaction value, measured in WBT base units.
2. Standard ERC-20 `Transfer` event amount, measured in raw units for one specific token contract.

Compare values only within the selected mode and, for ERC-20, the same token contract. No fiat conversion or cross-token raw amount comparison. Contract-internal native transfers are out of scope until transaction tracing exists. Match at `amount >= threshold`. Zero-value transfers are excluded; self-transfers are excluded. Mint/burn endpoint events belong to D-02 and are not D-01 transfer findings. Relative thresholds remain deferred until comparator population and reference window are specified. A token-specific threshold is required for ERC-20 mode.

### D-02 — Mint/Burn

Decode only validated standard ERC-20 `Transfer(address,address,uint256)` logs with exactly two correctly padded indexed addresses and one 32-byte amount. Mint is zero-address sender to nonzero recipient; burn is nonzero sender to zero-address recipient. Both endpoints zero are invalid/unsupported; all other transfers are ordinary transfers. Preserve emitter contract, network, block number/hash, transaction hash and exact log index. Malformed, removed, unsupported or undecodable logs are not negative matches; report coverage limitations.

### D-03 — Privileged Role Changes (staged)

Candidate initial event allowlist requires explicit owner approval: OpenZeppelin Ownable-style `OwnershipTransferred`; OpenZeppelin AccessControl-style `RoleGranted` and `RoleRevoked`. Initial meaning is event-only. Events do not independently verify current permissions or effective role state. Until the standards/signatures allowlist is approved, keep the rule staged and do not claim broad role-change coverage.

### D-04 — Pause/Upgrade Events (staged)

Candidate initial event allowlist requires explicit owner approval: OpenZeppelin Pausable-style `Paused`/`Unpaused`, and EIP-1967-style `Upgraded`. Initial meaning is event-only. A pause event does not prove current paused state; an upgrade event does not prove the implementation slot changed. Keep staged pending allowlist approval.

### D-05 — Concentration/Accumulation (staged)

Proposed metric is HHI over an explicit cohort of normalized addresses, one network, a bounded block window and explicit direction (inbound, outbound or both). Calculate separately per token contract; native WBT is a separate mode. Never aggregate raw amounts across tokens or infer common ownership. This is not a fraud, suspiciousness or maliciousness conclusion. Owner approval must define minimum transfer count, denominator/weighting, eligible transfer semantics, cohort behavior and required coverage before activation. Zero denominator yields uncomputable/insufficient, never zero concentration. Retain exact evidence for every contributing transfer. Until these parameters are approved, keep staged.

## 4. Evaluation and finding lifecycle

Store three independent dimensions; never collapse them into one status:

| Dimension | Values | Meaning |
|---|---|---|
| Execution | `completed`, `failed` | Whether evaluator execution finished successfully. |
| Analytical outcome | `matched`, `not_matched`, `insufficient_coverage` | Result of a completed evaluation. Failed executions have no analytical result. |
| Canonicality | `active`, `invalidated` | Whether the canonical inputs remain valid under current chain history. |

A successful evaluation with full required coverage and no positives is persisted as `completed / not_matched / active`, with zero findings. Do not create synthetic negative findings. A finding represents only a positive deterministic result. One evaluation may have zero or many findings. Findings and evaluations are separate records. Failed evaluations may retain diagnostics and observed coverage, but cannot claim a matched or not-matched analytical result.

Every evaluation records immutable rule version, normalized parameters, canonical input/context identity, evaluator build identity, execution status, outcome, canonicality, coverage, start/completion metadata and retained evidence envelope. Every finding links to its evaluation and rule version and has normalized parameters/context identity, stable identity, evidence references and evaluator build identity (directly or through immutable evaluation linkage). Finding canonicality follows its evaluation; invalidation does not erase it.

Evaluation idempotency key is unique over network, rule version, normalized parameter digest, canonical input/context identity and evaluator build identity. Findings have a stable unique identity within an evaluation (for example deterministic rule-specific finding key plus evidence identity). Repeated execution for identical inputs must not duplicate evaluation or findings. A changed rule semantic requires a new immutable rule version.

## 5. Coverage contract

Coverage is machine-readable, per dimension, and scoped to requested network/range/context. Minimum dimensions:

- requested block range and gaps;
- canonical chain continuity and canonical block hashes;
- transaction and receipt completeness, including receipt success where relevant;
- log completeness and block/transaction/log-index provenance;
- decoder support and validation;
- token metadata when a rule requires it;
- M3 enrichment when a rule requires it;
- protocol/proxy standard support and allowlist applicability.

Use `complete`, `partial`, `unknown`, `not_applicable` per dimension, with details and evidence where useful. Missing evidence is not evidence that an event did not occur. A bounded indexed range is not complete network coverage. Each rule version declares mandatory dimensions and a deterministic sufficiency policy. Only adequate coverage permits `not_matched`; otherwise a completed evaluation is `insufficient_coverage`.

## 6. Immutable evidence and reorganization behavior

An evidence snapshot must contain enough actual normalized input to explain and reproduce the historical evaluation after M1/M3 source rows are deleted. A digest alone is insufficient. Retain, for every consumed source item: network/chain ID, block number/hash, transaction hash, optional log index, source kind, exact normalized fields consumed, evidence digest, digest algorithm and evidence schema version. Also retain rule version, normalized parameters, evaluator build, original outcome and coverage assessment. The complete normalized input envelope is immutable and digest-verifiable.

PostgreSQL suffix rollback must, in the same transaction as existing source deletion:

1. Identify evaluations/findings dependent on orphaned block hashes (including evidence embedded in the retained envelope).
2. Mark their canonicality `invalidated` and append invalidation audit rows with affected hashes, rollback boundary/time/reason and prior active state.
3. Preserve original evaluation, findings, parameters and evidence snapshots.
4. Perform existing M1/M3 source-row deletion and knowledge recomputation.
5. Commit atomically, so any failure rolls back source deletion and M4 invalidation/audit changes together.

Do not add restrictive foreign keys from retained M4 evidence to rollback-deleted source tables. Store canonical identities as values and enforce network-scoped references among retained M4 tables. Replacement canonical evidence receives a new evaluation identity and may link to the invalidated predecessor via supersession; never overwrite historical results. Invalidation audit is append-only. Retain evidence at least as long as its evaluation; retention duration beyond that is an owner decision and must be set before implementation.

## 7. Rule versioning and PostgreSQL architecture recommendation

Additive, network-scoped tables are recommended; this is design only, with no migration in M4.0:

- `rule_versions`: stable rule ID, semantic version, definition digest, required input schema, parameter schema, supported formats/decoders, lifecycle state and creation/activation metadata. Enforce immutable definition fields; lifecycle transitions use append-only metadata or constrained state changes.
- `evaluations`: network ID, rule-version identity, normalized parameters and digest, canonical input/context identity, evaluator build identity, independent execution/outcome/canonicality fields, coverage, timestamps, retained evidence envelope and digest, idempotency uniqueness.
- `findings`: network ID, evaluation ID, deterministic finding identity, rule/version linkage, result payload and canonicality derived from evaluation; unique stable identity.
- `finding_evidence`: finding-to-retained-evidence identity links, including exact log index where applicable; evidence payload must remain independently available after source deletion.
- `evaluation_invalidations`: append-only audit keyed to evaluation/invalidation event, orphaned block identities and rollback metadata.
- Optional supersession link from replacement evaluation to predecessor, constrained to the same network and compatible rule identity.

Use composite `(network_id, id)` uniqueness/foreign keys between M4 records to prevent cross-network linkage. Do not FK retained snapshot rows to `blocks`, `transactions`, `logs`, `observations` or `evidence_refs` where deletion would block rollback. Exact block hash, transaction hash and nullable log index live in the immutable envelope and indexed identity columns. Constraints should ensure: `failed` has no analytical outcome; completed has exactly one outcome; allowed enum values; valid block ranges; log index requires transaction hash; rule definition digest/version uniqueness; idempotency uniqueness; finding identity uniqueness; audit append-only permissions; and replacement/supersession network consistency. Index network/rule/time and network/canonicality, plus GIN or targeted indexes only for proven query needs. Keep rollback invalidation, audit insert and source deletion in one transaction.

Evidence retention policy: retain complete evidence envelopes and invalidation audits for the lifetime of evaluations/findings; no age-based purge before linked evaluations are retired under an explicitly approved retention policy. Duration, archival medium and retirement semantics are deferred to owner approval.

## 8. Delivery sequence and acceptance

- **M4.0 — Specification and architecture approval:** this document and sequencing updates.
- **M4.1 — Rule contracts and persistence:** registry/versioning, lifecycle, findings, snapshots, coverage contracts and idempotency.
- **M4.2 — D-01 and D-02:** large transfers and mint/burn.
- **M4.3 — D-05:** concentration after metric/minimum-data approval.
- **M4.4 — D-03 and D-04:** event-only detection after allowlist approval.
- **M4.5 — Integration and reorganization lifecycle:** preservation, invalidation, replacement evaluations, reproducibility and bounded live demonstration.

Acceptance for M4 requires all five original PRD rules implemented and verified with fixtures and documented limitations; positive and negative evaluations persisted correctly; coverage gates tested; immutable versions and idempotency demonstrated; all findings provenance-complete; reorg invalidation/audit atomic with source rollback; replacement evaluations distinct; retained evidence reproduces/explains historical inputs; and bounded live evidence clearly labeled without implying whole-network coverage. If a rule remains deferred, M4 is not complete unless owner-approved scope change is recorded.

## 9. Outstanding owner decisions

1. Approve D-03 and D-04 event-standard allowlists. Until then, both are staged and no broad protocol support is claimed.
2. Set D-01 threshold values and approved parameter governance at implementation time; relative mode remains unavailable until comparator/window defined. No threshold is invented here.
3. Approve D-05 cohort construction, direction default, HHI weighting/denominator, eligible transfer definition, minimum transfer count and insufficient-data policy. Until then D-05 is staged.
4. Approve evidence retention duration and retirement/archival policy. Until then evidence remains for at least the evaluation lifetime; no purge behavior can be implemented.
5. M4.1 implementation authorization was provided by the owner request on 4 November 2026; implementation and verification are recorded in `docs/M4_1_VERIFICATION_REPORT.md`.

## 10. PRD traceability

| PRD item | M4 disposition |
|---|---|
| §5.2 D-01–D-05 | Retained and specified in §3; D-03/04 allowlists and D-05 parameters remain staged for approval. |
| §5.2 D-06 liquidity movement | Explicitly outside initial five; not silently promoted or included. |
| FR-06 / §9 deterministic rules | Versioned deterministic evaluations and positive findings with outcomes, coverage and provenance; negative evaluation stored without synthetic finding. |
| §8 evidence architecture / §12 reorg and reliability | Retained input snapshots and atomic invalidation audit with existing rollback; detailed in §§5–7. |
| PRD M3 deterministic intelligence / PRD M4 reasoning and investigations | Implementation sequencing changed by D-023: knowledge layer M3; deterministic intelligence M4; reasoning/investigations M5. Product requirements remain. |
