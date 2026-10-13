# shellcheck shell=sh
# Local MagicBlock cluster endpoints (single source of truth).
# Source it, don't execute:  . ./scripts/local-env.sh
export PROVIDER_ENDPOINT="${PROVIDER_ENDPOINT:-http://localhost:8899}"
export WS_ENDPOINT="${WS_ENDPOINT:-ws://localhost:8900}"
export EPHEMERAL_PROVIDER_ENDPOINT="${EPHEMERAL_PROVIDER_ENDPOINT:-http://localhost:7799}"
export EPHEMERAL_WS_ENDPOINT="${EPHEMERAL_WS_ENDPOINT:-ws://localhost:7800}"
export ANCHOR_PROVIDER_URL="$PROVIDER_ENDPOINT"
export ANCHOR_WALLET="${ANCHOR_WALLET:-$HOME/.config/solana/id.json}"
export VALIDATOR="${VALIDATOR:-mAGicPQYBMvcYveUZA5F5UNNwyHvfYh5xkLS2Fr1mev}"
