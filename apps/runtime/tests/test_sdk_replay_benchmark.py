import csv
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from threading import Event

from looprail.agent import MarketIntelligenceAgent
from looprail.mocks import write_cassette
from looprail.sdk import BudgetExceeded, LoopRail, load_policy

ROOT = Path(__file__).parents[3]
POLICY = ROOT / "scenarios" / "market-intelligence" / "policy.mock.json"


class SdkAndReplayTests(unittest.TestCase):
    def test_sdk_and_replay_have_same_outputs_and_spending(self):
        policy = load_policy(POLICY)
        rail = LoopRail(budget=policy.budget_usdc_base_units)
        with tempfile.TemporaryDirectory() as folder:
            cassette = Path(folder) / "session.json"
            write_cassette(cassette, MarketIntelligenceAgent().plan())
            mock = rail.run(policy=policy)
            replay = rail.run(policy=policy, replay_path=cassette)
        self.assertEqual(mock.metrics["usdc_spent_base_units"], replay.metrics["usdc_spent_base_units"])
        self.assertEqual(mock.report["recommendation"], replay.report["recommendation"])
        self.assertEqual([event["cost_usdc_base_units"] for event in mock.events],
                         [event["cost_usdc_base_units"] for event in replay.events])
        self.assertEqual(len(replay.events), 50)

    def test_sdk_budget_ceiling_and_abort(self):
        policy = load_policy(POLICY)
        with self.assertRaises(BudgetExceeded):
            LoopRail(budget=0).run(policy=policy)
        stop = Event()
        stop.set()
        result = LoopRail(budget=policy.budget_usdc_base_units).run(policy=policy, stop_event=stop)
        self.assertEqual(result.status, "aborted")
        self.assertEqual(result.metrics["steps"], 0)
        self.assertEqual(result.metrics["usdc_spent_base_units"], 0)

    def test_streamed_budget_snapshots_respect_invariant(self):
        policy = load_policy(POLICY)
        snapshots = []
        LoopRail(budget=policy.budget_usdc_base_units).run(policy=policy, telemetry_sink=snapshots.append)
        self.assertTrue(any(item["reserved_usdc_base_units"] > 0 for item in snapshots))
        self.assertTrue(all(item["spent_usdc_base_units"] + item["reserved_usdc_base_units"]
                            <= policy.budget_usdc_base_units for item in snapshots))
        self.assertEqual(snapshots[-1]["reserved_usdc_base_units"], 0)


class BenchmarkTests(unittest.TestCase):
    @staticmethod
    def module():
        spec = importlib.util.spec_from_file_location("comparison", ROOT / "benchmarks" / "compare.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_summary_and_chart_use_only_csv_measurements(self):
        module = self.module()
        with tempfile.TemporaryDirectory() as folder:
            csv_path = Path(folder) / "runs.csv"
            with csv_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=sorted(module.REQUIRED))
                writer.writeheader()
                for scenario, fees, tx in (("onchain_per_call", 5000, 50),
                                           ("x402_per_call", 4000, 50),
                                           ("looprail", 1000, 3)):
                    for _ in range(20):
                        writer.writerow({
                            "scenario": scenario, "steps": 50, "tx_count": tx,
                            "fees_lamports": fees, "usdc_spent_base_units": 58000,
                            "provider_latency_p50_ms": 50, "provider_latency_p95_ms": 140,
                            "looprail_overhead_p50_ms": 2, "looprail_overhead_p95_ms": 5,
                        })
            summary = module.summarize(csv_path)
            self.assertEqual(summary["estimated_savings"]["onchain_per_call"]["fees_saved_lamports_median"], 4000)
            self.assertEqual(summary["estimated_savings"]["x402_per_call"]["fees_saved_percent_median"], 75)
            svg = Path(folder) / "fees.svg"
            module.chart(summary, svg)
            self.assertIn("Measured median", svg.read_text(encoding="utf-8"))
            module.chart(summary, Path(folder) / "transactions.svg", "tx_count")
            with self.assertRaises(ValueError):
                module.summarize(csv_path, minimum_runs=21)


if __name__ == "__main__":
    unittest.main()
