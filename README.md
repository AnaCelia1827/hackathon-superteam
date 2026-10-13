# LoopRail

Initial monorepo structure. The contracts in `packages/contracts/` should be agreed on before integration work.

| Path | Owner | Purpose |
| --- | --- | --- |
| `apps/dashboard/` | Person B | Demo interface and metrics |
| `apps/runtime/` | Person B | Agent loop, policy, and tools |
| `apps/ledger-service/` | Person A | MagicBlock integration API |
| `apps/providers/` | Person A | Paid demo APIs |
| `packages/contracts/` | Both | Shared schemas and examples |
| `packages/sdk-python/` | Person B | Public Python SDK |
| `programs/looprail-session/` | Person A | Anchor program |
| `scenarios/market-intelligence/` | Person B | Agent scenario |
| `scenarios/replay/` | Person B | Recorded responses for the demo |
| `benchmarks/` | Both | Runners and measured results |
| `docs/adr/` | Both | Architecture decisions |
| `docs/demo/` | Both | Demo script and materials |
| `infra/` | Person A | Local environment and support services |

The [implementation plan](looprail_implementation_plan.md) is in English. The original ideation PDF remains in Portuguese at the repository root.

## Person B prototype

The Python runtime executes a simulated 50-step session, and the local dashboard reads the generated events. See [apps/runtime/README.md](apps/runtime/README.md) and [apps/dashboard/README.md](apps/dashboard/README.md) for commands. On-chain integration and real payments depend on Person A's tasks.
