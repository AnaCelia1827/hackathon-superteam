# Contratos v1

Arquivos compartilhados entre runtime, ledger, pagamentos e dashboard. Os valores monetários são inteiros em unidades base do USDC (6 casas decimais).

- `policy.schema.json`: configuração da política.
- `step-record.schema.json`: evento de cada passo.
- `metrics.schema.json`: resumo de uma sessão.
- `payment-message.schema.json`: mensagens trocadas com o adapter de pagamentos.

Os schemas descrevem a API proposta para o MVP. A decisão de linguagem (ADR-1) e o mapeamento para pay-kit/Anchor ainda dependem dos spikes A2/A3.
