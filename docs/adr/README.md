# Architecture Decision Records

| ADR | Title | Status |
| --- | --- | --- |
| [ADR-1](ADR-1-language.md) | Runtime/payments language | Accepted: Python + TS sidecar |
| [ADR-2](ADR-2-channel-topology.md) | Payment channel topology | Accepted: one channel/provider |
| [ADR-3](ADR-3-pda-model.md) | `Session` PDA model | Accepted (A1 measured) |

Gate **A4** closed on **2026-10-13** with spike results from A1 (ER latency), A2 (x402 `upto`) and
A3 (MPP session); ADR-1/ADR-2 statuses were decided then and the ADR-3 economics carry the measured
latencies. Proceed to A5/A6/A7.

Sources pinned in these ADRs were verified on **2026-10-12**:
`solana_pay_kit==0.10.0`, MagicBlock docs + `magicblock-dev-skill` (commit
`0d78851e54f7ef38b979c788d58774013e4da3d1`), payment-channels program
`solana-foundation/payment-channels`, spec `paymentauth.org/draft-solana-session-00`.
