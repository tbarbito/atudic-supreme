# Compreensão Inteligente — Resolver descrições vagas em entidades técnicas

**Data:** 2026-03-27
**Status:** Em design

---

## O Problema

O usuário diz: "rotina de abate, campo de desconto não salva"
O sistema precisa descobrir: tabela ZZM, campo ZZM_VLDESC, rotina MGFTAE15

Hoje o sistema chuta (LLM classify) e frequentemente erra (retorna SE1 ao invés de ZZM).

---

## Como o consultor humano resolve

1. **Identifica O QUE é** — "é uma tela" → busca nos menus
2. **Encontra ONDE está** — menu "abate" → rotina MGFTAE15
3. **Da rotina, encontra as TABELAS** — MGFTAE15 → write_tables: ZZM, ZZN
4. **Nas tabelas, encontra o CAMPO** — "desconto" nos títulos → ZZM_VLDESC

Variações:
- "Job não processa" → busca nos JOBS, não nos menus
- "Quando salvo o pedido, campo não altera" → busca PEs do MATA410
- "Gatilho não preenche" → busca gatilhos (SX7)
- "Integração não manda dado" → busca fontes WebService

---

## Arquitetura proposta (baseada em pesquisa)

### Pipeline de 5 estágios

```
USUÁRIO DIGITA
    │
    ▼
[ESTÁGIO 0: Regex] → extrai códigos técnicos (XX_CAMPO, MATA410, etc.)
    │                  Custo: ZERO
    ▼
[ESTÁGIO 1: Classificação] → extrai action + object + context
    │                         Custo: keywords=ZERO, LLM fallback=1 chamada
    │
    │  Retorna:
    │  {
    │    "action": "nao_salva",           → tipo do problema
    │    "object_type": "campo",          → o que é afetado
    │    "object_desc": "desconto",       → descrição do objeto
    │    "context_type": "tela",          → onde acontece
    │    "context_desc": "abate"          → descrição do contexto
    │  }
    │
    ▼
[ESTÁGIO 2: Busca paralela no banco] → SQL/FTS5, sem LLM
    │
    │  context_type=tela → busca MENUS WHERE nome LIKE '%abate%'
    │  context_type=job  → busca JOBS WHERE rotina LIKE '%abate%'
    │  context_type=pe   → busca padrao_pes WHERE rotina LIKE '%pedido%'
    │
    │  Da rotina encontrada → busca TABELAS (fontes.write_tables)
    │  Nas tabelas → busca CAMPOS por object_desc
    │  Cross-search: tabela×campo (nosso resolver atual)
    │
    ▼
[ESTÁGIO 3: Ranking + Slot Check]
    │
    │  Confiança > 0.8  → prossegue automaticamente
    │  Confiança 0.5-0.8 → mostra opções
    │  Confiança < 0.5  → pergunta direcionada
    │
    ▼
[ESTÁGIO 4: Investigação] → com tabela+campo corretos
```

### Estágio 1 — Classificação por keywords (sem LLM)

```python
ACTION_KEYWORDS = {
    "nao_salva":    ["nao salva", "nao grava", "perde valor", "volta valor", "nao atualiza"],
    "nao_processa": ["nao processa", "job parado", "nao roda", "schedule"],
    "nao_preenche": ["nao preenche", "fica vazio", "gatilho nao", "nao dispara"],
    "erro":         ["erro", "fatal", "travou", "bugado", "crash"],
    "nao_valida":   ["nao deixa salvar", "validacao", "campo obrigatorio"],
    "nao_integra":  ["nao integra", "ws nao", "api nao", "nao envia"],
}

OBJECT_KEYWORDS = {
    "campo":    ["campo", "valor", "dado", "informacao"],
    "job":      ["job", "agendamento", "schedule", "automatico", "batch"],
    "pe":       ["ponto de entrada", "PE", "quando salva", "ao gravar", "ao incluir"],
    "gatilho":  ["gatilho", "trigger", "preenche automatico"],
    "fonte":    ["programa", "fonte", "rotina", "prw"],
    "relatorio":["relatorio", "impressao", "crystal"],
}

CONTEXT_KEYWORDS = {
    "tela":        ["tela", "cadastro", "browse", "rotina"],
    "job":         ["job", "schedule", "appserver"],
    "integracao":  ["integracao", "webservice", "api", "ws", "edi"],
    "gravacao":    ["quando salva", "ao gravar", "ao incluir", "ao alterar"],
}
```

### Estágio 2 — Busca paralela por tipo de contexto

```python
SEARCH_STRATEGY = {
    "tela": [
        ("menus", "nome", context_desc),           # menu "abate" → MGFTAE15
        ("tabelas", "nome", context_desc),          # tabela "abate" → ZZM
    ],
    "job": [
        ("jobs", "rotina", context_desc),           # job "abate" → U_MGFTAE15
        ("schedules", "rotina", context_desc),
    ],
    "gravacao": [
        ("menus", "nome", context_desc),            # rotina padrão
        ("padrao_pes", "rotina", context_desc),     # PEs da rotina
    ],
    "integracao": [
        ("fontes", "arquivo", context_desc),        # fontes WS/INT
        ("propositos", "proposito", context_desc),  # propósito do fonte
    ],
}

# Depois de encontrar rotina → buscar tabelas via fontes.write_tables
# Nas tabelas → buscar campo por titulo LIKE object_desc
```

### Estágio 3 — Desambiguação inteligente

Quando encontra múltiplos candidatos:

```
Confiança alta (1 resultado claro):
  → "Encontrei: ZZM_VLDESC (Val.Desconto) na rotina Boletim de Abate"
  → Prossegue automaticamente

Confiança média (2-3 resultados):
  → "Encontrei possíveis campos:
     1. ZZM_VLDESC (Val.Desconto) — Boletim de Abate
     2. ZZM_DESPEC (Desc Especial) — Boletim de Abate
     Qual deles?"

Confiança baixa (muitos resultados ou nenhum):
  → "Em qual módulo/tela você está trabalhando?"
```

---

## O que já temos vs o que falta

| Componente | Temos? | Status |
|------------|:------:|--------|
| Regex para códigos técnicos | ✅ | Funcional |
| Cross-search tabela×campo | ✅ | Funcional (resolver) |
| Busca em menus | ✅ | No resolver, mas básica |
| Busca em tabelas por nome | ✅ | No resolver |
| Keywords de action/object/context | ❌ | Falta implementar |
| Busca em jobs | ❌ | Falta integrar no resolver |
| Busca em PEs por rotina | ❌ | Falta integrar |
| Busca em fontes por propósito | ❌ | Falta integrar |
| Tabela de sinônimos | ❌ | Falta criar |
| FTS5 para busca textual | ❌ | Seria melhoria de performance |
| Desambiguação com opções | ❌ | Falta implementar |
| Slot tracking | ❌ | Falta implementar |

---

## Decisão: keyword-first ou LLM-first?

| Abordagem | Custo | Acurácia | Manutenção |
|-----------|:-----:|:--------:|:----------:|
| **Keywords only** | ZERO | ~70% | Precisa manter lista |
| **LLM only** | 1 chamada/msg | ~85% | Zero manutenção |
| **Keyword + LLM fallback** | 0-1 chamada | ~95% | Lista + prompt |

**Recomendação:** Keyword-first com LLM fallback. A maioria dos casos (70-80%) é resolvida por keywords sem custo. Casos ambíguos vão pro LLM.

---

## Tabela de sinônimos (proposta)

```python
SYNONYMS = {
    # Contexto funcional → código técnico
    "pedido de venda": ["MATA410", "SC5", "SC6"],
    "pedido de compra": ["MATA120", "SC7"],
    "nota fiscal saida": ["MATA460", "SF2", "SD2"],
    "nota fiscal entrada": ["MATA103", "SF1", "SD1"],
    "cadastro cliente": ["MATA030", "SA1"],
    "cadastro fornecedor": ["MATA020", "SA2"],
    "cadastro produto": ["MATA010", "SB1"],
    "contas a receber": ["FINA040", "SE1"],
    "contas a pagar": ["FINA050", "SE2"],
    "abate": ["MGFTAE15", "ZZM", "ZZN"],
    "boletim de abate": ["MGFTAE15", "ZZM"],
    # ... expandir com cada cliente
}
```

---

## Próximos passos

1. Implementar keywords de action/object/context (sem LLM)
2. Melhorar resolver com busca por tipo de contexto
3. Adicionar tabela de sinônimos
4. Implementar desambiguação com opções
5. (Futuro) FTS5 para busca textual mais eficiente
6. (Futuro) Embeddings para sinônimos semânticos
