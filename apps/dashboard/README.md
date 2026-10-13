# Dashboard da Pessoa B

Protótipo local de B7, alimentado pelo cenário determinístico de B3. É uma página estática sem dependências enquanto A6/A7 e o transporte SSE não estão disponíveis. A implementação final prevista no plano é Next.js.

```powershell
cd apps/runtime
python -m looprail.demo --output ../dashboard/data/mock-50.json
cd ../dashboard
python -m http.server 8000
```

Abra `http://localhost:8000`. O painel identifica os dados como simulação, não mostra liquidação fictícia e mantém o kill switch indisponível até existir uma sessão real com endpoint de abort.
