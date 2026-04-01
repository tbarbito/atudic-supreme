# ExtraiRPO — Design Spec

## Visão Geral

**ExtraiRPO** é uma aplicação standalone (Python + web) que permite a um analista Protheus chegar no cliente, apontar os arquivos do ambiente (dicionário de dados + fontes customizados) e imediatamente ter uma base de conhecimento inteligente sobre aquele cliente.

A ferramenta analisa a estrutura de dados (SX2, SX3, SX7, SIX), os fontes customizados e, usando IA, mapeia como os processos funcionam naquele cliente específico. A base se enriquece progressivamente conforme o uso — cada pergunta no chat pode gerar ou atualizar documentação.

### Princípios

- **Rápido de usar** — `python run.py`, aponta caminhos, clica "Iniciar"
- **Leve e portátil** — um processo só, sem dependências pesadas
- **Um cliente por vez** — ferramenta de campo, não plataforma
- **Duas bases separadas** — padrão Protheus (referência) e cliente (gerada pela IA)
- **Progressivo** — quanto mais perguntas, mais rica a base

---

## Stack Tecnológica

| Componente | Tecnologia | Justificativa |
|---|---|---|
| Backend | Python + FastAPI | Leve, async, serve API + frontend |
| Banco estruturado | SQLite | Zero config, um arquivo, portátil |
| Busca semântica | ChromaDB | Embarcado, sem servidor externo |
| Multi-provider IA | LiteLLM | Claude, GPT, Ollama com mesma interface |
| Frontend | Vue 3 + Vite (SPA buildado) | Leve, rápido de buildar, servido pelo FastAPI |
| Streaming | Server-Sent Events (SSE) | Chat com resposta em tempo real |

---

## Estrutura de Pastas

```
ExtraiRPO/
├── run.py                      # Entry point — python run.py → abre browser
├── config.json                 # API keys + caminhos apontados no setup
├── requirements.txt
│
├── backend/
│   ├── app.py                  # FastAPI — serve API + frontend estático
│   ├── routers/
│   │   ├── setup.py            # Wizard de configuração inicial
│   │   ├── chat.py             # Chat com streaming SSE
│   │   └── docs.py             # Visualização dos docs gerados
│   └── services/
│       ├── ingestor.py         # Orquestra toda a ingestão
│       ├── parser_sx.py        # Parse CSVs do dicionário (SX2, SX3, SX7, SIX)
│       ├── parser_source.py    # Parse fontes .prw/.tlpp
│       ├── vectorstore.py      # ChromaDB — indexação e busca semântica
│       ├── llm.py              # LiteLLM — multi-provider
│       ├── doc_generator.py    # Gera .MD em 2 camadas (humano + IA)
│       └── knowledge.py        # Consultas cruzadas na base
│
├── frontend/dist/              # SPA buildado — servido como estático
│
├── templates/
│   └── processos/              # Processos padrão Protheus (referência)
│       ├── compras.md
│       ├── faturamento.md
│       ├── financeiro.md
│       ├── estoque.md
│       ├── fiscal.md
│       ├── pcp.md
│       ├── rh.md
│       ├── contabilidade.md
│       └── mapa-modulos.json   # Mapeamento tabela → módulo
│
└── workspace/                  # Dados da sessão atual
    ├── knowledge/
    │   ├── padrao/             # Base fixa — Protheus de fábrica
    │   │   ├── humano/
    │   │   └── ia/
    │   └── cliente/            # Base gerada — ambiente real do cliente
    │       ├── humano/
    │       └── ia/
    └── db/
        ├── extrairpo.db        # SQLite — dicionário estruturado
        └── chroma/             # ChromaDB — vetores dos fontes
```

---

## Fluxo de Primeiro Uso

```
1. python run.py
2. Browser abre → tela de Setup
3. Usuário configura:
   - Nome do cliente
   - Caminho da pasta de CSVs do dicionário
   - Caminho da pasta de fontes customizados
   - Caminho da pasta de fontes padrão (opcional)
   - Provider de IA (Claude/GPT/Ollama)
   - API Key
4. Clica "Iniciar"
5. Sistema executa ingestão automática (3 fases)
6. Quando termina → redireciona pro Chat, base pronta
```

Nas próximas vezes: abre e já cai no chat. Para outro cliente: Config → "Limpar workspace", reconfigura.

---

## Ingestão — 3 Fases

### Fase 1 — Parse Estrutural (segundos)

- Lê CSVs do dicionário (SX2, SX3, SX7, SIX)
- Monta mapa: tabelas → campos → índices → gatilhos
- Identifica campos customizados (prefixo `X_` no nome)
- Identifica tabelas customizadas (SZ*, QA*-QZ*, etc.)
- Salva tudo estruturado no SQLite

### Fase 2 — Indexação de Fontes (minutos)

- Escaneia pasta de fontes customizados
- Escaneia pasta de fontes padrão (se fornecida)
- Para cada fonte extrai: funções, User Functions, pontos de entrada, ExecAutos, includes, tabelas referenciadas
- Compara custom vs padrão quando ambos existem
- Indexa tudo no ChromaDB para busca semântica

### Fase 3 — Análise do Cliente (LLM)

- Para cada módulo detectado nas tabelas e fontes:
  1. Analisa os fontes custom daquele módulo
  2. Analisa gatilhos e campos custom relacionados
  3. Envia pro LLM: "com base nesses fontes e dicionário, descreva como esse processo funciona neste cliente"
  4. Gera doc do CLIENTE na pasta `knowledge/cliente/`
- Resultado: workspace nasce com docs dos processos detectados

**Guardrails da Fase 3:**
- Máximo 2 chamadas LLM simultâneas (evita rate limit)
- Antes de iniciar, exibe no setup: "X módulos detectados. Estimativa: ~Y chamadas ao LLM. Continuar?"
- Usuário pode pular Fase 3 e gerar docs sob demanda no chat depois
- Para Ollama (local), sem limite de custo — processa tudo sequencialmente

---

## Duas Bases de Conhecimento

### Base Padrão (`knowledge/padrao/`)

Referência pura do Protheus de fábrica. Vem embarcada no ExtraiRPO a partir dos templates. Serve para consulta — "como funciona de fábrica". Não se mistura com dados do cliente.

### Base Cliente (`knowledge/cliente/`)

Gerada pela IA analisando o que foi ingerido. Descreve como os processos funcionam **naquele cliente específico**. Enriquece progressivamente com cada interação no chat.

Cada base tem 2 camadas:

| Camada | Público | Conteúdo |
|---|---|---|
| `humano/` | Analista | Processo passo a passo, tabelas envolvidas, customizações, pontos de atenção |
| `ia/` | Sistema | Metadados estruturados com frontmatter YAML: tabelas, campos, fontes, funções, dependências, tags |

### Uso cruzado

| Pergunta | Fontes consultadas |
|---|---|
| "Como funciona compras no Protheus?" | `knowledge/padrao/` |
| "Como funciona compras nesse cliente?" | `knowledge/cliente/` |
| "O que esse cliente customizou em compras?" | LLM cruza padrao + cliente |
| "Gera um projeto de melhoria pro faturamento" | `cliente/ia/` + fontes + dicionário |

---

## Chat — Fluxo de uma Pergunta

```
Usuário pergunta
    │
    ├─→ Busca semântica no ChromaDB (fontes relevantes)
    ├─→ Consulta SQLite (tabelas, campos, gatilhos)
    ├─→ Verifica knowledge/cliente/ (doc existente?)
    │
    ├─→ Monta contexto unificado
    ├─→ Envia pro LLM com prompt especializado Protheus
    │
    ├─→ Responde no chat com streaming
    │
    └─→ Gera/atualiza docs automaticamente:
         knowledge/cliente/humano/{processo}.md
         knowledge/cliente/ia/{processo}.md
```

### Tipos de pergunta

| Tipo | Exemplo |
|---|---|
| Processo | "Como funciona o faturamento desse cliente?" |
| Customização | "O que foi customizado no cadastro de clientes?" |
| Tabela | "Quais campos customizados tem na SA1?" |
| Desenvolvimento | "Preciso criar um relatório de inadimplência" |
| Insight | "Quais pontos de entrada esse cliente usa?" |

### Comportamento progressivo

- **Primeira pergunta sobre compras** → gera doc do zero
- **Segunda pergunta sobre compras** → lê doc existente, enriquece, atualiza
- **Pergunta sobre desenvolvimento** → lê `knowledge/cliente/ia/` como contexto antes de responder

---

## Formato dos Documentos Gerados

### Doc Humano (exemplo: `knowledge/cliente/humano/faturamento.md`)

```markdown
# Faturamento — Processo do Cliente

## Visão Geral
Descrição de como o faturamento funciona neste cliente...

## Passo a Passo
1. Pedido de venda (MATA410 → SC5/SC6)
2. Validação gerencial (custom — XFAT001.prw verifica C5_XAPROV)
3. Liberação do pedido (MATA411)
4. Faturamento (MATA461 → SF2/SD2)
5. Transmissão NF-e

## Tabelas Envolvidas
- SC5 — Pedidos de venda
- SC6 — Itens do pedido
- SF2 — Notas fiscais de saída

## Customizações Identificadas
### Fontes Customizados
- XFAT001.prw — Validação extra na liberação do pedido

### Campos Customizados (SX3)
- C5_XAPROV (Char 1) — Flag de aprovação gerencial
- C5_XPRIOR (Char 1) — Prioridade do pedido

### Gatilhos Customizados (SX7)
- C5_CLIENT → C5_XREGIAO (busca região do cliente)

### Pontos de Entrada Utilizados
- MT410GRV — Gravação do pedido (em XFAT001.prw)

## Pontos de Atenção
- Cliente usa aprovação gerencial não padrão
```

### Doc IA (exemplo: `knowledge/cliente/ia/faturamento.md`)

```markdown
---
processo: faturamento
modulo: faturamento
tabelas: [SC5, SC6, SF2, SD2]
fontes_custom: [XFAT001.prw]
campos_custom: [C5_XAPROV, C5_XPRIOR]
gatilhos_custom: [C5_CLIENT->C5_XREGIAO]
pontos_entrada: [MT410GRV]
rotinas_padrao: [MATA410, MATA411, MATA461]
ultima_atualizacao: 2026-03-18
tags: [faturamento, pedido, nota-fiscal, aprovacao]
---

## Contexto Técnico
Função principal: MATA410 (pedido de venda)
Customizações detectadas: validação de aprovação gerencial via campo C5_XAPROV
Dependências: XFAT001.prw depende de SA1 (cadastro clientes) para região
```

---

## Interface Web — 5 Telas

### 1. Setup

Tela inicial exibida no primeiro uso ou quando workspace está vazio.

- Campo: nome do cliente
- Campo: caminho pasta CSVs do dicionário
- Campo: caminho pasta fontes customizados
- Campo: caminho pasta fontes padrão (opcional)
- Provider de IA: seletor (Claude / GPT / Ollama)
- Campo: API Key (ou URL do Ollama)
- Botão "Iniciar" → exibe barra de progresso das 3 fases
- Ao concluir → redireciona pro Chat

### 2. Chat

Área principal de trabalho.

- Área de conversa com streaming (SSE)
- Campo de input fixo na parte inferior
- Sidebar direita: fontes e tabelas consultadas na resposta atual
- Badge em respostas que geram/atualizam docs: "Doc atualizado: faturamento.md"

### 3. Base Padrão

Consulta da referência Protheus de fábrica.

- Lista dos processos padrão disponíveis
- Clique → visualiza o .MD renderizado
- Somente leitura

### 4. Base Cliente

Documentação gerada do ambiente do cliente.

- Lista dos docs gerados, divididos em `humano/` e `ia/`
- Clique → visualiza renderizado
- Status por módulo: mapeado / não mapeado
- Botão "Regenerar" por doc (reprocessar com LLM)

### 5. Config

Configurações da sessão.

- Provider de IA e API Key
- Modelo preferido
- Caminhos das pastas (reconfigurar)
- Botão "Limpar workspace" (resetar para outro cliente)

---

## Provider de IA — Multi-Provider via LiteLLM

```python
# config.json
{
  "cliente": "ACME Corp",
  "paths": {
    "csv_dicionario": "C:/Cliente/dicionario",
    "fontes_custom": "C:/Cliente/fontes",
    "fontes_padrao": "C:/Protheus/fontes_padrao"
  },
  "llm": {
    "provider": "anthropic",
    "model": "claude-sonnet-4-20250514",
    "api_key": "sk-ant-..."
  }
}
```

Providers suportados:
- **Anthropic** — Claude Sonnet/Opus
- **OpenAI** — GPT-4o/GPT-4-turbo
- **Ollama** — Modelos locais (Llama, Mistral, etc.)

---

## Decisões Técnicas

| Decisão | Escolha | Motivo |
|---|---|---|
| Banco | SQLite | Portátil, zero config, um arquivo |
| Vetores | ChromaDB embarcado | Sem servidor externo, persiste local |
| IA | LiteLLM | Abstrai providers com mesma interface |
| Frontend servido por | FastAPI (static files) | Um processo só, sem Node em produção |
| Streaming | SSE | Simples, suportado nativamente |
| Docs gerados | Markdown (.md) | Legível em qualquer editor, versionável |
| Config | JSON | Simples, editável manualmente se necessário |

---

## API Endpoints

| Método | Rota | Descrição |
|---|---|---|
| GET | `/api/status` | Estado atual: setup pendente, ingerindo, pronto |
| POST | `/api/setup` | Recebe config (nome, caminhos, provider, API key), inicia ingestão |
| GET | `/api/setup/progress` | SSE — progresso da ingestão em tempo real |
| POST | `/api/chat` | Envia pergunta, retorna resposta via SSE streaming |
| GET | `/api/chat/history` | Histórico de conversas da sessão |
| GET | `/api/docs/padrao` | Lista docs da base padrão |
| GET | `/api/docs/padrao/{slug}` | Conteúdo de um doc padrão renderizado |
| GET | `/api/docs/cliente` | Lista docs gerados do cliente (humano + ia) |
| GET | `/api/docs/cliente/{tipo}/{slug}` | Conteúdo de um doc do cliente (tipo: humano\|ia) |
| POST | `/api/docs/cliente/{slug}/regenerar` | Regenera doc com LLM |
| GET | `/api/config` | Config atual |
| PUT | `/api/config` | Atualiza config (provider, modelo, caminhos) |
| POST | `/api/config/limpar` | Limpa workspace (com confirmação no frontend) |

---

## Schema SQLite — `extrairpo.db`

```sql
-- Tabelas do dicionário (SX2)
CREATE TABLE tabelas (
    codigo      TEXT PRIMARY KEY,   -- ex: SA1
    nome        TEXT,               -- ex: Clientes
    modo        TEXT,               -- C=Compartilhado, E=Exclusivo
    custom      INTEGER DEFAULT 0   -- 1 se SZ*, QA*-QZ*
);

-- Campos do dicionário (SX3)
CREATE TABLE campos (
    tabela      TEXT REFERENCES tabelas(codigo),
    campo       TEXT,               -- ex: A1_COD
    tipo        TEXT,               -- C, N, D, L, M
    tamanho     INTEGER,
    decimal     INTEGER,
    titulo      TEXT,
    descricao   TEXT,
    validacao   TEXT,
    inicializador TEXT,
    obrigatorio INTEGER DEFAULT 0,
    custom      INTEGER DEFAULT 0,  -- 1 se prefixo X_
    PRIMARY KEY (tabela, campo)
);

-- Índices (SIX)
CREATE TABLE indices (
    tabela      TEXT REFERENCES tabelas(codigo),
    indice      TEXT,               -- ex: 1, 2, 3
    chave       TEXT,               -- ex: A1_FILIAL+A1_COD+A1_LOJA
    descricao   TEXT,
    PRIMARY KEY (tabela, indice)
);

-- Gatilhos (SX7)
CREATE TABLE gatilhos (
    campo_origem TEXT,
    sequencia   TEXT,
    campo_destino TEXT,
    regra       TEXT,               -- expressão AdvPL
    tipo        TEXT,               -- P=Primário, E=Estrangeiro
    tabela      TEXT REFERENCES tabelas(codigo),
    custom      INTEGER DEFAULT 0,
    PRIMARY KEY (campo_origem, sequencia)
);

-- Histórico de chat
CREATE TABLE chat_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    role        TEXT,               -- user | assistant
    content     TEXT,
    sources     TEXT,               -- JSON: fontes/tabelas consultadas
    doc_updated TEXT,               -- slug do doc gerado/atualizado (nullable)
    created_at  TEXT DEFAULT (datetime('now'))
);

-- Controle de progresso da ingestão
CREATE TABLE ingest_progress (
    item        TEXT PRIMARY KEY,   -- ex: "SX3.csv", "XFAT001.prw"
    fase        INTEGER,            -- 1, 2 ou 3
    status      TEXT,               -- pending | done | error
    error_msg   TEXT,
    updated_at  TEXT DEFAULT (datetime('now'))
);

-- Fontes indexados
CREATE TABLE fontes (
    arquivo     TEXT PRIMARY KEY,   -- ex: XFAT001.prw
    caminho     TEXT,               -- path completo
    tipo        TEXT,               -- custom | padrao
    modulo      TEXT,               -- faturamento, compras, etc.
    funcoes     TEXT,               -- JSON: lista de funções encontradas
    user_funcs  TEXT,               -- JSON: User Functions
    pontos_entrada TEXT,            -- JSON: PEs detectados
    tabelas_ref TEXT,               -- JSON: tabelas referenciadas
    includes    TEXT,               -- JSON: #includes
    hash        TEXT                -- hash do arquivo pra detectar mudança
);
```

---

## ChromaDB — Collections

| Collection | Conteúdo | Metadata |
|---|---|---|
| `fontes_custom` | Chunks dos fontes customizados (por função) | arquivo, funcao, modulo, tipo |
| `fontes_padrao` | Chunks dos fontes padrão (se fornecidos) | arquivo, funcao, modulo |
| `knowledge_cliente` | Chunks dos docs gerados do cliente | processo, modulo, camada (humano\|ia) |

Embedding model: `all-MiniLM-L6-v2` (padrão ChromaDB). Fontes Protheus contêm nomes de variáveis e funções que são universais (não dependem de idioma), então o modelo padrão é adequado para v1. Nota: docs em `knowledge_cliente` contêm texto em português — considerar modelo multilingual em v2.

### Chunking Strategy

- Fontes são divididos **por função**: cada `Function`/`Method` vira um chunk
- Código fora de funções (includes, variáveis globais, defines) vai num chunk "header" por arquivo
- Limite por chunk: 1000 tokens (~4000 chars). Se uma função excede, divide em blocos de 800 tokens com overlap de 100
- Ao regenerar doc (`/api/docs/cliente/{slug}/regenerar`), os chunks antigos da collection `knowledge_cliente` são deletados por filtro `processo == slug` antes de inserir os novos

### Atribuição de Módulo a Fontes

Cada fonte recebe um módulo com base em:
1. **Nome do arquivo** — se bate com `rotinas` do `mapa-modulos.json` (ex: MATA410 → faturamento)
2. **Tabelas referenciadas** — cruza `tabelas_ref` extraídas do fonte com `tabelas` do mapa. O módulo com mais tabelas referenciadas vence
3. **Multi-módulo** — se um fonte referencia tabelas de 2+ módulos igualmente, recebe o primeiro detectado + tag `multi_modulo` nos metadados

---

## Parser de Fontes — Estratégia

Abordagem: **regex + heurísticas** (não AST completo). Suficiente para v1.

Extrai de cada `.prw`/`.tlpp`:
- Declarações de função: `(Static|User|Main)?\s*Function\s+(\w+)`
- Classes TLPP: `Class\s+(\w+)`, `Method\s+(\w+)`
- Pontos de entrada: funções com nomes conhecidos (MT410GRV, A010TOK, etc.) + padrão `^[A-Z]{2,3}\d{3}[A-Z]{3}$`
- Tabelas referenciadas: `DbSelectArea\(['"](\w+)['"]\)`, `RetSqlName\(['"](\w+)['"]\)`, aliases SX2
- Includes: `#Include\s+['"](.+?)['"]`
- ExecAutos: `MsExecAuto\(.*?MATA\d+`

Encoding: tenta UTF-8 primeiro, fallback para CP1252 (padrão Protheus Windows).

---

## Parse de CSVs — Encoding e Formato

- Encoding: detecta automaticamente com `chardet`, fallback CP1252 → Latin-1 → UTF-8
- Delimitador: detecta automaticamente (`;` é comum em ambientes BR, `,` também)
- Validação: verifica colunas esperadas por tipo de SX antes de importar
- Erro: se CSV não bate com o formato esperado, reporta erro claro no setup com exemplo do formato aceito

---

## Contrato da API de Chat

### Request — `POST /api/chat`

```json
{
  "message": "Como funciona o faturamento desse cliente?"
}
```

### Response — SSE stream

```
event: sources
data: {"tabelas": ["SC5","SC6","SF2"], "fontes": ["XFAT001.prw"], "docs": ["faturamento.md"]}

event: token
data: {"content": "O faturamento"}

event: token
data: {"content": " deste cliente"}

...

event: doc_updated
data: {"slug": "faturamento", "action": "created|updated"}

event: done
data: {}
```

O frontend usa o evento `sources` pra popular a sidebar direita, os eventos `token` pra streaming da resposta, e `doc_updated` pra exibir o badge de doc atualizado.

---

## Classificação de Perguntas e Geração de Docs

Quando o usuário pergunta no chat, o LLM decide (via function calling / tool use):

1. **Classificar** — o LLM recebe a pergunta + contexto e retorna: módulo(s) relacionado(s), se deve gerar/atualizar doc, quais fontes consultar
2. **Buscar** — sistema busca ChromaDB + SQLite com base na classificação
3. **Responder** — LLM responde com o contexto montado
4. **Documentar** — se o LLM classificou como "gera doc", dispara geração assíncrona após a resposta (não bloqueia o chat)

A geração de doc é **assíncrona e pós-resposta** — não duplica custo de LLM na mesma chamada. O sistema pede ao LLM separadamente: "com base nessa conversa e contexto, gere/atualize o doc do processo X".

---

## Tratamento de Erros

| Cenário | Comportamento |
|---|---|
| API key inválida | Setup reporta erro, pede pra corrigir antes de iniciar |
| CSV malformado | Reporta arquivo + linha do erro, sugere formato esperado |
| Encoding errado | Fallback automático CP1252 → Latin-1 → UTF-8 |
| Fonte muito grande (>5000 linhas) | Chunka por função, indexa separadamente |
| LLM rate limit | Retry com backoff exponencial (3 tentativas), depois reporta erro |
| Ingestão falha no meio | Salva progresso no SQLite, permite retomar de onde parou |
| ChromaDB falha | Log do erro, continua sem busca semântica (degraded mode) |
| Pasta inexistente | Setup valida caminhos antes de iniciar |

---

## Mapa de Módulos — `mapa-modulos.json`

```json
{
  "compras":       { "tabelas": ["SC7","SC8","SA2","SCR","SCJ"], "rotinas": ["MATA120","MATA121","MATA103"] },
  "faturamento":   { "tabelas": ["SC5","SC6","SF2","SD2","SA1"], "rotinas": ["MATA410","MATA411","MATA460","MATA461"] },
  "financeiro":    { "tabelas": ["SE1","SE2","SE5","SA6","SEA"], "rotinas": ["FINA040","FINA050","FINA080"] },
  "estoque":       { "tabelas": ["SB1","SB2","SB5","SD1","SD3"], "rotinas": ["MATA240","MATA241","MATA250","MATA260"] },
  "fiscal":        { "tabelas": ["SF3","SF4","SFT","CDA","CDH"], "rotinas": ["MATA950","MATA953"] },
  "pcp":           { "tabelas": ["SC2","SG1","SG2","SD4","SHB"], "rotinas": ["MATA630","MATA650","MATA680"] },
  "rh":            { "tabelas": ["SRA","SRB","SRC","SRD","SRE"], "rotinas": ["GPEA010","GPEA020","GPEM020"] },
  "contabilidade": { "tabelas": ["CT1","CT2","CT5","CTS","CVD"], "rotinas": ["CTBA010","CTBA020","CTBA102"] }
}
```

Usado na Fase 3 da ingestão: detecta quais módulos o cliente usa cruzando tabelas encontradas no SX2/fontes com este mapa.

---

## Limpar Workspace

Quando o usuário clica "Limpar workspace":

1. Frontend exibe confirmação: "Isso apagará toda a base de conhecimento gerada. Deseja exportar antes?"
2. Se sim → gera ZIP da pasta `workspace/knowledge/` pra download
3. Se não → apaga `workspace/` inteiro (db + knowledge + chroma)
4. Reseta `config.json` → redireciona pro Setup

---

## Fora de Escopo (v1)

- Multi-client simultâneo
- Conexão direta ao banco do cliente (futuro)
- Diagramas visuais / Mermaid (futuro)
- Autenticação / login
- Deploy em servidor / cloud
- Comparação entre clientes
- API key criptografada (v1 usa plaintext em config.json, aceitável pra ferramenta local de campo)
