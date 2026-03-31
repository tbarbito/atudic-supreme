---
name: operations_database
description: Procedures operacionais para banco de dados, queries Protheus e fluxos de dicionario
intents: [table_info, dictionary_analysis]
keywords: [banco, database, query, sql, parametro, MV_, conexao, connection, schema, SYS_COMPANY]
priority: 80
max_tokens: 600
specialist: "database"
---

## PROCEDURES DE BANCO — Protheus

### REGRA #1: Use TEMPLATES em vez de SQL bruto
O sistema tem templates que montam o SQL com sufixo correto automaticamente.
SEMPRE prefira template. O sufixo e empresa ja estao no contexto pre-computado.

### Templates disponiveis para query_database
| Template | Uso | Exemplo de chamada |
|----------|-----|-------------------|
| `parametro` | Valor de MV_* | `{"template": "parametro", "param_name": "MV_ESTNEG"}` |
| `parametros_modulo` | Listar MV_* por prefixo | `{"template": "parametros_modulo", "prefix": "MV_COM"}` |
| `campos_tabela` | Campos de uma tabela | `{"template": "campos_tabela", "table_alias": "SA1"}` |
| `indices_tabela` | Indices de uma tabela | `{"template": "indices_tabela", "table_alias": "SA1"}` |
| `tabelas` | Listar todas as tabelas | `{"template": "tabelas"}` |
| `tabela_info` | Info de 1 tabela | `{"template": "tabela_info", "table_alias": "SA1"}` |
| `gatilhos_campo` | Triggers de um campo | `{"template": "gatilhos_campo", "field_name": "A1_COD"}` |
| `tabelas_genericas` | Tabela generica SX5 | `{"template": "tabelas_genericas", "tab_key": "01"}` |
| `empresas` | Listar empresas | `{"template": "empresas"}` |
| `dados_tabela` | Dados de tabela de negocio | `{"template": "dados_tabela", "table_alias": "SA1", "limit": "5"}` |
| `count_tabela` | Contar registros | `{"template": "count_tabela", "table_alias": "SA1"}` |

### Exemplo completo de chamada com template
```json
{"tool": "query_database", "params": {"connection_id": "HML", "template": "parametro", "param_name": "MV_ESTNEG"}}
```
O sistema resolve: connection_id "HML" → ID real, sufixo da empresa → 990, monta SQL completo.

### Quando usar SQL bruto (query) em vez de template
Apenas quando nenhum template atende. Exemplos:
- JOINs complexos entre tabelas
- Agregacoes (GROUP BY, HAVING)
- Subqueries especificas

### Comparacao de dicionario — params
- `conn_id_a` e `conn_id_b`: IDs ou aliases (HML/PRD) das conexoes
- `company_code`: codigo da empresa (se 1 empresa no ambiente, o sistema ja sabe)
- `tables`: lista opcional (ex: ["SX3"] para comparar so SX3)
