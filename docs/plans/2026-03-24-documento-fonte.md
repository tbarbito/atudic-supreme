# Documento do Fonte — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gerar um documento Markdown completo por fonte ADVPL, com dados do banco + síntese IA, exibido no Explorer e salvo em pasta dedicada.

**Architecture:** Endpoint backend monta 8 seções (7 do banco + 1 IA), salva MD em `knowledge/fontes/`, frontend exibe no painel de detalhe com MarkdownViewer existente. Botão na lista de fontes vinculados da tabela.

**Tech Stack:** Python/FastAPI (backend), Vue 3 + PrimeVue + MarkdownViewer (frontend), SQLite (dados), LiteLLM (síntese IA)

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| **Create** | `backend/services/fonte_doc_generator.py` | Monta as 8 seções do documento a partir do banco + IA |
| **Modify** | `backend/routers/explorer.py` | Novo endpoint `GET /fonte/{arquivo}/documento` |
| **Modify** | `frontend/src/views/ExplorerView.vue` | Botão "Doc" na lista de fontes, painel com MarkdownViewer |

---

## Task 1: Backend — fonte_doc_generator.py

**Files:**
- Create: `backend/services/fonte_doc_generator.py`

### Seções do documento (template):

```markdown
# {arquivo}

> Módulo: {modulo} | Tipo: {source_type} | LOC: {loc} | Encoding: {encoding}

## 1. Funções

| Função | Tipo | Assinatura | Retorno | Resumo |
|--------|------|-----------|---------|--------|
| ... rows from funcao_docs ... |

## 2. Tabelas e Campos

### Leitura
| Tabela | Campos Referenciados |
|--------|---------------------|

### Escrita
| Tabela | Campos Referenciados |
|--------|---------------------|

## 3. Grafo de Chamadas

### Este fonte chama:
- U_FUNCX → ARQUIVO.PRW
- U_FUNCY → ARQUIVO2.PRW

### Chamado por:
- FUNCZ (ARQUIVO3.PRW) → {funcao}

## 4. Pontos de Entrada

| PE | Rotina Afetada |
|----|---------------|

## 5. Menus

| Menu | Rotina | Descrição |
|------|--------|-----------|

## 6. Interação com Padrão

### Campos Customizados nas Tabelas Referenciadas
| Tabela | Campo | Tipo | Tamanho | Título |

### Diferenças vs Padrão
| Tabela | Campo | Ação | Valor Padrão | Valor Cliente |

## 7. Código — Resumo por Função

### {func_name}
```advpl
{first 30 lines of function code}
```

## 8. Síntese

> Gerado por IA com base nas seções anteriores.

{LLM narrative: fluxo, propósito, riscos, recomendações}
```

- [ ] **Step 1: Create fonte_doc_generator.py with section builders**

```python
# backend/services/fonte_doc_generator.py
"""Generate per-fonte Markdown documentation.

Sections 1-7: pure SQL queries (zero LLM cost).
Section 8: LLM synthesis using sections 1-7 as context.
"""
import json
import sqlite3
import asyncio
from pathlib import Path
from typing import Optional


def _safe_json(val) -> list:
    if not val:
        return []
    if isinstance(val, list):
        return val
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return []


def _query_all(conn, sql, params=()):
    return conn.execute(sql, params).fetchall()


def _query_one(conn, sql, params=()):
    return conn.execute(sql, params).fetchone()


def _section_header(arquivo: str, meta: dict) -> str:
    lines = [f"# {arquivo}", ""]
    tags = []
    if meta.get("modulo"):
        tags.append(f"**Módulo:** {meta['modulo']}")
    if meta.get("source_type"):
        tags.append(f"**Tipo:** {meta['source_type']}")
    if meta.get("loc"):
        tags.append(f"**LOC:** {meta['loc']}")
    if meta.get("encoding"):
        tags.append(f"**Encoding:** {meta['encoding']}")
    lines.append(" | ".join(tags))
    lines.append("")
    if meta.get("proposito"):
        lines.append(f"> {meta['proposito']}")
        lines.append("")
    return "\n".join(lines)


def _section_funcoes(conn, arquivo: str) -> str:
    rows = _query_all(conn,
        "SELECT funcao, tipo, assinatura, retorno, resumo "
        "FROM funcao_docs WHERE arquivo=? ORDER BY funcao",
        (arquivo,))
    if not rows:
        return ""
    lines = ["## 1. Funções", "",
             "| Função | Tipo | Assinatura | Retorno | Resumo |",
             "|--------|------|-----------|---------|--------|"]
    for r in rows:
        funcao, tipo, assinatura, retorno, resumo = r
        # Parse resumo JSON if it has ia.resumo
        resumo_text = resumo or ""
        try:
            parsed = json.loads(resumo_text)
            if isinstance(parsed, dict) and "ia" in parsed:
                resumo_text = parsed["ia"].get("resumo", resumo_text)
            elif isinstance(parsed, dict) and "resumo" in parsed:
                resumo_text = parsed["resumo"]
        except (json.JSONDecodeError, TypeError):
            pass
        resumo_text = resumo_text.replace("|", "\\|").replace("\n", " ")[:150]
        lines.append(f"| {funcao} | {tipo or ''} | {assinatura or ''} | {retorno or ''} | {resumo_text} |")
    lines.append("")
    return "\n".join(lines)


def _section_tabelas(conn, arquivo: str) -> str:
    row = _query_one(conn,
        "SELECT tabelas_ref, write_tables, fields_ref FROM fontes WHERE arquivo=?",
        (arquivo,))
    if not row:
        return ""
    tabelas_ref = _safe_json(row[0])
    write_tables = _safe_json(row[1])
    fields_ref = _safe_json(row[2])

    # Group fields by table prefix
    fields_by_table = {}
    for f in fields_ref:
        prefix = f[:2] if len(f) >= 2 else ""
        # Map field prefix to table: A1_ -> SA1, C5_ -> SC5, etc.
        # Try matching against known tables
        for t in tabelas_ref + write_tables:
            if len(t) == 3 and f.startswith(t[1:3] + "_"):
                fields_by_table.setdefault(t, []).append(f)
                break

    lines = ["## 2. Tabelas e Campos", ""]

    if tabelas_ref:
        read_only = [t for t in tabelas_ref if t not in write_tables]
        if read_only:
            lines += ["### Leitura", "",
                      "| Tabela | Campos Referenciados |",
                      "|--------|---------------------|"]
            for t in sorted(read_only):
                campos = ", ".join(sorted(fields_by_table.get(t, [])))
                lines.append(f"| {t} | {campos} |")
            lines.append("")

    if write_tables:
        lines += ["### Escrita", "",
                  "| Tabela | Campos Referenciados |",
                  "|--------|---------------------|"]
        for t in sorted(write_tables):
            campos = ", ".join(sorted(fields_by_table.get(t, [])))
            lines.append(f"| {t} | {campos} |")
        lines.append("")

    return "\n".join(lines)


def _section_grafo(conn, arquivo: str) -> str:
    rows = _query_all(conn,
        "SELECT funcao, chama, chamada_por FROM funcao_docs WHERE arquivo=?",
        (arquivo,))
    if not rows:
        return ""

    all_chama = {}
    all_chamada_por = {}
    for funcao, chama_json, chamada_json in rows:
        for c in _safe_json(chama_json):
            all_chama[c] = funcao
        for c in _safe_json(chamada_json):
            all_chamada_por[c] = funcao

    # Resolve where called functions are defined
    chama_resolved = []
    for called, caller in all_chama.items():
        dest_row = _query_one(conn,
            "SELECT arquivo FROM funcao_docs WHERE funcao=? LIMIT 1",
            (called,))
        dest = dest_row[0] if dest_row else "?"
        chama_resolved.append((caller, called, dest))

    chamada_resolved = []
    for caller, target in all_chamada_por.items():
        src_row = _query_one(conn,
            "SELECT arquivo FROM funcao_docs WHERE funcao=? LIMIT 1",
            (caller,))
        src = src_row[0] if src_row else "?"
        chamada_resolved.append((caller, src, target))

    lines = ["## 3. Grafo de Chamadas", ""]

    if chama_resolved:
        lines += ["### Este fonte chama:", ""]
        for caller, called, dest in sorted(chama_resolved):
            lines.append(f"- `{caller}` → `U_{called}` ({dest})")
        lines.append("")

    if chamada_resolved:
        lines += ["### Chamado por:", ""]
        for caller, src, target in sorted(chamada_resolved):
            lines.append(f"- `{caller}` ({src}) → `{target}`")
        lines.append("")

    if not chama_resolved and not chamada_resolved:
        lines += ["Nenhuma chamada externa detectada.", ""]

    return "\n".join(lines)


def _section_pes(conn, arquivo: str) -> str:
    row = _query_one(conn, "SELECT pontos_entrada FROM fontes WHERE arquivo=?", (arquivo,))
    pes = _safe_json(row[0]) if row else []
    if not pes:
        return ""

    lines = ["## 4. Pontos de Entrada", "",
             "| PE | Rotina Afetada |",
             "|----|---------------|"]

    for pe in pes:
        # Check vinculos for pe_afeta_rotina
        vrow = _query_one(conn,
            "SELECT destino FROM vinculos WHERE tipo='pe_afeta_rotina' AND origem=? LIMIT 1",
            (pe,))
        rotina = vrow[0] if vrow else "—"
        lines.append(f"| {pe} | {rotina} |")

    lines.append("")
    return "\n".join(lines)


def _section_menus(conn, arquivo: str) -> str:
    """Find menus that reference functions in this fonte."""
    row = _query_one(conn, "SELECT funcoes FROM fontes WHERE arquivo=?", (arquivo,))
    funcoes = _safe_json(row[0]) if row else []
    if not funcoes:
        return ""

    menu_hits = []
    for func in funcoes:
        # Check mpmenu table
        try:
            mrows = _query_all(conn,
                "SELECT menu, rotina, descricao FROM mpmenu WHERE rotina LIKE ? LIMIT 5",
                (f"%{func}%",))
            for m in mrows:
                menu_hits.append({"menu": m[0] or "", "rotina": m[1] or "", "descricao": m[2] or ""})
        except Exception:
            pass

        # Check vinculos
        try:
            vrows = _query_all(conn,
                "SELECT origem, destino FROM vinculos WHERE tipo='menu_chama_rotina' AND destino LIKE ?",
                (f"%{func}%",))
            for v in vrows:
                menu_hits.append({"menu": v[0], "rotina": v[1], "descricao": ""})
        except Exception:
            pass

    if not menu_hits:
        return ""

    # Deduplicate
    seen = set()
    unique = []
    for h in menu_hits:
        key = h["rotina"]
        if key not in seen:
            seen.add(key)
            unique.append(h)

    lines = ["## 5. Menus", "",
             "| Menu | Rotina | Descrição |",
             "|------|--------|-----------|"]
    for h in unique:
        lines.append(f"| {h['menu']} | {h['rotina']} | {h['descricao'][:80]} |")
    lines.append("")
    return "\n".join(lines)


def _section_padrao(conn, arquivo: str) -> str:
    """Show custom fields and diffs for tables referenced by this fonte."""
    row = _query_one(conn,
        "SELECT tabelas_ref, write_tables FROM fontes WHERE arquivo=?",
        (arquivo,))
    if not row:
        return ""
    tabelas = list(set(_safe_json(row[0]) + _safe_json(row[1])))
    if not tabelas:
        return ""

    lines = ["## 6. Interação com Padrão", ""]

    # Custom fields in referenced tables
    placeholders = ",".join("?" * len(tabelas))
    try:
        custom_rows = _query_all(conn,
            f"SELECT tabela, campo, tipo, tamanho, titulo FROM campos "
            f"WHERE tabela IN ({placeholders}) AND campo NOT IN "
            f"(SELECT campo FROM padrao_campos WHERE tabela=campos.tabela) "
            f"ORDER BY tabela, campo",
            tabelas)
    except Exception:
        custom_rows = []

    if custom_rows:
        lines += ["### Campos Customizados nas Tabelas Referenciadas", "",
                  "| Tabela | Campo | Tipo | Tamanho | Título |",
                  "|--------|-------|------|---------|--------|"]
        for r in custom_rows[:50]:  # Limit
            lines.append(f"| {r[0]} | {r[1]} | {r[2] or ''} | {r[3] or ''} | {r[4] or ''} |")
        lines.append("")

    # Diffs
    try:
        diff_rows = _query_all(conn,
            f"SELECT tabela, chave, acao, valor_padrao, valor_cliente FROM diff "
            f"WHERE tabela IN ({placeholders}) ORDER BY tabela, chave",
            tabelas)
    except Exception:
        diff_rows = []

    if diff_rows:
        lines += ["### Diferenças vs Padrão", "",
                  "| Tabela | Campo | Ação | Valor Padrão | Valor Cliente |",
                  "|--------|-------|------|-------------|--------------|"]
        for r in diff_rows[:50]:  # Limit
            vp = (r[3] or "")[:40].replace("|", "\\|")
            vc = (r[4] or "")[:40].replace("|", "\\|")
            lines.append(f"| {r[0]} | {r[1]} | {r[2]} | {vp} | {vc} |")
        lines.append("")

    if not custom_rows and not diff_rows:
        lines += ["Nenhuma customização detectada nas tabelas referenciadas.", ""]

    return "\n".join(lines)


def _section_codigo(conn, arquivo: str) -> str:
    """Show first 30 lines of each function."""
    rows = _query_all(conn,
        "SELECT funcao, content FROM fonte_chunks WHERE arquivo=? ORDER BY id",
        (arquivo,))
    if not rows:
        return ""

    lines = ["## 7. Código — Resumo por Função", ""]
    seen = set()
    for funcao, content in rows:
        if funcao in seen or funcao == "_header":
            continue
        seen.add(funcao)
        preview = "\n".join((content or "").splitlines()[:30])
        lines += [f"### {funcao}", "", "```advpl", preview, "```", ""]

    return "\n".join(lines)


async def _section_sintese(sections_text: str, arquivo: str, config: dict) -> str:
    """Generate AI synthesis from sections 1-7."""
    try:
        from litellm import acompletion
    except ImportError:
        return "## 8. Síntese\n\n> LiteLLM não disponível.\n"

    provider = config.get("provider", "anthropic")
    model_name = config.get("model", "claude-sonnet-4-20250514")
    model = f"{provider}/{model_name}" if "/" not in model_name else model_name

    prompt = f"""Você é um analista de sistemas Protheus. Com base na documentação técnica abaixo de um fonte ADVPL customizado, gere uma síntese concisa em português contendo:

1. **Propósito** — O que este programa faz (2-3 frases)
2. **Fluxo Principal** — Passo a passo do processo
3. **Riscos e Atenção** — Pontos críticos, tabelas de escrita, integrações sensíveis
4. **Recomendações** — Melhorias ou cuidados para manutenção

Fonte: {arquivo}

Documentação técnica:
{sections_text[:6000]}

Responda em Markdown, direto ao ponto, sem repetir os dados das tabelas."""

    try:
        response = await acompletion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1500,
            temperature=0.3,
        )
        text = response.choices[0].message.content
    except Exception as e:
        text = f"Erro ao gerar síntese: {e}"

    return f"## 8. Síntese\n\n{text}\n"


async def generate_fonte_doc(
    arquivo: str,
    db_path: Path,
    knowledge_dir: Path,
    llm_config: dict,
) -> dict:
    """Generate complete fonte documentation.

    Returns: {"arquivo": str, "md_path": str, "sections": int}
    """
    conn = sqlite3.connect(str(db_path))
    try:
        # Get basic metadata
        row = _query_one(conn,
            "SELECT arquivo, modulo, lines_of_code, encoding FROM fontes WHERE arquivo=?",
            (arquivo,))
        if not row:
            return {"error": f"Fonte '{arquivo}' not found"}

        meta = {
            "modulo": row[1] or "",
            "source_type": "",
            "loc": row[2] or 0,
            "encoding": row[3] or "cp1252",
            "proposito": "",
        }

        # Get proposito
        try:
            prow = _query_one(conn, "SELECT proposito FROM propositos WHERE chave=?", (arquivo,))
            if prow:
                meta["proposito"] = prow[0] or ""
        except Exception:
            pass

        # Build sections 1-7 from database
        header = _section_header(arquivo, meta)
        sec1 = _section_funcoes(conn, arquivo)
        sec2 = _section_tabelas(conn, arquivo)
        sec3 = _section_grafo(conn, arquivo)
        sec4 = _section_pes(conn, arquivo)
        sec5 = _section_menus(conn, arquivo)
        sec6 = _section_padrao(conn, arquivo)
        sec7 = _section_codigo(conn, arquivo)

        sections_text = "\n".join([header, sec1, sec2, sec3, sec4, sec5, sec6, sec7])

    finally:
        conn.close()

    # Section 8: AI synthesis
    sec8 = await _section_sintese(sections_text, arquivo, llm_config)

    # Assemble full document
    full_doc = sections_text + "\n" + sec8

    # Save to knowledge/fontes/
    fontes_dir = knowledge_dir / "fontes"
    fontes_dir.mkdir(parents=True, exist_ok=True)
    md_path = fontes_dir / f"{arquivo}.md"
    md_path.write_text(full_doc, encoding="utf-8")

    section_count = sum(1 for s in [sec1, sec2, sec3, sec4, sec5, sec6, sec7, sec8] if s.strip())

    return {
        "arquivo": arquivo,
        "md_path": str(md_path),
        "sections": section_count,
        "size": len(full_doc),
    }
```

- [ ] **Step 2: Commit**

```bash
git add backend/services/fonte_doc_generator.py
git commit -m "feat: fonte_doc_generator — 8-section per-fonte documentation"
```

---

## Task 2: Backend — Endpoint no Explorer

**Files:**
- Modify: `backend/routers/explorer.py`

- [ ] **Step 1: Add endpoint GET /fonte/{arquivo}/documento**

Add after the existing `protheusdoc_inject` endpoint:

```python
@router.get("/fonte/{arquivo}/documento")
async def fonte_documento(arquivo: str):
    """Generate or retrieve per-fonte documentation (Markdown)."""
    import asyncio
    from backend.services.fonte_doc_generator import generate_fonte_doc
    from backend.services.config import load_config

    config = load_config()
    client_dir = _get_client_dir()
    knowledge_dir = client_dir / "knowledge" / "cliente"
    db_path = client_dir / "db" / "extrairpo.db"

    # Check if doc already exists
    md_path = knowledge_dir / "fontes" / f"{arquivo}.md"
    if md_path.exists():
        return {
            "arquivo": arquivo,
            "content": md_path.read_text(encoding="utf-8"),
            "cached": True,
        }

    # Generate
    llm_config = {
        "provider": config.llm.get("provider", "anthropic"),
        "model": config.llm.get("model", "claude-sonnet-4-20250514"),
    }

    result = await asyncio.to_thread(
        asyncio.run,
        generate_fonte_doc(arquivo, db_path, knowledge_dir, llm_config)
    )

    if "error" in result:
        raise HTTPException(404, result["error"])

    content = md_path.read_text(encoding="utf-8") if md_path.exists() else ""
    return {
        "arquivo": arquivo,
        "content": content,
        "cached": False,
        **result,
    }


@router.delete("/fonte/{arquivo}/documento")
async def fonte_documento_delete(arquivo: str):
    """Delete cached fonte documentation to force regeneration."""
    client_dir = _get_client_dir()
    md_path = client_dir / "knowledge" / "cliente" / "fontes" / f"{arquivo}.md"
    if md_path.exists():
        md_path.unlink()
        return {"deleted": True}
    return {"deleted": False}
```

- [ ] **Step 2: Commit**

```bash
git add backend/routers/explorer.py
git commit -m "feat: endpoint GET/DELETE /fonte/{arquivo}/documento"
```

---

## Task 3: Frontend — Botão e Visualização

**Files:**
- Modify: `frontend/src/views/ExplorerView.vue`

- [ ] **Step 1: Add state variables**

In the script section, add:

```javascript
// Fonte Document state
const fonteDocContent = ref('')
const fonteDocLoading = ref(false)
const fonteDocArquivo = ref('')
const showFonteDoc = ref(false)
```

- [ ] **Step 2: Add method to load/generate document**

```javascript
async function loadFonteDocumento(arquivo) {
  fonteDocLoading.value = true
  fonteDocArquivo.value = arquivo
  try {
    const { data } = await api.get(`/explorer/fonte/${encodeURIComponent(arquivo)}/documento`)
    fonteDocContent.value = data.content
    showFonteDoc.value = true
  } catch (e) {
    toast.add({ severity: 'error', summary: 'Erro ao gerar documento', detail: e.message, life: 5000 })
  } finally {
    fonteDocLoading.value = false
  }
}

async function regenerateFonteDoc() {
  const arquivo = fonteDocArquivo.value
  fonteDocLoading.value = true
  try {
    await api.delete(`/explorer/fonte/${encodeURIComponent(arquivo)}/documento`)
    const { data } = await api.get(`/explorer/fonte/${encodeURIComponent(arquivo)}/documento`)
    fonteDocContent.value = data.content
    toast.add({ severity: 'success', summary: 'Documento regenerado', life: 3000 })
  } catch (e) {
    toast.add({ severity: 'error', summary: 'Erro', detail: e.message, life: 5000 })
  } finally {
    fonteDocLoading.value = false
  }
}
```

- [ ] **Step 3: Add "Doc" button in fontes DataTable**

In the fontes DataTable (TabPanel "Fontes"), add a new column:

```html
<Column header="" style="width: 60px;">
  <template #body="{ data }">
    <Button icon="pi pi-file" size="small" severity="info" text
      @click="loadFonteDocumento(data.arquivo)"
      :loading="fonteDocLoading && fonteDocArquivo === data.arquivo"
      v-tooltip.top="'Ver Documento'" />
  </template>
</Column>
```

- [ ] **Step 4: Add MarkdownViewer panel for fonte document**

After the TabView, add a conditional panel:

```html
<!-- Fonte Document Viewer -->
<div v-if="showFonteDoc" class="fonte-doc-panel">
  <div class="fonte-doc-toolbar">
    <Button icon="pi pi-arrow-left" label="Voltar" size="small" severity="secondary" text
      @click="showFonteDoc = false" />
    <span class="fonte-doc-title">{{ fonteDocArquivo }}</span>
    <Button icon="pi pi-refresh" label="Regenerar" size="small" severity="warning" text
      @click="regenerateFonteDoc" :loading="fonteDocLoading" />
  </div>
  <MarkdownViewer :content="fonteDocContent" :showToc="true" :showSearch="true" :collapsible="true" />
</div>
```

- [ ] **Step 5: Add CSS**

```css
.fonte-doc-panel { display: flex; flex-direction: column; height: 100%; }
.fonte-doc-toolbar { display: flex; align-items: center; gap: 1rem; padding: 0.8rem 1rem; background: #f8fafc; border-bottom: 1px solid #e2e8f0; flex-shrink: 0; }
.fonte-doc-title { font-weight: 700; font-size: 1rem; color: #1e293b; font-family: 'JetBrains Mono', monospace; }
```

- [ ] **Step 6: Hide main content when doc is showing**

Wrap the existing tabela detail content in a `v-if="!showFonteDoc"` and reset `showFonteDoc` when selecting a new node:

```javascript
// In selectNode or loadTabela:
showFonteDoc.value = false
```

- [ ] **Step 7: Import MarkdownViewer**

```javascript
import MarkdownViewer from '@/components/MarkdownViewer.vue'
```

Add to components if needed.

- [ ] **Step 8: Build and commit**

```bash
cd frontend && npm run build
git add frontend/src/views/ExplorerView.vue frontend/dist/
git commit -m "feat: botão Doc na lista de fontes + MarkdownViewer para documento"
```

---

## Task 4: Teste end-to-end

- [ ] **Step 1: Restart server**
- [ ] **Step 2: Navigate to Explorer → SA2 → Fontes tab**
- [ ] **Step 3: Click "Doc" button on any fonte (e.g., FISVALNFE.PRW)**
- [ ] **Step 4: Verify document loads with all 8 sections**
- [ ] **Step 5: Verify MD was saved to `workspace/clients/marfrig/knowledge/cliente/fontes/FISVALNFE.PRW.md`**
- [ ] **Step 6: Click again — should load from cache (instant)**
- [ ] **Step 7: Click "Regenerar" — should delete and regenerate**
- [ ] **Step 8: Click "Voltar" — should return to tabela detail**

---

## Task 5: Commit final

```bash
git add -A
git commit -m "feat: Documento do Fonte — per-source documentation with AI synthesis"
```
