import json
import tempfile
import urllib.request
from pathlib import Path

from solders.keypair import Keypair

from looprail.mpp import MppSessionAdapter

RPC = "https://402.surfnet.dev:8899"
MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
TOKEN = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"


def rpc(method, params):
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    request = urllib.request.Request(RPC, payload, {"content-type": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.load(response)
    if "error" in result:
        raise RuntimeError(result["error"])
    return result["result"]


with tempfile.TemporaryDirectory() as temp:
    payer = Keypair()
    address = str(payer.pubkey())
    keyfile = Path(temp) / "payer.json"
    keyfile.write_text(json.dumps(list(bytes(payer))), encoding="utf-8")
    print("payer", address, flush=True)
    rpc("surfnet_setAccount", [address, {"lamports": 1_000_000_000, "data": "", "executable": False, "owner": "11111111111111111111111111111111", "rentEpoch": 0}])
    rpc("surfnet_setTokenAccount", [address, MINT, {"amount": 100_000_000, "state": "initialized"}, TOKEN])
    print("sandbox funded", flush=True)
    adapter = MppSessionAdapter({"market_data": "http://127.0.0.1:8001/session"}, keyfile, settlement_rpc_url=RPC, timeout=90)
    channel = adapter.open("market_data", 60_000)
    reservation = adapter.reserve(channel, 2_000)
    adapter.commit(reservation, 1_250)
    print("committed 1250", flush=True)
    reservation = adapter.reserve(channel, 1_000)
    adapter.commit(reservation, 750)
    print("committed 750", flush=True)
    print(json.dumps(adapter.close_all(), indent=2), flush=True)
