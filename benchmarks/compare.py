"""Summarize measured A10 runs and draw a baseline comparison from CSV."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from statistics import median
from xml.sax.saxutils import escape

REQUIRED = {
    "scenario", "steps", "tx_count", "fees_lamports", "usdc_spent_base_units",
    "provider_latency_p50_ms", "provider_latency_p95_ms",
    "looprail_overhead_p50_ms", "looprail_overhead_p95_ms",
}
SCENARIOS = ("onchain_per_call", "x402_per_call", "looprail")


def summarize(path: Path, *, minimum_runs: int = 20) -> dict:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = REQUIRED - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Missing CSV columns: {', '.join(sorted(missing))}")
        groups: dict[str, list[dict[str, int]]] = defaultdict(list)
        for row in reader:
            scenario = row["scenario"]
            if scenario not in SCENARIOS:
                raise ValueError(f"Unknown scenario: {scenario}")
            values = {key: int(row[key]) for key in REQUIRED - {"scenario"}}
            if any(value < 0 for value in values.values()):
                raise ValueError("Metrics must be non-negative")
            groups[scenario].append(values)
    if any(len(groups[name]) < minimum_runs for name in SCENARIOS):
        raise ValueError(f"Need at least {minimum_runs} measured runs per scenario")
    steps = {row["steps"] for rows in groups.values() for row in rows}
    if len(steps) != 1:
        raise ValueError("All runs must have the same step count")
    metrics = REQUIRED - {"scenario", "steps"}
    scenarios = {
        name: {
            "runs": len(groups[name]),
            **{key: {"median": median(row[key] for row in groups[name]),
                     "min": min(row[key] for row in groups[name]),
                     "max": max(row[key] for row in groups[name])}
               for key in sorted(metrics)},
        }
        for name in SCENARIOS
    }
    looprail_fees = scenarios["looprail"]["fees_lamports"]["median"]
    savings = {}
    for name in SCENARIOS[:2]:
        baseline_fees = scenarios[name]["fees_lamports"]["median"]
        savings[name] = {
            "fees_saved_lamports_median": baseline_fees - looprail_fees,
            "fees_saved_percent_median": round(100 * (baseline_fees - looprail_fees) / baseline_fees, 2)
            if baseline_fees else None,
        }
    return {"source": "measured_csv", "steps": steps.pop(), "scenarios": scenarios,
            "estimated_savings": savings}


def chart(summary: dict, output: Path, metric: str = "fees_lamports") -> None:
    if metric not in {"fees_lamports", "tx_count"}:
        raise ValueError("Unsupported chart metric")
    width, height = 800, 330
    colors = ("#a9b4a9", "#67b1a0", "#a9ef43")
    labels = ("On-chain per call", "x402 per call", "LoopRail")
    values = [summary["scenarios"][name][metric]["median"] for name in SCENARIOS]
    maximum = max(values) or 1
    bars = []
    for index, (label, value, color) in enumerate(zip(labels, values, colors)):
        y = 76 + index * 80
        bar_width = 500 * value / maximum
        bars.append(f'<text x="25" y="{y + 19}" fill="#34443c" font-size="15">{escape(label)}</text>'
                    f'<rect x="205" y="{y}" width="{bar_width:.1f}" height="28" rx="5" fill="{color}"/>'
                    f'<text x="{215 + bar_width:.1f}" y="{y + 19}" fill="#34443c" font-size="14">{value:g} {"lamports" if metric == "fees_lamports" else "transactions"}</text>')
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}">'
           '<rect width="100%" height="100%" fill="white"/>'
           f'<text x="25" y="38" fill="#182620" font-size="22" font-weight="bold">Measured median {"transaction fees" if metric == "fees_lamports" else "transaction count"}</text>'
           + "".join(bars) + '</svg>')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(svg + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare measured A10 benchmark runs")
    parser.add_argument("csv", type=Path)
    parser.add_argument("--json", type=Path, default=Path("benchmarks/results/summary.json"))
    parser.add_argument("--svg", type=Path, default=Path("benchmarks/results/fees.svg"))
    parser.add_argument("--tx-svg", type=Path, default=Path("benchmarks/results/transactions.svg"))
    args = parser.parse_args()
    summary = summarize(args.csv)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    chart(summary, args.svg)
    chart(summary, args.tx_svg, "tx_count")
    print(f"Wrote {args.json}, {args.svg}, and {args.tx_svg}")


if __name__ == "__main__":
    main()
