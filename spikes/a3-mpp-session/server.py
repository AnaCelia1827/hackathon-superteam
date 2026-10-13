"""A3 MPP session server for wire-only or funded Surfpool sandbox smoke runs."""
from __future__ import annotations

import asyncio
import json
import os
import sys
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

RPC_URL = "https://402.surfnet.dev:8899"
AMOUNT = 1000  # base units per delivery ($0.001)
DEPOSIT = AMOUNT * 60  # covers 50 deliveries + headroom
RESOURCE_PATH = "/session"


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
    # Hosted Surfpool's blockhash context can be ahead of getSlot.
    return blockhash, max(0, slot - 2)


def build_adapter() -> tuple[Session, Any]:
    operator = Signer.demo()
    operator_pub = operator.pubkey()
    if os.environ.get("LOOPRAIL_MPP_ONCHAIN") == "1":
        method = new_session(SessionOptions(
            operator=operator_pub,
            recipient=operator_pub,
            amount=AMOUNT,
            currency="USDC",
            decimals=6,
            network="localnet",
            secret_key="a3-mpp-session-secret-key-32-bytes-padding!",
            realm="A3 spike",
            channel_program=PAYMENT_CHANNELS_PROGRAM_ID,
            suggested_deposit=DEPOSIT,
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
        amount=AMOUNT,
        currency="USDC",
        decimals=6,
        network="localnet",
        channel_program=str(PAYMENT_CHANNELS_PROGRAM_ID),
        suggested_deposit=DEPOSIT,
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
        secret_key="a3-mpp-session-secret-key-32-bytes-padding!",
        realm="A3 spike",
        amount=AMOUNT,
        currency="USDC",
        recipient=operator_pub,
        network="localnet",
        rpc=None,
        lifecycle=None,
        signer=None,
    )
    routes = session_routes(core)
    return method, routes


class Handler(BaseHTTPRequestHandler):
    def log_message(self, _fmt: str, *_args: Any) -> None:
        return

    def _send(self, status: int, body: dict, headers: dict[str, str] | None = None) -> None:
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

    def do_GET(self) -> None:  # noqa: N802
        if self.path != RESOURCE_PATH:
            self._send(404, {"error": "not_found"})
            return
        auth = self.headers.get("authorization", "")
        result = asyncio.run_coroutine_threadsafe(
            self.server.method.handle(auth or None, self.server.challenge), self.server.loop
        ).result()
        if not result.ok:
            self._send(result.status, result.body or {"error": "payment_required"}, result.headers)
            return
        self._send(200, {"ok": True, "paid": True, "protocol": "session"}, result.headers)

    def do_POST(self) -> None:  # noqa: N802
        raw = self.rfile.read(int(self.headers.get("content-length", "0") or "0")) or b"{}"
        if self.path == "/__402/session/deliveries":
            r = asyncio.run_coroutine_threadsafe(self.server.routes.deliveries("POST", raw), self.server.loop).result()
        elif self.path == "/__402/session/commit":
            r = asyncio.run_coroutine_threadsafe(self.server.routes.commit("POST", raw), self.server.loop).result()
        elif self.path == "/__402/session/close":
            auth = self.headers.get("authorization", "")
            result = asyncio.run_coroutine_threadsafe(
                self.server.method.handle(auth or None, self.server.challenge), self.server.loop
            ).result()
            if not result.ok:
                self._send(result.status, result.body or {"error": "payment_required"}, result.headers)
                return
            receipt_header = result.headers.get("payment-receipt", "")
            reference = parse_receipt(receipt_header).reference if receipt_header else ""
            self._send(200, {"ok": True, "paid": True, "reference": reference}, result.headers)
            return
        else:
            self._send(404, {"error": "not_found"})
            return
        self._send(r.status, r.body)


def main() -> None:
    method, routes = build_adapter()
    server = HTTPServer(("127.0.0.1", 8001), Handler)
    loop = asyncio.new_event_loop()
    server.loop = loop
    threading.Thread(target=loop.run_forever, daemon=True).start()
    server.method = method
    server.routes = routes
    server.challenge = SessionChallengeOptions(amount=str(AMOUNT), description="A3 session")
    mode = "on-chain sandbox" if os.environ.get("LOOPRAIL_MPP_ONCHAIN") == "1" else "wire-level"
    print(f"session server on 127.0.0.1:8001 ({mode})", flush=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        server.shutdown()
        loop.call_soon_threadsafe(loop.stop)


if __name__ == "__main__":
    main()
