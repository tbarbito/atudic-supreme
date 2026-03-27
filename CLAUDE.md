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
- **Deploy:** PyInstaller + Inno Setup (Windows), Docker (Linux)
- **Entry point:** `run.py` → http://localhost:5000

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

## Estrutura Principal

```
app/
  routes/              # Blueprints Flask (admin, dictionary, pipelines, agent, workspace, etc.)
  services/            # Logica de negocio (runner, scheduler, agent_*, dictionary_*)
  services/workspace/  # Engenharia reversa Protheus (ExtraiRPO): parsers, vinculos, knowledge
  services/tools/      # Submodulos do agente: formatters, helpers, parser
  database/            # Core DB, migrations (021+), seeds
  utils/               # Helpers (rate_limiter, crypto, logging_config, validators)
static/            # Frontend (JS lazy-loaded, CSS, locale)
prompt/            # Skills e contexto do agente IA embarcado
guia/              # Diretrizes e guidelines de engenharia
docs/              # Documentacao tecnica (ATUDIC_RESUMO, etc.)
tests/             # pytest (no .gitignore — tracked files commitam normal, novos precisam -f)
planos/            # Analises e decisoes (no .gitignore — NAO usar git add -f)
```

## Modulos Principais

### AtuDic (Dicionario Protheus)
Comparar, validar, equalizar e ingerir dicionario entre ambientes Protheus.
- Routes: `app/routes/dictionary.py`
- Services: `dictionary_compare.py`, `dictionary_equalizer.py`, `dictionary_ingestor.py`
- Schema: `protheus_metadata_schema.py`
- 13 tabelas de metadados: SX2, SX3, SIX, SX1, SX5, SX6, SX7, SX9, SXA, SXB, XXA, XAM, XAL

### Pipeline CI/CD
Orquestracao e execucao de pipelines de deploy.
- Services: `runner.py`, `scheduler.py`, `events.py`
- Webhooks: `webhook_dispatcher.py`

### Workspace — Engenharia Reversa (origem: ExtraiRPO)
Analise offline/live de ambientes Protheus: dicionario, fontes, vinculos, docs IA.
- Routes: `app/routes/workspace.py`
- Services: `app/services/workspace/` (parser_sx, parser_source, knowledge, build_vinculos, etc.)
- SQLite por workspace: 27 tabelas, 19 indices, PRAGMAs otimizadas (WAL, NORMAL)
- Modos: offline (CSV), live (DB direto), hibrido (DB + fontes filesystem)
- Pipeline docs IA: 3 agentes (dicionarista, analista_fontes, documentador) → 19 secoes
- Exporter: CSV/JSON/YAML para Protheus
- 4 tools novas: parse_source_code, analyze_impact, build_dependency_graph, list_vinculos

### Agente IA GolIAs Supreme (origem: ambos)
Assistente LLM integrado com multi-agent orchestration.
- Services: `agent_orchestrator.py`, `agent_chat.py`, `agent_skills.py`, etc.
- Submodulos: `services/tools/` (formatters, helpers, parser)
- Prompts: `prompt/skills/*.md`, `prompt/*.yml`
- 63+ tools com classificacao de risco (59 AtuDIC + 4 workspace)
- 15 specialists (9 AtuDIC + 6 ExtraiRPO)
- Retry LLM com backoff exponencial, timeout por provider
- Economia de tokens: summaries pre-computados, FTS, alert_trends
- 33+ skills categorizadas por specialist

## Banco de Dados

- Pool: `ThreadedConnectionPool` (thread-safe), config via `DB_POOL_MIN(2)`/`DB_POOL_MAX(30)`
- **CUIDADO**: `conn.close()` NAO devolve ao pool — sempre usar `release_db_connection(conn)`
- **CUIDADO**: conexoes diretas (`psycopg2.connect()`) devem usar `conn.close()`, NAO `release_db_connection()`
- Migrations: `app/database/migrations/`

## Frontend

- Lazy loading: modulos essenciais no boot, demais via `loadModule()` em `integration-core.js`
- i18n: `static/locale/pt-BR.json` e `en-US.json`, funcao `t('chave.sub')`
- Service Worker: `sw.js` na raiz
- Minificacao: `scripts/minify_assets.py`
- CSP: `unsafe-inline` necessario em script-src (scripts inline essenciais no HTML)

## Seguranca e Operacoes

- CORS restrito via `CORS_ALLOWED_ORIGINS` (env var, fallback localhost)
- Headers: CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy
- Request ID (`X-Request-ID`) em todas as requisicoes para rastreamento
- Health probes: `/api/health` (liveness), `/api/health/ready` (readiness com DB)
- Graceful shutdown: SIGTERM/SIGINT fecha scheduler, monitor e pool DB
- Rate limiter com auto-cleanup (previne memory leak)
- Logging JSON estruturado (JSONL) em app.log e errors.log
- Auto-cleanup: chat_messages >90d, audit_log >180d, alertas reconhecidos >30d
- Configuracao via `.env` (template em `.env.example`)

## Convencoes

- Comunicacao, UI, commits e docs em **portugues (pt-BR)**
- Conventional Commits: `feat()`, `fix()`, `refactor()`, `docs`, `test`, `chore`
- Encoding: UTF-8 (Python/JS/HTML), ANSI Windows-1252 (ADVPL)
- Queries parametrizadas SEMPRE
- Secrets em `.env`, nunca hardcoded — usar `TransactionContext` para DB
- Testes para funcoes publicas novas (`pytest`, `git add -f tests/`)
- Seguir principios SOLID e Clean Code

## Deploy / Build Windows

Pipeline do `build_installer.py` (6 etapas):
1. Verificar requisitos (PyArmor, PyInstaller, JS Obfuscator, Inno Setup)
2. Limpar builds anteriores
3. Minificar frontend
4. Ofuscar Python (PyArmor)
5. Ofuscar JavaScript
6. Criar executavel (PyInstaller) + instalador (Inno Setup)

**Ao adicionar arquivos novos, verificar `build_installer.py`:**
- `.py` em `app/` → automatico (PyArmor + hiddenimports)
- `.js` em `static/js/` → adicionar na lista `js_files`
- `.md` em `prompt/skills/` → automatico (copytree)
- Arquivo na raiz → adicionar em `root_files_to_copy`
- Data file (json, yml) → adicionar em `data_files_to_copy` ou no spec `datas`

## VM Windows (build/teste)

```bash
scp -o IdentitiesOnly=yes -i ~/.ssh/id_rsa_aturpo <arquivo> \
  'tiago@192.168.122.41:C:/Users/tiago/workspace/aturpo_demo/<path>/'
```

## Diretrizes CI/CD

- Preservar logica original dos artefatos — nao alterar base para evitar regressoes
- Novas implementacoes seguem padroes Python/Flask ja estabelecidos
- Interface e logs: manter padrao de emojis do sistema para leitura visual rapida

## Guias de Referencia

- `guia/DEVELOPMENT_GUIDELINES.md` — diretrizes de desenvolvimento
- `guia/AI_AGENT_ENGINEERING_GUIDELINE_v4.md` — guia de engenharia de agentes IA
- `docs/ATUDIC_RESUMO.md` — documentacao funcional do modulo AtuDic
