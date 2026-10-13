import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from looprail.policy import BudgetTracker, Context, Policy, evaluate
from looprail.runtime import run_scenario


POLICY_PATH = Path(__file__).parents[3] / "scenarios" / "market-intelligence" / "policy.mock.json"


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


if __name__ == "__main__":
    unittest.main()
