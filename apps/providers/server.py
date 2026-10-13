"""LoopRail owned providers: MPP `session` servers, one per provider, plus `/pricing`.

Each provider is an independent pay-kit MPP session server mounted under
`/<provider_id>/` (e.g. `/market_data/session` for the resource, with the
reserve/commit side-channel at `/<provider_id>/__402/session/...`). This is the
shape the A7 `MppSessionAdapter` (`apps/runtime/looprail/mpp.py`) consumes: it
derives the side-channel URL from the session URL's parent path.

Two modes, mirroring `spikes/a3-mpp-session`:
- wire-level (default): no on-chain settlement, close is a state flip.
- on-chain: `LOOPRAIL_PROVIDERS_ONCHAIN=1` — RPC-backed session server + operator
  signer against the Surfpool sandbox (which runs the payment-channels program
  and a funded USDC mint).
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import SimpleNamespace
from typing import Any

from solana_pay_kit import Signer
from solana_pay_kit.protocols.mpp._paymentchannels import PROGRAM_ID as PAYMENT_CHANNELS_PROGRAM_ID
from solana_pay_kit.protocols.mpp.core.headers import parse_receipt
from solana_pay_kit.protocols.mpp.server import (
    MemoryChannelStore,
    Session,
    SessionChallengeOptions,
    SessionConfig,
    SessionServer,
    session_routes,
)
from solana_pay_kit.protocols.mpp.server.session_method import SessionOptions, new_session
from solana_pay_kit._paycore.rpc import SolanaRpc
from solders.pubkey import Pubkey

from pricing import PRICES, pricing_payload

RPC_URL = os.environ.get("LOOPRAIL_PROVIDERS_RPC", "https://402.surfnet.dev:8899")
ONCHAIN = os.environ.get("LOOPRAIL_PROVIDERS_ONCHAIN") == "1"
PORT = int(os.environ.get("LOOPRAIL_PROVIDERS_PORT", "8001"))
SECRET_KEY = "looprail-providers-secret-key-32-bytes!"

#: Content returned after a valid session credential (one unit per provider).
CONTENT: dict[str, dict[str, Any]] = {
    "market_data": {
        "provider": "market_data",
        "symbol": "SOL",
        "price_usd": 150.42,
        "change_pct": 1.23,
        "volume_usd": 1_259_000,
    },
    "news": {
        "provider": "news",
        "headline": "Network activity increases across Solana applications",
        "sentiment": "mixed",
    },
    "inference": {
        "provider": "inference",
        "classification": "elevated_volatility",
        "risk": "moderate",
        "confidence": 0.78,
    },
}


class SessionRpc(SolanaRpc):
    """Bridge pay-kit's tuple account response to its session verifier shape."""

    async def get_account_info(self, address: str | Pubkey, commitment: str = "confirmed"):
        account = await super().get_account_info(str(address), commitment)
        if account is None:
            return SimpleNamespace(value=None)
        data, owner = account
        return SimpleNamespace(value=SimpleNamespace(data=data, owner=Pubkey.from_string(owner)))


def _fetch_recent_state_sync() -> tuple[str | None, int | None]:
    body = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": "getLatestBlockhash", "params": [{"commitment": "confirmed"}]}
    ).encode()
    req = urllib.request.Request(RPC_URL, data=body, headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        return data["result"]["value"]["blockhash"], data["result"]["context"]["slot"]
    except Exception:  # noqa: BLE001 - best-effort
        return None, None


def _blockhash_cache() -> tuple[str, int] | None:
    blockhash, slot = _fetch_recent_state_sync()
    if blockhash is None or slot is None:
        return None
    return blockhash, max(0, slot - 2)


def build_provider(provider_id: str) -> tuple[Session, Any]:
    """Build one (session method, session routes) pair for a provider."""
    amount = PRICES[provider_id].base_units
    deposit = amount * 60  # headroom for many deliveries
    operator = Signer.demo()
    operator_pub = operator.pubkey()
    realm = f"LoopRail {provider_id}"

    if ONCHAIN:
        method = new_session(SessionOptions(
            operator=operator_pub,
            recipient=operator_pub,
            amount=amount,
            currency="USDC",
            decimals=6,
            network="localnet",
            secret_key=SECRET_KEY,
            realm=realm,
            channel_program=PAYMENT_CHANNELS_PROGRAM_ID,
            suggested_deposit=deposit,
            grace_period_seconds=900,
            voucher_signer="client",
            idle_timeout_seconds=300,
            rpc=SessionRpc(RPC_URL),
            signer=operator,
        ))
        core = method.core().with_blockhash_cache(_blockhash_cache)
        return method, session_routes(core)

    config = SessionConfig(
        operator=operator_pub,
        recipient=operator_pub,
        amount=amount,
        currency="USDC",
        decimals=6,
        network="localnet",
        channel_program=str(PAYMENT_CHANNELS_PROGRAM_ID),
        suggested_deposit=deposit,
        grace_period_seconds=900,
        voucher_signer="client",
        idle_timeout_seconds=300,
    )

    async def _accept_wire_only(*_args: object) -> None:
        return None

    config.verify_open_tx = _accept_wire_only
    config.verify_top_up_tx = _accept_wire_only

    def _current_slot() -> int:
        _, slot = _fetch_recent_state_sync()
        if slot is None:
            raise ValueError("no current slot")
        return slot

    config.current_slot_provider = _current_slot

    core = SessionServer(config, MemoryChannelStore()).with_blockhash_cache(_blockhash_cache)
    method = Session(
        core=core,
        secret_key=SECRET_KEY,
        realm=realm,
        amount=amount,
        currency="USDC",
        recipient=operator_pub,
        network="localnet",
        rpc=None,
        lifecycle=None,
        signer=None,
    )
    return method, session_routes(core)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, _fmt: str, *_args: Any) -> None:
        return

    def _send(self, status: int, body: dict | list, headers: dict[str, str] | None = None) -> None:
        payload = json.dumps(body).encode()
        self.send_response(status)
        h = {"content-type": "application/json"}
        if headers:
            h.update({k.lower(): v for k, v in headers.items()})
        h["content-length"] = str(len(payload))
        for k, v in h.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(payload)

    def _run(self, coro: Any) -> Any:
        return asyncio.run_coroutine_threadsafe(coro, self.server.loop).result()

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._send(200, {"ok": True})
            return
        if self.path == "/pricing":
            self._send(200, pricing_payload())
            return
        provider, resource = self._split()
        if resource == "session" and provider in self.server.providers:
            method = self.server.providers[provider]["method"]
            challenge = self.server.providers[provider]["challenge"]
            auth = self.headers.get("authorization", "")
            result = self._run(method.handle(auth or None, challenge))
            if not result.ok:
                self._send(result.status, result.body or {"error": "payment_required"}, result.headers)
                return
            self._send(200, {"ok": True, "paid": True, "protocol": "session", **CONTENT[provider]}, result.headers)
            return
        self._send(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        provider, resource = self._split()
        if provider not in self.server.providers or resource not in ("deliveries", "commit", "close"):
            self._send(404, {"error": "not_found"})
            return
        entry = self.server.providers[provider]
        raw = self.rfile.read(int(self.headers.get("content-length", "0") or "0")) or b"{}"
        if resource == "close":
            auth = self.headers.get("authorization", "")
            result = self._run(entry["method"].handle(auth or None, entry["challenge"]))
            if not result.ok:
                self._send(result.status, result.body or {"error": "payment_required"}, result.headers)
                return
            receipt_header = result.headers.get("payment-receipt", "")
            reference = parse_receipt(receipt_header).reference if receipt_header else ""
            self._send(200, {"ok": True, "paid": True, "reference": reference}, result.headers)
            return
        routes = entry["routes"]
        if resource == "deliveries":
            r = self._run(routes.deliveries("POST", raw))
        elif resource == "commit":
            r = self._run(routes.commit("POST", raw))
        else:
            self._send(404, {"error": "not_found"})
            return
        self._send(r.status, r.body)

    def _split(self) -> tuple[str, str]:
        parts = [p for p in self.path.split("/") if p]
        if not parts:
            return "", ""
        provider = parts[0]
        # session resource: /<provider>/session
        if len(parts) == 2 and parts[1] == "session":
            return provider, "session"
        # side channel: /<provider>/__402/session/<deliveries|commit|close>
        if len(parts) == 4 and parts[1] == "__402" and parts[2] == "session":
            return provider, parts[3]
        return provider, ""


def main() -> None:
    providers: dict[str, dict[str, Any]] = {}
    for provider_id in PRICES:
        method, routes = build_provider(provider_id)
        providers[provider_id] = {
            "method": method,
            "routes": routes,
            "challenge": SessionChallengeOptions(
                amount=str(PRICES[provider_id].base_units),
                description=f"LoopRail {provider_id}",
            ),
        }

    server = HTTPServer(("127.0.0.1", PORT), Handler)
    loop = asyncio.new_event_loop()
    server.loop = loop
    threading.Thread(target=loop.run_forever, daemon=True).start()
    server.providers = providers
    mode = "on-chain sandbox" if ONCHAIN else "wire-level"
    print(f"providers server on 127.0.0.1:{PORT} ({mode}); providers={sorted(providers)}", flush=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        server.shutdown()
        loop.call_soon_threadsafe(loop.stop)


if __name__ == "__main__":
    main()
