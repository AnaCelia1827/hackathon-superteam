"""Offline tool loop for the first LoopRail demo."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from random import Random
from statistics import median

from .policy import BudgetTracker, Policy


@dataclass(frozen=True)
class Tool:
    name: str
    provider: str
    estimated_cost: int
    latency_min_ms: int
    latency_max_ms: int


@dataclass(frozen=True)
class ToolResult:
    actual_cost: int
    provider_latency_ms: int


class MockToolRegistry:
    def __init__(self, seed: int = 42):
        self.random = Random(seed)
        self.tools = {
            "market_data": Tool("market_data", "market_data", 1000, 20, 40),
            "inference": Tool("inference", "inference", 2000, 80, 140),
            "news_search": Tool("news_search", "news", 800, 30, 70),
            "coordination": Tool("coordination", "internal", 0, 1, 3),
        }

    def invoke(self, name: str) -> ToolResult:
        tool = self.tools[name]
        return ToolResult(
            actual_cost=tool.estimated_cost,
            provider_latency_ms=self.random.randint(tool.latency_min_ms, tool.latency_max_ms),
        )


def scenario_50_steps() -> list[str]:
    return (
        ["market_data"] * 20
        + ["inference"] * 15
        + ["news_search"] * 10
        + ["coordination"] * 5
    )


def _percentile(values: list[int], fraction: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = max(0, int((len(ordered) * fraction + 0.999999)) - 1)
    return ordered[index]


def run_scenario(policy: Policy, *, seed: int = 42, fail_on_steps: frozenset[int] = frozenset()) -> dict:
    registry = MockToolRegistry(seed)
    tracker = BudgetTracker(policy)
    events = []
    clock = datetime(2026, 1, 1, tzinfo=timezone.utc)
    provider_latencies = []
    for index, tool_name in enumerate(scenario_50_steps()):
        tool = registry.tools[tool_name]
        decision, reservation = tracker.reserve(tool.provider, tool.estimated_cost)
        if reservation is None:
            event = {
                "version": 1, "session_id": "mock-50", "step_index": index,
                "tool": tool.name, "provider": tool.provider,
                "outcome": "denied", "reason": decision.reason,
                "cost_usdc_base_units": 0, "provider_latency_ms": 0,
                "looprail_overhead_ms": 0, "cache_hit": False,
                "occurred_at": clock.isoformat().replace("+00:00", "Z"),
            }
        else:
            result = registry.invoke(tool_name)
            provider_latencies.append(result.provider_latency_ms)
            clock += timedelta(milliseconds=result.provider_latency_ms)
            failed = index in fail_on_steps
            if failed:
                tracker.release(reservation, error=True)
            else:
                tracker.commit(reservation, result.actual_cost)
            event = {
                "version": 1, "session_id": "mock-50", "step_index": index,
                "tool": tool.name, "provider": tool.provider,
                "outcome": "error" if failed else "success",
                "reason": "injected_failure" if failed else decision.reason,
                "cost_usdc_base_units": 0 if failed else result.actual_cost,
                "provider_latency_ms": result.provider_latency_ms,
                "looprail_overhead_ms": 0, "cache_hit": False,
                "occurred_at": clock.isoformat().replace("+00:00", "Z"),
            }
        events.append(event)
    metrics = {
        "version": 1, "session_id": "mock-50", "mode": "mock",
        "steps": len(events), "duration_ms": sum(provider_latencies),
        "provider_latency_p50_ms": int(median(provider_latencies)) if provider_latencies else 0,
        "provider_latency_p95_ms": _percentile(provider_latencies, 0.95),
        "looprail_overhead_p50_ms": 0, "looprail_overhead_p95_ms": 0,
        "usdc_authorized_base_units": 0,
        "usdc_reserved_base_units": tracker.reserved,
        "usdc_spent_base_units": tracker.spent,
        "usdc_refunded_base_units": 0,
        "onchain_transactions": 0, "settlements": 0, "source": "simulation",
    }
    return {"policy_decisions": [event["reason"] for event in events], "events": events, "metrics": metrics}
