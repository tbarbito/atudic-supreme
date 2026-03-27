# CLAUDE.md — AtuDIC Supreme

## Identidade

- **Produto:** AtuDIC Supreme — plataforma unificada de inteligencia Protheus
- **Repositorio:** `atudic-supreme`
- **Origem:** Merge de AtuDIC (aturpo_demo) + ExtraiRPO (protheus-extraiRPO)
- **Desenvolvedores:** Barbito (Tiago Barbieri) + Joni (Joni Praia)
- **Empresa:** Normatel / Todimo

## Stack

- **Backend:** Python 3.12+ / Flask
- **Banco Plataforma:** PostgreSQL (config, historico, agente, TDN)
- **Banco Workspace:** SQLite por workspace (dicionario, fontes, vinculos, chunks)
- **Banco Protheus:** Conexao direta (SQL Server, Oracle, PostgreSQL) via database_connections
- **Frontend:** HTML/CSS/JS vanilla com lazy loading
- **Embeddings:** Hibrido — ChromaDB (dev/Linux) ou FTS5+embeddings nativos (Windows/prod)
- **Deploy:** PyInstaller + Inno Setup (Windows), Docker (Linux)
- **Entry point:** `run.py` -> http://localhost:5000

## Comandos

```bash
# Dev
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python run.py

# Testes
python -m pytest tests/ -v --tb=short

# Build Windows (na VM)
python build_installer.py
```

## Arquitetura Hibrida (3 Camadas de Dados)

```
PostgreSQL (plataforma)     — config, users, historico, TDN 389K chunks, alertas
SQLite por workspace        — dicionario SX*, fontes, vinculos, chunks, docs IA
Conexao direta Protheus     — compare, validate, equalize, ingest (live)
```

### Principio: Cada Banco Faz o que Faz Melhor
- PostgreSQL: concorrencia, integridade, dados compartilhados
- SQLite: bulk insert rapido (WAL+NORMAL), isolamento, portabilidade
- Conexao direta: operacoes live que precisam do banco real

## Estrutura Principal

```
app/
  routes/              # Blueprints Flask
  services/            # Logica de negocio
  services/workspace/  # Parser SX, parser fontes, ingestor, vinculos, knowledge
  services/tools/      # Submodulos do agente: formatters, helpers, parser
  database/            # Core DB (PostgreSQL), migrations
  database/migrations/ # Migrations sequenciais
  utils/               # Helpers (rate_limiter, crypto, logging_config, validators)
static/                # Frontend (JS lazy-loaded, CSS, locale)
prompt/                # Skills e contexto do agente IA
  skills/              # 33+ skills .md
  specialists/         # 9+ specialists .md
memory/                # SQLite FTS5 + embeddings (agente)
templates/             # Templates HTML (Jinja2)
tests/                 # pytest
docs/                  # Documentacao tecnica
guia/                  # Diretrizes e guidelines de engenharia
```

## Modulos Principais

### Workspace (origem: ExtraiRPO)
Engenharia reversa de ambientes Protheus: parse CSV/DB, analise de fontes, vinculos.
- Services: `workspace/parser_sx.py`, `workspace/parser_source.py`
- Services: `workspace/ingestor.py`, `workspace/knowledge.py`, `workspace/build_vinculos.py`
- SQLite: 27 tabelas, 19 indices, PRAGMAs otimizadas (WAL, NORMAL, cache_size=2000)
- Modos: offline (CSV), live (DB direto), hibrido (DB + fontes filesystem)

### Dicionario Protheus (origem: AtuDIC)
Comparar, validar (19 camadas), equalizar e ingerir dicionario entre ambientes.
- Services: `dictionary_compare.py`, `dictionary_equalizer.py`, `dictionary_ingestor.py`
- 13 tabelas de metadados: SX2, SX3, SIX, SX1, SX5, SX6, SX7, SX9, SXA, SXB, XXA, XAM, XAL

### Pipeline CI/CD (origem: AtuDIC)
Orquestracao e execucao de pipelines de deploy.
- Services: `runner.py`, `scheduler.py`, `events.py`

### Agente IA GolIAs Supreme (origem: ambos)
Assistente LLM com multi-agent orchestration + engenharia reversa.
- Services: `agent_orchestrator.py`, `agent_chat.py`, `agent_skills.py`, etc.
- 63+ tools (59 AtuDIC + 4 novas do ExtraiRPO)
- 15 specialists (9 AtuDIC + 6 ExtraiRPO)
- 10+ LLM providers
- Memoria 3 tiers (semantica/episodica/procedural)

## Banco de Dados

### PostgreSQL (plataforma)
- Pool: `ThreadedConnectionPool` (thread-safe), config via `DB_POOL_MIN(2)`/`DB_POOL_MAX(30)`
- **CUIDADO**: `conn.close()` NAO devolve ao pool — sempre usar `release_db_connection(conn)`
- Migrations: `app/database/migrations/`

### SQLite por Workspace
- PRAGMAs: `journal_mode=WAL`, `synchronous=NORMAL`, `cache_size=2000`
- Encoding fontes: cp1252 fast-path (99% dos casos) → utf-8 → chardet
- Batch: 5 files commit, 100 chunks/lote, 512MB RAM max
- **CUIDADO**: WAL mode — apenas 1 writer por vez

## Frontend

- Lazy loading: modulos essenciais no boot, demais via `loadModule()`
- i18n: `static/locale/pt-BR.json` e `en-US.json`
- Mermaid.js e Highlight.js carregados sob demanda

## Seguranca

- RBAC 3 niveis: viewer/operator/admin
- CORS restrito via `CORS_ALLOWED_ORIGINS`
- Queries parametrizadas SEMPRE
- Secrets em `.env`, nunca hardcoded
- Confirmation token (SHA-256) para operacoes destrutivas
- Rate limiter com auto-cleanup

## Convencoes

- Comunicacao, UI, commits e docs em **portugues (pt-BR)**
- Conventional Commits: `feat()`, `fix()`, `refactor()`, `docs`, `test`, `chore`
- Encoding: UTF-8 (Python/JS/HTML), ANSI Windows-1252 (ADVPL)
- Testes para funcoes publicas novas (`pytest`)
- Seguir principios SOLID e Clean Code
