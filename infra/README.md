# infra

Local, reproducible stack for Person A (on-chain + payments). **Localnet only** — never point at mainnet.

## Quick start

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

Local ER validator identity: `mAGicPQYBMvcYveUZA5F5UNNwyHvfYh5xkLS2Fr1mev`
Delegation Program: `DELeGGvXpWV2fqJUhqcF5ZSYMS4JTLjteaAMARRSaeSh`

## Pins (authoritative)

Rust `1.89.0` · Solana/Agave `3.1.9` · Anchor `1.0.2` · Node `24.10.0` · Python `3.12` ·
`solana_pay_kit==0.10.0` · `@magicblock-labs/ephemeral-rollups-sdk@0.16.2`.

See `looprail_plano_implementacao.md` §J2. `@magicblock-labs/ephemeral-validator` is pinned to
`latest` because MagicBlock does not version-tag it per our toolchain; freeze the resolved version in
the Dockerfile once A1 locks it.

## Notes

- `mb-test-validator` clones MagicBlock program accounts from devnet on first run, so the first
  `make dev` needs network access.
- Devnet alternatives (not used by `make dev`): base `https://rpc.magicblock.app/devnet`,
  router `https://devnet-router.magicblock.app`. ER fqdn is discovered via router
  `getDelegationStatus`.
- `make ci` (`lint` + `test`) is what `.github/workflows/ci.yml` runs.
