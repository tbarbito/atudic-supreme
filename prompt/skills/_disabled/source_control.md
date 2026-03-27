---
name: source_control
description: Repositorios Git, operacoes de branch, commit, push, pull e branch policies
intents: [general]
keywords: [git, repositorio, branch, commit, push, pull, clone, tag, github, fonte, source]
priority: 60
always_load: false
max_tokens: 300
specialist: devops
---

## Repositorios Git

### Integracao GitHub
- Config: `POST /api/github-settings` (username + token PAT, criptografado)
- Descoberta: `POST /api/github/discover` — Busca repos do usuario

### Operacoes Git
| Operacao | Endpoint | Rate Limit |
|----------|----------|-----------|
| Clone | `POST /api/repositories/<id>/clone` | 10/5min |
| Pull | `POST /api/repositories/<id>/pull` | 10/min |
| Push | `POST /api/repositories/<id>/push` | 10/min |
| Tag | `POST /api/repositories/<id>/tag` | 10/min |
| Branch | `POST /api/repositories/<id>/branch` | 10/min |

### Source Control Avancado
- `POST /api/repositories/<id>/stage` — Git add / git reset HEAD
- `POST /api/repositories/<id>/commit` — Commit (valida branch policy)
- `POST /api/repositories/<id>/push-only` — Push (injeta token, limpa URL)
- `GET /api/repositories/<id>/status` — Git status
- `GET /api/repositories/<id>/diff` — Diff uncommitted

### Branch Policies
Politicas de protecao por ambiente/repositorio/branch:
- `allow_push`, `allow_pull`, `allow_commit`, `allow_create_branch`
- Sem politica definida = operacao permitida
