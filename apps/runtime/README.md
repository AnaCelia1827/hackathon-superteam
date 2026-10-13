# Person B runtime

First executable slice of B1, B2, and B3. It uses only the Python standard library and does not move USDC.

```powershell
cd apps/runtime
python -m looprail.demo
python -m unittest discover -s tests -v
```

To refresh the dashboard prototype data:

```powershell
python -m looprail.demo --output ../dashboard/data/mock-50.json
```

The demo writes events and metrics as JSON to standard output. The 50 steps and their latencies are simulated deterministically. `mode=mock`, `source=simulation`, `onchain_transactions=0`, and `settlements=0` prevent simulated values from appearing as real settlements.

Next integrations: A7 payment adapter, A6 ledger client, B5 replay mode, and B7 SSE dashboard.
