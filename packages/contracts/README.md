# Shared contracts v1

JSON Schemas shared by the Python runtime, TypeScript ledger, payment adapters, and dashboard. Money is always integer USDC base units (6 decimals): `1 USDC = 1_000_000`.

| Schema | Purpose |
| --- | --- |
| `policy.schema.json` | Runtime spending policy |
| `step-record.schema.json` | Runtime event for each step |
| `metrics.schema.json` | Session summary |
| `payment-message.schema.json` | Runtime payment messages |
| `step_record.schema.json` | Person A's ledger-facing StepRecord |
| `payment_adapter.schema.json` | Person A's PaymentAdapter contract |

The two StepRecord and payment schema pairs currently use different naming and field conventions. Reconcile them together before B6 integrates the ledger and real payments. Keep the valid examples in `examples/` synchronized with the ledger-facing schemas.

`policy_hash` is the SHA-256 digest of RFC 8785 canonical policy JSON. The planned on-chain Session PDA stores the 32-byte digest. Breaking contract changes require a new versioned schema rather than changing a published contract in place.

Run `make test` for the repository's contract validation and `python -m unittest discover -s apps/runtime/tests` after installing the runtime's Python dependencies.
