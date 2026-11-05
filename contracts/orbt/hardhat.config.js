require("dotenv").config({ path: "../../.env" });
require("@nomicfoundation/hardhat-ethers");
require("@nomicfoundation/hardhat-chai-matchers");

const key = process.env.PRIVATE_KEY;
const accounts = key ? [key] : [];

module.exports = {
  solidity: {
    version: "0.8.19",
    settings: {
      optimizer: { enabled: true, runs: 200 },
      evmVersion: "paris",
      viaIR: false,
      metadata: { bytecodeHash: "ipfs" }
    }
  },
  networks: {
    whitechainSepolia: {
      url: "https://rpc.ankr.com/whitechain_testnet",
      chainId: 1874,
      accounts
    }
  },
  paths: { sources: "./contracts", tests: "./test", cache: "./cache", artifacts: "./artifacts" }
};
