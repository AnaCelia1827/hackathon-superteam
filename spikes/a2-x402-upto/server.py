"""A2 spike: x402 `upto` server (Flask + solana_pay_kit).

One usage-gated route. The gate amount is the authorized ceiling; the handler
meters the actual via `charge().charge(...)`. Zero-config against the hosted
Surfpool sandbox (`network="solana_localnet"`, demo operator auto-funded by
preflight surfnet cheatcodes).
"""
import solana_pay_kit
from solana_pay_kit import Gate, Protocol, usd
from solana_pay_kit.flask import charge, require_usage
from flask import Flask, jsonify

solana_pay_kit.configure(network="solana_localnet")

app = Flask(__name__)

# $0.05 ceiling, $0.01 metered per call.
METERED_BASE_UNITS = 10_000  # $0.01

gate = Gate.build(
    name="report_usage",
    amount=usd("0.05"),
    accept=(Protocol.X402,),
    default_pay_to=solana_pay_kit.config().effective_recipient(),
)


@app.get("/report")
@require_usage(gate)
def report():
    meter = charge()
    if meter is not None:
        meter.charge(METERED_BASE_UNITS)
    return jsonify(content="premium content")


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000)
