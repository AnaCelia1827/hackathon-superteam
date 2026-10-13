# LoopRail

Monorepo for the LoopRail agent runtime, local dashboard, shared contracts, and planned Solana payment services.

| Path | Owner | Purpose |
| --- | --- | --- |
| `apps/dashboard/` | Person B | Demo interface and metrics |
| `apps/runtime/` | Person B | Agent loop, policy, and tools |
| `apps/ledger-service/` | Person A | MagicBlock integration API |
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

The Python runtime executes a deterministic 50-step session in mock or replay mode. The local dashboard streams step and budget events over SSE and can abort a virtual session. See [apps/runtime/README.md](apps/runtime/README.md) and [apps/dashboard/README.md](apps/dashboard/README.md) for commands. The measured benchmark comparison is described in [benchmarks/README.md](benchmarks/README.md). On-chain integration and real payments depend on Person A's tasks.
