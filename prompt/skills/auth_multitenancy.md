---
name: auth_multitenancy
description: Perfis de usuario, autenticacao, API keys e ambientes multi-tenancy
intents: [user_context, environment_status]
keywords: [perfil, admin, operator, viewer, login, autenticacao, ambiente, PRD, HML, DEV, TST, API key, sessao, token]
priority: 70
always_load: false
max_tokens: 300
specialist: general
---

## Autenticacao e Autorizacao

### Perfis de Usuario
| Perfil | Permissoes |
|--------|-----------|
| **admin** | Acesso total: usuarios, configuracoes, webhooks, licenca, DB, dicionario |
| **operator** | CI/CD, repositorios, servicos, variaveis, RPO, agendamentos |
| **viewer** | Somente leitura na maioria dos modulos |

### Decorators: `@require_auth`, `@require_admin`, `@require_operator`, `@require_api_key`

### Endpoints de Auth
- `POST /api/login` — Login (rate: 5/5min, retorna session_token hex 64)
- `POST /api/logout` — Logout
- `POST /api/session/keep-alive` — Keep-alive
- API Keys: formato `at_` + 48 hex, header `x-api-key` ou `Authorization: Bearer`

## Ambientes (Multi-Tenancy)

Todo request deve incluir header `X-Environment-Id`.

| ID | Nome | Descricao |
|----|------|-----------|
| 1 | Producao | Ambiente produtivo |
| 2 | Homologacao | Testes e validacao |
| 3 | Desenvolvimento | Desenvolvimento |
| 4 | Testes | Testes automatizados |

Variaveis por ambiente: sufixo `_PRD`, `_HOM`, `_DEV`, `_TST` (ex: `BASE_DIR_PRD`, `FONTES_DIR_HOM`)
