---
name: task_planning
description: Regras de planejamento para tarefas complexas que exigem multiplos passos
intents: []
keywords: [analise, investigue, diagnostique, compare, corrija, verifique, primeiro, depois, passo a passo]
priority: 85
always_load: false
max_tokens: 300
specialist: all
---

## Planejamento de Tarefas Complexas

Quando a tarefa do usuario exigir **multiplos passos** (analise + acao, comparacao + correcao, etc.):

### 1. PLANEJE antes de agir
Crie um plano curto antes de executar qualquer ferramenta:

```
PLANO:
1. [consultar X] usando [ferramenta] — objetivo
2. [analisar resultado] — decisao
3. [executar Y] usando [ferramenta] — acao final
```

### 2. EXECUTE passo a passo
- Use UMA ferramenta por vez
- Analise o resultado antes do proximo passo
- Se o resultado mudar o plano, adapte

### 3. CONSOLIDE ao final
- Resuma o que foi feito e o resultado
- Se algum passo falhou, explique por que

### Indicadores de tarefa complexa
- "analise X e sugira Y"
- "compare X e corrija Y"
- "verifique X, depois Y"
- "primeiro X, depois Y"
- "investigue" / "diagnostique"
- Multiplas entidades na mensagem (tabela + erro + ambiente)

### Indicadores de tarefa simples (NAO planejar)
- Pergunta direta (status, valor, sim/nao)
- Saudacao ou conversa casual
- Consulta unica (listar pipelines, ver alertas)
