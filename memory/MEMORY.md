# Memória Semântica do Agente AtuDIC

> Base de conhecimento completa sobre o AtuDIC e o ambiente Protheus.
> Indexado automaticamente pelo FTS5 para busca BM25.

---

## O que é o AtuDIC

O AtuDIC é uma plataforma de DevOps, Observabilidade e Inteligência Operacional para o ERP TOTVS Protheus. Centraliza CI/CD, gestão de RPO, análise de logs, banco de dados, documentação automática e assistente inteligente. Stack: Python 3.12 / Flask / PostgreSQL 16 / Vanilla JS / Bootstrap 5.

---

## Arquitetura do AtuDIC

### Backend
- **Entry point:** run.py — inicializa encoding, carrega .env, cria app Flask, registra blueprints, inicia scheduler e log monitor
- **Blueprints:** 16 módulos (auth, main, pipelines, repositories, source_control, commands, observability, knowledge, database, dictionary, processes, documentation, devworkspace, agent, settings, admin)
- **Services:** runner.py (executor de pipelines), log_parser.py (parser de logs), scheduler.py (agendador cron), notifier.py (email/WhatsApp), smart_notifications.py (regras inteligentes), agent_memory.py (memória FTS5), agent_chat.py (chat engine), llm_providers.py (10 providers LLM)
- **Database:** PostgreSQL 16 com ThreadedConnectionPool (psycopg2), migrations incrementais (001-015)
- **Segurança:** bcrypt 12 rounds para senhas, Fernet para tokens/API keys, rate limiting, decorators @require_auth/@require_admin/@require_operator

### Frontend
- SPA em Vanilla JS. index.html é o ponto de entrada
- Módulos JS em static/js/integration-*.js (um por funcionalidade)
- api-client.js é o wrapper HTTP (apiRequest com auth token)
- Temas claro/escuro com CSS variables
- Service Worker para cache e modo offline parcial

### Padrões de Design
- **Isolamento por ambiente:** toda entidade é filtrada por environment_id
- **Execução assíncrona:** pipelines, scan de logs e notificações rodam em background threads
- **Live streaming:** logs usam deque em memória para polling rápido + SSE
- **Criptografia:** tokens GitHub e senhas de banco armazenadas com Fernet
- **Transações atômicas:** operações críticas (equalização, correções) usam TransactionContext
- **Políticas de branch:** controlam quais operações são permitidas por ambiente/repo/branch

---

## Navegação do AtuDIC

A interface é organizada em categorias no menu superior:
- **Dashboard** — Visão geral do sistema
- **CI/CD** — Pipelines, Schedule, Comandos
- **Repositórios** — Repositórios GitHub, Controle de Versão, Dev Workspace
- **Observabilidade** — Observabilidade (logs), Banco de Dados, Processos
- **Conhecimento** — Base de Conhecimento, Documentação, Agente IA
- **Admin** — Usuários, Configurações

O ambiente ativo é selecionado no menu superior direito. Todos os módulos filtram dados por esse ambiente.

---

## Módulo: Pipelines (CI/CD)

Orquestração de pipelines de build e deploy com execução sequencial de comandos.

### Funcionalidades
- Criar, editar e excluir pipelines com sequência de comandos
- Execução manual ou agendada (daily, weekly, monthly)
- Live streaming de logs em tempo real (SSE + polling)
- Histórico de execuções com paginação
- Releases: criar release a partir de build bem-sucedido
- Notificação automática de sucesso/falha

### Como funciona
1. O admin cria um pipeline com uma sequência de comandos (bash, powershell, python, etc.)
2. O pipeline é executado manualmente ou via schedule
3. O Runner executa cada comando sequencialmente, capturando stdout/stderr
4. Logs são transmitidos em tempo real para o frontend
5. Ao finalizar, o status é atualizado (success/failed) e notificações são enviadas

### Tabelas
- pipelines, pipeline_commands, pipeline_runs, pipeline_run_logs, pipeline_run_output_logs, releases, release_logs, pipeline_schedules

---

## Módulo: Comandos

Scripts reutilizáveis que podem ser compostos em pipelines.

### Funcionalidades
- CRUD de comandos com categorização (build ou deploy)
- Tipos: bash, powershell, python, nodejs, docker
- Proteção de comandos do sistema (não podem ser alterados)
- Filtros por categoria e tipo

### Tabela
- commands (environment_id, name, type, script, command_category)

---

## Módulo: Repositórios GitHub

Integração com GitHub para gerenciamento de código-fonte.

### Funcionalidades
- Descoberta automática de repositórios via API GitHub
- Clone de repos com branch específica
- Pull (sync com origin), Push (commit + push)
- Criação de tags e branches
- Navegador de arquivos (Git ls-tree ou filesystem)
- Token GitHub criptografado com Fernet

### Tabelas
- repositories, github_settings

---

## Módulo: Controle de Versão

Operações Git em repositórios clonados — status, diff, staging, commits, push/pull.

### Funcionalidades
- Git status categorizado (staged, modified, untracked)
- Diff unificado para arquivos individuais
- Histórico de commits com metadados
- Stage/unstage de arquivos
- Commit com sanitização de mensagem
- Push com injeção de token
- Discard de changes
- Validação de políticas de branch (allow_push, allow_pull, allow_commit)

---

## Módulo: Dev Workspace

Cockpit de desenvolvimento AdvPL — navegação de fontes, análise de impacto, compilação.

### Funcionalidades
- Navegador de FONTES_DIR com busca textual e regex
- Viewer de código com syntax highlight e encoding ANSI (cp1252) para .prw/.tlpp
- Análise de impacto: cross-reference entre fontes, tabelas, processos e erros
- Diff FONTES_DIR vs repositório Git
- Gerador de compila.txt (lista de arquivos para compilar)
- Políticas de branch-ambiente (vincular branch a ambiente com regras)

### Tabelas
- branch_policies, source_impact_cache

---

## Módulo: Observabilidade

Parser de console.log/error.log do AppServer Protheus com alertas e categorização automática.

### Funcionalidades
- Configuração de monitores de log (path, tipo, intervalo de checagem)
- Scan manual ou automático (background thread)
- 50+ regex patterns para detecção de erros
- 15+ categorias: database, thread_error, rpo, service, ssl, ad_auth, http, memory, lock, etc.
- Severidade: critical, warning, info
- Dashboard: contadores por severidade/categoria, alertas críticos recentes
- Acknowledge de alertas (individual ou bulk)
- Modo de teste (parse sem salvar)

### Tabelas
- log_monitor_configs, log_alerts

---

## Módulo: Banco de Dados

Conexões multi-driver para explorar e consultar bancos Protheus.

### Funcionalidades
- CRUD de conexões (SQL Server, PostgreSQL, MySQL, Oracle)
- Senhas criptografadas com Fernet
- Descoberta de schema (tabelas, colunas, índices, constraints, triggers)
- Query editor com execução read-only (máx 1000 rows no UI, sem limite no CSV)
- Exportação CSV
- Histórico de queries por conexão
- Teste de conectividade com medição de latência

### Tabelas
- database_connections, schema_cache, query_history

---

## Módulo: Compare de Dicionário

Comparação de dicionário de dados Protheus entre duas bases.

### Funcionalidades
- Compara 13 tabelas de metadados (SX1, SX2, SX3, SX5, SX6, SX7, SX9, SXA, SXB, SIX, XXA, XAM, XAL)
- Validação de integridade: 20 verificações cruzadas (campos sem coluna física, índices divergentes, tipos incorretos, etc.)
- Suporte multi-empresa (SYS_COMPANY)
- Histórico de operações com export CSV

---

## Módulo: Equalizador de Dicionário

Sincronização seletiva de estrutura entre duas bases Protheus.

### Funcionalidades
- Preview SQL antes de executar (segurança)
- 4 fases: campos faltantes (ALTER TABLE + INSERT SX3), índices faltantes (CREATE INDEX + INSERT SIX), tabelas novas (CREATE TABLE + metadados), metadados puros
- Cross-driver: MSSQL ↔ PostgreSQL
- Execução em transação atômica (BEGIN/COMMIT/ROLLBACK)
- Confirmation token SHA-256 para evitar execução acidental
- Regras Protheus: NOT NULL em tudo, DEFAULT espaços/zero, R_E_C_N_O_ IDENTITY, TOP_FIELD

### Tabela
- dictionary_history (operation_type = 'equalize')

---

## Módulo: Processos da Empresa

Mapeamento de processos de negócio do ERP Protheus.

### Funcionalidades
- CRUD de processos por módulo Protheus (SIGAFAT, SIGACOM, SIGAFIN, etc.)
- Vincular tabelas a processos (papel: principal, secundário)
- Documentar campos de tabela (chave, obrigatório, regra de negócio)
- Auto-importação de campos do schema_cache
- Fluxos entre processos (tipo: data ou workflow)
- Mapa global de processos (grafo com dagre.js)
- 12 processos seed pré-cadastrados (pedido de venda, faturamento, financeiro, etc.)

### Tabelas
- business_processes, process_tables, process_fields, process_flows

---

## Módulo: Base de Conhecimento

Artigos sobre erros conhecidos do Protheus com causas e soluções.

### Funcionalidades
- CRUD de artigos (título, categoria, pattern regex, solução, código de exemplo)
- Busca textual em título, descrição, solução, tags, causas
- ~60 erros documentados em 15 categorias
- Import via upload de arquivo .md
- Contador de uso (usage_count)
- Correlação automática com alertas da Observabilidade (find_matching_article)
- Análise de recorrência (top erros por frequência nos últimos 7 dias)
- Histórico de correções aplicadas com validação

### Tabelas
- knowledge_articles, correction_history, alert_recurrence

---

## Módulo: Documentação Automática

Geração de documentação técnica e funcional a partir dos dados do sistema.

### Funcionalidades
- 4 tipos de documento: Dicionário de Dados, Mapa de Processos, Guia de Erros, Documentação Combinada
- Geração automática via templates Jinja2 embutidos
- Preview Markdown → HTML (marked.js)
- Download como .md
- Versionamento (parent_id + version)

### Tabela
- generated_docs (title, doc_type, content_md, version)

---

## Módulo: Agente IA (este módulo)

Chat inteligente com memória persistente e integração com LLMs.

### Funcionalidades
- Chat com 8 intents detectáveis: error_analysis, pipeline_status, table_info, procedure_lookup, alert_recurrence, environment_status, knowledge_search, general
- Modo rule-based (sem LLM) ou LLM-augmented (com contexto)
- Memória FTS5: MEMORY.md (semântica), TOOLS.md (procedural), logs diários (episódica)
- Busca BM25 com tokenizer unicode61 (português)
- 10 providers LLM: Ollama, OpenAI, Claude, Gemini, Grok, DeepSeek, OpenRouter, Groq, Mistral, Together
- Configuração de API keys por ambiente (criptografadas)
- Sessões de chat com histórico persistente

---

## Módulo: Notificações Inteligentes

Regras de notificação com filtros para evitar spam.

### Funcionalidades
- Regras por severidade, categoria, min_occurrences, time_window
- Cooldown entre notificações (previne repetição)
- Multi-canal: email (SMTP), WhatsApp, webhook
- Templates HTML para email
- Envio assíncrono (não bloqueia o sistema)

### Tabela
- notification_rules, notification_settings

---

## Módulo: Configurações

Configurações do sistema por ambiente.

### Funcionalidades
- Integrações: GitHub token/username, API management
- Notificações: SMTP, WhatsApp, webhook
- Políticas de branch-ambiente

---

## Perfis de Acesso

- **Admin** — acesso total, gerenciar usuários, configurações, LLM, comandos
- **Operator** — CI/CD, repositórios, observabilidade, conhecimento, comandos, agente IA
- **Viewer** — leitura de repositórios, pipelines, observabilidade, conhecimento, agente IA

---

## Fluxo de Dados Principal

```
Repositórios → Source Control (Git) → Dev Workspace (impacto)
                    ↓
            Branch Policies
                    ↓
Pipelines → Runner (executa) → Pipeline Runs → Releases
                    ↓
            Notifier ← Smart Notifications ← Rules

Log Monitors → Log Parser → Log Alerts
                    ↓
        Knowledge Base (sugere soluções)
        Smart Notifications (filtra)
        Notifier (envia)

Database Browser → Schema Cache → Compare Dicionário → Equalizador
                         ↓
                   Processos (tabelas/campos)
                         ↓
                   Documentation Generator
```

---

## Tabelas Principais do Protheus

### Vendas e Faturamento
- **SC5** — Pedidos de Venda (cabeçalho)
- **SC6** — Itens do Pedido de Venda
- **SC9** — Pedidos em Carteira (liberação de crédito)
- **SF2** — Notas Fiscais de Saída (cabeçalho)
- **SD2** — Itens das Notas Fiscais de Saída
- **SA1** — Cadastro de Clientes
- **DA0/DA1** — Tabelas de Preço (cabeçalho/itens)

### Compras
- **SC1** — Solicitações de Compra
- **SC7** — Pedidos de Compra
- **SC8** — Pedidos de Compra (itens por entrega)
- **SF1** — Notas Fiscais de Entrada (cabeçalho)
- **SD1** — Itens das Notas Fiscais de Entrada
- **SA2** — Cadastro de Fornecedores
- **SA5** — Vínculos Produto x Fornecedor

### Estoque
- **SB1** — Cadastro de Produtos
- **SB2** — Saldos em Estoque (por armazém)
- **SB5** — Dados Complementares de Produtos
- **SD3** — Movimentações Internas de Estoque

### Financeiro
- **SE1** — Contas a Receber
- **SE2** — Contas a Pagar
- **SE5** — Movimentação Bancária
- **SA6** — Cadastro de Bancos
- **FK2** — Movimentos contábeis

### Fiscal
- **SF3** — Livros Fiscais
- **SFT** — Livros Fiscais (SPED)
- **CDO** — Complemento de Documento Fiscal

### Contabilidade
- **CT1** — Plano de Contas
- **CT2** — Lançamentos Contábeis
- **CTT** — Centros de Custo

---

## Metadados Protheus (Dicionário de Dados)

- **SX1** — Perguntas e Respostas (parâmetros de relatórios)
- **SX2** — Mapeamento de Tabelas (alias → nome físico)
- **SX3** — Dicionário de Campos (schema lógico)
- **SX5** — Tabelas Genéricas (domínios de valores)
- **SX6** — Parâmetros do Sistema
- **SX7** — Gatilhos (triggers lógicos de campo)
- **SX9** — Relacionamentos entre Tabelas
- **SXA** — Pastas/Folders de Formulário
- **SXB** — Consulta Padrão (F3)
- **SIX** — Índices de Tabelas

### Regras de Metadados
- Sufixo de empresa: tabelas físicas terminam com código da empresa (ex: SC5010, SA1010)
- Protheus NÃO aceita NULL — todos os campos são NOT NULL, usar ' ' (espaço) ou 0 como default
- SIX: nome do índice é calculado (NICKNAME ou alias + ordem), CHAVE pode conter funções AdvPL
- TOP_FIELD gerencia auto-incremento para campos que não usam R_E_C_N_O_

---

## Padrões AdvPL

### Convenções de Nomenclatura
- Variáveis locais: prefixo com tipo (cVar = caractere, nVal = numérico, dData = data, lFlag = lógico, aArr = array, oObj = objeto)
- Funções customizadas: prefixo Z + módulo (ex: ZFAT001, ZCOM002)
- User Functions: declarar com `User Function` para exposição via menu

### Funções Frequentes
- **MsExecAuto()** — execução automática de rotinas padrão
- **MaFisAdd()** — adição de itens fiscais com cálculo automático
- **GDFieldPut()** — gravação de campos em grid MVC
- **FWBrowse()** — browse padrão com filtros e ações
- **Posicione()** — posiciona em registro pelo índice
- **RecLock()** / **MsUnlock()** — controle de lock de registros

### Sequência de Campos Fiscais
Sempre validar na ordem: ICMS → PIS → COFINS → ISS → IPI → ICMS-ST

---

## Erros Comuns do AppServer

### Categorias Principais
1. **SSL/TLS** — certificados, handshake, versão de protocolo
2. **TopConnect/SQL** — conexão perdida, query timeout, deadlock
3. **Thread Error** — excesso de threads, thread travada
4. **RPO** — função não encontrada, RPO corrompido
5. **Lock** — registro travado, timeout de lock
6. **Memória** — stack overflow, heap exhaustion
7. **Alias** — workarea já em uso, alias não encontrado
8. **Array** — acesso fora dos limites, referência nula

---

## Ambientes Protheus Típicos

| Ambiente | Sigla | Uso |
|----------|-------|-----|
| Produção | PRD | Operação real, nunca testar aqui |
| Homologação | HML | Testes de aceite, validação de releases |
| Desenvolvimento | DEV | Desenvolvimento ativo, compilação |
| Teste | TST | Testes automatizados, QA |

---

## Feedback & Workflows
- [feedback_deploy_workflow.md](feedback_deploy_workflow.md) — Fluxo completo de entrega: commit + push + scp + build installer Windows
