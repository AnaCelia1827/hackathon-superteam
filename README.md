# LoopRail

LoopRail is a monorepo for an agent runtime, a local dashboard, shared contracts,
and Solana-based payment services under development.

The repository contains a runnable deterministic prototype. The on-chain ledger
and real payment integrations are documented, but are not yet the default demo
path.

## Quick start: deterministic prototype

This path does not require a validator, an LLM, or network access after the
Python dependencies have been installed. It runs a 50-step market-intelligence
session using mock or replay data.

PowerShell:

```powershell
cd apps/runtime
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m looprail.demo --output ..\dashboard\data\mock-50.json
.\.venv\Scripts\python.exe ..\dashboard\server.py
```

Open <http://127.0.0.1:8000>, then choose **Run simulation** or **Run replay**.
The complete demo procedure is in [docs/demo/README.md](docs/demo/README.md).
The static dashboard is published at
[GitHub Pages](https://anacelia1827.github.io/hackathon-superteam/).

## Requirements

- Python 3.11 or newer for the runtime; local infrastructure is pinned to
  Python 3.12.
- Node.js 24.10.0 or newer for the TypeScript services.
- Docker and Docker Compose for the local Solana/MagicBlock stack.
- Rust and Anchor when building or testing the on-chain program.

## Repository map

| Path | Owner | Purpose |
| --- | --- | --- |
| [`apps/dashboard/`](apps/dashboard/) | Person B | Local demo interface and metrics |
| [`apps/runtime/`](apps/runtime/) | Person B | Agent loop, policy, tools, and Python SDK |
| [`apps/ledger/`](apps/ledger/) | Person A | TypeScript MagicBlock integration API |
| [`apps/providers/`](apps/providers/) | Person A | Paid demo provider adapters |
| [`packages/contracts/`](packages/contracts/) | Both | Shared schemas and examples |
| [`packages/sdk-python/`](packages/sdk-python/) | Person B | Public SDK packaging notes |
| [`programs/looprail-session/`](programs/looprail-session/) | Person A | Anchor program |
| [`scenarios/market-intelligence/`](scenarios/market-intelligence/) | Person B | Agent policy and scenario |
| [`scenarios/replay/`](scenarios/replay/) | Person B | Recorded responses for replay |
| [`benchmarks/`](benchmarks/) | Both | Benchmark runners and reports |
| [`docs/adr/`](docs/adr/) | Both | Architecture decision records |
| [`docs/demo/`](docs/demo/) | Both | Demo runbook |
| [`infra/`](infra/) | Person A | Local validators and support services |

The [implementation plan](looprail_implementation_plan.md) is in English.
The original ideation document is the Portuguese
[looprail_ideacao.pdf](looprail_ideacao.pdf).

## Running individual components

- [Runtime and Python SDK](apps/runtime/README.md)
- [Dashboard](apps/dashboard/README.md)
- [Ledger service](apps/ledger/README.md)
- [Local infrastructure](infra/README.md)
- [Benchmarks](benchmarks/README.md)
- [Architecture decisions](docs/adr/README.md)

The Python SDK is currently distributed from `apps/runtime` as
`looprail-runtime`; see [packages/sdk-python/README.md](packages/sdk-python/README.md).

## Tests and CI

The same commands used by GitHub Actions are available through:

```bash
make ci
```

This runs contract validation, ledger service tests, Python syntax validation,
and JSON validation.

The root `package.json` contains the Anchor/TypeScript flows:

```bash
yarn build
yarn test
yarn test:bankrun
yarn test:er
```

The `test:er` flow requires the local environment described in
[infra/README.md](infra/README.md). The deterministic runtime tests do not
require the validator.

## Project status and limitations

### Available now

- Deterministic 50-step runtime in mock and replay modes.
- Local dashboard with SSE step streaming and virtual-session abort.
- Shared contract schemas and examples.
- Ledger service queue behavior tested with a chain-port fake.
- An MPP payment adapter with a confirmed USDC settlement on the Surfpool sandbox.
- A dashboard view of that recorded settlement and an English demo video.
- ADRs documenting the selected language, channel topology, and PDA model.

### In progress or not yet connected

- The A5 base-to-ER path has not been verified in this Windows environment.
- The SDK now connects injected A6 and A7 adapters, reconciles receipts, and
  stops on uncertain payment commits. The default deterministic agent still
  uses virtual payments; no 50-step paid run has been verified.
- The dashboard labels mock/replay amounts as simulated and shows a separate
  recorded sandbox settlement; it does not start new paid runs.
- The ledger queue is in memory; restarting the service loses queued events.
- Benchmark outputs must come from measured runs; mock transaction counts and
  fees are intentionally not substituted.

See the [implementation plan](looprail_implementation_plan.md) and the
[architecture decisions](docs/adr/README.md) for authoritative constraints.
