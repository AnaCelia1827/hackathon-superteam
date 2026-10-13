# A6 TypeScript ledger service

The HTTP service queues ER `record_step` writes in step-index order. `POST /sessions/:id/steps` returns `202` after queueing; `POST /sessions/:id/close` waits for each write and verifies the ER `step_count` before the terminal commit. Repeating an identical `step_index` returns its current state; changed data returns `409`. Failed sends remain visible in `GET /sessions/:id` and can be retried by posting the same step. The worker checks the ER count before resending in case the original write landed but confirmation failed.

## API

- `POST /sessions`: `{session_id, policy_hash, budget_usdc_base_units, owner, authority, tools, providers}`. IDs and hashes are lowercase 32-byte hex. `tools` and `providers` define stable on-chain `u8` indices; at most 8 providers.
- `POST /sessions/:id/steps`: `StepRecord v1` from `packages/contracts/step-record.schema.json`, with `session_id` matching the URL.
- `GET /sessions/:id`: queue and confirmation status.
- `POST /sessions/:id/checkpoint`: drains queue, then commits; at most two checkpoints.
- `POST /sessions/:id/close`: drains queue, checks count, then terminal commit and undelegation.
- `POST /sessions/:id/abort`: stops queued writes and sends the kill-switch instruction.

All USDC values are integer base units. The TypeScript `LedgerClient` is in `src/client.ts`.

## Running

Use Node 24.10.0 or newer. Install dependencies with `npm install` in this directory, then set `LOOPRAIL_IDL` to A5's generated Anchor IDL, `LOOPRAIL_OWNER_KEYPAIR` and `LOOPRAIL_AUTHORITY_KEYPAIR` to local keypair JSON files outside the repo, `LOOPRAIL_BASE_RPC` (for example `http://127.0.0.1:8899`), `LOOPRAIL_ER_RPC` (for example `http://127.0.0.1:7799`), and `LOOPRAIL_ER_VALIDATOR` (local: `mAGicPQYBMvcYveUZA5F5UNNwyHvfYh5xkLS2Fr1mev`). Run `npm start`. The server binds to `127.0.0.1:8787` by default. `npm test` needs no validator or dependencies.

The Anchor adapter in `src/anchor-chain.ts` expects A5 methods `initSession(sessionId, policyHash, budget, authority)`, `delegateSession()`, `recordStep(stepIndex, toolIndex, providerIndex, cost, latencyMs, outcome, cacheHit)`, `checkpoint()`, `closeAndUndelegate()`, and `abort()`, plus the `session` account with `stepCount`. The generated IDL will determine the final argument and account names. A5 is not yet present, so this binding cannot be exercised against the actual program yet. The 50-step acceptance test uses a chain port fake and checks ordering, counts, idempotency, retry, and the close barrier. On-chain acceptance remains contingent on A5.

The queue is in memory. Run one service instance per session; restarting loses queued events. Persisting the queue or reconstructing it from the chain is needed before a durable deployment.
