"""Public Python entry point for offline and replay execution."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Any

from .adapters import LedgerAdapter, MockLedger, MockPaymentAdapter, PaymentAdapter
from .agent import MarketIntelligenceAgent
from .mocks import mock_registry, replay_registry
from .policy import Policy
from .runtime import EventSink, ExecutionEngine
from .tools import ToolRegistry


class LoopRailError(Exception):
    """Base error for the public SDK."""


class BudgetExceeded(LoopRailError):
    pass


class PolicyDenied(LoopRailError):
    pass


class KillSwitchTripped(LoopRailError):
    pass


class SettlementFailed(LoopRailError):
    pass


@dataclass(frozen=True)
class RunResult:
    metrics: dict[str, Any]
    events: list[dict[str, Any]]
    report: dict[str, Any]
    receipts: list[dict[str, Any]]
    policy_hash: str
    status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "metrics": self.metrics,
            "events": self.events,
            "report": self.report,
            "receipts": self.receipts,
            "policy_hash": self.policy_hash,
            "status": self.status,
        }


class LoopRail:
    """Start a policy-gated agent session with swappable adapters.

    The local and replay modes use virtual payment accounting. Real settlement
    requires the A6/A7 adapters and receipt reconciliation.
    """

    def __init__(
        self, *, network: str = "local", budget: int = 5_000_000,
        state: str = "memory", payment: str = "mock",
    ) -> None:
        if network not in {"local", "solana-devnet"}:
            raise ValueError("Only local and Solana devnet are allowed")
        if type(budget) is not int or budget < 0:
            raise ValueError("budget must be integer USDC base units")
        if state != "memory" or payment != "mock":
            raise NotImplementedError("Real state and payments require A6/A7 adapters")
        self.network = network
        self.budget = budget
        self.state = state
        self.payment = payment

    async def run_async(
        self, *, agent: MarketIntelligenceAgent | None = None,
        tools: ToolRegistry | None = None,
        policy: Policy | dict[str, Any],
        replay_path: Path | None = None,
        seed: int = 42,
        event_sink: EventSink | None = None,
        telemetry_sink: EventSink | None = None,
        stop_event: Event | None = None,
        wall_delay_ms: int = 0,
        payment_adapter: PaymentAdapter | None = None,
        ledger_adapter: LedgerAdapter | None = None,
    ) -> RunResult:
        chosen_policy = policy if isinstance(policy, Policy) else Policy.from_dict(policy)
        if chosen_policy.budget_usdc_base_units > self.budget:
            raise BudgetExceeded("Policy budget exceeds SDK spending ceiling")
        chosen_agent = agent or MarketIntelligenceAgent()
        if tools is not None and replay_path is not None:
            raise ValueError("Choose tools or replay_path, not both")
        registry = tools or (replay_registry(replay_path) if replay_path else mock_registry(seed=seed))
        mode = "replay" if replay_path else "mock"
        engine = ExecutionEngine(
            chosen_policy,
            registry,
            payment=payment_adapter or MockPaymentAdapter(),
            ledger=ledger_adapter or MockLedger(),
            session_id=f"{mode}-50",
            mode=mode,
            event_sink=event_sink,
            telemetry_sink=telemetry_sink,
            stop_event=stop_event,
            wall_delay_ms=wall_delay_ms,
        )
        try:
            data = await engine.run(chosen_agent)
        except NotImplementedError as error:
            raise SettlementFailed(str(error)) from error
        return RunResult(**data)

    def run(self, **kwargs: Any) -> RunResult:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.run_async(**kwargs))
        raise RuntimeError("Use await rail.run_async(...) inside an event loop")


def load_policy(path: Path) -> Policy:
    return Policy.from_dict(json.loads(path.read_text(encoding="utf-8")))
