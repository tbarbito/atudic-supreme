---
name: services_mgmt
description: Gerenciamento de servicos, variaveis de servidor e notificacoes (email/WhatsApp)
intents: [environment_status]
keywords: [servico, AppServer, DbAccess, variavel, notificacao, email, whatsapp, webhook, BASE_DIR, FONTES_DIR]
priority: 60
max_tokens: 300
specialist: diagnostico
---

## SERVICOS, VARIAVEIS E NOTIFICACOES

### Servicos (Windows/Linux via SSH)
- Lista: `GET /api/server-services`
- Status real-time: `GET /api/server-services/status` (systemctl/PowerShell)
- Acao: `POST /api/service-actions/{id}/execute` (start/stop/restart)

### Variaveis de servidor
- Lista: `GET /api/server-variables` (senhas mascaradas)
- Importantes: `BASE_DIR_*`, `FONTES_DIR_*`, `SSH_HOST_*`, `APPSERVER_*`, `DBACCESS_*`
- Flags: `is_protected` (nao editavel), `is_password` (mascarada)
- Use estas variaveis pra resolver paths nos ambientes

### Notificacoes
| Canal | Mecanismo |
|-------|-----------|
| Email | SMTP async, template HTML por severidade |
| WhatsApp | Webhook GET/POST, templates com `{{phone}}` e `{{message}}` |

Regras de notificacao: condicao + destinatarios + cooldown + janela de tempo

### Quando usar
- "quais variaveis do ambiente?" → listar com valores (senhas mascaradas)
- "onde ficam os fontes?" → consultar FONTES_DIR_{AMBIENTE}
- "configura notificacao" → orientar pelo modulo de Notificacoes
