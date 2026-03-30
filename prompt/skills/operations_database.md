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

### Query de parametro (SX6)
Para buscar valor de MV_ESTNEG, MV_SPEDURL, etc:
1. Descobrir empresa: `SELECT M0_CODIGO, M0_NOME FROM SYS_COMPANY`
2. Montar sufixo: empresa 99 → SX6**990**, empresa 01 → SX6**010**
3. Query: `SELECT X6_VAR, X6_CONTEUD, X6_TIPO, X6_DESCRIC FROM SX6{sufixo} WHERE X6_VAR = 'MV_ESTNEG'`

**Atalho:** Se ja sabe a empresa da sessao, pule o passo 1.

### Query de campos (SX3)
Para "quais campos tem a SA1":
1. Sufixo pela empresa (mesma regra: SX3 + M0_CODIGO + '0')
2. `SELECT X3_CAMPO, X3_TITULO, X3_TIPO, X3_TAMANHO, X3_DECIMAL FROM SX3{sufixo} WHERE X3_ARQUIVO = 'SA1' ORDER BY X3_ORDEM`

### Query de indices (SIX)
`SELECT INDICE, ORDEM, CHAVE, DESCRICAO FROM SIX{sufixo} WHERE INDICE = 'SA1' ORDER BY ORDEM`

### Tabelas SEM sufixo (excecoes)
- `SYS_COMPANY` — sempre sem sufixo
- `TOP_FIELD` — sempre sem sufixo
- Na duvida, tente com sufixo primeiro. Se der erro, tente sem.

### Regra do sufixo
Formula: `{TABELA}{M0_CODIGO}0`
- Empresa 99 → SA1**990**, SX3**990**, SX6**990**
- Empresa 01 → SA1**010**, SX3**010**, SX6**010**
- NUNCA assuma sufixo 010 — descubra via SYS_COMPANY

### Se a query falhar (tabela nao encontrada)
1. Verificar se usou sufixo correto
2. Se nao usou sufixo, adicionar (ex: SX6 → SX6990)
3. Se usou sufixo errado, consultar SYS_COMPANY
4. Informar ao usuario: "Empresa X (codigo {M0_CODIGO}), tabela {nome_com_sufixo}"

### Comparacao de dicionario — params
- `conn_id_a` e `conn_id_b`: IDs das conexoes (ou aliases HML/PRD — resolver pelo contexto)
- `company_code`: codigo da empresa (default "01", perguntar se >1 empresa)
- `tables`: lista opcional (ex: ["SX3"] para comparar so SX3)
- Resultado: divergencias agrupadas por tabela de metadado
