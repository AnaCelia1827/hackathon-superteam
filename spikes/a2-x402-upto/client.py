"""A2 spike: x402 `upto` client (solana_pay_kit.PayKitClient).

Demonstrates that the high-level client does NOT auto-pay an `upto` challenge:
it returns the raw 402 (it only wires the `exact` payment path). See README
"Findings" for the ADR-1 implication.
"""
import asyncio

from solana_pay_kit import Signer
from solana_pay_kit._paycore.rpc import SolanaRpc
from solana_pay_kit.client import PayKitClient

SERVER = "http://127.0.0.1:8000/report"
RPC = "https://402.surfnet.dev:8899"
CALLS = 3


async def main() -> None:
    signer = Signer.demo()
    payer = signer.pubkey()
    rpc = SolanaRpc(RPC)

    http = (
        PayKitClient.builder()
        .signer(signer)
        .rpc(rpc)
        .network("localnet")
        .permissions(False)
        .build()
    )

    results = []
    async with http:
        for i in range(CALLS):
            resp = await http.get(SERVER)
            results.append(
                {
                    "call": i,
                    "status": resp.status_code,
                    "payment_response": resp.headers.get("payment-response"),
                    "settlement": resp.headers.get("x-payment-settlement-signature"),
                    "challenge": (resp.text[:120] if resp.status_code == 402 else ""),
                }
            )

    print("== A2 results ==")
    for r in results:
        print(r)
    print(f"payer={payer}")
    print("note: 402 means the high-level client did not auto-pay (upto client not wired).")
    await rpc.aclose()


if __name__ == "__main__":
    asyncio.run(main())
