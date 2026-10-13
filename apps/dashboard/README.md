# Person B dashboard

A local B7 dashboard powered by the deterministic B3 scenario. Its Python server streams mock or replay step events over SSE and supports aborting a running virtual session.

```powershell
cd apps/runtime
.\.venv\Scripts\python.exe -m looprail.demo --output ../dashboard/data/mock-50.json
.\.venv\Scripts\python.exe ../dashboard/server.py
```

Open `http://127.0.0.1:8000`. Click **Run simulation** or **Run replay** to watch the steps arrive. **End session** aborts at the next batch boundary and closes the virtual channels. The step timeline shows 10 entries per page. Policy reasons appear on hover over outcome badges. Running `python -m http.server 8000` still shows the saved static fixture, with session controls disabled.

Click **View on-chain run** to inspect the saved Surfpool sandbox settlement from the A7 MPP smoke run. It shows two vouchers (1,250 + 750 USDC base units), 60,000 deposited, 2,000 spent, 58,000 refunded, and the finalized transaction signature. This is a recorded on-chain run; the dashboard does not start a new paid session from this button. Its latency is shown as unavailable because the smoke run did not measure provider latency.

Use the header button to switch between light and dark mode. The browser remembers the selected theme.

The simulation and replay views remain virtual. A live agent session wired through A6/A7, continuous receipt updates, and new paid providers are still B6/A9 work.
