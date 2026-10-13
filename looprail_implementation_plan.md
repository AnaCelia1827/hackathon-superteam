# LoopRail: detailed implementation plan (two people)

**Person A:** on-chain state and payments. **Person B:** runtime, policy, and demo.

Based on documentation for Solana Foundation pay-kit, Solana Payment Channels, and MagicBlock, consulted on October 12, 2026. Every task states the work, the approach, and its acceptance criteria.

---

## 0. Corrections to the original concept

1. **Pay-kit language.** The reviewed pay-kit is **Python** (v0.10.0, requires Python 3.11 or newer) and provides client and server support for x402 `upto` and MPP `session`. MagicBlock and Anchor use Rust/TypeScript. An equivalent TypeScript pay-kit package was not verified. The team selected Python for the runtime and TypeScript for the ledger service; spikes A2/A3 must confirm the payment integration details.
2. **One settlement is not exact.** Each payment channel settles with its recipient. Four providers mean four channels and four settlements, still fewer than 50 per-call payments. Say “N settlements, one per provider, instead of 50 payments.” A LoopRail gateway as the single recipient is an ADR-2 alternative.
3. **x402 `upto` may need on-chain transactions per call.** The client opens a channel with the authorized ceiling, the handler meters usage, and the gate settles the actual amount and refunds the remainder. Use `upto` for one-off calls; repeated traffic should use **MPP sessions**. Spike A2 must measure this.
4. **QuickNode MPP appears to settle on Tempo, not Solana.** Its CLI mentions a signed Tempo payment and a funded Tempo channel. Verify Solana USDC support before using it as a provider, or start with owned providers.
5. **Ephemeral Rollup limits shape the step log.** A delegated account without a fee payer stops after 10 commits. With a fee payer, it continues and starts paying commit fees from the 26th commit. Resizing a delegated PDA requires enough rent-exempt lamports and may require a delegated payer. Use a **fixed-size ring buffer** for `StepLog` and only a few commits per session, never one per step.
6. **The pay-kit client is restrictive by default.** It allows known stablecoins on mainnet only, with a $1 per-payment cap; unknown assets and non-mainnet networks require explicit permission. Configure test networks explicitly. These permissions can provide another defense below LoopRail's policy.
7. **Pay-kit changes quickly.** There were 10 releases between June 29 and October 2, 2026. Pin the exact version and expect breaking changes.

---

## 1. Shared tasks at the start

### J1: Contracts and ADRs (half a day, both people)

- **ADR-1 (language).** The team selected a **Python runtime and payments** plus a **TypeScript ledger service** for Anchor/MagicBlock. The dashboard is planned in Next.js; the current static dashboard is an early prototype. Spikes A2/A3 still validate pay-kit capabilities.
- **ADR-2 (channel topology).** Default MVP: one channel per provider. Alternative: LoopRail as the only recipient and gateway, paying the providers itself. That would enable a “one settlement” story and a take rate because MPP supports `fee_within`. Standard x402 facilitators settle to one address, so x402 is disabled automatically on those gates. The gateway adds custody and credit risk; defer it.
- **ADR-3 (PDA model).** See A5.
- **JSON Schema contracts** in `packages/contracts/`: `Policy`, `StepRecord`, `PaymentAdapter`, and `Metrics`. All USDC amounts use **integer base units (6 decimals)**, never floating point.
- **Acceptance:** Written ADRs (about one page each), versioned schemas, and one valid example of each schema.

### J2: Environments and pinned versions (half a day)

- Versions from MagicBlock documentation: Solana 3.1.9, Rust 1.89.0, Anchor 1.0.2, Node 24.10.0, Python 3.11 or newer, and `solana_pay_kit==0.10.0`. Pin everything with lockfiles.
- **Local network first:** pay-kit supports `solana_localnet` (hosted or local Surfpool sandbox); MagicBlock has a **local ER** at `localhost:7799`. This avoids devnet airdrop and availability issues.
- Keep keys in a file through `Signer.file` or environment variables, never in the repository. Pay-kit rejects the demo signer on mainnet, but this project should remain on localnet/devnet.
- **Acceptance:** `make dev` starts the validator, local ER, and stub services; CI runs lint and tests.

---

## 2. Person A: on-chain state and payments

### A1: Ephemeral Rollup spike (end-to-end counter)

- Clone MagicBlock's `counter/anchor` example. Initialize on the base layer, delegate, increment on the ER, then `commit` or `commit_and_undelegate`. Select the validator through `remaining_accounts` (the documentation lists public keys for Asia/EU/US/TEE devnet endpoints).
- Measure p50/p95 latency for 100 increments on ER versus base layer. Confirm that committed state returns to the base layer.
- **Acceptance:** Reproducible script, latency table, and notes on any delegation errors.

### A2: x402 `upto` spike

- Build a server with `require_usage` and an *operator signer* (required for `upto`). Use `PayKitClient` with `ClientPermissions` that explicitly allow the test network and set a cap.
- Measure **on-chain transactions per call**, authorized versus settled value, and refund.
- **Acceptance:** A “transactions per call” table and a decision on using `upto` for one-off calls only.

### A3: MPP `session` spike

- Create a server with `new_session`, reserve/commit metering routes (`session_routes`), an idle-close watchdog, and settlement on close. Settlement requires a configured signer and RPC; without them, closing only changes state and the signature is `null`. Use `ActiveSession` and `SessionConsumer` on the client.
- Run 50 metered requests in one session.
- **Acceptance:** 50 cumulative vouchers, a real on-chain `settledSignature`, and a count of open-plus-close transactions. Record behavior when the client disappears and idle-close runs.

### A4: Decision gate (A + B after the first block)

- Update the ADRs with spike measurements. If A3 fails, **fallback plan** is per-call x402 `upto` with measured costs. The narrative becomes “transparent per-call cost plus policy.” Confirm ADR-1 integration details.

### A5: Anchor program `looprail_session`

- **Fixed-size `Session` PDA** with seeds `["session", owner, session_id]`:
  - `owner`, `authority` (runtime key that writes on the ER), `session_id`, `policy_hash [u8;32]`.
  - `budget_total`, `spent`, `reserved` as `u64` USDC base units.
  - `step_count`, `status` (Open/Closing/Closed/Aborted), `opened_at`, `closed_at`.
  - `channels[N]` with channel public key and spend per provider; use a small fixed N, such as 8.
  - `steps[K]` ring buffer with `tool_id u8`, `provider_idx u8`, `cost u64`, `latency_ms u32`, `outcome u8`, and `cache_hit bool`. K around 64 covers the 50-step demo.
- **Instructions:** `init_session` (base), `delegate_session` (base, validator from the first `remaining_accounts`), `record_step` (ER), `checkpoint` (ER, `commit`), `close_and_undelegate` (ER), and `abort` (kill switch).
- **`record_step` checks:** `signer == authority`; `status == Open`; monotonic `step_idx`; `spent + cost <= budget_total`; write into the ring buffer.
- **Macros and SDK:** `#[ephemeral]` on the module, `#[delegate]` on the delegation context, `#[commit]` on commit contexts, and `MagicIntentBundleBuilder` instead of deprecated `commit_accounts` and `commit_and_undelegate_accounts`. The undelegation callback discriminator `[196, 28, 41, 206, 48, 37, 51, 167]` is injected by `#[ephemeral]`.
- **Design caution:** Plan for a delegated fee payer and at most **two checkpoints plus one final commit** per session.
- **Optional hardening:** Magic Actions can run a base-layer instruction after commit. An instruction marked `#[action]` remains directly callable by any wallet, so it must verify the injected escrow signer.
- **Acceptance:** Anchor/Bankrun tests cover budget overrun, out-of-order `step_idx`, wrong signer, abort, full ring buffer, and delegate → record → commit → undelegate.

### A6: TypeScript ledger service and client

- Expose `POST /sessions`, `/sessions/:id/steps`, `/checkpoint`, `/close`, and `/abort`. Connect to base layer and ER. Use Magic Router's `ConnectionMagicRouter` or a fixed ER RPC for `record_step`.
- Queue `record_step` asynchronously so the agent loop does not wait for confirmation. Confirm all queued steps before `close`.
- **Acceptance:** 50 steps recorded in order with matching counts; retrying the same `step_idx` is idempotent.

### A7: Real `PaymentAdapter` (ChannelManager)

- Align the interface with B: `open(provider, allocation) → channel`, `reserve(channel, max) → reservation`, `commit(reservation, actual)`, `release(reservation)`, `close_all() → Settlement[]`.
- Implement `MppSessionAdapter` by default and `X402UptoAdapter` for one-off calls. Map adapter reserve/commit to pay-kit's side-channel reserve/commit.
- The ChannelManager receives per-provider deposit allocations from the Policy Engine.
- **Acceptance:** Voucher sums per channel equal settled amounts; `usdc_refunded = deposited - spent`; verify everything in the explorer.

### A8: Reconciliation and failures

- Test provider failure during a session, premature idle-close, repeated or out-of-order vouchers, and a runtime crash with open channels.
- Build a **reaper** process to close orphaned channels. This is the real financial kill switch.
- **Acceptance:** No funds remain stuck in any injected failure scenario.

### A9: Owned providers (pay-kit server)

- Provide three endpoints: market data, news/context, and an inference proxy. Protect each with `Gate.build(...)`. Streaming inference uses metered SSE helpers (`MeteredSseSession`).
- Document pricing and metering rules for each endpoint.
- **Acceptance:** The agent consumes all three with real payments, and the dashboard displays prices. Verify the settlement network before adding any external provider.

### A10: On-chain benchmark

- Build runners for two baselines (on-chain payment per call; x402 per call without ER) and LoopRail. Count transactions from RPC signatures and measure actual fees.
- Run at least 20 executions; report median and dispersion.
- **Acceptance:** Automatically generated CSV per run with `steps, tx_count, fees, usdc_*, p50, p95`.

---

## 3. Person B: runtime, policy, and demo

### B1: Spend Policy Engine

- **Pure API** without I/O: `evaluate(ctx, request) → Decision{allow | deny | cache_hit | fallback(provider), reason}`.
- Rules: task budget, per-provider `max_session_spend`, maximum price per call, retries with backoff, cache TTL, loop detection from repeated tool-and-arguments hashes, and kill switch based on error rate and budget use.
- Partition the budget by channel because each provider's channel requires a deposit. Output `allocations{provider: amount}`.
- **Reserve before spending:** `reserve → commit/release` so concurrent calls cannot exceed the budget.
- Store `policy_hash` as the hash of RFC 8785 canonical JSON in the PDA.
- **Acceptance:** Property tests under concurrency preserve `spent + reserved <= budget`; test every rule, including the policy example in the ideation document.

### B2: Agent loop and `ToolRegistry`

- A tool has a name, provider, pricing model, input schema, `idempotent` flag, and timeout.
- Per-step cycle: observe → decide → `policy.evaluate` → `reserve` → invoke → `commit/release` → record in ledger → emit event.
- Parallelize independent data requests, then run dependent inference sequentially.
- **Acceptance:** The loop runs offline with the B3 mock and respects every policy decision.

### B3: Deterministic mock and simulated providers

- Provide simulated adapters and providers with configurable latency distributions and injected failures.
- Standard scenario: **50 steps** = 20 data calls + 15 inference calls + 10 scraping/API calls + 5 state/coordination steps.
- **Acceptance:** CI runs the scenario in seconds and a fixed seed produces the same result.

### B4: Public SDK

- Match the ideation example: `new LoopRail({network, budget, state, payment})` and `rail.run({agent, tools, policy})`, adapted to the chosen language. `result.metrics` must come from ledger data and payment receipts, never hard-coded values.
- Typed errors: `BudgetExceeded`, `PolicyDenied`, `KillSwitchTripped`, and `SettlementFailed`.
- **Acceptance:** A short README example runs end to end.

### B5: Market intelligence agent

- Flow: monitor → detect event → open session → market data → news → inference classification → specialist tool/sub-agent → update thesis, risk, and recommendation.
- **Replay mode:** Record responses as cassettes so the demo does not rely on an LLM or network access on presentation day.
- **Acceptance:** A coherent 50-step report in live and replay modes.

### B6: Runtime ↔ ledger ↔ payment integration (main milestone)

- Connect B2 to A6's ledger service and A7's adapter. Test injected failures such as slow provider, payment error, and unavailable ledger.
- **Acceptance:** A real session has `usdc_authorized`, `usdc_spent`, `usdc_refunded`, and settlement count verified. Ledger, receipts, and dashboard show matching metrics.

### B7: Dashboard

- Stream events over SSE: cost and latency per step; remaining, authorized, reserved, and spent budget; policy decisions with reasons; timeline.
- Provide a kill-switch button that calls `abort`, plus explorer links for settlement signatures.
- **Acceptance:** A live session updates in real time, and abort closes its channels.

### B8: Benchmark metrics and narrative

- Separate **provider/LLM latency**, which LoopRail cannot control, from **LoopRail overhead** for policy, ledger, and payment.
- Calculate `estimated_savings` from A10's measured fees and label any mainnet projection as an estimate.
- **Acceptance:** Baseline-versus-LoopRail charts generated from CSV, without hand-entered numbers.

---

## 4. Shared final tasks

- **J3:** Script and record the video: problem → 50-step loop → metrics → business model.
- **J4:** README with setup, pinned versions, and honest limitations; rehearse with a recorded backup session.

## 5. Critical dependencies

```
J1 → (A1, A2, A3 | B1, B3) → A4 → (A5, A6, A7 | B2, B4) → B6 → (A9, A10 | B5, B7, B8) → J3, J4
```

The critical path is **A3 → A7 → B6**. If A3 is delayed, activate the A4 fallback.

## 6. Scope cuts if time runs short

Keep: (1) a 50-step loop with real settlement, (2) policy engine and kill switch, (3) dashboard with metrics, and (4) ER as ledger. Cut intelligent routing, model fallback, multi-agent coordination, the ADR-2b gateway, and SDK polish first.

## 7. Items not yet verified

- Whether a TypeScript pay-kit package supports `session` and `upto` equivalently to Python.
- Actual transaction counts for per-call `upto` and per-session MPP.
- QuickNode MPP's settlement network and availability of a Solana-settling external provider.
- Exact details of the MPP reserve/commit side channel.

## 8. Sources consulted

- Solana Foundation pay-kit: https://pypi.org/project/solana-pay-kit/
- Solana Payment Channels: https://solana.com/payment-channels
- MagicBlock Ephemeral Rollups quickstart: https://docs.magicblock.gg/pages/ephemeral-rollups-ers/how-to-guide/quickstart
- QuickNode agentic payments: https://www.quicknode.com/docs/build-with-ai/agentic-payments
