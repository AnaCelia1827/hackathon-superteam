#!/usr/bin/env bash
# Run the A1 spike inside the dev image: start base validator + local ER, then run the harness.
# Usage (inside `make shell`):  spikes/a1-er-counter/scripts/run-local.sh
#
# Requires io_uring for the Agave test validator. Under rootless podman/SELinux run the container with:
#   --security-opt seccomp=unconfined --security-opt label=disable
set -euo pipefail

cd "$(dirname "$0")/.."
LOG_DIR="$(pwd)/results/logs"
mkdir -p "$LOG_DIR"

# Ensure an Anchor wallet exists (the image ships none).
export ANCHOR_WALLET="${ANCHOR_WALLET:-$HOME/.config/solana/id.json}"
if [ ! -f "$ANCHOR_WALLET" ]; then
  mkdir -p "$(dirname "$ANCHOR_WALLET")"
  solana-keygen new --no-bip39-passphrase --silent -o "$ANCHOR_WALLET" >/dev/null
  echo "created wallet $ANCHOR_WALLET"
fi

wait_rpc() {
  local url="$1" name="$2" tries="${3:-120}"
  for _ in $(seq 1 "$tries"); do
    if curl -s -o /dev/null -X POST -H 'content-type: application/json' \
        -d '{"jsonrpc":"2.0","id":1,"method":"getHealth"}' "$url"; then
      echo "$name ready at $url"
      return 0
    fi
    sleep 1
  done
  echo "$name did not become ready at $url" >&2
  return 1
}

echo "== starting base validator (mb-test-validator) =="
mb-test-validator --reset >"$LOG_DIR/base.log" 2>&1 &
BASE_PID=$!
if ! wait_rpc "http://127.0.0.1:8899" "base"; then
  echo "---- base.log ----"; cat "$LOG_DIR/base.log"; exit 1
fi
# Fund the anchor/deploy wallet on the local base validator.
solana airdrop 100 --url http://127.0.0.1:8899 >/dev/null 2>&1 || true

echo "== starting local Ephemeral Rollup (ephemeral-validator) =="
setsid ephemeral-validator --no-tui --reset \
  --remotes "http://127.0.0.1:8899" \
  --remotes "ws://127.0.0.1:8900" \
  -l "127.0.0.1:7799" \
  --lifecycle ephemeral >"$LOG_DIR/er.log" 2>&1 < /dev/null &
ER_PID=$!
# one-shot probe for diagnostics
( sleep 3; curl -sS -m 5 -X POST -H 'content-type: application/json' \
    -d '{"jsonrpc":"2.0","id":1,"method":"getHealth"}' \
    http://127.0.0.1:7799 ) >"$LOG_DIR/er-probe.log" 2>&1 || true
if ! wait_rpc "http://127.0.0.1:7799" "er" 240; then
  echo "---- er.log ----"; cat "$LOG_DIR/er.log"
  echo "---- er-probe.log ----"; cat "$LOG_DIR/er-probe.log"
  kill "$BASE_PID" 2>/dev/null || true; exit 1
fi

cleanup() {
  echo "== stopping validators =="
  kill "$BASE_PID" "$ER_PID" 2>/dev/null || true
}
trap cleanup EXIT

echo "== running anchor test against the running stack =="
anchor test --skip-local-validator --provider.cluster localnet
