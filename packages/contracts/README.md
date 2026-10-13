# contracts

Shared JSON Schema contracts for LoopRail. **Define these together before integrating** (J1).

| Schema | Owner | Status |
| --- | --- | --- |
| `step_record.schema.json` | Pessoa A | v1 |
| `payment_adapter.schema.json` | Pessoa A | v1 |
| `policy.schema.json` | Pessoa B | pending |
| `metrics.schema.json` | Pessoa B | pending |

## Conventions

- **Money is always integer USDC base units (6 decimals)** in every schema and in the ledger.
  `1 USDC = 1_000_000`. Never use floats. See `$defs.usdc_base_units`.
- Schemas are versioned by path: `$id` = `https://looprail.local/schemas/v1/<name>.schema.json`.
  Breaking changes bump `v1` -> `v2`; never edit a published schema in place.
- `policy_hash` (packages/contracts `policy.schema.json`, Pessoa B) is the hash of the canonical
  JSON per **RFC 8785**; the same canonicalization is used by `solana_pay_kit`. The 32-byte digest is
  stored in the on-chain `Session` PDA.
- Valid example per schema lives in `examples/`. Keep examples in sync when a schema changes.

## Validation

`jsonschema`/`ajv` validation is wired into `make test` (see `infra/`, J2). Until then, validate a
single example with any draft 2020-12 validator, e.g.:

```bash
python -c "import json,jsonschema as j; \
 j.validate(json.load(open('packages/contracts/examples/step_record.example.json')), \
            json.load(open('packages/contracts/step_record.schema.json')))"
```

## On-chain mapping (A5)

The Anchor `Session` PDA stores compact `u8` indices, not the string ids. `StepRecord.tool_idx` /
`StepRecord.provider_idx` are the on-chain values; `tool_id` / `provider_id` are the registry handles
the runtime resolves through the `ToolRegistry`.
