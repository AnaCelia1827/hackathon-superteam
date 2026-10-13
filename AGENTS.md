# AGENTS.md

LoopRail is a runtime + metered-payment layer for autonomous AI agents on Solana.
Hackathon repo with shared contracts, a Python runtime prototype, and a local dashboard. Person A's on-chain and payment services are not implemented yet.

## Sources of truth
- `looprail_implementation_plan.md` — task plan (J1-J4, A1-A10, B1-B8), pinned versions, constraints. Primary.
- `looprail_ideacao.pdf` — product/pitch context (architecture, policy example, demo script).
The original PDF is in Portuguese. Read the English implementation plan before starting any task; it names acceptance criteria per task.

## Architecture decisions
- **ADR-1 (decided):** Python runtime + payments (pay-kit MPP `session` server/client), TypeScript ledger sidecar for Anchor/MagicBlock. Python is the primary payment path; `upto` is server-side only (the high-level `PayKitClient` does not auto-pay `upto`).
- **ADR-2 (decided):** one payment channel per provider (not a single gateway). "1 settlement" is aspirational: with N providers there are N settlements (one per receiver). Prefer "N settlements instead of 50 payments".
- **ADR-3:** fixed-size `Session` PDA on the ER; see `docs/adr/`.

## Hard conventions (from the plan)
- All money is USDC base units (6 decimals) as **integers**, never float. Applies to contracts/schemas and the ledger.
- `policy_hash` = hash of canonical JSON per RFC 8785 (same scheme pay-kit uses); it is stored in the on-chain PDA.
- Planned commands (not yet implemented): `make dev` should bring up validator + local ER + stub services; CI runs lint + tests.
- Pin versions exactly: Solana 3.1.9, Rust 1.89.0, Anchor 1.0.2, Node 24.10.0, Python >= 3.11, `solana_pay_kit==0.10.0`.
  - Note: `anchor-cli 1.0.2` self-installs Agave **3.0.0/3.1.10**, not 3.1.9; ER SDK is `@magicblock-labs/ephemeral-rollups-sdk@0.16.2`, validator `@magicblock-labs/ephemeral-validator@0.14.10`.
- Devnet/local only. Never commit keys (use `Signer.file`/env); pay-kit refuses the demo signer on mainnet.

## Architecture / ownership (planned)
- Person A: on-chain + payments — Anchor program `looprail_session` (fixed-size `Session` PDA, `steps[K]` ring buffer), TS ledger service, `PaymentAdapter` (`open/reserve/commit/release/close_all`).
- Person B: runtime + policy + demo — pure-API Spend Policy Engine (`evaluate(ctx, request) -> Decision`), agent loop, `ToolRegistry`, deterministic mock, SDK, dashboard.
- Shared contracts as JSON Schema in `packages/contracts/`: `Policy`, `StepRecord`, `PaymentAdapter`, `Metrics`.

## Gotchas that will bite (verified 2026-10-13)
- **Docker on this host:** the shell user is in the `docker` group but it is not active here — run Docker as `sg docker -c '...'`. Containers need `--security-opt seccomp=unconfined --security-opt label=disable` because Agave `solana-test-validator` requires `io_uring`.
- **Local ER:** run `ephemeral-validator` with `--no-tui` and start it only after the base validator is healthy; `mb-test-validator` ships inside `@magicblock-labs/ephemeral-validator` (no standalone npm package). Local ER validator id `mAGicPQYBMvcYveUZA5F5UNNwyHvfYh5xkLS2Fr1mev`; Delegation Program `DELeGGvXpWV2fqJUhqcF5ZSYMS4JTLjteaAMARRSaeSh`.
- **MagicBlock ER commits:** `record_step` on the ER is free and is **not** a commit; only `checkpoint`/`close_and_undelegate` consume the commit nonce. A delegated account without a fee payer hard-fails at nonce >= 10 (`0xA0000000`). Undelegation cleanup = `3_000_000 + 1_000_000×(commits−1)` lamports. => fixed-size `StepLog` ring buffer, <= 2 checkpoints + 1 final commit, never one commit per step.
- **MagicBlock ER duplicate-tx trap:** identical instructions collide (same blockhash/message) and the second is silently dropped — `record_step` must carry a strictly monotonic `step_idx` (or unique seed). Cost the A1 spike a debugging cycle.
- **Measured (A1):** ER write p50 **~44 ms** vs base **~417 ms** (~9.4x); `checkpoint` **~13 ms**; terminal `commit_and_undelegate` **~29.5 s** (ER committor finalization, not configurable) — batch it into one terminal commit.
- **pay-kit `upto` (A2):** the Python **server** issues a correct `upto` challenge, but the high-level `PayKitClient` does **not** auto-pay `upto` (only `exact`); the low-level builder at `protocols/x402/client/upto/payment.py` is unwired. Use the Python MPP `session` path (A3) as primary.
- **MPP session (A3):** the Python pay-kit runs the full flow end-to-end (`open` → N reserve/commit cumulative vouchers → `close`). Server needs `SessionConfig.current_slot_provider` (open-freshness) + `session_routes` for reserve/commit, and `close` is handled by `Session.handle` (Authorization header), not `session_routes`. Real on-chain `settledSignature` needs the `solana-foundation/payment-channels` program + funded USDC mint; the Surfpool sandbox (`https://402.surfnet.dev:8899`) runs **no** payment-channels program, so close is a state flip (`onchain_settlement=false`) — deferred to A7 `PaymentAdapter`.
- Policy Engine is pure (no I/O). Invariant: `spent + reserved <= budget` must hold under concurrency; reserve before spending.
- Priority / critical path: A3 done -> A7 -> B6. Fallback per-call x402 `upto` remains (server-side) if the session settle path slips.
