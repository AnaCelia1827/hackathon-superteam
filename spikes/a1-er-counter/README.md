# A1 — Ephemeral Rollup spike (counter end-to-end)

Throwaway spike (plan A1). Vendored from
`magicblock-labs/magicblock-engine-examples/counter/anchor` at anchor `1.0.2` /
`ephemeral-rollups-sdk` `0.16.2`.

## Hypothesis / what it proves

1. ER increments are an order of magnitude faster than base-layer increments (p50/p95).
2. `record_step`-style writes on the ER are **ordinary transactions, not commits** — 100 of them run
   while only 1 commit is needed.
3. The no-fee-payer **commit limit** is real: a plain commit fails once the account's current nonce
   reaches 10 (custom `0xA0000000`), which is why LoopRail caps at <= 2 checkpoints + 1 terminal commit.
4. Committed state **returns to the base layer** after `commit_and_undelegate`.

## Method

`tests/er-latency.ts`:

1. `initialize` on base; airdrop if the wallet is low (localnet only).
2. `A1_BASE_STEPS` increments on base, each `sendAndConfirm` (measure ms).
3. `delegate` to the local ER validator (`mAGicPQYBMvcYveUZA5F5UNNwyHvfYh5xkLS2Fr1mev`).
4. `A1_ER_STEPS` increments on the ER (measure ms).
5. one `commit` + await the base-layer commitment signature.
6. `commit_and_undelegate`; assert the base-layer count equals base + ER steps.
7. optional (`A1_TEST_COMMIT_LIMIT=1`) loop plain commits to reproduce the `0xA0000000` limit.

Results are written to `results/a1-er-counter.json`.

## Prerequisites

```bash
make build   # from repo root: builds the pinned image
make dev     # base validator + local ER
```

## Run

From `spikes/a1-er-counter/` (inside `make shell`):

```bash
yarn install
yarn build                                  # anchor keys sync && anchor build
. ./scripts/local-env.sh
npx ts-mocha -p ./tsconfig.json -t 1000000 tests/er-latency.ts
```

Tune with `A1_BASE_STEPS`, `A1_ER_STEPS`, `A1_TEST_COMMIT_LIMIT` (see `.env.example`).

## Acceptance (plan A1)

- [x] reproducible latency table (p50/p95, base vs ER)
- [x] state returns to the base layer after commit
- [ ] commit limit reproduced when `A1_TEST_COMMIT_LIMIT=1` (not run yet)
- [x] delegation errors noted below

## Findings (local mb-stack, `results/a1-er-counter.json`)

| Metric | Base layer | Ephemeral Rollup |
| --- | --- | --- |
| samples | 10 | 100 |
| p50 | **417 ms** | **44.3 ms** |
| p95 | 435 ms | 47.6 ms |
| max | 435 ms | 138 ms |

- **Speedup p50 ≈ 9.4×** (base p50 / ER p50). The ER write path is ~44 ms here because the local
  validator round-trips the write through the rollup; the earlier "3.5 ms / 115×" figure was bogus —
  those transactions were rejected as duplicates and never executed.
- `delegate_ms ≈ 400 ms`, `commit_ms ≈ 13 ms`, `commit_settle_ms ≈ 112 ms` (real on-chain
  `commit_signature` captured), `count_after_commit = 110`, `state_returned_to_base = true`.
- **Terminal `commit_and_undelegate` takes a fixed ~29.5 s** regardless of the RPC commitment
  (`confirmed` or `processed`): the ER holds the `.rpc()` until the committor seals the final
  commit+undelegation back to base. The base layer then reverts ownership ~2 ms after `.rpc()`
  returns. So the ~30 s is a once-per-session terminal-close cost (not configurable via CLI), not a
  per-step cost. Checkpoints stay at ~13 ms, so the "≤2 checkpoints + 1 terminal commit" design holds;
  the ledger `close` / idle-close path (A6/A8) must budget ~30 s.
- **Duplicate-tx trap:** ER writes land ~3-5 ms apart, so identical instructions sharing a recent
  blockhash produce the same signature and the validator rejects the repeat with
  "already been processed". Fix: give each instruction a unique argument (`increment(seed)`), which
  stands in for `record_step`'s monotonic `step_idx` in the real program.
- **Gotchas that shaped `infra/`:** Agave's `solana-test-validator` needs `io_uring` (run containers
  with `--security-opt seccomp=unconfined --security-opt label=disable`); the ER needs `--no-tui` and
  must not start before the base is healthy; `anchor-cli 1.0.2` self-installs Agave `3.0.0`/`3.1.10`
  (not the plan's 3.1.9).
