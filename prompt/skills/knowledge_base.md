---
name: knowledge_base
description: Base de conhecimento de erros e solucoes Protheus, artigos e busca
intents: [knowledge_search]
keywords: [artigo, conhecimento, KB, solucao, busca, erro, documentacao, referencia]
priority: 65
always_load: false
max_tokens: 200
specialist: knowledge
---

## Base de Conhecimento (KB)

### Artigos
- 78 artigos seed cobrindo ~60 erros Protheus documentados com causas e solucoes
- Categorias: database, thread_error, network, rpo, service, memory, authentication, etc.

### Endpoints
- `GET /api/knowledge` — Lista (filtro: category, search)
- `POST /api/knowledge` — Cria artigo (title, category, content, tags, error_pattern)
- `GET /api/knowledge/<id>` — Detalhes
- `POST /api/knowledge/import` — Importar de JSON

### Busca e Recorrencia
- `find_matching_article(category, message)` — Match por regex
- `get_recurring_errors(env_id, min_count=3, days=7)` — Erros com >= N ocorrencias
- `get_error_analysis(env_id, days=7)` — Trend: new/increasing/decreasing/stable
