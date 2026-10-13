# infra

Local, reproducible stack for Person A (on-chain + payments). **Localnet only** — never point at mainnet.

## Quick start

Requires the `docker` group (or root): `sudo usermod -aG docker "$USER"` then re-login.

```bash
make build   # build the pinned dev image (slow: compiles anchor-cli + Solana)
make dev     # start base validator (mb-test-validator) + local MagicBlock ER
make shell   # shell inside the image with the repo mounted at /workspace
make down    # stop
```

`make dev` uses **host networking** so endpoints match the MagicBlock local-development guide:

| Service | RPC | WS |
| --- | --- | --- |
| Solana base layer (`mb-test-validator`) | `http://127.0.0.1:8899` | `ws://127.0.0.1:8900` |
| Ephemeral Rollup (`ephemeral-validator`) | `http://127.0.0.1:7799` | `ws://127.0.0.1:7800` |

`base` has a healthcheck and `er` waits for `service_healthy` (+5s) before starting, because the ER
must not connect before the base's WS/geyser is ready. Both services also set
`security_opt: [seccomp=unconfined, label=disable]` — Agave's `solana-test-validator` needs
`io_uring`, which the default seccomp profile (and SELinux labels under rootless) block.

Local ER validator identity: `mAGicPQYBMvcYveUZA5F5UNNwyHvfYh5xkLS2Fr1mev`
Delegation Program: `DELeGGvXpWV2fqJUhqcF5ZSYMS4JTLjteaAMARRSaeSh`

## Pins (authoritative)

Rust `1.89.0` · Anchor `1.0.2` · Node `24.10.0` · Python `3.12` · `solana_pay_kit==0.10.0` ·
`@magicblock-labs/ephemeral-rollups-sdk@0.16.2` · `@magicblock-labs/ephemeral-validator@0.14.10`.

**Agave/Solana version is not fixed by us**: `anchor-cli 1.0.2` self-provisions the Agave release it
needs (observed `3.0.0` when an `Anchor.toml` is present, `3.1.10` otherwise), which is newer than
the plan's 3.1.9. See mini-task findings in `docs/adr/`.

`@magicblock-labs/ephemeral-validator` provides the `mb-test-validator` and `mb-stack` binaries
(there is no standalone `solana-test-validator` npm package).

## Notes

- `mb-test-validator` clones MagicBlock program accounts from devnet on first run, so the first
  `make dev` needs network access.
- Devnet alternatives (not used by `make dev`): base `https://rpc.magicblock.app/devnet`,
  router `https://devnet-router.magicblock.app`. ER fqdn is discovered via router
  `getDelegationStatus`.
- `make ci` (`lint` + `test`) is what `.github/workflows/ci.yml` runs.
