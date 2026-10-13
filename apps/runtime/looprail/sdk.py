"""Public Python entry point for offline and replay execution."""

from __future__ import annotations

import asyncio
import json
import secrets
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

    Local and replay modes use virtual payment accounting. Inject both real
    adapters and a real tool registry for a live run.
    """

    def __init__(
        self, *, network: str = "local", budget: int = 5_000_000,
        state: str = "memory", payment: str = "mock",
    ) -> None:
        if network not in {"local", "solana-devnet"}:
            raise ValueError("Only local and Solana devnet are allowed")
        if type(budget) is not int or budget < 0:
            raise ValueError("budget must be integer USDC base units")
        if state not in {"memory", "ledger"} or payment not in {"mock", "mpp"}:
            raise ValueError("state must be memory or ledger; payment must be mock or mpp")
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
        session_id: str | None = None,
    ) -> RunResult:
        chosen_policy = policy if isinstance(policy, Policy) else Policy.from_dict(policy)
        if chosen_policy.budget_usdc_base_units > self.budget:
            raise BudgetExceeded("Policy budget exceeds SDK spending ceiling")
        chosen_agent = agent or MarketIntelligenceAgent()
        if tools is not None and replay_path is not None:
            raise ValueError("Choose tools or replay_path, not both")
        live = payment_adapter is not None or ledger_adapter is not None or self.state == "ledger" or self.payment == "mpp"
        if live and (payment_adapter is None or ledger_adapter is None or tools is None or replay_path is not None):
            raise ValueError("Live mode requires both real adapters and a tool registry; replay is separate")
        if live and (isinstance(payment_adapter, MockPaymentAdapter) or isinstance(ledger_adapter, MockLedger)):
            raise ValueError("Live mode cannot use mock adapters")
        registry = tools or (replay_registry(replay_path) if replay_path else mock_registry(seed=seed))
        mode = "live" if live else ("replay" if replay_path else "mock")
        engine = ExecutionEngine(
            chosen_policy,
            registry,
            payment=payment_adapter or MockPaymentAdapter(),
            ledger=ledger_adapter or MockLedger(),
            session_id=session_id or (secrets.token_hex(32) if live else f"{mode}-50"),
            mode=mode,
            event_sink=event_sink,
            telemetry_sink=telemetry_sink,
            stop_event=stop_event,
            wall_delay_ms=wall_delay_ms,
        )
        try:
            data = await engine.run(chosen_agent)
        except (RuntimeError, OSError, ValueError) as error:
            if not live:
                raise
            details = "; ".join(getattr(error, "__notes__", ()))
            raise SettlementFailed(f"{error}; {details}" if details else str(error)) from error
        return RunResult(**data)

    def run(self, **kwargs: Any) -> RunResult:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.run_async(**kwargs))
        raise RuntimeError("Use await rail.run_async(...) inside an event loop")


def load_policy(path: Path) -> Policy:
    return Policy.from_dict(json.loads(path.read_text(encoding="utf-8")))
