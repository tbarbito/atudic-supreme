---
name: observability_crud
description: CRUD de monitores de log — criar, listar, atualizar, deletar, scan manual
intents: [error_analysis, alert_recurrence]
keywords: [monitor, log, criar monitor, scan, browse, arquivo log, alertas, observabilidade]
priority: 70
max_tokens: 300
specialist: diagnostico
---

## CRUD de Monitores de Log

### Criar monitor
```json
{"tool": "create_log_monitor", "params": {"name": "Monitor PRD", "log_file_path": "/var/log/protheus.log", "environment_id": 1, "scan_interval": 60}}
```
Campos obrigatorios: name, log_file_path, environment_id

### Listar monitores
```json
{"tool": "list_log_monitors", "params": {"environment_id": 1}}
```

### Scan manual
```json
{"tool": "scan_log_monitor", "params": {"config_id": 1}}
```

### Listar arquivos de log disponiveis
```json
{"tool": "browse_log_files", "params": {}}
```

### Alertas
- `get_alerts` — lista alertas com filtros (severity, category)
- `get_alerts_timeline` — timeline por hora para grafico
- `acknowledge_alert` / `acknowledge_alerts_bulk` — marcar como visto
