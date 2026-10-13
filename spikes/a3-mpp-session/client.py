"""A3 spike: MPP `session` client (50 metered deliveries + close).

Adapted from the pay-kit harness `python-session-client`. Opens a session
channel, then runs N reserve/commit cycles (cumulative vouchers), then closes.
Wire-level (no on-chain settle; the Surfpool sandbox has no payment-channels
program), so `settledSignature` is expected to be null — see README.
"""
from __future__ import annotations

import json
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from solders.keypair import Keypair

from solana_pay_kit.protocols.mpp.client.payment_channels import create_payment_channel_session_opener
from solana_pay_kit.protocols.mpp.client.session import serialize_session_credential
from solana_pay_kit.protocols.mpp.core.headers import parse_www_authenticate
from solana_pay_kit.protocols.mpp.intents.session import ClosePayload, SessionAction, SessionRequest

TARGET = "http://127.0.0.1:8001/session"
BASE = TARGET.rsplit("/", 1)[0]
AMOUNT = 1000  # base units per delivery
DELIVERIES = 50


def _request(method: str, url: str, body: dict | None = None, auth: str = ""):
    data = None if body is None else json.dumps(body).encode()
    req = Request(url, data=data, method=method)
    if data is not None:
        req.add_header("content-type", "application/json")
    if auth:
        req.add_header("authorization", auth)
    try:
        resp = urlopen(req, timeout=30)
        return resp.status, {k.lower(): v for k, v in resp.headers.items()}, resp.read()
    except HTTPError as err:
        return err.code, {k.lower(): v for k, v in err.headers.items()}, err.read()


def _json(raw: bytes):
    if not raw:
        return None
    try:
        return json.loads(raw.decode())
    except json.JSONDecodeError:
        return raw.decode(errors="replace")


def main() -> None:
    status, headers, raw = _request("GET", TARGET)
    if status != 402:
        print(f"expected 402 challenge, got {status}: {_json(raw)}")
        sys.exit(1)
    challenge = parse_www_authenticate(headers.get("www-authenticate", ""))
    request = SessionRequest.from_dict(challenge.decode_request())

    payer = Keypair()
    session_signer = Keypair()
    opener = create_payment_channel_session_opener(request, payer, session_signer)

    open_auth = serialize_session_credential(challenge, opener.action)
    status, _, raw = _request("GET", TARGET, auth=open_auth)
    if status != 200:
        print(f"open failed {status}: {_json(raw)}")
        sys.exit(1)

    channel_id = opener.session.channel_id_string
    cumulative = 0
    last_voucher = None
    for i in range(DELIVERIES):
        s, _, rraw = _request("POST", f"{BASE}/__402/session/deliveries", {"sessionId": channel_id, "amount": str(AMOUNT)})
        rb = _json(rraw)
        if s != 200 or not isinstance(rb, dict):
            print(f"delivery {i} failed {s}: {rb}")
            sys.exit(1)
        voucher = opener.session.prepare_increment(AMOUNT)
        s2, _, craw = _request("POST", f"{BASE}/__402/session/commit", {"deliveryId": rb["deliveryId"], "voucher": voucher.to_dict()})
        cb = _json(craw)
        if s2 != 200:
            print(f"commit {i} failed {s2}: {cb}")
            sys.exit(1)
        opener.session.record_voucher(voucher)
        cumulative += AMOUNT
        last_voucher = voucher

    close_auth = serialize_session_credential(
        challenge,
        SessionAction.close_action(ClosePayload(channel_id=channel_id, voucher=last_voucher)),
    )
    s3, close_headers, craw = _request("POST", f"{BASE}/__402/session/close", auth=close_auth)
    cb = _json(craw)
    reference = ""
    if isinstance(cb, dict):
        reference = str(cb.get("reference") or cb.get("settledSignature") or "")

    # Wire-level close: the receipt reference is the channel id (state-flip),
    # NOT a real on-chain settlement signature. A real settle is a base58
    # signature (~88 chars), not a pubkey-length channel id.
    is_real_settle = bool(reference) and reference != channel_id

    print("== A3 results ==")
    print(json.dumps({
        "deliveries": DELIVERIES,
        "amount_each_base_units": AMOUNT,
        "cumulative_base_units": cumulative,
        "cumulative_vouchers": opener.session.cumulative,
        "channel_id": channel_id,
        "close_status": s3,
        "settled_signature": reference if is_real_settle else None,
        "onchain_settlement": is_real_settle,
    }, indent=2))


if __name__ == "__main__":
    main()
