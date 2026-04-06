# RBAC Hibrido — Permissoes por Perfil + Overrides por Usuario

## Visao Geral

O BiizHubOps utiliza um modelo **RBAC hibrido**: cada usuario possui um **perfil base**
(admin, operator, viewer) que concede um conjunto padrao de permissoes. Alem disso,
o administrador pode criar **overrides por usuario** que adicionam (GRANT) ou removem
(DENY) permissoes individualmente.

## Perfis Base

| Perfil   | Descricao                                                    |
|----------|--------------------------------------------------------------|
| admin    | Acesso completo a gestao do sistema (users, envs, settings)  |
| operator | Operacao de pipelines, schedules, services, variaveis        |
| viewer   | Somente leitura (pipelines, repositorios, agendamentos)      |

Root admin (`username='admin'`) possui bypass total — nenhum override se aplica a ele.

## Formato de Permission Key

`resource:action` — ex: `pipelines:execute`, `users:delete`, `repositories:sync`.

O catalogo completo esta disponivel em `GET /api/permissions/catalog` (requer admin).

## Ordem de Resolucao

Quando o sistema verifica se um usuario tem uma permissao:

```
1. E root admin (username='admin')?              -> ALLOW (bypass)
2. Usuario inativo?                              -> DENY
3. Existe override DENY para este user+key?      -> DENY  (explicito)
4. Existe override GRANT para este user+key?     -> ALLOW (explicito)
5. Permissao esta no perfil base?                -> ALLOW
6. Default                                       -> DENY
```

**DENY explicito sempre vence sobre GRANT do perfil.** Isso permite revogar pontualmente
uma permissao sem trocar o perfil do usuario.

## Tabela de Overrides

```sql
user_permission_overrides
  id              SERIAL PK
  user_id         INT FK users(id) ON DELETE CASCADE
  permission_key  VARCHAR(100)     -- ex: 'pipelines:execute'
  effect          VARCHAR(10)      -- 'GRANT' ou 'DENY'
  granted_by      INT FK users(id) -- quem criou o override
  reason          TEXT             -- motivo (obrigatorio)
  expires_at      TIMESTAMP NULL   -- expirar automaticamente (opcional)
  created_at      TIMESTAMP
  UNIQUE(user_id, permission_key)
```

## API

### Catalogo
```
GET /api/permissions/catalog
→ { catalog: [{key, resource, action, description}], roles: {admin: [...], ...} }
```

### Permissoes efetivas de um usuario
```
GET /api/users/<id>/permissions
→ { user_id, username, profile, is_root, permissions, permission_keys, overrides }
```

### CRUD de overrides
```
POST   /api/users/<id>/permissions/overrides
       Body: { permission_key, effect, reason, expires_at? }

PUT    /api/users/<id>/permissions/overrides/<override_id>
       Body: { effect?, reason, expires_at? }

DELETE /api/users/<id>/permissions/overrides/<override_id>
```

### Permissoes do usuario logado
```
GET /api/me/permissions
→ { profile, username, is_root, permissions, permission_keys }
```

## Frontend

### Modal de Permissoes Detalhadas
Acessivel via botao de escudo na tabela de usuarios (Admin > Usuarios). Mostra:
- Cada recurso em accordion expansivel
- Para cada acao: status do perfil, override (se houver), permissao efetiva calculada
- Botoes GRANT / DENY / Remover override por acao

### Funcoes JavaScript
- `showPermissionOverridesModal({userId})` — abre o modal
- `setPermOverride({userId, key, effect})` — cria/atualiza override (pede motivo)
- `removePermOverride({userId, overrideId})` — remove override (volta ao perfil)

### Verificacao de permissao (backend)
```python
from app.utils.security import has_permission, require_permission

# Verificacao inline
if has_permission('pipelines:delete', user):
    ...

# Decorator em rota
@require_permission('pipelines:execute')
def run_pipeline(): ...
```

## Feature Flag

Env var `RBAC_OVERRIDES_ENABLED` (default `true`). Se definida como `false`, o sistema
ignora a tabela de overrides e usa apenas o perfil base — util para rollback emergencial.

## Exemplos de Uso

### Operator que NAO pode deletar pipelines
```json
POST /api/users/42/permissions/overrides
{
  "permission_key": "pipelines:delete",
  "effect": "DENY",
  "reason": "Restrict delete - only operates homolog"
}
```

### Viewer com acesso temporario para executar pipeline
```json
POST /api/users/55/permissions/overrides
{
  "permission_key": "pipelines:execute",
  "effect": "GRANT",
  "reason": "Temp access for release sprint",
  "expires_at": "2026-05-01T00:00:00"
}
```

## Limpeza Automatica

Overrides com `expires_at` expirado sao removidos automaticamente pelo scheduler
(ciclo de ~24h), junto com chat_messages antigos e audit_logs.
