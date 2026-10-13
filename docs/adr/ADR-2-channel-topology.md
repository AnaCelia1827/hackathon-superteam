# ADR-2: Payment channel topology

- **Status:** Accepted — option 1 (one channel per provider)
- **Date:** 2026-10-13 (confirmed at gate A4)
- **Owners:** Pessoa A + Pessoa B

## Context

A payment channel settles with **one** receiver. With N providers there are N channels and N
settlements — far fewer than one transaction per call, but not literally "1 settlement". The pitch
line must read "**N settlements, one per provider, instead of 50 payments**".

x402 is single-recipient by design and auto-disables on gates with `fee_within`/`fee_on_top`.
MPP supports multi-recipient splits and a `fee_within` take rate.

## Options

1. **One channel per provider (MVP default).** Simple, non-custodial, each provider is paid directly.
   Cost: N settlements. This is what the demo uses.
2. **LoopRail gateway as single receiver (extension).** The gateway is paid once and pays providers,
   enabling "1 settlement" and a take rate via MPP `fee_within`. Cost: custody + credit risk.

## Decision

Use option 1 for the hackathon. Option 2 is documented as a product extension, not built now.
Wording everywhere is "N settlements instead of 50 payments".

## Consequences

- `ChannelManager` is keyed per provider; the Policy Engine partitions the budget into
  `allocations{provider: amount}` because each channel needs its own deposit.
- The dashboard/benchmark report **settlements = number of funded providers**, not 1.
