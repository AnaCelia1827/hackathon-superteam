"""Synchronous Python client for the A6 ordered ledger service."""

from __future__ import annotations

import json
import re
import time
from threading import RLock
from typing import Any, Sequence
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from .policy import Policy


class HttpLedgerAdapter:
    """Keep accepted StepRecords locally and verify A6's close barrier."""

    def __init__(
        self, base_url: str, *, owner: str, authority: str,
        budget_usdc_base_units: int, tools: Sequence[str],
        provider_pubkeys: dict[str, str], provider_allocations_usdc_base_units: dict[str, int],
        timeout: float = 60,
    ) -> None:
        if type(budget_usdc_base_units) is not int or budget_usdc_base_units < 0:
            raise ValueError("Ledger budget must be integer USDC base units")
        if set(provider_pubkeys) != set(provider_allocations_usdc_base_units):
            raise ValueError("Provider public keys and allocations must match")
        self.base_url = base_url.rstrip("/")
        self.owner = owner
        self.authority = authority
        self.budget = budget_usdc_base_units
        self.tools = list(tools)
        self.provider_pubkeys = dict(provider_pubkeys)
        self.allocations = dict(provider_allocations_usdc_base_units)
        self.timeout = timeout
        self._events: dict[str, list[dict[str, Any]]] = {}
        self._snapshots: dict[str, dict[str, Any]] = {}
        self._lock = RLock()

    def validate_policy(self, policy: Policy, planned_tools: set[str]) -> None:
        if self.budget != policy.budget_usdc_base_units or self.allocations != policy.allocations:
            raise ValueError("A6 ledger budget or allocations disagree with the policy")
        if not planned_tools.issubset(self.tools):
            raise ValueError("A6 ledger tools do not cover the agent plan")

    def _request(self, path: str, method: str = "GET", payload: dict[str, Any] | None = None) -> dict[str, Any]:
        data = None if payload is None else json.dumps(payload, separators=(",", ":")).encode()
        request = Request(self.base_url + path, data=data, method=method)
        if data is not None:
            request.add_header("content-type", "application/json")
        try:
            with urlopen(request, timeout=self.timeout) as response:
                result = json.load(response)
        except HTTPError as error:
            try:
                detail = json.load(error).get("error", error.reason)
            except (ValueError, AttributeError):
                detail = error.reason
            raise RuntimeError(f"Ledger HTTP {error.code}: {detail}") from error
        if not isinstance(result, dict):
            raise ValueError("Ledger returned a non-object response")
        return result

    def open(self, session_id: str, policy_hash: str) -> None:
        if not re.fullmatch(r"[0-9a-f]{64}", session_id):
            raise ValueError("A6 session_id must be 32-byte lowercase hex")
        providers = list(self.provider_pubkeys)
        input_data = {
            "session_id": session_id, "policy_hash": policy_hash,
            "budget_usdc_base_units": self.budget,
            "owner": self.owner, "authority": self.authority,
            "tools": self.tools, "providers": providers,
            "provider_pubkeys": [self.provider_pubkeys[name] for name in providers],
            "provider_allocations_usdc_base_units": [self.allocations[name] for name in providers],
        }
        with self._lock:
            try:
                snapshot = self._request("/sessions", "POST", input_data)
            except OSError:
                snapshot = self._request(f"/sessions/{session_id}")
            if snapshot.get("session_id") != session_id or snapshot.get("status") != "open":
                raise ValueError("Ledger did not open the requested session")
            self._events[session_id] = []
            self._snapshots[session_id] = snapshot

    def record_step(self, session_id: str, event: dict[str, Any]) -> None:
        with self._lock:
            events = self._events[session_id]
            if event["step_index"] != len(events):
                raise ValueError("Ledger step indices must be consecutive")
            try:
                response = self._request(f"/sessions/{session_id}/steps", "POST", event)
            except OSError:
                # A6 accepts an identical step_index again after a lost reply.
                response = self._request(f"/sessions/{session_id}/steps", "POST", event)
            if response.get("step_index") != event["step_index"] or response.get("state") not in {
                "queued", "sending", "confirmed",
            }:
                raise ValueError("Ledger did not accept the step")
            events.append(dict(event))

    def close(self, session_id: str) -> None:
        with self._lock:
            path = f"/sessions/{session_id}"
            try:
                snapshot = self._request(path + "/close", "POST")
            except (RuntimeError, OSError):
                snapshot = self._request(path)
                deadline = time.monotonic() + self.timeout
                while snapshot.get("status") == "closing" and time.monotonic() < deadline:
                    time.sleep(0.25)
                    snapshot = self._request(path)
                if snapshot.get("status") == "closing":
                    raise TimeoutError("Ledger close is still pending; query the session before retrying")
                if snapshot.get("status") != "closed":
                    for item in snapshot.get("steps", []):
                        if item.get("state") == "failed":
                            index = item["step_index"]
                            if type(index) is not int or index < 0 or index >= len(self._events[session_id]):
                                raise ValueError("Ledger reported an unknown failed step")
                            self._request(path + "/steps", "POST", self._events[session_id][index])
                    snapshot = self._request(path + "/close", "POST")
            count = len(self._events[session_id])
            if snapshot.get("status") != "closed" or snapshot.get("confirmed_count") != count:
                raise ValueError("Ledger close did not confirm every step")
            self._snapshots[session_id] = snapshot

    def abort(self, session_id: str) -> None:
        with self._lock:
            self._snapshots[session_id] = self._request(f"/sessions/{session_id}/abort", "POST")

    def events(self, session_id: str) -> list[dict[str, Any]]:
        with self._lock:
            snapshot = self._snapshots[session_id]
            events = self._events[session_id]
            if snapshot.get("confirmed_count") != len(events):
                raise ValueError("Ledger has unconfirmed steps")
            return [dict(event) for event in events]

    def snapshot(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            return dict(self._snapshots[session_id])
