"""A9 smoke test: consume the owned providers with a real MPP session settlement.

Uses the A7 `MppSessionAdapter` (`apps/runtime/looprail/mpp.py`) against the A9
provider server, funding a throwaway payer with Surfpool sandbox cheatcodes, then
opens a channel, commits two cumulative vouchers, and closes — verifying the
on-chain settlement signature. Also checks the ungated `/pricing` table.

Requires the server running with `LOOPRAIL_PROVIDERS_ONCHAIN=1`.
"""

from __future__ import annotations

import json
import sys
import tempfile
import urllib.request
from pathlib import Path

from solders.keypair import Keypair

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "runtime"))

from looprail.mpp import MppSessionAdapter  # noqa: E402

RPC = "https://402.surfnet.dev:8899"
MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
TOKEN = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
BASE = "http://127.0.0.1:8001"


def rpc(method: str, params: list) -> dict:
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    request = urllib.request.Request(RPC, payload, {"content-type": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.load(response)
    if "error" in result:
        raise RuntimeError(result["error"])
    return result["result"]


def get_json(path: str) -> dict:
    with urllib.request.urlopen(BASE + path, timeout=10) as response:
        return json.load(response)


def main() -> None:
    pricing = get_json("/pricing")
    print("== pricing ==")
    print(json.dumps(pricing, indent=2))

    with tempfile.TemporaryDirectory() as temp:
        payer = Keypair()
        address = str(payer.pubkey())
        keyfile = Path(temp) / "payer.json"
        keyfile.write_text(json.dumps(list(bytes(payer))), encoding="utf-8")
        rpc("surfnet_setAccount", [address, {"lamports": 1_000_000_000, "data": "", "executable": False, "owner": "11111111111111111111111111111111", "rentEpoch": 0}])
        rpc("surfnet_setTokenAccount", [address, MINT, {"amount": 100_000_000, "state": "initialized"}, TOKEN])

        adapter = MppSessionAdapter(
            {"market_data": f"{BASE}/market_data/session"},
            keyfile,
            settlement_rpc_url=RPC,
            timeout=90,
        )
        channel = adapter.open("market_data", 60_000)
        reservation = adapter.reserve(channel, 2_000)
        adapter.commit(reservation, 1_250)
        reservation = adapter.reserve(channel, 1_000)
        adapter.commit(reservation, 750)

        print("== settlement ==")
        print(json.dumps(adapter.close_all(), indent=2))


if __name__ == "__main__":
    main()
