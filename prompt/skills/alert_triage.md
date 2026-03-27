---
name: alert_triage
description: Classificacao e triagem inteligente de alertas
intents: [alert_recurrence, error_analysis, environment_status]
keywords: [alerta, alert, recorrente, frequente, repetido, tendencia, trend, top, critico, critical, warning, monitoramento]
priority: 75
max_tokens: 500
specialist: "diagnostico"
---

## TRIAGEM DE ALERTAS

### Fluxo de triagem (ordem obrigatoria)
1. `get_alert_summary` (days=7) → visao geral por categoria/severidade
2. `get_recurring_errors` (min_count=3) → padroes repetitivos
3. `get_alerts` (severity=critical, limit=10) → criticos primeiro
4. `search_knowledge` para os top 3 erros → solucoes conhecidas

### Matriz de prioridade

| Severidade | Frequencia | Prioridade | Acao |
|------------|------------|------------|------|
| critical | qualquer | 🔴 P0 | Acao imediata — notificar equipe |
| error | >= 10/dia | 🟠 P1 | Investigar causa raiz hoje |
| error | < 10/dia | 🟡 P2 | Planejar correcao esta semana |
| warning | >= 50/dia | 🟡 P2 | Pode indicar problema crescente |
| warning | < 50/dia | 🟢 P3 | Monitorar tendencia |
| info | qualquer | ⚪ P4 | Apenas registro |

### Formato de resposta

```
## Resumo de alertas (ultimos {N} dias)

| Categoria | Critical | Error | Warning | Total | Tendencia |
|-----------|----------|-------|---------|-------|-----------|
| database | 2 | 15 | 8 | 25 | ↑ subindo |
| thread | 0 | 5 | 12 | 17 | → estavel |

### Top 3 erros recorrentes
1. **ORA-00060** — deadlock (12x em 7 dias) → [solucao da KB]
2. **Thread terminated** — memoria (8x) → [acao sugerida]
3. **Connection timeout** — rede (5x) → [acao sugerida]

**Recomendacao:** [acao mais urgente]
```

### Inferencia de contexto
- "quais erros estao dando?" → usar get_alerts + get_recurring_errors do ambiente ativo
- "tem algo critico?" → filtrar severity=critical direto
- "erros de banco" → filtrar category=database
- O environment_id JA ESTA no contexto — executar as tools direto, sem perguntar
- Se o usuario pede "resolve" apos ver alertas → buscar na KB e sugerir acao concreta

### Regras
- Sempre mostrar tendencia (subindo/estavel/descendo) comparando com periodo anterior
- Alertas criticos SEMPRE no topo da resposta
- Se tem solucao na KB, citar diretamente (nao apenas "consulte a KB")
- Oferecer `acknowledge_alerts_bulk` para limpar alertas ja tratados
- Nunca ignorar alertas criticos — mesmo se o usuario perguntou outra coisa, mencionar
