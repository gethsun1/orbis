# M5.1.3 Whitechain Sepolia Test Token Deployment Report

## Result

**ORBT testnet deployment and controlled mint/burn verification: COMPLETE.** Direct Ankr JSON-RPC reads and transaction receipts establish the network, wallet, deployment, token metadata, and event/state results below. This is testnet evidence only. Source verification on a public explorer was not performed, and deployment does not approve this address for D-02.

**Verification timestamp:** 6 November 2026, 01:16 Africa/Nairobi.

## Network and signer verification

RPC provenance: Ankr Whitechain Testnet RPC, `https://rpc.ankr.com/whitechain_testnet` (no credentials used or recorded). Three repeated JSON-RPC observations returned chain ID `0x752` (1874) and the same genesis block hash, `0xb92575f4a11271b5fe065eb8289be17906302e1c23218c5a67c2871a99e6f0d5`. Head height advanced from `0xbbfe06` to `0xbbfe07`, consistent with a live endpoint. Wallet balance was stable at `0x1bc16d674ec80000` native units during preflight. The configured deployment key was derived in-process and matched `0x7D8C33636CAd243f937b8F42E7084882Fd8b61Cf`; the key was not printed or written to a file.

The project identity implementation (`orbis.network.fingerprint`, scheme `evm-genesis-sha256-v1`) derives canonical fingerprint:

```text
sha256:b37bd66208154e284e3b6b53b8bc475a40a1e95cf8eca72d2696a1789d6e6174
```

The Hardhat network configuration uses Ankr, and the deploy script checks chain ID, the independently verified genesis hash, expected signer address, and nonzero gas balance before deployment.

## Contract and local verification

The implementation conforms to the approved specification: `ORBIS Test Token` (`ORBT`), 18 decimals, zero initial supply, Solidity 0.8.19, owner-only mint, holder burn, no proxy, and no transfer tax. OpenZeppelin Contracts 4.9.6 is pinned; compiler optimizer is enabled for 200 runs, EVM target Paris, `viaIR: false`, IPFS metadata hash.

From `contracts/orbt/`:

```bash
npm ci
npm test
npm run compile
```

Results: install completed; **5 passing, 0 failing**; compilation succeeded (`Nothing to compile` on the final post-deployment guard rebuild because artifacts were current). npm reported 22 dependency audit advisories (10 low, 3 moderate, 9 high); no dependency remediation was applied as part of this milestone.

## Deployment evidence

| Field | Verified value |
|---|---|
| Chain ID | 1874 (`0x752`) |
| Contract | `0x0dDb9ed0C4795b5Ed29c600e0Ade784973Cde1EC` |
| Deployment transaction | `0xae70a5c1e71a381802e3e2762ba29aaf8561afc2a18acb98d1e936d03a749780` |
| Receipt status | 1 (success) |
| Block number / hash | `12320298` / `0x4de3ba802875c26d0da3fa0b0701b0383d761f73c40e498b5619d9f6ea0f0bcb` |
| Deployer | `0x7D8C33636CAd243f937b8F42E7084882Fd8b61Cf` |
| Deployed code | Present; 3,171 bytes |

The deployment receipt, transaction sender/creation target, and canonical block hash were fetched independently from the Ankr endpoint. Read calls returned name `ORBIS Test Token`, symbol `ORBT`, decimals `18`, owner equal to the deployer, and initial `totalSupply = 0`.

## Controlled mint and burn evidence

Minted `2 ORBT` (`2000000000000000000` base units) to the deployment wallet, then burned `0.75 ORBT` (`750000000000000000` base units) from that holder. Each entry below is decoded from the actual successful transaction receipt; topic0 is the standard ERC-20 `Transfer(address,address,uint256)` signature. Log index is 0 and emitter is the deployed contract.

| Evidence | Mint | Burn |
|---|---|---|
| Transaction hash | `0x9172206e7eecbb10be285ca74fd03c0ece5fcaca8119c2419da5eea99937ee95` | `0x95c69961c66c391f8afa221d2c3337dc8e66c764db9eab175fddb6a98da76adb` |
| Receipt status | 1 | 1 |
| Block number / hash | `12320339` / `0x4a21a7abc7d3bc6688ccce992168a484c359805d0792d0cffe5761f74d731762` | `12320348` / `0xf08a28dc868e301560ff4c3d6a7807058b82910870006d3c5144d6bd23250315` |
| `from` | `0x0000000000000000000000000000000000000000` | `0x7D8C33636CAd243f937b8F42E7084882Fd8b61Cf` |
| `to` | `0x7D8C33636CAd243f937b8F42E7084882Fd8b61Cf` | `0x0000000000000000000000000000000000000000` |
| Amount (base units) | `2000000000000000000` | `750000000000000000` |
| ABI data word | `0x0000000000000000000000000000000000000000000000001bc16d674ec80000` | `0x0000000000000000000000000000000000000000000000000a688906bd8b0000` |

After mint, wallet balance and total supply were both `2000000000000000000`. After burn, both were `1250000000000000000` (1.25 ORBT). Receipt topics contained the zero address and correctly padded wallet address in the expected indexed positions. No mint/burn log was fabricated or inferred from local tests.

## Explorer status and boundaries

No explorer source-verification result is claimed. An explorer URL/API was not used as evidence. The verified RPC, transaction hashes, block identities, and receipts are the provenance source for this report. Deployment is a testnet action only; no mainnet or production deployment occurred. No D-02 rule was activated and no production emitter allowlist was changed.

The deployed address is a P01 candidate requiring separate owner review. P01 policy approval alone does not approve this emitter address.
