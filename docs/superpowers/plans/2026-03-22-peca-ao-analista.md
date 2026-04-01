# Peca ao Analista — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a new "Peca ao Analista" view where consultants describe needs in natural language, the AI investigates the client database, and generates project documents (1 gerencial MD + N technical MDs).

**Architecture:** New backend router (`analista.py`) with SSE streaming chat, reusing existing tools (analise-impacto, cruzamento, enriquecer, knowledge). New Vue view with two modes: project cards list and chat+artifacts panel. SQLite tables for projects, messages, artifacts, documents.

**Tech Stack:** FastAPI + SSE (sse-starlette), Vue 3 + PrimeVue, SQLite, LiteLLM

---

## File Structure

### Backend (new files)
- `backend/routers/analista.py` — Router with 10 endpoints (CRUD projetos, chat SSE, artefatos, documentos)
- `backend/services/analista_tools.py` — Internal tools the AI calls silently (wraps existing endpoints as functions)
- `backend/services/analista_prompts.py` — System prompts and document templates

### Backend (modify)
- `backend/app.py` — Register analista router (1 import + 1 include_router)

### Frontend (new files)
- `frontend/src/views/AnalistaView.vue` — Main view with cards list + chat+panel modes

### Frontend (modify)
- `frontend/src/router.js` — Add route for /analista

---

## Chunk 1: Backend Foundation (SQLite + CRUD + Router)

### Task 1: Create analista_tools.py — Internal tool wrappers

**Files:**
- Create: `backend/services/analista_tools.py`

These are pure functions that wrap existing analysis capabilities for the AI chat to call silently.

- [ ] **Step 1: Create the tools module**

```python
"""Internal tools for the Analista AI — wraps existing analysis functions."""
import json
from pathlib import Path
from backend.services.config import load_config, get_client_workspace
from backend.services.database import Database

WORKSPACE = Path("workspace")
CONFIG_PATH = Path("config.json")


def _get_db() -> Database:
    config = load_config(CONFIG_PATH)
    client_dir = get_client_workspace(WORKSPACE, config.active_client)
    db_path = client_dir / "db" / "extrairpo.db"
    return Database(db_path)


def _safe_json(val):
    if not val:
        return []
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return []


def tool_analise_impacto(tabela: str, campo: str = "", alteracao: str = "novo_campo") -> dict:
    """Run impact analysis for a table/field change. Returns filtered results (write-only)."""
    db = _get_db()
    try:
        # Get fontes that WRITE to this table (bom senso: ignore read-only)
        fontes_rows = db.execute(
            "SELECT arquivo, modulo, write_tables, pontos_entrada, lines_of_code "
            "FROM fontes WHERE write_tables LIKE ?",
            (f'%"{tabela}"%',),
        ).fetchall()

        fontes = []
        for r in fontes_rows:
            fontes.append({
                "arquivo": r[0],
                "modulo": r[1] or "",
                "write_tables": _safe_json(r[2]),
                "pontos_entrada": _safe_json(r[3]),
                "loc": r[4] or 0,
            })

        # Get triggers related to this table
        gatilhos = []
        gat_rows = db.execute(
            "SELECT campo_origem, campo_destino, regra, tipo FROM gatilhos WHERE tabela=?",
            (tabela,),
        ).fetchall()
        for g in gat_rows:
            gatilhos.append({
                "campo_origem": g[0], "campo_destino": g[1],
                "regra": g[2] or "", "tipo": g[3] or "",
            })

        # Get existing custom fields
        campos_custom = []
        cc_rows = db.execute(
            "SELECT campo, tipo, tamanho, titulo, descricao FROM campos WHERE upper(tabela)=? AND custom=1",
            (tabela.upper(),),
        ).fetchall()
        for c in cc_rows:
            campos_custom.append({
                "campo": c[0], "tipo": c[1], "tamanho": c[2],
                "titulo": c[3] or "", "descricao": c[4] or "",
            })

        return {
            "tabela": tabela,
            "fontes_escrita": fontes,
            "gatilhos": gatilhos,
            "campos_custom": campos_custom,
            "total_fontes_escrita": len(fontes),
        }
    finally:
        db.close()


def tool_buscar_pes(rotina: str = "", modulo: str = "") -> list[dict]:
    """Find standard PEs for a routine or module."""
    db = _get_db()
    try:
        if rotina:
            rows = db.execute(
                "SELECT nome, objetivo, modulo, rotina FROM padrao_pes WHERE upper(rotina) LIKE ?",
                (f"%{rotina.upper()}%",),
            ).fetchall()
        elif modulo:
            rows = db.execute(
                "SELECT nome, objetivo, modulo, rotina FROM padrao_pes WHERE upper(modulo) LIKE ?",
                (f"%{modulo.upper()}%",),
            ).fetchall()
        else:
            rows = []
        return [{"nome": r[0], "objetivo": r[1] or "", "modulo": r[2] or "", "rotina": r[3] or ""} for r in rows]
    finally:
        db.close()


def tool_buscar_fontes_tabela(tabela: str, modo: str = "escrita") -> list[dict]:
    """Find fontes that read or write a table. modo: 'escrita'|'leitura'|'todos'."""
    db = _get_db()
    try:
        if modo == "escrita":
            rows = db.execute(
                "SELECT arquivo, modulo, write_tables, pontos_entrada, lines_of_code "
                "FROM fontes WHERE write_tables LIKE ?",
                (f'%"{tabela}"%',),
            ).fetchall()
        elif modo == "leitura":
            rows = db.execute(
                "SELECT arquivo, modulo, write_tables, pontos_entrada, lines_of_code "
                "FROM fontes WHERE tabelas_ref LIKE ? AND write_tables NOT LIKE ?",
                (f'%"{tabela}"%', f'%"{tabela}"%'),
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT arquivo, modulo, write_tables, pontos_entrada, lines_of_code "
                "FROM fontes WHERE tabelas_ref LIKE ? OR write_tables LIKE ?",
                (f'%"{tabela}"%', f'%"{tabela}"%'),
            ).fetchall()

        result = []
        for r in rows:
            # Get overview if exists
            overview = ""
            pr = db.execute("SELECT proposito FROM propositos WHERE chave=?", (r[0],)).fetchone()
            if pr and pr[0]:
                try:
                    parsed = json.loads(pr[0])
                    overview = parsed.get("humano", "")
                except (json.JSONDecodeError, TypeError):
                    overview = pr[0][:200] if pr[0] else ""

            result.append({
                "arquivo": r[0],
                "modulo": r[1] or "",
                "write_tables": _safe_json(r[2]),
                "pes": _safe_json(r[3]),
                "loc": r[4] or 0,
                "overview": overview,
            })
        return result
    finally:
        db.close()


def tool_info_tabela(tabela: str) -> dict:
    """Get table info: name, fields count, custom fields, indices."""
    db = _get_db()
    try:
        row = db.execute(
            "SELECT codigo, nome FROM tabelas WHERE upper(codigo)=?", (tabela.upper(),)
        ).fetchone()
        if not row:
            return {"tabela": tabela, "existe": False}

        total = db.execute("SELECT COUNT(*) FROM campos WHERE upper(tabela)=?", (tabela.upper(),)).fetchone()[0]
        custom = db.execute("SELECT COUNT(*) FROM campos WHERE upper(tabela)=? AND custom=1", (tabela.upper(),)).fetchone()[0]
        indices = db.execute("SELECT COUNT(*) FROM indices WHERE upper(tabela)=?", (tabela.upper(),)).fetchone()[0]

        return {
            "tabela": row[0], "nome": row[1], "existe": True,
            "total_campos": total, "campos_custom": custom, "indices": indices,
        }
    finally:
        db.close()


def tool_gerar_overview_fonte(arquivo: str) -> str:
    """Generate overview for a fonte if missing. Returns overview text."""
    db = _get_db()
    try:
        # Check if already has overview
        pr = db.execute("SELECT proposito FROM propositos WHERE chave=?", (arquivo,)).fetchone()
        if pr and pr[0]:
            try:
                parsed = json.loads(pr[0])
                return parsed.get("humano", pr[0])
            except (json.JSONDecodeError, TypeError):
                return pr[0]

        # No overview — need to generate (will be done via enriquecer endpoint call)
        return ""
    finally:
        db.close()
```

- [ ] **Step 2: Commit**

```bash
git add backend/services/analista_tools.py
git commit -m "feat(analista): add internal tool wrappers for AI analyst"
```

---

### Task 2: Create analista_prompts.py — System prompts and templates

**Files:**
- Create: `backend/services/analista_prompts.py`

- [ ] **Step 1: Create the prompts module**

```python
"""Prompts and templates for the Analista AI."""

SYSTEM_PROMPT = """Voce e um analista tecnico senior de ambientes TOTVS Protheus.
O usuario e um consultor funcional ou analista de negocio. Ele descreve necessidades e voce investiga e propoe solucoes tecnicas.

COMPORTAMENTO:
- Seja direto e objetivo, como um consultor senior. Sem enrolacao.
- Nas primeiras mensagens, faca 2-4 perguntas de negocio para entender o escopo.
- Depois de entender, proponha a solucao tecnica de forma enxuta.
- Explique o "porque" so quando o usuario pedir.
- Use BOM SENSO: so traga informacoes relevantes ao escopo.
  - Se o usuario quer alterar gravacao na SA1, ignore relatorios que so leem SA1.
  - Foque em: fontes que ESCREVEM, integracoes, PEs, gatilhos, validacoes.
- Quando encontrar fontes sem overview que sao relevantes, gere silenciosamente.

FORMATO:
- Texto conversacional limpo no chat. Sem tabelas enormes, sem dumps de dados.
- Quando sugerir artefatos para o projeto (campos, PEs, fontes, tabelas), inclua ao final da mensagem:
###ARTEFATOS###
[{"tipo": "campo|pe|fonte|tabela|gatilho", "nome": "NOME", "tabela": "SA1", "acao": "criar|alterar", "descricao": "breve"}]

CONTEXTO DO AMBIENTE DO CLIENTE:
{context}

ARTEFATOS JA NO PROJETO:
{artefatos}

HISTORICO DE FERRAMENTAS USADAS:
{tool_results}
"""

TEMPLATE_GERENCIAL = """# {nome_projeto} — Projeto Gerencial

## 1. Resumo Executivo

{resumo}

## 2. Justificativa

{justificativa}

## 3. Escopo

### Itens a Criar/Alterar

{escopo_itens}

## 4. Fluxo do Processo

```mermaid
{fluxo_mermaid}
```

## 5. Estimativa de Esforco

{estimativa}

## 6. Riscos e Pontos de Atencao

{riscos}

---
*Gerado por ExtraiRPO — Peca ao Analista*
"""

TEMPLATE_TECNICO_CAMPO = """# Especificacao Tecnica — Campo {nome}

## Informacoes do Campo

| Propriedade | Valor |
|---|---|
| Campo | {nome} |
| Tabela | {tabela} |
| Tipo | {tipo} |
| Tamanho | {tamanho} |
| Titulo | {titulo} |
| Descricao | {descricao} |

## Validacao

{validacao}

## Inicializador

{inicializador}

## Gatilhos

{gatilhos}

## Impactos

{impactos}

---
*Gerado por ExtraiRPO — Peca ao Analista*
"""

TEMPLATE_TECNICO_PE = """# Especificacao Tecnica — Ponto de Entrada {nome}

## Informacoes

| Propriedade | Valor |
|---|---|
| Nome | {nome} |
| Rotina Padrao | {rotina} |
| Modulo | {modulo} |

## Objetivo

{objetivo}

## PARAMIXB

{paramixb}

## Logica Esperada

{logica}

## Retorno

{retorno}

---
*Gerado por ExtraiRPO — Peca ao Analista*
"""

TEMPLATE_TECNICO_FONTE = """# Especificacao Tecnica — Fonte {nome}

## Informacoes

| Propriedade | Valor |
|---|---|
| Arquivo | {nome} |
| Modulo | {modulo} |
| Tipo | {tipo} |

## Objetivo

{objetivo}

## Funcoes

{funcoes}

## Tabelas

{tabelas}

## Fluxo

```mermaid
{fluxo}
```

---
*Gerado por ExtraiRPO — Peca ao Analista*
"""

PROMPT_GERAR_PROJETO = """Com base na conversa e artefatos do projeto, gere a documentacao completa.

PROJETO: {nome_projeto}
DESCRICAO: {descricao}

ARTEFATOS DEFINIDOS:
{artefatos_json}

CONTEXTO TECNICO DO AMBIENTE:
{contexto_tecnico}

Gere um JSON com esta estrutura:
{{
  "gerencial": {{
    "resumo": "texto",
    "justificativa": "texto",
    "escopo_itens": "markdown com lista",
    "fluxo_mermaid": "flowchart TD ...",
    "estimativa": "markdown com tabela",
    "riscos": "markdown com lista"
  }},
  "tecnicos": [
    {{
      "tipo": "campo|pe|fonte",
      "nome": "NOME",
      "conteudo": {{ ... campos do template ... }}
    }}
  ]
}}
"""
```

- [ ] **Step 2: Commit**

```bash
git add backend/services/analista_prompts.py
git commit -m "feat(analista): add system prompts and document templates"
```

---

### Task 3: Create analista.py router — CRUD + Chat SSE

**Files:**
- Create: `backend/routers/analista.py`
- Modify: `backend/app.py:5-10` (add import) and `backend/app.py:21-26` (add include_router)

- [ ] **Step 1: Create the router with SQLite table creation and CRUD endpoints**

```python
"""Router for Peca ao Analista: AI-driven project analysis."""
import json
import asyncio
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
from backend.services.config import load_config, get_client_workspace
from backend.services.database import Database

router = APIRouter(prefix="/api/analista", tags=["analista"])

WORKSPACE = Path("workspace")
CONFIG_PATH = Path("config.json")


def _get_db() -> Database:
    config = load_config(CONFIG_PATH)
    if not config or not config.active_client:
        raise HTTPException(400, "No active client")
    client_dir = get_client_workspace(WORKSPACE, config.active_client)
    db_path = client_dir / "db" / "extrairpo.db"
    return Database(db_path)


def _ensure_tables(db: Database):
    """Create analista tables if they don't exist."""
    db.execute("""CREATE TABLE IF NOT EXISTS analista_projetos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        descricao TEXT,
        status TEXT DEFAULT 'rascunho',
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS analista_mensagens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        projeto_id INTEGER NOT NULL REFERENCES analista_projetos(id),
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        tool_data TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS analista_artefatos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        projeto_id INTEGER NOT NULL REFERENCES analista_projetos(id),
        tipo TEXT NOT NULL,
        nome TEXT NOT NULL,
        tabela TEXT,
        acao TEXT DEFAULT 'criar',
        spec TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS analista_documentos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        projeto_id INTEGER NOT NULL REFERENCES analista_projetos(id),
        tipo TEXT NOT NULL,
        titulo TEXT NOT NULL,
        conteudo TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now'))
    )""")
    db.commit()


# ─── CRUD Projetos ───

class ProjetoCreate(BaseModel):
    nome: str
    descricao: str = ""

class ProjetoUpdate(BaseModel):
    nome: str | None = None
    status: str | None = None


@router.get("/projetos")
async def list_projetos():
    db = _get_db()
    try:
        _ensure_tables(db)
        rows = db.execute(
            "SELECT id, nome, descricao, status, created_at, updated_at "
            "FROM analista_projetos ORDER BY updated_at DESC"
        ).fetchall()
        projetos = []
        for r in rows:
            msg_count = db.execute(
                "SELECT COUNT(*) FROM analista_mensagens WHERE projeto_id=?", (r[0],)
            ).fetchone()[0]
            art_count = db.execute(
                "SELECT COUNT(*) FROM analista_artefatos WHERE projeto_id=?", (r[0],)
            ).fetchone()[0]
            projetos.append({
                "id": r[0], "nome": r[1], "descricao": r[2] or "",
                "status": r[3], "created_at": r[4], "updated_at": r[5],
                "mensagens": msg_count, "artefatos": art_count,
            })
        return projetos
    finally:
        db.close()


@router.post("/projetos")
async def create_projeto(body: ProjetoCreate):
    db = _get_db()
    try:
        _ensure_tables(db)
        db.execute(
            "INSERT INTO analista_projetos (nome, descricao) VALUES (?, ?)",
            (body.nome, body.descricao),
        )
        db.commit()
        pid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        return {"id": pid, "nome": body.nome, "status": "rascunho"}
    finally:
        db.close()


@router.put("/projetos/{projeto_id}")
async def update_projeto(projeto_id: int, body: ProjetoUpdate):
    db = _get_db()
    try:
        _ensure_tables(db)
        if body.nome:
            db.execute("UPDATE analista_projetos SET nome=?, updated_at=datetime('now') WHERE id=?",
                       (body.nome, projeto_id))
        if body.status:
            db.execute("UPDATE analista_projetos SET status=?, updated_at=datetime('now') WHERE id=?",
                       (body.status, projeto_id))
        db.commit()
        return {"status": "ok"}
    finally:
        db.close()


@router.delete("/projetos/{projeto_id}")
async def delete_projeto(projeto_id: int):
    db = _get_db()
    try:
        _ensure_tables(db)
        db.execute("DELETE FROM analista_documentos WHERE projeto_id=?", (projeto_id,))
        db.execute("DELETE FROM analista_artefatos WHERE projeto_id=?", (projeto_id,))
        db.execute("DELETE FROM analista_mensagens WHERE projeto_id=?", (projeto_id,))
        db.execute("DELETE FROM analista_projetos WHERE id=?", (projeto_id,))
        db.commit()
        return {"status": "deleted"}
    finally:
        db.close()


# ─── Mensagens & Artefatos ───

@router.get("/projetos/{projeto_id}/mensagens")
async def get_mensagens(projeto_id: int):
    db = _get_db()
    try:
        _ensure_tables(db)
        rows = db.execute(
            "SELECT id, role, content, tool_data, created_at "
            "FROM analista_mensagens WHERE projeto_id=? ORDER BY id",
            (projeto_id,),
        ).fetchall()
        return [{"id": r[0], "role": r[1], "content": r[2],
                 "tool_data": json.loads(r[3]) if r[3] else None,
                 "created_at": r[4]} for r in rows]
    finally:
        db.close()


@router.get("/projetos/{projeto_id}/artefatos")
async def get_artefatos(projeto_id: int):
    db = _get_db()
    try:
        _ensure_tables(db)
        rows = db.execute(
            "SELECT id, tipo, nome, tabela, acao, spec, created_at "
            "FROM analista_artefatos WHERE projeto_id=? ORDER BY id",
            (projeto_id,),
        ).fetchall()
        return [{"id": r[0], "tipo": r[1], "nome": r[2], "tabela": r[3] or "",
                 "acao": r[4], "spec": json.loads(r[5]) if r[5] else None,
                 "created_at": r[6]} for r in rows]
    finally:
        db.close()
```

- [ ] **Step 2: Add the chat SSE endpoint to the same router**

Append to `backend/routers/analista.py`:

```python
# ─── Chat SSE ───

class ChatMessage(BaseModel):
    message: str


@router.post("/projetos/{projeto_id}/chat")
async def chat(projeto_id: int, body: ChatMessage):
    """SSE streaming chat for a project."""
    from backend.routers.chat import _get_services
    from backend.services.analista_tools import (
        tool_analise_impacto, tool_buscar_pes,
        tool_buscar_fontes_tabela, tool_info_tabela,
    )
    from backend.services.analista_prompts import SYSTEM_PROMPT

    db_svc, vs, ks, llm, client_dir = _get_services()
    db = _get_db()

    try:
        _ensure_tables(db)

        # Verify project exists
        proj = db.execute("SELECT id, nome, status FROM analista_projetos WHERE id=?", (projeto_id,)).fetchone()
        if not proj:
            raise HTTPException(404, "Projeto nao encontrado")

        # Update status to em_andamento
        if proj[2] == "rascunho":
            db.execute("UPDATE analista_projetos SET status='em_andamento', updated_at=datetime('now') WHERE id=?",
                       (projeto_id,))
            db.commit()

        # Save user message
        db.execute("INSERT INTO analista_mensagens (projeto_id, role, content) VALUES (?, 'user', ?)",
                   (projeto_id, body.message))
        db.commit()

        # Load history
        hist_rows = db.execute(
            "SELECT role, content FROM analista_mensagens WHERE projeto_id=? ORDER BY id",
            (projeto_id,),
        ).fetchall()

        # Load current artifacts
        art_rows = db.execute(
            "SELECT tipo, nome, tabela, acao FROM analista_artefatos WHERE projeto_id=?",
            (projeto_id,),
        ).fetchall()
        artefatos_text = "\n".join(
            f"- [{a[3]}] {a[0]}: {a[1]}" + (f" ({a[2]})" if a[2] else "")
            for a in art_rows
        ) or "Nenhum artefato ainda."

        # Classify user intent to gather relevant context
        classification = await asyncio.to_thread(llm.classify, body.message)
        tabelas = classification.get("tabelas", [])
        modulos = classification.get("modulos", [])

        # Gather context silently (bom senso: only write-relevant data)
        tool_results_parts = []

        for tab in tabelas[:3]:
            impacto = await asyncio.to_thread(tool_analise_impacto, tab)
            if impacto.get("fontes_escrita"):
                tool_results_parts.append(
                    f"Tabela {tab}: {impacto['total_fontes_escrita']} fontes escrevem, "
                    f"{len(impacto.get('gatilhos', []))} gatilhos, "
                    f"{len(impacto.get('campos_custom', []))} campos custom"
                )
            info = await asyncio.to_thread(tool_info_tabela, tab)
            if info.get("existe"):
                tool_results_parts.append(
                    f"Tabela {tab} ({info['nome']}): {info['total_campos']} campos, "
                    f"{info['campos_custom']} custom, {info['indices']} indices"
                )

            # Deep field analysis for mentioned tables
            deep = ks.build_deep_field_analysis(tab)
            if deep and len(deep) > 100:
                tool_results_parts.append(f"Analise campos {tab}:\n{deep[:3000]}")

        # Search for PEs in mentioned routines/modules
        for mod in modulos[:2]:
            pes = await asyncio.to_thread(tool_buscar_pes, modulo=mod)
            if pes:
                pe_list = ", ".join(f"{p['nome']} ({p['objetivo'][:40]})" for p in pes[:10])
                tool_results_parts.append(f"PEs disponiveis em {mod}: {pe_list}")

        # Semantic search in fontes
        search_terms = classification.get("search_terms", [])
        if search_terms:
            query = " ".join(search_terms)
            fonte_results = vs.search("fontes_custom", query, n_results=5)
            for r in fonte_results:
                arq = r["metadata"].get("arquivo", "")
                if arq:
                    tool_results_parts.append(f"Fonte relevante: {arq}")

        tool_results_text = "\n".join(tool_results_parts) or "Nenhuma busca necessaria ainda."

        # Build context (truncate to avoid token limits)
        context = tool_results_text[:8000]

        # Build messages for LLM
        system = SYSTEM_PROMPT.format(
            context=context,
            artefatos=artefatos_text,
            tool_results=tool_results_text[:4000],
        )

        messages = [{"role": "system", "content": system}]
        # Add last 10 messages from history
        for r in hist_rows[-10:]:
            messages.append({"role": r[0], "content": r[1][:2000]})

        async def event_generator():
            full_response = ""
            for attempt in range(3):
                try:
                    stream = await asyncio.to_thread(lambda: list(llm.chat_stream(messages)))
                    break
                except Exception as e:
                    if ("rate_limit" in str(e).lower() or "429" in str(e)) and attempt < 2:
                        wait = 30 * (attempt + 1)
                        yield {"event": "token", "data": json.dumps({"content": f"\n\n... aguardando {wait}s...\n\n"})}
                        await asyncio.sleep(wait)
                        continue
                    yield {"event": "token", "data": json.dumps({"content": f"\n\nErro: {str(e)[:200]}"})}
                    yield {"event": "done", "data": "{}"}
                    return

            for token in stream:
                full_response += token
                yield {"event": "token", "data": json.dumps({"content": token})}

            # Parse artifacts from response
            artefatos_novos = []
            if "###ARTEFATOS###" in full_response:
                parts = full_response.split("###ARTEFATOS###", 1)
                chat_text = parts[0].strip()
                try:
                    artefatos_novos = json.loads(parts[1].strip())
                except (json.JSONDecodeError, IndexError):
                    artefatos_novos = []
            else:
                chat_text = full_response

            # Save assistant message
            db2 = _get_db()
            try:
                db2.execute(
                    "INSERT INTO analista_mensagens (projeto_id, role, content, tool_data) VALUES (?, 'assistant', ?, ?)",
                    (projeto_id, chat_text, json.dumps(artefatos_novos) if artefatos_novos else None),
                )

                # Save new artifacts
                for art in artefatos_novos:
                    db2.execute(
                        "INSERT INTO analista_artefatos (projeto_id, tipo, nome, tabela, acao) VALUES (?, ?, ?, ?, ?)",
                        (projeto_id, art.get("tipo", ""), art.get("nome", ""),
                         art.get("tabela", ""), art.get("acao", "criar")),
                    )
                db2.execute("UPDATE analista_projetos SET updated_at=datetime('now') WHERE id=?", (projeto_id,))
                db2.commit()
            finally:
                db2.close()

            # Send artifacts update event
            if artefatos_novos:
                yield {"event": "artefatos", "data": json.dumps(artefatos_novos)}

            yield {"event": "done", "data": "{}"}

        return EventSourceResponse(event_generator())
    finally:
        db.close()
```

- [ ] **Step 3: Add document generation endpoint**

Append to `backend/routers/analista.py`:

```python
# ─── Gerar Projeto (Documentos) ───

@router.post("/projetos/{projeto_id}/gerar")
async def gerar_projeto(projeto_id: int):
    """Generate project documents (gerencial + tecnicos)."""
    from backend.routers.chat import _get_services
    from backend.services.analista_prompts import (
        PROMPT_GERAR_PROJETO, TEMPLATE_GERENCIAL,
        TEMPLATE_TECNICO_CAMPO, TEMPLATE_TECNICO_PE, TEMPLATE_TECNICO_FONTE,
    )
    import re

    db_svc, vs, ks, llm, client_dir = _get_services()
    db = _get_db()
    try:
        _ensure_tables(db)
        proj = db.execute("SELECT nome, descricao FROM analista_projetos WHERE id=?", (projeto_id,)).fetchone()
        if not proj:
            raise HTTPException(404, "Projeto nao encontrado")

        # Get artifacts
        arts = db.execute(
            "SELECT tipo, nome, tabela, acao, spec FROM analista_artefatos WHERE projeto_id=?",
            (projeto_id,),
        ).fetchall()
        artefatos = [{"tipo": a[0], "nome": a[1], "tabela": a[2] or "", "acao": a[3]} for a in arts]

        if not artefatos:
            raise HTTPException(400, "Nenhum artefato definido. Converse com o analista primeiro.")

        # Build technical context from DB (reuse existing data, save tokens)
        contexto_parts = []
        tabelas_mencionadas = set(a["tabela"] for a in artefatos if a["tabela"])
        for tab in tabelas_mencionadas:
            deep = ks.build_deep_field_analysis(tab)
            if deep:
                contexto_parts.append(deep[:2000])

        contexto_tecnico = "\n".join(contexto_parts)[:6000]

        # Call LLM to generate project docs
        prompt = PROMPT_GERAR_PROJETO.format(
            nome_projeto=proj[0],
            descricao=proj[1] or "",
            artefatos_json=json.dumps(artefatos, ensure_ascii=False),
            contexto_tecnico=contexto_tecnico,
        )

        result = await asyncio.to_thread(
            llm._call, [{"role": "user", "content": prompt}], temperature=0.3, use_gen=True
        )

        # Parse JSON response
        result = result.strip()
        if result.startswith("```"):
            result = result.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        try:
            docs_data = json.loads(result)
        except json.JSONDecodeError:
            m = re.search(r'\{[\s\S]+\}', result)
            if m:
                docs_data = json.loads(m.group())
            else:
                raise HTTPException(500, "Erro ao gerar documentos")

        # Save gerencial doc
        ger = docs_data.get("gerencial", {})
        gerencial_md = TEMPLATE_GERENCIAL.format(
            nome_projeto=proj[0],
            resumo=ger.get("resumo", ""),
            justificativa=ger.get("justificativa", ""),
            escopo_itens=ger.get("escopo_itens", ""),
            fluxo_mermaid=ger.get("fluxo_mermaid", "flowchart TD\n  A[Inicio] --> B[Fim]"),
            estimativa=ger.get("estimativa", ""),
            riscos=ger.get("riscos", ""),
        )
        db.execute(
            "INSERT INTO analista_documentos (projeto_id, tipo, titulo, conteudo) VALUES (?, 'gerencial', ?, ?)",
            (projeto_id, f"{proj[0]} — Projeto Gerencial", gerencial_md),
        )

        # Save technical docs
        for tec in docs_data.get("tecnicos", []):
            tipo = tec.get("tipo", "")
            nome = tec.get("nome", "")
            conteudo = tec.get("conteudo", {})

            if tipo == "campo":
                md = TEMPLATE_TECNICO_CAMPO.format(
                    nome=nome, tabela=conteudo.get("tabela", ""),
                    tipo=conteudo.get("tipo", "C"), tamanho=conteudo.get("tamanho", ""),
                    titulo=conteudo.get("titulo", ""), descricao=conteudo.get("descricao", ""),
                    validacao=conteudo.get("validacao", "N/A"),
                    inicializador=conteudo.get("inicializador", "N/A"),
                    gatilhos=conteudo.get("gatilhos", "N/A"),
                    impactos=conteudo.get("impactos", "N/A"),
                )
            elif tipo == "pe":
                md = TEMPLATE_TECNICO_PE.format(
                    nome=nome, rotina=conteudo.get("rotina", ""),
                    modulo=conteudo.get("modulo", ""),
                    objetivo=conteudo.get("objetivo", ""),
                    paramixb=conteudo.get("paramixb", "N/A"),
                    logica=conteudo.get("logica", ""),
                    retorno=conteudo.get("retorno", ""),
                )
            elif tipo == "fonte":
                md = TEMPLATE_TECNICO_FONTE.format(
                    nome=nome, modulo=conteudo.get("modulo", ""),
                    tipo=conteudo.get("tipo_programa", "user_function"),
                    objetivo=conteudo.get("objetivo", ""),
                    funcoes=conteudo.get("funcoes", ""),
                    tabelas=conteudo.get("tabelas", ""),
                    fluxo=conteudo.get("fluxo", "flowchart TD\n  A[Inicio] --> B[Fim]"),
                )
            else:
                md = f"# {nome}\n\n{json.dumps(conteudo, ensure_ascii=False, indent=2)}"

            db.execute(
                "INSERT INTO analista_documentos (projeto_id, tipo, titulo, conteudo) VALUES (?, 'tecnico', ?, ?)",
                (projeto_id, f"Tecnico — {tipo.title()} {nome}", md),
            )

        # Update project status
        db.execute("UPDATE analista_projetos SET status='concluido', updated_at=datetime('now') WHERE id=?",
                   (projeto_id,))
        db.commit()

        return {"status": "ok", "documentos": len(docs_data.get("tecnicos", [])) + 1}
    finally:
        db.close()


# ─── Documentos ───

@router.get("/projetos/{projeto_id}/documentos")
async def get_documentos(projeto_id: int):
    db = _get_db()
    try:
        _ensure_tables(db)
        rows = db.execute(
            "SELECT id, tipo, titulo, created_at FROM analista_documentos WHERE projeto_id=? ORDER BY id",
            (projeto_id,),
        ).fetchall()
        return [{"id": r[0], "tipo": r[1], "titulo": r[2], "created_at": r[3]} for r in rows]
    finally:
        db.close()


@router.get("/projetos/{projeto_id}/documentos/{doc_id}")
async def get_documento(projeto_id: int, doc_id: int):
    db = _get_db()
    try:
        _ensure_tables(db)
        row = db.execute(
            "SELECT id, tipo, titulo, conteudo, created_at "
            "FROM analista_documentos WHERE id=? AND projeto_id=?",
            (doc_id, projeto_id),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Documento nao encontrado")
        return {"id": row[0], "tipo": row[1], "titulo": row[2], "conteudo": row[3], "created_at": row[4]}
    finally:
        db.close()
```

- [ ] **Step 4: Register router in app.py**

In `backend/app.py`, add:
- Line 11: `from backend.routers.analista import router as analista_router`
- Line 27: `app.include_router(analista_router)`

- [ ] **Step 5: Commit**

```bash
git add backend/routers/analista.py backend/app.py
git commit -m "feat(analista): add router with CRUD, chat SSE, and doc generation"
```

---

## Chunk 2: Frontend — AnalistaView.vue + Route

### Task 4: Add route in router.js

**Files:**
- Modify: `frontend/src/router.js`

- [ ] **Step 1: Add the route**

Add import and route entry:
```javascript
import AnalistaView from './views/AnalistaView.vue'

// In routes array, between dashboard and padrao:
{ path: '/analista', component: AnalistaView, meta: { label: 'Peça ao Analista', icon: 'pi pi-user' } },
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/router.js
git commit -m "feat(analista): add route for Peca ao Analista view"
```

---

### Task 5: Create AnalistaView.vue

**Files:**
- Create: `frontend/src/views/AnalistaView.vue`

- [ ] **Step 1: Create the view with both modes (cards list + chat)**

```vue
<template>
  <div class="analista-container">
    <!-- Mode: Project List -->
    <div v-if="!activeProject" class="projetos-list">
      <div class="projetos-header">
        <h2>Peca ao Analista</h2>
        <Button icon="pi pi-plus" label="Novo Projeto" @click="showNewDialog = true" />
      </div>
      <div class="projetos-grid">
        <div v-for="p in projetos" :key="p.id" class="projeto-card" @click="openProject(p)">
          <div class="projeto-card-header">
            <strong>{{ p.nome }}</strong>
            <Tag :value="p.status" :severity="statusSeverity(p.status)" />
          </div>
          <p class="projeto-card-desc">{{ p.descricao || 'Sem descricao' }}</p>
          <div class="projeto-card-footer">
            <span><i class="pi pi-comments"></i> {{ p.mensagens }}</span>
            <span><i class="pi pi-box"></i> {{ p.artefatos }}</span>
            <span class="projeto-date">{{ formatDate(p.updated_at) }}</span>
          </div>
        </div>
        <div v-if="!projetos.length && !loading" class="empty-state">
          <i class="pi pi-user" style="font-size: 3rem; color: #ccc;"></i>
          <p>Nenhum projeto ainda. Crie um novo para comecar.</p>
        </div>
      </div>
    </div>

    <!-- Mode: Project Chat -->
    <div v-else class="projeto-workspace">
      <div class="projeto-topbar">
        <Button icon="pi pi-arrow-left" text @click="closeProject" />
        <h3>{{ activeProject.nome }}</h3>
        <Tag :value="activeProject.status" :severity="statusSeverity(activeProject.status)" />
        <div style="flex:1"></div>
        <Button icon="pi pi-file-export" label="Gerar Projeto" severity="success"
          @click="gerarProjeto" :loading="gerando" :disabled="!artefatos.length" />
        <Button icon="pi pi-trash" text severity="danger" @click="deleteProject" />
      </div>

      <div class="projeto-body">
        <!-- Chat -->
        <div class="chat-panel">
          <div class="chat-messages" ref="chatContainer">
            <div v-for="msg in mensagens" :key="msg.id" :class="['chat-msg', msg.role]">
              <div class="msg-content" v-html="renderMsg(msg.content)"></div>
            </div>
            <div v-if="streaming" class="chat-msg assistant">
              <div class="msg-content" v-html="renderMsg(streamContent)"></div>
            </div>
          </div>
          <div class="chat-input">
            <InputText v-model="userMessage" placeholder="Descreva sua necessidade..."
              @keydown.enter="sendMessage" :disabled="streaming" style="flex:1;" />
            <Button icon="pi pi-send" @click="sendMessage" :disabled="!userMessage.trim() || streaming" />
          </div>
        </div>

        <!-- Artifacts Panel -->
        <div class="artifacts-panel">
          <h4>Artefatos do Projeto</h4>
          <div v-for="tipo in artefatoTipos" :key="tipo" class="artifact-group">
            <div class="artifact-group-header" @click="toggleGroup(tipo)">
              <i :class="expandedGroups[tipo] ? 'pi pi-chevron-down' : 'pi pi-chevron-right'"></i>
              <span>{{ tipoLabel(tipo) }} ({{ artefatosByTipo(tipo).length }})</span>
            </div>
            <div v-if="expandedGroups[tipo]" class="artifact-items">
              <div v-for="art in artefatosByTipo(tipo)" :key="art.id" class="artifact-item">
                <Tag :value="art.acao" :severity="art.acao === 'criar' ? 'success' : 'warning'" style="font-size:0.7rem;" />
                <span>{{ art.nome }}</span>
                <small v-if="art.tabela">({{ art.tabela }})</small>
              </div>
            </div>
          </div>
          <div v-if="!artefatos.length" class="empty-artifacts">
            <p>Os artefatos aparecerao aqui conforme a conversa evoluir.</p>
          </div>

          <!-- Generated Documents -->
          <div v-if="documentos.length" class="docs-section">
            <h4>Documentos Gerados</h4>
            <div v-for="doc in documentos" :key="doc.id" class="doc-item" @click="downloadDoc(doc)">
              <i :class="doc.tipo === 'gerencial' ? 'pi pi-file' : 'pi pi-cog'"></i>
              <span>{{ doc.titulo }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- New Project Dialog -->
    <Dialog v-model:visible="showNewDialog" header="Novo Projeto" :modal="true" style="width: 450px;">
      <div style="display:flex; flex-direction:column; gap:1rem;">
        <div>
          <label>Nome do Projeto</label>
          <InputText v-model="newProjeto.nome" placeholder="Ex: Campo Alcada Pedido Venda" style="width:100%;" />
        </div>
        <div>
          <label>Descricao (opcional)</label>
          <Textarea v-model="newProjeto.descricao" rows="3" placeholder="Descreva brevemente a necessidade..." style="width:100%;" />
        </div>
      </div>
      <template #footer>
        <Button label="Cancelar" text @click="showNewDialog = false" />
        <Button label="Criar" icon="pi pi-plus" @click="createProject" :disabled="!newProjeto.nome.trim()" />
      </template>
    </Dialog>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, onMounted } from 'vue'
import Button from 'primevue/button'
import Tag from 'primevue/tag'
import InputText from 'primevue/inputtext'
import Textarea from 'primevue/textarea'
import Dialog from 'primevue/dialog'
import { useToast } from 'primevue/usetoast'
import axios from 'axios'

const api = axios.create({ baseURL: '/api/analista' })
const toast = useToast()

// State
const loading = ref(false)
const projetos = ref([])
const activeProject = ref(null)
const mensagens = ref([])
const artefatos = ref([])
const documentos = ref([])
const streaming = ref(false)
const streamContent = ref('')
const userMessage = ref('')
const showNewDialog = ref(false)
const newProjeto = ref({ nome: '', descricao: '' })
const gerando = ref(false)
const chatContainer = ref(null)
const expandedGroups = ref({ campo: true, pe: true, fonte: true, tabela: true, gatilho: true })

// Computed
const artefatoTipos = computed(() => {
  const tipos = new Set(artefatos.value.map(a => a.tipo))
  return [...tipos].sort()
})

function artefatosByTipo(tipo) {
  return artefatos.value.filter(a => a.tipo === tipo)
}

function tipoLabel(tipo) {
  const labels = { campo: 'Campos', pe: 'Pontos de Entrada', fonte: 'Fontes', tabela: 'Tabelas', gatilho: 'Gatilhos' }
  return labels[tipo] || tipo
}

function statusSeverity(status) {
  if (status === 'concluido') return 'success'
  if (status === 'em_andamento') return 'info'
  return 'secondary'
}

function formatDate(dt) {
  if (!dt) return ''
  return new Date(dt).toLocaleDateString('pt-BR')
}

function toggleGroup(tipo) {
  expandedGroups.value[tipo] = !expandedGroups.value[tipo]
}

function renderMsg(text) {
  if (!text) return ''
  // Basic markdown: bold, newlines
  return text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br>')
}

// API calls
async function loadProjetos() {
  loading.value = true
  try {
    const { data } = await api.get('/projetos')
    projetos.value = data
  } catch { }
  loading.value = false
}

async function createProject() {
  try {
    const { data } = await api.post('/projetos', newProjeto.value)
    showNewDialog.value = false
    newProjeto.value = { nome: '', descricao: '' }
    await loadProjetos()
    // Open the new project
    const proj = projetos.value.find(p => p.id === data.id)
    if (proj) openProject(proj)
  } catch {
    toast.add({ severity: 'error', summary: 'Erro ao criar projeto', life: 3000 })
  }
}

async function openProject(proj) {
  activeProject.value = proj
  await Promise.all([loadMensagens(), loadArtefatos(), loadDocumentos()])
}

function closeProject() {
  activeProject.value = null
  mensagens.value = []
  artefatos.value = []
  documentos.value = []
  loadProjetos()
}

async function deleteProject() {
  if (!confirm(`Excluir projeto "${activeProject.value.nome}"?`)) return
  try {
    await api.delete(`/projetos/${activeProject.value.id}`)
    closeProject()
    toast.add({ severity: 'success', summary: 'Projeto excluido', life: 3000 })
  } catch { }
}

async function loadMensagens() {
  try {
    const { data } = await api.get(`/projetos/${activeProject.value.id}/mensagens`)
    mensagens.value = data
  } catch { }
}

async function loadArtefatos() {
  try {
    const { data } = await api.get(`/projetos/${activeProject.value.id}/artefatos`)
    artefatos.value = data
  } catch { }
}

async function loadDocumentos() {
  try {
    const { data } = await api.get(`/projetos/${activeProject.value.id}/documentos`)
    documentos.value = data
  } catch { }
}

async function sendMessage() {
  if (!userMessage.value.trim() || streaming.value) return
  const msg = userMessage.value.trim()
  userMessage.value = ''
  streaming.value = true
  streamContent.value = ''

  // Add user message to UI immediately
  mensagens.value.push({ id: Date.now(), role: 'user', content: msg })
  await nextTick()
  scrollToBottom()

  try {
    const response = await fetch(`/api/analista/projetos/${activeProject.value.id}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: msg }),
    })

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let currentEvent = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (line.startsWith('event: ')) {
          currentEvent = line.slice(7).trim()
        } else if (line.startsWith('data: ')) {
          const payload = line.slice(6)
          try {
            const data = JSON.parse(payload)
            if (currentEvent === 'token') {
              streamContent.value += data.content || ''
              scrollToBottom()
            } else if (currentEvent === 'artefatos') {
              // Reload artifacts
              await loadArtefatos()
            } else if (currentEvent === 'done') {
              // Finalize
              if (streamContent.value) {
                mensagens.value.push({ id: Date.now(), role: 'assistant', content: streamContent.value })
              }
              streamContent.value = ''
              streaming.value = false
            }
          } catch { }
        }
      }
    }
  } catch {
    toast.add({ severity: 'error', summary: 'Erro na comunicacao', life: 3000 })
  }
  streaming.value = false
  streamContent.value = ''
}

async function gerarProjeto() {
  gerando.value = true
  try {
    const { data } = await api.post(`/projetos/${activeProject.value.id}/gerar`)
    toast.add({ severity: 'success', summary: `${data.documentos} documentos gerados`, life: 3000 })
    await loadDocumentos()
    activeProject.value.status = 'concluido'
  } catch (e) {
    toast.add({ severity: 'error', summary: 'Erro ao gerar projeto', life: 5000 })
  }
  gerando.value = false
}

async function downloadDoc(doc) {
  try {
    const { data } = await api.get(`/projetos/${activeProject.value.id}/documentos/${doc.id}`)
    const blob = new Blob([data.conteudo], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${data.titulo.replace(/[^a-zA-Z0-9_-]/g, '_')}.md`
    a.click()
    URL.revokeObjectURL(url)
  } catch { }
}

function scrollToBottom() {
  nextTick(() => {
    if (chatContainer.value) {
      chatContainer.value.scrollTop = chatContainer.value.scrollHeight
    }
  })
}

onMounted(loadProjetos)
</script>

<style scoped>
.analista-container { height: calc(100vh - 4rem); display: flex; flex-direction: column; padding: 1rem; }

/* Project List */
.projetos-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem; }
.projetos-header h2 { margin: 0; }
.projetos-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 1rem; }
.projeto-card { background: #fff; border: 1px solid #e0e0e0; border-radius: 8px; padding: 1rem; cursor: pointer; transition: box-shadow 0.2s; }
.projeto-card:hover { box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
.projeto-card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem; }
.projeto-card-desc { font-size: 0.85rem; color: #666; margin: 0 0 0.8rem; line-height: 1.4; }
.projeto-card-footer { display: flex; gap: 1rem; font-size: 0.78rem; color: #999; }
.projeto-date { margin-left: auto; }
.empty-state { grid-column: 1 / -1; text-align: center; padding: 3rem; color: #999; }

/* Project Workspace */
.projeto-workspace { display: flex; flex-direction: column; height: 100%; }
.projeto-topbar { display: flex; align-items: center; gap: 0.5rem; padding: 0.5rem 0; border-bottom: 1px solid #e0e0e0; margin-bottom: 0.5rem; }
.projeto-topbar h3 { margin: 0; }
.projeto-body { display: flex; flex: 1; gap: 1rem; min-height: 0; }

/* Chat Panel */
.chat-panel { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.chat-messages { flex: 1; overflow-y: auto; padding: 0.5rem; display: flex; flex-direction: column; gap: 0.8rem; }
.chat-msg { padding: 0.8rem 1rem; border-radius: 8px; max-width: 85%; line-height: 1.5; font-size: 0.9rem; }
.chat-msg.user { background: #e3f2fd; align-self: flex-end; }
.chat-msg.assistant { background: #f5f5f5; align-self: flex-start; }
.chat-input { display: flex; gap: 0.5rem; padding: 0.5rem 0; }

/* Artifacts Panel */
.artifacts-panel { width: 280px; border-left: 1px solid #e0e0e0; padding: 0.5rem 1rem; overflow-y: auto; flex-shrink: 0; }
.artifacts-panel h4 { margin: 0 0 0.8rem; font-size: 0.9rem; color: #555; }
.artifact-group { margin-bottom: 0.5rem; }
.artifact-group-header { display: flex; align-items: center; gap: 0.4rem; cursor: pointer; padding: 0.3rem 0; font-weight: 600; font-size: 0.82rem; color: #333; }
.artifact-items { padding-left: 1.2rem; }
.artifact-item { display: flex; align-items: center; gap: 0.4rem; padding: 0.2rem 0; font-size: 0.8rem; }
.artifact-item small { color: #999; }
.empty-artifacts { color: #999; font-size: 0.82rem; font-style: italic; padding: 1rem 0; }
.docs-section { border-top: 1px solid #e0e0e0; margin-top: 1rem; padding-top: 0.8rem; }
.doc-item { display: flex; align-items: center; gap: 0.5rem; padding: 0.4rem; cursor: pointer; font-size: 0.82rem; border-radius: 4px; }
.doc-item:hover { background: #f0f0f0; }
</style>
```

- [ ] **Step 2: Build and verify**

```bash
cd frontend && npm run build
```
Expected: Build succeeds with no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/AnalistaView.vue frontend/src/router.js
git commit -m "feat(analista): add AnalistaView with chat + artifacts panel"
```

---

## Chunk 3: Integration and Polish

### Task 6: Register backend router and test end-to-end

**Files:**
- Modify: `backend/app.py`

- [ ] **Step 1: Add import and include_router**

In `backend/app.py`:
- After line 10 (`from backend.routers.explorer import router as explorer_router`), add:
  ```python
  from backend.routers.analista import router as analista_router
  ```
- After line 26 (`app.include_router(explorer_router)`), add:
  ```python
  app.include_router(analista_router)
  ```

- [ ] **Step 2: Restart server and test CRUD**

```bash
curl -s http://localhost:8741/api/analista/projetos | python -m json.tool
curl -s -X POST http://localhost:8741/api/analista/projetos -H "Content-Type: application/json" -d '{"nome":"Teste","descricao":"teste"}' | python -m json.tool
```
Expected: Empty list first, then `{"id": 1, "nome": "Teste", "status": "rascunho"}`

- [ ] **Step 3: Build frontend and test in browser**

```bash
cd frontend && npm run build
```
Navigate to `http://localhost:8741/analista`, verify:
- Menu shows "Peca ao Analista" between Dashboard and Base Padrao
- Cards grid loads (empty or with test project)
- Click "Novo Projeto" opens dialog
- Create project → opens chat view
- Send message → streaming response appears
- Artifacts panel updates

- [ ] **Step 4: Commit all integration**

```bash
git add backend/app.py
git commit -m "feat(analista): register router and complete integration"
```

---

## Summary

| Task | What | Files |
|---|---|---|
| 1 | Internal tool wrappers | `backend/services/analista_tools.py` |
| 2 | Prompts and templates | `backend/services/analista_prompts.py` |
| 3 | Backend router (CRUD + Chat SSE + Docs) | `backend/routers/analista.py` |
| 4 | Frontend route | `frontend/src/router.js` |
| 5 | AnalistaView.vue | `frontend/src/views/AnalistaView.vue` |
| 6 | Integration + test | `backend/app.py` |

Total: 4 new files, 2 modified files, ~800 lines of code.
