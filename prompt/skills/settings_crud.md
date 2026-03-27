---
name: settings_crud
description: CRUD de variaveis de servidor e consulta de ambientes
intents: [settings_management, environment_status]
keywords: [ambiente, variavel, servidor, notificacao, configurar, criar, alterar, remover, PRD, HML, DEV, TST]
priority: 75
max_tokens: 300
specialist: settings
---

## Ambientes

Ambientes (PRD, HML, DEV) sao SOMENTE LEITURA pelo agente. Criacao/edicao/exclusao
de ambientes e restrita ao administrador root via interface grafica.

### Listar ambientes
```json
{"tool": "get_environments", "params": {}}
```

## CRUD de Variaveis de Servidor

ATENCAO: variaveis protegidas (is_protected=true) NAO podem ser alteradas
nem excluidas. O sistema retornara erro 403 se tentar.

### Criar variavel
```json
{"tool": "create_server_variable", "params": {"name": "BASE_DIR_PRD", "value": "/totvs/protheus", "environment_id": 1, "is_password": false}}
```
Campos obrigatorios: name, value, environment_id

### Atualizar variavel
```json
{"tool": "update_server_variable", "params": {"var_id": 5, "value": "/totvs/protheus_v2"}}
```

### Deletar variavel
```json
{"tool": "delete_server_variable", "params": {"var_id": 5}}
```
NAO e possivel deletar variaveis protegidas.

### Historico de alteracoes
```json
{"tool": "get_variable_history", "params": {"var_id": 5}}
```

### Notificacoes (admin only)
```json
{"tool": "update_notification_settings", "params": {"smtp_host": "smtp.gmail.com", "smtp_port": 587}}
```
