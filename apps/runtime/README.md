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

The demo writes 50 step events, a market intelligence report, and metrics as JSON. Mock mode is deterministic for a fixed seed. Replay mode consumes `scenarios/replay/market-intelligence.json` without a network or LLM. `source=simulation`, `onchain_transactions=0`, and `settlements=0` identify virtual payments clearly.

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

Real ledger and payment adapters, receipt-derived authorization and settlement metrics, and paid providers depend on A6, A7, and A9. The SDK refuses unsupported real adapters until those integrations are implemented.
