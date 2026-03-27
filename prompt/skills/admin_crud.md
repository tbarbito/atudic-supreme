---
name: admin_crud
description: CRUD de webhooks e gestao administrativa
intents: [admin_management]
keywords: [webhook, admin, rate limit, usuarios, log sistema, testar webhook]
priority: 70
max_tokens: 250
specialist: admin_ops
---

## CRUD de Webhooks

### Listar webhooks
```json
{"tool": "list_webhooks", "params": {}}
```

### Criar webhook
```json
{"tool": "create_webhook", "params": {"url": "https://exemplo.com/hook", "events": ["alert_created", "pipeline_completed"], "environment_id": 1}}
```
Campos obrigatorios: url, events, environment_id

### Atualizar webhook
```json
{"tool": "update_webhook", "params": {"webhook_id": 1, "url": "https://novo.com/hook"}}
```

### Testar webhook
```json
{"tool": "test_webhook", "params": {"webhook_id": 1}}
```

### Deletar webhook
```json
{"tool": "delete_webhook", "params": {"webhook_id": 1}}
```

## Usuarios
- `get_users` — lista usuarios com perfil e status (admin only)
