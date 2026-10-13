"""Deterministic providers and replay cassettes for the 50-step scenario."""

from __future__ import annotations

import json
from pathlib import Path
from random import Random
from typing import Any

from .agent import StepSpec
from .tools import Tool, ToolRegistry, ToolResult


PRICES = {
    "market_data": (1000, 20, 40),
    "inference": (2000, 80, 140),
    "news_search": (800, 30, 70),
    "coordination": (0, 1, 3),
}
PROVIDERS = {
    "market_data": "market_data",
    "inference": "inference",
    "news_search": "news",
    "coordination": "internal",
}
HEADLINES = (
    "SOL trading volume rises alongside higher volatility",
    "Network activity increases across Solana applications",
    "Market participants watch macro liquidity conditions",
    "On-chain activity remains elevated after the price move",
)


def _input_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["symbol", "step_index"],
        "properties": {
            "symbol": {"const": "SOL"},
            "step_index": {"type": "integer", "minimum": 0},
            "query": {"type": "string"},
        },
        "additionalProperties": False,
    }


def _mock_result(name: str, index: int, seed: int, latency_multiplier: float) -> ToolResult:
    price, low, high = PRICES[name]
    rng = Random(seed * 100_003 + index * 97 + sum(ord(char) for char in name))
    latency = round(rng.randint(low, high) * latency_multiplier)
    if name == "market_data":
        output = {
            "symbol": "SOL",
            "price_usd": round(150 + (index % 7 - 3) * 0.42, 2),
            "change_pct": round(1.1 + (index % 5) * 0.13, 2),
            "volume_usd": 1_250_000 + index * 9_000,
        }
    elif name == "news_search":
        output = {"headline": HEADLINES[index % len(HEADLINES)], "sentiment": "mixed"}
    elif name == "inference":
        output = {
            "classification": "elevated_volatility",
            "risk": "moderate",
            "confidence": round(0.78 + (index % 5) * 0.02, 2),
        }
    else:
        output = {"state": "thesis_updated", "checkpoint": index}
    return ToolResult(output, price, latency)


def mock_registry(
    *, seed: int = 42, fail_attempts: dict[int, set[int]] | None = None,
    latency_multiplier: float = 1.0,
) -> ToolRegistry:
    if latency_multiplier < 0:
        raise ValueError("latency_multiplier must be non-negative")
    failures = fail_attempts or {}
    registry = ToolRegistry()
    for name, (price, _, _) in PRICES.items():
        async def handle(arguments: dict[str, Any], attempt: int, tool_name: str = name) -> ToolResult:
            index = arguments["step_index"]
            if attempt in failures.get(index, set()):
                raise RuntimeError(f"Injected {tool_name} failure at step {index}")
            return _mock_result(tool_name, index, seed, latency_multiplier)

        registry.register(Tool(
            name=name,
            provider=PROVIDERS[name],
            estimated_cost_usdc_base_units=price,
            pricing_model="per_call",
            input_schema=_input_schema(),
            idempotent=True,
            timeout_ms=5_000,
            handler=handle,
        ))
    return registry


def replay_registry(path: Path) -> ToolRegistry:
    cassette = json.loads(path.read_text(encoding="utf-8"))
    if cassette.get("version") != 1 or cassette.get("scenario") != "market_intelligence":
        raise ValueError("Unsupported replay cassette")
    responses = cassette["responses"]
    registry = ToolRegistry()
    for name, (price, _, _) in PRICES.items():
        async def handle(arguments: dict[str, Any], attempt: int, tool_name: str = name) -> ToolResult:
            if attempt:
                raise ValueError("Replay cassette has no retry response")
            record = responses[str(arguments["step_index"])]
            if record["tool"] != tool_name:
                raise ValueError("Replay tool does not match step")
            return ToolResult(
                output=record["output"],
                actual_cost_usdc_base_units=record["cost_usdc_base_units"],
                provider_latency_ms=record["provider_latency_ms"],
            )

        registry.register(Tool(
            name=name,
            provider=PROVIDERS[name],
            estimated_cost_usdc_base_units=price,
            pricing_model="recorded_usage",
            input_schema=_input_schema(),
            idempotent=True,
            timeout_ms=5_000,
            handler=handle,
        ))
    return registry


def write_cassette(path: Path, steps: list[StepSpec], seed: int = 42) -> None:
    responses = {}
    for step in steps:
        index = step.arguments["step_index"]
        result = _mock_result(step.tool, index, seed, 1.0)
        responses[str(index)] = {
            "tool": step.tool,
            "output": result.output,
            "cost_usdc_base_units": result.actual_cost_usdc_base_units,
            "provider_latency_ms": result.provider_latency_ms,
        }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "version": 1, "scenario": "market_intelligence", "seed": seed,
        "responses": responses,
    }, indent=2) + "\n", encoding="utf-8")
