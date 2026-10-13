"""Exercise the live runtime boundary without a validator or real funds."""

import unittest

from looprail.adapters import MockLedger, MockPaymentAdapter
from looprail.http_ledger import HttpLedgerAdapter
from looprail.mocks import mock_registry
from looprail.sdk import LoopRail, SettlementFailed, load_policy

from pathlib import Path


POLICY = Path(__file__).parents[3] / "scenarios" / "market-intelligence" / "policy.mock.json"


class ConfirmingLedger:
    def __init__(self):
        self.inner = MockLedger()
        self.status = None

    def open(self, session_id, policy_hash):
        self.inner.open(session_id, policy_hash)

    def record_step(self, session_id, event):
        self.inner.record_step(session_id, event)

    def close(self, session_id):
        self.inner.close(session_id)
        self.status = "closed"

    def abort(self, session_id):
        self.inner.abort(session_id)
        self.status = "aborted"

    def events(self, session_id):
        return self.inner.events(session_id)


class ReceiptPayment:
    def __init__(self):
        self.inner = MockPaymentAdapter()
        self.commits = 0

    def open(self, provider, allocation):
        return self.inner.open(provider, allocation)

    def reserve(self, channel, maximum):
        return self.inner.reserve(channel, maximum)

    def commit(self, reservation, actual):
        self.commits += 1
        self.inner.commit(reservation, actual)

    def release(self, reservation):
        self.inner.release(reservation)

    def close_all(self):
        self.inner.close_all()
        return [
            {
                "provider": channel.provider,
                "usdc_deposited": channel.allocation_usdc_base_units,
                "usdc_spent": self.inner.spent[channel.id],
                "usdc_refunded": channel.allocation_usdc_base_units - self.inner.spent[channel.id],
                "settlements": 1,
                "settled_signature": "test-signature",
                "simulated": False,
            }
            for channel in self.inner.channels.values() if self.inner.spent[channel.id]
        ]


class UncertainPayment(ReceiptPayment):
    def commit(self, reservation, actual):
        self.commits += 1
        raise TimeoutError("commit response lost")

    def release(self, reservation):
        raise RuntimeError("remote commit pending")


class IncorrectReceiptPayment(ReceiptPayment):
    def close_all(self):
        receipts = super().close_all()
        receipts[0]["usdc_refunded"] += 1
        return receipts


class LiveIntegrationTests(unittest.TestCase):
    def test_http_ledger_validates_config_and_close_count(self):
        policy = load_policy(POLICY)
        ledger = HttpLedgerAdapter(
            "http://127.0.0.1:8787", owner="owner", authority="authority",
            budget_usdc_base_units=policy.budget_usdc_base_units,
            tools=["market_data"],
            provider_pubkeys={name: f"key-{name}" for name in policy.allocations},
            provider_allocations_usdc_base_units=policy.allocations,
        )
        ledger.validate_policy(policy, {"market_data"})
        with self.assertRaisesRegex(ValueError, "tools do not cover"):
            ledger.validate_policy(policy, {"inference"})
        calls = []

        def request(path, method="GET", payload=None):
            calls.append((path, method, payload))
            if path == "/sessions":
                return {"session_id": "a" * 64, "status": "open", "confirmed_count": 0}
            if path.endswith("/steps"):
                return {"step_index": 0, "state": "queued"}
            return {"session_id": "a" * 64, "status": "closed", "confirmed_count": 1}

        ledger._request = request
        ledger.open("a" * 64, policy.hash)
        step = {"step_index": 0, "cost_usdc_base_units": 1000}
        ledger.record_step("a" * 64, step)
        ledger.close("a" * 64)
        self.assertEqual(ledger.events("a" * 64), [step])
        self.assertEqual(calls[0][2]["provider_allocations_usdc_base_units"], list(policy.allocations.values()))

    def test_http_ledger_retries_failed_step_before_close(self):
        policy = load_policy(POLICY)
        ledger = HttpLedgerAdapter(
            "http://127.0.0.1:8787", owner="owner", authority="authority",
            budget_usdc_base_units=policy.budget_usdc_base_units,
            tools=["market_data"],
            provider_pubkeys={name: f"key-{name}" for name in policy.allocations},
            provider_allocations_usdc_base_units=policy.allocations,
        )
        attempts = {"close": 0, "step": 0}

        def request(path, method="GET", payload=None):
            if path == "/sessions":
                return {"session_id": "b" * 64, "status": "open", "confirmed_count": 0}
            if path.endswith("/steps"):
                attempts["step"] += 1
                return {"step_index": 0, "state": "queued"}
            if path.endswith("/close"):
                attempts["close"] += 1
                if attempts["close"] == 1:
                    raise RuntimeError("Step 0 failed")
                return {"status": "closed", "confirmed_count": 1}
            return {"status": "open", "steps": [{"step_index": 0, "state": "failed"}]}

        ledger._request = request
        ledger.open("b" * 64, policy.hash)
        ledger.record_step("b" * 64, {"step_index": 0})
        ledger.close("b" * 64)
        self.assertEqual(attempts, {"close": 2, "step": 2})

    def test_receipts_reconcile_with_50_ledger_steps(self):
        policy = load_policy(POLICY)
        ledger = ConfirmingLedger()
        payment = ReceiptPayment()
        result = LoopRail(budget=policy.budget_usdc_base_units).run(
            policy=policy, tools=mock_registry(), payment_adapter=payment, ledger_adapter=ledger,
        )
        self.assertEqual(result.status, "closed")
        self.assertEqual(ledger.status, "closed")
        self.assertEqual(result.metrics["steps"], 50)
        self.assertEqual(result.metrics["source"], "ledger_and_receipts")
        self.assertEqual(result.metrics["usdc_authorized_base_units"] - result.metrics["usdc_refunded_base_units"],
                         result.metrics["usdc_spent_base_units"])
        self.assertIsNone(result.metrics["onchain_transactions"])

    def test_uncertain_commit_stops_before_another_provider_call(self):
        policy = load_policy(POLICY)
        ledger = ConfirmingLedger()
        payment = UncertainPayment()
        with self.assertRaisesRegex(SettlementFailed, "needs reconciliation"):
            LoopRail(budget=policy.budget_usdc_base_units).run(
                policy=policy, tools=mock_registry(), payment_adapter=payment, ledger_adapter=ledger,
            )
        self.assertEqual(payment.commits, 1)
        self.assertEqual(ledger.status, "aborted")

    def test_incorrect_receipt_cannot_be_reported_as_settled(self):
        policy = load_policy(POLICY)
        ledger = ConfirmingLedger()
        with self.assertRaisesRegex(SettlementFailed, "does not reconcile"):
            LoopRail(budget=policy.budget_usdc_base_units).run(
                policy=policy, tools=mock_registry(),
                payment_adapter=IncorrectReceiptPayment(), ledger_adapter=ledger,
            )
        self.assertEqual(ledger.status, "aborted")


if __name__ == "__main__":
    unittest.main()
