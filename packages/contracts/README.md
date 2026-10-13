# Contracts v1

Files shared by the runtime, ledger, payments, and dashboard. Monetary values are integers in USDC base units (6 decimals).

- `policy.schema.json`: policy configuration.
- `step-record.schema.json`: event for each step.
- `metrics.schema.json`: session summary.
- `payment-message.schema.json`: messages exchanged with the payment adapter.

The schemas describe the proposed MVP API. Python was selected for the runtime, with a TypeScript ledger service. Mapping these contracts to pay-kit and Anchor still depends on spikes A2/A3.
