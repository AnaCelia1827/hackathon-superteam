#!/usr/bin/env python3
"""Validate every packages/contracts example against its schema (draft 2020-12).

Each `<name>.schema.json` is paired with `examples/<name>.example.json`. Exits non-zero on any
validation error so CI fails loudly.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover
    sys.exit("jsonschema is required: pip install jsonschema")


def main() -> int:
    root = Path(__file__).resolve().parents[2] / "packages" / "contracts"
    schemas = sorted(root.glob("*.schema.json"))
    if not schemas:
        sys.exit(f"no schemas found under {root}")

    failures = 0
    for schema_path in schemas:
        name = schema_path.name[: -len(".schema.json")]
        example_path = root / "examples" / f"{name}.example.json"
        if not example_path.exists():
            print(f"MISSING example for {name}: {example_path}")
            failures += 1
            continue
        schema = json.loads(schema_path.read_text())
        instance = json.loads(example_path.read_text())
        errors = sorted(Draft202012Validator(schema).iter_errors(instance), key=lambda e: list(e.path))
        if errors:
            failures += 1
            print(f"FAIL {example_path}")
            for err in errors:
                where = "/".join(str(p) for p in err.path) or "<root>"
                print(f"  {where}: {err.message}")
        else:
            print(f"ok   {example_path.relative_to(root)}")

    print(f"\n{len(schemas) - failures}/{len(schemas)} examples valid")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
