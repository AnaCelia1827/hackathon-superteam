"""Pure spending decisions and atomic, in-memory reservations.

The in-memory tracker is a local implementation of the shared contract. The
on-chain ledger and payment adapter must enforce their own limits as well.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from threading import RLock
from typing import Any

import rfc8785


def _money(value: Any, name: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a non-negative integer in USDC base units")
    return value


def policy_hash(document: dict[str, Any]) -> str:
    """Return the SHA-256 digest of RFC 8785 canonical JSON."""
    return sha256(rfc8785.dumps(document)).hexdigest()


def request_signature(tool: str, arguments: dict[str, Any]) -> str:
    return sha256(rfc8785.dumps({"tool": tool, "arguments": arguments})).hexdigest()


@dataclass(frozen=True)
class ProviderLimit:
    allocation_usdc_base_units: int
    max_price_per_call_usdc_base_units: int
    cache_ttl_seconds: int = 0
    fallback_provider: str | None = None


@dataclass(frozen=True)
class Policy:
    budget_usdc_base_units: int
    max_steps: int
    provider_limits: dict[str, ProviderLimit]
    max_retries_per_step: int = 0
    retry_backoff_ms: int = 100
    max_error_rate: float = 1.0
    kill_switch_budget_ratio: float = 1.0
    max_repeated_calls: int = 3
    hash: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Policy":
        if data.get("version") != 1:
            raise ValueError("Policy version must be 1")
        if not isinstance(data.get("provider_limits"), dict) or not data["provider_limits"]:
            raise ValueError("provider_limits must contain at least one provider")
        limits: dict[str, ProviderLimit] = {}
        for name, value in data["provider_limits"].items():
            if not isinstance(name, str) or not name or not isinstance(value, dict):
                raise ValueError("Invalid provider limit")
            ttl = value.get("cache_ttl_seconds", 0)
            if type(ttl) is not int or ttl < 0:
                raise ValueError("cache_ttl_seconds must be a non-negative integer")
            limits[name] = ProviderLimit(
                allocation_usdc_base_units=_money(
                    value["allocation_usdc_base_units"], "allocation_usdc_base_units"
                ),
                max_price_per_call_usdc_base_units=_money(
                    value["max_price_per_call_usdc_base_units"], "max_price_per_call_usdc_base_units"
                ),
                cache_ttl_seconds=ttl,
                fallback_provider=value.get("fallback_provider"),
            )
        for limit in limits.values():
            if limit.fallback_provider is not None and limit.fallback_provider not in limits:
                raise ValueError("fallback_provider must name a configured provider")
        budget = _money(data["budget_usdc_base_units"], "budget_usdc_base_units")
        if sum(limit.allocation_usdc_base_units for limit in limits.values()) > budget:
            raise ValueError("Provider allocations exceed the task budget")
        max_steps = data["max_steps"]
        retries = data.get("max_retries_per_step", 0)
        backoff = data.get("retry_backoff_ms", 100)
        repeated = data.get("max_repeated_calls", 3)
        if any(type(value) is not int or value < minimum for value, minimum in (
            (max_steps, 1), (retries, 0), (backoff, 0), (repeated, 1)
        )):
            raise ValueError("Invalid integer policy limit")
        error_rate = data.get("max_error_rate", 1.0)
        budget_ratio = data.get("kill_switch_budget_ratio", 1.0)
        if (type(error_rate) not in (int, float) or not 0 <= error_rate <= 1
                or type(budget_ratio) not in (int, float) or not 0 < budget_ratio <= 1):
            raise ValueError("Invalid kill-switch threshold")
        return cls(
            budget_usdc_base_units=budget,
            max_steps=max_steps,
            provider_limits=limits,
            max_retries_per_step=retries,
            retry_backoff_ms=backoff,
            max_error_rate=float(error_rate),
            kill_switch_budget_ratio=float(budget_ratio),
            max_repeated_calls=repeated,
            hash=policy_hash(deepcopy(data)),
        )

    @property
    def allocations(self) -> dict[str, int]:
        return {
            name: limit.allocation_usdc_base_units
            for name, limit in self.provider_limits.items()
        }


@dataclass(frozen=True)
class Context:
    spent: int
    reserved: int
    provider_spent: int
    provider_reserved: int
    completed_steps: int
    errors: int
    pending_steps: int = 0
    repeated_calls: int = 0
    cached: bool = False
    retry_index: int = 0
    aborted: bool = False
    fallback_estimate: int | None = None


@dataclass(frozen=True)
class Decision:
    action: str
    reason: str
    provider: str | None = None


def evaluate(policy: Policy, context: Context, provider: str, estimate: int) -> Decision:
    """Evaluate a proposed call without I/O or mutation."""
    if type(estimate) is not int or estimate < 0:
        return Decision("deny", "invalid_estimate")
    if context.aborted:
        return Decision("deny", "aborted")
    limit = policy.provider_limits.get(provider)
    if limit is None:
        return Decision("deny", "unknown_provider")
    if context.completed_steps + context.pending_steps >= policy.max_steps:
        return Decision("deny", "max_steps")
    if context.completed_steps and context.errors / context.completed_steps > policy.max_error_rate:
        return Decision("deny", "error_rate_kill_switch")
    if context.spent >= policy.budget_usdc_base_units * policy.kill_switch_budget_ratio:
        return Decision("deny", "budget_kill_switch")
    if context.repeated_calls > policy.max_repeated_calls:
        return Decision("deny", "loop_detected")
    if context.retry_index > policy.max_retries_per_step:
        return Decision("deny", "retry_limit")
    if context.cached:
        return Decision("cache_hit", "cached_response", provider)
    if estimate > limit.max_price_per_call_usdc_base_units:
        if limit.fallback_provider:
            fallback = policy.provider_limits[limit.fallback_provider]
            fallback_estimate = context.fallback_estimate
            if (
                type(fallback_estimate) is int
                and 0 <= fallback_estimate < estimate
                and fallback_estimate <= fallback.max_price_per_call_usdc_base_units
                and context.spent + context.reserved + fallback_estimate <= policy.budget_usdc_base_units
            ):
                return Decision("fallback", "price_cap", limit.fallback_provider)
        return Decision("deny", "price_cap")
    if context.spent + context.reserved + estimate > policy.budget_usdc_base_units:
        return Decision("deny", "budget_exceeded")
    if context.provider_spent + context.provider_reserved + estimate > limit.allocation_usdc_base_units:
        return Decision("deny", "provider_allocation_exceeded")
    return Decision("allow", "within_policy", provider)


def retry_delay_ms(policy: Policy, retry_index: int) -> int:
    """Exponential backoff before retry_index (1 is the first retry)."""
    if retry_index < 1 or retry_index > policy.max_retries_per_step:
        raise ValueError("retry_index outside policy")
    return policy.retry_backoff_ms * (2 ** (retry_index - 1))


@dataclass(frozen=True)
class Reservation:
    id: int
    provider: str
    amount: int


class BudgetTracker:
    """Atomic budget accounting for concurrent calls in one runtime process."""

    def __init__(self, policy: Policy):
        self.policy = policy
        self.spent = 0
        self.reserved = 0
        self.provider_spent = {name: 0 for name in policy.provider_limits}
        self.provider_reserved = {name: 0 for name in policy.provider_limits}
        self.completed_steps = 0
        self.errors = 0
        self.aborted = False
        self._next_id = 1
        self._active: dict[int, Reservation] = {}
        self._lock = RLock()

    def context(self, provider: str, **kwargs: Any) -> Context:
        with self._lock:
            return Context(
                spent=self.spent,
                reserved=self.reserved,
                provider_spent=self.provider_spent.get(provider, 0),
                provider_reserved=self.provider_reserved.get(provider, 0),
                completed_steps=self.completed_steps,
                errors=self.errors,
                pending_steps=len(self._active),
                aborted=self.aborted,
                **kwargs,
            )

    def reserve(self, provider: str, estimate: int, **kwargs: Any) -> tuple[Decision, Reservation | None]:
        with self._lock:
            decision = evaluate(self.policy, self.context(provider, **kwargs), provider, estimate)
            if decision.action != "allow":
                return decision, None
            reservation = Reservation(self._next_id, provider, estimate)
            self._next_id += 1
            self._active[reservation.id] = reservation
            self.reserved += estimate
            self.provider_reserved[provider] += estimate
            return decision, reservation

    def commit(self, reservation: Reservation, actual: int) -> None:
        if type(actual) is not int or actual < 0 or actual > reservation.amount:
            raise ValueError("Actual cost must fit the reservation")
        with self._lock:
            self._take(reservation)
            self.spent += actual
            self.provider_spent[reservation.provider] += actual
            self.completed_steps += 1

    def release(self, reservation: Reservation, *, error: bool = False, final: bool = True) -> None:
        with self._lock:
            self._take(reservation)
            if final:
                self.completed_steps += 1
                self.errors += int(error)

    def record_cache_hit(self) -> None:
        with self._lock:
            if self.completed_steps + len(self._active) >= self.policy.max_steps:
                raise ValueError("Maximum step count reached")
            self.completed_steps += 1

    def abort(self) -> None:
        with self._lock:
            self.aborted = True

    def _take(self, reservation: Reservation) -> None:
        if self._active.get(reservation.id) != reservation:
            raise ValueError("Reservation already consumed or unknown")
        del self._active[reservation.id]
        self.reserved -= reservation.amount
        self.provider_reserved[reservation.provider] -= reservation.amount
