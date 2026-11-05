const { ethers } = require("hardhat");

async function main() {
  const network = await ethers.provider.getNetwork();
  if (network.chainId !== 1874n) throw new Error("Refusing deployment: RPC chain ID is not 1874");
  const genesis = await ethers.provider.getBlock(0);
  const expectedGenesisHash = "0xb92575f4a11271b5fe065eb8289be17906302e1c23218c5a67c2871a99e6f0d5";
  if (!genesis || genesis.hash.toLowerCase() !== expectedGenesisHash)
    throw new Error("Refusing deployment: RPC genesis block does not match verified Whitechain Sepolia identity");
  const [signer] = await ethers.getSigners();
  if (!signer) throw new Error("PRIVATE_KEY is required");
  const expected = "0x7D8C33636CAd243f937b8F42E7084882Fd8b61Cf";
  if ((await signer.getAddress()).toLowerCase() !== expected.toLowerCase())
    throw new Error("Refusing deployment: signer does not match the owner-approved test wallet");
  const balance = await ethers.provider.getBalance(expected);
  if (balance === 0n) throw new Error("Refusing deployment: deployment wallet has no test WBT");
  const factory = await ethers.getContractFactory("ORBSTestToken", signer);
  const token = await factory.deploy();
  const receipt = await token.deploymentTransaction().wait();
  console.log(JSON.stringify({ address: await token.getAddress(), transactionHash: receipt.hash,
    deployer: expected, chainId: Number(network.chainId), blockNumber: receipt.blockNumber,
    blockHash: receipt.blockHash }, null, 2));
}

main().catch((error) => { console.error(error.message); process.exitCode = 1; });
