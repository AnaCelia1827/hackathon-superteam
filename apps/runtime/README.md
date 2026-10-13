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

The SDK now accepts both A6 and A7 adapters in the same run. A live run requires a real `ToolRegistry`; the deterministic mock and replay providers remain simulation only. `HttpLedgerAdapter` submits ordered StepRecords to A6 and checks its confirmed count at close. The runtime reconciles the MPP receipts against the policy tracker and ledger events. `onchain_transactions` stays `null` until the A10 RPC transaction counter exists; it is not inferred from ER signatures. The A9 owned provider server now exists in `apps/providers`, but its three providers are not yet wired into a 50-step agent run. A5 still needs a base/ER validator run.

To construct the ledger client, use the same owner, authority, provider addresses, and allocations configured in the A5/A6 deployment:

```python
from looprail.http_ledger import HttpLedgerAdapter

ledger = HttpLedgerAdapter(
    "http://127.0.0.1:8787", owner="<base58 owner>", authority="<base58 authority>",
    budget_usdc_base_units=policy.budget_usdc_base_units,
    tools=["market_data", "news_search", "inference", "coordination"],
    provider_pubkeys={"market_data": "<base58>", "news": "<base58>",
                      "inference": "<base58>", "internal": "<base58>"},
    provider_allocations_usdc_base_units=policy.allocations,
)
result = rail.run(policy=policy, tools=real_tools,
                  payment_adapter=payment, ledger_adapter=ledger)
```

`real_tools` must invoke actual providers and return measured costs and latency; `payment` is an `MppSessionAdapter` configured with funded local/devnet credentials and matching provider session URLs. Session IDs are generated as 32-byte hex for A6. If the payment commit outcome is uncertain, the runtime stops before another provider call and raises `SettlementFailed` with the reservation ID. Reconcile that delivery with the provider before trying to close the channel; the runtime cannot safely guess whether an unacknowledged voucher was accepted.

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

By default, `close_all` requires the close receipt's `tx_hash` settlement signature and checks its status on the base-layer RPC. `allow_wire_only=True` is available for the A3 wire-level spike and returns `simulated=True`, `settlements=0`, `signature=None`. Pay-kit 0.10.0 has no remote release route; a failed commit may leave a pending voucher that requires reconciliation. A funded Surfpool sandbox run with two vouchers and one confirmed settlement is documented in `spikes/a3-mpp-session/README.md`. Other deployments require a provider server with RPC, operator signer, the payment-channels program, and funded USDC.

The one-off x402 `upto` fallback is still server-side only: pay-kit's high-level client does not automatically pay `upto`. The MPP adapter is the primary A7 payment path.
