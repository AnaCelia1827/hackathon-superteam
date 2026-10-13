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

- [ ] reproducible latency table (p50/p95, base vs ER)
- [ ] state returns to the base layer after commit
- [ ] commit limit reproduced when `A1_TEST_COMMIT_LIMIT=1`
- [ ] delegation errors (if any) noted here

## Findings

_Pending a run against a live local ER. Fill in from `results/a1-er-counter.json`._
