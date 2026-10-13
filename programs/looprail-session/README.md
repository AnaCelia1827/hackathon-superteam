# looprail-session

Anchor program for the LoopRail `Session` PDA. Fixed-size, auditable metered session on Solana
base layer + MagicBlock Ephemeral Rollup (ER). See `docs/adr/ADR-3-pda-model.md`.

## Layout (fixed size)

- Seeds: `["session", owner, session_id]`.
- `Session` (see `src/lib.rs`): `owner`, `authority`, `session_id`, `policy_hash`, `budget_total`,
  `spent`, `reserved`, `step_count`, `status`, `opened_at`, `closed_at`, `channel_count`,
  `checkpoint_count`, `bump`, `channels[8]` (`provider`, `allocation`, `spent`), and a
  `steps[64]` ring buffer (`step_idx`, `tool_idx`, `provider_idx`, `cost`, `latency_ms`, `outcome`,
  `cache_hit`). Measure account size and rent from the built program on the target validator.

## Instructions

| Instruction | Layer | Notes |
| --- | --- | --- |
| `init_session` | base | create PDA; set `policy_hash`, `authority`, budget, providers + allocations |
| `delegate_session` | base | delegate PDA; ER validator from first `remaining_accounts` |
| `record_step` | ER | free, **not** a commit; strict `step_idx == step_count` |
| `checkpoint` | ER | `commit` (<= 2 per session) |
| `close_and_undelegate` | ER | terminal `commit_and_undelegate` |
| `abort` | ER/base | kill switch; owner or authority |

## Build & test

```bash
anchor build
# base-layer logic tests (requires a running local validator and deployed program):
anchor test --skip-local-validator
# ER integration (requires base validator + ER running, see scripts/local-env.sh):
RUN_ER_TESTS=1 . ./scripts/local-env.sh && npx ts-mocha -p ./tsconfig.json -t 1000000 tests/session-er.ts
```

`record_step` checks: signer == authority; status Open; monotonic `step_idx`; `provider_idx < channel_count`;
`outcome <= 3`; cache-hit costs 0; `spent + cost <= budget_total`; per-channel `spent <= allocation`.
