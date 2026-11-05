# M5.1.3 P01 Emitter Provenance

## Status

**On-chain candidate provenance verified; address-specific owner review remains pending.** P01 policy is an immutable per-version emitter allowlist. Policy approval is not approval of this address. D-02 remains inactive.

**Verification timestamp:** 6 November 2026, 01:16 Africa/Nairobi.

## Verified on-chain facts

| Field | Verified value |
|---|---|
| RPC provenance | Ankr Whitechain Testnet RPC (`https://rpc.ankr.com/whitechain_testnet`) |
| Chain ID | 1874 (`0x752`) |
| Genesis block hash | `0xb92575f4a11271b5fe065eb8289be17906302e1c23218c5a67c2871a99e6f0d5` |
| Fingerprint scheme / canonical fingerprint | `evm-genesis-sha256-v1` / `sha256:b37bd66208154e284e3b6b53b8bc475a40a1e95cf8eca72d2696a1789d6e6174` |
| Candidate emitter | `0x0dDb9ed0C4795b5Ed29c600e0Ade784973Cde1EC` |
| Deployer / verified owner | `0x7D8C33636CAd243f937b8F42E7084882Fd8b61Cf` |
| Contract name / symbol / decimals | `ORBIS Test Token` / `ORBT` / `18` |
| Initial total supply | `0` |
| Deployment transaction | `0xae70a5c1e71a381802e3e2762ba29aaf8561afc2a18acb98d1e936d03a749780` |
| Deployment receipt | status 1; block `12320298`; hash `0x4de3ba802875c26d0da3fa0b0701b0383d761f73c40e498b5619d9f6ea0f0bcb` |
| Mint transaction | `0x9172206e7eecbb10be285ca74fd03c0ece5fcaca8119c2419da5eea99937ee95` |
| Burn transaction | `0x95c69961c66c391f8afa221d2c3337dc8e66c764db9eab175fddb6a98da76adb` |
| Explorer source verification | Not performed; no source verification is claimed |
| Address-specific P01 approval | **PENDING OWNER APPROVAL** |

The Ankr endpoint returned the expected chain ID and the same genesis hash across repeated calls. The fingerprint was derived with `orbis.network.fingerprint`; it was not manually selected. The deployment receipt, canonical block hash, metadata, owner, zero initial supply, and mint/burn receipt logs were read independently through JSON-RPC.

## Receipt and `Transfer` log evidence

Both receipts succeeded and contain one `Transfer` log emitted by the candidate address, at log index 0, with topic0 `0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef`.

| Field | Mint | Burn |
|---|---|---|
| Transaction / block | `0x9172206e7eecbb10be285ca74fd03c0ece5fcaca8119c2419da5eea99937ee95` / `12320339` | `0x95c69961c66c391f8afa221d2c3337dc8e66c764db9eab175fddb6a98da76adb` / `12320348` |
| Block hash | `0x4a21a7abc7d3bc6688ccce992168a484c359805d0792d0cffe5761f74d731762` | `0xf08a28dc868e301560ff4c3d6a7807058b82910870006d3c5144d6bd23250315` |
| Indexed `from` / `to` | zero address / deployment wallet | deployment wallet / zero address |
| Data amount | `2000000000000000000` (2 ORBT) | `750000000000000000` (0.75 ORBT) |
| Receipt status / log index | 1 / 0 | 1 / 0 |
| Post-transaction balance / supply | `2000000000000000000` / `2000000000000000000` | `1250000000000000000` / `1250000000000000000` |

See the [deployment verification report](M5_1_3_WHITECHAIN_TEST_TOKEN_DEPLOYMENT_REPORT.md) for raw topics, ABI data words, and build settings.

## Local evidence and owner gate

Local evidence: ORBT compiled with Solidity 0.8.19 and the local contract suite passed 5 tests. This supports implementation conformance but is not a substitute for the on-chain facts above.

**Owner decision still required:** review and explicitly approve or reject `0x0dDb9ed0C4795b5Ed29c600e0Ade784973Cde1EC` as a P01 allowlist emitter for the verified Whitechain Sepolia identity. Do not activate D-02 or add the address to an active production rule based solely on deployment or P01 policy approval. Other D-02 implementation and activation prerequisites remain governed by the owner decision record.
