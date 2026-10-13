"""LoopRail owned-provider price table.

All amounts are USDC base units (6 decimals) as integers, mirroring the runtime's
`apps/runtime/looprail/mocks.py::PRICES` so the demo, ledger and dashboard agree.

Provider ids follow `mocks.py::PROVIDERS`: `market_data`, `news`, `inference`
(coordination is internal and unpriced).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Price:
    provider_id: str
    tool: str
    base_units: int
    usd: str
    pricing_model: str
    description: str


# market_data $0.001, news $0.0008, inference $0.002 (per call).
PRICES: dict[str, Price] = {
    "market_data": Price(
        provider_id="market_data",
        tool="market_data",
        base_units=1000,
        usd="0.001",
        pricing_model="per_call",
        description="One SOL market snapshot (price, change, volume).",
    ),
    "news": Price(
        provider_id="news",
        tool="news_search",
        base_units=800,
        usd="0.0008",
        pricing_model="per_call",
        description="One news/context headline with sentiment.",
    ),
    "inference": Price(
        provider_id="inference",
        tool="inference",
        base_units=2000,
        usd="0.002",
        pricing_model="per_call",
        description="One inference classification (streamed; flat per request in the MVP).",
    ),
}


def pricing_payload() -> dict[str, dict[str, object]]:
    """Ungated JSON payload consumed by the dashboard and benchmark."""
    return {
        pid: {
            "provider_id": p.provider_id,
            "tool": p.tool,
            "usdc_base_units": p.base_units,
            "usd": p.usd,
            "pricing_model": p.pricing_model,
            "description": p.description,
        }
        for pid, p in PRICES.items()
    }
