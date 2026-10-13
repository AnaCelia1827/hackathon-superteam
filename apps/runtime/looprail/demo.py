"""Run the 50-step deterministic scenario: python -m looprail.demo."""

import json
import argparse
from pathlib import Path

from .policy import Policy
from .runtime import run_scenario


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the deterministic LoopRail demo")
    parser.add_argument("--output", type=Path, help="Write JSON to this path instead of stdout")
    args = parser.parse_args()
    policy_path = Path(__file__).parents[3] / "scenarios" / "market-intelligence" / "policy.mock.json"
    policy = Policy.from_dict(json.loads(policy_path.read_text(encoding="utf-8")))
    result = json.dumps(run_scenario(policy), indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result + "\n", encoding="utf-8")
    else:
        print(result)


if __name__ == "__main__":
    main()
