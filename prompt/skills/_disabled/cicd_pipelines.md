---
name: cicd_pipelines
description: Pipelines CI/CD, commands, execucao, releases, agendamentos e variaveis
intents: [pipeline_status]
keywords: [pipeline, build, deploy, compilar, release, command, schedule, agendamento, cron, run, execucao]
priority: 70
always_load: false
max_tokens: 500
specialist: devops
---

## Pipelines CI/CD

### Conceitos
- **Pipeline** = Sequencia ordenada de commands (build) + optional deploy command
- **Command** = Script reutilizavel (bash/powershell/python/nodejs/docker)
- **Run** = Execucao de um pipeline (logs em tempo real)
- **Release** = Deploy a partir de run bem-sucedido

### Ciclo: Criar Pipeline -> Associar Commands -> Executar Run -> [Sucesso] -> Criar Release

### Endpoints principais
- `GET /api/pipelines` — Lista (requer X-Environment-Id)
- `POST /api/pipelines/<id>/run` — Dispara execucao (async, retorna run_id)
- `GET /api/pipelines/<id>/runs` — Historico (paginado)
- `GET /api/runs/<run_id>/logs` — Logs do banco
- `POST /api/runs/<run_id>/release` — Cria release de run bem-sucedido

### Variaveis no Pipeline
- Substituicao: `${VAR_NAME}` nos scripts dos commands
- Senhas mascaradas nos logs como `********`
- Scripts PowerShell: .ps1 temporario com UTF-8 BOM
- Scripts Bash: execucao direta com shell=True

## Commands (Templates de Script)

| Tipo | Uso |
|------|-----|
| bash | Linux (compilacao, SSH, git) |
| powershell | Windows (servicos, APatcher) |
| python | Automacao cross-platform |

Scripts padrao: `apply_patch.ps1`, `compile_sources.ps1`, `hot_swap_rpo.sh`

## Agendamentos (Schedules)

| Tipo | Configuracao |
|------|-------------|
| `once` | Data e hora especificas |
| `daily` | Hora fixa |
| `weekly` | Dia da semana + hora |
| `monthly` | Dia do mes + hora |
| `cron` | Expressao cron padrao |

Endpoints: `GET/POST/PUT /api/schedules`, `PATCH /api/schedules/<id>/toggle`
