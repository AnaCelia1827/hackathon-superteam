#!/usr/bin/env bash
# One-shot A1 runner for the dev image: install deps, build the program, then run the spike.
# Usage (inside the container, mounted at /workspace): spikes/a1-er-counter/scripts/run-all.sh
set -euo pipefail

cd "$(dirname "$0")/.."

echo "== node/npm/anchor/solana versions =="
node --version
anchor --version
solana --version
mb-test-validator --version 2>/dev/null || true

echo "== installing JS deps =="
yarn install

echo "== building Anchor program =="
anchor build

echo "== running spike =="
exec ./scripts/run-local.sh
