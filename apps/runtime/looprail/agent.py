"""Market intelligence scenario and report assembly."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import Any


@dataclass(frozen=True)
class StepSpec:
    tool: str
    arguments: dict[str, Any]
    parallel_group: str | None = None


class MarketIntelligenceAgent:
    symbol = "SOL"
    detected_event = "Elevated price volatility and network activity"

    def plan(self) -> list[StepSpec]:
        steps: list[StepSpec] = []
        for batch in range(4):
            for _ in range(5):
                index = len(steps)
                steps.append(StepSpec(
                    "market_data",
                    {"symbol": self.symbol, "step_index": index, "query": f"market-window-{index}"},
                    f"market-{batch}",
                ))
        for batch in range(2):
            for _ in range(5):
                index = len(steps)
                steps.append(StepSpec(
                    "news_search",
                    {"symbol": self.symbol, "step_index": index, "query": f"context-{index}"},
                    f"news-{batch}",
                ))
        for _ in range(15):
            index = len(steps)
            steps.append(StepSpec(
                "inference",
                {"symbol": self.symbol, "step_index": index, "query": f"classify-{index}"},
            ))
        for _ in range(5):
            index = len(steps)
            steps.append(StepSpec(
                "coordination",
                {"symbol": self.symbol, "step_index": index, "query": f"checkpoint-{index}"},
            ))
        return steps

    def report(self, outputs: dict[int, dict[str, Any]], *, mode: str) -> dict[str, Any]:
        market = [item for item in outputs.values() if "price_usd" in item]
        news = [item for item in outputs.values() if "headline" in item]
        assessments = [item for item in outputs.values() if "classification" in item]
        prices = [item["price_usd"] for item in market]
        risk = max(
            (item["risk"] for item in assessments),
            key=lambda value: {"low": 0, "moderate": 1, "high": 2}.get(value, 0),
            default="unknown",
        )
        return {
            "title": f"{self.symbol} Market Intelligence Report",
            "detected_event": self.detected_event,
            "mode": mode,
            "market_observations": len(market),
            "news_items": len(news),
            "inference_assessments": len(assessments),
            "price_range_usd": [min(prices), max(prices)] if prices else None,
            "average_price_usd": round(mean(prices), 2) if prices else None,
            "headline_examples": [item["headline"] for item in news[:3]],
            "classification": assessments[-1]["classification"] if assessments else "undetermined",
            "risk": risk,
            "recommendation": (
                "Monitor volatility and validate the signal with fresh market data before taking action."
                if assessments and market else
                "Insufficient evidence. Gather more market data before taking action."
            ),
        }
