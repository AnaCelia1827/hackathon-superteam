# LoopRail dev image: pinned toolchain for Anchor + MagicBlock ER + pay-kit.
#
# Build once (slow; it compiles anchor-cli and Solana):
#   make build
# Run everything through `make dev`, `make shell`, `make test`.
FROM ubuntu:24.04

ARG RUST_VERSION=1.89.0
ARG SOLANA_VERSION=3.1.9
ARG ANCHOR_VERSION=1.0.2
ARG NODE_VERSION=24.10.0
ARG NVM_VERSION=v0.40.1
ARG ER_SDK_VERSION=0.16.2
ARG EPHEMERAL_VALIDATOR_VERSION=0.14.10
ARG PAY_KIT_VERSION=0.10.0

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8

RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential ca-certificates curl git jq make pkg-config \
      libssl-dev libudev-dev libusb-1.0-0-dev protobuf-compiler \
      python3 python3-pip python3-venv \
      && rm -rf /var/lib/apt/lists/*

# --- Rust (pinned) ---
ENV RUSTUP_HOME=/usr/local/rustup CARGO_HOME=/usr/local/cargo
RUN curl -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain "${RUST_VERSION}" --profile minimal \
      --no-modify-path \
 && "${CARGO_HOME}/bin/rustup" component add rustfmt clippy \
 && "${CARGO_HOME}/bin/rustc" --version
ENV PATH="/usr/local/cargo/bin:${PATH}"

# --- Solana / Agave CLI (pinned) ---
RUN curl -sSfL "https://release.anza.xyz/v${SOLANA_VERSION}/install" | sh
ENV PATH="/root/.local/share/solana/install/active_release/bin:${PATH}"

# --- Node (pinned via nvm) ---
ENV NVM_DIR=/usr/local/nvm
RUN mkdir -p "${NVM_DIR}" \
 && curl -fsSL "https://raw.githubusercontent.com/nvm-sh/nvm/${NVM_VERSION}/install.sh" | bash \
 && bash -c '. "${NVM_DIR}/nvm.sh" && nvm install "${NODE_VERSION}" && nvm alias default "${NODE_VERSION}"'
ENV PATH="${NVM_DIR}/versions/node/v${NODE_VERSION}/bin:${PATH}"

# --- Anchor via avm (pinned) ---
RUN cargo install --git https://github.com/coral-xyz/anchor avm --locked --force \
 && avm install "${ANCHOR_VERSION}" \
 && avm use "${ANCHOR_VERSION}"

# --- MagicBlock ER tooling + pay CLI + ER SDK ---
# `@magicblock-labs/ephemeral-validator` also provides the `mb-test-validator` binary
# (there is no standalone `@magicblock-labs/solana-test-validator` package on npm).
RUN npm install -g \
      "@magicblock-labs/ephemeral-validator@${EPHEMERAL_VALIDATOR_VERSION}" \
      "@magicblock-labs/ephemeral-rollups-sdk@${ER_SDK_VERSION}" \
      "@solana/pay"

# --- pay-kit (pinned) ---
RUN pip install --break-system-packages "solana_pay_kit==${PAY_KIT_VERSION}"

# --- yarn (classic, used by the Anchor/MagicBlock example workspaces) ---
RUN npm install -g yarn@1.22.19

# --- Bake anchor-cli's first-run toolchain setup ---
# `anchor` self-installs the Agave release it requires (observed: 3.1.10 for anchor-cli 1.0.2,
# newer than the plan's 3.1.9) plus SBF platform-tools. Doing it at build keeps `make dev`/tests fast.
RUN anchor --version

WORKDIR /workspace
