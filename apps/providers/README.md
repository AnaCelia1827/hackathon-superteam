# A9 — owned providers (pay-kit MPP session server)

Three LoopRail-owned providers, each an independent pay-kit **MPP session** endpoint,
plus a free `/pricing` table for the dashboard.

| Provider | Price | Session resource | Side-channel base |
| --- | --- | --- | --- |
| `market_data` | $0.001 (1000 base) | `GET /market_data/session` | `/market_data/__402/session/...` |
| `news` | $0.0008 (800 base) | `GET /news/session` | `/news/__402/session/...` |
| `inference` | $0.002 (2000 base) | `GET /inference/session` | `/inference/__402/session/...` |

Prices mirror `apps/runtime/looprail/mocks.py::PRICES`; all money is USDC base units as integers.

The side-channel shape matches the A7 `MppSessionAdapter` (`apps/runtime/looprail/mpp.py`),
which derives `/__402/session/{deliveries,commit,close}` from the session URL's parent path.

## Metering rules

Each provider runs one pay-kit MPP session: the agent opens a channel (deposit), then commits
running cumulative vouchers per call, and a single closing settlement refunds the remainder.
One open + one settlement per channel regardless of call count (ADR-2 / A3).

- `GET /pricing` (ungated): price table for the dashboard and benchmark.
- `GET /<provider>/session`: MPP session resource — 402 challenge on open, provider content on a
  valid credential.
- `POST /<provider>/__402/session/deliveries` + `/commit`: reserve/commit side channel.
- `POST /<provider>/__402/session/close`: terminal settlement (Authorization header).

## Modes

- **Wire-level (default)**: no on-chain settlement; close is a state flip.
- **On-chain**: `LOOPRAIL_PROVIDERS_ONCHAIN=1` — RPC-backed session server + operator signer
  against the Surfpool sandbox (`https://402.surfnet.dev:8899`), which runs the
  payment-channels program and a funded USDC mint.

## Running

```bash
# inside `make shell` (or the dev image), from apps/providers:
bash run.sh
```

`run.sh` boots the server on `127.0.0.1:8001` (on-chain mode) and runs `test_smoke.py`, which
funds a throwaway payer with Surfpool cheatcodes and drives the A7 `MppSessionAdapter` through
open → two cumulative vouchers → close, verifying the on-chain settlement signature. The smoke
payer keypair is temporary and lives outside the repository.

Config: `solana_pay_kit` demo operator (localnet only). For a real deployment set the operator to
a file-backed signer and keep it out of the repo (pay-kit refuses the demo signer on mainnet).

## Settlement network

Local/devnet only. The owned providers settle through the Surfpool sandbox. Verify the settlement
network (Solana vs Tempo) before pointing the demo at any external provider.
