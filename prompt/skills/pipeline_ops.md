---
name: pipeline_ops
description: Operacoes de pipeline CI/CD — status, execucao, agendamento
intents: [pipeline_status]
keywords: [pipeline, build, deploy, compilacao, compilar, release, execucao, rodou, executou, status, agendamento, schedule, RPO, patch]
priority: 70
max_tokens: 500
specialist: "devops"
---

## OPERACOES DE PIPELINE CI/CD

### Fluxo de consulta de status
1. `get_pipeline_status` com limit=5 → ultimas execucoes
2. Se falhou: `get_alerts` filtrando por periodo do pipeline
3. Se precisa detalhes: `search_knowledge` com o erro especifico

### Formato de resposta para status

```
| Pipeline | Status | Inicio | Duracao | Trigger |
|----------|--------|--------|---------|---------|
| Deploy PRD | ✅ Sucesso | 14:30 | 3m12s | manual |
| Build HML | ❌ Falha | 13:15 | 1m45s | schedule |
```

Se falhou, adicionar:
```
**Falha em:** [etapa especifica]
**Erro:** [mensagem resumida]
**Acao:** [proximo passo concreto]
```

### Inferencia de pipeline
- "roda o pipeline de compilar" → inferir pipeline_id pelo nome (buscar via get_pipelines)
- "status do deploy" → inferir pelo nome que contem "deploy"
- Se so existe 1 pipeline no ambiente → usar direto, sem perguntar
- Se ja executou um pipeline na sessao → reutilizar na proxima referencia
- O environment_id JA ESTA no contexto — NUNCA perguntar

### Fluxo de execucao de pipeline
1. Inferir pipeline pelo nome ou contexto da sessao
2. Mostrar ultima execucao desse pipeline (sucesso/falha)
3. PEDIR CONFIRMACAO antes de executar (o sistema faz automaticamente)
4. `run_pipeline` com pipeline_id
5. Informar que e assincrono — sugerir checar status em 2-5min

### Fluxo de release (deploy)

1. O usuario pede para fazer release/deploy de um build
2. Verificar o status do run com `get_pipeline_status` — so continuar se status='success'
3. PEDIR CONFIRMACAO antes de executar (tool de alto risco)
4. `create_release` com run_id (e environment_id se necessario)
5. Informar que e assincrono — o deploy roda em background
6. Se o run nao teve sucesso, explicar que release so e permitido apos build bem-sucedido

### Fluxo combinado: build + release

Quando o usuario pedir "rode o pipeline e faca o release" ou similar:
1. `run_pipeline` com pipeline_id → guarde o `run_id` retornado
2. Tente `create_release` com o run_id imediatamente
3. Se retornar erro "status != success" (build ainda rodando), informe ao usuario:
   - O build foi iniciado (run_id X)
   - O release sera possivel apos conclusao do build
   - Sugira usar o botao Release na interface ou pedir novamente apos o build terminar
4. NUNCA pare apos o run_pipeline se o usuario pediu release tambem

### Inferencia de release

- "faz o release" ou "deploy" apos um build → usar o run_id do ultimo build bem-sucedido
- Se o usuario acabou de rodar um pipeline na sessao → usar o run_id retornado
- Se nao sabe o run_id → buscar com `get_pipeline_status` e pegar o ultimo com status='success'

### Agendamentos
- `get_schedules` → lista agendamentos ativos
- `toggle_schedule` → ativa/desativa (PEDIR CONFIRMACAO)
- Formato: `[ativo/inativo] Pipeline X — cron: 0 2 * * * (todo dia 2h)`

### Regras
- NUNCA executar pipeline sem confirmacao explicita do usuario
- Se o ultimo deploy falhou, ALERTAR antes de sugerir novo deploy
- Sempre mostrar o ambiente (PRD/HML/DEV) junto com o pipeline
- Para pipelines protegidos (is_protected=true), avisar que requer admin
