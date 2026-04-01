# Base Padrão Inteligente Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the Base Padrão into an intelligent wiki with AI-powered enrichment (TDN + Web search) and navigable TDN reference tree.

**Architecture:** New backend router `padrao.py` with enrichment endpoints (search ChromaDB + web, LLM generates answer, insert into markdown). New service `web_search.py` for web scraping. New service `padrao_enricher.py` for orchestration. Frontend: rewrite PadraoView with 2 tabs (Módulos + TDN), add AskPadraoPanel and TdnTreeView components. Existing `docs.py` padrao endpoints changed to read from `processoPadrao/` directly.

**Tech Stack:** FastAPI, httpx (web search), LiteLLM, ChromaDB, Vue 3, PrimeVue (Tree, TabView)

**Spec:** `docs/superpowers/specs/2026-03-19-base-padrao-inteligente-design.md`

---

## File Structure

### New Files

| File | Responsibility |
|------|---------------|
| `backend/services/web_search.py` | Async web search via httpx: Google site-scoped search + HTML text extraction |
| `backend/services/padrao_enricher.py` | Orchestrate enrichment: ChromaDB search + web search + LLM call + markdown insertion |
| `backend/routers/padrao.py` | Endpoints: enriquecer, aplicar, tdn/{tipo}, tdn/{tipo}/content |
| `frontend/src/components/AskPadraoPanel.vue` | Right panel: question input, search button, preview, add/discard |
| `frontend/src/components/TdnTreeView.vue` | Tree navigation from JSON + content display from markdown |

### Modified Files

| File | Changes |
|------|---------|
| `backend/routers/docs.py:25-36` | Change `list_padrao` and `get_padrao` to read from `processoPadrao/` directly |
| `backend/app.py:19-22` | Register new `padrao_router` |
| `frontend/src/views/PadraoView.vue` | Full rewrite: 2 tabs (Módulos + TDN), 3-column layout with AskPadraoPanel |

---

## Chunk 1: Backend — Web Search + Enricher + Endpoints

### Task 1: Create web_search.py

**Files:**
- Create: `backend/services/web_search.py`

- [ ] **Step 1: Create the web search service**

```python
"""Web search service for enrichment — searches TDN and centraldeatendimento.totvs.com."""
import re
import httpx

SEARCH_DOMAINS = [
    "centraldeatendimento.totvs.com",
    "tdn.totvs.com",
]

TIMEOUT = 10.0
MAX_RESULTS = 3


async def search_web(query: str) -> list[dict]:
    """Search the web for TOTVS/Protheus content.

    Uses Google search with site: restriction. Returns list of
    {url, title, snippet} dicts. Best-effort — returns empty on failure.
    """
    site_filter = " OR ".join(f"site:{d}" for d in SEARCH_DOMAINS)
    search_query = f"{query} {site_filter}"
    search_url = "https://www.google.com/search"
    params = {"q": search_query, "num": MAX_RESULTS, "hl": "pt-BR"}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    results = []
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(search_url, params=params, headers=headers)
            if resp.status_code != 200:
                return results

            # Extract URLs from Google results (simple regex on href)
            html = resp.text
            urls = re.findall(r'href="(https?://(?:centraldeatendimento\.totvs|tdn\.totvs)[^"&]+)"', html)
            seen = set()
            for url in urls:
                clean = url.split("&")[0]
                if clean not in seen and len(seen) < MAX_RESULTS:
                    seen.add(clean)
                    results.append({"url": clean, "title": "", "content": ""})
    except Exception:
        return results

    return results


async def fetch_page_text(url: str) -> str:
    """Fetch a URL and extract text content. Returns empty string on failure."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            if resp.status_code != 200:
                return ""
            html = resp.text
            # Strip HTML tags, keep text
            text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
            text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
            text = re.sub(r'<[^>]+>', ' ', text)
            text = re.sub(r'\s+', ' ', text).strip()
            # Limit to 5000 chars to avoid token explosion
            return text[:5000]
    except Exception:
        return ""


async def search_and_fetch(query: str) -> list[dict]:
    """Search web and fetch content from top results.

    Returns list of {url, content} dicts.
    """
    results = await search_web(query)
    enriched = []
    for r in results:
        content = await fetch_page_text(r["url"])
        if content:
            enriched.append({"url": r["url"], "content": content})
    return enriched
```

- [ ] **Step 2: Commit**

```bash
git add backend/services/web_search.py
git commit -m "feat: web search service with Google site-scoped search + HTML extraction"
```

---

### Task 2: Create padrao_enricher.py

**Files:**
- Create: `backend/services/padrao_enricher.py`

- [ ] **Step 1: Create the enrichment service**

```python
"""Orchestrates Base Padrão enrichment: ChromaDB + Web + LLM → markdown insertion."""
import re
from datetime import date
from pathlib import Path
from backend.services.web_search import search_and_fetch

PADRAO_DIR = Path("processoPadrao")

ENRICH_PROMPT = """Você é um especialista em TOTVS Protheus. O usuário está consultando o módulo "{modulo}".

REGRAS ABSOLUTAS:
- Responda APENAS com base nas fontes fornecidas abaixo (TDN, Web, Base Padrão).
- NÃO invente funcionalidades, parâmetros ou comportamentos que não estejam nas fontes.
- Se não encontrar informação suficiente nas fontes, diga EXPLICITAMENTE que não encontrou.
- Formate a resposta em Markdown.
- Indique a seção do documento onde a resposta deve ser inserida.

SEÇÕES EXISTENTES NO DOCUMENTO:
{secoes_existentes}

FONTES TDN:
{contexto_tdn}

FONTES WEB:
{contexto_web}

FONTES BASE PADRÃO:
{contexto_padrao}

PERGUNTA DO USUÁRIO:
{pergunta}

Responda APENAS no formato JSON válido:
{{"encontrou": true/false, "secao_sugerida": "nome da seção existente ou nova", "resposta_md": "conteúdo markdown formatado", "fontes": ["fonte1", "fonte2"]}}
"""


def _get_existing_sections(content: str) -> list[str]:
    """Extract h2 section titles from markdown content."""
    return re.findall(r'^## (.+)$', content, re.MULTILINE)


async def enrich(slug: str, pergunta: str, vs, llm) -> dict:
    """Search sources and generate enrichment preview.

    Args:
        slug: module filename stem (e.g. SIGACOM_Fluxo_Compras)
        pergunta: user question
        vs: VectorStore instance (initialized)
        llm: LLMService instance

    Returns:
        dict with keys: encontrou, secao_sugerida, resposta_md, fontes
    """
    md_path = PADRAO_DIR / f"{slug}.md"
    if not md_path.exists():
        return {"encontrou": False, "secao_sugerida": "", "resposta_md": "", "fontes": []}

    content = md_path.read_text(encoding="utf-8")
    secoes = _get_existing_sections(content)

    # 1. ChromaDB: TDN collection
    tdn_results = vs.search("tdn", pergunta, n_results=5)
    contexto_tdn = "\n\n".join([r["content"] for r in tdn_results]) if tdn_results else "Nenhum resultado no TDN."

    # 2. ChromaDB: padrao collection (other modules)
    padrao_results = vs.search("padrao", pergunta, n_results=3)
    contexto_padrao = "\n\n".join([r["content"] for r in padrao_results]) if padrao_results else "Nenhum resultado na base padrão."

    # 3. Web search (best-effort)
    web_results = await search_and_fetch(pergunta + " TOTVS Protheus")
    contexto_web = "\n\n".join([f"URL: {r['url']}\n{r['content']}" for r in web_results]) if web_results else "Nenhum resultado web."

    # 4. LLM call
    modulo = slug.split("_")[0] if "_" in slug else slug
    prompt = ENRICH_PROMPT.format(
        modulo=modulo,
        secoes_existentes="\n".join(f"- {s}" for s in secoes) if secoes else "Nenhuma seção encontrada.",
        contexto_tdn=contexto_tdn[:8000],
        contexto_web=contexto_web[:5000],
        contexto_padrao=contexto_padrao[:5000],
        pergunta=pergunta,
    )

    import json
    raw = llm._call(
        [{"role": "user", "content": prompt}],
        temperature=0.2,
        use_gen=True,
    )

    # Parse JSON response
    try:
        # Strip markdown code fences if present
        clean = re.sub(r'^```json\s*', '', raw.strip())
        clean = re.sub(r'\s*```$', '', clean)
        result = json.loads(clean)
    except json.JSONDecodeError:
        result = {
            "encontrou": False,
            "secao_sugerida": "",
            "resposta_md": raw,
            "fontes": [],
        }

    # Add web URLs to fontes
    for wr in web_results:
        if wr["url"] not in result.get("fontes", []):
            result.setdefault("fontes", []).append(wr["url"])

    return result


def apply_enrichment(slug: str, resposta_md: str, secao_sugerida: str, fontes: list[str], pergunta: str) -> str:
    """Insert enrichment into the module markdown file.

    Returns the updated content.
    """
    md_path = PADRAO_DIR / f"{slug}.md"
    if not md_path.exists():
        raise FileNotFoundError(f"File not found: {md_path}")

    content = md_path.read_text(encoding="utf-8")
    today = date.today().strftime("%d/%m/%Y")
    fontes_str = ", ".join(fontes) if fontes else "N/A"

    # Build enrichment block
    block = f"\n\n> 📋 Adicionado em {today} | Fontes: {fontes_str}\n> Pergunta: {pergunta}\n\n{resposta_md}\n"

    # Try to find the target section (case-insensitive, strip punctuation)
    lines = content.split("\n")
    target_lower = re.sub(r'[^\w\s]', '', secao_sugerida.lower()).strip()
    insert_idx = None

    for i, line in enumerate(lines):
        if line.startswith("## "):
            section_title = line[3:].strip()
            section_lower = re.sub(r'[^\w\s]', '', section_title.lower()).strip()
            if section_lower == target_lower:
                # Found the section — scan forward to next ## or EOF
                for j in range(i + 1, len(lines)):
                    if lines[j].startswith("## "):
                        insert_idx = j
                        break
                else:
                    insert_idx = len(lines)  # End of file
                break

    if insert_idx is not None:
        # Insert before the next section
        lines.insert(insert_idx, block)
    else:
        # Section not found — create new section at end
        lines.append(f"\n## {secao_sugerida}")
        lines.append(block)

    updated = "\n".join(lines)
    md_path.write_text(updated, encoding="utf-8")
    return updated
```

- [ ] **Step 2: Commit**

```bash
git add backend/services/padrao_enricher.py
git commit -m "feat: padrao enricher — ChromaDB + Web + LLM orchestration + markdown insertion"
```

---

### Task 3: Create padrao router

**Files:**
- Create: `backend/routers/padrao.py`

- [ ] **Step 1: Create the router with all endpoints**

```python
"""Router for Base Padrão intelligence: enrichment + TDN tree navigation."""
import json
import re
from pathlib import Path
from fastapi import APIRouter, HTTPException
from backend.services.padrao_ingestor import ingest_padrao, PADRAO_DIR, TDN_DIR

router = APIRouter(prefix="/api/padrao", tags=["padrao"])

# TDN JSON file mapping
TDN_MAP = {
    "advpl": {
        "json": "advpl_tdn_tree.json",
        "markdown": "advpl_tdn_knowledge_base.md",
    },
    "framework": {
        "json": "tdn_framework_v2.json",
        "markdown": "framework_tdn_knowledge_base.md",
    },
    "tlpp": {
        "json": "tdn_tlpp_v2.json",
        "markdown": "tdn_v2_knowledge_base.md",
    },
    "rest": {
        "json": "tdn_totvstec_rest.json",
        "markdown": "tdn_v2_knowledge_base.md",
    },
}


def _get_vs_and_llm():
    """Get VectorStore and LLM instances from shared services."""
    from backend.routers.chat import _get_services as get_shared_services
    db, vs, ks, llm, client_dir = get_shared_services()
    return vs, llm


@router.post("/{slug}/enriquecer")
async def enriquecer(slug: str, body: dict):
    """Search TDN + Web and return enrichment preview."""
    pergunta = body.get("pergunta", "").strip()
    if not pergunta:
        raise HTTPException(400, "Pergunta é obrigatória")

    md_path = PADRAO_DIR / f"{slug}.md"
    if not md_path.exists():
        raise HTTPException(404, f"Módulo '{slug}' não encontrado")

    vs, llm = _get_vs_and_llm()

    from backend.services.padrao_enricher import enrich
    result = await enrich(slug, pergunta, vs, llm)
    return result


@router.post("/{slug}/aplicar")
async def aplicar(slug: str, body: dict):
    """Apply approved enrichment to the module markdown."""
    resposta_md = body.get("resposta_md", "")
    secao_sugerida = body.get("secao_sugerida", "")
    fontes = body.get("fontes", [])
    pergunta = body.get("pergunta", "")

    if not resposta_md:
        raise HTTPException(400, "resposta_md é obrigatória")

    from backend.services.padrao_enricher import apply_enrichment
    try:
        apply_enrichment(slug, resposta_md, secao_sugerida, fontes, pergunta)
    except FileNotFoundError:
        raise HTTPException(404, f"Módulo '{slug}' não encontrado")

    # Re-ingest the updated doc into ChromaDB
    vs, _ = _get_vs_and_llm()
    ingest_padrao(vs)

    return {"status": "ok", "slug": slug}


@router.get("/tdn/{tipo}")
async def get_tdn_tree(tipo: str):
    """Return the TDN JSON tree for navigation."""
    if tipo not in TDN_MAP:
        raise HTTPException(400, f"tipo must be one of: {list(TDN_MAP.keys())}")

    json_path = TDN_DIR / TDN_MAP[tipo]["json"]
    if not json_path.exists():
        raise HTTPException(404, f"TDN file not found: {json_path.name}")

    return json.loads(json_path.read_text(encoding="utf-8"))


@router.get("/tdn/{tipo}/content")
async def get_tdn_content(tipo: str, title: str = ""):
    """Search TDN markdown for content matching a tree node title."""
    if tipo not in TDN_MAP:
        raise HTTPException(400, f"tipo must be one of: {list(TDN_MAP.keys())}")

    if not title:
        raise HTTPException(400, "title parameter is required")

    md_filename = TDN_MAP[tipo]["markdown"]
    md_path = TDN_DIR / md_filename
    if not md_path.exists():
        return {"title": title, "content": "", "found": False, "url": ""}

    content = md_path.read_text(encoding="utf-8")

    # Match section by title (case-insensitive, strip trailing punctuation)
    title_clean = re.sub(r'[^\w\s]', '', title.lower()).strip()
    sections = re.split(r'^(## .+)$', content, flags=re.MULTILINE)

    for i in range(1, len(sections), 2):
        header = sections[i]
        header_clean = re.sub(r'[^\w\s]', '', header[3:].lower()).strip()
        if header_clean == title_clean:
            body = sections[i + 1] if i + 1 < len(sections) else ""
            return {
                "title": title,
                "content": header + "\n" + body.strip(),
                "found": True,
            }

    return {"title": title, "content": "", "found": False}
```

- [ ] **Step 2: Commit**

```bash
git add backend/routers/padrao.py
git commit -m "feat: padrao router — enriquecer, aplicar, TDN tree + content endpoints"
```

---

### Task 4: Modify docs.py padrao endpoints + register router

**Files:**
- Modify: `backend/routers/docs.py:25-36`
- Modify: `backend/app.py:7-22`

- [ ] **Step 1: Update docs.py padrao endpoints to read from processoPadrao/ directly**

In `backend/routers/docs.py`, replace the `list_padrao` and `get_padrao` functions (lines 25-36):

```python
@router.get("/docs/padrao")
async def list_padrao():
    from backend.services.padrao_ingestor import list_padrao_docs
    docs = list_padrao_docs()
    return [{"slug": d["arquivo"].replace(".md", ""), "filename": d["arquivo"], "size": d["size"], "modulo": d["modulo"]} for d in docs]

@router.get("/docs/padrao/{slug}")
async def get_padrao(slug: str):
    from pathlib import Path
    md_path = Path("processoPadrao") / f"{slug}.md"
    if not md_path.exists():
        raise HTTPException(404, "Document not found")
    content = md_path.read_text(encoding="utf-8")
    return {"slug": slug, "content": content}
```

- [ ] **Step 2: Register padrao router in app.py**

In `backend/app.py`, add import and include after line 8:

```python
from backend.routers.padrao import router as padrao_router
```

And add after line 22:

```python
app.include_router(padrao_router)
```

- [ ] **Step 3: Verify backend starts**

Run: `cd d:/IA/Projetos/Protheus && .venv/Scripts/python -c "from backend.app import app; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/routers/docs.py backend/app.py
git commit -m "feat: padrao endpoints read from processoPadrao/ directly + register padrao router"
```

---

## Chunk 2: Frontend — AskPadraoPanel + TdnTreeView + PadraoView Rewrite

### Task 5: Create AskPadraoPanel component

**Files:**
- Create: `frontend/src/components/AskPadraoPanel.vue`

- [ ] **Step 1: Create the component**

```vue
<template>
  <div class="ask-panel">
    <div class="panel-title">
      <i class="pi pi-question-circle"></i>
      Pergunte ao Padrão
    </div>

    <div class="ask-form">
      <Textarea
        v-model="pergunta"
        placeholder="Ex: Na cotação tem como definir fornecedores padrão por produto?"
        :autoResize="true"
        rows="3"
        class="w-full"
      />
      <Button
        label="Pesquisar"
        icon="pi pi-search"
        @click="pesquisar"
        :loading="searching"
        :disabled="!pergunta.trim() || !slug"
        class="w-full"
      />
    </div>

    <!-- Preview result -->
    <div v-if="result" class="result-area">
      <div class="result-header">
        <Tag :severity="result.encontrou ? 'success' : 'warn'" :value="result.encontrou ? 'Encontrado' : 'Não encontrado'" />
        <span v-if="result.secao_sugerida" class="section-hint">
          Seção: {{ result.secao_sugerida }}
        </span>
      </div>

      <div class="result-preview md-content" v-html="renderedPreview"></div>

      <div v-if="result.fontes?.length" class="result-fontes">
        <div class="fontes-title">Fontes consultadas:</div>
        <div v-for="f in result.fontes" :key="f" class="fonte-item">
          <a v-if="f.startsWith('http')" :href="f" target="_blank" rel="noopener">{{ truncateUrl(f) }}</a>
          <span v-else>{{ f }}</span>
        </div>
      </div>

      <div class="result-actions">
        <Button
          label="Adicionar ao Doc"
          icon="pi pi-check"
          @click="aplicar"
          :loading="applying"
          severity="success"
          size="small"
        />
        <Button
          label="Descartar"
          icon="pi pi-times"
          @click="result = null"
          severity="secondary"
          size="small"
        />
      </div>
    </div>

    <!-- Status messages -->
    <Message v-if="successMsg" severity="success" :closable="true" @close="successMsg = ''" class="mt-05">
      {{ successMsg }}
    </Message>
    <Message v-if="errorMsg" severity="error" :closable="true" @close="errorMsg = ''" class="mt-05">
      {{ errorMsg }}
    </Message>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import Textarea from 'primevue/textarea'
import Button from 'primevue/button'
import Tag from 'primevue/tag'
import Message from 'primevue/message'
import { useMarkdown } from '../composables/useMarkdown'
import api from '../api'

const props = defineProps({
  slug: { type: String, default: '' },
})

const emit = defineEmits(['enriched'])

const { md } = useMarkdown()
const pergunta = ref('')
const searching = ref(false)
const applying = ref(false)
const result = ref(null)
const successMsg = ref('')
const errorMsg = ref('')

const renderedPreview = computed(() => {
  if (!result.value?.resposta_md) return ''
  return md.render(result.value.resposta_md)
})

function truncateUrl(url) {
  try {
    const u = new URL(url)
    return u.hostname + u.pathname.slice(0, 40) + (u.pathname.length > 40 ? '...' : '')
  } catch { return url }
}

async function pesquisar() {
  if (!pergunta.value.trim() || !props.slug) return
  searching.value = true
  errorMsg.value = ''
  result.value = null
  try {
    const { data } = await api.post(`/padrao/${props.slug}/enriquecer`, {
      pergunta: pergunta.value.trim(),
    })
    result.value = data
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || 'Erro ao pesquisar'
  }
  searching.value = false
}

async function aplicar() {
  if (!result.value) return
  applying.value = true
  try {
    await api.post(`/padrao/${props.slug}/aplicar`, {
      resposta_md: result.value.resposta_md,
      secao_sugerida: result.value.secao_sugerida,
      fontes: result.value.fontes || [],
      pergunta: pergunta.value.trim(),
    })
    successMsg.value = 'Informação adicionada ao documento!'
    result.value = null
    pergunta.value = ''
    emit('enriched')
  } catch (e) {
    errorMsg.value = e.response?.data?.detail || 'Erro ao aplicar'
  }
  applying.value = false
}
</script>

<style scoped>
.ask-panel {
  display: flex;
  flex-direction: column;
  gap: 0.8rem;
  height: 100%;
  overflow-y: auto;
}

.panel-title {
  font-weight: 700;
  font-size: 0.95rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: var(--totvs-primary, #00a1e0);
}

.ask-form { display: flex; flex-direction: column; gap: 0.5rem; }
.w-full { width: 100%; }

.result-area {
  border: 1px solid #e0e0e0;
  border-radius: 6px;
  padding: 0.8rem;
  background: var(--bg-page, #f5f7fa);
}

.result-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}

.section-hint {
  font-size: 0.8rem;
  color: var(--text-secondary, #666);
  font-style: italic;
}

.result-preview {
  max-height: 300px;
  overflow-y: auto;
  padding: 0.5rem;
  background: white;
  border-radius: 4px;
  font-size: 0.85rem;
  margin-bottom: 0.5rem;
}

.result-fontes { margin-bottom: 0.5rem; }
.fontes-title { font-size: 0.75rem; font-weight: 600; color: var(--text-muted, #999); margin-bottom: 0.3rem; }
.fonte-item { font-size: 0.78rem; padding: 0.1rem 0; }
.fonte-item a { color: var(--totvs-primary, #00a1e0); text-decoration: none; }
.fonte-item a:hover { text-decoration: underline; }

.result-actions { display: flex; gap: 0.5rem; }
.mt-05 { margin-top: 0.5rem; }
</style>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/AskPadraoPanel.vue
git commit -m "feat: AskPadraoPanel — question input, AI search preview, add/discard"
```

---

### Task 6: Create TdnTreeView component

**Files:**
- Create: `frontend/src/components/TdnTreeView.vue`

- [ ] **Step 1: Create the component**

```vue
<template>
  <div class="tdn-tree-view">
    <TabView v-model:activeIndex="tabIdx" @tab-change="onTabChange">
      <TabPanel v-for="tab in tabs" :key="tab.key" :header="tab.label" />
    </TabView>

    <div class="tdn-layout">
      <!-- Left: Tree -->
      <div class="tree-panel">
        <InputText v-model="treeFilter" placeholder="Buscar na árvore..." size="small" class="w-full tree-search" />
        <div class="tree-container">
          <Tree
            :value="filteredNodes"
            :filter="false"
            selectionMode="single"
            v-model:selectionKeys="selectedKeys"
            @node-select="onNodeSelect"
            class="tree-component"
          />
          <div v-if="loading" class="tree-loading">
            <i class="pi pi-spin pi-spinner"></i> Carregando...
          </div>
        </div>
      </div>

      <!-- Right: Content -->
      <div class="content-panel">
        <div v-if="nodeContent" class="node-content">
          <MarkdownViewer :content="nodeContent" :showToc="false" :showSearch="false" :collapsible="false" />
          <a v-if="nodeUrl" :href="nodeUrl" target="_blank" rel="noopener" class="tdn-link">
            <i class="pi pi-external-link"></i> Ver no TDN
          </a>
        </div>
        <div v-else-if="nodeUrl && !nodeContent" class="no-content">
          <p>Conteúdo não disponível no markdown local.</p>
          <a :href="nodeUrl" target="_blank" rel="noopener" class="tdn-link">
            <i class="pi pi-external-link"></i> Ver no TDN
          </a>
        </div>
        <div v-else class="placeholder">
          <i class="pi pi-sitemap" style="font-size: 2rem; color: #ccc;"></i>
          <p>Selecione um item na árvore</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import TabView from 'primevue/tabview'
import TabPanel from 'primevue/tabpanel'
import InputText from 'primevue/inputtext'
import Tree from 'primevue/tree'
import MarkdownViewer from './MarkdownViewer.vue'
import api from '../api'

const tabs = [
  { key: 'advpl', label: 'AdvPL' },
  { key: 'framework', label: 'Framework' },
  { key: 'tlpp', label: 'TLPP' },
  { key: 'rest', label: 'REST API' },
]

const tabIdx = ref(0)
const treeData = ref([])
const treeFilter = ref('')
const selectedKeys = ref(null)
const nodeContent = ref('')
const nodeUrl = ref('')
const loading = ref(false)

const currentTab = computed(() => tabs[tabIdx.value]?.key || 'advpl')

// Transform TDN JSON nodes to PrimeVue Tree format
function transformNode(node, parentKey = '') {
  const key = parentKey ? `${parentKey}__${node.title}` : node.title
  return {
    key,
    label: node.title,
    data: { url: node.url || '', depth: node.depth || 0 },
    children: (node.children || []).map(c => transformNode(c, key)),
  }
}

// Filter tree nodes by search term
function filterNodes(nodes, term) {
  if (!term) return nodes
  const lower = term.toLowerCase()
  const result = []
  for (const node of nodes) {
    const childMatches = filterNodes(node.children || [], term)
    if (node.label.toLowerCase().includes(lower) || childMatches.length > 0) {
      result.push({ ...node, children: childMatches })
    }
  }
  return result
}

const filteredNodes = computed(() => filterNodes(treeData.value, treeFilter.value))

async function loadTree() {
  loading.value = true
  treeData.value = []
  nodeContent.value = ''
  nodeUrl.value = ''
  selectedKeys.value = null
  try {
    const { data } = await api.get(`/padrao/tdn/${currentTab.value}`)
    treeData.value = data.map(n => transformNode(n))
  } catch {}
  loading.value = false
}

function onTabChange() {
  treeFilter.value = ''
  loadTree()
}

async function onNodeSelect(node) {
  nodeContent.value = ''
  nodeUrl.value = node.data?.url || ''
  try {
    const { data } = await api.get(`/padrao/tdn/${currentTab.value}/content`, {
      params: { title: node.label },
    })
    if (data.found) {
      nodeContent.value = data.content
    }
  } catch {}
}

// Load initial tree
watch(() => tabIdx.value, () => {}, { immediate: true })
loadTree()
</script>

<style scoped>
.tdn-tree-view {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.tdn-layout {
  display: flex;
  flex: 1;
  overflow: hidden;
  gap: 0;
}

.tree-panel {
  width: 280px;
  flex-shrink: 0;
  border-right: 1px solid #e0e0e0;
  display: flex;
  flex-direction: column;
}

.tree-search { margin: 0.5rem; }
.w-full { width: 100%; }

.tree-container {
  flex: 1;
  overflow-y: auto;
  padding: 0 0.3rem;
}

.tree-component {
  font-size: 0.82rem;
  border: none;
  padding: 0;
}

.tree-loading {
  padding: 1rem;
  color: var(--text-muted, #999);
  font-size: 0.85rem;
}

.content-panel {
  flex: 1;
  overflow-y: auto;
  padding: 1rem;
}

.node-content {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.tdn-link {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  color: var(--totvs-primary, #00a1e0);
  text-decoration: none;
  font-size: 0.85rem;
  margin-top: 0.5rem;
}

.tdn-link:hover { text-decoration: underline; }

.no-content {
  padding: 2rem;
  text-align: center;
  color: var(--text-secondary, #666);
}

.placeholder {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  color: #999;
  padding: 3rem;
}
</style>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/TdnTreeView.vue
git commit -m "feat: TdnTreeView — PrimeVue Tree from TDN JSON + content lookup"
```

---

### Task 7: Rewrite PadraoView

**Files:**
- Modify: `frontend/src/views/PadraoView.vue` (full rewrite)

- [ ] **Step 1: Rewrite with 2 tabs + 3-column layout**

Replace entire `frontend/src/views/PadraoView.vue`:

```vue
<template>
  <div class="padrao-view">
    <h1>Base Padrão Protheus</h1>
    <TabView v-model:activeIndex="mainTab">
      <!-- Tab: Módulos -->
      <TabPanel header="Módulos">
        <div class="three-col">
          <!-- Left: Doc list -->
          <div class="doc-list-panel">
            <div class="search-field">
              <InputText v-model="filter" placeholder="Filtrar módulo..." size="small" class="w-full" />
            </div>
            <ul class="doc-list">
              <li
                v-for="doc in filteredDocs"
                :key="doc.slug"
                @click="select(doc.slug)"
                :class="{ active: selected === doc.slug }"
              >
                <span class="doc-name">{{ doc.slug }}</span>
                <Tag v-if="doc.modulo" :value="doc.modulo" severity="info" class="doc-tag" />
              </li>
              <li v-if="!filteredDocs.length" class="empty">
                {{ filter ? 'Nenhum resultado' : 'Nenhum módulo encontrado' }}
              </li>
            </ul>
          </div>

          <!-- Center: Content -->
          <div class="content-panel">
            <MarkdownViewer
              v-if="rawContent"
              :key="contentKey"
              :content="rawContent"
              :showToc="true"
              :showSearch="true"
              :collapsible="true"
            />
            <div v-else class="placeholder">
              <i class="pi pi-book" style="font-size: 2rem; color: #ccc;"></i>
              <p>Selecione um módulo padrão</p>
            </div>
          </div>

          <!-- Right: Ask panel -->
          <div class="ask-panel-container" v-if="selected">
            <AskPadraoPanel :slug="selected" @enriched="reloadContent" />
          </div>
        </div>
      </TabPanel>

      <!-- Tab: Referência TDN -->
      <TabPanel header="Referência TDN">
        <div class="tdn-container">
          <TdnTreeView />
        </div>
      </TabPanel>
    </TabView>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import TabView from 'primevue/tabview'
import TabPanel from 'primevue/tabpanel'
import InputText from 'primevue/inputtext'
import Tag from 'primevue/tag'
import MarkdownViewer from '../components/MarkdownViewer.vue'
import AskPadraoPanel from '../components/AskPadraoPanel.vue'
import TdnTreeView from '../components/TdnTreeView.vue'
import api from '../api'

const mainTab = ref(0)
const docs = ref([])
const selected = ref('')
const rawContent = ref('')
const contentKey = ref(0)
const filter = ref('')

const filteredDocs = computed(() => {
  if (!filter.value) return docs.value
  const q = filter.value.toLowerCase()
  return docs.value.filter((d) =>
    d.slug.toLowerCase().includes(q) || (d.modulo || '').toLowerCase().includes(q)
  )
})

onMounted(async () => {
  try {
    const { data } = await api.get('/docs/padrao')
    docs.value = data
  } catch {}
})

async function select(slug) {
  selected.value = slug
  const { data } = await api.get(`/docs/padrao/${slug}`)
  rawContent.value = data.content
  contentKey.value++
}

async function reloadContent() {
  if (selected.value) {
    const { data } = await api.get(`/docs/padrao/${selected.value}`)
    rawContent.value = data.content
    contentKey.value++
  }
}
</script>

<style scoped>
.padrao-view { height: calc(100vh - 6rem); display: flex; flex-direction: column; }
.padrao-view h1 { margin-bottom: 0.8rem; font-size: 1.3rem; }

.three-col {
  display: flex;
  flex: 1;
  gap: 0;
  overflow: hidden;
  background: var(--bg-card, white);
  border-radius: 8px;
  border: 1px solid #e0e0e0;
  height: calc(100vh - 14rem);
}

.doc-list-panel {
  width: 220px;
  border-right: 1px solid #e0e0e0;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}

.search-field { padding: 0.6rem; }
.w-full { width: 100%; }

.doc-list {
  flex: 1;
  overflow-y: auto;
  list-style: none;
  padding: 0;
  margin: 0;
}

.doc-list li {
  padding: 0.55rem 0.8rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 0.85rem;
  border-bottom: 1px solid #f0f0f0;
}

.doc-list li:hover { background: #f5f7fa; }
.doc-list li.active { background: #e3f2fd; border-left: 3px solid var(--totvs-primary, #00a1e0); }
.doc-list .empty { color: #999; font-style: italic; padding: 1rem; }
.doc-tag { font-size: 0.6rem; }

.content-panel {
  flex: 1;
  overflow: hidden;
  padding: 1rem;
  display: flex;
  flex-direction: column;
}

.ask-panel-container {
  width: 300px;
  flex-shrink: 0;
  border-left: 1px solid #e0e0e0;
  padding: 0.8rem;
  overflow-y: auto;
}

.placeholder {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  color: #999;
}

.tdn-container {
  height: calc(100vh - 14rem);
  background: var(--bg-card, white);
  border-radius: 8px;
  border: 1px solid #e0e0e0;
  overflow: hidden;
}
</style>
```

- [ ] **Step 2: Verify build**

Run: `cd d:/IA/Projetos/Protheus/frontend && npm run build`
Expected: Build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/PadraoView.vue
git commit -m "feat: PadraoView rewrite — Módulos tab with AskPadraoPanel + TDN tab"
```

---

## Chunk 3: Build + Test + Verify

### Task 8: Frontend Production Build

- [ ] **Step 1: Build frontend**

Run: `cd d:/IA/Projetos/Protheus/frontend && npm run build`
Expected: Build succeeds.

- [ ] **Step 2: Commit build**

```bash
git add -f frontend/dist/
git commit -m "feat: frontend production build with Base Padrão Inteligente"
```

---

### Task 9: Run Backend Tests

- [ ] **Step 1: Run tests**

Run: `cd d:/IA/Projetos/Protheus && .venv/Scripts/python -m pytest tests/ -v`
Expected: Same pass/fail as before (29 pass, 5 pre-existing failures). No new failures.

- [ ] **Step 2: Verify padrao endpoints**

Run: `cd d:/IA/Projetos/Protheus && .venv/Scripts/python -c "from backend.routers.padrao import router; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Verify enricher import**

Run: `cd d:/IA/Projetos/Protheus && .venv/Scripts/python -c "from backend.services.padrao_enricher import enrich, apply_enrichment; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit any fixes**

```bash
git add -A
git commit -m "fix: resolve any issues from Base Padrão implementation"
```

---

### Task 10: Integration Verification

- [ ] **Step 1: Start the app**

Run: `cd d:/IA/Projetos/Protheus && python run.py`

- [ ] **Step 2: Verify in browser**

Check at http://localhost:8741/padrao:
- Tab "Módulos": 6 modules in list, MarkdownViewer renders on click, "Pergunte ao Padrão" panel on right
- Tab "Referência TDN": 4 sub-tabs, tree loads and is navigable, content appears on node click
- Enrichment flow: ask a question → preview → add to doc → content updates
