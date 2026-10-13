# Measured benchmark comparison

`compare.py` consumes A10's measured CSV once its three runners are available. Each scenario needs at least 20 runs with identical `steps` values. The required columns are:

```text
scenario,steps,tx_count,fees_lamports,usdc_spent_base_units,provider_latency_p50_ms,provider_latency_p95_ms,looprail_overhead_p50_ms,looprail_overhead_p95_ms
```

Use scenario names `onchain_per_call`, `x402_per_call`, and `looprail`. All numeric values are non-negative integers. The script calculates medians and ranges, measured fee savings against each baseline, and an SVG bar chart. It never substitutes mock transaction counts or fees for measured runs.

```powershell
python benchmarks/compare.py benchmarks/results/a10-runs.csv
```

Outputs: `benchmarks/results/summary.json`, `benchmarks/results/fees.svg`, and `benchmarks/results/transactions.svg`. Provider latency and LoopRail overhead remain separate in the summary. Any mainnet projection must be labeled as an estimate and based on measured data; this tool reports only local/devnet measurements.
