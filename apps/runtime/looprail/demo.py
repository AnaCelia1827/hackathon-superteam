"""Run or record the deterministic market-intelligence scenario."""

import json
import argparse
from pathlib import Path

from .agent import MarketIntelligenceAgent
from .mocks import write_cassette
from .sdk import LoopRail, load_policy


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the deterministic LoopRail demo")
    parser.add_argument("--output", type=Path, help="Write JSON to this path instead of stdout")
    parser.add_argument("--mode", choices=("mock", "replay"), default="mock")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--record-cassette", action="store_true", help="Refresh the replay cassette")
    args = parser.parse_args()
    root = Path(__file__).parents[3]
    policy = load_policy(root / "scenarios" / "market-intelligence" / "policy.mock.json")
    cassette_path = root / "scenarios" / "replay" / "market-intelligence.json"
    agent = MarketIntelligenceAgent()
    if args.record_cassette:
        write_cassette(cassette_path, agent.plan(), seed=args.seed)
    rail = LoopRail(network="local", budget=policy.budget_usdc_base_units)
    result = rail.run(
        agent=agent,
        policy=policy,
        seed=args.seed,
        replay_path=cassette_path if args.mode == "replay" else None,
    )
    serialized = json.dumps(result.to_dict(), indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    else:
        print(serialized)


if __name__ == "__main__":
    main()
