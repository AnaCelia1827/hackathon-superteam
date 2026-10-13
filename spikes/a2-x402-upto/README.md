# A2 — x402 `upto` spike

Throwaway spike (plan A2): measure on-chain transaction cost of x402 `upto` (authorize a ceiling,
meter actual usage, settle actual + refund the remainder).

## Hypothesis / what it proves

1. `upto` = one channel **open** (deposit ceiling) + one **settle** (meter actual + refund) per call,
   i.e. ~2 on-chain transactions per metered call — vs `exact` (1 tx, no metering).
2. The client authorizes the ceiling; the handler meters actual; the gate settles `actual ≤ ceiling`
   and refunds the unused deposit.

## Method

- `server.py`: Flask `require_usage(usd("0.05"))`, handler meters `$0.01` via `charge().charge(...)`.
- `client.py`: `PayKitClient` (demo signer, `network="localnet"`, Surfpool sandbox) makes `CALLS=3`
  calls and reports status, settlement header, and the payer's on-chain signature count delta.

Run (inside `make shell`):

```bash
spikes/a2-x402-upto/run.sh
```

## Acceptance (plan A2)

- [~] tx-per-call table — see findings (protocol: open + settle = 2 tx/call; not measured end-to-end, see below)
- [x] authorized vs settled vs refund — ceiling $0.05 / metered $0.01 / refund $0.04 (server-side, see findings)

## Findings (pay-kit 0.10.0, Python)

- The **server** side of `upto` works: `require_usage(Gate(...))` issues a correct challenge with
  `amount=50000` base units ($0.05 ceiling), USDC (`EPjFWdd5...`), `feePayer`/`receiverAuthorizer` =
  operator, and a Surfpool `SURFNETxSAFEHASH...` recent blockhash.
- The **high-level `PayKitClient` does NOT auto-pay `upto`**: its transport imports the `exact`
  payment path (`parse_x402_challenge_with_version` from `protocols/x402/client/exact/payment.py`),
  so an `upto` 402 is returned unchanged (client logs "failed to build x402 payment credential").
- A low-level `upto` client builder **does** exist at `protocols/x402/client/upto/payment.py`, but it
  is not wired into `PayKitClient`. A LoopRail `X402UptoAdapter` (A7) would have to call that builder
  directly, or use a non-Python client.
- Protocol-level cost (from `_paycore/paymentchannels.py` + x402 upto types): `upto` = one channel
  **open** (deposit ceiling) + one **settle** (meter actual + refund remainder) ≈ **2 on-chain tx per
  call**, vs `exact` = 1 tx. The demo-signer payer is shared on the public sandbox, so a clean
  per-caller tx count needs a dedicated payer keypair.

## Open / decision for A4

- ADR-1 input: Python pay-kit covers x402 `exact` end-to-end but `upto` only server-side. If the demo
  needs `upto` per-call, either call the low-level Python builder or lean on the TypeScript/Rust
  client (the pay-kit harness runs a TS MPP client; x402 `upto` TS client still unverified).
