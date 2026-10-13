# Person B runtime

Python runtime for the independent parts of B1–B5. It uses virtual payment channels and does not move USDC.

```powershell
cd apps/runtime
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m looprail.demo --record-cassette --mode replay
```

To refresh the dashboard prototype data:

```powershell
.\.venv\Scripts\python.exe -m looprail.demo --output ../dashboard/data/mock-50.json
```

The demo writes 50 step events, a market intelligence report, and metrics as JSON. Mock mode is deterministic for a fixed seed. Replay mode consumes `scenarios/replay/market-intelligence.json` without a network or LLM. `source=simulation`, `onchain_transactions=0`, and `settlements=0` identify virtual payments clearly. Simulated provider latency is present; unmeasured LoopRail overhead is `null`.

Public SDK example:

```python
from pathlib import Path
from looprail import LoopRail
from looprail.sdk import load_policy

policy = load_policy(Path("scenarios/market-intelligence/policy.mock.json"))
rail = LoopRail(network="local", budget=policy.budget_usdc_base_units,
                state="memory", payment="mock")
result = rail.run(policy=policy)
print(result.report["recommendation"], result.metrics["usdc_spent_base_units"])
```

Run the example from the repository root after installing the package. Money values use integer USDC base units. The SDK also accepts a custom agent and `ToolRegistry`, `event_sink`, and `stop_event`. `run_async` is available inside an event loop. Typed SDK errors include `BudgetExceeded`, `PolicyDenied`, `KillSwitchTripped`, and `SettlementFailed`.

The TypeScript A6 ledger service and the A7 MPP payment adapter are available separately. Running them together through the public SDK, receipt-derived metrics, and owned paid providers remain B6/A9 integration work. The SDK still rejects unsupported real-metrics runs.

## MPP payment adapter (A7)

`looprail.mpp.MppSessionAdapter` implements the existing `PaymentAdapter` boundary with one pay-kit MPP channel per provider. Install `apps/runtime[payments]`, configure a funded payer keypair file outside this repo, and pass provider `/session` URLs. `open` registers each allocation; the actual payment channel opens on the first positive commit, so providers with no spend receive no deposit. `reserve` holds the policy ceiling locally; `commit` sends the actual amount through pay-kit's deliveries/commit side channel and checks the cumulative voucher receipt. `close_all` returns deposited, spent, refunded and settlement signature per channel.

```python
from looprail.mpp import MppSessionAdapter

payment = MppSessionAdapter(
    {"market_data": "http://127.0.0.1:8001/session"},
    payer_keypair_path="/path/outside/repo/payer.json",
    settlement_rpc_url="http://127.0.0.1:8899",
)
channel = payment.open("market_data", 100_000)
hold = payment.reserve(channel, 2_000)
payment.commit(hold, 1_250)
print(payment.close_all())
```

By default, `close_all` requires the close receipt's `tx_hash` settlement signature and checks its status on the base-layer RPC. `allow_wire_only=True` is available for the A3 wire-level spike and returns `simulated=True`, `settlements=0`, `signature=None`. Pay-kit 0.10.0 has no remote release route; a failed commit must be retried before its reservation can be released. A funded Surfpool sandbox run with two vouchers and one confirmed settlement is documented in `spikes/a3-mpp-session/README.md`. Other deployments require a provider server with RPC, operator signer, the payment-channels program, and funded USDC.

The one-off x402 `upto` fallback is still server-side only: pay-kit's high-level client does not automatically pay `upto`. The MPP adapter is the primary A7 payment path.
