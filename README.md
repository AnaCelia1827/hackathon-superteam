# LoopRail

Estrutura inicial do monorepo. Os contratos em `packages/contracts/` devem ser definidos em conjunto antes das integrações.

| Caminho | Responsável | Finalidade |
| --- | --- | --- |
| `apps/dashboard/` | Pessoa B | Interface e métricas da demo |
| `apps/runtime/` | Pessoa B | Loop do agente, policy e ferramentas |
| `apps/ledger-service/` | Pessoa A | API de integração com MagicBlock |
| `apps/providers/` | Pessoa A | APIs pagas usadas pela demo |
| `packages/contracts/` | Ambos | Schemas e exemplos compartilhados |
| `packages/sdk-python/` | Pessoa B | SDK público, sujeito à decisão de linguagem |
| `programs/looprail-session/` | Pessoa A | Programa Anchor |
| `scenarios/market-intelligence/` | Pessoa B | Fluxo do agente |
| `scenarios/replay/` | Pessoa B | Respostas gravadas para a demo |
| `benchmarks/` | Ambos | Runners e resultados medidos |
| `docs/adr/` | Ambos | Decisões de arquitetura |
| `docs/demo/` | Ambos | Roteiro e material da apresentação |
| `infra/` | Pessoa A | Ambiente local e serviços de apoio |

O PDF original da ideia está na raiz do repositório.

## Protótipo da Pessoa B

O runtime Python já executa uma sessão simulada de 50 passos e o dashboard local lê os eventos gerados. Veja [apps/runtime/README.md](apps/runtime/README.md) e [apps/dashboard/README.md](apps/dashboard/README.md) para os comandos. Integrações on-chain e pagamentos reais dependem das tarefas da Pessoa A.
