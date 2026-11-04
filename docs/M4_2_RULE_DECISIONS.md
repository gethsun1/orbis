# ORBIS M4.2 — D-01 and D-02 Rule Decisions

**Status:** Decision brief for owner review. No D-01/D-02 evaluator, deployable rule version, threshold, or production behavior is implemented by this document. D-03–D-06 are out of scope.

## Purpose and decision format

M4.2 is scoped to the original D-01 Large Transfer and D-02 Mint/Burn identities. The approved M4 specification supplies useful provisional semantics, but D-01 thresholds/governance and some boundary cases remain open. This brief distinguishes the proposed contract from decisions that require owner approval. No rule should be activated until its immutable version includes the approved semantics, parameters and coverage policy.

## Shared contract requirements

- Evaluate only explicitly bounded inclusive block ranges on one fingerprinted canonical network. Evaluation identity must use the approved versioned network-fingerprint scheme described in the M4.1 audit before cross-installation identities are promised.
- Pin immutable rule version, normalized parameters, evaluator build, context digest and evidence envelope to every evaluation.
- A positive result creates one or more positive findings; a complete negative has no finding. Incomplete mandatory coverage is `insufficient_coverage`, never `not_matched`.
- Finding identity must include stable source identity (network fingerprint, rule/version, transaction hash and exact log index when log-based) plus the rule-specific match key. Identical results on different logs must not deduplicate. Enforce uniqueness in PostgreSQL and test concurrent creation.
- Never compare raw amounts across different assets. WBT base units and each ERC-20 contract's raw units are separate measurement domains. No fiat valuation or implicit cross-token conversion is allowed.
- Coverage must identify range continuity, canonical hashes, transaction/receipt completeness and status, log provenance/completeness, decoder support, malformed/removed source records and any asset metadata actually required. Token decimals are display metadata only if no conversion is performed; they are not a substitute for a token-specific raw-unit threshold.

## D-01 — Large transfer detection

### Proposed deterministic contract

Two independent modes:

1. **Native WBT:** direct transaction `value`, measured in native base units, from a successful transaction. This does not cover internal contract transfers because tracing is not available in M3.
2. **ERC-20:** validated standard `Transfer` logs emitted by a specific token contract, amount in that token contract's raw units. Each token contract is evaluated separately.

Match a single transfer when `amount >= threshold` (inclusive boundary), subject to the approved eligibility rules below. A transaction that reverts does not produce a transfer finding. Mint/burn endpoint transfers are classified by D-02 and excluded from D-01 to prevent overlap. A native transaction is identified by transaction hash; an ERC-20 transfer is identified by transaction hash plus exact log index. A successful transaction with multiple eligible large token logs may produce multiple findings, one per log.

No aggregation of transfers is implied by “large transfer.” If the owner wants per-window aggregate movement as well as single-transfer detection, that is a separate semantic mode with separately approved parameters and versioning.

### Owner decisions required

| Decision | Required choice / proposed default | Reason |
|---|---|---|
| Native WBT eligibility | Confirm direct external transaction value only; explicitly exclude internal calls/value movement until trace coverage exists. | Current canonical tables contain transaction value but no call trace. |
| ERC-20 eligibility | Confirm only standard, validated ERC-20 `Transfer` logs; choose whether any token contract is eligible or a governed allowlist/metadata policy is required. | Avoid treating arbitrary event-shaped logs as token transfers. |
| Thresholds | Choose absolute WBT threshold in WBT base units and per-token-contract threshold in that token's raw units. Define who may set/change them, approval/audit path, effective block/time and how a new value produces a new immutable rule version or parameter identity. | Values are not supplied; thresholds must be reproducible and must not vary silently during a window. |
| Comparison boundary | Approve inclusive `>=` versus strict `>` (spec currently proposes inclusive). Specify exact boundary tests. | A one-unit boundary changes positives. |
| Evaluation window | Choose single-event scan over an explicit range (proposed) versus any aggregation within a window. For aggregation, define window length, alignment/overlap, subject direction and whether the threshold applies to each event or total. | Do not infer rolling aggregation from a block range. |
| Relative mode | Decide whether relative baselines are needed for M4.2. Proposed initial mode is absolute-only. If required, define eligible comparator population, time/block reference window, statistic, minimum sample size, same-asset grouping, gap handling and versioned parameters before implementation. | Relative mode has no defined comparator/window today. |
| Zero-value transfer | Confirm exclusion (proposed and current M4 spec). | Zero has no transferred value and is not a large movement. |
| Self-transfer | Confirm exclusion (proposed and current M4 spec), including how subject equality is determined for token holders. | Avoid duplicate/no-net-movement positives; token event semantics may still be useful to another rule. |
| Mint/burn overlap | Confirm all zero-address endpoint events are D-02 only, never D-01. | One canonical classification avoids duplicate findings. |
| Coverage and negative results | Require complete canonical range, every transaction's receipt/status, complete receipt-log provenance for ERC-20 mode, and decoder validation for eligible token logs. Choose whether unsupported/malformed token logs anywhere in range make the whole ERC-20 evaluation partial or only affect a declared token allowlist. | A missing transfer log cannot be treated as absence of a transfer. |
| Subject/window scope | Define whether the rule is wallet-subject, token-contract subject, or a general bounded transfer scan, and what one evaluation returns when several senders/recipients match. | Identity, API shape later, and finding grouping depend on scope. |

### Evidence contract

For native findings retain network fingerprint, block number/hash, transaction hash, sender, recipient, raw native value, transaction/receipt status and exact bounded-range context needed to establish completeness. For ERC-20 findings retain the same block/transaction identities plus emitter token contract, exact log index, topic0/topics/data, decoded from/to/raw amount and decoder/schema version. Store raw integer quantities as canonical decimal strings and hashes/addresses as normalized lowercase hex. Evidence must be sufficient to recalculate eligibility and threshold comparison after source deletion.

### Coverage requirements

Native mode requires complete requested block continuity/canonical hashes, transaction completeness and receipt status for every transaction in range. ERC-20 mode additionally requires complete receipt-log provenance and supported/validated Transfer decoding for the rule's declared token scope. Missing receipts, unproven log completeness, untrusted decoder/standard, or a missing required threshold makes the evaluation insufficient; none may become a negative result. Coverage should report range start/end, gaps, observed and expected source counts, unsupported/malformed counts and the exact token scope.

## D-02 — ERC-20 mint/burn detection

### Proposed standard event contract

Support exactly the standard ERC-20 event:

```text
Transfer(address indexed from, address indexed to, uint256 value)
```

- Event signature text: `Transfer(address,address,uint256)`.
- `topic0`: Keccak-256 event signature `0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef`.
- `topic1`: 32-byte ABI word containing the indexed `from` address; the first 12 bytes must be zero.
- `topic2`: 32-byte ABI word containing the indexed `to` address; the first 12 bytes must be zero.
- `data`: exactly one 32-byte ABI word encoding unsigned `uint256 value`.
- `log.address` is the emitting token contract and part of the finding identity/evidence.

Classification:

- **Mint:** `from == 0x0000000000000000000000000000000000000000` and `to != zero`.
- **Burn:** `from != zero` and `to == zero`.
- **Ordinary transfer:** neither endpoint is zero; no D-02 finding.
- **Invalid/unsupported:** both endpoints are zero, wrong topic count, malformed/padded addresses, invalid topic0, malformed data length or noncanonical source provenance. Do not infer supply change.

The emitter address and exact `(network fingerprint, block hash, transaction hash, log index)` identify the evidence item. Multiple valid mint/burn logs in one transaction are separate events and may create separate findings, even when emitter and recipient repeat. Stable ordering uses block number, transaction index, then log index. Deduplication uses exact log identity, not transaction hash alone.

### Owner decisions required

| Decision | Required choice / proposed default | Reason |
|---|---|---|
| Token scope | Confirm scan of all indexed emitters versus an approved token allowlist/registry. Do not treat a matching signature from an arbitrary contract as established ERC-20 behavior without declaring the support policy. | Event signature alone cannot prove complete token standard compliance. |
| Zero-value events | Confirm whether zero-amount mint/burn events count (proposed: event classification still counts, because D-02 detects the standard event's endpoints; amount is evidence, not a threshold). | Avoid inventing a minimum mint/burn amount. |
| Both-zero endpoints | Confirm unsupported/malformed, not mint or burn (proposed). | It does not express a one-sided supply endpoint and is ambiguous. |
| Removed logs | Confirm removed/reorg-marked logs are excluded from active positives and reflected in coverage/invalidation (proposed). | Preserve canonicality semantics. |
| Unsupported/malformed event | Confirm evaluation behavior: record decoder coverage as partial/unknown and do not count as a negative; preserve bounded diagnostics and source identity where valid (proposed). | No inference from malformed or unsupported encoding. |
| Historical support | Specify what indexed range is considered available and how missing/pruned receipts/logs are represented. | A bounded scan cannot imply chain-wide absence. |
| Finding granularity | Confirm one finding per qualifying log (proposed), with zero/nonzero value retained and no transaction-level collapse. | Exact log identity distinguishes multiple events in one transaction. |

### Evidence contract

Retain chain ID plus network fingerprint, emitting contract, block number/hash, transaction hash, exact log index, transaction index if used for order, topic0/topics/data as observed canonical hex, decoded from/to/value, decoder identity/version and validation result. Each evidence item must be independently digest-verifiable and survive source rollback. Findings point to the exact log item; no source-row FK is permitted.

### Coverage requirements

Require complete canonical block continuity/hashes and transaction/receipt-log provenance for the requested range. Coverage must enumerate supported versus unsupported emitters/standards, malformed event counts, removed logs and gaps. A successful complete scan with no qualifying zero-address endpoint event may be `not_matched`; any unresolved mandatory source/decoder gap means `insufficient_coverage`. Unsupported layouts do not imply supply change and must never produce mint/burn findings.

## Readiness gate

The rule contracts are sufficiently prepared for owner decision review. M4.2 implementation should begin only after the owner resolves the tables above, approves D-01 threshold governance and D-02 token support policy, and accepts the M4.1 identity/finding-key remediation plan. No rule version should be activated from proposed defaults alone.
