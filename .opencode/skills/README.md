# Vendored agent skills

These skills are vendored (copied, not symlinked) so the hackathon repo is self-contained.

| Skill | Source | Commit |
|---|---|---|
| `solana-dev/` | https://github.com/solana-foundation/solana-dev-skill | `491a19a4f69e1e80cdf0f8fa476066d726894138` |
| `magicblock/` | https://github.com/magicblock-labs/magicblock-dev-skill | `0d78851e54f7ef38b979c788d58774013e4da3d1` |
| `impeccable/` | https://github.com/pbakaus/impeccable (`.opencode/skills/impeccable`, v4.5.2) | `245ad82def45831dc56a21b683c7a1ff530b06cc` |

Refresh the Solana and MagicBlock skills with `task j2` / manually re-copy from the source repos. Do NOT use either repo's
`install.sh --agents-md` target: it writes/flattens `AGENTS.md` and would clobber ours.

Impeccable provides frontend design guidance for this project's dashboard. Its skill can be invoked on a new agent turn; project initialization and optional design hooks are separate steps.
