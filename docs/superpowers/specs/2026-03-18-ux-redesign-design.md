# ExtraiRPO — UX Redesign: Visual TOTVS + Markdown Premium + Fluxogramas + Export

**Data:** 2026-03-18
**Status:** Aprovado
**Abordagem:** PrimeVue + Mermaid.js + markdown-it

---

## 1. Objetivo

Melhorar a experiência do usuário do ExtraiRPO em 4 frentes:

1. **Visual TOTVS-aligned** — identidade visual alinhada ao ecossistema TOTVS
2. **Markdown premium** — renderização bonita + interativa (collapse, TOC, busca, tabelas ricas)
3. **Fluxogramas** — diagramas Mermaid gerados pelo LLM + auto-gerados a partir do layer `ia`
4. **Export** — selecionar docs da base do cliente e baixar como markdown (.md ou .zip)

---

## 2. Design System — Identidade Visual TOTVS

### 2.1 Paleta de Cores

| Token | Cor | Uso |
|-------|-----|-----|
| `--primary` | `#00a1e0` | Azul TOTVS — botões, links, ações primárias |
| `--secondary` | `#f47920` | Laranja TOTVS — destaques, badges custom |
| `--bg-page` | `#f5f7fa` | Background geral |
| `--bg-card` | `#ffffff` | Cards e painéis |
| `--bg-sidebar` | `#1e2a3a` | Sidebar (azul escuro) |
| `--text-primary` | `#333333` | Texto principal |
| `--text-secondary` | `#666666` | Texto secundário |
| `--success` | `#28a745` | Operações concluídas |
| `--danger` | `#dc3545` | Erros, exclusões |
| `--warning` | `#ffc107` | Alertas, rate-limit |

### 2.2 Tipografia

- **Font family:** Inter (sans-serif) — usada no ecossistema TOTVS Carol
- **Headers:** Inter SemiBold
- **Body:** Inter Regular, 14px
- **Code:** JetBrains Mono, 13px

### 2.3 PrimeVue — Tema e Componentes

**Tema:** Aura customizado com CSS tokens TOTVS acima.

**Componentes utilizados:**

| Componente | Onde |
|------------|------|
| `PanelMenu` | Sidebar — navegação hierárquica com ícones |
| `Breadcrumb` | Topo — caminho contextual |
| `Card` | Containers de conteúdo em todas as views |
| `DataTable` | Listagens de tabelas, campos, docs, fontes |
| `Tag` | Badges de módulo, status, tipo |
| `Accordion` | Seções colapsáveis nos docs |
| `Toolbar` | Ações contextuais (exportar, regenerar, buscar) |
| `SplitButton` | Botão exportar com opções |
| `Toast` | Feedback de operações (sucesso, erro) |
| `ProgressBar` | Progresso de ingestão e geração |
| `Steps` | Wizard do setup (3 fases) |
| `InputText`, `Password`, `Dropdown` | Forms (config, setup) |
| `Dialog` | Modais (fluxograma fullscreen, confirmações) |
| `TabView` | Toggle humano/ia na ClienteView |
| `InputIcon` / `IconField` | Campo de busca com ícone |

### 2.4 Layout Geral

```
┌─────────────────────────────────────────────────┐
│  ┌──────────┬──────────────────────────────────┐ │
│  │          │  Breadcrumb: Home > Docs > ...   │ │
│  │  SIDEBAR │──────────────────────────────────│ │
│  │  240px   │                                  │ │
│  │          │  Conteúdo principal               │ │
│  │  Logo    │  (varia por view)                │ │
│  │  Menu    │                                  │ │
│  │  Cliente │                                  │ │
│  │  ativo   │                                  │ │
│  │          │                                  │ │
│  └──────────┴──────────────────────────────────┘ │
└─────────────────────────────────────────────────┘
```

**Sidebar:**
- Logo ExtraiRPO no topo
- Cliente ativo com badge
- Menu PanelMenu:
  - Setup (ícone: `pi-cog`)
  - Chat (ícone: `pi-comments`)
  - Gerar Docs (ícone: `pi-file-edit`)
  - Docs Padrão (ícone: `pi-book`)
  - Docs Cliente (ícone: `pi-folder-open`)
  - Configurações (ícone: `pi-sliders-h`)

---

## 3. Renderização de Markdown Premium

### 3.1 Stack

Substituir `marked` por:

- **markdown-it** — parser extensível
- **markdown-it-anchor** — IDs nos headers para navegação
- **markdown-it-toc-done-right** — geração automática de TOC
- **markdown-it-container** — blocos customizados (dica, alerta, aviso)
- **highlight.js** — syntax highlight (ADVPL, SQL, JSON)
- **mermaid** — renderiza blocos ```mermaid inline

### 3.2 Componente MarkdownViewer.vue

Componente reutilizável usado em PadraoView, ClienteView e ChatView.

**Props:**
- `content: string` — markdown raw
- `showToc: boolean` — exibe TOC lateral (default true)
- `showSearch: boolean` — campo de busca interna (default true)
- `collapsible: boolean` — seções como Accordion (default true)

**Features:**
- **TOC lateral** com scroll-spy (destaca seção visível ao rolar)
- **Seções colapsáveis** — cada `##` vira um painel Accordion, expandido por default
- **Busca interna** — highlight nos matches, scroll até o primeiro resultado
- **Tabelas ricas** — tabelas markdown renderizadas como DataTable PrimeVue (sort por coluna)
- **Blocos de código** — highlight.js com tema que combine com TOTVS, botão "copiar"
- **Blocos Mermaid** — detecta ```mermaid e renderiza diagramas inline
- **Blocos customizados** — `::: dica`, `::: alerta`, `::: aviso` com ícones e cores

### 3.3 Layout do Visualizador de Docs (3 colunas)

```
┌──────────┬─────────────────────────┬──────────┐
│ Lista    │  Toolbar                │  TOC     │
│ de Docs  │  [↻ Regen] [⬇ Export▾] │  Lateral │
│          │─────────────────────────│          │
│ [busca]  │                         │  • Visão │
│          │  Conteúdo Markdown       │  • Tab.  │
│ doc1     │  renderizado com:        │  • Camp. │
│ doc2 ●   │  - Accordion             │  • Fluxo │
│ doc3     │  - DataTable             │  • Res.  │
│          │  - Mermaid               │          │
│          │  - Highlight.js          │          │
│          │  - Blocos customizados   │          │
└──────────┴─────────────────────────┴──────────┘
```

- **Coluna esquerda (220px):** Lista de docs com busca e badge de módulo
- **Coluna central (flex):** Conteúdo renderizado com toolbar no topo
- **Coluna direita (180px):** TOC gerado automaticamente com scroll-spy

---

## 4. Fluxogramas

### 4.1 Geração pelo LLM (layer humano)

**Ajuste no prompt `AGENT_DOCUMENTADOR`** em `backend/services/llm.py`:

Adicionar na instrução da seção "Fluxo do Processo":

> "Gere o fluxo do processo em formato Mermaid (flowchart TD). Use os nomes das tabelas como nós. Indique aprovações com nós diamond. Use cores: #00a1e0 para início, #28a745 para conclusão, #dc3545 para rejeição/erro. Exemplo de formato:
> ```mermaid
> flowchart TD
>     A[Pedido SC7] --> B{Aprovação?}
>     B -->|Sim| C[Documento SF1]
>     B -->|Não| D[Retorna]
> ```"

O bloco Mermaid gerado fica dentro do markdown normal e é renderizado pelo `MarkdownViewer`.

### 4.2 Geração automática a partir do layer `ia` (FlowDiagram.vue)

**Componente `FlowDiagram.vue`:**

Lê o YAML frontmatter do layer `ia` e gera um diagrama Mermaid automaticamente:

- **Tabelas** → nós retangulares (azul TOTVS `#00a1e0`)
- **Relacionamentos** → setas entre tabelas
- **Gatilhos** → setas tracejadas com label do campo
- **Fontes custom** → nós destacados (laranja `#f47920`)
- **Pontos de entrada** → nós hexagonais

**Props:**
- `yamlData: object` — frontmatter parseado do layer ia
- `fullscreen: boolean` — modo modal expandido

**Uso na ClienteView:**
- Tab "Humano": mostra o markdown com Mermaid inline (gerado pelo LLM)
- Tab "IA": mostra o YAML + botão "Ver Fluxo" que abre o `FlowDiagram` em modal

### 4.3 Renderização

Ambas as fontes usam **Mermaid.js** para renderizar:

- Tema: `theme: 'base'` com variáveis customizadas (cores TOTVS)
- Zoom/pan em diagramas grandes (click para fullscreen em Dialog)
- Export do diagrama como PNG (botão no canto do diagrama)

---

## 5. Exportação de Markdown

### 5.1 Frontend

**Toolbar do visualizador** com `SplitButton`:

| Opção | Comportamento |
|-------|---------------|
| Exportar este doc | Download `.md` do doc atual |
| Exportar seleção | Checkbox na lista de docs → download `.zip` |
| Exportar todos | Download `.zip` com todos os docs do cliente |

**Opções no modal de export:**
- Layer: `humano` / `ia` / `ambos` (radio buttons)
- Incluir fluxogramas Mermaid: checkbox (default: sim)

### 5.2 Backend

**Novo endpoint:** `POST /api/docs/export`

```python
# Request body
{
    "slugs": ["compras_marfrig", "faturamento_marfrig"],  # ou ["*"] para todos
    "layer": "humano",          # "humano" | "ia" | "ambos"
    "include_mermaid": true
}

# Response
# Se 1 doc: Content-Type: text/markdown, attachment .md
# Se múltiplos: Content-Type: application/zip, attachment .zip
#   zip structure:
#     humano/
#       compras_marfrig.md
#       faturamento_marfrig.md
#     ia/
#       compras_marfrig.md
#       faturamento_marfrig.md
```

**Implementação:** Novo arquivo `backend/routers/export.py` com lógica de empacotamento.

---

## 6. Views — Mudanças por Tela

### 6.1 App.vue
- Sidebar: trocar HTML/CSS manual por PanelMenu PrimeVue
- Adicionar Breadcrumb no topo da área de conteúdo
- Badge do cliente ativo na sidebar
- Toast global para feedback

### 6.2 SetupView.vue
- Wizard com `Steps` PrimeVue (Fase 1, 2, 3)
- Cards PrimeVue para formulário
- `ProgressBar` PrimeVue para progresso de ingestão
- Lista de clientes como `DataTable` com ações (ativar, excluir)

### 6.3 ChatView.vue
- Output usa `MarkdownViewer` (com Mermaid e highlight)
- Input estilizado com PrimeVue
- Sidebar de fontes consultadas com `Tag` badges

### 6.4 PadraoView.vue
- Layout 3 colunas com `MarkdownViewer`
- Lista de docs com busca e badge de módulo
- TOC lateral com scroll-spy

### 6.5 ClienteView.vue
- Layout 3 colunas com `MarkdownViewer`
- `TabView` para toggle humano/ia
- Tab ia: `FlowDiagram` component
- Toolbar com export `SplitButton`
- Checkbox de seleção na lista para export em lote

### 6.6 GerarDocsView.vue
- `DataTable` PrimeVue para seleção de tabelas/fontes (com checkbox, sort, filter)
- `Tag` badges para módulo e contagem de customizações
- Summary cards com ícones no topo

### 6.7 ConfigView.vue
- Forms PrimeVue (`InputText`, `Password`, `Dropdown`)
- `Card` por seção (API Keys, Modelos, Usage)
- Usage como mini-dashboard com números formatados

---

## 7. Novos Componentes

| Componente | Responsabilidade |
|------------|-----------------|
| `MarkdownViewer.vue` | Renderização markdown com TOC, busca, collapse, Mermaid, highlight |
| `FlowDiagram.vue` | Gera Mermaid a partir do YAML frontmatter do layer ia |
| `ExportDialog.vue` | Modal de opções de export (layer, mermaid, seleção) |

---

## 8. Dependências Novas

### Frontend (package.json)

| Pacote | Versão | Propósito |
|--------|--------|-----------|
| `primevue` | ^4.x | Component library |
| `primeicons` | ^7.x | Ícones |
| `@primeuix/themes` | ^1.x | Tema Aura customizável |
| `markdown-it` | ^14.x | Parser markdown extensível |
| `markdown-it-anchor` | ^9.x | IDs nos headers |
| `markdown-it-toc-done-right` | ^4.x | TOC automático |
| `markdown-it-container` | ^4.x | Blocos customizados |
| `mermaid` | ^11.x | Renderização de diagramas |
| `highlight.js` | ^11.x | Syntax highlight |
| `file-saver` | ^2.x | Download helper |

### Frontend — Remover

| Pacote | Motivo |
|--------|--------|
| `marked` | Substituído por markdown-it |

### Backend (requirements.txt)

| Pacote | Propósito |
|--------|-----------|
| `pyyaml` | Parsing YAML frontmatter do layer ia |

---

## 9. Ajustes no Backend

### 9.1 Prompt do AGENT_DOCUMENTADOR

**Arquivo:** `backend/services/llm.py` (ou `doc_pipeline.py` onde o prompt é definido)

Adicionar instrução para gerar blocos Mermaid na seção "Fluxo do Processo".

### 9.2 Endpoint Export em docs.py

Adicionar `POST /api/docs/export` em `backend/routers/docs.py` (mesmo arquivo dos endpoints `/api/docs/*` existentes).

### 9.3 YAML Frontmatter Parsing

Ajustar `GET /api/docs/cliente/ia/{slug}` para retornar `frontmatter` como campo JSON separado (parseado com `pyyaml` no backend).

### 9.4 Nenhuma outra mudança estrutural no backend

O backend já serve o frontend estático e todos os endpoints existentes continuam iguais.

---

## 10. Fora de Escopo

- Exportação PDF (futuro)
- Autenticação/autorização
- Internacionalização (i18n)
- Testes E2E do frontend
- Refatoração de services do backend
- Mobile responsive (foco desktop)

---

## 11. Detalhes Técnicos de Implementação

### 11.1 Setup PrimeVue 4.x no main.js

```javascript
import { createApp } from 'vue'
import PrimeVue from 'primevue/config'
import Aura from '@primeuix/themes/aura'
import ToastService from 'primevue/toastservice'
import 'primeicons/primeicons.css'

import App from './App.vue'
import router from './router'

const app = createApp(App)

app.use(PrimeVue, {
  theme: {
    preset: Aura,
    options: {
      prefix: 'p',
      darkModeSelector: false,
      cssLayer: false
    }
  },
  pt: {  // PassThrough para override de tokens TOTVS
    global: {
      css: `
        :root {
          --p-primary-color: #00a1e0;
          --p-primary-contrast-color: #ffffff;
          --p-surface-0: #ffffff;
          --p-surface-50: #f5f7fa;
          --p-surface-900: #1e2a3a;
          --p-text-color: #333333;
          --p-text-muted-color: #666666;
        }
      `
    }
  }
})

app.use(ToastService)
app.use(router)
app.mount('#app')
```

**Modo:** Styled (não unstyled) — aproveitamos os estilos base do Aura e sobrescrevemos tokens.

### 11.2 Estratégia de Renderização do MarkdownViewer

**Abordagem escolhida: Pós-processamento DOM + slots Vue dinâmicos**

O MarkdownViewer usa uma estratégia em 3 fases:

1. **Parse:** markdown-it converte markdown em HTML string
2. **Split:** O HTML é dividido nas fronteiras de `<h2>` para criar painéis do Accordion
3. **Render + Post-process:** Cada painel é renderizado via `v-html`, e no `onMounted`/`onUpdated`:
   - `querySelectorAll('pre code')` → chama `hljs.highlightElement()`
   - `querySelectorAll('.language-mermaid')` → chama `mermaid.run({ nodes: [...] })`
   - `querySelectorAll('table')` → aplica classes CSS PrimeVue (não converte em DataTable Vue; usa apenas o estilo `p-datatable` via classes CSS para manter simplicidade)

**Justificativa:** Converter tabelas markdown em componentes Vue DataTable reais exigiria parsing de HTML → dados estruturados → mount dinâmico, complexidade desproporcional ao benefício. Em vez disso, aplicamos as classes CSS do PrimeVue DataTable (`p-datatable`, `p-datatable-thead`, etc.) nas `<table>` existentes para obter o visual consistente sem a complexidade de montagem dinâmica de componentes.

**Ciclo de vida do Accordion:**
```
markdown string
  → markdown-it.render()
  → HTML string
  → split no regex /<h2[^>]*>(.*?)<\/h2>/
  → Array de { title: string, html: string }
  → v-for com AccordionTab
      → cada tab.html via v-html
      → nextTick → post-process (highlight, mermaid, table styles)
```

### 11.3 Mermaid — Inicialização e Lifecycle

```javascript
// Em MarkdownViewer.vue (setup)
import mermaid from 'mermaid'

mermaid.initialize({
  startOnLoad: false,  // controle manual
  theme: 'base',
  themeVariables: {
    primaryColor: '#00a1e0',
    primaryTextColor: '#fff',
    primaryBorderColor: '#0080b3',
    secondaryColor: '#f47920',
    tertiaryColor: '#f5f7fa',
    lineColor: '#666666',
    fontFamily: 'Inter, sans-serif'
  }
})

// Após cada render de markdown (nextTick):
async function renderMermaidBlocks(container) {
  const nodes = container.querySelectorAll('pre code.language-mermaid')
  for (const node of nodes) {
    const id = `mermaid-${crypto.randomUUID()}`
    const { svg } = await mermaid.render(id, node.textContent)
    node.closest('pre').outerHTML = `<div class="mermaid-diagram">${svg}</div>`
  }
}
```

**Re-render:** Quando `content` prop muda, o watcher chama `renderMermaidBlocks()` no `nextTick`.

### 11.4 Scroll-spy TOC

**Mecanismo:** IntersectionObserver nos elementos `<h2>` e `<h3>` dentro dos painéis expandidos do Accordion.

- Observer criado no `onMounted` com `rootMargin: '-20% 0px -70% 0px'` (ativa quando heading está no terço superior)
- Quando um heading entra no viewport, o TOC destaca o item correspondente
- Quando um AccordionTab é expandido/colapsado, o observer é recriado para os novos headings visíveis

### 11.5 ADVPL Syntax Highlight

highlight.js não inclui gramática ADVPL nativa. Registrar gramática customizada:

```javascript
import hljs from 'highlight.js/lib/core'
// Registrar linguagens necessárias
import javascript from 'highlight.js/lib/languages/javascript'
import sql from 'highlight.js/lib/languages/sql'
import json from 'highlight.js/lib/languages/json'

hljs.registerLanguage('javascript', javascript)
hljs.registerLanguage('sql', sql)
hljs.registerLanguage('json', json)

// ADVPL como extensão de xBase
hljs.registerLanguage('advpl', function(hljs) {
  return {
    case_insensitive: true,
    keywords: {
      keyword: 'function user static return local private public if else elseif endif do while enddo for next begin end class method endclass endmethod',
      built_in: 'MsgAlert MsgInfo MsgYesNo MsgStop DbSelectArea DbSetOrder DbSeek RecLock MsUnlock Replace Conout FwAlertSuccess',
      literal: '.T. .F. NIL'
    },
    contains: [
      hljs.COMMENT('//', '$'),
      hljs.COMMENT('/\\*', '\\*/'),
      hljs.QUOTE_STRING_MODE,
      hljs.NUMBER_MODE
    ]
  }
})
```

### 11.6 YAML Frontmatter — Parsing

**Abordagem:** Backend retorna o frontmatter como campo JSON separado.

Ajustar o endpoint `GET /api/docs/cliente/ia/{slug}` em `docs.py` para retornar:

```json
{
  "slug": "compras_marfrig",
  "content": "... markdown sem frontmatter ...",
  "frontmatter": {
    "processo": "compras",
    "modulo": "SIGACOM",
    "tabelas": ["SC7", "SC8", "SF1"],
    "relacionamentos": [...],
    "gatilhos": [...],
    "fontes_custom": [...],
    "pontos_entrada": [...]
  }
}
```

Isso evita adicionar `js-yaml` no frontend. O backend já tem acesso ao markdown raw e pode parsear o YAML com `yaml` (stdlib-like, já disponível via pyyaml no ecossistema).

**Dependência backend:** Adicionar `pyyaml` ao `requirements.txt`.

### 11.7 Export — Simplificação

**Decisão:** Zip é montado no backend (zipfile stdlib). Frontend usa apenas `file-saver` para download do blob.

**Remover `jszip`** da lista de dependências frontend — não é necessário.

### 11.8 Export Router — Localização

**Decisão:** O endpoint `POST /api/docs/export` fica em `backend/routers/docs.py` (mesmo arquivo dos endpoints `/api/docs/*` existentes) para manter a coesão de namespace. Não criar `export.py` separado.

### 11.9 Largura Mínima

**Desktop mínimo:** 1280px. Abaixo disso, o TOC lateral é ocultado automaticamente (toggle via botão).

Em telas 1280px: 240 (sidebar) + 220 (lista) + 180 (TOC) = 640px fixo → 640px para conteúdo. Suficiente.

### 11.10 Ordem de Implementação Sugerida

1. **PrimeVue setup + App.vue shell** (sidebar, breadcrumb, tema)
2. **MarkdownViewer.vue** (componente core: markdown-it, highlight, mermaid, accordion, TOC)
3. **PadraoView** (primeira view a usar MarkdownViewer — mais simples, sem export)
4. **ClienteView** (MarkdownViewer + FlowDiagram + export + tabs humano/ia)
5. **FlowDiagram.vue** (componente de fluxo a partir do YAML ia)
6. **GerarDocsView** (DataTable PrimeVue para seleção)
7. **ChatView** (MarkdownViewer no output do chat)
8. **SetupView** (Steps wizard, ProgressBar)
9. **ConfigView** (forms PrimeVue)
10. **Backend: prompt Mermaid + endpoint export + YAML parsing**

---

## 12. Dependências — Versão Corrigida

### Frontend (package.json)

| Pacote | Versão | Propósito |
|--------|--------|-----------|
| `primevue` | ^4.x | Component library |
| `primeicons` | ^7.x | Ícones |
| `@primeuix/themes` | ^1.x | Tema Aura customizável |
| `markdown-it` | ^14.x | Parser markdown extensível |
| `markdown-it-anchor` | ^9.x | IDs nos headers |
| `markdown-it-toc-done-right` | ^4.x | TOC automático |
| `markdown-it-container` | ^4.x | Blocos customizados |
| `mermaid` | ^11.x | Renderização de diagramas |
| `highlight.js` | ^11.x | Syntax highlight |
| `file-saver` | ^2.x | Download helper |

### Frontend — Remover

| Pacote | Motivo |
|--------|--------|
| `marked` | Substituído por markdown-it |

### Backend (requirements.txt)

| Pacote | Propósito |
|--------|-----------|
| `pyyaml` | Parsing YAML frontmatter do layer ia |
