import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from dataclasses import replace

from jsonschema import Draft202012Validator

from looprail.adapters import MockLedger, MockPaymentAdapter
from looprail.agent import MarketIntelligenceAgent, StepSpec
from looprail.mocks import mock_registry
from looprail.policy import (
    BudgetTracker, Context, Policy, evaluate, policy_hash, retry_delay_ms,
)
from looprail.runtime import ExecutionEngine, run_scenario
from looprail.tools import Tool, ToolRegistry, ToolResult
import asyncio


POLICY_PATH = Path(__file__).parents[3] / "scenarios" / "market-intelligence" / "policy.mock.json"
CONTRACTS_PATH = Path(__file__).parents[3] / "packages" / "contracts"


def example_policy() -> Policy:
    return Policy.from_dict(json.loads(POLICY_PATH.read_text(encoding="utf-8")))


class PolicyTests(unittest.TestCase):
    def test_price_cap_and_unknown_provider(self):
        policy = example_policy()
        context = Context(0, 0, 0, 0, 0, 0)
        self.assertEqual(evaluate(policy, context, "inference", 2001).reason, "price_cap")
        self.assertEqual(evaluate(policy, context, "missing", 1).reason, "unknown_provider")

    def test_reservation_prevents_overspend_under_concurrency(self):
        data = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        data["budget_usdc_base_units"] = 10000
        data["provider_limits"]["market_data"]["allocation_usdc_base_units"] = 10000
        for name in ("inference", "news", "internal"):
            data["provider_limits"][name]["allocation_usdc_base_units"] = 0
        data["max_steps"] = 100
        tracker = BudgetTracker(Policy.from_dict(data))

        def attempt(_):
            decision, reservation = tracker.reserve("market_data", 1000)
            return reservation if decision.action == "allow" else None

        with ThreadPoolExecutor(max_workers=20) as executor:
            reservations = list(executor.map(attempt, range(100)))
        accepted = [item for item in reservations if item is not None]
        self.assertEqual(len(accepted), 10)
        self.assertEqual(tracker.spent + tracker.reserved, 10000)
        for reservation in accepted:
            tracker.commit(reservation, 700)
        self.assertEqual(tracker.spent, 7000)
        self.assertEqual(tracker.reserved, 0)

    def test_commit_cannot_exceed_reservation_or_repeat(self):
        tracker = BudgetTracker(example_policy())
        _, reservation = tracker.reserve("market_data", 1000)
        self.assertIsNotNone(reservation)
        with self.assertRaises(ValueError):
            tracker.commit(reservation, 1001)
        self.assertEqual(tracker.reserved, 1000)
        tracker.commit(reservation, 500)
        with self.assertRaises(ValueError):
            tracker.commit(reservation, 500)

    def test_mock_is_deterministic_and_derived_from_events(self):
        policy = example_policy()
        first = run_scenario(policy)
        second = run_scenario(policy)
        self.assertEqual(first, second)
        self.assertEqual(len(first["events"]), 50)
        self.assertEqual(first["metrics"]["usdc_spent_base_units"], sum(
            event["cost_usdc_base_units"] for event in first["events"]
        ))
        self.assertEqual(first["metrics"]["source"], "simulation")
        self.assertEqual(first["metrics"]["onchain_transactions"], 0)

    def test_injected_failure_triggers_error_rate_kill_switch(self):
        result = run_scenario(example_policy(), fail_on_steps=frozenset({0}))
        self.assertEqual(result["events"][0]["outcome"], "error")
        self.assertEqual(result["events"][1]["reason"], "error_rate_kill_switch")
        self.assertEqual(result["metrics"]["usdc_spent_base_units"], 0)

    def test_policy_hash_is_canonical(self):
        original = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        reordered = dict(reversed(list(original.items())))
        self.assertEqual(policy_hash(original), policy_hash(reordered))
        self.assertEqual(len(policy_hash(original)), 64)
        self.assertEqual(Policy.from_dict(original).hash, policy_hash(original))

    def test_cache_loop_retry_and_fallback_decisions(self):
        data = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        data["provider_limits"]["market_data"]["fallback_provider"] = "news"
        data["provider_limits"]["news"]["max_price_per_call_usdc_base_units"] = 3000
        policy = Policy.from_dict(data)
        base = Context(0, 0, 0, 0, 0, 0)
        self.assertEqual(evaluate(policy, replace(base, cached=True), "market_data", 1000).action, "cache_hit")
        self.assertEqual(evaluate(policy, replace(base, repeated_calls=4), "market_data", 1000).reason, "loop_detected")
        self.assertEqual(evaluate(policy, replace(base, retry_index=3), "market_data", 1000).reason, "retry_limit")
        fallback = evaluate(
            policy, replace(base, fallback_estimate=500), "market_data", 2000
        )
        self.assertEqual((fallback.action, fallback.provider), ("fallback", "news"))
        self.assertEqual(retry_delay_ms(policy, 1), 100)
        self.assertEqual(retry_delay_ms(policy, 2), 200)

    def test_mock_events_and_metrics_match_contracts(self):
        result = run_scenario(example_policy())
        event_schema = json.loads((CONTRACTS_PATH / "step-record.schema.json").read_text(encoding="utf-8"))
        metric_schema = json.loads((CONTRACTS_PATH / "metrics.schema.json").read_text(encoding="utf-8"))
        for event in result["events"]:
            Draft202012Validator(event_schema).validate(event)
        Draft202012Validator(metric_schema).validate(result["metrics"])
        self.assertEqual(result["report"]["market_observations"], 20)
        self.assertEqual(result["report"]["news_items"], 10)
        self.assertEqual(result["report"]["inference_assessments"], 15)
        self.assertEqual(len(result["receipts"]), 4)
        self.assertTrue(all(receipt["simulated"] for receipt in result["receipts"]))

    def test_retry_succeeds_without_double_charge(self):
        engine = ExecutionEngine(
            example_policy(), mock_registry(fail_attempts={0: {0}}),
        )
        result = asyncio.run(engine.run(MarketIntelligenceAgent()))
        self.assertEqual(result["events"][0]["outcome"], "ok")
        self.assertEqual(result["events"][0]["retry_count"], 1)
        self.assertEqual(result["events"][0]["retry_backoff_ms"], 100)
        self.assertEqual(result["metrics"]["usdc_spent_base_units"], 58000)

    def test_cache_hit_avoids_second_payment(self):
        class RepeatingAgent:
            def plan(self):
                args = {"symbol": "SOL", "step_index": 0, "query": "same"}
                return [StepSpec("market_data", args), StepSpec("market_data", args)]

            def report(self, outputs, *, mode):
                return {"outputs": len(outputs)}

        engine = ExecutionEngine(example_policy(), mock_registry())
        result = asyncio.run(engine.run(RepeatingAgent()))
        self.assertEqual([event["outcome"] for event in result["events"]], ["ok", "ok"])
        self.assertEqual(result["metrics"]["usdc_spent_base_units"], 1000)
        self.assertEqual(result["report"]["outputs"], 2)

    def test_ledger_rejects_conflicting_replay_of_step(self):
        ledger = MockLedger()
        ledger.open("s1", "hash")
        ledger.record_step("s1", {"step_index": 0, "outcome": "ok"})
        ledger.record_step("s1", {"step_index": 0, "outcome": "ok"})
        with self.assertRaises(ValueError):
            ledger.record_step("s1", {"step_index": 0, "outcome": "error"})

    def test_fallback_uses_cheaper_tool(self):
        data = {
            "version": 1, "budget_usdc_base_units": 3000, "max_steps": 1,
            "provider_limits": {
                "primary": {
                    "allocation_usdc_base_units": 2000,
                    "max_price_per_call_usdc_base_units": 1000,
                    "fallback_provider": "cheap",
                },
                "cheap": {
                    "allocation_usdc_base_units": 1000,
                    "max_price_per_call_usdc_base_units": 500,
                },
            },
        }
        registry = ToolRegistry()
        schema = {"type": "object"}

        async def handler(_arguments, _attempt):
            return ToolResult({"classification": "ok"}, 500, 5)

        registry.register(Tool("primary", "primary", 2000, "per_call", schema, True, 1000, handler, "secondary"))
        registry.register(Tool("secondary", "cheap", 500, "per_call", schema, True, 1000, handler))

        class OneStepAgent:
            def plan(self):
                return [StepSpec("primary", {})]

            def report(self, outputs, *, mode):
                return {"output": outputs[0]}

        result = asyncio.run(ExecutionEngine(Policy.from_dict(data), registry).run(OneStepAgent()))
        self.assertEqual(result["events"][0]["provider"], "cheap")
        self.assertEqual(result["events"][0]["reason"], "fallback_provider")
        self.assertEqual(result["metrics"]["usdc_spent_base_units"], 500)


if __name__ == "__main__":
    unittest.main()
