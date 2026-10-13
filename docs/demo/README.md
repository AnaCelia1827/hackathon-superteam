# LoopRail demo runbook

This runbook presents the deterministic prototype. It uses virtual payments
and replayable data; it does not move USDC or submit on-chain transactions.

## Prerequisites

- Python 3.11 or newer
- PowerShell on Windows, or an equivalent shell on Linux/macOS
- No validator, wallet, LLM, or provider credentials

## Start the dashboard

From the repository root, run:

```powershell
cd apps/runtime
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m looprail.demo --output ..\dashboard\data\mock-50.json
.\.venv\Scripts\python.exe ..\dashboard\server.py
```

Open <http://127.0.0.1:8000>.

## Demo sequence

1. Click **Run simulation** to execute the deterministic mock scenario.
2. Watch the step timeline, budget events, provider latency, and policy
   outcomes arrive over SSE.
3. Use the page controls to inspect the 50 steps; the timeline displays ten
   entries per page.
4. Click **Run replay** to execute the recorded response scenario without a
   network or LLM.
5. Click **End session** during a run to abort at the next batch boundary.
6. Toggle the theme using the header button. The browser stores the selection.

The dashboard uses `source=simulation`, `onchain_transactions=0`, and
`settlements=0` to distinguish this prototype from a real payment run.

## Regenerate fixture data

From `apps/runtime`, run:

```powershell
.\.venv\Scripts\python.exe -m looprail.demo --output ..\dashboard\data\mock-50.json
```

To view the fixture without session controls:

```powershell
cd ..\dashboard
python -m http.server 8000
```

## Scope

Real authorization, reserved balances, explorer links, settlement signatures,
and paid providers require the on-chain and payment tasks described in the
[implementation plan](../../looprail_implementation_plan.md).
