#!/usr/bin/env bash
# A9 provider server runner (inside the dev image): boots the MPP session
# provider server (on-chain Surfpool sandbox), then smoke-tests that the A7
# MppSessionAdapter can open/commit/close a channel with a real settlement.
set -uo pipefail

cd "$(dirname "$0")"

export LOOPRAIL_PROVIDERS_ONCHAIN=1
export LOOPRAIL_PROVIDERS_PORT="${LOOPRAIL_PROVIDERS_PORT:-8001}"

# Runtime deps imported by apps/runtime/looprail/__init__.py.
pip install -q --break-system-packages jsonschema rfc8785

python3 server.py > server.log 2>&1 &
SERVER_PID=$!
cleanup() { kill "$SERVER_PID" 2>/dev/null || true; }
trap cleanup EXIT

for _ in $(seq 1 30); do
  curl -s -o /dev/null http://127.0.0.1:8001/health && break || sleep 1
done

python3 test_smoke.py
