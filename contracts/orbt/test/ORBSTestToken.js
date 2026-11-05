const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("ORBSTestToken", function () {
  async function deploy() {
    const [owner, alice, bob, stranger] = await ethers.getSigners();
    const Token = await ethers.getContractFactory("ORBSTestToken");
    const token = await Token.deploy();
    await token.waitForDeployment();
    return { token, owner, alice, bob, stranger };
  }

  it("exposes the required metadata and starts with zero supply", async function () {
    const { token, owner } = await deploy();
    expect(await token.name()).to.equal("ORBIS Test Token");
    expect(await token.symbol()).to.equal("ORBT");
    expect(await token.decimals()).to.equal(18);
    expect(await token.totalSupply()).to.equal(0n);
    expect(await token.owner()).to.equal(owner.address);
  });

  it("mints with a standard Transfer event and tracks supply", async function () {
    const { token, alice } = await deploy();
    await expect(token.mint(alice.address, 100n))
      .to.emit(token, "Transfer").withArgs(ethers.ZeroAddress, alice.address, 100n);
    expect(await token.balanceOf(alice.address)).to.equal(100n);
    expect(await token.totalSupply()).to.equal(100n);
  });

  it("burns as a holder with a standard Transfer event", async function () {
    const { token, alice } = await deploy();
    await token.mint(alice.address, 100n);
    await expect(token.connect(alice).burn(40n))
      .to.emit(token, "Transfer").withArgs(alice.address, ethers.ZeroAddress, 40n);
    expect(await token.balanceOf(alice.address)).to.equal(60n);
    expect(await token.totalSupply()).to.equal(60n);
  });

  it("supports ordinary transfers and zero-amount transfers", async function () {
    const { token, alice, bob } = await deploy();
    await token.mint(alice.address, 25n);
    await expect(token.connect(alice).transfer(bob.address, 10n))
      .to.emit(token, "Transfer").withArgs(alice.address, bob.address, 10n);
    await expect(token.connect(alice).transfer(bob.address, 0n))
      .to.emit(token, "Transfer").withArgs(alice.address, bob.address, 0n);
    expect(await token.totalSupply()).to.equal(25n);
    expect(await token.balanceOf(bob.address)).to.equal(10n);
  });

  it("rejects minting by anyone other than the owner", async function () {
    const { token, alice, stranger } = await deploy();
    await expect(token.connect(stranger).mint(alice.address, 1n))
      .to.be.revertedWith("Ownable: caller is not the owner");
  });
});
