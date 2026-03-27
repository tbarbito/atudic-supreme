---
name: docs_processes
description: Documentacao automatizada, processos de negocio Protheus e mapa de fluxos
intents: [knowledge_search, procedure_lookup]
keywords: [documentacao, documento, gerar, processo, fluxo, mapa, modulo, SIGAFIN, SIGACOM, SIGAFAT, SIGAMNT, SIGAFIS]
priority: 60
always_load: false
max_tokens: 300
specialist: knowledge
---

## Documentacao Automatizada

### Tipos de Documento
| Tipo | Fonte de Dados |
|------|---------------|
| `dicionario_dados` | schema_cache (tabelas + colunas + tipos) |
| `mapa_processos` | business_processes (modulos, fluxos) |
| `guia_erros` | knowledge_articles + alert_recurrence |
| `combinado` | Todos acima |

Endpoints: `POST /api/docs/generate`, `GET /api/docs`, `GET /api/docs/<id>/download`
Formato: Markdown com templates Jinja2, versionamento via parent_id.

## Processos de Negocio Protheus

### Modulos Mapeados
| Modulo | Descricao |
|--------|-----------|
| SIGAFIN | Contas a pagar/receber, bancos, fluxo de caixa |
| SIGACOM | Solicitacoes, pedidos, cotacoes |
| SIGAFAT | Vendas, PDV, notas fiscais |
| SIGAMNT | Ordens de servico, ativos |
| SIGAFIS | Livros fiscais, SPED, obrigacoes |
| SIGAEST | Saldos, movimentacoes, inventario |
| SIGACTB | Lancamentos, balancetes |

### CRUD de Processos
- `GET /api/processes` — Lista (filtros: module, status, search)
- `POST /api/processes/<id>/tables` — Vincula tabela (seletor de schema_cache)
- `GET /api/processes/flow-map` — Grafo completo para dagre.js (nodes + edges)
