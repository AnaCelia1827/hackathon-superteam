# AGENTS.md

LoopRail is a runtime + metered-payment layer for autonomous AI agents on Solana.
Hackathon repo with shared contracts, a Python runtime prototype, and a local dashboard. Person A's on-chain and payment services are not implemented yet.

## Sources of truth
- `looprail_implementation_plan.md` — task plan (J1-J4, A1-A10, B1-B8), pinned versions, constraints. Primary.
- `looprail_ideacao.pdf` — product/pitch context (architecture, policy example, demo script).
The original PDF is in Portuguese. Read the English implementation plan before starting any task; it names acceptance criteria per task.

## Architecture decisions
- The user selected Python for the runtime and TypeScript for the ledger service. A2/A3 still determine the payment integration details.
- Channel topology is ADR-2; MVP default is one payment channel per provider, not a single gateway.
- "1 settlement" in the pitch is aspirational: with N providers there are N settlements (one per receiver). Prefer "N settlements instead of 50 payments".

## Hard conventions (from the plan)
- All money is USDC base units (6 decimals) as **integers**, never float. Applies to contracts/schemas and the ledger.
- `policy_hash` = hash of canonical JSON per RFC 8785 (same scheme pay-kit uses); it is stored in the on-chain PDA.
- Planned commands (not yet implemented): `make dev` should bring up validator + local ER + stub services; CI runs lint + tests.
- Pin versions exactly: Solana 3.1.9, Rust 1.89.0, Anchor 1.0.2, Node 24.10.0, Python >= 3.11, `solana_pay_kit==0.10.0`.
- Devnet/local only. Never commit keys (use `Signer.file`/env); pay-kit refuses the demo signer on mainnet.

## Architecture / ownership (planned)
- Person A: on-chain + payments — Anchor program `looprail_session` (fixed-size `Session` PDA, `steps[K]` ring buffer), TS ledger service, `PaymentAdapter` (`open/reserve/commit/release/close_all`).
- Person B: runtime + policy + demo — pure-API Spend Policy Engine (`evaluate(ctx, request) -> Decision`), agent loop, `ToolRegistry`, deterministic mock, SDK, dashboard.
- Shared contracts as JSON Schema in `packages/contracts/`: `Policy`, `StepRecord`, `PaymentAdapter`, `Metrics`.

## Gotchas that will bite
- MagicBlock ER: a delegated account without a fee payer halts after 10 commits (with fee payer, fees apply from the 26th). Resizing a delegated PDA needs rent lamports and possibly a delegated payer. => `StepLog` must be fixed-size ring buffer and sessions use <= 2 checkpoints + 1 final commit, never one commit per step.
- Policy Engine is pure (no I/O). Invariant: `spent + reserved <= budget` must hold under concurrency; reserve before spending.
- Priority / critical path: A3 (MPP session spike) -> A7 -> B6. If A3 fails, fall back to per-call x402 `upto` (plan B at gate A4).
