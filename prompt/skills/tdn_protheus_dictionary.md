---
name: tdn_protheus_dictionary
description: Referencia do dicionario de dados Protheus (SX2, SX3, SIX, SX1, SX5, SX6, SX7, SX9) para operacoes de consulta, comparacao e equalizacao
intents: [table_info, knowledge_search, procedure_lookup, error_analysis]
keywords: [sx2, sx3, sx1, sx5, sx6, sx7, sx9, sxa, sxb, six, dicionario, dictionary, tabela, campo, field, parametro, gatilho, trigger, indice, index, equalizacao, comparacao, alias, x3_campo, x3_tipo, x3_tamanho]
priority: 80
max_tokens: 1200
specialist: "database"
---

## Dicionario de Dados Protheus — Referencia Operacional

### Tabelas SX e sua funcao

| Tabela | Funcao | Campos-chave | Operacoes |
|--------|--------|--------------|-----------|
| SX2 | Cadastro de tabelas (aliases) | X2_CHAVE, X2_NOME, X2_MODO | Consulta, comparacao entre ambientes |
| SX3 | Cadastro de campos | X3_ARQUIVO, X3_CAMPO, X3_TIPO, X3_TAMANHO, X3_DECIMAL | Equalizacao, validacao, ingestao |
| SIX | Indices das tabelas | INDICE, ORDEM, CHAVE, NICKNAME | Consulta, validacao de performance |
| SX1 | Perguntas (parametros de tela) | X1_GRUPO, X1_ORDEM, X1_PERGUNT | Comparacao entre ambientes |
| SX5 | Tabelas genericas | X5_TABELA, X5_CHAVE, X5_DESCRI | Consulta de dominios |
| SX6 | Parametros do sistema (MV_) | X6_VAR, X6_CONTEUD, X6_TIPO | Consulta, alteracao |
| SX7 | Gatilhos de campo | X7_CAMPO, X7_SEQUENC, X7_REGRA | Comparacao, equalizacao |
| SX9 | Relacionamentos entre tabelas | X9_DOM, X9_IDENT, X9_CDOM | Consulta de dependencias |

### Tipos de campo SX3 (X3_TIPO)

| Tipo | Descricao | Exemplo |
|------|-----------|---------|
| C | Caractere | A1_COD, A1_NOME |
| N | Numerico | B1_PRV1, D2_TOTAL |
| D | Data | E1_VENCTO, C5_EMISSAO |
| L | Logico | A1_MSBLQL (bloqueado) |
| M | Memo | CT2_HIST (historico longo) |

### Fluxo de equalizacao de dicionario

1. **Comparar** ambientes (origem vs destino) usando `compare_dictionary`
2. **Analisar** diferencas: campos novos, alterados, removidos
3. **Validar** consistencia antes de aplicar (tipos, tamanhos, dependencias)
4. **Equalizar** aplicando DDL no destino via `execute_equalization`

### Sufixo de empresa

Tabelas Protheus usam sufixo de empresa+filial (ex: SA1**010**, SB1**010**).
O sistema detecta automaticamente via SYS_COMPANY na conexao ativa.
Ao consultar, usar o alias base (SA1, SB1) — o sufixo e adicionado automaticamente.

### Modulos e tabelas principais

| Modulo | Cadastros | Movimentos | Rotinas |
|--------|-----------|------------|---------|
| SIGAFIN | SE1, SE2, SA6, SED | SE5, FK1 | FINA040, FINA050, FINA100 |
| SIGACOM | SA2, SC1, SC7 | SD1, SF1 | MATA120, MATA103 |
| SIGAFAT | SA1, SC5, SC6, SC9 | SD2, SF2 | MATA410, MATA460 |
| SIGAEST | SB1, SB2, NNR | SD3, SB5 | MATA240, MATA250 |
| SIGAFIS | SF3, SF4, SFT | CDT, CDA | MATXFIS, MATXFISA |
| SIGAMNT | ST4, ST9, TQ1 | TQ2, TQ3 | MNTA400, MNTA410 |
