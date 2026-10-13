import assert from "node:assert/strict";
import { after, test } from "node:test";
import { createLedgerServer } from "../src/http.ts";
import { Ledger } from "../src/ledger.ts";
import { LedgerClient } from "../src/client.ts";
import type { ChainPort, OpenSession, Step } from "../src/types.ts";

const id = "ab".repeat(32);
const input: OpenSession = { session_id: id, policy_hash: "cd".repeat(32), budget_usdc_base_units: 100000, owner: "owner", authority: "authority", tools: ["tool"], providers: ["provider"] };
const step = (n: number): Step => ({ version: 1, session_id: id, step_index: n, tool: "tool", provider: "provider", outcome: "success", cost_usdc_base_units: 1000, provider_latency_ms: 10, looprail_overhead_ms: null, cache_hit: false, occurred_at: "2026-10-13T00:00:00Z" });

class FakeChain implements ChainPort {
  steps: number[] = [];
  failAt = -1;
  countFailureAfter = -1;
  closedAt = -1;
  async open() { return { address: "pda", signature: "init" }; }
  async delegate() { return "delegate"; }
  async record(_input: OpenSession, _address: string, event: Step) {
    await new Promise(resolve => setTimeout(resolve, 2));
    if (event.step_index === this.failAt) throw new Error("temporary ER outage");
    assert.equal(event.step_index, this.steps.length);
    this.steps.push(event.step_index);
    return `record-${event.step_index}`;
  }
  async count() {
    if (this.steps.length === this.countFailureAfter) {
      this.countFailureAfter = -1;
      throw new Error("confirmation RPC unavailable");
    }
    return this.steps.length;
  }
  async checkpoint() { return "checkpoint"; }
  async close() { this.closedAt = this.steps.length; return "close"; }
  async abort() { return "abort"; }
}

const chain = new FakeChain();
const server = createLedgerServer(new Ledger(chain));
await new Promise<void>(resolve => server.listen(0, "127.0.0.1", resolve));
after(() => server.close());
const address = server.address();
assert.ok(address && typeof address !== "string");
const client = new LedgerClient(`http://127.0.0.1:${address.port}`);

test("50 ordered steps, idempotent retry and close barrier", async () => {
  await client.open(input);
  const responses = await Promise.all(Array.from({ length: 50 }, (_, i) => client.step(id, step(i))));
  assert.equal(responses.length, 50);
  await client.step(id, step(12));
  await assert.rejects(client.step(id, { ...step(12), cost_usdc_base_units: 2 }), /409/);
  const result = await client.close(id);
  assert.equal(result.confirmed_count, 50);
  assert.equal(result.queued_count, 50);
  assert.deepEqual(chain.steps, Array.from({ length: 50 }, (_, i) => i));
  assert.equal(chain.closedAt, 50);
  assert.equal((await client.close(id)).status, "closed");
});

test("failed step blocks close until identical retry succeeds", async () => {
  const other = { ...input, session_id: "ef".repeat(32) };
  const localChain = new FakeChain();
  localChain.failAt = 0;
  const localServer = createLedgerServer(new Ledger(localChain));
  await new Promise<void>(resolve => localServer.listen(0, "127.0.0.1", resolve));
  const location = localServer.address();
  assert.ok(location && typeof location !== "string");
  const localClient = new LedgerClient(`http://127.0.0.1:${location.port}`);
  try {
    await localClient.open(other);
    const event = { ...step(0), session_id: other.session_id };
    await localClient.step(other.session_id, event);
    await assert.rejects(localClient.close(other.session_id), /503/);
    localChain.failAt = -1;
    await localClient.step(other.session_id, event);
    assert.equal((await localClient.close(other.session_id)).confirmed_count, 1);
  } finally { localServer.close(); }
});

test("retry observes an already landed ER write", async () => {
  const another = { ...input, session_id: "ac".repeat(32) };
  const localChain = new FakeChain();
  localChain.countFailureAfter = 1;
  const localServer = createLedgerServer(new Ledger(localChain));
  await new Promise<void>(resolve => localServer.listen(0, "127.0.0.1", resolve));
  const location = localServer.address();
  assert.ok(location && typeof location !== "string");
  const localClient = new LedgerClient(`http://127.0.0.1:${location.port}`);
  try {
    await localClient.open(another);
    const event = { ...step(0), session_id: another.session_id };
    await localClient.step(another.session_id, event);
    await assert.rejects(localClient.close(another.session_id), /503/);
    await localClient.step(another.session_id, event);
    assert.equal((await localClient.close(another.session_id)).confirmed_count, 1);
    assert.deepEqual(localChain.steps, [0]);
  } finally { localServer.close(); }
});
