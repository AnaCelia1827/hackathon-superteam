"""Run the 50-step deterministic scenario: python -m looprail.demo."""

import json
from pathlib import Path

from .policy import Policy
from .runtime import run_scenario


def main() -> None:
    policy_path = Path(__file__).parents[3] / "scenarios" / "market-intelligence" / "policy.mock.json"
    policy = Policy.from_dict(json.loads(policy_path.read_text(encoding="utf-8")))
    print(json.dumps(run_scenario(policy), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
