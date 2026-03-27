---
name: devworkspace
description: Navegador de fontes AdvPL, analise de impacto, diff com repo e compilacao
intents: [general]
keywords: [fonte, fontes, AdvPL, TLPP, compilar, impacto, devworkspace, prw, tlpp, prx, navegador]
priority: 60
always_load: false
max_tokens: 300
specialist: devops
---

## Dev Workspace

### Navegacao de Fontes
- `GET /api/devworkspace/fontes` — Lista FONTES_DIR por ambiente
- `GET /api/devworkspace/browse` — Navega diretorio (protegido contra path traversal)
- `GET /api/devworkspace/file` — Le arquivo (cp1252 para AdvPL, max 2MB)
- `POST /api/devworkspace/search` — Busca em fontes (regex, com line numbers)

### Analise de Impacto
- `POST /api/devworkspace/impact` — Analisa impacto de mudanca
  - Busca tabelas referenciadas (regex S[A-Z][0-9A-Z])
  - Busca funcoes definidas (Function nome())
  - Cruza com schema_cache, business_processes, knowledge_articles
  - Calcula risk_level: baixo/medio/alto

### Diff com Repositorio
- `POST /api/devworkspace/diff` — Compara FONTES_DIR com repo clonado
  - Retorna: modificados, so_em_fontes, so_em_repo, inalterados
  - Comparacao por hash MD5

### Gerador de Compila.txt
- `POST /api/devworkspace/compila` — Gera conteudo para compilador AdvPL
