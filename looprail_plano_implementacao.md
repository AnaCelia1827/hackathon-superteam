# LoopRail: plano de implementação detalhado (2 pessoas)

**Pessoa A:** on-chain e pagamentos. **Pessoa B:** runtime, policy e demo.
Baseado na documentação de pay-kit (Solana Foundation), Payment Channels da Solana e MagicBlock (consultadas em 12/10/2026). Cada tarefa tem *o quê*, *como* e *critério de aceite*.

---

## 0. O que a documentação muda no plano original

1. **Linguagem do pay-kit.** O pay-kit consultado é **Python** (v0.10.0, requer ≥ 3.11) e traz client e server para x402 `upto` e MPP `session`. MagicBlock e Anchor são Rust/TypeScript. Não foi verificado um pacote TypeScript equivalente do pay-kit. Isso vira decisão no spike (ADR-1, tarefa J1).
2. **"1 liquidação" não é exato.** Cada canal de pagamento liquida com o seu recebedor. Com 4 providers são 4 canais e 4 liquidações (ainda muito menos que 50). O pitch deve dizer "N liquidações, uma por provider, em vez de 50 pagamentos". Alternativa: o LoopRail como gateway/recebedor único (ADR-2).
3. **x402 `upto` provavelmente custa transações on-chain por chamada.** O cliente abre um canal depositando o teto autorizado, o handler mede o uso, e o gate liquida o valor real e devolve o restante. Portanto `upto` serve para chamadas avulsas; tráfego repetido deve usar **MPP session**. O spike A2 mede isso.
4. **O MPP da Quicknode parece rodar em Tempo, não em Solana.** O CLI deles menciona pagamentos e canais Tempo. Para USDC em Solana, isso precisa ser verificado, ou usar só providers próprios.
5. **Limites do ER que desenham o `StepLog`.** Uma conta delegada sem fee payer para após 10 commits; com fee payer ela continua e passa a pagar as taxas de commit a partir do 26º. Redimensionar uma PDA delegada exige lamports para a isenção de rent e, se faltar, o payer também precisa estar delegado. Conclusão: `StepLog` de **tamanho fixo** (ring buffer) e **poucos commits** por sessão (checkpoint ocasional + final), nunca um por passo.
6. **O client do pay-kit é restritivo por padrão.** Por padrão permite stablecoins conhecidas só na mainnet, com teto de US$ 1 por pagamento; ativos desconhecidos e redes não-mainnet são negados, a menos que habilitados explicitamente. Em devnet é preciso configurar isso. Essas permissões também podem servir como camada de defesa abaixo da policy do LoopRail.
7. **O pay-kit muda rápido.** Foram 10 releases entre 29/06 e 02/10/2026. Fixar a versão exata e esperar quebras.

---

## 1. Tarefas conjuntas (início)

### J1: Contratos e ADRs (meio dia, os dois)
- **ADR-1 (linguagem).** Padrão recomendado: runtime e pagamentos em **Python** (onde o client de sessão está documentado) + **serviço de ledger em TypeScript** (fala com Anchor/MagicBlock) + dashboard em Next.js. Se os spikes A2/A3 mostrarem que o pacote TS do pay-kit cobre session e upto, vira monorepo único em TS.
- **ADR-2 (topologia de canais).** (a) Um canal por provider (padrão do MVP); (b) gateway LoopRail como recebedor único, que paga os providers. O gateway entrega "1 liquidação" e encaixa no take rate (MPP suporta taxa `fee_within`; o x402 é desabilitado automaticamente nesses gates porque facilitators x402 padrão liquidam para um único endereço). O custo é custódia e risco de crédito. Fica como extensão.
- **ADR-3 (modelo da PDA).** Ver A5.
- **Contratos em JSON Schema** (pasta `contracts/`): `Policy`, `StepRecord`, `PaymentAdapter`, `Metrics`. Unidades: valores em **unidades base do USDC (6 casas), inteiros**, nunca float.
- **Aceite:** ADRs escritos (1 página cada), schemas versionados e um exemplo válido de cada.

### J2: Ambientes e versões pinadas (meio dia)
- Versões da doc do MagicBlock: Solana 3.1.9, Rust 1.89.0, Anchor 1.0.2, Node 24.10.0; Python ≥ 3.11 para o pay-kit. Fixar tudo (lockfiles, `solana_pay_kit==0.10.0`).
- **Rede local primeiro:** o pay-kit traz `solana_localnet` (sandbox Surfpool hospedado ou local) e o MagicBlock tem ER local (`localhost:7799`). Evita travar em airdrop e instabilidade de devnet.
- Chaves em arquivo (`Signer.file`) ou env, nunca no repo. O pay-kit bloqueia o signer demo na mainnet (`DemoSignerOnMainnetError`), mas o projeto deve ficar só em devnet/local.
- **Aceite:** `make dev` sobe validator + ER local + serviços vazios; CI rodando lint e testes.

---

## 2. Pessoa A: on-chain e pagamentos

### A1: Spike do ER (counter ponta a ponta)
- **Como:** clonar o exemplo `counter/anchor` do MagicBlock. Fluxo: inicializar na base layer, delegar, incrementar no ER, `commit` ou `commit_and_undelegate`. Fixar o validador via `remaining_accounts` (na devnet, os endpoints Asia/EU/US/TEE têm chaves públicas listadas na doc).
- Medir: latência de 100 incrementos no ER (p50/p95) vs. base layer; confirmar que o estado volta à base após o commit.
- **Aceite:** tabela de latências e script reproduzível. Anotar erros de delegation encontrados.

### A2: Spike do x402 `upto`
- **Como:** servidor com `require_usage` e *operator signer* (obrigatório para upto); cliente `PayKitClient` com `ClientPermissions` habilitando a rede de teste explicitamente e um teto.
- Medir: **nº de transações on-chain por chamada**, valor autorizado vs. liquidado, refund.
- **Aceite:** tabela "tx por chamada" (valida o ponto 3 da seção 0) e decisão: `upto` só para chamadas avulsas.

### A3: Spike do MPP `session`
- **Como:** server com `new_session`, rotas de metering **reserve/commit** (`session_routes`), watchdog de idle-close e *settle-at-close* (requer signer + RPC; sem eles o fechamento é só troca de estado e a assinatura fica `null`). Client com `ActiveSession` e `SessionConsumer`.
- Rodar 50 requisições medidas numa sessão.
- **Aceite:** 50 vouchers cumulativos, `settledSignature` real on-chain, contagem de tx = abrir + fechar. Anotar o que acontece se o cliente some (idle-close).

### A4: Gate de decisão (A + B, ao fim do bloco 1)
- Atualizar os ADRs com os números dos spikes. Se A3 falhar: **plano B** = x402 upto por chamada com os custos medidos, e a narrativa muda de "1 liquidação" para "custo por chamada transparente + policy". Decidir ADR-1 (Python + sidecar vs. TS puro).

### A5: Programa Anchor `looprail_session`
- **PDA `Session`** (seeds `["session", owner, session_id]`), **tamanho fixo**:
  - `owner`, `authority` (chave do runtime que escreve no ER), `session_id`, `policy_hash [u8;32]`
  - `budget_total`, `spent`, `reserved` (u64, unidades base)
  - `step_count`, `status` (Open/Closing/Closed/Aborted), `opened_at`, `closed_at`
  - `channels[N]` (pubkey do canal + gasto por provider; N pequeno e fixo, ex.: 8)
  - `steps[K]` ring buffer (tool_id u8, provider_idx u8, cost u64, latency_ms u32, outcome u8, cache_hit bool). K ≈ 64 cobre os 50 passos da demo.
- **Instruções:** `init_session` (base), `delegate_session` (base; validador pelo primeiro `remaining_accounts`), `record_step` (ER), `checkpoint` (ER, `commit`), `close_and_undelegate` (ER), `abort` (kill switch).
- **Regras de `record_step`:** `signer == authority`; `status == Open`; `step_idx` monotônico; `spent + cost <= budget_total`; escrita no ring buffer.
- **Macros e SDK:** `#[ephemeral]` no módulo, `#[delegate]` no contexto de delegação, `#[commit]` nos de commit, e `MagicIntentBundleBuilder` (substitui os helpers deprecated `commit_accounts` e `commit_and_undelegate_accounts`). O callback de undelegation (discriminador `[196, 28, 41, 206, 48, 37, 51, 167]`) é injetado pelo `#[ephemeral]`.
- **Cuidado de design:** fee payer delegado e limite de 10 commits (seção 0, ponto 5). Planejar **no máximo 2 checkpoints + 1 commit final** por sessão.
- **Opcional (hardening):** Magic Actions para rodar uma instrução na base layer logo após o commit. Atenção ao aviso da doc: a instrução marcada com `#[action]` continua chamável diretamente por qualquer carteira, então precisa verificar o signer de escrow injetado.
- **Aceite:** testes (Anchor/Bankrun) cobrindo estouro de orçamento, `step_idx` fora de ordem, signer errado, abort, ring buffer cheio, e o ciclo delegate → record → commit → undelegate.

### A6: Serviço de ledger (TS) + cliente
- **O quê:** processo Node que expõe `POST /sessions`, `/sessions/:id/steps`, `/checkpoint`, `/close`, `/abort` e fala com a base layer e com o ER. A doc oferece o **Magic Router** (decide se a transação vai ao ER ou à base layer) via `ConnectionMagicRouter`; usá-lo, ou um RPC fixo do ER para o `record_step`.
- Fila interna: `record_step` é assíncrono ao loop do agente (o loop não espera confirmação), com confirmação garantida antes do `close`.
- **Aceite:** 50 passos gravados com sucesso; ordem e contagem batendo com o que o runtime enviou; retry idempotente (reenviar o mesmo `step_idx` não duplica).

### A7: `PaymentAdapter` real (ChannelManager)
- **Interface (alinhada com B):** `open(provider, allocation) → channel`, `reserve(channel, max) → reservation`, `commit(reservation, actual)`, `release(reservation)`, `close_all() → Settlement[]`.
- **Implementações:** `MppSessionAdapter` (padrão) e `X402UptoAdapter` (avulsas). Mapear `reserve/commit` do adapter para o side channel reserve/commit do pay-kit.
- **Alocação do orçamento:** o `ChannelManager` recebe do Policy Engine quanto depositar por provider (por isso a policy particiona o orçamento, ver B1).
- **Aceite:** soma dos vouchers por canal = valor liquidado; `usdc_refunded = depositado − gasto`; tudo conferido no explorer.

### A8: Reconciliação e falhas
- Casos a testar: provider cai no meio da sessão, idle-close dispara cedo, voucher fora de ordem ou repetido, crash do runtime com canais abertos.
- **Reaper:** processo que fecha canais órfãos (o "kill switch de verdade").
- **Aceite:** nenhum fundo preso em nenhum dos cenários injetados.

### A9: Providers próprios (pay-kit server)
- 3 endpoints: dados de mercado, notícias/contexto e proxy de inference. Cada gate com `Gate.build(...)`. Inference com streaming usa os helpers SSE medidos (`MeteredSseSession`).
- Documentar preços e a política de metering de cada um.
- **Aceite:** o agente consome os 3 com pagamento real; preços visíveis no dashboard. Se quiser um provider externo, verificar antes a rede de liquidação (seção 0, ponto 4).

### A10: Benchmark do lado on-chain
- Runners dos **dois baselines** (pagamento on-chain por chamada; x402 por chamada sem ER) e do LoopRail. Contagem de transações via assinaturas no RPC e custo real das taxas medidas.
- 20+ execuções, com mediana e dispersão.
- **Aceite:** CSV por execução (`steps, tx_count, fees, usdc_*, p50, p95`) gerado automaticamente.

---

## 3. Pessoa B: runtime, policy e demo

### B1: Spend Policy Engine
- **API pura** (sem I/O): `evaluate(ctx, request) → Decision{allow | deny | cache_hit | fallback(provider), reason}`.
- **Regras:** orçamento total; teto por provider (`max_session_spend`); preço máximo por chamada; retries com backoff; cache TTL; detecção de loop (hash de ferramenta + argumentos repetido N vezes); kill switch (taxa de erro e % do orçamento).
- **Particionamento de orçamento por canal:** necessário porque cada canal exige depósito (seção 0, ponto 2). Saída: `allocations{provider: amount}`.
- **Reserva antes de gastar:** `reserve` → `commit/release`, para nunca estourar com chamadas concorrentes.
- **`policy_hash`:** hash do JSON canônico (RFC 8785, o mesmo padrão que o pay-kit usa), gravado na PDA.
- **Aceite:** testes de propriedade com concorrência (invariante: `spent + reserved ≤ budget` sempre) e um teste por regra, incluindo o exemplo de policy do documento de ideação.

### B2: Runtime do loop e `ToolRegistry`
- **Tool:** nome, provider, modelo de preço, esquema de entrada, flag `idempotent`, timeout.
- **Ciclo por passo:** observar → decidir → `policy.evaluate` → `reserve` → chamar → `commit/release` → gravar no ledger → emitir evento.
- Chamadas paralelas para consultas de dados; sequencial para inference dependente.
- **Aceite:** o loop roda sem tocar em rede (com o mock de B3) e respeita todas as decisões da policy.

### B3: Mock determinístico e providers simulados
- Adapter e providers simulados com distribuições de latência configuráveis e falhas injetáveis.
- Cenário padrão do documento: **50 passos** = 20 dados + 15 inference + 10 scraping/API + 5 estado/coordenação.
- **Aceite:** o cenário roda em CI em segundos, com resultado reproduzível (semente fixa).

### B4: SDK público
- `new LoopRail({network, budget, state, payment})` e `rail.run({agent, tools, policy})`, como no documento de ideação. `result.metrics` **sai do ledger e dos recibos de pagamento**, nunca de valores fixos.
- Erros tipados (`BudgetExceeded`, `PolicyDenied`, `KillSwitchTripped`, `SettlementFailed`).
- **Aceite:** o exemplo de 10 linhas do README roda de ponta a ponta.

### B5: Agente de market intelligence
- Fluxo: monitorar → detectar evento → abrir sessão → dados → notícias → classificação (inference) → ferramenta/sub-agente → atualizar tese, risco e recomendação.
- **Modo replay:** gravar as respostas (cassettes) para a demo não depender de LLM nem de rede no dia.
- **Aceite:** produz um relatório coerente nos 50 passos, ao vivo e em replay.

### B6: Integração runtime ↔ ledger ↔ pagamentos (**marco principal**)
- Ligar B2 ao serviço de A6 e ao adapter de A7. Testes com **injeção de falhas** (provider lento, erro de pagamento, ledger indisponível).
- **Aceite:** sessão real com `usdc_authorized`, `usdc_spent`, `usdc_refunded` e número de liquidações conferidos, e métricas idênticas entre ledger, recibos e dashboard.

### B7: Dashboard
- Eventos via SSE: custo e latência por passo, orçamento restante (autorizado/reservado/gasto), decisões da policy com motivo, linha do tempo.
- Botão de **kill switch** que chama `abort`, e links para o explorer nas assinaturas de liquidação.
- **Aceite:** durante uma sessão real tudo atualiza em tempo real e o abort fecha os canais.

### B8: Métricas e narrativa do benchmark
- Separar **latência do provider/LLM** (que o LoopRail não controla) do **overhead do LoopRail** (policy + ledger + pagamento). O overhead pequeno é o que se consegue provar.
- `estimated_savings` calculado a partir das taxas medidas por A10, rotulado como estimativa para mainnet.
- **Aceite:** gráficos baseline vs. LoopRail gerados do CSV, sem números digitados à mão.

---

## 4. Juntos (final)

- **J3:** roteiro e gravação do vídeo (problema → loop de 50 passos → métricas → modelo de negócio).
- **J4:** README (como rodar, versões pinadas, limitações honestas) e ensaio da demo com **uma sessão gravada de backup**.

---

## 5. Dependências críticas

```
J1 → (A1, A2, A3 | B1, B3) → A4 → (A5, A6, A7 | B2, B4) → B6 → (A9, A10 | B5, B7, B8) → J3, J4
```

O caminho crítico é **A3 → A7 → B6**. Se A3 atrasar, acionar o plano B no gate A4.

## 6. Ordem de corte se o prazo apertar

Manter: (1) loop de 50 passos com liquidação real, (2) policy engine com kill switch, (3) dashboard com métricas, (4) ER como ledger. Cortar primeiro: routing inteligente, fallback entre modelos, multi-agente, gateway (ADR-2b), SDK polido.

## 7. O que não foi verificado (confirmar nos spikes)

- Existência de pacote **TypeScript** do pay-kit com session e upto equivalentes ao Python.
- Quantidade real de transações por chamada no `upto` e por sessão no MPP.
- Rede de liquidação do MPP da Quicknode e se há provider externo que liquide em Solana.
- Detalhes do side channel reserve/commit do MPP (lidos só no nível da descrição).

## 8. Fontes consultadas

- pay-kit (Solana Foundation): https://pypi.org/project/solana-pay-kit/
- Payment Channels da Solana: https://solana.com/payment-channels
- MagicBlock, quickstart de Ephemeral Rollups: https://docs.magicblock.gg/pages/ephemeral-rollups-ers/how-to-guide/quickstart
- Quicknode, pagamentos agênticos (x402/MPP): https://www.quicknode.com/docs/build-with-ai/agentic-payments
