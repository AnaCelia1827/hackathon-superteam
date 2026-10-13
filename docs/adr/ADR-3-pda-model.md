# ADR-3: `Session` PDA model

- **Status:** Accepted (implementation in A5; constants + economics re-verified in A1)
- **Date:** 2026-10-13 (A1 measured)
- **Owner:** Pessoa A

## Context

The agent executes ~50 steps per task. Each step must be recorded with low latency and the whole
session must remain auditable on Solana. Storing one commit per step is not viable (commit limits and
cost, see below), so the step log must be a **fixed-size ring buffer** updated on the ER and committed
only a few times.

A delegated PDA **cannot be cheaply resized**: resizing requires extra rent lamports and, if top-up is
needed, a delegated payer (MagicBlock `Resize PDA`). Therefore every size must be fixed at creation.

## Decision

One program `looprail_session` owns a single fixed-size `Session` PDA per session.

- **Seeds:** `["session", owner, session_id]`
- **Layout (fixed size):**
  - `owner: Pubkey` — session payer/authority of last resort.
  - `authority: Pubkey` — the runtime key allowed to `record_step` on the ER.
  - `session_id: [u8; 32]`
  - `policy_hash: [u8; 32]` — RFC 8785 canonical-JSON digest.
  - `budget_total / spent / reserved: u64` — USDC base units.
  - `step_count: u32`, `status: u8` (Open/Closing/Closed/Aborted), `opened_at / closed_at: i64`.
  - `channels[N]` with `N = 8`: `{ provider: Pubkey, spent: u64 }` per provider.
  - `steps[K]` ring buffer with `K = 64`; each entry `{ tool_idx: u8, provider_idx: u8, cost: u64,
    latency_ms: u32, outcome: u8, cache_hit: bool }`. `K = 64` covers the 50-step demo with headroom.

### Instructions

| Instruction | Layer | Notes |
| --- | --- | --- |
| `init_session` | base | create PDA, set budget + `policy_hash` |
| `delegate_session` | base | ER validator from first `remaining_accounts` |
| `record_step` | ER | append to ring buffer, update `spent`/`step_count` |
| `checkpoint` | ER | `MagicIntentBundleBuilder::commit` |
| `close_and_undelegate` | ER | `commit_and_undelegate` (terminal) |
| `abort` | ER/base | kill switch; close out |

### `record_step` rules

- `signer == authority`
- `status == Open`
- `step_idx` strictly monotonic (`== step_count`)
- `spent + cost <= budget_total`
- writes into the ring buffer

### Commit policy: Path A, <= 2 checkpoints + 1 terminal commit

Use the **no-delegated-fee-payer path** only. Do **not** add a `magic_fee_vault` or delegated payer.
Consequence: a plain commit hard-fails once the account's current nonce reaches 10 (custom
`0xA0000000`), so cap at **<= 2 `checkpoint` + 1 `close_and_undelegate`** (<= 3 commits).

Crucially, `record_step` on the ER is **not a commit**: ER execution fee is 0 and it does not consume
the commit nonce. Only `checkpoint`/`close_and_undelegate` do.

## Verified commit economics (magicblock-dev-skill, 2026-10-06)

Do not call commits "free". At undelegation the Delegation Program charges
`3_000_000 + 1_000_000 * (finalized_commits - 1)` lamports (capped by the delegation record+metadata
PDA balances), refunding the remainder to the **`rent_payer` stored at delegation time**. So a session
with 2 checkpoints + 1 final commit costs ~`5_000_000` lamports cleanup (~0.005 SOL) plus base tx fees,
independent of how many `record_step` calls ran.

## Measured latencies (spike A1, `spikes/a1-er-counter`, 2026-10-13)

Public counter program, `count=110` steps, ER vs base:

| Path | p50 |
| --- | --- |
| ER `record_step` equivalent (delegated write) | **~44 ms** |
| Base-layer tx | **~417 ms** |
| ER `checkpoint` (commit) | **~13 ms** |
| `commit_and_undelegate` (terminal) | **~29.5 s** |

- The ~9.4x ER-vs-base speedup is the product thesis; only the terminal undelegation is slow (ER
  committor finalization), so sessions must batch it into <= 1 terminal commit.
- **Duplicate-tx trap:** identical instructions collide on the ER (same blockhash/message) and the
  second is dropped. `record_step` must carry a strictly monotonic `step_idx` (already the rule above)
  or a unique seed; this was the A1 bug fixed before the clean run.

## Consequences

- The ledger mirrors the on-chain ring buffer; see `packages/contracts/step_record.schema.json`.
- Because the buffer is fixed, `step_count` may exceed `K`; the ring buffer keeps the last `K` entries
  and `step_count` is the authoritative total for the ledger.
- Payment channels live in the separate `payment-channels` program on the base layer and are **not**
  part of this ER delegation graph.

## Alternatives rejected

- **Ephemeral Account for the step log** — never commits, so it cannot serve as an audit trail.
- **One commit per step** — hits the commit limit and pays a commit fee per step.
- **Resizable PDA** — delegated resizes need rent + a delegated payer; unnecessary complexity.
- **No delegation (base-layer only)** — loses the low-latency loop that is the product thesis.
