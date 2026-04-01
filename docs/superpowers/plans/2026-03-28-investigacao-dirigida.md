# Investigação Dirigida — Plano de Implementação

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development or superpowers:executing-plans.

**Goal:** Criar uma função `investigar_campo_escrita(tabela, campo)` que rastreia a cadeia completa de escrita de um campo específico — quem grava, sob qual condição, de onde vem a condição, quais parâmetros controlam — para uso no Peça ao Analista.

**Architecture:** Função pura SQL/regex (sem LLM) que navega operacoes_escrita → condições → fonte_chunks (regex variáveis) → parametros. O Analista chama essa função durante a fase de investigação quando detecta que a pergunta é sobre "campo não salva" ou "campo não atualiza".

**Benchmark:** `docs/superpowers/specs/2026-03-28-benchmark-investigacao-dirigida.md`

---

## Task 1: Criar `investigar_campo_escrita()` em `backend/services/analista_tools.py`

**Files:**
- Modify: `backend/services/analista_tools.py`

Função que recebe `(tabela, campo)` e retorna:

```python
{
    "tabela": "ZZM",
    "campo": "ZZM_VLDESC",
    "campo_info": {"tipo": "N", "tamanho": 14, "titulo": "Vl.Desconto"},
    "operacoes": [
        {
            "arquivo": "MGFTAE15.PRW",
            "funcao": "TAE15_GRV",
            "tipo": "reclock_alt",
            "condicao": "bEmite",
            "grava_campo": True,  # este campo está na lista de campos gravados
            "campos_gravados": ["ZZM_VLDESC", "ZZM_VLACR", ...],
            "origens": {"ZZM_VLDESC": "tela:M->ZZM_VLDESC"},
            "variaveis_condicao": [
                {
                    "variavel": "bEmite",
                    "definicao": "bEmite := !(cFilAnt $ SuperGetMV('MGF_TAE17'))",
                    "parametros_envolvidos": [
                        {"nome": "MGF_TAE17", "valor": "010005;010064;010068", "descricao": "Filiais onde fornecedor emite NF"}
                    ],
                    "funcoes_chamadas": ["MGFFIS36"]
                }
            ]
        },
        {
            "arquivo": "MGFTAE15.PRW",
            "funcao": "TAE15_GRV",
            "tipo": "reclock_alt",
            "condicao": "NOT (bEmite)",
            "grava_campo": False,  # este bloco NAO grava ZZM_VLDESC
            "campos_gravados": ["ZZM_OBS", "ZZM_VENCE"]
        }
    ],
    "diagnostico": {
        "grava_sempre": False,
        "condicional": True,
        "condicoes_que_bloqueiam": ["bEmite = .F. (filiais 010005, 010064, 010068)"],
        "parametros_chave": ["MGF_TAE17", "MGF_TAE15A", "MGF_TAE15R"]
    }
}
```

Passos internos da função:
1. Buscar campo info em `campos` (tipo, tamanho, titulo)
2. Buscar em `operacoes_escrita WHERE tabela=X AND campos LIKE '%CAMPO%'`
3. Para cada operação, verificar se o campo específico está na lista de campos
4. Para cada condição, extrair variáveis (regex: identificar nomes de variáveis AdvPL)
5. Para cada variável, buscar nos `fonte_chunks` como é definida (regex: `variavel := `, `variavel =`)
6. Para cada GetMV/SuperGetMV encontrado, buscar valor em `parametros`
7. Para cada U_ encontrado, buscar info do fonte chamado
8. Montar diagnóstico: grava sempre? condicional? quais condições bloqueiam?

---

## Task 2: Criar `investigar_problema()` — wrapper inteligente

**Files:**
- Modify: `backend/services/analista_tools.py`

Função que recebe `(tabela, campo, acao)` onde acao pode ser "nao_salva", "nao_atualiza", "erro", etc.

1. Chama `investigar_campo_escrita(tabela, campo)`
2. Se acao é "nao_salva" → foca nas condições que BLOQUEIAM a gravação
3. Adiciona contexto do graph (via `traverse_graph`) para ecossistema
4. Se encontra processos vinculados que não existem → registra via `tool_registrar_processo`
5. Retorna contexto pronto para o LLM

---

## Task 3: Integrar no chat_conversa do Analista

**Files:**
- Modify: `backend/routers/analista.py` (chat_conversa, ~linha 934)

Na fase de investigação (Phase 1 do event_generator):

1. Após a classificação (tabelas, campos extraídos), detectar se é uma pergunta de "campo não salva/atualiza"
   - Keywords: "não salva", "não grava", "não atualiza", "não persiste", "perde valor"
2. Se sim: chamar `investigar_problema(tabela, campo, "nao_salva")`
3. O resultado substitui (ou complementa) o contexto das tools genéricas
4. O graph genérico continua rodando para ecossistema geral

---

## Task 4: Benchmark A/B/C/D no mesmo caso de teste

**Files:**
- Create: `tests/test_benchmark_investigacao.py`

Script que roda as 4 abordagens na mesma pergunta e salva:
- Tokens de contexto
- Tempo de execução
- Resposta completa do LLM
- Score manual (checklist de itens que a resposta deveria conter)

Checklist para a pergunta do abate:
- [ ] Identificou ZZM_VLDESC como o campo
- [ ] Listou quem grava (TAE15_GRV, MGFTAE14)
- [ ] Explicou condição bEmite
- [ ] Trouxe parâmetro MGF_TAE17 com valor (filiais)
- [ ] Explicou que nas filiais da lista o desconto não é gravado
- [ ] Mencionou exceção Rondônia ou MGFFIS36
- [ ] Resposta em duas camadas (executivo + técnico)
