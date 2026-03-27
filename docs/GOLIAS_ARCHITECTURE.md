# GolIAs — Arquitetura e Engenharia do Agente Orquestrador

> Documento tecnico completo do agente inteligente GolIAs, parte da plataforma AtuDIC.
> Versao: 2026-03-27 | Autor: Barbito + Claude Opus 4.6

---

## 1. Identidade

O **GolIAs** (Agente Orquestrador) e o motor de inteligencia artificial embarcado do AtuDIC. Ele **nao e um chatbot** — e um terminal inteligente humanizado que recebe comandos em linguagem natural, traduz em acoes concretas, orquestra ferramentas e entrega resultados validados.

**Principio central:** Se uma tarefa pode ser executada, execute. Se precisa de aprovacao, peca UMA VEZ. Nunca peca permissao para pensar.

---

## 2. Arquitetura Geral

```
Mensagem do Usuario
    |
    v
+-----------------------------------------------------------+
|  CAMADA DE PERCEPCAO                                       |
|  - Intent Detection (regex 4-fases + LLM fallback)        |
|  - Entity Extraction (tabelas, campos, rotinas, erros)     |
|  - ProtheusIntelligence (grafo de conhecimento, zero-LLM)  |
+-----------------------------------------------------------+
    |
    v
+-----------------------------------------------------------+
|  CAMADA DE CONTEXTO                                        |
|  - Memoria Hibrida (BM25 + embeddings via SQLite FTS5)     |
|  - Base TDN (389K+ chunks via PostgreSQL tsvector)          |
|  - Sinonimos Protheus (55+ mapeamentos)                    |
|  - KB Articles, Alertas, Pipelines, Ambientes              |
|  - Working Memory (sessao, entidades, decisoes)            |
+-----------------------------------------------------------+
    |
    v
+-----------------------------------------------------------+
|  CAMADA DE DECISAO (Mode Selector — 5 tiers)               |
|                                                             |
|  Tier 1: Multi-Agent Orchestration (fan_out / chain)        |
|  Tier 2: Single Sub-Agent Dispatch (specialist autonomo)    |
|  Tier 3: Legacy (two-step / ReAct / plan-execute)           |
|  Tier 4: Chain Execution (sequencias pre-definidas)         |
|  Tier 5: Rule-based (sem LLM)                              |
+-----------------------------------------------------------+
    |
    v
+-----------------------------------------------------------+
|  CAMADA DE EXECUCAO                                        |
|  - 60 ferramentas com RBAC (viewer < operator < admin)     |
|  - Fallback chains automaticos                             |
|  - Confirmacao para acoes destrutivas                       |
|  - Token budget por sub-agente (15K default)               |
+-----------------------------------------------------------+
    |
    v
+-----------------------------------------------------------+
|  CAMADA DE ENTREGA                                         |
|  - Formatacao markdown estruturada                         |
|  - Citacao de fontes (KB, TDN, alertas)                    |
|  - SSE streaming para UI em tempo real                     |
|  - Auditoria de tokens em agent_audit_log                  |
+-----------------------------------------------------------+
```

---

## 3. Camada de Percepcao

### 3.1 Intent Detection (`agent_intent.py`)

Classificador de intencao em 4 fases cascata:

| Fase | Metodo | Confianca | Custo |
|------|--------|-----------|-------|
| 1 | Regex patterns (14 intents) | 0.90 | Zero |
| 2 | Keyword scoring | 0.55–0.80 | Zero |
| 3 | LLM fallback (se conf < 0.68) | 0.70–0.90 | ~200 tokens |
| 4 | Default "general" | 0.30 | Zero |

**14 Intents registrados:** `user_context`, `error_analysis`, `alert_recurrence`, `ini_audit`, `service_operations`, `pipeline_status`, `table_info`, `environment_status`, `procedure_lookup`, `settings_management`, `admin_management`, `repository_operations`, `schedule_management`, `knowledge_search`.

### 3.2 Entity Extraction (`agent_intent.py`)

Extrai automaticamente da mensagem:
- Codigos de erro Oracle (ORA-NNNNN)
- Tabelas Protheus (SA1, SB1, SC5, etc.)
- Tabelas SX de metadados (SX2, SX3, SIX)
- Nomes de campos (A1_COD, B1_DESC, etc.)
- Funcoes AdvPL (FWBrowse, MsExecAuto, etc.)

### 3.3 ProtheusIntelligence (`tdn_intelligence.py`)

Motor de inteligencia semantica que funciona **sem LLM** — toda a cognição esta em regras e grafos de conhecimento.

**Grafo de conhecimento:**
- 9 modulos Protheus completamente mapeados (SIGAFAT, SIGAFIN, SIGACOM, SIGAEST, SIGAFIS, SIGAMNT, SIGACTB, SIGAGPE, SIGALOJA)
- Cada modulo com: aliases coloquiais, tabelas principais, rotinas, conceitos de negocio
- 10 tabelas SX com descricoes
- 10 patterns de linguagem coloquial → intencao tecnica

**Pipeline de analise:**
1. Detectar modulos (lookup reverso: termo → modulo)
2. Detectar tabelas (regex + dicionario SX)
3. Detectar rotinas (MATA410, FINA040, etc.)
4. Detectar conceitos de negocio ("nota fiscal de saida", "pedido de venda")
5. Classificar intencao Protheus (module_info, table_info, procedure_info, etc.)
6. Gerar queries otimizadas para busca TDN (multiplas, combinando termos tecnicos)
7. Gerar context hint para orientar o LLM

**Exemplo:**
```
Entrada: "resuma o que faz o modulo sigafat"
Saida:
  - Modulos: [SIGAFAT]
  - Intent: module_info
  - Queries: ["SIGAFAT Faturamento MATA410 MATA460 MATA461"]
  - Hint: "Modulo SIGAFAT (Faturamento): tabelas [SC5,SC6,SD2,SF2], rotinas [MATA410,MATA460]"
```

---

## 4. Camada de Contexto

### 4.1 Memoria do Agente (`agent_memory.py`)

Sistema de memoria persistente em 3 camadas:

| Camada | Fonte | Tipo | Uso |
|--------|-------|------|-----|
| Semantica | MEMORY.md, TDN .md | Conhecimento conceitual | Referencia Protheus, arquitetura |
| Procedural | TOOLS.md | Procedimentos operacionais | Passo a passo de tarefas |
| Episodica | logs/*.md | Registros operacionais | Historico de operacoes |

**Busca hibrida (BM25 + Embeddings):**
1. BM25 via SQLite FTS5 (tokenizer unicode61, accent-insensitive)
2. Embeddings via LLM provider (cosine similarity)
3. Merge via **Reciprocal Rank Fusion (RRF)**
4. Fallback para BM25 puro se provider nao suporta embeddings

**Armazenamento:**
- Fonte da verdade: arquivos `.md` em `memory/`
- Indice de busca: SQLite `memory.db` (WAL mode, thread-safe)
- Chunking: max 3500 chars, overlap 500 chars, split por headings

### 4.2 Base de Conhecimento TDN (`tdn_ingestor.py`)

Base com **389.000+ chunks** de documentacao oficial TOTVS, armazenada em PostgreSQL.

| Fonte | Paginas | Chunks |
|-------|---------|--------|
| Framework | 4.177 | 52.102 |
| TOTVSTEC | 1.759 | 30.535 |
| TLPP | 360 | 2.695 |
| TSS | 78 | 809 |
| ADVPL | 3 | 623 |
| Protheus 12 | 12.387 | 302.603 |
| **Total** | **18.764** | **389.367** |

**Busca multi-estrategia:**
1. tsvector FTS (portugues, com ranking)
2. Busca por titulo (section_title + page_title)
3. Fallback ILIKE (termos com 4+ caracteres)
4. Deduplicacao por chunk_id

### 4.3 Sinonimos Protheus (`tdn_synonyms.py`)

Dicionario bidirecional com 55+ mapeamentos:
- Coloquial → tecnico: "cliente" → SA1, MATA030, CRMA980
- Tecnico → coloquial: SA1 → "cliente"
- Expansao de query: "cadastro de cliente" → "cadastro de cliente SA1 MATA030 CRMA980"

### 4.4 Working Memory (`agent_working_memory.py`)

Memoria de sessao (transiente, nao persistida):
- Entidades acumuladas (max 30)
- Decisoes do agente (max 10)
- Resultados de ferramentas (max 15, resumos de 300 chars)
- Plano ativo de orquestracao
- Renderizado como bloco markdown (~200-500 tokens) no prompt

### 4.5 Montagem do Contexto (`agent_context.py`)

O `ContextBuilder` monta o contexto em ordem de prioridade:

1. **Protheus Hint** (grafo de conhecimento — ~100 tokens)
2. **Memoria do Agente** (BM25/embeddings — ~300 tokens)
3. **KB Articles** (artigos da base de conhecimento)
4. **Alert Trends** (view materializada — ~200 tokens vs ~2000 bruto)
5. **Alertas brutos** (fallback se view nao existe)
6. **Pipelines recentes**
7. **Dicionario SX2** (tabelas Protheus)
8. **Documentacao TDN** (ate 5 chunks x 600 chars = ~3000 tokens)
9. **Ambientes**
10. **Dados de chain** (resultados de execucoes encadeadas)

---

## 5. Camada de Decisao

### 5.1 Mode Selector (`agent_chat.py`)

Cascata de 5 niveis que decide o modo de execucao:

```
Mensagem
  |
  v
[LLM disponivel?]
  |--- NAO → Rule-based (ResponseComposer)
  |--- SIM
        |
        v
      [Modelo capaz?] (Claude, GPT-4, DeepSeek)
        |--- NAO → Legacy fallback
        |--- SIM
              |
              v
            [Multi-dominio?] (2+ dominios detectados)
              |--- SIM → Orchestrator (fan_out ou chain)
              |--- NAO
                    |
                    v
                  [Specialist com agent_enabled?]
                    |--- SIM → Sub-Agent Dispatch
                    |--- NAO → Legacy fallback
```

### 5.2 Orquestrador (`agent_orchestrator.py`)

3 padroes de orquestracao:

| Padrao | Quando | Exemplo |
|--------|--------|---------|
| **Single** | 1 dominio detectado | "compare o SX6 entre HML e PRD" → database |
| **Fan-out** | 2+ dominios independentes | "status dos pipelines e alertas criticos" → devops + diagnostico |
| **Chain** | 2+ dominios sequenciais | "analise os erros e sugira correcao" → diagnostico → knowledge |

**Deteccao de dominios:** keyword scoring contra 8 dominios (diagnostico, database, auditor, settings, admin_ops, devops, knowledge, general). Keywords incluem termos Protheus especificos (SIGAFAT, SA1, MATA410, etc.).

**Fallback chain:** se um agente falha, tenta agente alternativo:
- diagnostico → knowledge
- database → knowledge
- devops → diagnostico
- settings → admin_ops

### 5.3 Sub-Agente (`agent_base.py`)

Cada sub-agente e uma instancia de `BaseSpecialistAgent`:
- Prompt customizado carregado de `prompt/specialists/<name>.md`
- Ferramentas filtradas por RBAC e allowlist do specialist
- Token budget dedicado (default 15K, configuravel)
- Loop ReAct autonomo (max 5 iteracoes)
- Formato de tool call: JSON `{"tool": "nome", "params": {...}}` (provider-agnostic)

**9 Specialists registrados:**

| Specialist | Dominio | agent_enabled | Budget | Max Iter | Tools |
|-----------|---------|---------------|--------|----------|-------|
| diagnostico | Erros, alertas, logs | Sim | 20K | 6 | 14 |
| database | Banco, dicionario, SQL | Sim | 35K | 8 | 17 |
| devops | Pipelines, servicos, git | Sim | 30K | 8 | 11 |
| knowledge | Base TDN, KB, procedimentos | Sim | 12K | 5 | 1 |
| settings | Ambientes, variaveis | Sim | 15K | 6 | 6 |
| admin_ops | Webhooks, usuarios | Sim | 15K | 6 | 6 |
| auditor | Auditoria INI | Nao | 15K | 6 | 6 |
| general | Fallback cross-domain | Nao | 20K | 6 | 16 |
| proactive | Monitoramento autonomo | Sim | 15K | 6 | 4 |

### 5.4 Skills (`agent_skills.py`)

Sistema de injecao modular de prompts baseado em contexto:
- 27+ skills ativas em `prompt/skills/*.md`
- Selecionadas por: specialist match (+15), intent match (+10), keyword match (+2/kw)
- Budget: max 5 skills, max 4000 tokens por request
- `quick_response` e a unica skill `always_load` (regras de formatacao)

---

## 6. Camada de Execucao

### 6.1 Ferramentas (`agent_tools.py`)

**60 ferramentas** registradas em 13 categorias:

| Categoria | Qtd | Exemplos |
|-----------|-----|----------|
| Ambientes e Config | 6 | get_environments, create/update/delete_server_variable |
| Monitoramento | 6 | get_alerts, get_alert_summary, acknowledge_alert |
| Log Monitors | 4 | list_log_monitors, scan_log_monitor, browse_log_files |
| Pipelines CI/CD | 3 | get_pipelines, get_pipeline_status, run_pipeline |
| Servicos | 2 | get_services, execute_service_action |
| Repositorios | 2 | get_repositories, git_pull |
| Banco de Dados | 7 | query_database, discover_db_schema, create/update/delete_db_connection |
| Dicionario | 6 | compare_dictionaries, validate_dictionary, preview/execute_equalization |
| Knowledge Base | 1 | search_knowledge |
| Admin | 6 | get_users, list/create/update/delete/test_webhook |
| Auditor | 3 | get_auditor_history, get_audit_detail |
| Ingestao | 3 | upload_ingest_file, preview/execute_ingestion |
| Sistema | 5+ | read_file, list_directory, search_files, run_command |

**RBAC:** 3 perfis (viewer < operator < admin). Cada ferramenta tem `min_profile` definido.

**Fallback Map:** se uma ferramenta falha, tenta alternativa:
- get_alerts → search_knowledge
- get_alert_summary → get_alerts
- query_database → search_knowledge
- get_services → get_environments

### 6.2 Acoes Destrutivas

Ferramentas com `requires_confirmation=True` usam protocolo de dupla confirmacao:
1. `preview_equalization` retorna `confirmation_token`
2. Usuario confirma
3. `execute_equalization` recebe o token
4. Acao executada

---

## 7. Provedores LLM (`llm_providers.py`)

### 7.1 Providers Suportados

| Provider | Adaptador | Modelo Default | Vision | Timeout |
|----------|-----------|----------------|--------|---------|
| Ollama | openai_compatible | llama3.2:3b | Nao | 15s |
| OpenAI | openai_compatible | gpt-4o-mini | Sim | 60s |
| Anthropic | anthropic | claude-sonnet-4 | Sim | 60s |
| Google Gemini | google | gemini-2.0-flash | Sim | 90s |
| xAI Grok | openai_compatible | grok-3-mini | Sim | 60s |
| DeepSeek | openai_compatible | deepseek-chat | Nao | 60s |
| OpenRouter | openai_compatible | llama-3.1-8b | Nao | 75s |
| Groq | openai_compatible | llama-3.3-70b | Nao | 20s |
| Mistral | openai_compatible | mistral-small | Nao | 60s |
| Together | openai_compatible | Llama-3.2-3B | Nao | 60s |

### 7.2 Adaptadores

- **openai_compatible:** cobre 7 de 10 providers via API OpenAI-compatible
- **anthropic:** API nativa Anthropic Messages
- **google:** API Gemini generateContent

**Sem dependencias de SDK** — implementado apenas com `requests`.

### 7.3 Retry e Resiliencia

- Max 3 tentativas com backoff exponencial (1s, 3s, 7s) + jitter
- Retenta: timeout, rate_limit, server_error (inclui HTTP 529 Overloaded)
- Nao retenta: auth_error, api_error (erros de request malformado)

---

## 8. System Prompt (`ATUDIC_AGENT_CONTEXT_CORE.md`)

### 8.1 Principios

1. **Foco na Acao** — "Quais ferramentas aciono?" nunca "como explico?"
2. **Precisao Cirurgica** — primeira frase = resposta ou acao
3. **Pensamento ReAct** — Reason → Act → Observe
4. **Autonomia Supervisionada** — resolve erros previsiveis sozinho
5. **Economia de Tokens** — denso, nao verboso

### 8.2 Protocolo de Execucao (5 fases)

1. INTAKE — compreender intencao, perguntar UMA VEZ se necessario
2. PLANO — simples: executar direto; complexas: documentar plano
3. EXECUCAO — ferramentas na ordem correta
4. VALIDACAO — resultado faz sentido?
5. REPORTE — resultado estruturado em markdown

### 8.3 Regras Absolutas

1. USE ferramentas — nunca invente dados
2. Cite fontes ("Conexao #1", "KB artigo #45", URL TDN)
3. Nunca exponha senhas/tokens/chaves
4. Estruture com markdown
5. Uma ferramenta por vez
6. Verifique idempotencia antes de modificar estado
7. Nunca diga "nao tenho acesso" se a ferramenta existe
8. Nunca fabrique respostas baseadas em inferencia

### 8.4 Base TDN no Prompt

O prompt instrui explicitamente o GolIAs sobre a base TDN:
- 389.000+ chunks de documentacao oficial TOTVS
- Cobre todos os modulos Protheus, AdvPL/TLPP, Framework MVC, REST, TSS
- Quando dados TDN aparecem no contexto, DEVE usa-los como base factual
- Citar fontes (URL TDN) sempre que disponivel

---

## 9. Vantagens da Arquitetura

### 9.1 Independencia de LLM
- Tool calling via JSON generico (nao depende de function calling nativo)
- ProtheusIntelligence funciona sem LLM (zero-cost, zero-latency)
- 10 providers suportados, troca a quente via UI
- Fallback automatico para modo rule-based sem LLM

### 9.2 Discernimento Protheus
- Grafo de conhecimento com 9 modulos, 70+ tabelas, 60+ rotinas mapeadas
- Sinonimos bidirecionais (coloquial ↔ tecnico)
- 389K chunks de documentacao oficial TDN pesquisaveis por full-text
- Busca multi-estrategia (tsvector + titulo + ILIKE)

### 9.3 Resiliencia
- 5 tiers de fallback na decisao (orchestrator → agent → legacy → chain → rule-based)
- Retry com backoff exponencial para erros transientes de LLM
- Fallback chain entre ferramentas (get_alerts → search_knowledge)
- Replanejamento automatico quando sub-agente falha
- Checkpoint/resume no scraping TDN

### 9.4 Seguranca
- RBAC em 3 niveis (viewer/operator/admin) em todas as ferramentas
- Dupla confirmacao para acoes destrutivas (confirmation_token)
- environment_id injetado no prompt para evitar fabricacao
- Zona vermelha para DELETE em massa, force push, alteracoes em producao
- Nunca expoe senhas, tokens ou connection strings

### 9.5 Economia de Tokens
- Skills injetadas por relevancia (max 4K tokens, nao 53K)
- Alert trends via view materializada (~200 tokens vs ~2000)
- Context hint do grafo (~100 tokens vs busca completa)
- Working memory compacta (~200-500 tokens)
- Token budget por sub-agente (evita runaway)

### 9.6 Extensibilidade
- Adicionar modulo Protheus: 1 entrada em `PROTHEUS_MODULES`
- Adicionar ferramenta: `register_tool()` + handler
- Adicionar skill: criar `.md` em `prompt/skills/`
- Adicionar provider LLM: 1 entrada em `PROVIDERS`
- Adicionar fonte TDN: `POST /api/tdn/ingest` ou `crawl_and_ingest.py`

---

## 10. Desvantagens e Limitacoes

### 10.1 Intent Detection por Regex
A deteccao de intencao usa regex e keywords — funciona bem para padroes comuns mas pode falhar em linguagem muito coloquial ou ambigua. O fallback LLM mitiga parcialmente, mas adiciona latencia e custo.

### 10.2 Orquestracao Sequencial
O fan-out do orquestrador executa sub-agentes **sequencialmente** (nao em paralelo) devido a limitacoes do contexto Flask. Em tarefas multi-dominio, isso adiciona latencia proporcional ao numero de agentes.

### 10.3 Dependencia de Qualidade do LLM
Apesar da camada de inteligencia Protheus, a qualidade final da resposta depende do LLM escolhido. Modelos menores (Ollama local, llama3.2:3b) produzem respostas significativamente piores que Claude ou GPT-4.

### 10.4 TDN Chunks Estaticos
A base TDN e uma foto do momento do scraping. Se a TOTVS atualizar documentacao no TDN, os chunks locais ficam desatualizados. Necessita re-scraping periodico.

### 10.5 Sem Embeddings Vetoriais na Busca TDN
A busca TDN usa tsvector (keyword-based) — nao tem busca semantica por embeddings. Perguntas semanticamente similares mas lexicamente diferentes podem nao encontrar chunks relevantes. O fallback ILIKE e a ProtheusIntelligence mitigam parcialmente.

### 10.6 Grafo de Conhecimento Manual
O `PROTHEUS_MODULES` e mantido manualmente. Novos modulos, rotinas ou conceitos precisam ser adicionados no codigo. Nao ha aprendizado automatico.

### 10.7 Token Budget Fixo
O budget de tokens por sub-agente e fixo (configuravel mas nao adaptativo). Tarefas mais complexas podem esgotar o budget antes de concluir, resultando em escalonamento.

---

## 11. Fluxo Completo — Exemplo

**Mensagem:** "resuma o que faz o modulo SIGAFAT"

```
1. PERCEPCAO
   - Intent: knowledge_search (conf: 0.75)
   - Entities: {table_names: [], routines: []}
   - ProtheusIntelligence:
     - Modulos: [SIGAFAT]
     - Intent: module_info
     - Queries: ["SIGAFAT Faturamento MATA410 MATA460 MATA461"]
     - Hint: "Modulo SIGAFAT (Faturamento): tabelas [SC5,SC6,SD2,SF2]"

2. CONTEXTO
   - Protheus Hint: "Modulo SIGAFAT (Faturamento)..."
   - Memoria: 2 chunks sobre faturamento
   - TDN: 5 chunks (Pedido de Venda MATA410, NF Saida MATA460, etc.)
   - Skills: tdn_protheus_dictionary, protheus_structure

3. DECISAO
   - Mode: Sub-Agent Dispatch → knowledge specialist
   - Budget: 12K tokens

4. EXECUCAO
   - Sub-agente knowledge recebe context_text com TDN chunks
   - Nao precisa chamar ferramentas (contexto ja tem a informacao)
   - Responde direto com base nos dados TDN

5. ENTREGA
   - Resposta estruturada com informacoes do SIGAFAT
   - Cita fontes TDN (URLs)
   - ~150 tokens de resposta
```

---

## 12. Stack Tecnica

| Componente | Tecnologia |
|-----------|------------|
| Backend | Python 3.12+ / Flask |
| Banco principal | PostgreSQL (pool ThreadedConnectionPool) |
| Memoria agente | SQLite + FTS5 (WAL mode) |
| Busca TDN | PostgreSQL tsvector (portugues) |
| LLM providers | requests (sem SDK externo) |
| Frontend | HTML/CSS/JS vanilla (lazy-loaded) |
| Streaming | Server-Sent Events (SSE) |
| Deploy | PyInstaller + Inno Setup (Windows) |
| Scraping | asyncio + aiohttp (Ubuntu), requests + BS4 (fallback) |

---

## 13. Metricas da Base de Conhecimento

| Metrica | Valor |
|---------|-------|
| Chunks TDN | 389.367 |
| Paginas processadas | 18.764 |
| Texto bruto | 99 MB |
| Tamanho PG (com indices) | 344 MB |
| Fontes distintas | 6 |
| Modulos no grafo | 9 |
| Sinonimos mapeados | 55+ |
| Skills ativas | 27+ |
| Ferramentas registradas | 60 |
| LLM providers | 10 |

---

*Documento gerado em 2026-03-27. Para atualizacoes, consultar o codigo-fonte em `app/services/agent_*.py` e `prompt/`.*
