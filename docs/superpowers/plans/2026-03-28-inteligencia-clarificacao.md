# Inteligência de Clarificação — Plano de Implementação

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development or superpowers:executing-plans.

**Goal:** Quando uma pergunta é genérica e tem múltiplas possibilidades no ambiente do cliente, o Analista deve perguntar antes de investigar — listando opções reais baseadas nos dados do banco.

**Architecture:** Função `avaliar_ambiguidade()` que conta possibilidades e decide se responde direto ou pergunta. Sem LLM na decisão — puro SQL/dados. O LLM só formata a resposta final.

**Spec:** Baseado na sessão 28/03 — casos de teste: liberação pedido de venda (13 campos bloqueio), rateio (múltiplas rotinas).

---

## Conceito

### Regra de Decisão

```
Pergunta → classificar tabela/campo/keywords
  → buscar possibilidades no banco
  → contar "blocos lógicos" distintos
  → DECISÃO:
    1 bloco  → investiga direto (caso abate)
    2-3      → investiga os principais, responde com todos
    4+       → pergunta antes, lista opções com dados reais
```

### Exemplos

**1 bloco — responde direto:**
- "desconto não salva no abate" → ZZM_VLDESC, só 1 condição (bEmite)
- "sintegra não libera pedido" → só 1 processo de sintegra
- "não consigo emitir NF do abate" → processo específico

**2-3 blocos — investiga e responde:**
- "erro na nota de entrada" → pode ser SF1 ou SD1, mas são do mesmo processo
- "campo não grava no cadastro de produto" → SB1/SB5, investiga ambos

**4+ blocos — pergunta antes:**
- "não libera o pedido" → 13 campos de bloqueio em SC5 → lista opções
- "rateio não funciona" → rateio existe em SC1, SC7, SD1, SE1, CT2 → lista opções
- "aprovação travada" → workflow em SC5, SC1, SC7, ZGX → lista opções

### O que é um "bloco lógico"

Não é 1 campo = 1 bloco. Campos que fazem parte do mesmo processo são 1 bloco:
- C5_ZBLQRGA + MGFFAT10 + MGFFAT53 + MGFFAT17 = "Motor de regras comerciais" (1 bloco)
- C5_BLQ + C5_LIBEROK = "Liberação padrão Protheus" (1 bloco)
- C5_ZBLQTAU + C5_ZSTATUS = "Integração Taura" (1 bloco)
- C5_ZLIBPES = "Pesagem" (1 bloco)
- C5_APROV = "Aprovação/Workflow" (1 bloco)

Agrupamento por: fontes que gravam o campo (se 2 campos são gravados pelo mesmo fonte → mesmo bloco).

---

## Task 1: `avaliar_ambiguidade()` — detectar e agrupar possibilidades

**Files:**
- Create: `backend/services/clarificacao.py`

Função que recebe `(tabelas, keywords, campos_encontrados)` e retorna:

```python
{
    "ambiguo": True/False,
    "total_blocos": 5,
    "blocos": [
        {
            "nome": "Motor de regras comerciais",
            "campos": ["C5_ZBLQRGA"],
            "fontes_principais": ["MGFFAT10.prw", "MGFFAT53.prw", "MGFFAT17.prw"],
            "descricao": "Bloqueio por regras de negócio customizadas — 13 operações de escrita",
            "keywords_match": ["regra", "bloqueio", "motor"],
        },
        {
            "nome": "Liberação padrão Protheus",
            "campos": ["C5_BLQ", "C5_LIBEROK", "C5_TIPLIB"],
            "fontes_principais": ["MATA410A.PRW"],
            "descricao": "Bloqueio padrão por crédito, estoque, duplicidade",
        },
        ...
    ],
    "sugestao_pergunta": "No ambiente Marfrig existem 5 tipos de bloqueio no pedido de venda...",
}
```

### Lógica interna:

1. Para cada tabela identificada:
   - Buscar campos que matcham os keywords (bloq, lib, status, aprov, rateio, etc.)
   - Para cada campo, buscar em `operacoes_escrita` quem grava
   - Agrupar campos que compartilham fontes de escrita → mesmo bloco
2. Enriquecer cada bloco:
   - Resumo do(s) fonte(s) principal(is) (propositos)
   - Contagem de operações
   - Processos vinculados (processos_detectados)
3. Contar blocos → decidir ambiguidade
4. Montar sugestão de pergunta com opções reais

### Keywords por tipo de problema:

```python
KEYWORDS_BLOQUEIO = ["bloq", "lib", "trav", "aprov", "status", "pend"]
KEYWORDS_RATEIO = ["rate", "rateio", "cc", "centro_custo", "distr"]
KEYWORDS_INTEGRACAO = ["integr", "taura", "tms", "sfa", "argo", "commerce"]
KEYWORDS_FISCAL = ["sintr", "sped", "reinf", "nfe", "fiscal", "icms"]
```

---

## Task 2: `montar_opcoes_clarificacao()` — formatar opções pro LLM

**Files:**
- Modify: `backend/services/clarificacao.py`

Transforma os blocos em texto formatado que vai no prompt do LLM:

```
O ambiente possui 5 processos distintos de bloqueio no pedido de venda (SC5):

1. **Motor de regras comerciais** — Campo C5_ZBLQRGA
   Fontes: MGFFAT10.prw (motor), MGFFAT17.prw (liberação), MGFFAT53.prw (regras)
   13 operações de escrita, controlado por parâmetro MGF_FAT16F

2. **Liberação padrão Protheus** — Campos C5_BLQ, C5_LIBEROK
   Bloqueio por crédito, estoque, duplicidade

3. **Integração Taura** — Campos C5_ZBLQTAU, C5_ZSTATUS
   Fontes: MGFFAT13.prw, MGFTAS01.prw

4. **Pesagem** — Campo C5_ZLIBPES
   Liberação após conferência de peso

5. **Workflow de aprovação** — Campo C5_APROV
   Grupo de aprovação configurado

Qual desses cenários se aplica ao seu caso?
```

O LLM recebe isso como contexto e gera a pergunta de clarificação naturalmente.

---

## Task 3: Integrar no `chat_conversa` — decidir quando perguntar

**Files:**
- Modify: `backend/routers/analista.py`

No Phase 1 (investigação), após classificar e resolver contexto:

```python
# Após resolver tabelas e campos...
from backend.services.clarificacao import avaliar_ambiguidade

amb = avaliar_ambiguidade(tabelas, keywords_da_pergunta, campos_msg)

if amb["ambiguo"]:
    # Em vez de investigar tudo, manda as opções pro LLM
    tool_results_parts.append(amb["sugestao_pergunta"])
    # Flag para o prompt: "PERGUNTE ao usuário qual cenário se aplica"
else:
    # Investiga direto (caso normal)
    # ... investigar_problema, tools, etc.
```

### Interação multi-turno:

1. User: "não libera o pedido" → Analista lista 5 opções
2. User: "acho que é o motor de regras" → Analista agora sabe: C5_ZBLQRGA → investigar_campo_escrita → resposta cirúrgica

A segunda mensagem é classificada com contexto do histórico (já sabe que é SC5) + a clarificação do usuário.

---

## Task 4: Enriquecer `tool_resolver_contexto` com detecção de ambiguidade

**Files:**
- Modify: `backend/services/analista_tools.py` (tool_resolver_contexto)

Adicionar no resolver:
- Quando encontra múltiplos campos de bloqueio/status → sinalizar ambiguidade
- Quando keywords são genéricos ("rateio", "aprovação") → buscar em quais tabelas/módulos existe
- Retornar flag `ambiguidade_detectada` + blocos pra decisão upstream

---

## Task 5: Testes

### Caso 1: "não libera o pedido" (genérico → pergunta)
- Esperado: Lista 5+ opções de bloqueio na SC5

### Caso 2: "não libera o pedido sintegra" (específico → responde)
- Esperado: Investiga direto o bloqueio sintegra

### Caso 3: "rateio não funciona" (genérico → pergunta)
- Esperado: Lista rateio em SC1, SC7, SD1, SE1, CT2

### Caso 4: "rateio do pedido de compra não calcula" (específico → responde)
- Esperado: Investiga direto SC7 + campos de rateio

### Caso 5: "desconto não salva no abate" (específico → responde)
- Esperado: Investiga direto ZZM_VLDESC (1 bloco, 0 ambiguidade)

---

## Dependências

- `avaliar_ambiguidade` usa: `operacoes_escrita`, `vinculos`, `campos`, `propositos`, `processos_detectados`
- Não precisa de LLM na decisão — tudo SQL/regex
- LLM só entra pra formatar a pergunta de clarificação e a resposta final

## Estimativa de complexidade

- Task 1 (avaliar_ambiguidade): Médio — agrupamento por fontes, contagem de blocos
- Task 2 (formatar opções): Simples — template com dados dos blocos
- Task 3 (integrar chat_conversa): Simples — if/else na fase de investigação
- Task 4 (enriquecer resolver): Médio — detectar keywords genéricos
- Task 5 (testes): Simples — 5 cenários manuais
