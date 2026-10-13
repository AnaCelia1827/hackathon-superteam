import * as anchor from "@coral-xyz/anchor";
import { Program, BN } from "@coral-xyz/anchor";
import { PublicKey, Keypair, SystemProgram, LAMPORTS_PER_SOL } from "@solana/web3.js";
import { expect } from "chai";
import { LooprailSession } from "../target/types/looprail_session";

const SESSION_SEED = "session";
const RING_CAPACITY = 64;
const STATUS_OPEN = 0;
const STATUS_ABORTED = 2;

function bytes32(n: number): number[] {
  const b = Buffer.alloc(32);
  b.writeUInt32BE(n, 0);
  return Array.from(b);
}

async function expectProgramError(promise: Promise<unknown>, pattern: RegExp): Promise<void> {
  try {
    await promise;
  } catch (error) {
    expect(String(error)).to.match(pattern);
    return;
  }
  throw new Error(`Expected program error matching ${pattern}`);
}

describe("looprail-session (local validator)", () => {
  const provider = anchor.AnchorProvider.env();
  anchor.setProvider(provider);
  const program = anchor.workspace.LooprailSession as Program<LooprailSession>;
  const owner = (provider.wallet as anchor.Wallet).payer;

  function pda(sid: number): PublicKey {
    const [p] = PublicKey.findProgramAddressSync(
      [Buffer.from(SESSION_SEED), owner.publicKey.toBuffer(), Buffer.from(bytes32(sid))],
      program.programId,
    );
    return p;
  }

  async function init(sid: number, authority: PublicKey, budget: number, providers: PublicKey[], allocations: number[]) {
    const sessionPda = pda(sid);
    await program.methods
      .initSession(bytes32(sid), bytes32(1000 + sid), authority, new BN(budget), providers, allocations.map((a) => new BN(a)))
      .accounts({ owner: owner.publicKey, session: sessionPda, systemProgram: SystemProgram.programId })
      .rpc();
    return sessionPda;
  }

  async function record(sid: number, sessionPda: PublicKey, authority: Keypair, stepIdx: number, providerIdx: number, cost: number) {
    return program.methods
      .recordStep(owner.publicKey, bytes32(sid), stepIdx, 0, providerIdx, new BN(cost), 5, 0, false)
      .accounts({ session: sessionPda, authority: authority.publicKey })
      .signers([authority])
      .rpc();
  }

  before(async () => {
    const bal = await provider.connection.getBalance(owner.publicKey);
    if (bal < LAMPORTS_PER_SOL) {
      const sig = await provider.connection.requestAirdrop(owner.publicKey, 100 * LAMPORTS_PER_SOL);
      await provider.connection.confirmTransaction(sig);
    }
  });

  it("initializes a session with providers and allocations", async () => {
    const authority = Keypair.generate();
    const providers = [Keypair.generate().publicKey, Keypair.generate().publicKey];
    const sessionPda = await init(1, authority.publicKey, 100_000, providers, [60_000, 40_000]);

    const session = await program.account.session.fetch(sessionPda);
    expect(session.owner.toString()).to.equal(owner.publicKey.toString());
    expect(session.authority.toString()).to.equal(authority.publicKey.toString());
    expect(session.budgetTotal.toNumber()).to.equal(100_000);
    expect(session.status).to.equal(STATUS_OPEN);
    expect(session.channelCount).to.equal(2);
    expect(session.stepCount).to.equal(0);
  });

  it("rejects a budget overrun", async () => {
    const authority = Keypair.generate();
    const sessionPda = await init(2, authority.publicKey, 1_000, [Keypair.generate().publicKey], [1_000]);
    await expectProgramError(record(2, sessionPda, authority, 0, 0, 1_001), /0x1779|budget/i);
  });

  it("rejects a provider allocation overrun", async () => {
    const authority = Keypair.generate();
    const sessionPda = await init(3, authority.publicKey, 10_000, [Keypair.generate().publicKey], [500]);
    await expectProgramError(record(3, sessionPda, authority, 0, 0, 501), /0x177A|allocation/i);
  });

  it("rejects an out-of-order step_idx", async () => {
    const authority = Keypair.generate();
    const sessionPda = await init(4, authority.publicKey, 10_000, [Keypair.generate().publicKey], [10_000]);
    await expectProgramError(record(4, sessionPda, authority, 1, 0, 1), /0x1775|step_idx|monotonic/i);
  });

  it("rejects a wrong signer", async () => {
    const authority = Keypair.generate();
    const impostor = Keypair.generate();
    const sessionPda = await init(5, authority.publicKey, 10_000, [Keypair.generate().publicKey], [10_000]);
    await expectProgramError(
      program.methods
        .recordStep(owner.publicKey, bytes32(5), 0, 0, 0, new BN(1), 5, 0, false)
        .accounts({ session: sessionPda, authority: impostor.publicKey })
        .signers([impostor])
        .rpc(),
      /0x1773|authority/i,
    );
  });

  it("aborts and blocks further steps", async () => {
    const authority = Keypair.generate();
    const sessionPda = await init(6, authority.publicKey, 10_000, [Keypair.generate().publicKey], [10_000]);

    await record(6, sessionPda, authority, 0, 0, 1);
    await program.methods.abort(owner.publicKey, bytes32(6)).accounts({ signer: owner.publicKey, session: sessionPda }).rpc();

    const session = await program.account.session.fetch(sessionPda);
    expect(session.status).to.equal(STATUS_ABORTED);
    await expectProgramError(record(6, sessionPda, authority, 1, 0, 1), /0x1774|not open/i);
  });

  it("wraps the ring buffer and keeps the last K steps", async () => {
    const authority = Keypair.generate();
    const sessionPda = await init(7, authority.publicKey, 1_000_000, [Keypair.generate().publicKey], [1_000_000]);

    const total = RING_CAPACITY + 5;
    for (let i = 0; i < total; i++) {
      await record(7, sessionPda, authority, i, 0, 1);
    }

    const session = await program.account.session.fetch(sessionPda);
    expect(session.stepCount).to.equal(total);
    expect(session.steps[0].stepIdx).to.equal(RING_CAPACITY);
    expect(session.steps[4].stepIdx).to.equal(total - 1);
    expect(session.spent.toNumber()).to.equal(total);
  });
});
