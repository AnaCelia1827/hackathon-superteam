import type { ChainPort, OpenSession, Step } from "./types.ts";

type Queued = { step: Step; state: "queued" | "sending" | "confirmed" | "failed"; signature?: string; error?: string };
type Session = { input: OpenSession; address: string; status: "open" | "closing" | "closed" | "aborted"; records: Map<number, Queued>; next: number; worker?: Promise<void>; checkpointCount: number; signatures: string[] };

export class LedgerError extends Error {
  status: number;
  constructor(status: number, message: string) { super(message); this.status = status; }
}

function integer(value: unknown, max = Number.MAX_SAFE_INTEGER): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0 && value <= max;
}
function object(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}
function str(value: unknown): value is string { return typeof value === "string" && value.length > 0; }

export function parseOpen(value: unknown): OpenSession {
  if (!object(value) || !/^[0-9a-f]{64}$/.test(String(value.session_id)) || !/^[0-9a-f]{64}$/.test(String(value.policy_hash)) ||
      !integer(value.budget_usdc_base_units) || !str(value.owner) || !str(value.authority) ||
      !Array.isArray(value.tools) || value.tools.length > 255 || !value.tools.every(str) || new Set(value.tools).size !== value.tools.length ||
      !Array.isArray(value.providers) || value.providers.length > 8 || !value.providers.every(str) || new Set(value.providers).size !== value.providers.length ||
      !Array.isArray(value.provider_pubkeys) || value.provider_pubkeys.length !== value.providers.length || !value.provider_pubkeys.every(str) || new Set(value.provider_pubkeys).size !== value.provider_pubkeys.length ||
      !Array.isArray(value.provider_allocations_usdc_base_units) || value.provider_allocations_usdc_base_units.length !== value.providers.length ||
      !value.provider_allocations_usdc_base_units.every(amount => integer(amount)) ||
      value.provider_allocations_usdc_base_units.reduce((sum: number, amount: number) => sum + amount, 0) > value.budget_usdc_base_units) {
    throw new LedgerError(400, "Invalid session: require 32-byte hex IDs, integer budget, owner, authority, tools and up to 8 providers with unique pubkeys and allocations within budget");
  }
  return value as OpenSession;
}

export function parseStep(value: unknown, sessionId: string): Step {
  if (!object(value) || value.version !== 1 || value.session_id !== sessionId ||
      !integer(value.step_index, 0xffffffff) || !str(value.tool) || !str(value.provider) ||
      !["success", "error", "denied", "cache_hit"].includes(String(value.outcome)) ||
      !integer(value.cost_usdc_base_units) || !integer(value.provider_latency_ms, 0xffffffff) ||
      !(value.looprail_overhead_ms === null || integer(value.looprail_overhead_ms, 0xffffffff)) ||
      typeof value.cache_hit !== "boolean" || !str(value.occurred_at) ||
      Number.isNaN(Date.parse(String(value.occurred_at))) ||
      (value.reason !== undefined && typeof value.reason !== "string") ||
      (value.retry_count !== undefined && !integer(value.retry_count)) ||
      (value.retry_backoff_ms !== undefined && !integer(value.retry_backoff_ms))) {
    throw new LedgerError(400, "Invalid StepRecord v1");
  }
  return value as Step;
}

export class Ledger {
  private sessions = new Map<string, Session>();
  private chain: ChainPort;
  constructor(chain: ChainPort) { this.chain = chain; }

  async open(input: OpenSession) {
    if (this.sessions.has(input.session_id)) throw new LedgerError(409, "Session already exists");
    const opened = await this.chain.open(input);
    const session: Session = { input, address: opened.address, status: "open", records: new Map(), next: 0, checkpointCount: 0, signatures: [opened.signature] };
    this.sessions.set(input.session_id, session);
    try { session.signatures.push(await this.chain.delegate(input, opened.address)); }
    catch (error) { this.sessions.delete(input.session_id); throw error; }
    return this.snapshot(input.session_id);
  }

  enqueue(id: string, step: Step) {
    const s = this.get(id);
    if (s.status !== "open") throw new LedgerError(409, "Session is not open");
    if (!s.input.tools.includes(step.tool) || !s.input.providers.includes(step.provider)) throw new LedgerError(400, "Unknown tool or provider");
    const prior = s.records.get(step.step_index);
    if (prior) {
      if (JSON.stringify(prior.step) !== JSON.stringify(step)) throw new LedgerError(409, "Conflicting step_index");
      if (prior.state === "failed") { prior.state = "queued"; prior.error = undefined; this.start(s); }
      return { step_index: step.step_index, state: prior.state, signature: prior.signature ?? null };
    }
    if (step.step_index !== s.records.size) throw new LedgerError(409, `Expected step_index ${s.records.size}`);
    s.records.set(step.step_index, { step, state: "queued" });
    this.start(s);
    return { step_index: step.step_index, state: "queued", signature: null };
  }

  private start(s: Session) {
    if (s.worker) return;
    s.worker = this.process(s).finally(() => {
      s.worker = undefined;
      const next = s.records.get(s.next);
      if (next?.state === "queued" && s.status !== "aborted") this.start(s);
    });
  }

  private async process(s: Session) {
    while (s.status !== "aborted") {
      const item = s.records.get(s.next);
      if (!item || item.state !== "queued") return;
      item.state = "sending";
      try {
        // A prior send can land on the ER even when its confirmation RPC fails.
        // Read the on-chain count before resubmitting that step.
        const before = await this.chain.count(s.address);
        if (before === s.next) item.signature = await this.chain.record(s.input, s.address, item.step);
        else if (before !== s.next + 1) throw new Error(`ER count mismatch before send: expected ${s.next} or ${s.next + 1}, got ${before}`);
        const count = await this.chain.count(s.address);
        if (count !== s.next + 1) throw new Error(`ER count mismatch: expected ${s.next + 1}, got ${count}`);
        item.state = "confirmed";
        s.next++;
      } catch (error) {
        item.state = "failed";
        item.error = String(error);
        return;
      }
    }
  }

  private async drain(s: Session) {
    while (s.worker) await s.worker;
    if (s.next !== s.records.size) throw new LedgerError(503, `Step ${s.next} failed; retry the identical step before closing`);
    const count = await this.chain.count(s.address);
    if (count !== s.next) throw new LedgerError(503, `ER count mismatch: expected ${s.next}, got ${count}`);
  }

  async checkpoint(id: string) {
    const s = this.get(id);
    if (s.status !== "open") throw new LedgerError(409, "Session is not open");
    if (s.checkpointCount >= 2) throw new LedgerError(409, "Checkpoint limit reached");
    await this.drain(s);
    const signature = await this.chain.checkpoint(s.input, s.address);
    s.checkpointCount++;
    s.signatures.push(signature);
    return this.snapshot(id);
  }

  async close(id: string) {
    const s = this.get(id);
    if (s.status === "closed") return this.snapshot(id);
    if (s.status !== "open") throw new LedgerError(409, "Session is not open");
    s.status = "closing";
    try {
      await this.drain(s);
      s.signatures.push(await this.chain.close(s.input, s.address));
      s.status = "closed";
    } catch (error) { s.status = "open"; throw error; }
    return this.snapshot(id);
  }

  async abort(id: string) {
    const s = this.get(id);
    if (s.status === "aborted") return this.snapshot(id);
    if (s.status === "closed") throw new LedgerError(409, "Session is closed");
    s.status = "aborted";
    try {
      if (s.worker) await s.worker;
      s.signatures.push(await this.chain.abort(s.input, s.address));
    } catch (error) { s.status = "open"; throw error; }
    return this.snapshot(id);
  }

  snapshot(id: string) {
    const s = this.get(id);
    return { session_id: id, address: s.address, status: s.status, queued_count: s.records.size,
      confirmed_count: s.next, checkpoint_count: s.checkpointCount,
      steps: [...s.records.values()].map(r => ({ step_index: r.step.step_index, state: r.state, signature: r.signature ?? null, error: r.error ?? null })),
      signatures: [...s.signatures] };
  }

  private get(id: string): Session {
    const s = this.sessions.get(id);
    if (!s) throw new LedgerError(404, "Session not found");
    return s;
  }
}
