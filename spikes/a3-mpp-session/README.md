# A3 — MPP `session` spike

Throwaway spike (plan A3, critical path): run a metered MPP session with many deliveries,
each authorized by a running cumulative voucher, and close at the end.

## Hypothesis / what it proves

1. The session flow is `open` (deposit) -> many `reserve`/`commit` (cumulative vouchers) -> `close`
   (settle), i.e. **one open + one settle on-chain** regardless of delivery count.
2. The reserve/commit side channel enforces `cumulative <= deposit`.

## Method

- `server.py`: pay-kit `Session` method + `session_routes` (deliveries/commit/close), wire-level.
- `client.py`: opens a channel, runs `DELIVERIES=50` reserve/commit cycles (cumulative vouchers),
  then closes and reports the cumulative and the settlement signature.

Run (inside `make shell`):

```bash
spikes/a3-mpp-session/run.sh
```

## Acceptance (plan A3)

- [x] 50 cumulative vouchers — confirmed (cumulative = 50 × 1000 = 50000 base units)
- [~] `settledSignature` real on-chain — **not yet**: wire-level run returns the channel id as the
  close reference, `onchain_settlement=false`
- [~] tx = open + close — holds at protocol level (one open, one settle per session)

## Findings (pay-kit 0.10.0, wire-level against Surfpool)

- The full session flow works end-to-end: `open` (challenge + client-signed opener) → 50
  `reserve`/`commit` cycles (running cumulative voucher) → `close` (200).
- Server needs `SessionConfig.current_slot_provider` (open-freshness validation) and the
  reserve/commit `session_routes`; `close` goes through `Session.handle` (Authorization header),
  not `session_routes`.
- **Real on-chain `settledSignature` requires** the `solana-foundation/payment-channels` program +
  a funded USDC mint on a local validator, plus a session server configured with `rpc` + operator
  `signer` (settle-at-close). The Surfpool sandbox runs no payment-channels program, so the close is
  a state flip and the signature stays null. This is the A7 `PaymentAdapter` (ChannelManager) work.
