# ORBIS M4.1.2A.1 Implementation Report

**Status:** isolated identity and configuration foundation implemented. This report does not claim PostgreSQL registry readiness or production readiness.

## Files created and modified

- Created `src/orbis/network.py` for canonical identity, immutable trust contexts, and exact resolver validation.
- Modified `src/orbis/chain/rpc.py` to validate block-zero identity, parse quantities strictly, and avoid echoing provider error text.
- Modified `src/orbis/config.py` to parse explicit named profiles while retaining the singular environment configuration.
- Modified `src/orbis/observer/indexer.py` to verify chain ID and genesis identity before checkpoint access; PostgreSQL style stores are refused until an exact resolver exists.
- Modified `src/orbis/observer/store.py` to mark SQLite as the supported single-profile local exception.
- Added `tests/test_network_identity.py`; extended `tests/test_rpc.py` and `tests/test_observer.py`.

No migration, database schema, `.env` file, or database content was changed or accessed.

## Identity serialization and fingerprint

The implementation uses scheme `evm-genesis-sha256-v1`. It rejects non-positive, boolean, non-integer chain IDs and requires a 32-byte hexadecimal genesis hash. Hashes normalize to lowercase. Canonical bytes are compact, sorted-key UTF-8 JSON with no trailing newline:

```json
{"chain_id":1,"genesis_hash":"0x<64 lowercase hex>"}
```

SHA-256 is represented as `sha256:<64 lowercase hex>`. Fingerprints are always derived locally; caller-supplied fingerprint values are checked against the canonical derivation when constructing a context. Both published vectors are asserted byte-for-byte and digest-for-digest in tests.

## NetworkContext trust states

`NetworkContext` is frozen and cannot be initialized by ordinary callers. The public unverified factory creates an untrusted context with no identity fields. The RPC verifier creates an unresolved context after validating `eth_chainId`, block zero height, and genesis hash. An exact registry resolver factory checks the selected tuple and stored genesis before producing a trusted context with a positive internal `network_id`.

The indexer now verifies identity before its first checkpoint read. Until registry resolution is implemented, it refuses to run against registry-backed stores. SQLite remains allowed as a single-profile local/fixture store under the approved SQLite exception. It still uses its existing chain-ID keyed API and must not be used for multiple profiles.

## Configuration precedence and validation

`ORBIS_NETWORKS_JSON` accepts 1–32 profile objects with `name`, `rpc_url`, and positive integer `chain_id`, plus optional string descriptive metadata. The JSON input is capped at 65,536 bytes; duplicate profile names/fields, unsupported fields, malformed values, and invalid endpoints are rejected. More than one profile requires exact `ORBIS_NETWORK` selection. A simultaneous legacy RPC/chain pair is accepted only when it matches the selected profile; otherwise loading fails. Legacy `ORBIS_RPC_URL` and `ORBIS_CHAIN_ID` continue to select the sole default profile. SQLite configuration rejects more than one profile.

## API integration and remaining chain-ID-only paths

The indexer performs genesis verification before data selection and refuses registry-backed operations until exact resolution can be wired to the database. The implementation intentionally leaves the PostgreSQL schema and service APIs untouched in this isolated step.

Chain-ID-only paths remain in:

- `src/orbis/observer/postgres.py`: `_network_id`, `checkpoint`, `block_hash`, `commit_block`, `rollback_from`, and `count`.
- `src/orbis/knowledge.py`: `_network` and the public/nested service calls that pass `chain_id`.
- `src/orbis/observer/indexer.py` and `ObserverStore`: selector/write method signatures remain chain-ID based for SQLite compatibility; PostgreSQL invocation is fenced pending resolution.
- `src/orbis/observer/store.py`: SQLite table keys and selectors remain chain-ID based by approved single-network policy.
- Rule/evidence service boundaries continue their current network ID and chain-ID handling; evaluation v1 and envelopes were not changed in this milestone.

The CLI's pre-existing runtime migration call remains unchanged. A later coordinated runtime/schema milestone must remove or gate it and wire exact PostgreSQL registry resolution before enabling PostgreSQL indexing.

## Test results

Command: `uv run --frozen python -m unittest tests.test_network_identity tests.test_rpc tests.test_observer tests.test_rules`

Result: **27 tests passed; 1 expected failure** (existing suite expectation). Coverage includes frozen vectors, deterministic output, malformed identity rejection, same chain ID with different genesis, endpoint-independent identity, context construction and mismatch rejection, profile selection/conflicts, SQLite multi-profile rejection, genesis RPC validation, credential redaction, and regression behavior.

`compileall` passed for source and focused test modules. `git diff --check` passed. Pytest is not installed in the project environment; lint and type-check commands are not configured/available. PostgreSQL integration tests were not run because they can connect to an externally configured database. No database was accessed.

## Known limitations

- There is no PostgreSQL identity registry resolver or schema support in this milestone. The indexer therefore refuses PostgreSQL network data operations rather than using chain-only selectors.
- The trusted context factory is implemented and validated but cannot yet be obtained in application flow until the registry milestone.
- Knowledge and rule/evidence API propagation remains pending.
- SQLite is intentionally single-network and cannot separate same-chain-ID networks.
- Existing CLI migration startup behavior remains and must be addressed with the coordinated runtime/schema boundary.

## Recommended next milestone

Implement the coordinated registry and runtime propagation milestone: reviewed additive PostgreSQL identity schema, exact tuple resolution to preserved `network_id`, context-based observer and knowledge APIs, runtime migration separation/compatibility gates, and real PostgreSQL isolation/security tests. Keep deployment and production readiness claims gated by the closure document's outstanding evidence and operational controls.
