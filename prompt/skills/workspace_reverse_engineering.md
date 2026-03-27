---
name: workspace_reverse_engineering
description: Engenharia reversa de ambientes Protheus — parse de fontes, dicionario, vinculos e analise de impacto
intents: [source_analysis, dictionary_analysis, table_info, code_review]
keywords: [workspace, fonte, prw, tlpp, advpl, parse, engenharia reversa, codigo, funcao, ponto de entrada, PE, call graph]
priority: 8
specialist: analista_fontes
always_load: false
---

# Engenharia Reversa de Ambientes Protheus

## Capacidades

Voce tem acesso a ferramentas de engenharia reversa que permitem:

1. **Parsear codigo-fonte** — Analisar arquivos .prw/.tlpp extraindo funcoes, tabelas, PEs, call graph
2. **Analisar impacto** — Verificar o que quebra se alterar um campo ou tabela
3. **Construir grafos** — Visualizar dependencias entre modulos, fontes, tabelas e funcoes
4. **Listar vinculos** — 11 tipos de relacionamento (funcao→fonte, campo→funcao, PE→rotina, etc)

## Tools Disponiveis

### parse_source_code
Analisa um arquivo ADVPL/TLPP. Retorna: funcoes, user functions, pontos de entrada, tabelas (leitura/escrita), call graph, operacoes de escrita, linhas de codigo.

### analyze_impact
Dado uma tabela e opcionalmente um campo, retorna: fontes que leem, fontes que escrevem, operacoes de escrita detalhadas, gatilhos afetados, vinculos relacionados, e nivel de risco (BAIXO/MEDIO/ALTO).

### build_dependency_graph
Retorna o grafo de dependencias de um modulo inteiro: nodes (fontes, tabelas, funcoes, PEs) e edges (vinculos entre eles).

### list_vinculos
Lista vinculos com filtros por tipo, origem ou destino. Tipos disponiveis:
- funcao_definida_em, fonte_chama_funcao
- fonte_le_tabela, fonte_escreve_tabela
- campo_valida_funcao, gatilho_executa_funcao
- pe_afeta_rotina, campo_consulta_tabela
- tabela_pertence_modulo, modulo_integra_modulo
- job_executa_funcao, schedule_executa_funcao

## Quando Usar

- Usuario pergunta sobre codigo-fonte, funcoes, programas
- Usuario quer saber o impacto de uma alteracao
- Usuario quer entender dependencias de um modulo
- Usuario menciona PEs, call graph, RecLock, MsExecAuto
