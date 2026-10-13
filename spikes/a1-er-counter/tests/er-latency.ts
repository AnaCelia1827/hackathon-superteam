import * as anchor from "@coral-xyz/anchor";
import { Program, web3 } from "@coral-xyz/anchor";
import { PublicCounter } from "../target/types/public_counter";
import { LAMPORTS_PER_SOL } from "@solana/web3.js";
import { GetCommitmentSignature } from "@magicblock-labs/ephemeral-rollups-sdk";
import * as fs from "fs";
import * as path from "path";

const COUNTER_SEED = "counter";
const BASE_STEPS = Number(process.env.A1_BASE_STEPS ?? 10);
const ER_STEPS = Number(process.env.A1_ER_STEPS ?? 100);
const TEST_COMMIT_LIMIT = process.env.A1_TEST_COMMIT_LIMIT === "1";

function percentile(sorted: number[], p: number): number {
  if (sorted.length === 0) return 0;
  const idx = Math.min(sorted.length - 1, Math.max(0, Math.ceil((p / 100) * sorted.length) - 1));
  return sorted[idx];
}

function stats(samples: number[]) {
  const sorted = [...samples].sort((a, b) => a - b);
  const sum = sorted.reduce((a, b) => a + b, 0);
  return {
    n: sorted.length,
    min: sorted[0] ?? 0,
    p50: percentile(sorted, 50),
    p95: percentile(sorted, 95),
    max: sorted[sorted.length - 1] ?? 0,
    mean: sorted.length ? Math.round((sum / sorted.length) * 100) / 100 : 0,
  };
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

// Local validators occasionally report "already been processed" when a signed tx is
// re-submitted. Treat it as success; the write already landed.
async function sendWithDupRetry(fn: () => Promise<string>, label: string): Promise<string> {
  try {
    return await fn();
  } catch (e) {
    const msg = String(e);
    if (msg.includes("already been processed")) {
      console.log(`  (${label}: duplicate tx ignored)`);
      return "";
    }
    throw e;
  }
}

describe("a1-er-counter", () => {
  const provider = new anchor.AnchorProvider(
    new anchor.web3.Connection(
      process.env.PROVIDER_ENDPOINT || process.env.ANCHOR_PROVIDER_URL || "http://localhost:8899",
      { wsEndpoint: process.env.WS_ENDPOINT || undefined, commitment: "confirmed" },
    ),
    anchor.Wallet.local(),
  );
  anchor.setProvider(provider);

  const erProvider = new anchor.AnchorProvider(
    new anchor.web3.Connection(process.env.EPHEMERAL_PROVIDER_ENDPOINT || "http://localhost:7799", {
      wsEndpoint: process.env.EPHEMERAL_WS_ENDPOINT || undefined,
      commitment: "confirmed",
    }),
    anchor.Wallet.local(),
  );

  const program = anchor.workspace.PublicCounter as Program<PublicCounter>;
  const programEr = new Program<PublicCounter>(program.idl as any, erProvider);
  const [counterPda] = anchor.web3.PublicKey.findProgramAddressSync(
    [Buffer.from(COUNTER_SEED)],
    program.programId,
  );
  const validator = new web3.PublicKey(
    process.env.VALIDATOR || "mAGicPQYBMvcYveUZA5F5UNNwyHvfYh5xkLS2Fr1mev",
  );

  const result: Record<string, unknown> = {
    spike: "A1",
    generated_at: new Date().toISOString(),
    base_endpoint: provider.connection.rpcEndpoint,
    er_endpoint: erProvider.connection.rpcEndpoint,
    program_id: program.programId.toString(),
    counter_pda: counterPda.toString(),
    validator: validator.toString(),
    base_steps: BASE_STEPS,
    er_steps: ER_STEPS,
  };

  it("measures base vs ER increment latency, commit and undelegate", async () => {
    const wallet = provider.wallet as anchor.Wallet;
    console.log("base:", provider.connection.rpcEndpoint, "er:", erProvider.connection.rpcEndpoint);
    console.log("wallet:", wallet.publicKey.toString());

    const balance = await provider.connection.getBalance(wallet.publicKey);
    if (balance < 5 * LAMPORTS_PER_SOL) {
      try {
        const sig = await provider.connection.requestAirdrop(wallet.publicKey, 100 * LAMPORTS_PER_SOL);
        await provider.connection.confirmTransaction(sig);
      } catch (e) {
        console.warn("airdrop failed (fund the wallet manually if this is not localnet):", String(e));
      }
    }

    // 1. initialize on base
    console.log("-> initialize");
    await sendWithDupRetry(
      () =>
        program.methods
          .initialize()
          .accounts({ user: wallet.publicKey })
          .rpc({ skipPreflight: true, commitment: "confirmed" }),
      "initialize",
    );

    // 2. base-layer increments
    console.log(`-> ${BASE_STEPS} base increments`);
    const baseSamples: number[] = [];
    for (let i = 0; i < BASE_STEPS; i++) {
      const t0 = performance.now();
      await sendWithDupRetry(
        () =>
          program.methods
            .increment(new anchor.BN(i))
            .accounts({ counter: counterPda })
            .rpc({ skipPreflight: true, commitment: "confirmed" }),
        `base increment ${i}`,
      );
      baseSamples.push(performance.now() - t0);
    }

    // 3. delegate to ER
    console.log("-> delegate");
    const delStart = performance.now();
    await sendWithDupRetry(
      () =>
        program.methods
          .delegate()
          .accounts({ payer: wallet.publicKey, pda: counterPda })
          .remainingAccounts([{ pubkey: validator, isSigner: false, isWritable: false }])
          .rpc({ skipPreflight: true, commitment: "confirmed" }),
      "delegate",
    );
    result.delegate_ms = performance.now() - delStart;
    await sleep(3000);

    // 4. ER increments (these are NOT commits)
    console.log(`-> ${ER_STEPS} ER increments`);
    const erSamples: number[] = [];
    for (let i = 0; i < ER_STEPS; i++) {
      const t0 = performance.now();
      await sendWithDupRetry(
        () =>
          programEr.methods
            .increment(new anchor.BN(i))
            .accounts({ counter: counterPda })
            .rpc(),
        `er increment ${i}`,
      );
      erSamples.push(performance.now() - t0);
    }

    // 5. commit (checkpoint) on ER + await base-layer commitment signature
    console.log("-> commit");
    const commitStart = performance.now();
    const commitSig = await sendWithDupRetry(
      () =>
        programEr.methods
          .commit()
          .accounts({ payer: erProvider.wallet.publicKey })
          .rpc(),
      "commit",
    );
    result.commit_ms = performance.now() - commitStart;

    const settleStart = performance.now();
    const baseCommitSig = commitSig
      ? await GetCommitmentSignature(commitSig, erProvider.connection)
      : null;
    result.commit_settle_ms = performance.now() - settleStart;
    result.commit_signature = baseCommitSig ? baseCommitSig.toString() : null;

    const expected = BASE_STEPS + ER_STEPS;
    await sleep(1000);
    const afterCommit = await program.account.counter.fetch(counterPda);
    result.count_after_commit = Number(afterCommit.count);

    // 6. commit-and-undelegate (terminal)
    console.log("-> undelegate");
    const undelCommitment = process.env.A1_UNDELEGATE_COMMITMENT || "confirmed";
    const undelStart = performance.now();
    const undelSig = await sendWithDupRetry(
      () =>
        programEr.methods
          .undelegate()
          .accounts({ payer: erProvider.wallet.publicKey })
          .rpc({ commitment: undelCommitment as anchor.web3.Commitment }),
      "undelegate",
    );
    result.undelegate_ms = performance.now() - undelStart;
    result.undelegate_commitment = undelCommitment;

    // How long after the ER `.rpc()` returns does the BASE layer actually revert
    // ownership back to the program? Separates "ER rpc confirmation" from "base finalization".
    const pollStart = performance.now();
    let baseOwnerRevertedMs: number | null = null;
    const ownerSamples: Array<[number, string]> = [];
    for (let j = 0; j < 80; j++) {
      const ai = await provider.connection.getAccountInfo(counterPda);
      const owner = ai ? ai.owner.toBase58() : "none";
      if (j % 10 === 0) {
        ownerSamples.push([Math.round(performance.now() - pollStart), owner]);
      }
      if (ai && ai.owner.toBase58() === program.programId.toBase58()) {
        baseOwnerRevertedMs = Math.round(performance.now() - pollStart);
        break;
      }
      await sleep(500);
    }
    result.base_owner_reverted_ms = baseOwnerRevertedMs;
    result.base_owner_samples = ownerSamples;
    console.log(
      `undelegate rpc=${Math.round(result.undelegate_ms as number)}ms, base owner reverted after ${baseOwnerRevertedMs}ms`,
    );

    const afterUndelegate = await program.account.counter.fetch(counterPda);
    result.count_after_undelegate = Number(afterUndelegate.count);
    result.state_returned_to_base = Number(afterUndelegate.count) === expected;
    result.count_matches_expected = Number(afterUndelegate.count) === expected;
    result.expected_count = expected;
    result.undelegate_signature = undelSig || null;

    // 7. optional: reproduce the no-fee-payer commit limit (>= 11 plain commits)
    if (TEST_COMMIT_LIMIT) {
      const attempts: { attempt: number; ok: boolean; error?: string }[] = [];
      for (let i = 1; i <= 11; i++) {
        try {
          await programEr.methods
            .commit()
            .accounts({ payer: erProvider.wallet.publicKey })
            .rpc({ skipPreflight: true, commitment: "confirmed" });
          attempts.push({ attempt: i, ok: true });
        } catch (e) {
          attempts.push({ attempt: i, ok: false, error: String(e).slice(0, 200) });
          break;
        }
        await sleep(500);
      }
      result.commit_limit_attempts = attempts;
    }

    const baseStats = stats(baseSamples);
    const erStats = stats(erSamples);
    result.base_increment_stats = baseStats;
    result.er_increment_stats = erStats;
    result.speedup_p50 = baseStats.p50 && erStats.p50 ? Math.round((baseStats.p50 / erStats.p50) * 100) / 100 : null;

    const resultsDir = path.join(__dirname, "..", "results");
    fs.mkdirSync(resultsDir, { recursive: true });
    const outPath = path.join(resultsDir, "a1-er-counter.json");
    fs.writeFileSync(outPath, JSON.stringify(result, null, 2) + "\n");

    console.log("\n=== A1 results ===");
    console.log(JSON.stringify(result, null, 2));
    console.log(`\nwritten to ${outPath}`);

    if (!result.state_returned_to_base) {
      throw new Error(
        `state did not return to base: expected ${expected}, got ${result.count_after_undelegate}`,
      );
    }
  });
});
