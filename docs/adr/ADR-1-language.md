# ADR-1: Runtime and payments language

- **Status:** Proposed — decide at gate A4
- **Date:** 2026-10-12
- **Owners:** Pessoa A + Pessoa B

## Context

`solana_pay_kit==0.10.0` (Solana Foundation, released 2026-10-02) is **Python** (requires >= 3.11)
and ships both client and server for x402 `upto` and MPP `session`. MagicBlock and Anchor are
Rust/TypeScript. The plan originally assumed no equivalent TypeScript pay-kit package.

New evidence (2026-10-12): the pay-kit repo contains a cross-language **harness** that runs a
**TypeScript MPP client** against the Python server:

```
MPP_HARNESS_CLIENTS=typescript MPP_HARNESS_SERVERS=python pnpm test
```

So a TypeScript MPP *client* exists. It is not yet established that a TypeScript MPP *server*
(session issuance, reserve/commit side channel, settle-at-close) exists.

## Options

1. **Python runtime + payments, TypeScript ledger sidecar** (plan default). Use the documented Python
   session client/server; keep the ledger service in TypeScript for `ConnectionMagicRouter` / Anchor.
2. **Pure TypeScript monorepo.** Viable only if spike A3 shows the TS client plus a usable session
   server covers open/reserve/commit/close and real `settledSignature`.

## Decision

Pending spike results. **A2** measures x402 `upto`; **A3** measures MPP `session` (the critical path).
If A3 passes on Python only, adopt option 1. If A3 passes end-to-end in TypeScript, option 2 is allowed.

## Consequences

- Until decided, do not commit to a single language for `apps/runtime` / `apps/ledger-service`;
  keep contracts language-neutral JSON Schema.
- `packages/sdk-python/` in the repo layout is provisional and contingent on this ADR.
