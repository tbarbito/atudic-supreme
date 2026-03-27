---
name: documentation_generation
description: Geracao automatica de documentacao tecnica de modulos Protheus
intents: [documentation_generation, project_analysis]
keywords: [documentar, documentacao, gerar doc, template, 19 secoes, mermaid, relatorio]
priority: 7
specialist: documentador
always_load: false
---

# Geracao de Documentacao

## Capacidade

O agente pode gerar documentacao completa de um modulo Protheus com 19 secoes padrao, incluindo diagramas Mermaid.

## Pipeline

A geracao e feita em 3 etapas:

1. **Dicionarista**: Analisa SX2/SX3/SIX/SX7 do modulo → Secoes 1-7
2. **Analista de Fontes**: Disseca codigo customizado → Secoes 15-17
3. **Documentador**: Consolida tudo → Documento 19 secoes

## Quando Usar

- Usuario pede para documentar um modulo
- Usuario quer relatorio tecnico de customizacoes
- Usuario precisa de documentacao para auditoria
- Usuario menciona "gerar doc", "documentar", "relatorio"

## Secoes do Documento

1-7: Dicionario (quantitativos, parametros, campos, indices, gatilhos, tipos, tabelas)
8-14: Processo (fluxo, integracoes, controles, comparativo, atencao, recomendacoes, glossario)
15-17: Fontes (detalhados, vinculos, grafo)
18-19: Operacoes de escrita e anexos
