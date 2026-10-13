"""Policy-gated agent execution with swappable ledger and payment adapters."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from statistics import median
from threading import Event
from typing import Any, Callable

from .adapters import LedgerAdapter, MockLedger, MockPaymentAdapter, PaymentAdapter
from .agent import MarketIntelligenceAgent, StepSpec
from .mocks import mock_registry
from .policy import BudgetTracker, Policy, evaluate, request_signature, retry_delay_ms
from .tools import ToolRegistry


EventSink = Callable[[dict[str, Any]], None]
START_TIME = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _percentile(values: list[int], fraction: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, int(len(ordered) * fraction + 0.999999) - 1))]


def _event(
    session_id: str, index: int, tool: str, provider: str, outcome: str,
    reason: str, cost: int = 0, latency: int = 0, cache_hit: bool = False,
    retry_count: int = 0, retry_backoff_ms: int = 0,
) -> dict[str, Any]:
    return {
        "version": 1,
        "session_id": session_id,
        "step_index": index,
        "tool": tool,
        "provider": provider,
        "outcome": outcome,
        "reason": reason,
        "cost_usdc_base_units": cost,
        "provider_latency_ms": latency,
        "looprail_overhead_ms": None,
        "cache_hit": cache_hit,
        "retry_count": retry_count,
        "retry_backoff_ms": retry_backoff_ms,
        "occurred_at": "",
    }


class ExecutionEngine:
    def __init__(
        self,
        policy: Policy,
        tools: ToolRegistry,
        *,
        payment: PaymentAdapter | None = None,
        ledger: LedgerAdapter | None = None,
        session_id: str = "mock-50",
        mode: str = "mock",
        event_sink: EventSink | None = None,
        telemetry_sink: EventSink | None = None,
        stop_event: Event | None = None,
        wall_delay_ms: int = 0,
    ) -> None:
        if mode not in {"mock", "replay", "live"}:
            raise ValueError("Unknown execution mode")
        self.policy = policy
        self.tools = tools
        self.payment = payment or MockPaymentAdapter()
        self.ledger = ledger or MockLedger()
        self.session_id = session_id
        self.mode = mode
        self.event_sink = event_sink
        self.telemetry_sink = telemetry_sink
        self.stop_event = stop_event or Event()
        self.wall_delay_ms = wall_delay_ms
        self.tracker = BudgetTracker(policy)
        self.cache: dict[str, tuple[int, dict[str, Any]]] = {}
        self.channels = {}

    async def run(self, agent: MarketIntelligenceAgent) -> dict[str, Any]:
        plan = agent.plan()
        validate_policy = getattr(self.ledger, "validate_policy", None)
        if validate_policy is not None:
            validate_policy(self.policy, {step.tool for step in plan})
        self.channels = {
            provider: self.payment.open(provider, allocation)
            for provider, allocation in self.policy.allocations.items()
        }
        self.ledger.open(self.session_id, self.policy.hash)
        self._publish_budget()
        outputs: dict[int, dict[str, Any]] = {}
        logical_ms = 0
        last_signature = None
        repeated_count = 0
        index = 0
        mock_adapters = isinstance(self.payment, MockPaymentAdapter) and isinstance(self.ledger, MockLedger)
        authorized = refunded = settlements = 0
        try:
            while index < len(plan):
                if self.stop_event.is_set():
                    self.tracker.abort()
                    break
                group = [plan[index]]
                group_key = plan[index].parallel_group
                if group_key is not None:
                    while index + len(group) < len(plan) and plan[index + len(group)].parallel_group == group_key:
                        group.append(plan[index + len(group)])
                jobs = []
                for offset, step in enumerate(group):
                    signature = request_signature(step.tool, step.arguments)
                    repeated_count = repeated_count + 1 if signature == last_signature else 1
                    last_signature = signature
                    jobs.append((index + offset, step, logical_ms, repeated_count, signature))
                # A paid run never starts the next provider call while a voucher is uncertain.
                if self.mode == "live":
                    for job in jobs:
                        event, output, elapsed = await self._execute_step(*job)
                        logical_ms += elapsed
                        event["occurred_at"] = (START_TIME + timedelta(milliseconds=logical_ms)).isoformat().replace("+00:00", "Z")
                        self.ledger.record_step(self.session_id, event)
                        if output is not None:
                            outputs[event["step_index"]] = output
                        if self.event_sink is not None:
                            self.event_sink(dict(event))
                else:
                    results = await asyncio.gather(*(self._execute_step(*job) for job in jobs))
                    logical_ms += max((elapsed for _, _, elapsed in results), default=0)
                    for event, output, _ in results:
                        event["occurred_at"] = (START_TIME + timedelta(milliseconds=logical_ms)).isoformat().replace("+00:00", "Z")
                        self.ledger.record_step(self.session_id, event)
                        if output is not None:
                            outputs[event["step_index"]] = output
                        if self.event_sink is not None:
                            self.event_sink(dict(event))
                index += len(group)
                if self.wall_delay_ms:
                    await asyncio.sleep(self.wall_delay_ms / 1000)

            receipts = self.payment.close_all()
            if not mock_adapters:
                authorized, refunded, settlements = self._reconcile_receipts(receipts)
            if self.stop_event.is_set():
                self.ledger.abort(self.session_id)
            else:
                self.ledger.close(self.session_id)
        except Exception as error:
            self.tracker.abort()
            for operation in (lambda: self.ledger.abort(self.session_id), self.payment.close_all):
                try:
                    operation()
                except Exception as cleanup_error:
                    error.add_note(f"Cleanup needs reconciliation: {cleanup_error}")
            raise
        events = self.ledger.events(self.session_id)
        latencies = [event["provider_latency_ms"] for event in events if event["provider_latency_ms"] > 0]
        overheads = [event["looprail_overhead_ms"] for event in events if event["looprail_overhead_ms"] is not None]
        if self.mode == "live" and (isinstance(self.payment, MockPaymentAdapter) or isinstance(self.ledger, MockLedger)):
            raise ValueError("Live mode requires real ledger and payment adapters")
        metrics = {
            "version": 1,
            "session_id": self.session_id,
            "mode": self.mode,
            "steps": len(events),
            "duration_ms": logical_ms,
            "provider_latency_p50_ms": int(median(latencies)) if latencies else 0,
            "provider_latency_p95_ms": _percentile(latencies, 0.95),
            "looprail_overhead_p50_ms": int(median(overheads)) if overheads else None,
            "looprail_overhead_p95_ms": _percentile(overheads, 0.95) if overheads else None,
            "policy_budget_usdc_base_units": self.policy.budget_usdc_base_units,
            "usdc_authorized_base_units": authorized,
            "usdc_reserved_base_units": self.tracker.reserved,
            "usdc_spent_base_units": sum(event["cost_usdc_base_units"] for event in events),
            "usdc_refunded_base_units": refunded,
            "onchain_transactions": 0 if mock_adapters else None,
            "settlements": settlements,
            "source": "simulation" if mock_adapters or any(receipt.get("simulated") for receipt in receipts) else "ledger_and_receipts",
            "retry_count": sum(event["retry_count"] for event in events),
        }
        if metrics["usdc_spent_base_units"] != self.tracker.spent:
            raise ValueError("Ledger and budget tracker disagree about spending")
        return {
            "events": events,
            "metrics": metrics,
            "report": agent.report(outputs, mode=self.mode),
            "receipts": receipts,
            "policy_hash": self.policy.hash,
            "status": "aborted" if self.stop_event.is_set() else "closed",
        }

    def _reconcile_receipts(self, receipts: list[dict[str, Any]]) -> tuple[int, int, int]:
        authorized = refunded = settlements = 0
        seen_providers: set[str] = set()
        for receipt in receipts:
            provider = receipt.get("provider")
            deposited = receipt.get("usdc_deposited")
            spent = receipt.get("usdc_spent")
            refund = receipt.get("usdc_refunded")
            count = receipt.get("settlements")
            simulated = receipt.get("simulated")
            if provider not in self.policy.allocations or provider in seen_providers:
                raise ValueError("Payment receipt has an unknown or duplicate provider")
            seen_providers.add(provider)
            if any(type(value) is not int or value < 0 for value in (deposited, spent, refund, count)):
                raise ValueError("Payment receipt has invalid USDC amounts or settlement count")
            if (type(simulated) is not bool or deposited != spent + refund
                    or deposited > self.policy.allocations[provider]
                    or spent != self.tracker.provider_spent[provider]
                    or count != (0 if simulated else 1)):
                raise ValueError("Payment receipt does not reconcile")
            if not simulated and not (receipt.get("settled_signature") or receipt.get("signature")):
                raise ValueError("On-chain payment receipt has no settlement signature")
            authorized += deposited
            refunded += refund
            settlements += count
        if (authorized - refunded != self.tracker.spent
                or any(spent and provider not in seen_providers for provider, spent in self.tracker.provider_spent.items())):
            raise ValueError("Payment receipts and budget tracker disagree about spending")
        return authorized, refunded, settlements

    def _publish_budget(self) -> None:
        if self.telemetry_sink is not None:
            context = self.tracker.context("")
            self.telemetry_sink({
                "type": "budget",
                "authorized_usdc_base_units": 0,
                "reserved_usdc_base_units": context.reserved,
                "spent_usdc_base_units": context.spent,
                "remaining_usdc_base_units": max(0, self.policy.budget_usdc_base_units - context.spent - context.reserved),
            })

    async def _execute_step(
        self, index: int, step: StepSpec, now_ms: int, repeated_count: int, signature: str,
    ) -> tuple[dict[str, Any], dict[str, Any] | None, int]:
        tool = self.tools.get(step.tool)
        provider = tool.provider
        estimate = tool.estimated_cost_usdc_base_units
        cached = self.cache.get(signature)
        cache_valid = cached is not None and now_ms < cached[0]
        fallback_tool = self.tools.get(tool.fallback_tool) if tool.fallback_tool else None
        decision = evaluate(
            self.policy,
            self.tracker.context(
                provider, repeated_calls=repeated_count, cached=cache_valid,
                fallback_estimate=fallback_tool.estimated_cost_usdc_base_units if fallback_tool else None,
            ),
            provider,
            estimate,
        )
        if decision.action == "cache_hit":
            self.tracker.record_cache_hit()
            return _event(self.session_id, index, tool.name, provider, "ok", decision.reason, cache_hit=True), cached[1], 0
        if decision.action == "fallback":
            if fallback_tool is None or fallback_tool.provider != decision.provider:
                raise ValueError("Policy fallback has no matching tool")
            tool = fallback_tool
            provider = tool.provider
            estimate = tool.estimated_cost_usdc_base_units
        elif decision.action == "deny":
            return _event(self.session_id, index, tool.name, provider, "denied", decision.reason), None, 0

        elapsed_ms = 0
        backoff_ms = 0
        for attempt in range(self.policy.max_retries_per_step + 1):
            reserve_decision, budget_reservation = self.tracker.reserve(
                provider, estimate, repeated_calls=repeated_count, retry_index=attempt,
            )
            if budget_reservation is None:
                return _event(self.session_id, index, tool.name, provider, "denied", reserve_decision.reason, retry_count=attempt), None, elapsed_ms
            self._publish_budget()
            payment_reservation = None
            commit_started = False
            payment_committed = False
            try:
                payment_reservation = self.payment.reserve(self.channels[provider], estimate)
                result = await self.tools.invoke(tool.name, step.arguments, attempt)
                if result.actual_cost_usdc_base_units > estimate:
                    raise ValueError("Provider cost exceeded the authorized estimate")
                commit_started = True
                self.payment.commit(payment_reservation, result.actual_cost_usdc_base_units)
                payment_committed = True
                self.tracker.commit(budget_reservation, result.actual_cost_usdc_base_units)
                self._publish_budget()
                elapsed_ms += result.provider_latency_ms
                ttl = self.policy.provider_limits[provider].cache_ttl_seconds
                if tool.idempotent and ttl:
                    self.cache[signature] = (now_ms + elapsed_ms + ttl * 1000, result.output)
                reason = "fallback_provider" if decision.action == "fallback" else "within_policy"
                return (
                    _event(
                        self.session_id, index, tool.name, provider, "ok", reason,
                        cost=result.actual_cost_usdc_base_units, latency=result.provider_latency_ms,
                        retry_count=attempt, retry_backoff_ms=backoff_ms,
                    ),
                    result.output,
                    elapsed_ms,
                )
            except Exception as error:
                if payment_committed:
                    raise RuntimeError(
                        f"Payment committed for reservation {payment_reservation.id} "
                        "but local accounting failed; reconciliation is required"
                    ) from error
                if payment_reservation is not None:
                    try:
                        self.payment.release(payment_reservation)
                    except Exception as release_error:
                        raise RuntimeError(
                            f"Payment reservation {payment_reservation.id} needs reconciliation; "
                            "stop the session before another provider call"
                        ) from release_error
                if commit_started:
                    raise RuntimeError(
                        f"Payment commit for reservation {payment_reservation.id} failed; "
                        "the provider call must not be repeated"
                    ) from error
                final = attempt == self.policy.max_retries_per_step
                self.tracker.release(budget_reservation, error=final, final=final)
                self._publish_budget()
                if final:
                    return (
                        _event(
                            self.session_id, index, tool.name, provider, "error",
                            type(error).__name__, retry_count=attempt, retry_backoff_ms=backoff_ms,
                        ),
                        None,
                        elapsed_ms,
                    )
                delay = retry_delay_ms(self.policy, attempt + 1)
                elapsed_ms += delay
                backoff_ms += delay
        raise AssertionError("Retry loop must return")


def run_scenario(
    policy: Policy, *, seed: int = 42, fail_on_steps: frozenset[int] = frozenset(),
) -> dict[str, Any]:
    failures = {
        index: set(range(policy.max_retries_per_step + 1))
        for index in fail_on_steps
    }
    engine = ExecutionEngine(policy, mock_registry(seed=seed, fail_attempts=failures))
    return asyncio.run(engine.run(MarketIntelligenceAgent()))
