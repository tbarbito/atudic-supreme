# AtuDIC Supreme — Manual de Operacoes para Agentes IA

> Documento de referencia definitivo para agentes IA operarem o sistema AtuDIC Supreme.
> Versao: 1.0 | Data: 2026-03-30 | Autores: Barbito + Claude

---

## Indice

1. [Arquitetura Geral](#1-arquitetura-geral)
2. [Autenticacao e Autorizacao (RBAC)](#2-autenticacao-e-autorizacao-rbac)
3. [Endpoints Completos por Modulo](#3-endpoints-completos-por-modulo)
4. [Ferramentas do Agente (67 Tools)](#4-ferramentas-do-agente-67-tools)
5. [Skills do Agente (37 Skills)](#5-skills-do-agente-37-skills)
6. [Especialistas (11 Specialists)](#6-especialistas-11-specialists)
7. [Orquestracao Multi-Agente](#7-orquestracao-multi-agente)
8. [Banco de Dados — Schema Completo](#8-banco-de-dados-schema-completo)
9. [Services — Funcoes Criticas](#9-services-funcoes-criticas)
10. [Frontend — Modulos e Fluxos](#10-frontend-modulos-e-fluxos)
11. [Seguranca e Restricoes](#11-seguranca-e-restricoes)
12. [Fluxos de Execucao Principais](#12-fluxos-de-execucao-principais)
13. [Integracoes Externas](#13-integracoes-externas)
14. [Referencia Rapida de Operacoes](#14-referencia-rapida-de-operacoes)

---

## 1. Arquitetura Geral

```
                          +------------------+
                          |   Browser (SPA)  |
                          |  static/js/*.js  |
                          +--------+---------+
                                   |
                          AJAX (api-client.js)
                          Authorization header
                          X-Environment-Id header
                                   |
                          +--------v---------+
                          |  Flask Gateway   |
                          |  25 Blueprints   |
                          +--------+---------+
                                   |
                  +----------------+----------------+
                  |                |                |
          +-------v------+  +-----v------+  +------v-------+
          |   Services   |  |  Agente IA |  |   Database   |
          |  (negocio)   |  |  (GolIAs)  |  |   (core.py)  |
          +--------------+  +-----+------+  +------+-------+
                                  |                |
                          +-------v------+  +------v-------+
                          | 67 Tools     |  | PostgreSQL   |
                          | 37 Skills    |  | (plataforma) |
                          | 11 Especial. |  +--------------+
                          +--------------+  | SQLite       |
                                            | (workspace)  |
                                            +--------------+
                                            | External DBs |
                                            | MSSQL/Oracle |
                                            +--------------+
```

**Stack:** Python 3.12+ / Flask / PostgreSQL / SQLite / HTML+JS vanilla

**Entry point:** `run.py` → http://localhost:5000

**Blueprints registrados (25):**
auth, main, pipelines, users, repositories, source_control, settings, services, commands, admin, license, rpo, api, observability, knowledge, database, processes, documentation, devworkspace, dictionary, agent, mcp, auditor, tdn, workspace

---

## 2. Autenticacao e Autorizacao (RBAC)

### Niveis de Acesso

| Nivel | Profile | Codigo | Acesso |
|-------|---------|--------|--------|
| 1 | `viewer` | Leitura | Consultas, dashboards, historico |
| 2 | `operator` | Execucao | Pipelines, servicos, CRUD basico |
| 3 | `admin` | Total | Configuracao, usuarios, producao |
| — | `root` | Super | Usuario `admin` — imune a protecoes |

### Decorators de Rota

| Decorator | Nivel Minimo | Descricao |
|-----------|-------------|-----------|
| `@require_auth` | viewer | Qualquer usuario autenticado |
| `@require_operator` | operator | Operador ou admin |
| `@require_admin` | admin | Apenas admin |
| `@require_api_key` | — | Validacao via header `x-api-key` |
| `@require_auth_no_update` | viewer | Auth sem atualizar last_activity |
| `@rate_limit(N, W)` | — | Max N requests em W segundos |

### Fluxo de Autenticacao

```
POST /api/login {username, password}
    → Valida credenciais (bcrypt 12 rounds)
    → Retorna token (64 hex chars) + perfil
    → Frontend armazena em sessionStorage

Todas as requests subsequentes:
    Header: Authorization: <token>
    Header: X-Environment-Id: <env_id>

Keep-alive: POST /api/session/keep-alive (30s interval)
Logout: POST /api/logout → limpa sessao
```

---

## 3. Endpoints Completos por Modulo

### 3.1 Autenticacao (auth_bp)

| Metodo | Endpoint | Auth | Descricao |
|--------|----------|------|-----------|
| POST | `/api/login` | — | Login (rate: 5/5min) |
| POST | `/api/logout` | auth | Logout |
| POST | `/api/session/keep-alive` | auth | Heartbeat |
| GET | `/api/first-access/check` | — | Verifica primeiro acesso |

### 3.2 Sistema (main_bp)

| Metodo | Endpoint | Auth | Descricao |
|--------|----------|------|-----------|
| GET | `/api/system/info` | — | Info do SO e tipo de comando |
| GET | `/api/health` | — | Liveness probe |
| GET | `/api/health/ready` | — | Readiness (testa DB) |
| GET | `/api/dashboard/stats` | auth | Estatisticas do dashboard |

### 3.3 Pipelines (pipelines_bp)

| Metodo | Endpoint | Auth | Body/Params | Descricao |
|--------|----------|------|-------------|-----------|
| GET | `/api/pipelines` | auth | H: X-Environment-Id | Lista pipelines |
| POST | `/api/pipelines` | operator | name, description, deploy_command_id, commands[] | Cria pipeline |
| PUT | `/api/pipelines/<id>` | operator | name, description, deploy_command_id, commands[] | Atualiza pipeline |
| DELETE | `/api/pipelines/<id>` | operator | — | Remove pipeline |
| POST | `/api/pipelines/<id>/run` | operator | H: X-Environment-Id | Executa pipeline (thread) |
| GET | `/api/pipelines/<id>/runs` | auth | Q: page, limit | Historico de execucoes |
| GET | `/api/pipelines/<id>/stream-logs` | auth | — | SSE: logs em tempo real |
| GET | `/api/events` | auth | — | SSE: eventos do sistema |

**Schedules:**

| Metodo | Endpoint | Auth | Body | Descricao |
|--------|----------|------|------|-----------|
| GET | `/api/pipeline-schedules` | auth | H: X-Environment-Id | Lista agendamentos |
| POST | `/api/pipeline-schedules` | operator | pipeline_id, name, schedule_type, cron_expression, is_active | Cria agendamento |
| PUT | `/api/pipeline-schedules/<id>` | operator | (mesmo) | Atualiza agendamento |
| DELETE | `/api/pipeline-schedules/<id>` | operator | — | Remove agendamento |

**Releases:**

| Metodo | Endpoint | Auth | Descricao |
|--------|----------|------|-----------|
| GET | `/api/releases` | auth | Lista releases |
| POST | `/api/releases/<pipeline_id>` | operator | Cria release (thread) |
| GET | `/api/releases/<id>/status` | auth | Status da release |

### 3.4 Usuarios (users_bp)

| Metodo | Endpoint | Auth | Body | Descricao |
|--------|----------|------|------|-----------|
| GET | `/api/users` | admin | — | Lista usuarios |
| POST | `/api/users` | admin | username, name, email, password, profile, active, session_timeout_minutes, environment_ids[] | Cria usuario |
| PUT | `/api/users/<id>` | admin | name, email, profile, password, active, session_timeout_minutes, environment_ids[] | Atualiza usuario |
| DELETE | `/api/users/<id>` | admin | — | Remove usuario |
| PUT | `/api/users/<id>/password` | admin | admin_password, new_password | Altera senha (admin) |

### 3.5 Repositorios (repositories_bp)

| Metodo | Endpoint | Auth | Body/Params | Descricao |
|--------|----------|------|-------------|-----------|
| GET | `/api/repositories` | auth | H: X-Environment-Id | Lista repositorios |
| POST | `/api/repositories` | admin | Array de repos (GitHub format) | Salva repositorios |
| POST | `/api/repositories/<id>/clone` | operator | branch_name (rate: 10/5min) | Clona repositorio |
| POST | `/api/repositories/<id>/pull` | operator | branch_name (rate: 10/min) | Pull |
| POST | `/api/repositories/<id>/push` | operator | branch_name, commit_message (rate: 10/min) | Push |
| POST | `/api/repositories/<id>/commit` | operator | branch_name, files[], message (rate: 10/min) | Commit |
| GET | `/api/repositories/<id>/branches` | auth | — | Lista branches |
| POST | `/api/repositories/<id>/create-branch` | operator | branch_name, from_branch (rate: 30/min) | Cria branch |

### 3.6 Source Control (source_control_bp)

| Metodo | Endpoint | Auth | Params | Descricao |
|--------|----------|------|--------|-----------|
| GET | `/api/repositories/<id>/status` | auth | Q: branch (rate: 60/min) | Git status |
| GET | `/api/repositories/<id>/diff` | auth | Q: branch, file_path, staged, untracked (rate: 60/min) | Diff de arquivo |
| GET | `/api/repositories/<id>/log` | auth | Q: branch, limit (max 50, rate: 60/min) | Log de commits |
| GET | `/api/repositories/<id>/commit-files` | auth | Q: branch, hash (rate: 60/min) | Arquivos do commit |
| GET | `/api/repositories/<id>/commit-diff` | auth | Q: branch, hash, file_path (rate: 60/min) | Diff de commit |
| POST | `/api/repositories/<id>/discard` | operator | branch_name, file_paths[] (rate: 30/min) | Descarta alteracoes |
| POST | `/api/repositories/<id>/stage` | operator | branch_name, file_paths[] (rate: 30/min) | Stage arquivos |
| POST | `/api/repositories/<id>/unstage` | operator | branch_name, file_paths[] (rate: 30/min) | Unstage arquivos |

### 3.7 Settings (settings_bp)

**Environments:**

| Metodo | Endpoint | Auth | Body | Descricao |
|--------|----------|------|------|-----------|
| GET | `/api/environments` | auth | — | Lista ambientes |
| POST | `/api/environments` | admin | name, description | Cria ambiente |
| PUT | `/api/environments/<id>` | admin | name, description | Atualiza ambiente |
| DELETE | `/api/environments/<id>` | admin | — | Remove ambiente |

**Server Variables:**

| Metodo | Endpoint | Auth | Body | Descricao |
|--------|----------|------|------|-----------|
| GET | `/api/server-variables` | operator | — | Lista variaveis (senhas mascaradas) |
| POST | `/api/server-variables` | operator | name, value, description, is_password | Cria variavel |
| PUT | `/api/server-variables/<id>` | operator | name, value, description, is_password | Atualiza variavel |
| DELETE | `/api/server-variables/<id>` | operator | — | Remove variavel |
| GET | `/api/server-variables/<id>/history` | operator | — | Historico (ultimas 50) |

**Notificacoes:**

| Metodo | Endpoint | Auth | Body | Descricao |
|--------|----------|------|------|-----------|
| GET | `/api/notification-settings` | admin | — | Config SMTP + WhatsApp |
| PUT | `/api/notification-settings` | admin | smtp_*, whatsapp_* | Atualiza config |

### 3.8 Services (services_bp)

**Server Services:**

| Metodo | Endpoint | Auth | Descricao |
|--------|----------|------|-----------|
| GET | `/api/server-services` | operator | Lista servicos |
| POST | `/api/server-services` | operator | Cria servico |
| PUT | `/api/server-services/<id>` | operator | Atualiza servico |
| DELETE | `/api/server-services/<id>` | operator | Remove servico |

**Service Actions:**

| Metodo | Endpoint | Auth | Body | Descricao |
|--------|----------|------|------|-----------|
| GET | `/api/service-actions` | auth | H: X-Environment-Id | Lista acoes |
| POST | `/api/service-actions` | operator | name, server_service_id, action_type, os_type, command | Cria acao |
| PUT | `/api/service-actions/<id>` | operator | (mesmo) | Atualiza acao |
| DELETE | `/api/service-actions/<id>` | operator | — | Remove acao |
| POST | `/api/service-actions/<id>/execute` | operator | — | Executa acao (thread) |

### 3.9 Commands (commands_bp)

| Metodo | Endpoint | Auth | Body | Descricao |
|--------|----------|------|------|-----------|
| GET | `/api/commands` | auth | H: X-Environment-Id, Q: category, search | Lista comandos |
| POST | `/api/commands` | admin | name, type (bash/powershell/python/nodejs/docker), command_category (build/deploy), script, description | Cria comando |
| PUT | `/api/commands/<id>` | admin | (mesmo) | Atualiza comando |
| DELETE | `/api/commands/<id>` | admin | — | Remove comando |

### 3.10 Admin (admin_bp)

| Metodo | Endpoint | Auth | Descricao |
|--------|----------|------|-----------|
| GET | `/api/admin/logs/<type>` | admin | Logs do sistema (general/errors/audit, max 1000 linhas) |
| GET | `/api/admin/rate-limits` | admin | Status do rate limiter |
| POST | `/api/admin/rate-limits/clear` | admin | Limpa rate limits |
| GET | `/api/admin/encryption-key/info` | admin | Info da chave (sem expor) |
| POST | `/api/admin/encryption-key/backup` | admin | Cria backup da chave |
| GET | `/api/admin/webhooks` | admin | Lista webhooks |
| POST | `/api/admin/webhooks` | admin | Cria webhook |
| PUT | `/api/admin/webhooks/<id>` | admin | Atualiza webhook |
| DELETE | `/api/admin/webhooks/<id>` | admin | Remove webhook |

### 3.11 API Externa (api_bp)

**API Keys:**

| Metodo | Endpoint | Auth | Descricao |
|--------|----------|------|-----------|
| GET | `/api/api_management/keys` | admin | Lista API keys (mascaradas) |
| POST | `/api/api_management/keys` | admin | Gera nova API key |
| DELETE | `/api/api_management/keys/<id>` | admin | Remove API key |

**Endpoints Externos (via API key):**

| Metodo | Endpoint | Auth | Descricao |
|--------|----------|------|-----------|
| POST | `/api/v1/pipelines/<id>/trigger` | api_key | Dispara pipeline (202) |
| GET | `/api/v1/pipelines/<id>/status` | api_key | Status do pipeline |
| POST | `/api/v1/services/actions/<id>/trigger` | api_key | Dispara acao (202) |

### 3.12 MCP Gateway (mcp_bp)

| Metodo | Endpoint | Auth | Body | Descricao |
|--------|----------|------|------|-----------|
| GET | `/api/mcp/health` | — | — | Health check MCP |
| GET | `/api/mcp/tools` | api_key | — | Lista ferramentas (formato MCP) |
| POST | `/api/mcp/execute` | api_key | tool_name, params | Executa ferramenta |

### 3.13 Observability (observability_bp)

**Log Monitors:**

| Metodo | Endpoint | Auth | Descricao |
|--------|----------|------|-----------|
| GET | `/api/log-monitors` | operator | Lista monitores |
| GET | `/api/log-monitors/browse-logs` | operator | Arquivos de log disponiveis |
| POST | `/api/log-monitors` | operator | Cria monitor |
| PUT | `/api/log-monitors/<id>` | operator | Atualiza monitor |
| DELETE | `/api/log-monitors/<id>` | operator | Remove monitor |

**Alert Rules:**

| Metodo | Endpoint | Auth | Descricao |
|--------|----------|------|-----------|
| GET | `/api/alert-rules` | operator | Lista regras |
| POST | `/api/alert-rules` | operator | Cria regra |
| PUT | `/api/alert-rules/<id>` | operator | Atualiza regra |
| DELETE | `/api/alert-rules/<id>` | operator | Remove regra |

### 3.14 Knowledge Base (knowledge_bp)

| Metodo | Endpoint | Auth | Params/Body | Descricao |
|--------|----------|------|-------------|-----------|
| GET | `/api/knowledge` | auth | Q: q, category, source, limit (max 200), offset | Busca artigos |
| GET | `/api/knowledge/<id>` | auth | — | Detalhe (incrementa usage_count) |
| POST | `/api/knowledge` | operator | title, category, error_pattern, description, causes, solution, code_snippet, reference_url, tags, source | Cria artigo |
| PUT | `/api/knowledge/<id>` | operator | (mesmo) | Atualiza artigo |
| DELETE | `/api/knowledge/<id>` | operator | — | Remove artigo |

### 3.15 Documentation (documentation_bp)

| Metodo | Endpoint | Auth | Body | Descricao |
|--------|----------|------|------|-----------|
| GET | `/api/docs` | auth | Q: doc_type, limit, offset | Lista documentos |
| GET | `/api/docs/<id>` | auth | — | Documento completo |
| POST | `/api/docs/generate` | admin | doc_type (dicionario_dados/mapa_processos/guia_erros/combinado), title, connection_id, module, category | Gera documento |
| GET | `/api/docs/<id>/versions` | auth | — | Versoes do documento |
| DELETE | `/api/docs/<id>` | admin | — | Remove documento |

### 3.16 Processes (processes_bp)

| Metodo | Endpoint | Auth | Descricao |
|--------|----------|------|-----------|
| GET | `/api/protheus-modules` | admin | Lista modulos Protheus |
| GET | `/api/processes/sx2-lookup` | admin | Lookup tabela SX2 |
| POST | `/api/processes/seed` | admin | Seed processos padrao |
| GET | `/api/processes` | admin | Lista processos (filtros: module, status, search) |
| POST | `/api/processes` | admin | Cria processo |
| PUT | `/api/processes/<id>` | admin | Atualiza processo |
| DELETE | `/api/processes/<id>` | admin | Remove processo |
| GET | `/api/processes/<id>/tables` | admin | Tabelas do processo |
| POST | `/api/processes/<id>/tables` | admin | Vincula tabela |

### 3.17 Dev Workspace (devworkspace_bp)

| Metodo | Endpoint | Auth | Descricao |
|--------|----------|------|-----------|
| GET | `/api/devworkspace/fontes` | auth | Lista diretorios FONTES (rate: 60/min) |
| GET | `/api/devworkspace/browse` | auth | Navega diretorio (rate: 120/min) |
| GET | `/api/devworkspace/file` | auth | Le arquivo fonte (rate: 120/min) |
| POST | `/api/devworkspace/search` | auth | Busca em fontes (rate: 30/min) |
| POST | `/api/devworkspace/impact` | auth | Analise de impacto (rate: 30/min) |
| POST | `/api/devworkspace/compile` | operator | Compilacao ADVPL |
| GET | `/api/devworkspace/branch-policies` | admin | Lista policies de branch |
| POST | `/api/devworkspace/branch-policies` | admin | Cria policy |
| PUT | `/api/devworkspace/branch-policies/<id>` | admin | Atualiza policy |
| DELETE | `/api/devworkspace/branch-policies/<id>` | admin | Remove policy |

### 3.18 Dictionary (dictionary_bp)

| Metodo | Endpoint | Auth | Body | Descricao |
|--------|----------|------|------|-----------|
| GET | `/api/dictionary/companies/<conn_id>` | admin | — | Lista empresas (SYS_COMPANY) |
| POST | `/api/dictionary/compare` | admin | conn_id_a, conn_id_b, company_code, tables[], alias_filter, include_deleted | Compara dicionarios |
| POST | `/api/dictionary/validate` | admin | connection_id, company_code, layers[] | Valida integridade |
| POST | `/api/dictionary/equalize` | admin | conn_source_id, conn_target_id, company_code, operations[] | Equaliza dicionarios |
| GET | `/api/dictionary/history` | admin | Q: limit, offset | Historico de operacoes |
| GET | `/api/dictionary/history/<id>` | admin | — | Detalhe da operacao |

### 3.19 Database Connections (database_bp)

| Metodo | Endpoint | Auth | Body | Descricao |
|--------|----------|------|------|-----------|
| GET | `/api/db-connections` | admin | Q: environment_id | Lista conexoes |
| POST | `/api/db-connections` | admin | name, driver, host, port, database_name, username, password, extra_params, is_readonly, ref_environment_id, connection_role, rest_url | Cria conexao |
| PUT | `/api/db-connections/<id>` | admin | (mesmo) | Atualiza conexao |
| DELETE | `/api/db-connections/<id>` | admin | — | Remove conexao |
| POST | `/api/db-connections/<id>/test` | admin | — | Testa conexao |
| GET | `/api/db-connections/<id>/schema` | admin | Q: limit, offset, filter | Schema das tabelas |
| GET | `/api/db-connections/<id>/table/<name>` | admin | — | Estrutura da tabela |
| POST | `/api/db-connections/<id>/query` | admin | query (somente SELECT, max 1000 rows) | Executa query |

### 3.20 Agent (agent_bp)

| Metodo | Endpoint | Auth | Body/Params | Descricao |
|--------|----------|------|-------------|-----------|
| POST | `/api/agent/chat` | auth | messages[], temperature, max_tokens | Chat SSE streaming |
| GET | `/api/agent/chat/models` | auth | — | Modelos LLM disponiveis |
| GET | `/api/agent/memory/search` | auth | Q: q (required), type, environment_id, limit (max 50) | Busca BM25 na memoria |
| GET | `/api/agent/memory/stats` | auth | — | Estatisticas de memoria |
| GET | `/api/agent/memory/chunks` | auth | Q: type, source, limit, offset | Lista chunks |
| GET | `/api/agent/memory/chunks/<id>` | auth | — | Detalhe do chunk |
| GET | `/api/agent/memory/files` | auth | — | Lista arquivos .md |
| GET | `/api/agent/memory/file` | auth | Q: path | Le arquivo de memoria |
| POST | `/api/agent/memory/file` | operator | path, content | Cria arquivo de memoria |

### 3.21 Auditor INI (auditor_bp)

| Metodo | Endpoint | Auth | Body | Descricao |
|--------|----------|------|------|-----------|
| POST | `/api/auditor/upload` | auth | Multipart: ini_file (ou JSON: content, filename) | Analisa INI |
| GET | `/api/auditor/history` | auth | Q: environment_id, limit (max 100), offset | Historico de auditorias |
| GET | `/api/auditor/audit/<id>` | auth | — | Detalhe da auditoria |
| GET | `/api/auditor/best-practices` | auth | Q: ini_type | Lista boas praticas |
| POST | `/api/auditor/best-practices/seed` | admin | — | Seed boas praticas |
| PUT | `/api/auditor/best-practices/<id>` | admin | rule_name, severity, recommendation, enabled | Atualiza regra |

### 3.22 TDN (tdn_bp)

| Metodo | Endpoint | Auth | Body | Descricao |
|--------|----------|------|------|-----------|
| GET | `/api/tdn/stats` | auth | — | Estatisticas da base TDN |
| GET | `/api/tdn/sources` | auth | — | Fontes disponiveis |
| POST | `/api/tdn/ingest` | auth | json_file, source, max_pages, scrape, workers | Ingestao JSON (202) |
| POST | `/api/tdn/ingest-md` | auth | md_file, source | Ingestao Markdown (202) |
| GET | `/api/tdn/search` | auth | Q: q, limit, offset | Busca full-text |
| GET | `/api/tdn/pages` | auth | Q: source, limit, offset | Lista paginas |
| GET | `/api/tdn/runs` | auth | Q: limit, offset | Historico de scraping |

### 3.23 License (license_bp)

| Metodo | Endpoint | Auth | Descricao |
|--------|----------|------|-----------|
| GET | `/api/license/status-admin` | admin | Status da licenca |
| GET | `/activate` | — | Pagina de ativacao |
| POST | `/api/license/validate-admin` | — | Valida admin para licenca |
| GET | `/api/license/info` | — | Info da licenca + hardware ID |
| POST | `/api/license/activate` | — | Ativa licenca |

### 3.24 RPO (rpo_bp)

| Metodo | Endpoint | Auth | Descricao |
|--------|----------|------|-----------|
| GET | `/api/rpo/versions/<env_id>` | auth | Lista versoes RPO |
| POST | `/api/rpo/upload/<env_id>` | operator | Upload RPO (.rpo/.zip/.rar) |
| GET | `/api/rpo/download/<version_id>` | auth | Download RPO |

### 3.25 Workspace (workspace_bp) [prefixo: /api/workspace]

| Metodo | Endpoint | Auth | Body | Descricao |
|--------|----------|------|------|-----------|
| GET | `/api/workspace/workspaces` | — | — | Lista workspaces |
| POST | `/api/workspace/workspaces` | admin | slug, client_name, description | Cria workspace |
| GET | `/api/workspace/workspaces/<slug>` | admin | — | Detalhe do workspace |
| POST | `/api/workspace/workspaces/<slug>/ingest-csv` | admin | Multipart: CSV | Ingestao CSV (202) |
| POST | `/api/workspace/workspaces/<slug>/ingest-protheus` | admin | connection_id, company_code | Ingestao live DB (202) |
| GET | `/api/workspace/workspaces/<slug>/tables` | admin | Q: search, limit, offset | Lista tabelas |
| GET | `/api/workspace/workspaces/<slug>/table/<name>` | admin | — | Estrutura da tabela |
| GET | `/api/workspace/workspaces/<slug>/relationships` | admin | Q: from_table, to_table | Grafo de relacionamentos |
| POST | `/api/workspace/workspaces/<slug>/analyze` | admin | prompt | Analise LLM (SSE) |
| DELETE | `/api/workspace/workspaces/<slug>` | admin | — | Remove workspace |

---

## 4. Ferramentas do Agente (67 Tools)

### 4.1 Classificacao de Risco

| Nivel | Cor | Descricao | Exemplos |
|-------|-----|-----------|----------|
| LOW | Verde | Somente leitura | get_*, search_*, query_database |
| MEDIUM | Amarelo | CRUD em HML/DEV | create_*, update_*, acknowledge_* |
| HIGH | Vermelho | Producao / destrutivo | execute_equalization, run_command, write_file |

### 4.2 Inventario Completo

#### A. Leitura (12 tools) — viewer — LOW

| # | Tool | Descricao | Parametros |
|---|------|-----------|------------|
| 1 | `get_environments` | Lista ambientes | — |
| 2 | `get_pipelines` | Lista pipelines | — |
| 3 | `get_pipeline_status` | Historico de runs | pipeline_id |
| 4 | `get_alerts` | Alertas recentes | environment_id, category, severity, limit |
| 5 | `get_alert_summary` | Resumo estatistico | environment_id, days (7-30) |
| 6 | `get_recurring_errors` | Erros cronicos (min 3x) | environment_id, limit, days |
| 7 | `get_repositories` | Repositorios git | — |
| 8 | `get_services` | Servicos monitorados | environment_id |
| 9 | `get_schedules` | Agendamentos | — |
| 10 | `get_server_variables` | Variaveis (senhas mascaradas) | — |
| 11 | `get_db_connections` | Conexoes de banco | environment_id |
| 12 | `get_users` | Usuarios do sistema | — (admin only) |

#### B. Busca (2 tools) — viewer — LOW

| # | Tool | Descricao | Parametros |
|---|------|-----------|------------|
| 13 | `search_knowledge` | Busca na base de conhecimento | query, category, limit |
| 14 | `get_system_overview` | Snapshot completo do sistema | — |

#### C. Acoes (7 tools) — operator — MEDIUM/HIGH

| # | Tool | Descricao | Confirmacao | Parametros |
|---|------|-----------|-------------|------------|
| 15 | `run_pipeline` | Dispara pipeline | Nao | pipeline_id |
| 16 | `create_release` | Deploy de release | **Sim** | pipeline_id, run_id |
| 17 | `execute_service_action` | Start/stop/restart servico | Nao | action_id |
| 18 | `acknowledge_alert` | Marca alerta como visto | Nao | alert_id |
| 19 | `acknowledge_alerts_bulk` | Ack em lote | **Sim** | alert_ids[] |
| 20 | `toggle_schedule` | Liga/desliga agendamento | Nao | schedule_id |
| 21 | `git_pull` | Pull de repositorio | Nao | repository_id, branch |

#### D. Database (9 tools) — admin — MEDIUM

| # | Tool | Descricao | Confirmacao | Parametros |
|---|------|-----------|-------------|------------|
| 22 | `query_database` | SELECT com auto-correcao suffix Protheus | Nao | connection_id, query |
| 23 | `compare_dictionary` | Compara SX2/SX3/SIX/SX7/SX5/SX6/SX9 | Nao | conn_id_a, conn_id_b, company_code |
| 24 | `validate_dictionary` | Valida integridade vs fisico | Nao | connection_id, company_code |
| 25 | `get_dictionary_history` | Historico de comparacoes | Nao | limit, offset |
| 26 | `preview_equalization` | Gera SQL de equalizacao (preview) | Nao | conn_source, conn_target, company_code |
| 27 | `execute_equalization` | Executa equalizacao | **Sim** | conn_source, conn_target, company_code |
| 28 | `upload_ingest_file` | Parse JSON/MD de dicionario | Nao | file_content, format |
| 29 | `preview_ingestion` | Preview SQL de ingestao | Nao | file_content, target_connection_id |
| 30 | `execute_ingestion` | Executa ingestao | **Sim** | file_content, target_connection_id |

#### E. Conexoes DB (5 tools) — admin — MEDIUM

| # | Tool | Descricao | Confirmacao | Parametros |
|---|------|-----------|-------------|------------|
| 31 | `create_db_connection` | Cria conexao | **Sim** | name, driver, host, port, database_name, username, password |
| 32 | `update_db_connection` | Atualiza conexao | **Sim** | connection_id, (campos) |
| 33 | `delete_db_connection` | Remove conexao | **Sim** | connection_id |
| 34 | `test_db_connection` | Testa conectividade | Nao | connection_id |
| 35 | `discover_db_schema` | Introspecta schema | Nao | connection_id |

#### F. Log Monitoring (7 tools) — operator — LOW/MEDIUM

| # | Tool | Descricao | Confirmacao | Parametros |
|---|------|-----------|-------------|------------|
| 36 | `list_log_monitors` | Lista monitores | Nao | environment_id |
| 37 | `create_log_monitor` | Cria monitor | **Sim** | name, file_path, environment_id, patterns, severity |
| 38 | `update_log_monitor` | Atualiza monitor | **Sim** | monitor_id, (campos) |
| 39 | `delete_log_monitor` | Remove monitor | **Sim** | monitor_id |
| 40 | `scan_log_monitor` | Scan manual | Nao | monitor_id |
| 41 | `browse_log_files` | Arquivos .log no servidor | Nao | environment_id |
| 42 | `get_alerts_timeline` | Timeline por hora | Nao | environment_id, hours |

#### G. Server Variables (4 tools) — operator — MEDIUM

| # | Tool | Descricao | Confirmacao | Parametros |
|---|------|-----------|-------------|------------|
| 43 | `create_server_variable` | Cria variavel | **Sim** | name, value, description, is_password |
| 44 | `update_server_variable` | Atualiza variavel | **Sim** | variable_id, (campos) |
| 45 | `delete_server_variable` | Remove variavel | **Sim** | variable_id |
| 46 | `get_variable_history` | Trilha de auditoria | Nao | variable_id |

#### H. Webhooks (5 tools) — admin — MEDIUM

| # | Tool | Descricao | Confirmacao | Parametros |
|---|------|-----------|-------------|------------|
| 47 | `list_webhooks` | Lista webhooks | Nao | — |
| 48 | `create_webhook` | Registra webhook | **Sim** | url, event_type, is_active |
| 49 | `update_webhook` | Modifica webhook | **Sim** | webhook_id, (campos) |
| 50 | `delete_webhook` | Remove webhook | **Sim** | webhook_id |
| 51 | `test_webhook` | Envia evento teste | Nao | webhook_id |

#### I. Auditoria (3 tools) — viewer/admin

| # | Tool | Descricao | Confirmacao | Parametros |
|---|------|-----------|-------------|------------|
| 52 | `get_auditor_history` | Historico de auditorias INI | Nao | environment_id, limit |
| 53 | `get_audit_detail` | Detalhe completo | Nao | audit_id |
| 54 | `delete_audit` | Remove auditoria | **Sim** | audit_id |

#### J. Sistema / Sandbox (6 tools) — admin — HIGH

| # | Tool | Descricao | Confirmacao | Restricoes |
|---|------|-----------|-------------|------------|
| 55 | `read_file` | Le arquivo (max 1MB, texto) | Nao | Sandbox paths |
| 56 | `write_file` | Cria/sobrescreve (max 100KB) | **Sim** | Sandbox paths |
| 57 | `list_directory` | Lista diretorio (max 100) | Nao | Sandbox paths |
| 58 | `search_files` | Busca regex em arquivos | Nao | Max 100 arquivos |
| 59 | `get_file_info` | Metadados do arquivo | Nao | Sandbox paths |
| 60 | `run_command` | Executa comando shell | **Sim** | Allowlist, timeout 30s |

#### K. Workspace / ExtraiRPO (6 tools) — operator

| # | Tool | Descricao | Parametros |
|---|------|-----------|------------|
| 61 | `parse_source_code` | Analisa ADVPL/TLPP | file_path |
| 62 | `analyze_impact` | Impacto de campo/tabela | table, field |
| 63 | `build_dependency_graph` | Grafo de dependencias | module |
| 64 | `list_vinculos` | Relacionamentos campo/funcao/gatilho | table, field |
| 65 | `processos_cliente` | Processos de negocio detectados | workspace_slug |
| 66 | `registrar_processo` | Registra/enriquece processo | workspace_slug, process_data |

#### L. Dinamicos (1+)

| # | Tool | Descricao |
|---|------|-----------|
| 67+ | Workspace tools | Registrados dinamicamente de workspace/agent_tools.py |

### 4.3 Cadeia de Fallback

Se uma tool falha, o agente tenta automaticamente:

| Tool Original | Fallback |
|---------------|----------|
| `get_alerts` | `search_knowledge` |
| `get_alert_summary` | `get_alerts` |
| `get_recurring_errors` | `search_knowledge` |
| `get_pipeline_status` | `get_pipelines` |
| `query_database` | `search_knowledge` |
| `create_release` | `get_pipeline_status` |

---

## 5. Skills do Agente (37 Skills)

Skills sao fragmentos de prompt carregados sob demanda com base no intent detectado.

### 5.1 Regras de Carregamento

- `always_load: true` → sempre injetado (ex: `quick_response`)
- Match por intent (primario)
- Match por keywords na mensagem (secundario)
- Match por specialist (para sub-agentes)
- Limite: 5 skills por mensagem, 4000 tokens max

### 5.2 Inventario Completo

| # | Skill | Specialist | Intents | Prioridade |
|---|-------|-----------|---------|------------|
| 1 | `agent_behavior` | general | error_analysis, ini_audit, table_info, procedure_lookup, admin_management, settings_management | — |
| 2 | `alert_triage` | diagnostico | error_analysis, alert_recurrence | — |
| 3 | `admin_crud` | all | admin_management | — |
| 4 | `auth_multitenancy` | general | user_context, settings_management | — |
| 5 | `cicd_pipelines` | devops | pipeline_status, repository_operations | — |
| 6 | `database_ops` | database | table_info | — |
| 7 | `devworkspace` | devops | source_analysis | — |
| 8 | `dictionary_ops` | database | table_info, dictionary_analysis | — |
| 9 | `dictionary_schema` | database | table_info | — |
| 10 | `docs_processes` | documentador | documentation_generation | — |
| 11 | `documentation_generation` | documentador | documentation_generation | — |
| 12 | `error_diagnosis` | diagnostico | error_analysis, alert_recurrence, bug_diagnosis | — |
| 13 | `git_ops` | devops | repository_operations | — |
| 14 | `impact_analysis` | dicionarista, analista_fontes, campo_agent, projeto_agent | table_info, field_change_request, source_analysis | — |
| 15 | `knowledge_base` | auditor | knowledge_search, procedure_lookup, ini_audit | — |
| 16 | `monitoring_alerts` | diagnostico | error_analysis, alert_recurrence | — |
| 17 | `observability_crud` | diagnostico | error_analysis | — |
| 18 | `pipeline_ops` | devops | pipeline_status | — |
| 19 | `platform_overview` | general | general, user_context, environment_status | — |
| 20 | `process_ops` | knowledge | procedure_lookup, project_analysis | — |
| 21 | `protheus_framework` | auditor | ini_audit, procedure_lookup, bug_diagnosis | — |
| 22 | `protheus_structure` | auditor | ini_audit, table_info, source_analysis | — |
| 23 | `protheus_tlpp` | knowledge | procedure_lookup, source_analysis, bug_diagnosis | — |
| 24 | `quick_response` | general | ALL (always_load=true, priority=100) | 100 |
| 25 | `react_operations` | general | general | — |
| 26 | `service_ops` | devops | service_operations | — |
| 27 | `services_mgmt` | devops | service_operations | — |
| 28 | `settings_crud` | settings | settings_management | — |
| 29 | `sql_protheus` | database | table_info, knowledge_search, general | — |
| 30 | `task_planning` | general | general | — |
| 31 | `tdn_advpl_functions` | knowledge | procedure_lookup, knowledge_search | — |
| 32 | `tdn_appserver_config` | diagnostico | error_analysis, ini_audit | — |
| 33 | `tdn_protheus_dictionary` | dicionarista | table_info, dictionary_analysis | — |
| 34 | `tdn_tss_diagnostico` | diagnostico | error_analysis, alert_recurrence | — |
| 35 | `user_context` | general | general, user_context | — |
| 36 | `workspace_reverse_engineering` | dicionarista, analista_fontes, campo_agent, bug_agent, projeto_agent | source_analysis, code_review, field_change_request, documentation_generation | — |
| 37 | (reservado para expansao) | — | — | — |

---

## 6. Especialistas (11 Specialists)

Definidos em `prompt/specialists.yml`:

| Especialista | Agent Autonomo | Budget | Max Iter | Tools | Intents Primarios |
|-------------|:--------------:|-------:|:--------:|------:|-------------------|
| `diagnostico` | Sim | 20K | 6 | 13 | error_analysis, alert_recurrence |
| `database` | Sim | 35K | 8 | 19 | table_info, dictionary_analysis |
| `devops` | Sim | 30K | 8 | 10 | pipeline_status, repository_ops, service_ops |
| `auditor` | Nao | 15K | 6 | 6 | ini_audit |
| `settings` | Sim | 15K | 6 | 6 | settings_management |
| `admin_ops` | Sim | 15K | 6 | 6 | admin_management |
| `knowledge` | Sim | 12K | 5 | 5 | knowledge_search, procedure_lookup |
| `general` | Nao | 20K | 6 | 13 | general, user_context |
| `proactive` | Sim | 15K | 6 | 4 | (monitoramento autonomo) |
| `dicionarista` | Sim | 25K | 8 | 10 | table_info, dictionary_analysis |
| `analista_fontes` | Sim | 25K | 6 | 5 | source_analysis, code_review |

Especialistas adicionais: `documentador`, `campo_agent`, `bug_agent`, `projeto_agent`

---

## 7. Orquestracao Multi-Agente

### 7.1 Padroes de Orquestracao

| Padrao | Descricao | Quando usar |
|--------|-----------|-------------|
| **Single** | 1 tarefa → 1 especialista | Dominio unico claro |
| **Fan-Out** | N especialistas em paralelo → merge | Multi-dominio (ex: diagnostico + database) |
| **Chain** | Output(A) → Input(B) | Tarefas sequenciais dependentes |

### 7.2 Deteccao de Dominio

9 dominios com keywords score:
- `diagnostico`: erro, falha, log, alerta, crash, ORA-, TOPCONN
- `database`: tabela, campo, SX, dicionario, query, SQL
- `auditor`: INI, appserver, configuracao, auditoria
- `settings`: variavel, ambiente, configurar
- `admin_ops`: webhook, usuario, permissao
- `devops`: pipeline, deploy, repositorio, compilar, servico
- `knowledge`: como fazer, funcao, ADVPL, TDN
- `general`: (fallback)

### 7.3 Fluxo Completo

```
Mensagem do Usuario
    |
    v
Intent Detection (9 intents, regex + keywords)
    |
    v
Entity Extraction (tabelas, campos, codigos erro, funcoes)
    |
    v
Complexity Classification (simples/complexo)
    |
    v
Orchestrator Decision (single/fan_out/chain)
    |
    v
Skill Loading (até 5 skills, 4K tokens)
    |
    v
Context Gathering (memoria + KB + alertas + TDN + sistema)
    |
    v
System Prompt Composition
    |
    v
LLM Call (com tools disponiveis filtrados por RBAC)
    |
    v
Tool Call Parsing (JSON/XML tolerante)
    |
    v
Tool Execution (permissao + budget + fallback)
    |
    v
Result Formatting (max 3000 chars)
    |
    v
Response Composition (LLM ou template)
    |
    v
Audit Log + History Save
    |
    v
SSE Stream → Usuario
```

### 7.4 Token Budget

| Contexto | Budget Padrao |
|----------|---------------|
| Mensagem principal | 50.000 tokens |
| Sub-agente (specialist) | 15.000-35.000 tokens |
| Estimativa: | len(text) // 4 |
| Custo referencia: | $3/1M input + $15/1M output |

---

## 8. Banco de Dados — Schema Completo

### 8.1 PostgreSQL (Plataforma) — 35+ tabelas

**Autenticacao & Usuarios:**
- `users` — id, username, name, email, password_hash, salt, profile, active, session_timeout_minutes
- `sessions` — token, user_id, last_activity, expires_at
- `user_environments` — user_id, environment_id

**Ambientes & Config:**
- `environments` — id, name, description
- `server_variables` — id, name, value, description, is_password, environment_id
- `server_variables_audit` — historico de alteracoes
- `notification_settings` — smtp_*, whatsapp_*

**Pipelines & CI/CD:**
- `pipelines` — id, name, description, deploy_command_id, environment_id, is_protected
- `pipeline_commands` — pipeline_id, command_id, execution_order
- `commands` — id, name, type, command_category, script, description, environment_id
- `pipeline_runs` — id, pipeline_id, run_number, status, started_at, finished_at, user_id
- `execution_logs` — run_id, log_line, log_level, created_at
- `pipeline_schedules` — id, pipeline_id, name, schedule_type, cron_expression, is_active, next_run
- `releases` — id, pipeline_id, run_id, rpo_version_id, status

**Repositorios:**
- `repositories` — id, name, full_name, clone_url, github_token_encrypted, environment_id
- `branch_policies` — repo_name, branch_name, allow_push/pull/commit, require_approval

**Servicos:**
- `server_services` — id, name, display_name, server_name, environment_id
- `service_actions` — id, name, server_service_id, action_type, os_type, command

**Observability:**
- `log_monitor_configs` — id, name, log_type, log_path, check_interval_seconds, environment_id
- `log_alerts` — id, severity, category, message, thread_id, username, acknowledged_at, environment_id
- `alert_rules` — id, name, trigger_pattern, condition, action, environment_id
- `alert_trends` — materialized view (category + environment)
- `alert_recurrence` — id, environment_id, category, message_hash, occurrence_count

**Knowledge:**
- `knowledge_articles` — id, title, category, error_pattern, solution, causes, tsv (FTS)
- `correction_history` — environment_id, alert_id, article_id, correction_applied
- `notification_rules` — severity, category, min_occurrences, cooldown_minutes

**Documentacao:**
- `generated_docs` — id, doc_type, title, content_markdown, version, file_size

**Processos:**
- `business_processes` — id, name, module, description, status
- `process_tables` — process_id, table_name, table_alias, table_role
- `process_fields` — table_id, column_name, column_label, is_key
- `process_flows` — source_process_id, target_process_id, flow_type

**Database:**
- `database_connections` — id, name, driver, host, port, database_name, username, password_encrypted, is_readonly, ref_environment_id, connection_role, rest_url
- `schema_cache` — connection_id, table_name, columns (JSONB)
- `query_history` — connection_id, query_text, user_id, executed_at

**Agente:**
- `agent_settings` — environment_id, setting_key, setting_value
- `llm_provider_configs` — provider_id, api_key_encrypted, model, base_url, options
- `agent_audit_log` — user_id, session_id, action, params, result_status, tokens_used
- `agent_sandbox_config` — environment_id, allowed_paths, blocked_commands, max_iterations

**Auditoria INI:**
- `ini_audits` — id, environment_id, filename, ini_type, raw_content, parsed_json, score, llm_summary
- `ini_best_practices` — ini_type, section, key_name, recommended_value, severity
- `ini_audit_results` — audit_id, section, key_name, current_value, status, llm_insight

**TDN:**
- `tdn_pages` — id, source, page_title, page_url, breadcrumb, content_hash, chunks_count, status
- `tdn_chunks` — id, page_id, chunk_index, content, section_title, tokens_approx, tsv (FTS GIN)
- `tdn_scrape_runs` — id, source, status, pages_total, pages_scraped, started_at

**Admin:**
- `api_keys` — id, name, key_hash, created_at
- `webhooks` — id, url, event_type, is_active, headers
- `audit_logs` — action, user_id, details, status, ip_address
- `rpo_versions` — id, environment_id, filename, md5_hash, file_size, user_id
- `schema_migrations` — version, applied_at

### 8.2 SQLite (por Workspace) — 8+ tabelas

- `tabelas` — codigo, nome, modo, custom
- `campos` — tabela, campo, tipo, tamanho, decimal, titulo, descricao, validacao
- `indices` — tabela, ordem, chave, descricao
- `gatilhos` — campo_origem, sequencia, campo_destino, regra
- `perguntas` — grupo, ordem, pergunta, variavel, tipo
- `tabelas_genericas` — filial, tabela, chave, descricao
- `parametros` — filial, variavel, tipo, descricao, conteudo
- `relacionamentos` — tabela_origem, identificador, tabela_destino

### 8.3 Regras Criticas de Conexao

> **CUIDADO**: `conn.close()` NAO devolve ao pool — SEMPRE usar `release_db_connection(conn)`

> **CUIDADO**: Conexoes diretas (`psycopg2.connect()`) devem usar `conn.close()`, NAO `release_db_connection()`

- Pool: `ThreadedConnectionPool` (min=2, max=30)
- Warning automatico em 90% de ocupacao
- Usar `TransactionContext` para operacoes com auto-commit/rollback
- SAVEPOINT suportado para transacoes aninhadas

---

## 9. Services — Funcoes Criticas

### 9.1 Execucao de Pipeline (runner.py)

```python
execute_pipeline_thread(pipeline_id, user_id)
    1. Adquire environment lock (exclusivo)
    2. Carrega pipeline + comandos ordenados
    3. Executa cada step sequencialmente
    4. Atualiza pipeline_runs (status, timestamps)
    5. Registra execution_logs por step
    6. Dispara webhooks na conclusao
    7. Libera environment lock
```

### 9.2 Agendamento (scheduler.py)

```python
PipelineScheduler:
    _scheduler_loop() → poll a cada 60s
    _check_and_execute_schedules() → query pending_runs
    calculate_next_run(schedule) → datetime
    Tipos: once, daily, weekly, monthly, cron
```

### 9.3 Comparacao de Dicionario (dictionary_compare.py)

```python
compare_dictionaries(conn_a_id, conn_b_id, company_code)
    13 tabelas de metadados: SX2, SX3, SIX, SX1, SX5, SX6, SX7, SX9, SXA, SXB, XXA, XAM, XAL
    Retorna: tables_compared, differences[], summary
    Cada diff: {table, action (added/removed/modified), record, old_value, new_value}
```

### 9.4 Equalizacao de Dicionario (dictionary_equalizer.py)

```python
execute_equalization(connection_id, preview_only=False)
    4 fases:
    1. DDL: ALTER TABLE / CREATE TABLE / CREATE INDEX
    2. DML: INSERT/UPDATE metadados SX2, SX3, SIX
    3. Signal: UPDATE SYSTEM_INFO (invalidar cache AppServer)
    4. TcRefresh: REST call ao Protheus ZATUREF
```

### 9.5 Ingestao de Dicionario (dictionary_ingestor.py)

```python
ingest_from_json(json_path, target_connection_id)
    4 fases identicas a equalizacao
    Parse JSON → DDL + DML → Signal → TcRefresh
```

### 9.6 Parse de Logs (log_parser.py)

```python
parse_log_file(file_path, environment_id, last_read_position)
    Categorias: oracle, topconn, thread, ad, ssl, http, memory, shutdown, startup
    Severidades: critical, error, warning
    Retorna: alerts[], next_position
```

### 9.7 Auditoria INI (ini_auditor.py)

```python
IniAuditService.audit_ini_content(content, environment_id, user_id)
    1. Parse INI (secoes, chaves, comentarios, linhas sujas)
    2. Valida contra best_practices
    3. Calcula score (0-100)
    4. Gera LLM summary
    5. Persiste no PostgreSQL
```

### 9.8 LLM Providers (llm_providers.py)

10+ provedores via 3 adaptadores:

| Provedor | Adaptador | Modelos |
|----------|-----------|---------|
| Ollama | openai_compatible | Local (llama, mistral, etc) |
| OpenAI | openai_compatible | gpt-4o, gpt-4o-mini |
| Anthropic | anthropic | claude-sonnet, claude-haiku |
| Gemini | google | gemini-pro |
| Grok | openai_compatible | grok-* |
| DeepSeek | openai_compatible | deepseek-* |
| OpenRouter | openai_compatible | Multiplos |
| Groq | openai_compatible | llama, mixtral |
| Mistral | openai_compatible | mistral-* |
| Together | openai_compatible | Multiplos |

Retry: 3 tentativas, backoff exponencial (1s base)
Timeouts: Ollama 15s, Groq 20s, default 60s

### 9.9 TDN Scraping (tdn_ingestor.py)

```python
TDNIngestor.ingest_from_json(tree_json_path, source_name)
    1. Parse arvore JSON → lista de paginas
    2. Scrape HTML → Markdown (request_delay=1.5s, timeout=30s)
    3. Chunk conteudo (max=2500 chars, overlap=200, min=80)
    4. Persiste em tdn_pages + tdn_chunks com FTS tsvector
    5. ThreadPoolExecutor para paralelismo
```

### 9.10 Workspace (workspace_populator.py)

```python
WorkspacePopulator:
    populate_from_csv(csv_dir) → Parse SX2/SX3/SIX/SX7/SX1 CSVs
    populate_from_live_db(connection_id) → Query Protheus direto
    populate_from_hybrid(csv_dir, connection_id) → CSV + live DB
```

### 9.11 Doc Pipeline — 3 Agentes (doc_pipeline.py)

```python
DocPipeline.generate_for_module(modulo)
    Agente 1 — Dicionarista: Secoes 1-7 (analise de dicionario)
    Agente 2 — Analista de Fontes: Secoes 15-17 (analise de codigo)
    Agente 3 — Documentador: Secoes 1-19 (documento consolidado)
```

---

## 10. Frontend — Modulos e Fluxos

### 10.1 Arquitetura

- SPA (Single Page Application) com lazy loading
- Entry point: `index.html`
- Core: `api-client.js` + `integration-core.js`
- Modulos carregados sob demanda via `loadModule()`
- i18n: `static/locale/pt-BR.json` e `en-US.json`

### 10.2 Modulos JavaScript

| Modulo | Linhas | Funcao Principal |
|--------|--------|-----------------|
| `api-client.js` | 581 | Cliente HTTP central (Authorization + X-Environment-Id) |
| `integration-core.js` | 2.307 | Estado global, router, lazy loading, i18n |
| `integration-auth.js` | 1.313 | Login/logout, gestao de usuarios, primeiro acesso |
| `integration-ui.js` | 2.673 | Componentes UI: modal, notificacao, tabela, tema |
| `integration-ci-cd.js` | 1.753 | Builds, releases, logs em tempo real |
| `integration-database.js` | 4.727 | Conexoes, explorer de schema, execucao SQL |
| `integration-repositories.js` | 906 | Clone, pull, push, branches |
| `integration-source-control.js` | 774 | Status git, diffs, commits, stage/unstage |
| `integration-schedules.js` | 1.582 | Agendamentos com cron |
| `integration-pipelines.js` | 388 | CRUD de pipelines |
| `integration-commands.js` | 671 | Biblioteca de comandos |
| `integration-environments.js` | 266 | Gestao de ambientes |
| `integration-knowledge.js` | 1.139 | Base de conhecimento |
| `integration-auditor.js` | 1.019 | Auditoria INI |
| `integration-observability.js` | 740 | Dashboard, metricas, alertas |
| `integration-documentation.js` | 641 | Geracao de documentacao |
| `integration-processes.js` | 1.696 | Processos de negocio |
| `integration-agent.js` | 1.808 | Chat IA com SSE streaming |

### 10.3 Estado Global (integration-core.js)

```javascript
currentUser          // {id, username, profile, email}
userPermissions      // {users: {}, pipelines: {}, ...}
serverOS             // Tipo de SO
repositories[]       // Repositorios
pipelines[]          // Pipelines
commands[]           // Comandos
schedules[]          // Agendamentos
users[]              // Usuarios
environments[]       // Ambientes
serverVariables[]    // Variaveis
serverServices[]     // Servicos
serviceActions[]     // Acoes de servico
```

### 10.4 Fluxo de Dados

```
Browser ──AJAX──> Flask Routes ──> Services ──> Database
   ↑                                              |
   └──────────── JSON Response ────────────────────┘
```

Headers obrigatorios:
- `Authorization: <token>` — autenticacao
- `X-Environment-Id: <id>` — contexto de ambiente
- `Content-Type: application/json`

---

## 11. Seguranca e Restricoes

### 11.1 Camadas de Seguranca

| Camada | Mecanismo | Detalhes |
|--------|-----------|---------|
| Transporte | HTTPS | CSP headers, X-Frame-Options: DENY |
| Autenticacao | Session tokens | bcrypt 12 rounds |
| Rate Limiting | Por endpoint | Login: 5/5min, Git: 10-60/min |
| Input | Sanitizacao | Path traversal, Git injection, SQL injection |
| Secrets | Fernet encryption | Tokens encriptados em repouso |
| CORS | Whitelist | CORS_ALLOWED_ORIGINS |
| Audit | Logging completo | Todas as acoes de seguranca |
| RBAC | Profile-based | admin, operator, viewer |
| Protecao | Flags | Pipelines/comandos podem ser locked |

### 11.2 Sandbox do Agente

- `allowed_paths` — whitelist de caminhos acessiveis
- `blocked_commands` — blacklist de comandos bloqueados
- `max_iterations` — limite de iteracoes por mensagem
- `token_budget` — orcamento maximo de tokens
- `command_timeout` — timeout de execucao (30s padrao)
- Somente SELECT permitido em `query_database`
- Arquivos max 1MB para leitura, 100KB para escrita

### 11.3 Validators (app/utils/validators.py)

- `sanitize_path_component()` — bloqueia `..`, `./`, `\`, `$`, `;`, `|`
- `sanitize_branch_name()` — valida nomes de branch git
- `sanitize_commit_message()` — previne Git injection
- `validate_git_url()` — somente HTTPS
- `execute_git_command_safely()` — shell=False, timeout 300s

---

## 12. Fluxos de Execucao Principais

### 12.1 Chat com Agente IA

```
1. POST /api/agent/chat {messages[], temperature, max_tokens}
2. Extract: environment_id, user_profile, session_id
3. Intent Detection → (intent, confidence, entities)
4. Orchestrator Decision → single|fan_out|chain
5. Skill Loading → até 5 skills relevantes
6. Context Gathering → memoria + KB + alertas + TDN
7. System Prompt Build → specialist + skills + context
8. LLM Call → com tools filtrados por RBAC
9. Tool Parsing → tolerante a JSON/XML
10. Tool Execution → permissao + budget + fallback
11. Result Formatting → max 3000 chars
12. Response → SSE stream
13. Audit Log + History Save
```

### 12.2 Execucao de Pipeline

```
1. POST /api/pipelines/<id>/run
2. Adquire environment lock (exclusivo)
3. Cria pipeline_run (status: running)
4. Executa comandos em ordem (thread)
5. Registra logs em execution_logs
6. Atualiza status (success/failed)
7. Dispara webhooks
8. Libera environment lock
```

### 12.3 Comparacao de Dicionario

```
1. POST /api/dictionary/compare {conn_a, conn_b, company_code}
2. Conecta nos 2 bancos externos (MSSQL/Oracle/PostgreSQL)
3. Busca 13 tabelas de metadados (SX2..XAL)
4. Normaliza linhas (whitespace, NULL, BLOB, datetime)
5. Gera chave composta por tabela
6. Compara registro a registro
7. Classifica: added, removed, modified
8. Salva historico em dictionary_history
9. Retorna summary + differences[]
```

### 12.4 Equalizacao de Dicionario

```
1. POST /api/dictionary/equalize {conn_source, conn_target, operations[]}
2. Para cada operacao:
   Fase 1 (DDL): ALTER TABLE / CREATE TABLE / CREATE INDEX
   Fase 2 (DML): INSERT/UPDATE metadados SX2/SX3/SIX
   Fase 3 (Signal): UPDATE SYSTEM_INFO
   Fase 4 (TcRefresh): REST call Protheus ZATUREF
3. Tudo em transacao (rollback se falhar)
```

### 12.5 Parse e Monitoramento de Logs

```
1. Scheduler poll (60s interval)
2. Para cada log_monitor_config ativo:
   a. Le arquivo a partir de last_read_position
   b. Aplica regex patterns (14 categorias)
   c. Classifica severidade (critical/error/warning)
   d. Insere em log_alerts
   e. Atualiza last_read_position
   f. Verifica alert_rules para notificacao
   g. Dispara notificacao se threshold atingido
```

### 12.6 Auditoria de INI

```
1. POST /api/auditor/upload {ini_file}
2. Parse INI (secoes, chaves, comentarios, linhas sujas)
3. Compara cada chave vs ini_best_practices
4. Calcula score (0-100)
5. Gera LLM summary (se provedor configurado)
6. Persiste ini_audit + ini_audit_results
7. Retorna violations[], score, summary
```

### 12.7 Ingestao TDN

```
1. POST /api/tdn/ingest {json_file, source}
2. Parse arvore JSON → lista de URLs
3. Thread: para cada URL
   a. HTTP GET pagina
   b. Extract #main-content
   c. HTML → Markdown
   d. Chunk conteudo (2500 chars, 200 overlap)
   e. INSERT tdn_pages + tdn_chunks
   f. Gera tsvector para FTS
4. Atualiza tdn_scrape_runs
```

---

## 13. Integracoes Externas

### 13.1 APIs Consumidas

| Servico | Uso | Modulo |
|---------|-----|--------|
| GitHub API | Repos, branches, commits | github_integration.py |
| TDN (TOTVS) | Scrape paginas de documentacao | tdn_ingestor.py |
| Protheus REST | TcRefresh (invalidar cache) | dictionary_equalizer.py |
| SMTP | Notificacoes por email | notifier.py |
| Twilio | Notificacoes WhatsApp | notifier.py |
| LLM (10+) | Chat, classificacao, docs | llm_providers.py |

### 13.2 Bancos Externos Suportados

| Driver | Biblioteca | Uso |
|--------|-----------|-----|
| MSSQL | pymssql | Protheus principal |
| PostgreSQL | psycopg2 | Diversos |
| MySQL | pymysql | Diversos |
| Oracle | oracledb | Protheus (alternativo) |

### 13.3 Webhooks Dispatchados

Eventos que disparam webhooks:
- Pipeline started/completed/failed
- Release created/deployed
- Alert triggered
- Service action executed

Formato:
```json
{
  "event": "pipeline.completed",
  "timestamp": "2026-03-30T10:00:00Z",
  "data": { ... }
}
```

---

## 14. Referencia Rapida de Operacoes

### 14.1 Para o Agente IA: O Que Fazer Quando...

| Situacao | Tools a Usar | Ordem |
|----------|-------------|-------|
| "Erro ORA-12154 em producao" | `get_alerts` → `get_recurring_errors` → `search_knowledge` | 1→2→3 |
| "Compara HML com PRD" | `get_db_connections` → `compare_dictionary` | 1→2 |
| "Equaliza dicionario" | `preview_equalization` → (confirmacao) → `execute_equalization` | 1→2 |
| "Roda pipeline de deploy" | `get_pipelines` → `run_pipeline` | 1→2 |
| "Status dos servicos" | `get_services` | 1 |
| "Cria release" | `get_pipeline_status` → `create_release` (confirmacao) | 1→2 |
| "Audita appserver.ini" | Upload via endpoint → `get_audit_detail` | 1→2 |
| "Busca funcao ADVPL" | `search_knowledge` + TDN search | 1 |
| "Analisa impacto de campo" | `analyze_impact` → `list_vinculos` → `build_dependency_graph` | 1→2→3 |
| "Visao geral do sistema" | `get_system_overview` | 1 |

### 14.2 Chains Pre-Definidas

| Chain | Tools Encadeadas | Uso |
|-------|-----------------|-----|
| `diagnose_error` | get_alerts → get_recurring_errors → search_knowledge | Diagnostico de erro |
| `environment_health` | get_services → get_alert_summary → get_db_connections | Saude do ambiente |
| `knowledge_deep_search` | search_knowledge (5 resultados) | Busca profunda |
| `database_overview` | get_db_connections → get_alert_summary | Visao do banco |
| `setup_monitoring` | browse_log_files → list_log_monitors | Configurar monitoramento |
| `setup_database` | get_db_connections → get_environments | Configurar banco |
| `audit_overview` | get_auditor_history | Visao de auditorias |

### 14.3 Mapa de Confirmacoes Obrigatorias

Operacoes que SEMPRE exigem confirmacao do usuario antes de executar:

- `create_release` — Deploy para producao
- `execute_equalization` — Altera estrutura fisica do banco
- `execute_ingestion` — Ingere dados no dicionario
- `acknowledge_alerts_bulk` — Ack em massa
- `create_db_connection` — Nova conexao de banco
- `update_db_connection` — Altera conexao
- `delete_db_connection` — Remove conexao
- `create_log_monitor` — Novo monitor
- `update_log_monitor` — Altera monitor
- `delete_log_monitor` — Remove monitor
- `create_server_variable` — Nova variavel
- `update_server_variable` — Altera variavel
- `delete_server_variable` — Remove variavel
- `create_webhook` — Novo webhook
- `update_webhook` — Altera webhook
- `delete_webhook` — Remove webhook
- `write_file` — Escreve arquivo
- `run_command` — Executa comando shell

---

> **Nota:** Este manual cobre 150+ endpoints, 67 tools, 37 skills, 11 especialistas, 35+ tabelas e todos os fluxos de execucao do AtuDIC Supreme. Deve ser atualizado sempre que novos modulos forem adicionados ao sistema.
