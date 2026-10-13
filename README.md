# LoopRail

Monorepo for the LoopRail agent runtime, local dashboard, shared contracts, and Solana session ledger.

| Path | Owner | Purpose |
| --- | --- | --- |
| `apps/dashboard/` | Person B | Demo interface and metrics |
| `apps/runtime/` | Person B | Agent loop, policy, and tools |
| `apps/ledger/` | Person A | TypeScript ledger API and Anchor client |
| `apps/providers/` | Person A | Paid demo APIs |
| `packages/contracts/` | Both | Shared schemas and examples |
| `packages/sdk-python/` | Person B | SDK packaging notes; public API is installed from `apps/runtime` |
| `programs/looprail-session/` | Person A | Anchor program |
| `scenarios/market-intelligence/` | Person B | Agent scenario |
| `scenarios/replay/` | Person B | Recorded responses for the demo |
| `benchmarks/` | Both | Runners and measured results |
| `docs/adr/` | Both | Architecture decisions |
| `docs/demo/` | Both | Demo script and materials |
| `infra/` | Person A | Local environment and support services |

The [implementation plan](looprail_implementation_plan.md) is in English. The original ideation PDF remains in Portuguese at the repository root.

## Person B prototype

The Python runtime executes a deterministic 50-step session in mock or replay mode. To verify the demo from the repository root after installing `apps/runtime` into a Python environment:

```bash
python -m looprail.demo --mode replay --output demo.json
python -m unittest discover -s apps/runtime/tests -v
node --experimental-strip-types --test apps/ledger/test/ledger.test.ts
```

The local dashboard streams step and budget events over SSE and can abort a virtual session. See [apps/runtime/README.md](apps/runtime/README.md) and [apps/dashboard/README.md](apps/dashboard/README.md) for commands. A5's Anchor program and A6's HTTP ledger service are in the repository, but their combined base/ER path has not been verified in this Windows environment. A7's real USDC payment-channel settlement remains outstanding. Replay metrics are labeled `source=simulation`; no real settlement signature is claimed.
