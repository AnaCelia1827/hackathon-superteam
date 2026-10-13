# Person B dashboard

A local B7 dashboard powered by the deterministic B3 scenario. Its Python server streams mock or replay step events over SSE and supports aborting a running virtual session.

```powershell
cd apps/runtime
.\.venv\Scripts\python.exe -m looprail.demo --output ../dashboard/data/mock-50.json
.\.venv\Scripts\python.exe ../dashboard/server.py
```

Open `http://127.0.0.1:8000`. Click **Run simulation** or **Run replay** to watch the steps arrive. **End session** aborts at the next batch boundary and closes the virtual channels. The step timeline shows 10 entries per page. Policy reasons appear on hover over outcome badges. Running `python -m http.server 8000` still shows the saved static fixture, with session controls disabled.

Use the header button to switch between light and dark mode. The browser remembers the selected theme.

Real authorization, reserved balance, explorer links, and settlement signatures require A6/A7. The dashboard currently labels all amounts as simulated and shows zero on-chain settlements.
