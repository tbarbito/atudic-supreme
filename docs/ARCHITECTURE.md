# Arquitetura AtuDIC Supreme

## Visao Geral

AtuDIC Supreme e o merge de dois projetos complementares:

- **AtuDIC** (Barbito) — DevOps, dicionario Protheus live, agente GolIAs
- **ExtraiRPO** (Joni) — Engenharia reversa, parser de fontes, grafo de vinculos

O resultado e uma plataforma que cobre o ciclo completo:
Descobrir -> Comparar -> Entender -> Documentar -> Corrigir -> Monitorar

## Arquitetura Hibrida de Dados

### Por que 3 bancos?

| Banco | Uso | Justificativa |
|-------|-----|---------------|
| **PostgreSQL** | Plataforma (config, users, TDN, alertas) | Concorrencia, ACID, 389K chunks TDN |
| **SQLite** | Workspace (dicionario, fontes, vinculos) | Bulk insert 3-5x mais rapido, isolamento |
| **Conexao direta** | Protheus live (compare, equalize) | Operacoes que PRECISAM do banco real |

### Performance: Por que SQLite para Workspace?

O ExtraiRPO processa 1987 arquivos em 2.8s com SQLite porque:
- In-process (zero latencia de rede)
- WAL mode (write-ahead logging) para concorrencia leitura/escrita
- PRAGMA synchronous=NORMAL (menos fsync)
- PRAGMA cache_size=2000 (paginas em memoria)
- Batch insert com executemany (5 files/commit)

Migrar para PostgreSQL adicionaria:
- ~2-5ms por query (latencia rede)
- Overhead de pool/conexao
- Complexidade de transacao distribuida

**Decisao: manter SQLite para workspace. Performance > uniformidade.**

### Diagrama de Fluxo

```
┌──────────────────────────────────────────────────────────────┐
│                    ATUDIC SUPREME                             │
│                                                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │ PostgreSQL   │  │ SQLite/WS   │  │ Protheus DB (live)  │ │
│  │              │  │              │  │                     │ │
│  │ - users      │  │ - tabelas    │  │ - SX2010, SX3010   │ │
│  │ - settings   │  │ - campos     │  │ - TOP_FIELD         │ │
│  │ - TDN chunks │  │ - fontes     │  │ - SYSTEM_INFO       │ │
│  │ - alertas    │  │ - vinculos   │  │                     │ │
│  │ - pipelines  │  │ - chunks     │  │ Compare/Validate    │ │
│  │ - audit_log  │  │ - docs IA    │  │ Equalize/Ingest     │ │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬──────────┘ │
│         │                 │                      │            │
│         └─────────────────┼──────────────────────┘            │
│                           │                                   │
│                    ┌──────▼───────┐                           │
│                    │  GolIAs      │                           │
│                    │  Supreme     │                           │
│                    │              │                           │
│                    │  63+ tools   │                           │
│                    │  15 specs    │                           │
│                    │  10+ LLMs    │                           │
│                    └──────────────┘                           │
└──────────────────────────────────────────────────────────────┘
```

## Workspace: 3 Modos de Alimentacao

### Modo Offline (CSV)
Consultor exporta CSVs do Protheus (SX2, SX3, SIX...) + copia fontes .prw/.tlpp.
Parser le CSVs e popula SQLite. Funciona sem rede.

### Modo Live (DB direto)
AtuDIC conecta ao banco Protheus via database_connections.
Le SX* diretamente e popula SQLite. Sem CSV intermediario.

### Modo Hibrido (DB + Fontes)
Dicionario vem do banco (live). Fontes vem do filesystem.
Melhor dos dois mundos — dicionario sempre atualizado, fontes analisadas localmente.

## Agente GolIAs Supreme

### Evolucao

| Origem | Contribuicao |
|--------|-------------|
| GolIAs (AtuDIC) | Orquestracao multi-agente, 59 tools, 33 skills, RBAC, memoria 3 tiers |
| ExtraiRPO | 6 agentes especializados, parser fontes, grafo vinculos, analise impacto |

### Novas Tools (vindas do ExtraiRPO)

| Tool | Funcao | Risco |
|------|--------|-------|
| `parse_source_code` | Analisa arquivo ADVPL/TLPP (funcoes, tabelas, PEs) | low |
| `analyze_impact` | Impacto de alterar campo/tabela (fontes afetadas) | low |
| `build_dependency_graph` | Grafo de vinculos de um modulo | low |
| `list_vinculos` | Lista relacoes campo->funcao->gatilho->PE | low |

### Novos Specialists (vindos do ExtraiRPO)

| Specialist | Dominio | Origem |
|-----------|---------|--------|
| dicionarista | Analise estrutura SX3/SIX/SX7 | ExtraiRPO |
| analista_fontes | Dissecacao de codigo ADVPL/TLPP | ExtraiRPO |
| documentador | Geracao de docs (19 secoes + Mermaid) | ExtraiRPO |
| campo_agent | Alteracoes em campos SX3 | ExtraiRPO |
| bug_agent | Diagnostico de erros ADVPL | ExtraiRPO |
| projeto_agent | Analise de novas funcionalidades | ExtraiRPO |

## Plano de Implementacao

### Fase 1 — Fundacao (2-3 semanas)
- Estrutura workspace SQLite
- Portar parsers (parser_sx, parser_source)
- Portar knowledge + build_vinculos
- WorkspacePopulator (DB direto -> SQLite)
- Rotas Flask basicas

### Fase 2 — Frontend Workspace (2-3 semanas)
- Aba Workspace no menu
- Modulo Setup (CSV ou conexao DB)
- Modulo Explorer (tree, tabela, diff)
- Dashboard com stats

### Fase 3 — Agentes Unificados (2-3 semanas)
- 4 novas tools no GolIAs
- 6 novos specialists
- Adapter LiteLLM -> llm_providers
- Portar prompts para skills .md

### Fase 4 — Docs IA + Polish (1-2 semanas)
- Pipeline docs IA (3 agentes)
- Export AtuDic (YAML/CSV)
- Testes de integracao
- Build installer check

## Decisoes Arquiteturais

### ADR-001: SQLite para Workspace (nao PostgreSQL)
**Contexto:** ExtraiRPO usa SQLite com performance excelente.
**Decisao:** Manter SQLite por workspace.
**Motivo:** Bulk insert 3-5x mais rapido, isolamento natural, portabilidade.
**Consequencia:** 2 bancos para gerenciar (PG + SQLite), mas com dominios claros.

### ADR-002: ChromaDB opcional (Adapter pattern)
**Contexto:** ChromaDB funciona bem mas e problematico no PyInstaller.
**Decisao:** Adapter WorkspaceVectorStore com 2 backends.
**Motivo:** ChromaDB para dev/Linux, FTS5+embeddings para Windows/prod.
**Consequencia:** Busca semantica funciona em ambos ambientes.

### ADR-003: LLM via llm_providers (nao LiteLLM)
**Contexto:** ExtraiRPO usa LiteLLM (2 providers). AtuDIC tem llm_providers (10+).
**Decisao:** Usar llm_providers.py do AtuDIC como base.
**Motivo:** Mais providers, retry com backoff, timeouts por provider, streaming.
**Consequencia:** Agentes ExtraiRPO precisam de adapter para nova interface.

### ADR-004: Frontend Vanilla JS (nao Vue)
**Contexto:** ExtraiRPO usa Vue 3 + PrimeVue. AtuDIC usa vanilla JS.
**Decisao:** Converter components para vanilla JS (lazy-loaded).
**Motivo:** Build unico, sem node/npm em producao, menor tamanho.
**Consequencia:** Perda de reatividade Vue, compensada com JS modular.
