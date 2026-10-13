# A3 — MPP `session` spike

Throwaway spike (plan A3, critical path): run a metered MPP session with many deliveries,
each authorized by a running cumulative voucher, and close at the end.

## Hypothesis / what it proves

1. The session flow is `open` (deposit) -> many `reserve`/`commit` (cumulative vouchers) -> `close`
   (settle), i.e. **one open + one settle on-chain** regardless of delivery count.
2. The reserve/commit side channel enforces `cumulative <= deposit`.

## Method

- `server.py`: pay-kit `Session` method + `session_routes` (deliveries/commit/close), with
  wire-level and funded Surfpool sandbox modes.
- `client.py`: opens a channel, runs `DELIVERIES=50` reserve/commit cycles (cumulative vouchers),
  then closes and reports the cumulative and the settlement signature.

Run (inside `make shell`):

```bash
spikes/a3-mpp-session/run.sh
```

## Acceptance (plan A3)

- [x] 50 cumulative vouchers — confirmed (cumulative = 50 × 1000 = 50000 base units)
- [x] On-chain close in the Surfpool sandbox: one confirmed settlement signature for two
  cumulative vouchers (1250 + 750 base units); 60000 deposited, 2000 spent, 58000 refunded.
- [x] One open and one settlement transaction per channel in the funded smoke run.

## Findings (pay-kit 0.10.0, wire-level against Surfpool)

- The full session flow works end-to-end: `open` (challenge + client-signed opener) → 50
  `reserve`/`commit` cycles (running cumulative voucher) → `close` (200).
- Server needs `SessionConfig.current_slot_provider` (open-freshness validation) and the
  reserve/commit `session_routes`; `close` goes through `Session.handle` (Authorization header),
  not `session_routes`.
- The Surfpool sandbox has the payment-channels program and USDC mint. Set
  `LOOPRAIL_MPP_ONCHAIN=1` to use an RPC-backed session server and operator signer.
  The sandbox smoke script funds a throwaway payer with Surfpool cheatcodes, opens a
  channel, commits two vouchers, then confirms the close signature on the RPC.
- Pay-kit 0.10.0's session verifier expects an account response object while its
  `SolanaRpc.get_account_info` returns a tuple. The spike server bridges these shapes.
- The close receipt stores the channel ID in `reference` and the settlement signature
  in `tx_hash`; the A7 adapter reads and verifies `tx_hash`.

From the repository root with `apps/runtime[payments]` installed, use two terminals:

```powershell
$env:LOOPRAIL_MPP_ONCHAIN = '1'
.\.venv\Scripts\python.exe spikes/a3-mpp-session/server.py
```

```powershell
.\.venv\Scripts\python.exe spikes/a3-mpp-session/onchain_smoke.py
```

The smoke script uses Surfpool sandbox funds only. It creates a temporary keypair
outside the repository and removes it after the run.
