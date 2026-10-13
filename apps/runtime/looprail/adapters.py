"""Local adapters with the same boundary expected from Person A's services."""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Any, Protocol


@dataclass(frozen=True)
class Channel:
    id: str
    provider: str
    allocation_usdc_base_units: int


@dataclass(frozen=True)
class PaymentReservation:
    id: str
    channel_id: str
    amount_usdc_base_units: int


class PaymentAdapter(Protocol):
    def open(self, provider: str, allocation: int) -> Channel: ...
    def reserve(self, channel: Channel, maximum: int) -> PaymentReservation: ...
    def commit(self, reservation: PaymentReservation, actual: int) -> None: ...
    def release(self, reservation: PaymentReservation) -> None: ...
    def close_all(self) -> list[dict[str, Any]]: ...


class LedgerAdapter(Protocol):
    def open(self, session_id: str, policy_hash: str) -> None: ...
    def record_step(self, session_id: str, event: dict[str, Any]) -> None: ...
    def close(self, session_id: str) -> None: ...
    def abort(self, session_id: str) -> None: ...
    def events(self, session_id: str) -> list[dict[str, Any]]: ...


class MockPaymentAdapter:
    """Virtual accounting only: no escrow, vouchers, or on-chain settlements."""

    def __init__(self) -> None:
        self.channels: dict[str, Channel] = {}
        self.spent: dict[str, int] = {}
        self.reserved: dict[str, int] = {}
        self._active: dict[str, PaymentReservation] = {}
        self._next_id = 1
        self._lock = RLock()

    def open(self, provider: str, allocation: int) -> Channel:
        if type(allocation) is not int or allocation < 0:
            raise ValueError("Allocation must be non-negative USDC base units")
        with self._lock:
            if provider in self.channels:
                return self.channels[provider]
            channel = Channel(f"virtual-{provider}", provider, allocation)
            self.channels[provider] = channel
            self.spent[channel.id] = 0
            self.reserved[channel.id] = 0
            return channel

    def reserve(self, channel: Channel, maximum: int) -> PaymentReservation:
        if type(maximum) is not int or maximum < 0:
            raise ValueError("Reservation must be non-negative USDC base units")
        with self._lock:
            if self.channels.get(channel.provider) != channel:
                raise ValueError("Unknown channel")
            if self.spent[channel.id] + self.reserved[channel.id] + maximum > channel.allocation_usdc_base_units:
                raise ValueError("Virtual provider allocation exceeded")
            reservation = PaymentReservation(f"virtual-reservation-{self._next_id}", channel.id, maximum)
            self._next_id += 1
            self._active[reservation.id] = reservation
            self.reserved[channel.id] += maximum
            return reservation

    def commit(self, reservation: PaymentReservation, actual: int) -> None:
        if type(actual) is not int or actual < 0 or actual > reservation.amount_usdc_base_units:
            raise ValueError("Actual cost must fit the payment reservation")
        with self._lock:
            self._take(reservation)
            self.spent[reservation.channel_id] += actual

    def release(self, reservation: PaymentReservation) -> None:
        with self._lock:
            self._take(reservation)

    def close_all(self) -> list[dict[str, Any]]:
        with self._lock:
            if self._active:
                raise ValueError("Cannot close channels with active reservations")
            return [
                {
                    "provider": channel.provider,
                    "channel_id": channel.id,
                    "spent_usdc_base_units": self.spent[channel.id],
                    "settled_signature": None,
                    "simulated": True,
                }
                for channel in self.channels.values()
            ]

    def _take(self, reservation: PaymentReservation) -> None:
        if self._active.get(reservation.id) != reservation:
            raise ValueError("Payment reservation already consumed or unknown")
        del self._active[reservation.id]
        self.reserved[reservation.channel_id] -= reservation.amount_usdc_base_units


class MockLedger:
    """Idempotent in-memory ledger for offline runs and integration tests."""

    def __init__(self) -> None:
        self._sessions: dict[str, dict[str, Any]] = {}
        self._lock = RLock()

    def open(self, session_id: str, policy_hash: str) -> None:
        with self._lock:
            if session_id in self._sessions:
                raise ValueError("Session already exists")
            self._sessions[session_id] = {
                "policy_hash": policy_hash, "status": "open", "steps": {},
            }

    def record_step(self, session_id: str, event: dict[str, Any]) -> None:
        with self._lock:
            session = self._sessions[session_id]
            if session["status"] != "open":
                raise ValueError("Session is not open")
            index = event["step_index"]
            prior = session["steps"].get(index)
            if prior is not None and prior != event:
                raise ValueError("Conflicting event for step_index")
            session["steps"][index] = dict(event)

    def close(self, session_id: str) -> None:
        with self._lock:
            self._sessions[session_id]["status"] = "closed"

    def abort(self, session_id: str) -> None:
        with self._lock:
            self._sessions[session_id]["status"] = "aborted"

    def events(self, session_id: str) -> list[dict[str, Any]]:
        with self._lock:
            steps = self._sessions[session_id]["steps"]
            return [dict(steps[index]) for index in sorted(steps)]
