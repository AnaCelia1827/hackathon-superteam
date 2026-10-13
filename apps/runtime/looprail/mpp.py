"""Pay-kit 0.10.0 MPP session payment adapter (one channel per provider).

The policy/runtime reserves locally before a provider call. Pay-kit's remote
delivery reservation is created at commit time for the actual cost because
pay-kit 0.10.0 has no release route for unused deliveries.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

from .adapters import Channel, PaymentReservation


def _usdc(value: int, name: str) -> int:
    if type(value) is not int or value < 0 or value > 2**64 - 1:
        raise ValueError(f"{name} must be non-negative integer USDC base units")
    return value


def _http(method: str, url: str, payload: dict[str, Any] | None = None, auth: str = "", timeout: float = 30):
    data = None if payload is None else json.dumps(payload, separators=(",", ":")).encode("utf-8")
    request = Request(url, data=data, method=method)
    if data is not None:
        request.add_header("content-type", "application/json")
    if auth:
        request.add_header("authorization", auth)
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.status, {k.lower(): v for k, v in response.headers.items()}, response.read()
    except HTTPError as error:
        return error.code, {k.lower(): v for k, v in error.headers.items()}, error.read()


def _body(raw: bytes) -> dict[str, Any]:
    value = json.loads(raw or b"{}")
    if not isinstance(value, dict):
        raise ValueError("Payment server returned a non-object response")
    return value


@dataclass
class _State:
    channel: Channel
    url: str
    spent: int = 0
    reserved: int = 0
    opener: Any = None
    challenge: Any = None
    last_voucher: Any = None
    settlement: dict[str, Any] | None = None


class MppSessionAdapter:
    """Implements Person B's synchronous PaymentAdapter over MPP session routes.

    `provider_urls` maps policy provider IDs to owned provider `/session` URLs.
    `payer_keypair_path` points to a funded keypair file outside the repository.
    Real settlement is required unless `allow_wire_only=True` is explicitly set.
    """

    def __init__(
        self,
        provider_urls: dict[str, str],
        payer_keypair_path: str | Path,
        *,
        allow_wire_only: bool = False,
        settlement_rpc_url: str | None = None,
        timeout: float = 30,
    ) -> None:
        from solders.keypair import Keypair

        if not provider_urls:
            raise ValueError("At least one provider session URL is required")
        self._urls = dict(provider_urls)
        self._payer = Keypair.from_bytes(bytes(json.loads(Path(payer_keypair_path).read_text(encoding="utf-8"))))
        self._allow_wire_only = allow_wire_only
        if not allow_wire_only and not settlement_rpc_url:
            raise ValueError("settlement_rpc_url is required to verify on-chain settlement")
        self._settlement_rpc_url = settlement_rpc_url
        self._timeout = timeout
        self._lock = RLock()
        self._channels: dict[str, _State] = {}
        self._reservations: dict[str, PaymentReservation] = {}
        self._pending: dict[str, tuple[str, Any]] = {}

    def open(self, provider: str, allocation: int) -> Channel:
        _usdc(allocation, "allocation")
        with self._lock:
            if provider not in self._urls:
                raise ValueError(f"No MPP session endpoint for provider {provider}")
            existing = self._channels.get(provider)
            if existing:
                if existing.channel.allocation_usdc_base_units != allocation:
                    raise ValueError("Provider allocation changed after open")
                return existing.channel
            channel = Channel(f"mpp-pending-{uuid4().hex}", provider, allocation)
            self._channels[provider] = _State(channel, self._urls[provider])
            return channel

    def reserve(self, channel: Channel, maximum: int) -> PaymentReservation:
        _usdc(maximum, "maximum")
        with self._lock:
            state = self._state(channel)
            if state.settlement is not None:
                raise ValueError("Channel already closed")
            if state.spent + state.reserved + maximum > channel.allocation_usdc_base_units:
                raise ValueError("Provider deposit allocation exceeded")
            reservation = PaymentReservation(f"mpp-{uuid4().hex}", channel.id, maximum)
            self._reservations[reservation.id] = reservation
            state.reserved += maximum
            return reservation

    def commit(self, reservation: PaymentReservation, actual: int) -> None:
        _usdc(actual, "actual")
        with self._lock:
            state = self._reservation_state(reservation)
            if actual > reservation.amount_usdc_base_units:
                raise ValueError("Actual cost exceeds reservation")
            if actual:
                if state.opener is None:
                    self._open_remote(state)
                self._commit_remote(state, reservation, actual)
            state.spent += actual
            state.reserved -= reservation.amount_usdc_base_units
            del self._reservations[reservation.id]

    def release(self, reservation: PaymentReservation) -> None:
        with self._lock:
            state = self._reservation_state(reservation)
            if reservation.id in self._pending:
                raise RuntimeError("Remote commit is pending; retry commit before release")
            state.reserved -= reservation.amount_usdc_base_units
            del self._reservations[reservation.id]

    def close_all(self) -> list[dict[str, Any]]:
        with self._lock:
            if self._reservations or self._pending:
                raise RuntimeError("Cannot close with active or pending reservations")
            receipts = []
            for state in self._channels.values():
                if state.opener is None:
                    continue  # No deposit was ever made for this provider.
                if state.settlement is None:
                    state.settlement = self._close_remote(state)
                receipts.append(dict(state.settlement))
            return receipts

    def _state(self, channel: Channel) -> _State:
        state = self._channels.get(channel.provider)
        if state is None or state.channel != channel:
            raise ValueError("Unknown channel")
        return state

    def _reservation_state(self, reservation: PaymentReservation) -> _State:
        if self._reservations.get(reservation.id) != reservation:
            raise ValueError("Reservation already consumed or unknown")
        state = next((s for s in self._channels.values() if s.channel.id == reservation.channel_id), None)
        if state is None:
            raise ValueError("Unknown channel")
        return state

    def _open_remote(self, state: _State) -> None:
        from solders.keypair import Keypair
        from solana_pay_kit.protocols.mpp.client.payment_channels import (
            PaymentChannelOpenOptions, PaymentChannelSessionOpenOptions,
            create_payment_channel_session_opener,
        )
        from solana_pay_kit.protocols.mpp.client.session import serialize_session_credential
        from solana_pay_kit.protocols.mpp.core.headers import parse_www_authenticate
        from solana_pay_kit.protocols.mpp.intents.session import SessionRequest

        status, headers, raw = _http("GET", state.url, timeout=self._timeout)
        if status != 402:
            raise RuntimeError(f"MPP challenge failed: HTTP {status}: {_body(raw)}")
        challenge = parse_www_authenticate(headers.get("www-authenticate", ""))
        request = SessionRequest.from_dict(challenge.decode_request())
        if request.currency != "USDC" or request.method_details.network not in {"localnet", "devnet", "solana_localnet", "solana_devnet"}:
            raise ValueError("Only Solana localnet/devnet USDC sessions are supported")
        opener = create_payment_channel_session_opener(
            request, self._payer, Keypair(),
            options=PaymentChannelSessionOpenOptions(
                open=PaymentChannelOpenOptions(deposit=state.channel.allocation_usdc_base_units),
            ),
        )
        authorization = serialize_session_credential(challenge, opener.action)
        status, _, raw = _http("GET", state.url, auth=authorization, timeout=self._timeout)
        if status != 200:
            raise RuntimeError(f"MPP channel open failed: HTTP {status}: {_body(raw)}")
        state.opener = opener
        state.challenge = challenge

    def _commit_remote(self, state: _State, reservation: PaymentReservation, actual: int) -> None:
        from solana_pay_kit.protocols.mpp.intents.session import CommitReceipt

        channel_id = state.opener.session.channel_id_string
        base = state.url.rsplit("/", 1)[0]
        pending = self._pending.get(reservation.id)
        if pending is None:
            status, _, raw = _http(
                "POST", f"{base}/__402/session/deliveries",
                {"sessionId": channel_id, "amount": str(actual), "deliveryId": reservation.id},
                timeout=self._timeout,
            )
            if status != 200:
                raise RuntimeError(f"MPP reserve failed: HTTP {status}: {_body(raw)}")
            delivery_id = str(_body(raw)["deliveryId"])
            voucher = state.opener.session.prepare_increment(actual)
            self._pending[reservation.id] = (delivery_id, voucher)
        else:
            delivery_id, voucher = pending
        status, _, raw = _http(
            "POST", f"{base}/__402/session/commit",
            {"deliveryId": delivery_id, "voucher": voucher.to_dict()},
            timeout=self._timeout,
        )
        if status != 200:
            raise RuntimeError(f"MPP commit failed: HTTP {status}: {_body(raw)}")
        receipt = CommitReceipt.from_dict(_body(raw))
        expected_cumulative = state.opener.session.cumulative + actual
        if (receipt.session_id != channel_id or receipt.delivery_id != delivery_id or
                receipt.amount_base_units() != actual or receipt.cumulative_base_units() != expected_cumulative):
            raise RuntimeError("MPP commit receipt does not match the signed voucher")
        state.opener.session.record_voucher(voucher)
        state.last_voucher = voucher
        del self._pending[reservation.id]

    def _close_remote(self, state: _State) -> dict[str, Any]:
        from solana_pay_kit.protocols.mpp.client.session import serialize_session_credential
        from solana_pay_kit.protocols.mpp.core.headers import parse_receipt
        from solana_pay_kit.protocols.mpp.intents.session import ClosePayload, SessionAction

        channel_id = state.opener.session.channel_id_string
        if state.last_voucher is None or state.opener.session.cumulative != state.spent:
            raise RuntimeError("Cannot close: voucher sum does not match channel spending")
        authorization = serialize_session_credential(
            state.challenge,
            SessionAction.close_action(ClosePayload(channel_id=channel_id, voucher=state.last_voucher)),
        )
        base = state.url.rsplit("/", 1)[0]
        status, headers, raw = _http("POST", f"{base}/__402/session/close", auth=authorization, timeout=self._timeout)
        if status != 200:
            raise RuntimeError(f"MPP close failed: HTTP {status}: {_body(raw)}")
        response = _body(raw)
        reference = str(response.get("settledSignature") or response.get("reference") or "")
        if not reference and headers.get("payment-receipt"):
            reference = parse_receipt(headers["payment-receipt"]).reference
        signature = reference if reference and reference != channel_id else None
        if signature is None and not self._allow_wire_only:
            raise RuntimeError(f"Channel {channel_id} closed without an on-chain settlement signature")
        if signature is not None:
            self._verify_signature(signature)
        deposited = state.channel.allocation_usdc_base_units
        refunded = deposited - state.spent
        return {
            "provider": state.channel.provider,
            "provider_id": state.channel.provider,
            "channel_id": channel_id,
            "usdc_deposited": deposited,
            "usdc_spent": state.spent,
            "usdc_refunded": refunded,
            "spent_usdc_base_units": state.spent,
            "settlements": 1 if signature else 0,
            "signature": signature,
            "settled_signature": signature,
            "simulated": signature is None,
        }

    def _verify_signature(self, signature: str) -> None:
        from solders.signature import Signature

        Signature.from_string(signature)
        if self._settlement_rpc_url is None:
            return
        status, _, raw = _http(
            "POST", self._settlement_rpc_url,
            {"jsonrpc": "2.0", "id": 1, "method": "getSignatureStatuses",
             "params": [[signature], {"searchTransactionHistory": True}]},
            timeout=self._timeout,
        )
        if status != 200:
            raise RuntimeError(f"Settlement RPC returned HTTP {status}")
        result = _body(raw)
        values = result.get("result", {}).get("value", [])
        if (not values or values[0] is None or values[0].get("err") is not None or
                values[0].get("confirmationStatus") not in {"confirmed", "finalized"}):
            raise RuntimeError(f"Settlement signature {signature} was not confirmed on the base layer")
