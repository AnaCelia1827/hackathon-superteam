"""A3 spike: MPP `session` server (wire-level).

Mirrors the pay-kit harness `_build_session` path: a Session method + the
reserve/commit side-channel routes. Wire-level only (`rpc=None`, accept-all tx
verifiers) because the Surfpool sandbox runs no `payment-channels` program, so
settle-at-close stays off and the close `reference` is a state-flip signature
(null on-chain). See README "Findings".
"""
from __future__ import annotations

import asyncio
import json
import sys
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
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

RPC_URL = "https://402.surfnet.dev:8899"
AMOUNT = 1000  # base units per delivery ($0.001)
DEPOSIT = AMOUNT * 60  # covers 50 deliveries + headroom
RESOURCE_PATH = "/session"


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


def build_adapter() -> tuple[Session, Any]:
    operator = Signer.demo()
    operator_pub = operator.pubkey()
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

    def _blockhash_cache() -> tuple[str, int] | None:
        blockhash, slot = _fetch_recent_state_sync()
        if blockhash is None or slot is None:
            return None
        return blockhash, slot

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
        result = asyncio.run(self.server.method.handle(auth or None, self.server.challenge))
        if not result.ok:
            self._send(result.status, result.body or {"error": "payment_required"}, result.headers)
            return
        self._send(200, {"ok": True, "paid": True, "protocol": "session"}, result.headers)

    def do_POST(self) -> None:  # noqa: N802
        raw = self.rfile.read(int(self.headers.get("content-length", "0") or "0")) or b"{}"
        if self.path == "/__402/session/deliveries":
            r = asyncio.run(self.server.routes.deliveries("POST", raw))
        elif self.path == "/__402/session/commit":
            r = asyncio.run(self.server.routes.commit("POST", raw))
        elif self.path == "/__402/session/close":
            auth = self.headers.get("authorization", "")
            result = asyncio.run(self.server.method.handle(auth or None, self.server.challenge))
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
    server.method = method
    server.routes = routes
    server.challenge = SessionChallengeOptions(amount=str(AMOUNT), description="A3 session")
    print(f"session server on 127.0.0.1:8001 (wire-level)", flush=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
