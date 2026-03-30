---
name: operations_devops
description: Procedures operacionais para pipelines, releases, servicos e monitoramento
intents: [pipeline_status, service_operations, repository_operations]
keywords: [pipeline, deploy, release, servico, service, restart, start, stop, git, pull, push, clone, monitoramento, log]
priority: 75
max_tokens: 400
specialist: "devops"
---

## PROCEDURES DE DEVOPS

### Executar pipeline
1. `get_pipelines` — listar pipelines disponiveis (se nao souber o ID)
2. `run_pipeline` com pipeline_id — dispara execucao em thread
3. Acompanhar via SSE (stream-logs) ou `get_pipeline_status`

### Criar release
1. `get_pipeline_status` (pipeline_id) — verificar ultima run com sucesso
2. `create_release` (pipeline_id, run_id) — **requer confirmacao**
3. Informar: "Release criada a partir da run #{run_number}"

### Gerenciar servicos
- `get_services` — lista servicos do ambiente com status
- `execute_service_action` (action_id) — start/stop/restart
- Acoes vem pre-configuradas por servico (OS-specific: bash/powershell)

### Operacoes Git
| Operacao | Tool | Params |
|---|---|---|
| Atualizar repo | `git_pull` | repository_id, branch |
| Status | usar endpoint `/api/repositories/{id}/status` via tool | — |
| Listar branches | usar `get_repositories` | — |

### Monitoramento de logs
1. `browse_log_files` — ver arquivos de log no servidor
2. `list_log_monitors` — monitores configurados
3. `get_alerts` — alertas recentes por categoria/severidade
4. `get_recurring_errors` — erros cronicos (min 3 ocorrencias)
5. `get_alert_summary` — resumo estatistico (ultimos N dias)

### Agendamentos
- `get_schedules` — lista agendamentos ativos
- `toggle_schedule` (schedule_id) — liga/desliga
- Tipos: once, daily, weekly, monthly, cron
