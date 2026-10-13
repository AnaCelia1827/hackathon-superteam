# ADR-1: Runtime and payments language

- **Status:** Accepted — option 1 (Python + TypeScript sidecar)
- **Date:** 2026-10-13 (decided at gate A4)
- **Owners:** Pessoa A + Pessoa B

## Context

`solana_pay_kit==0.10.0` (Solana Foundation, 2026-10-02) is **Python** (>= 3.11) and ships both
client and server for MPP `session` and the x402 `upto` **server**. MagicBlock and Anchor are
Rust/TypeScript. The pay-kit repo has a cross-language harness that runs a **TypeScript MPP client**
against the Python server, but no TS session *server* is established.

## Spike results (A1/A2/A3, 2026-10-13)

- **A3 (MPP session, critical path):** Python pay-kit runs the full session flow end-to-end —
  `open` → 50 `reserve`/`commit` cumulative vouchers → `close` (200). Confirmed on Surfpool sandbox.
  Real on-chain `settledSignature` still needs the `payment-channels` program deployed (deferred to A7).
- **A2 (x402 upto):** the Python **server** issues a correct `upto` challenge, but the high-level
  `PayKitClient` **does not auto-pay `upto`** (only `exact` is wired; a low-level upto builder exists
  but is unwired). So `upto` is usable server-side, not as a drop-in Python client.
- **A1 (MagicBlock ER):** Rust `anchor-lang 1.0.2` + `ephemeral-rollups-sdk 0.16.2` with a TS/web3.js
  client. ER increment p50 ~44 ms vs base ~417 ms.

## Decision

**Option 1 — Python runtime + payments, TypeScript ledger sidecar.** MPP `session` (Python) is the
primary payment path; the TS ledger service talks to MagicBlock (`ConnectionMagicRouter`) and the
Anchor program. x402 `upto` remains a fallback and needs either the low-level Python builder or a
non-Python client. Pure TypeScript (option 2) is rejected: no TS session server is verified.

## Consequences

- `apps/runtime` (Person B) and the payment integration (Person A) use Python for the pay-kit
  session; `apps/ledger-service` uses TypeScript for Anchor/MagicBlock.
- The A7 `PaymentAdapter` must call the pay-kit Python session server/client surface directly
  (`Session` method, `session_routes`, `ActiveSession`/`SessionConsumer`), not the high-level
  `PayKitClient` (which lacks `upto` auto-pay).
- `packages/sdk-python/` is now the real public SDK; the earlier "pure TS" contingency is dropped.
