---
name: dictionary_schema
description: Dicionario Protheus (SX2/SX3/SIX), comparacao, integridade e equalizacao
intents: [table_info]
keywords: [dicionario, dictionary, SX2, SX3, SIX, compare, comparar, equalizar, integridade, metadado, campo, indice]
priority: 70
always_load: false
max_tokens: 500
specialist: database
---

## Dicionario de Dados Protheus

### Tabelas de Metadados
| Tabela | Conteudo |
|--------|----------|
| SX2 | Cadastro de tabelas (alias, nome fisico, modo) |
| SX3 | Campos (tipo, tamanho, decimal, titulo, validacao) |
| SIX | Indices (chave, ordem, nickname) |
| SX1 | Perguntas de relatorios |
| SX5 | Tabelas genericas (codigos auxiliares) |
| SX6 | Parametros do sistema (MV_*) |
| SX7 | Gatilhos de campos |
| SX9 | Relacionamentos entre tabelas |
| SXA/SXB | Pastas e consultas padrao (F3) |
| XXA/XAM/XAL | Validacoes e aliases MVC |

### Chaves Logicas (TABLE_KEYS)
- SX3: `{X3_ARQUIVO, X3_CAMPO}` | SIX: `{INDICE, ORDEM, NICKNAME}` | SX2: `{X2_CHAVE}`

### Colunas Sempre Ignoradas
- `R_E_C_N_O_`, `R_E_C_D_E_L_`, `D_E_L_E_T_`

### Comparacao: `POST /api/dictionary/compare` (source_connection_id, target_connection_id, company_code, tables)

### Equalizacao (2 fases atomicas)
1. DDL: CREATE TABLE, ALTER TABLE ADD COLUMN, CREATE INDEX
2. DML: INSERT em SX2, SX3, SIX, TOP_FIELD

Fluxo: Preview -> Revisar SQL -> Executar com confirmation_token (SHA-256)

### Regras Protheus de DDL
- NOT NULL sempre — Protheus nao aceita NULL
- Defaults: CHAR -> espacos, NUMERIC -> 0, DATE -> ''
- `R_E_C_N_O_` gerado por driver (IDENTITY/SEQUENCE)
- `D_E_L_E_T_` sempre CHAR(1) default ' '

### Convencao de Nomes
- Sufixo: `{M0_CODIGO}0` (empresa 01 -> 010, empresa 99 -> 990)
- Filial NAO faz parte do sufixo — e campo dentro da tabela
- NUNCA assuma sufixo 010 — consulte SYS_COMPANY ou schema_cache
