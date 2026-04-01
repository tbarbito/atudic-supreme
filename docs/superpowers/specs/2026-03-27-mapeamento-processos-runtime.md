# Mapeamento de Processos em Runtime — Expansão Lateral

**Data:** 2026-03-27
**Status:** Para implementar

---

## Problema

O analista faz análise em **profundidade** (campo → quem grava → condição) mas não em **largura** (quais campos são parte do mesmo processo → quais tabelas estão envolvidas → qual é o fluxo).

Exemplo: C5_ZBLQRGA é parte de um processo de aprovação com 8 fontes, 4 tabelas e um workflow completo. O analista hoje lista quem grava o campo, mas não descobre o PROCESSO.

---

## O que a tool precisa fazer

### Input
Um campo ou tabela inicial (ex: C5_ZBLQRGA ou SC5)

### Passos

```
1. PONTOS DE ESCRITA do campo inicial
   → operacoes_escrita WHERE campo LIKE '%C5_ZBLQRGA%'
   → 13 pontos em 8 arquivos

2. CAMPOS COMPANHEIROS — quais campos são gravados JUNTO
   → Para cada operação que grava C5_ZBLQRGA, quais outros campos estão na lista?
   → C5_ZLIBENV (aparece em 10/13), C5_ZTAUREE (9/13), C5_ZENVAPR (4/13)
   → Campos com alta co-ocorrência = MESMO PROCESSO

3. TABELAS SATÉLITE — quais outras tabelas os mesmos fontes gravam
   → MGFFAT53 grava SC5 E SZV → SZV é satélite
   → MGFFAT10 grava SC5 E SZV → confirma
   → SZT é referenciada (tabelas_ref) pelos mesmos fontes → tabela de config

4. ESTADOS DO PROCESSO — quais valores o campo recebe
   → C5_ZBLQRGA recebe 'B' (Bloqueado) e 'L' (Liberado)
   → Isso define uma MÁQUINA DE ESTADOS

5. FLUXO ENTRE FONTES — quem faz o quê na cadeia
   → MGFFAT53: CRIA bloqueios (inclusão na SZV, B no SC5)
   → MGFFAT64: APROVA (altera SZV, pode mudar SC5)
   → MGFFAT17: LIBERA (L no SC5) ou REBLOQUEIA (B)
   → MGFFATB0: LIBERAÇÃO AUTOMÁTICA
   → Ordem: criação → análise → aprovação → liberação

6. COMPLEXIDADE — classificar o processo
   → Simples: 1-2 fontes, sem tabela satélite
   → Médio: 3-5 fontes, 1 tabela satélite
   → Complexo: 5+ fontes, 2+ tabelas satélite, máquina de estados
   → Este caso: COMPLEXO (8 fontes, 3 tabelas, 2 estados)
```

### Output esperado

```json
{
  "campo_inicial": "C5_ZBLQRGA",
  "processo": {
    "nome_sugerido": "Aprovação de Pedido de Venda",
    "complexidade": "alta",
    "total_fontes": 8,
    "total_tabelas": 4
  },
  "estados": {
    "valores": {"B": "Bloqueado", "L": "Liberado", "": "Não consultado"},
    "transicoes": [
      {"de": "", "para": "B", "fonte": "MGFFAT53", "acao": "Motor de regras bloqueia"},
      {"de": "B", "para": "L", "fonte": "MGFFAT17", "acao": "Aprovador libera"},
      {"de": "B", "para": "L", "fonte": "MGFFATB0", "acao": "Liberação automática"},
      {"de": "L", "para": "B", "fonte": "MGFFATB4", "acao": "Reprocessamento bloqueia"},
    ]
  },
  "campos_companheiros": [
    {"campo": "C5_ZLIBENV", "titulo": "Liber Envio", "co_ocorrencia": "77%"},
    {"campo": "C5_ZTAUREE", "titulo": "Reenvia Taura", "co_ocorrencia": "69%"},
    {"campo": "C5_ZENVAPR", "titulo": "Enviou Aprov", "co_ocorrencia": "31%"},
  ],
  "tabelas_satelite": [
    {"tabela": "SZV", "nome": "BLOQUEIOS", "relacao": "registros de bloqueio por regra"},
    {"tabela": "SZT", "nome": "REGRAS", "relacao": "cadastro de regras de bloqueio"},
    {"tabela": "ZHL", "nome": "HISTORICO", "relacao": "histórico de consultas externas"},
  ],
  "fontes_no_fluxo": [
    {"arquivo": "MGFFAT53.prw", "papel": "Motor de regras — cria bloqueios", "loc": 1253},
    {"arquivo": "MGFFAT64.prw", "papel": "Tela de aprovação", "loc": 3903},
    {"arquivo": "MGFFAT17.prw", "papel": "Consulta/liberação de regras", "loc": 252},
    {"arquivo": "MGFFAT10.prw", "papel": "Gestão de pedidos (MVC)", "loc": 1844},
    {"arquivo": "MGFLIBPD.prw", "papel": "Liberação de pedidos", "loc": 760},
    {"arquivo": "MGFFATB0.PRW", "papel": "Liberação automática", "loc": 96},
    {"arquivo": "MGFFATB4.PRW", "papel": "Reprocessamento", "loc": 119},
    {"arquivo": "MGFFINXL.prw", "papel": "Bloqueio financeiro", "loc": 218},
  ]
}
```

---

## Como o analista apresentaria

### Resumo Executivo
"O campo 'Bloqueio de Regra' faz parte de um processo complexo de aprovação de pedidos de venda.
O pedido passa por um motor de regras que verifica condições fiscais, financeiras e comerciais.
Se alguma regra bloqueia, o pedido fica com status 'Bloqueado' e precisa ser aprovado manualmente
na tela de aprovação. São 8 programas envolvidos e 3 tabelas auxiliares."

### Análise Técnica
- Mapa do processo com estados (B→L)
- Lista de fontes com papel de cada um
- Tabelas satélite com relação
- Campos companheiros
- Regras cadastradas (SZT)
- Consultas externas (Receita, Sintegra, CCC, Suframa)

---

## Implementação

### Nova tool: `tool_mapear_processo(tabela, campo)`

1. Buscar operacoes_escrita do campo
2. Calcular co-ocorrência de campos companheiros
3. Encontrar tabelas satélite (mesmos fontes gravam)
4. Detectar estados (valores literais gravados)
5. Classificar complexidade
6. Ordenar fontes por papel no fluxo

### Integração no pipeline
Quando a investigação encontrar campo com 5+ pontos de escrita,
automaticamente rodar o mapeamento de processo.

### Custo: ZERO (tudo SQL)
