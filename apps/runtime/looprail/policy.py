"""Pure policy evaluation plus atomic in-memory budget reservations."""

from dataclasses import dataclass
from threading import Lock


@dataclass(frozen=True)
class ProviderLimit:
    allocation_usdc_base_units: int
    max_price_per_call_usdc_base_units: int


@dataclass(frozen=True)
class Policy:
    budget_usdc_base_units: int
    max_steps: int
    provider_limits: dict[str, ProviderLimit]
    max_error_rate: float = 1.0
    kill_switch_budget_ratio: float = 1.0

    @classmethod
    def from_dict(cls, data: dict) -> "Policy":
        if data.get("version") != 1:
            raise ValueError("Policy version must be 1")
        limits = {
            name: ProviderLimit(
                allocation_usdc_base_units=value["allocation_usdc_base_units"],
                max_price_per_call_usdc_base_units=value["max_price_per_call_usdc_base_units"],
            )
            for name, value in data["provider_limits"].items()
        }
        policy = cls(
            budget_usdc_base_units=data["budget_usdc_base_units"],
            max_steps=data["max_steps"],
            provider_limits=limits,
            max_error_rate=data.get("max_error_rate", 1.0),
            kill_switch_budget_ratio=data.get("kill_switch_budget_ratio", 1.0),
        )
        if (
            policy.budget_usdc_base_units < 0
            or policy.max_steps < 1
            or not 0 <= policy.max_error_rate <= 1
            or not 0 < policy.kill_switch_budget_ratio <= 1
        ):
            raise ValueError("Invalid policy limits")
        if any(
            limit.allocation_usdc_base_units < 0
            or limit.max_price_per_call_usdc_base_units < 0
            for limit in limits.values()
        ):
            raise ValueError("Money values must be non-negative integers")
        if any(type(value) is not int for value in [policy.budget_usdc_base_units, *(
            amount
            for limit in limits.values()
            for amount in (limit.allocation_usdc_base_units, limit.max_price_per_call_usdc_base_units)
        )]):
            raise ValueError("Money values must be integers")
        return policy


@dataclass(frozen=True)
class Context:
    spent: int
    reserved: int
    provider_spent: int
    provider_reserved: int
    completed_steps: int
    errors: int
    pending_steps: int = 0


@dataclass(frozen=True)
class Decision:
    action: str
    reason: str


def evaluate(policy: Policy, context: Context, provider: str, estimate: int) -> Decision:
    """Evaluate a proposed call without changing state or performing I/O."""
    if type(estimate) is not int or estimate < 0:
        return Decision("deny", "invalid_estimate")
    limit = policy.provider_limits.get(provider)
    if limit is None:
        return Decision("deny", "unknown_provider")
    if context.completed_steps + context.pending_steps >= policy.max_steps:
        return Decision("deny", "max_steps")
    if context.completed_steps > 0 and context.errors / context.completed_steps > policy.max_error_rate:
        return Decision("deny", "error_rate_kill_switch")
    if context.spent >= policy.budget_usdc_base_units * policy.kill_switch_budget_ratio:
        return Decision("deny", "budget_kill_switch")
    if estimate > limit.max_price_per_call_usdc_base_units:
        return Decision("deny", "price_cap")
    if context.spent + context.reserved + estimate > policy.budget_usdc_base_units:
        return Decision("deny", "budget_exceeded")
    if context.provider_spent + context.provider_reserved + estimate > limit.allocation_usdc_base_units:
        return Decision("deny", "provider_allocation_exceeded")
    return Decision("allow", "within_policy")


@dataclass(frozen=True)
class Reservation:
    id: int
    provider: str
    amount: int


class BudgetTracker:
    """The lock makes reserve/commit/release atomic for concurrent tool calls."""

    def __init__(self, policy: Policy):
        self.policy = policy
        self.spent = 0
        self.reserved = 0
        self.provider_spent = {name: 0 for name in policy.provider_limits}
        self.provider_reserved = {name: 0 for name in policy.provider_limits}
        self.completed_steps = 0
        self.errors = 0
        self._next_id = 1
        self._active: dict[int, Reservation] = {}
        self._lock = Lock()

    def reserve(self, provider: str, estimate: int) -> tuple[Decision, Reservation | None]:
        with self._lock:
            context = Context(
                self.spent,
                self.reserved,
                self.provider_spent.get(provider, 0),
                self.provider_reserved.get(provider, 0),
                self.completed_steps,
                self.errors,
                len(self._active),
            )
            decision = evaluate(self.policy, context, provider, estimate)
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

    def release(self, reservation: Reservation, *, error: bool = False) -> None:
        with self._lock:
            self._take(reservation)
            self.completed_steps += 1
            if error:
                self.errors += 1

    def _take(self, reservation: Reservation) -> None:
        if self._active.get(reservation.id) != reservation:
            raise ValueError("Reservation already consumed or unknown")
        del self._active[reservation.id]
        self.reserved -= reservation.amount
        self.provider_reserved[reservation.provider] -= reservation.amount
