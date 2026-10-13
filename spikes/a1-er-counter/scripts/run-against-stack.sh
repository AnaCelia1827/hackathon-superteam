#!/usr/bin/env bash
# Run the A1 harness against an already-running stack (base :8899 + ER :7799),
# e.g. brought up by `make dev`. Use this instead of run-local.sh when the stack is managed.
set -euo pipefail

cd "$(dirname "$0")/.."

export ANCHOR_WALLET="${ANCHOR_WALLET:-$HOME/.config/solana/id.json}"
if [ ! -f "$ANCHOR_WALLET" ]; then
  mkdir -p "$(dirname "$ANCHOR_WALLET")"
  solana-keygen new --no-bip39-passphrase --silent -o "$ANCHOR_WALLET" >/dev/null
fi

# Fund the deploy wallet on the running base validator.
solana airdrop 100 --url "${BASE_RPC_URL:-http://127.0.0.1:8899}" >/dev/null 2>&1 || true

yarn install
anchor build
anchor test --skip-local-validator --provider.cluster localnet
