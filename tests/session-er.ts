import * as anchor from "@coral-xyz/anchor";
import { Program, BN, web3 } from "@coral-xyz/anchor";
import { LooprailSession } from "../target/types/looprail_session";
import { GetCommitmentSignature } from "@magicblock-labs/ephemeral-rollups-sdk";
import { randomBytes } from "node:crypto";

const SESSION_SEED = "session";
const N_STEPS = Number(process.env.A5_ER_STEPS ?? 50);

function arr(n: number, len = 32): number[] {
  const b = Buffer.alloc(len);
  b.writeUInt32BE(n, 0);
  return Array.from(b);
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

// gated: run against a live base validator + ER (see scripts/local-env.sh)
describe("looprail-session (ER integration)", () => {
  it("delegate -> record -> checkpoint -> close_and_undelegate", async function () {
    if (process.env.RUN_ER_TESTS !== "1") {
      this.skip();
      return;
    }

    const provider = new anchor.AnchorProvider(
      new anchor.web3.Connection(process.env.PROVIDER_ENDPOINT || "http://localhost:8899", {
        commitment: "confirmed",
      }),
      anchor.Wallet.local(),
    );
    anchor.setProvider(provider);

    const erProvider = new anchor.AnchorProvider(
      new anchor.web3.Connection(process.env.EPHEMERAL_PROVIDER_ENDPOINT || "http://localhost:7799", {
        commitment: "confirmed",
      }),
      anchor.Wallet.local(),
    );

    const program = anchor.workspace.LooprailSession as Program<LooprailSession>;
    const programEr = new Program<LooprailSession>(program.idl as any, erProvider);

    const owner = provider.wallet.publicKey;
    const authority = anchor.Wallet.local().payer;
    const sid = Array.from(randomBytes(32));
    const [sessionPda] = anchor.web3.PublicKey.findProgramAddressSync(
      [Buffer.from(SESSION_SEED), owner.toBuffer(), Buffer.from(sid)],
      program.programId,
    );
    const validator = new web3.PublicKey(
      process.env.VALIDATOR || "mAGicPQYBMvcYveUZA5F5UNNwyHvfYh5xkLS2Fr1mev",
    );

    const provider0 = anchor.web3.Keypair.generate().publicKey;

    // 1. init on base
    await program.methods
      .initSession(sid, arr(2), authority.publicKey, new BN(1_000_000), [provider0], [new BN(1_000_000)])
      .accounts({ owner, session: sessionPda, systemProgram: web3.SystemProgram.programId })
      .rpc({ skipPreflight: true, commitment: "confirmed" });

    // 2. delegate
    await program.methods
      .delegateSession(sid)
      .accounts({ owner, session: sessionPda })
      .remainingAccounts([{ pubkey: validator, isSigner: false, isWritable: false }])
      .rpc({ skipPreflight: true, commitment: "confirmed" });
    await sleep(3000);

    // 3. record on ER
    for (let i = 0; i < N_STEPS; i++) {
      await programEr.methods
        .recordStep(owner, sid, i, 0, 0, new BN(10), 5, 0, false)
        .accounts({ session: sessionPda, authority: authority.publicKey })
        .signers([authority])
        .rpc();
    }

    // 4. checkpoint (commit)
    const commitSig = await programEr.methods
      .checkpoint(owner, sid)
      .accounts({ payer: erProvider.wallet.publicKey, session: sessionPda })
      .rpc({ skipPreflight: true, commitment: "confirmed" });
    await GetCommitmentSignature(commitSig, erProvider.connection);
    await sleep(1000);
    const afterCommit = await program.account.session.fetch(sessionPda);
    if (Number(afterCommit.stepCount) !== N_STEPS) {
      throw new Error(`step_count after commit: expected ${N_STEPS}, got ${afterCommit.stepCount}`);
    }

    // 5. terminal close_and_undelegate
    await programEr.methods
      .closeAndUndelegate(owner, sid)
      .accounts({ payer: erProvider.wallet.publicKey, session: sessionPda })
      .rpc({ skipPreflight: true, commitment: "confirmed" });
    await sleep(1000);
    const afterClose = await program.account.session.fetch(sessionPda);
    if (afterClose.status !== 1) {
      throw new Error(`status after close: expected 1, got ${afterClose.status}`);
    }
    if (Number(afterClose.stepCount) !== N_STEPS || afterClose.spent.toNumber() !== N_STEPS * 10) {
      throw new Error(`final ledger mismatch: count=${afterClose.stepCount}, spent=${afterClose.spent}`);
    }
  });
});
