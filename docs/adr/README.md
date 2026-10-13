# Architecture Decision Records

| ADR | Title | Status |
| --- | --- | --- |
| [ADR-1](ADR-1-language.md) | Runtime/payments language | Proposed (gate A4) |
| [ADR-2](ADR-2-channel-topology.md) | Payment channel topology | Proposed (gate A4) |
| [ADR-3](ADR-3-pda-model.md) | `Session` PDA model | Accepted |

Each ADR is one page. Update the status and the spike numbers at gate **A4** before starting A5/A6/A7.

Sources pinned in these ADRs were verified on **2026-10-12**:
`solana_pay_kit==0.10.0`, MagicBlock docs + `magicblock-dev-skill` (commit
`0d78851e54f7ef38b979c788d58774013e4da3d1`), payment-channels program
`solana-foundation/payment-channels`, spec `paymentauth.org/draft-solana-session-00`.
