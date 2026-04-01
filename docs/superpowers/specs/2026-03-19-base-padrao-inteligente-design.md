# Base Padrão Inteligente — Wiki Enriquecível do Protheus

**Data:** 2026-03-19
**Status:** Aprovado
**Dependência:** UX Redesign (PrimeVue + MarkdownViewer) já implementado

---

## 1. Objetivo

Transformar a Base Padrão de uma referência estática em uma **wiki inteligente do Protheus** com duas capacidades:

1. **Enriquecimento sob demanda** — o usuário faz perguntas sobre o módulo, a IA pesquisa (TDN + Web) e adiciona a resposta no markdown do módulo
2. **Referência TDN navegável** — árvore hierárquica dos JSONs do TDN com conteúdo dos markdowns

A Base Padrão é **totalmente separada** da Base do Cliente. É conhecimento genérico do Protheus padrão.

---

## 2. Layout da PadraoView

### 2.1 Estrutura Geral

Duas abas no topo: **Módulos** e **Referência TDN**.

### 2.2 Aba "Módulos" — Layout 3 colunas

```
┌─ Abas: [Módulos ●] [Referência TDN] ────────────────────────┐
│                                                               │
│ ┌──────────┬──────────────────────────┬───────────────────┐   │
│ │ Lista    │  Conteúdo Markdown       │  Pergunte ao      │   │
│ │ Módulos  │  (MarkdownViewer)        │  Padrão           │   │
│ │ (220px)  │  (flex)                  │  (300px)          │   │
│ │          │                          │                   │   │
│ │ [filtro] │  # Compras               │  [campo pergunta] │   │
│ │          │  ## Cotação              │  [🔍 Pesquisar]   │   │
│ │ Compras● │  texto do processo...    │                   │   │
│ │ Fatur.   │                          │  ┌─ Preview ────┐ │   │
│ │ Financ.  │  ## Parâmetros           │  │ MV_FORNPAD   │ │   │
│ │ Estoque  │  MV_FORNPAD ativa...     │  │ ativa forn...│ │   │
│ │ Fiscal   │                          │  │              │ │   │
│ │ Contab.  │  > 📋 Pesquisado em      │  │ Fontes:      │ │   │
│ │          │  > 19/03/2026            │  │ TDN, Web     │ │   │
│ │          │  > MV_RESTEFIN não       │  └──────────────┘ │   │
│ │          │  > encontrado no padrão  │                   │   │
│ │          │                          │  [✓ Adicionar]    │   │
│ │          │                          │  [✗ Descartar]    │   │
│ └──────────┴──────────────────────────┴───────────────────┘   │
└───────────────────────────────────────────────────────────────┘
```

**Coluna esquerda (220px):** Lista de módulos auto-detectada de `processoPadrao/*.md`. Filtro por nome. Qualquer `.md` novo aparece automaticamente.

**Coluna central (flex):** MarkdownViewer completo (Accordion, TOC, busca, Mermaid, highlight). Mostra o markdown integral do módulo selecionado — conteúdo original + enriquecimentos integrados.

**Coluna direita (300px):** Painel "Pergunte ao Padrão" — campo de pergunta, botão pesquisar, preview do resultado, botões adicionar/descartar.

### 2.3 Aba "Referência TDN" — Árvore + Conteúdo

```
┌─ Abas: [Módulos] [Referência TDN ●] ────────────────────────┐
│                                                               │
│ ┌─ Sub-abas: [AdvPL ●] [Framework] [TLPP] [REST API] ─────┐ │
│ │                                                           │ │
│ │ ┌─ Árvore (250px) ─────┬─ Conteúdo (flex) ────────────┐ │ │
│ │ │                       │                               │ │ │
│ │ │ [🔍 buscar na árvore] │  ## Connect To                │ │ │
│ │ │                       │  Função que conecta ao...     │ │ │
│ │ │ ▼ Linguagem           │                               │ │ │
│ │ │   ▼ 4GL               │  **Sintaxe:**                 │ │ │
│ │ │     ▼ Banco de dados  │  `CONNECT TO cServer`         │ │ │
│ │ │       • Connect To ●  │                               │ │ │
│ │ │       • DBTableExists │  🔗 Ver no TDN               │ │ │
│ │ │     ► Funções Screen  │  (abre URL original)          │ │ │
│ │ │   ► AdvPL             │                               │ │ │
│ │ │   ► xBase             │                               │ │ │
│ │ │                       │                               │ │ │
│ │ └───────────────────────┴───────────────────────────────┘ │ │
│ └───────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────┘
```

**4 sub-abas** correspondendo aos JSONs:

| Sub-aba | JSON fonte | Markdown associado |
|---------|-----------|-------------------|
| AdvPL | `advpl_tdn_tree.json` | `advpl_tdn_knowledge_base.md` |
| Framework | `tdn_framework_v2.json` | `framework_tdn_knowledge_base.md` |
| TLPP | `tdn_tlpp_v2.json` | (sem markdown dedicado, usa links TDN) |
| REST API | `tdn_totvstec_rest.json` | (sem markdown dedicado, usa links TDN) |

**Navegação:**
- Árvore hierárquica usando componente `Tree` do PrimeVue (expandir/colapsar nós)
- Campo de busca que filtra nós da árvore por título
- Ao clicar num nó folha → busca conteúdo correspondente no markdown TDN (match por título da seção)
- Se não tem conteúdo no markdown → mostra link "Ver no TDN" (campo `url` do JSON)
- Somente leitura — sem "Pergunte ao Padrão" nesta aba

---

## 3. Fluxo "Pergunte ao Padrão"

### 3.1 Fluxo do Usuário

1. Usuário está lendo o doc de Compras
2. Digita no painel direito: "Na cotação tem como definir fornecedores padrão por produto?"
3. Clica "Pesquisar"
4. Painel mostra loading → preview do resultado aparece
5. Usuário lê o preview, vê as fontes consultadas
6. Clica "Adicionar ao Doc" → conteúdo é inserido no markdown
7. MarkdownViewer atualiza mostrando o novo conteúdo integrado

### 3.2 Fluxo da IA (Backend)

1. Recebe a pergunta + slug do módulo
2. Pesquisa em paralelo:
   - ChromaDB coleção `tdn` (funções, parâmetros, framework)
   - ChromaDB coleção `padrao` (conteúdo de outros módulos que possam ter relação)
   - Busca web (centraldeatendimento.totvs.com, TDN online, documentação TOTVS)
3. Monta contexto com os resultados das 3 fontes
4. Chama o LLM (gen_model) com prompt específico:
   - Responda APENAS com base nas fontes fornecidas
   - Se não encontrar informação suficiente, diga explicitamente
   - Formate em markdown compatível com o doc existente
   - Sugira a seção do documento onde a resposta deve ser inserida
5. Retorna preview + fontes + seção sugerida

### 3.3 Regras Absolutas da IA

- **Nunca inventa** — só documenta o que encontrou nas fontes
- **Se não encontrar:** registra honestamente com data:
  ```markdown
  > ⚠️ Pesquisado em 19/03/2026 — Não foi encontrada funcionalidade
  > padrão no Protheus para definir fornecedores preferenciais por
  > produto na cotação. Esta necessidade pode requerer customização
  > via Ponto de Entrada.
  > Fontes consultadas: TDN, centraldeatendimento.totvs.com
  ```
- **Cada adição tem marcador:**
  ```markdown
  > 📋 Adicionado em 19/03/2026 | Fontes: TDN - MV_FORNPAD, Web
  ```
- **Inserção híbrida:**
  - Se existe seção relevante no doc (ex: "Parâmetros") → adiciona ali dentro
  - Se não existe → cria nova seção contextual no local mais adequado

### 3.4 Prompt do Agente de Enriquecimento

```
Você é um especialista em TOTVS Protheus. O usuário está consultando o módulo "{modulo}".

REGRAS ABSOLUTAS:
- Responda APENAS com base nas fontes fornecidas abaixo (TDN, Web, Base Padrão).
- NÃO invente funcionalidades, parâmetros ou comportamentos.
- Se não encontrar informação suficiente nas fontes, diga explicitamente que não encontrou.
- Formate a resposta em Markdown.
- Indique a seção do documento onde a resposta deve ser inserida.

CONTEXTO DO DOCUMENTO ATUAL:
{secoes_existentes}

FONTES TDN:
{contexto_tdn}

FONTES WEB:
{contexto_web}

FONTES BASE PADRÃO:
{contexto_padrao}

PERGUNTA DO USUÁRIO:
{pergunta}

Responda no formato JSON:
{
  "encontrou": true/false,
  "secao_sugerida": "nome da seção existente ou nova",
  "resposta_md": "conteúdo markdown formatado",
  "fontes": ["fonte1", "fonte2"]
}
```

---

## 4. Endpoints

### 4.1 Endpoints Novos

#### POST /api/padrao/{slug}/enriquecer

Pesquisa a resposta e retorna preview (não salva ainda).

```python
# Request
{
    "pergunta": "Na cotação tem como definir fornecedores padrão por produto?"
}

# Response
{
    "encontrou": true,
    "secao_sugerida": "Parâmetros",
    "resposta_md": "### MV_FORNPAD\nO parâmetro MV_FORNPAD ativa...",
    "fontes": [
        "TDN - MV_FORNPAD",
        "https://centraldeatendimento.totvs.com/..."
    ]
}
```

#### POST /api/padrao/{slug}/aplicar

Aplica o enriquecimento aprovado pelo usuário.

```python
# Request
{
    "resposta_md": "### MV_FORNPAD\nO parâmetro MV_FORNPAD ativa...",
    "secao_sugerida": "Parâmetros",
    "fontes": ["TDN - MV_FORNPAD", "https://..."],
    "pergunta": "Na cotação tem como definir fornecedores padrão?"
}

# Response
{
    "status": "ok",
    "slug": "SIGACOM_Fluxo_Compras"
}
```

**Ações do `/aplicar`:**
1. Lê o markdown atual de `processoPadrao/{slug}.md`
2. Identifica a seção sugerida (ou cria nova)
3. Insere a resposta com marcador de data e fontes
4. Salva o arquivo `.md` atualizado
5. Re-ingere o doc no ChromaDB coleção `padrao`

#### GET /api/padrao/tdn/{tipo}

Retorna a árvore JSON para navegação.

```python
# tipo: "advpl" | "framework" | "tlpp" | "rest"
# Response: array de nós com { title, url, depth, children }
```

#### GET /api/padrao/tdn/{tipo}/content?title={title}

Busca conteúdo de um nó específico no markdown TDN.

```python
# Response
{
    "title": "Connect To",
    "content": "## Connect To\nFunção que conecta ao...",
    "url": "https://tdn.totvs.com/display/tec/Connect+To",
    "found": true
}
```

### 4.2 Endpoints Existentes (sem mudança)

- `POST /api/padrao/ingest` — ingestão no ChromaDB
- `GET /api/padrao/list` — lista arquivos disponíveis

### 4.3 Endpoints Existentes (com mudança)

**`GET /api/docs/padrao`** — Atualmente lê de `workspace/<client>/knowledge/padrao/humano/` (por cliente). Deve ser alterado para ler direto de `processoPadrao/*.md` (global). Usar `padrao_ingestor.list_padrao_docs()` para listar os arquivos.

**`GET /api/docs/padrao/{slug}`** — Atualmente lê de workspace do cliente. Deve ler direto de `processoPadrao/{slug}.md`. A Base Padrão é global, não por cliente.

### 4.4 Algoritmo de Inserção no Markdown (`/aplicar`)

O endpoint `/aplicar` faz "cirurgia" no markdown seguindo este algoritmo:

1. Lê o arquivo `processoPadrao/{slug}.md` completo
2. Busca a linha que contém `## {secao_sugerida}` (case-insensitive, strip pontuação)
3. Se encontrar a seção:
   - Escaneia para frente até encontrar o próximo `## ` (header de nível 2)
   - Insere o bloco de enriquecimento **antes** do próximo header
   - O bloco inclui o marcador de data/fontes
4. Se não encontrar a seção:
   - Busca o final do arquivo (antes da última seção ou no final absoluto)
   - Cria uma nova seção `## {secao_sugerida}` com o conteúdo
5. Salva o arquivo `.md` atualizado
6. Re-ingere no ChromaDB (usa `ingest_padrao(vs)` do `padrao_ingestor.py`)

**Nota:** O servidor confia no payload do cliente em `/aplicar` pois é uma ferramenta local/trusted. Não há correlação entre `/enriquecer` e `/aplicar` — o preview é stateless.

---

## 5. Modificações nos Arquivos

### 5.1 Frontend

| Arquivo | Mudança |
|---------|---------|
| `frontend/src/views/PadraoView.vue` | Reescrever: 2 abas (Módulos + TDN), layout 3 colunas com painel "Pergunte ao Padrão" |
| **Novo:** `frontend/src/components/AskPadraoPanel.vue` | Painel lateral: campo pergunta, pesquisar, preview, adicionar/descartar |
| **Novo:** `frontend/src/components/TdnTreeView.vue` | Árvore hierárquica TDN com Tree PrimeVue + busca + conteúdo |

### 5.2 Backend

| Arquivo | Mudança |
|---------|---------|
| `backend/routers/docs.py` | Ajustar `list_padrao` e `get_padrao` para ler de `processoPadrao/` direto |
| **Novo:** `backend/routers/padrao.py` | Endpoints: enriquecer, aplicar, tdn/{tipo}, tdn/{tipo}/content |
| **Novo:** `backend/services/padrao_enricher.py` | Lógica de pesquisa (ChromaDB + Web), chamada LLM, inserção no markdown |
| `backend/app.py` | Registrar novo router `padrao_router` |

### 5.3 Dependências

| Pacote | Propósito |
|--------|-----------|
| Nenhum novo no frontend | Tree e TabView já disponíveis no PrimeVue |
| `httpx` (backend) | Busca web assíncrona para enriquecimento (já é dependência transitiva do LiteLLM) |

---

## 6. Estratégia de Busca Web

### 6.1 Implementação

Novo serviço `backend/services/web_search.py`:

- Usa `httpx` (async HTTP client, já disponível como dep transitiva do LiteLLM)
- Faz busca no Google com `site:centraldeatendimento.totvs.com` ou `site:tdn.totvs.com`
- Scrape básico do HTML retornado (extrai texto do `<body>`, sem JS rendering)
- Limite: máx 3 URLs por busca, timeout 10s por request

### 6.2 Fluxo de busca no `/enriquecer`

```
1. ChromaDB "tdn"    → top 5 chunks relevantes
2. ChromaDB "padrao" → top 3 chunks de outros módulos
3. Web search        → busca "{pergunta} site:centraldeatendimento.totvs.com OR site:tdn.totvs.com"
                     → fetch top 3 URLs, extrai texto
4. Monta contexto com as 3 fontes
5. LLM gera resposta
```

Se a busca web falhar (timeout, erro HTTP), continua apenas com ChromaDB. A busca web é best-effort.

---

## 7. Notas sobre TDN

### 7.1 Mapeamento JSON → Markdown

| Sub-aba | JSON | Markdown | Notas |
|---------|------|----------|-------|
| AdvPL | `advpl_tdn_tree.json` | `advpl_tdn_knowledge_base.md` | Match por título de seção `## ` |
| Framework | `tdn_framework_v2.json` | `framework_tdn_knowledge_base.md` | Match por título de seção |
| TLPP | `tdn_tlpp_v2.json` | `tdn_v2_knowledge_base.md` | Fallback: link para URL do TDN |
| REST API | `tdn_totvstec_rest.json` | `tdn_v2_knowledge_base.md` | Fallback: link para URL do TDN |

- `tdn_framework.json` (não-v2) é arquivo legado, **ignorado** — usar apenas `tdn_framework_v2.json`
- Match de título: case-insensitive, strip pontuação final (ex: "Banco de dados." → "Banco de dados")
- Se não encontrar conteúdo no markdown → mostrar apenas o link "Ver no TDN" com a URL do nó

### 7.2 Transformação para PrimeVue Tree

Os JSONs TDN usam `{ title, url, depth, children }`. O PrimeVue `<Tree>` espera `{ key, label, data, children }`. A transformação recursiva é feita no frontend:

```javascript
function transformNode(node, parentKey = '') {
  const key = parentKey ? `${parentKey}_${node.title}` : node.title
  return {
    key,
    label: node.title,
    data: { url: node.url, depth: node.depth },
    children: (node.children || []).map(c => transformNode(c, key))
  }
}
```

### 7.3 Performance

Os JSONs maiores (advpl: 2.3MB, framework: 1.6MB) são carregados **uma vez por sub-aba**. O PrimeVue Tree faz filtering client-side no dataset completo. Aceitável para uso desktop.

---

## 8. Módulos Abertos

O sistema detecta automaticamente qualquer `.md` na pasta `processoPadrao/`:

- Para adicionar um módulo novo (ex: SIGAPCP), basta criar `processoPadrao/SIGAPCP_Fluxo_PCP.md`
- Aparece na lista da UI sem alteração de código
- O módulo do arquivo é extraído do prefixo do nome (antes do `_`)
- Funciona para qualquer sigla: SIGAEEC, SIGAPCP, SIGARH, etc.

---

## 9. Fora de Escopo

- Edição manual do markdown pela UI (por enquanto só via "Pergunte ao Padrão")
- Versionamento/histórico de alterações do markdown (pode usar git)
- Autenticação de quem fez a pergunta
- Cache de buscas web
- Tradução de conteúdo TDN
