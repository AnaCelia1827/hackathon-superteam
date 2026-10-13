"""Tool definitions and validated invocation."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from jsonschema import Draft202012Validator


@dataclass(frozen=True)
class ToolResult:
    output: dict[str, Any]
    actual_cost_usdc_base_units: int
    provider_latency_ms: int


ToolHandler = Callable[[dict[str, Any], int], Awaitable[ToolResult]]


@dataclass(frozen=True)
class Tool:
    name: str
    provider: str
    estimated_cost_usdc_base_units: int
    pricing_model: str
    input_schema: dict[str, Any]
    idempotent: bool
    timeout_ms: int
    handler: ToolHandler
    fallback_tool: str | None = None


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Duplicate tool: {tool.name}")
        if type(tool.estimated_cost_usdc_base_units) is not int or tool.estimated_cost_usdc_base_units < 0:
            raise ValueError("Tool estimates must be non-negative USDC base units")
        if tool.timeout_ms < 1:
            raise ValueError("Tool timeout must be positive")
        Draft202012Validator.check_schema(tool.input_schema)
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        return self._tools[name]

    async def invoke(self, name: str, arguments: dict[str, Any], attempt: int = 0) -> ToolResult:
        tool = self.get(name)
        Draft202012Validator(tool.input_schema).validate(arguments)
        result = await asyncio.wait_for(tool.handler(arguments, attempt), timeout=tool.timeout_ms / 1000)
        if (
            type(result.actual_cost_usdc_base_units) is not int
            or result.actual_cost_usdc_base_units < 0
            or type(result.provider_latency_ms) is not int
            or result.provider_latency_ms < 0
        ):
            raise ValueError("Tool returned invalid cost or latency")
        return result
