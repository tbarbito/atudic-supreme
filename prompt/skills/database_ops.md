---
name: database_ops
description: Conexoes de banco externo, query executor, schema browser e drivers
intents: [table_info]
keywords: [banco, database, conexao, query, SQL, SELECT, schema, tabela, coluna, mssql, postgresql, oracle, mysql]
priority: 65
always_load: false
max_tokens: 300
specialist: database
---

## Integacao com Bancos de Dados Externos

### Drivers Suportados
| Driver | Porta Padrao | Biblioteca |
|--------|-------------|-----------|
| SQL Server (mssql) | 1433 | pymssql |
| PostgreSQL | 5432 | psycopg2 |
| MySQL | 3306 | pymysql |
| Oracle | 1521 | oracledb |

### Conexoes
- `GET /api/db-connections` — Lista (filtro: environment_id)
- `POST /api/db-connections` — Cria (senha criptografada com Fernet)
- `POST /api/db-connections/<id>/test` — Testa conexao (retorna latencia_ms)
- `POST /api/db-connections/<id>/discover` — Descobre schema

### Query Executor
- `POST /api/db-connections/<id>/query` — Executa SQL (somente SELECT)
  - Bloqueado: INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE
  - Retorna: columns, rows, row_count, duration_ms, truncated
- `POST /api/db-connections/<id>/query/csv` — Export CSV

### Schema Browser
- `GET /api/db-connections/<id>/tables` — Lista tabelas
- `GET /api/db-connections/<id>/tables/<name>/columns` — Colunas
- `GET /api/db-connections/<id>/tables/<name>/details` — Indexes, triggers, constraints

### Inferencia de conexao
- "no banco protheus homolog" → inferir connection_id pelo nome
- "no banco PRD" / "na producao" → inferir pelo nome que contem PRD/Producao
- Se ja usou uma conexao na sessao → REUTILIZAR sem perguntar
- Se so existe 1 conexao no ambiente → usar direto
- query_database NAO pede confirmacao — execute direto (e SELECT only)
