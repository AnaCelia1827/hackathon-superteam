# Runtime da Pessoa B

Primeiro corte executável de B1, B2 e B3. Usa apenas a biblioteca padrão do Python e não movimenta USDC.

```powershell
cd apps/runtime
python -m looprail.demo
python -m unittest discover -s tests -v
```

Para atualizar os dados do protótipo do dashboard:

```powershell
python -m looprail.demo --output ../dashboard/data/mock-50.json
```

A demo escreve os eventos e as métricas em JSON na saída padrão. Os 50 passos e as latências são simulados de forma determinística; `mode=mock`, `source=simulation`, `onchain_transactions=0` e `settlements=0` evitam apresentar valores simulados como liquidação real.

Próximos encaixes: adapter de pagamentos A7, cliente do ledger A6, modo replay B5 e SSE/dashboard B7.
