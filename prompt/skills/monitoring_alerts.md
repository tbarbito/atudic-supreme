---
name: monitoring_alerts
description: Observabilidade, monitoramento de logs, alertas, categorias de erro e recorrencia
intents: [error_analysis, alert_recurrence]
keywords: [alerta, alert, monitor, log, erro, observabilidade, recorrencia, severidade, categoria, ORA, thread, timeout]
priority: 70
always_load: false
max_tokens: 400
specialist: diagnostico
---

## Observabilidade — Monitoramento de Logs

### Categorias de Erro Protheus (15+)
| Categoria | Exemplos |
|-----------|----------|
| `database` | ORA-01017, ORA-12154, TopConnect errors |
| `thread_error` | Thread Error, Error Ending Thread |
| `network` | SSL/TLS failures, HTTP failures |
| `connection` | AD/LDAP errors, inactivity timeout |
| `rpo` | Empty RPO, compilation errors |
| `service` | Server shutdown, server already running |
| `rest_api` | REST endpoint errors |
| `memory` | OS memory failures, app memory warnings |
| `authentication` | Login failures, session expired |

### Dicas de Correcao (CORRECTION_TIPS)
50+ dicas automaticas mapeadas por categoria + regex:
- TopConnect blob length -> "Verifique campos memo e tamanho maximo"
- Array out of bounds -> "Valide com Len() antes de acessar o indice"
- ORA-01017 -> "Verifique credenciais de acesso ao Oracle"

### Endpoints
- `GET /api/log-alerts` — Lista alertas (filtros: severity, category, acknowledged)
- `GET /api/log-alerts/summary` — Resumo por tipo
- `POST /api/log-alerts/<id>/acknowledge` — Marcar como visto
- `GET /api/analysis/recurring` — Erros recorrentes (7 dias, min 3 ocorrencias)
- `GET /api/analysis/suggest/<alert_id>` — Sugestao da KB para alerta
- `GET /api/analysis/overview` — Visao geral (tendencia, distribuicao)
