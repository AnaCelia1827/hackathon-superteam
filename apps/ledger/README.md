# A6 TypeScript ledger service

The HTTP service queues ER `record_step` writes in step-index order. `POST /sessions/:id/steps` returns `202` after queueing; `POST /sessions/:id/close` waits for each write and verifies the ER `step_count` before the terminal commit. Repeating an identical `step_index` returns its current state; changed data returns `409`. Failed sends remain visible in `GET /sessions/:id` and can be retried by posting the same step. The worker checks the ER count before resending in case the original write landed but confirmation failed.

## API

- `POST /sessions`: `{session_id, policy_hash, budget_usdc_base_units, owner, authority, tools, providers, provider_pubkeys, provider_allocations_usdc_base_units}`. IDs and hashes are lowercase 32-byte hex. The parallel provider arrays define stable on-chain `u8` indices, Solana recipient keys and USDC allocation ceilings; at most 8 providers.
- `POST /sessions/:id/steps`: `StepRecord v1` from `packages/contracts/step-record.schema.json`, with `session_id` matching the URL.
- `GET /sessions/:id`: queue and confirmation status.
- `POST /sessions/:id/checkpoint`: drains queue, then commits; at most two checkpoints.
- `POST /sessions/:id/close`: drains queue, checks count, then terminal commit and undelegation.
- `POST /sessions/:id/abort`: stops queued writes and sends the kill-switch instruction.

All USDC values are integer base units. The TypeScript `LedgerClient` is in `src/client.ts`.

## Running

Use Node 24.10.0 or newer. Install dependencies with `npm install` in this directory, then set `LOOPRAIL_IDL` to A5's generated Anchor IDL, `LOOPRAIL_OWNER_KEYPAIR` and `LOOPRAIL_AUTHORITY_KEYPAIR` to local keypair JSON files outside the repo, `LOOPRAIL_BASE_RPC` (for example `http://127.0.0.1:8899`), `LOOPRAIL_ER_RPC` (for example `http://127.0.0.1:7799`), and `LOOPRAIL_ER_VALIDATOR` (local: `mAGicPQYBMvcYveUZA5F5UNNwyHvfYh5xkLS2Fr1mev`). Run `npm start`. The server binds to `127.0.0.1:8787` by default. `npm test` needs no validator or dependencies.

The Anchor adapter in `src/anchor-chain.ts` follows the A5 instruction signatures in `programs/looprail-session/src/lib.rs`. It uses the configured base RPC for init/delegation and the fixed ER RPC for records, checkpoints and terminal close. `denied` maps to on-chain outcome 3; `cache_hit` maps to outcome 0 with the separate cache-hit flag. The 50-step test checks ordering, counts, idempotency, retry and the close barrier through a chain-port fake. An actual validator run still requires a built/deployed A5 program and funded local accounts.

The queue is in memory. Run one service instance per session; restarting loses queued events. Persisting the queue or reconstructing it from the chain is needed before a durable deployment.
