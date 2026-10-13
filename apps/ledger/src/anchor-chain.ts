import { readFileSync } from "node:fs";
import type { ChainPort, OpenSession, Step } from "./types.ts";

// This adapter binds to the A5 IDL once that program exists. Method argument and
// account names are the A5 interface contract documented in this service's README.
export async function anchorChainFromEnv(): Promise<ChainPort> {
  const anchor = await import("@coral-xyz/anchor");
  const web3 = await import("@solana/web3.js");
  const required = (key: string) => {
    const value = process.env[key];
    if (!value) throw new Error(`${key} is required`);
    return value;
  };
  const keypair = (path: string) => web3.Keypair.fromSecretKey(Uint8Array.from(JSON.parse(readFileSync(path, "utf8"))));
  const owner = keypair(required("LOOPRAIL_OWNER_KEYPAIR"));
  const authority = keypair(required("LOOPRAIL_AUTHORITY_KEYPAIR"));
  const idl = JSON.parse(readFileSync(required("LOOPRAIL_IDL"), "utf8"));
  const programId = new web3.PublicKey(idl.address);
  const base = new anchor.AnchorProvider(new web3.Connection(required("LOOPRAIL_BASE_RPC"), "confirmed"), new anchor.Wallet(owner), { commitment: "confirmed" });
  const er = new anchor.AnchorProvider(new web3.Connection(required("LOOPRAIL_ER_RPC"), "confirmed"), new anchor.Wallet(authority), { commitment: "confirmed" });
  const baseProgram = new anchor.Program(idl, base);
  const erProgram = new anchor.Program(idl, er);
  const validator = new web3.PublicKey(required("LOOPRAIL_ER_VALIDATOR"));
  const addresses = (input: OpenSession) => {
    if (input.owner !== owner.publicKey.toBase58() || input.authority !== authority.publicKey.toBase58()) throw new Error("Session signers do not match configured keypairs");
    return web3.PublicKey.findProgramAddressSync([Buffer.from("session"), owner.publicKey.toBuffer(), Buffer.from(input.session_id, "hex")], programId)[0];
  };
  const pda = (address: string) => new web3.PublicKey(address);
  const count = async (address: string) => {
    const account = await (erProgram.account as any).session.fetch(pda(address));
    return Number(account.stepCount);
  };
  return {
    async open(input) {
      const session = addresses(input);
      const signature = await (baseProgram.methods as any)
        .initSession([...Buffer.from(input.session_id, "hex")], [...Buffer.from(input.policy_hash, "hex")], new anchor.BN(input.budget_usdc_base_units), authority.publicKey)
        .accounts({ owner: owner.publicKey, session, systemProgram: web3.SystemProgram.programId }).rpc();
      return { address: session.toBase58(), signature };
    },
    async delegate(input, address) {
      addresses(input);
      return (baseProgram.methods as any).delegateSession()
        .accounts({ payer: owner.publicKey, session: pda(address) })
        .remainingAccounts([{ pubkey: validator, isSigner: false, isWritable: false }]).rpc();
    },
    async record(input, address, step) {
      const tool = input.tools.indexOf(step.tool);
      const provider = input.providers.indexOf(step.provider);
      if (tool < 0 || provider < 0) throw new Error("Unknown tool or provider");
      const outcome = { success: 0, error: 1, denied: 2, cache_hit: 3 }[step.outcome];
      return (erProgram.methods as any)
        .recordStep(step.step_index, tool, provider, new anchor.BN(step.cost_usdc_base_units), step.provider_latency_ms, outcome, step.cache_hit)
        .accounts({ authority: authority.publicKey, session: pda(address) }).rpc();
    },
    count,
    async checkpoint(_input, address) {
      return (erProgram.methods as any).checkpoint().accounts({ payer: authority.publicKey, session: pda(address) }).rpc();
    },
    async close(_input, address) {
      return (erProgram.methods as any).closeAndUndelegate().accounts({ payer: authority.publicKey, session: pda(address) }).rpc();
    },
    async abort(_input, address) {
      return (erProgram.methods as any).abort().accounts({ authority: authority.publicKey, session: pda(address) }).rpc();
    },
  };
}
