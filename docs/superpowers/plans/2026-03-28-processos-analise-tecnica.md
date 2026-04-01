# Processos — Análise Técnica + Chat + Cadastro Inteligente

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform ProcessoDialog into a complete process hub with persisted technical analysis, inline chat, and intelligent process registration available as both UI and internal Analista tool.

**Architecture:** Extend `processos_detectados` with analysis columns, add `processo_mensagens` table. Three new backend endpoints reuse existing Analista investigation tools. Frontend ProcessoDialog gets analysis + chat sections. Registration tool injected into Analista prompts for silent enrichment.

**Tech Stack:** Python/FastAPI/SQLite (backend), Vue 3/PrimeVue (frontend), SSE streaming, LLM via existing `LLMService`

**Spec:** `docs/superpowers/specs/2026-03-28-processos-analise-tecnica-design.md`

---

## Chunk 1: Database Schema + Migration

### Task 1: Add columns to `processos_detectados` and create `processo_mensagens`

**Files:**
- Modify: `backend/services/database.py:370-411` (SCHEMA constant + initialize method)

- [ ] **Step 1: Add columns to SCHEMA constant**

In `backend/services/database.py`, inside the `processos_detectados` CREATE TABLE (line 370-384), add three new columns before the closing `);`:

```sql
    analise_markdown TEXT DEFAULT NULL,
    analise_json TEXT DEFAULT NULL,
    analise_updated_at TEXT DEFAULT NULL,
```

Add after the `processos_detectados` table (after line 386):

```sql
CREATE TABLE IF NOT EXISTS processo_mensagens (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    processo_id INTEGER NOT NULL REFERENCES processos_detectados(id),
    role        TEXT NOT NULL,
    content     TEXT NOT NULL,
    created_at  TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_proc_msg_processo ON processo_mensagens(processo_id);
```

- [ ] **Step 2: Add ALTER TABLE migrations in initialize()**

In `Database.initialize()` (after line 411), add idempotent migrations for existing DBs:

```python
        for col in [
            "ALTER TABLE processos_detectados ADD COLUMN analise_markdown TEXT DEFAULT NULL",
            "ALTER TABLE processos_detectados ADD COLUMN analise_json TEXT DEFAULT NULL",
            "ALTER TABLE processos_detectados ADD COLUMN analise_updated_at TEXT DEFAULT NULL",
        ]:
            try:
                self._conn.execute(col)
                self._conn.commit()
            except Exception:
                pass  # column already exists
```

- [ ] **Step 3: Verify migration works**

Run: `cd d:/IA/Projetos/Protheus && python -c "from backend.services.database import Database; from pathlib import Path; db = Database(Path('/tmp/test_migration.db')); db.initialize(); print('OK'); db.close()"`

Expected: `OK` — no errors

- [ ] **Step 4: Commit**

```bash
git add backend/services/database.py
git commit -m "feat(db): add analise columns to processos_detectados + processo_mensagens table"
```

---

## Chunk 2: Backend — Analysis Generation Endpoint

### Task 2: Create analysis generation function

**Files:**
- Modify: `backend/routers/analista.py:385-470` (add after `gerar_fluxo_processo` function)

- [ ] **Step 1: Add the sync function `gerar_analise_processo`**

Add this function after `gerar_fluxo_processo` (after line 435) in `backend/routers/analista.py`. This function opens its own DB connection (same pattern as `gerar_fluxo_processo`) to avoid SQLite cross-thread issues:

```python
def gerar_analise_processo(db_path, llm, processo_id: int, force: bool) -> dict | None:
    """Sync function: generates technical analysis for a process via investigation tools + LLM.
    Opens its own DB connection to avoid SQLite cross-thread issues."""
    import json as _json

    db = Database(db_path)
    db.initialize()

    row = db.execute(
        "SELECT id, nome, tipo, descricao, criticidade, tabelas, score, "
        "analise_markdown, analise_json, analise_updated_at "
        "FROM processos_detectados WHERE id = ?",
        (processo_id,),
    ).fetchone()

    if row is None:
        db.close()
        return None

    # Cache hit — return existing analysis
    if row[7] is not None and not force and row[9] != 'generating':
        db.close()
        return {
            "analise_markdown": row[7],
            "analise_json": _json.loads(row[8]) if row[8] else {},
            "analise_updated_at": row[9],
        }

    # Concurrency guard — if another request is generating, wait
    if row[9] == 'generating' and not force:
        for _ in range(60):  # poll up to 120s
            import time; time.sleep(2)
            check = db.execute(
                "SELECT analise_updated_at, analise_markdown, analise_json FROM processos_detectados WHERE id = ?",
                (processo_id,),
            ).fetchone()
            if check and check[0] and check[0] != 'generating':
                db.close()
                return {
                    "analise_markdown": check[1],
                    "analise_json": _json.loads(check[2]) if check[2] else {},
                    "analise_updated_at": check[0],
                }
        db.close()
        raise TimeoutError("Analysis generation timed out waiting for another request")

    # Mark as generating
    db.execute(
        "UPDATE processos_detectados SET analise_updated_at = 'generating' WHERE id = ?",
        (processo_id,),
    )
    db.commit()

    try:
        tabelas = _json.loads(row[5]) if row[5] else []
        nome = row[1]
        tipo = row[2]
        descricao = row[3]

        # ── Phase 1: Investigate using existing tools ──
        # NOTE: tool_investigar_condicao requires (arquivo, funcao, variavel) — not usable in per-table loop.
        # tool_buscar_pes returns list[dict], not {"pes": [...]}.
        # tool_buscar_parametros accepts tabela= named arg.
        from backend.services.analista_tools import (
            tool_analise_impacto, tool_operacoes_tabela,
            tool_buscar_pes, tool_buscar_parametros, tool_info_tabela,
        )

        tool_results_parts = []
        for tab in tabelas[:8]:  # limit to 8 tables to avoid token explosion
            try:
                info = tool_info_tabela(tab)
                if info.get("existe"):
                    tool_results_parts.append(f"### Tabela {tab}\n{_json.dumps(info, ensure_ascii=False, indent=2)}")
            except Exception:
                pass
            try:
                impacto = tool_analise_impacto(tab)
                if impacto:
                    tool_results_parts.append(f"### Impacto {tab}\n{_json.dumps(impacto, ensure_ascii=False, indent=2)}")
            except Exception:
                pass
            try:
                ops = tool_operacoes_tabela(tab)
                if ops and ops.get("operacoes"):
                    tool_results_parts.append(f"### Operacoes {tab}\n{_json.dumps(ops, ensure_ascii=False, indent=2)}")
            except Exception:
                pass

        # PEs and parameters (once, not per-table)
        for tab in tabelas[:4]:
            try:
                pes = tool_buscar_pes(tabela=tab)  # returns list[dict]
                if pes:
                    tool_results_parts.append(f"### PEs {tab}\n{_json.dumps(pes, ensure_ascii=False, indent=2)}")
            except Exception:
                pass
            try:
                params = tool_buscar_parametros(tabela=tab)
                if params and params.get("parametros"):
                    tool_results_parts.append(f"### Parametros {tab}\n{_json.dumps(params, ensure_ascii=False, indent=2)}")
            except Exception:
                pass

        tool_results_text = "\n\n".join(tool_results_parts) or "Nenhum dado de investigacao encontrado."

        # ── Phase 2: LLM generates markdown + JSON ──
        prompt = f"""Analise o processo "{nome}" (tipo: {tipo}, criticidade: {row[4]}).
Descricao: {descricao}
Tabelas envolvidas: {', '.join(tabelas)}

DADOS DE INVESTIGACAO:
{tool_results_text}

Gere DUAS saidas:

1. ANALISE EM MARKDOWN — relatorio tecnico completo com secoes:
## Write Points
## Triggers e Gatilhos
## Entry Points (PEs)
## Parametros Relacionados
## Fontes Envolvidas
## Condicoes Criticas
## Resumo do Processo

2. JSON ESTRUTURADO — no formato abaixo (dentro de um bloco ```json):
```json
{{
  "tabelas": [
    {{
      "codigo": "XXX",
      "write_points": [
        {{ "fonte": "ARQUIVO.PRW", "funcao": "Funcao", "campos": ["CAMPO1"], "condicao": "cond" }}
      ],
      "triggers": [
        {{ "campo": "CAMPO", "gatilho": "U_FUNC", "tipo": "change" }}
      ],
      "operacoes": [
        {{ "tipo": "reclock", "funcao": "Funcao", "modo": "inclusao" }}
      ]
    }}
  ],
  "entry_points": [
    {{ "pe": "NOME_PE", "fonte": "ARQUIVO.PRW", "descricao": "desc" }}
  ],
  "parametros": [
    {{ "nome": "MV_XXXX", "conteudo": "valor", "descricao": "desc" }}
  ],
  "fontes_envolvidas": ["ARQUIVO1.PRW", "ARQUIVO2.PRW"],
  "condicoes_criticas": [
    {{ "condicao": "expr", "impacto": "desc", "fonte": "ARQUIVO.PRW" }}
  ]
}}
```

Retorne PRIMEIRO o markdown completo, depois o bloco JSON.
Baseie-se APENAS nos dados de investigacao fornecidos. Nao invente dados."""

        messages = [{"role": "user", "content": prompt}]
        text = llm.chat(messages)

        # ── Phase 3: Parse response ──
        # Extract JSON block
        json_match = re.search(r"```json\s*([\s\S]*?)```", text)
        analise_json_str = "{}"
        if json_match:
            try:
                analise_json_obj = _json.loads(json_match.group(1).strip())
                analise_json_str = _json.dumps(analise_json_obj, ensure_ascii=False)
            except _json.JSONDecodeError:
                analise_json_str = "{}"

        # Markdown = everything before the JSON block (or full text if no JSON block)
        if json_match:
            analise_md = text[:json_match.start()].strip()
        else:
            analise_md = text.strip()

        # ── Phase 4: Save ──
        from datetime import datetime
        now = datetime.utcnow().isoformat()
        db.execute(
            "UPDATE processos_detectados SET analise_markdown=?, analise_json=?, analise_updated_at=? WHERE id=?",
            (analise_md, analise_json_str, now, processo_id),
        )
        db.commit()
        db.close()

        return {
            "analise_markdown": analise_md,
            "analise_json": _json.loads(analise_json_str),
            "analise_updated_at": now,
        }

    except Exception:
        # Reset generating flag on error
        db.execute(
            "UPDATE processos_detectados SET analise_updated_at = NULL WHERE id = ? AND analise_updated_at = 'generating'",
            (processo_id,),
        )
        db.commit()
        db.close()
        raise
```

- [ ] **Step 2: Add the API endpoint**

Add the endpoint after `gerar_fluxo_processo_endpoint` (after line 470):

```python
@router.get("/processos/{processo_id}/analise")
async def get_analise_processo(processo_id: int, force: bool = False):
    """Get (or generate) technical analysis for a detected process."""
    import asyncio
    from backend.routers.chat import _get_services

    config = load_config(CONFIG_PATH)
    if not config or not config.active_client:
        raise HTTPException(400, "No active client")
    client_dir = get_client_workspace(WORKSPACE, config.active_client)
    db_path = client_dir / "db" / "extrairpo.db"

    try:
        db_svc, vs, ks, llm, _ = _get_services()
    except Exception as e:
        try:
            from backend.services.llm import LLMService
            llm = LLMService(**config.llm)
        except Exception:
            raise HTTPException(500, f"Erro ao iniciar servicos: {str(e)[:200]}")

    try:
        result = await asyncio.to_thread(gerar_analise_processo, db_path, llm, processo_id, force)
    except TimeoutError:
        raise HTTPException(504, "Analise em geracao por outra requisicao — timeout")
    except Exception as e:
        raise HTTPException(500, f"Erro ao gerar analise: {str(e)[:300]}")

    if result is None:
        raise HTTPException(404, "Processo nao encontrado")

    return result
```

- [ ] **Step 3: Verify endpoint is importable**

Run: `cd d:/IA/Projetos/Protheus && python -c "from backend.routers.analista import router; print('Router OK')"`

Expected: `Router OK`

- [ ] **Step 4: Commit**

```bash
git add backend/routers/analista.py
git commit -m "feat(api): add GET /processos/{id}/analise — generates and caches technical analysis"
```

---

## Chunk 3: Backend — Process Chat Endpoint

### Task 3: Add chat endpoint for process conversations

**Files:**
- Modify: `backend/routers/analista.py` (add after the analise endpoint)

- [ ] **Step 1: Add the chat endpoint**

Add after the `get_analise_processo` endpoint. This follows the same SSE pattern as `chat_conversa` (line 473):

```python
@router.post("/processos/{processo_id}/chat")
async def chat_processo(processo_id: int, body: ChatMessage):
    """SSE streaming chat scoped to a process — uses duvida mode with process context."""
    import traceback
    from backend.routers.chat import _get_services
    from backend.services.analista_tools import (
        tool_analise_impacto, tool_info_tabela,
        tool_operacoes_tabela,
    )
    from backend.services.analista_prompts import SYSTEM_PROMPT_DUVIDA

    try:
        db_svc, vs, ks, llm, client_dir = _get_services()
    except Exception as e:
        try:
            from backend.services.config import load_config as _lc, get_client_workspace as _gcw
            from backend.services.database import Database as _Db
            from backend.services.knowledge import KnowledgeService
            from backend.services.llm import LLMService
            _cfg = _lc(Path("config.json"))
            client_dir = _gcw(Path("workspace"), _cfg.active_client)
            db_svc = _Db(client_dir / "db" / "extrairpo.db")
            db_svc.initialize()
            vs = None
            ks = KnowledgeService(db_svc)
            llm = LLMService(**_cfg.llm)
        except Exception as e2:
            raise HTTPException(500, f"Erro ao iniciar servicos: {str(e)[:200]}")

    db = _get_db()
    try:
        # Load process
        row = db.execute(
            "SELECT id, nome, tipo, descricao, tabelas, analise_json "
            "FROM processos_detectados WHERE id = ?",
            (processo_id,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Processo nao encontrado")

        proc_nome = row[1]
        proc_tabelas = json.loads(row[4]) if row[4] else []
        analise_json = row[5] or "{}"

        # Save user message immediately
        db.execute(
            "INSERT INTO processo_mensagens (processo_id, role, content) VALUES (?, 'user', ?)",
            (processo_id, body.message),
        )
        db.commit()

        # Load last 30 messages for context
        hist_rows = db.execute(
            "SELECT role, content FROM processo_mensagens WHERE processo_id = ? ORDER BY id DESC LIMIT 30",
            (processo_id,),
        ).fetchall()
        hist_rows = list(reversed(hist_rows))  # chronological order

        processo_id_val = processo_id

        async def event_generator():
            yield {"event": "status", "data": json.dumps({"step": "Investigando contexto do processo..."})}

            # ── Phase 1: Gather tool results (sync, same pattern as chat_conversa) ──
            tool_results_parts = []
            try:
                for tab in proc_tabelas[:5]:
                    try:
                        info = tool_info_tabela(tab)
                        if info.get("existe"):
                            tool_results_parts.append(f"Info {tab}: {json.dumps(info, ensure_ascii=False)}")
                    except Exception:
                        pass
                    try:
                        impacto = tool_analise_impacto(tab)
                        if impacto:
                            tool_results_parts.append(f"Impacto {tab}: {json.dumps(impacto, ensure_ascii=False)}")
                    except Exception:
                        pass
                    try:
                        ops = tool_operacoes_tabela(tab)
                        if ops and ops.get("operacoes"):
                            tool_results_parts.append(f"Operacoes {tab}: {json.dumps(ops, ensure_ascii=False)}")
                    except Exception:
                        pass
            except Exception as e:
                traceback.print_exc()

            tool_results_text = "\n".join(tool_results_parts)

            # Build context with process info + existing analysis
            context = f"""PROCESSO: {proc_nome}
Tabelas: {', '.join(proc_tabelas)}
Analise tecnica existente (JSON): {analise_json}
"""

            system_prompt = SYSTEM_PROMPT_DUVIDA.format(
                context=context,
                tool_results=tool_results_text,
            )

            # Build messages
            messages = [{"role": "system", "content": system_prompt}]
            for h_role, h_content in hist_rows:
                messages.append({"role": h_role, "content": h_content})

            # ── Phase 2: Stream LLM response ──
            yield {"event": "status", "data": json.dumps({"step": "Gerando resposta..."})}

            full_text = ""
            try:
                for chunk in llm.chat_stream(messages):
                    full_text += chunk
                    yield {"event": "content", "data": json.dumps({"text": chunk})}
            except Exception as e:
                yield {"event": "error", "data": json.dumps({"error": str(e)[:300]})}
                return

            # ── Phase 3: Save assistant message (only after full stream) ──
            db2 = _get_db()
            try:
                db2.execute(
                    "INSERT INTO processo_mensagens (processo_id, role, content) VALUES (?, 'assistant', ?)",
                    (processo_id_val, full_text),
                )
                db2.commit()

                # ── Phase 4: Evaluate enrichment (V1 heuristic — append max 3 times) ──
                # Only enrich if analysis exists and response has technical content
                existing_analysis = json.loads(analise_json) if analise_json and analise_json != "{}" else None
                if existing_analysis and any(kw in full_text.lower() for kw in ["reclock", "gatilho", "trigger", "ponto de entrada", "pe_", "u_"]):
                    # Count existing enrichments to avoid unbounded growth
                    existing_md = db2.execute(
                        "SELECT analise_markdown FROM processos_detectados WHERE id = ?",
                        (processo_id_val,),
                    ).fetchone()
                    enrichment_count = (existing_md[0] or "").count("## Complemento via Chat") if existing_md else 0
                    if enrichment_count < 3:
                        db2.execute(
                            """UPDATE processos_detectados
                            SET analise_markdown = COALESCE(analise_markdown, '') || char(10) || char(10) || '## Complemento via Chat' || char(10) || ?,
                                analise_updated_at = datetime('now')
                            WHERE id = ?""",
                            (full_text[:2000], processo_id_val),
                        )
                        db2.commit()
            finally:
                db2.close()

            yield {"event": "done", "data": json.dumps({"status": "ok"})}

        return EventSourceResponse(event_generator())
    finally:
        db.close()
```

- [ ] **Step 2: Add endpoint to load chat history**

Add a GET endpoint to load existing messages (for when the dialog opens):

```python
@router.get("/processos/{processo_id}/mensagens")
def listar_mensagens_processo(processo_id: int, limit: int = 30, offset: int = 0):
    """List chat messages for a process."""
    db = _get_db()
    try:
        total = db.execute(
            "SELECT COUNT(*) FROM processo_mensagens WHERE processo_id = ?",
            (processo_id,),
        ).fetchone()[0]
        rows = db.execute(
            "SELECT id, role, content, created_at FROM processo_mensagens "
            "WHERE processo_id = ? ORDER BY id DESC LIMIT ? OFFSET ?",
            (processo_id, limit, offset),
        ).fetchall()
        mensagens = [
            {"id": r[0], "role": r[1], "content": r[2], "created_at": r[3]}
            for r in reversed(rows)
        ]
        return {"total": total, "mensagens": mensagens}
    finally:
        db.close()
```

- [ ] **Step 3: Verify endpoints are importable**

Run: `cd d:/IA/Projetos/Protheus && python -c "from backend.routers.analista import router; print('Router OK')"`

Expected: `Router OK`

- [ ] **Step 4: Commit**

```bash
git add backend/routers/analista.py
git commit -m "feat(api): add POST /processos/{id}/chat + GET /processos/{id}/mensagens"
```

---

## Chunk 4: Backend — Process Registration Endpoint + Tool

### Task 4: Add registration endpoint and Analista tool

**Files:**
- Modify: `backend/routers/analista.py` (add endpoint)
- Modify: `backend/services/analista_tools.py:1500+` (add tool)
- Modify: `backend/services/analista_prompts.py:66-68,110-116,242-245` (add instruction to prompts)

- [ ] **Step 1: Add `registrar_ou_enriquecer_processo` helper in `analista_tools.py`**

Add after `tool_processos_cliente` (after line 1534):

```python
def tool_registrar_processo(
    nome: str, tipo: str, descricao: str,
    tabelas: list[str] | None = None, criticidade: str = "media",
) -> dict:
    """Register or enrich a client business process.
    If a similar process exists (by name), enriches it. Otherwise creates new.
    Used silently by the Analista during conversations.

    Args:
        nome: Process name (e.g. 'Gestão de Exportação')
        tipo: Process type (workflow, integracao, logistica, fiscal, automacao, qualidade, outro)
        descricao: Free-text description
        tabelas: List of involved table codes
        criticidade: alta, media, baixa
    """
    import json as _json

    db = _get_db()
    try:
        tabelas = tabelas or []

        # Stage 1: Cheap text match
        termos = nome.lower().split()
        candidatos = []
        for termo in termos:
            if len(termo) < 3:
                continue
            rows = db.execute(
                "SELECT id, nome, tipo, descricao, tabelas, score FROM processos_detectados "
                "WHERE lower(nome) LIKE ? OR lower(descricao) LIKE ? "
                "ORDER BY score DESC LIMIT 10",
                (f"%{termo}%", f"%{termo}%"),
            ).fetchall()
            for r in rows:
                if r[0] not in [c["id"] for c in candidatos]:
                    candidatos.append({
                        "id": r[0], "nome": r[1], "tipo": r[2],
                        "descricao": r[3], "tabelas": _safe_json(r[4]), "score": r[5],
                    })

        # Stage 2: Simplified from spec's LLM-based matching to avoid nested LLM calls
        # from within tool execution context. Uses substring match instead of LLM scoring.
        best_match = None
        if candidatos:
            nome_lower = nome.lower().strip()
            for c in candidatos:
                c_nome_lower = c["nome"].lower().strip()
                # Exact or near-exact match
                if c_nome_lower == nome_lower or nome_lower in c_nome_lower or c_nome_lower in nome_lower:
                    best_match = c
                    break

        if best_match:
            # Enrich existing process
            existing_tabs = set(best_match["tabelas"])
            new_tabs = existing_tabs | set(tabelas)
            new_desc = best_match["descricao"]
            if descricao and descricao not in new_desc:
                new_desc = f"{new_desc}\n{descricao}".strip()

            db.execute(
                "UPDATE processos_detectados SET tabelas=?, descricao=?, updated_at=datetime('now') WHERE id=?",
                (_json.dumps(list(new_tabs)), new_desc, best_match["id"]),
            )
            db.commit()

            return {
                "acao": "enriquecido",
                "processo": {**best_match, "tabelas": list(new_tabs), "descricao": new_desc},
            }
        else:
            # Create new process
            db.execute(
                "INSERT INTO processos_detectados (nome, tipo, descricao, criticidade, tabelas, metodo, score) "
                "VALUES (?, ?, ?, ?, ?, 'manual', 0.5)",
                (nome, tipo, descricao, criticidade, _json.dumps(tabelas)),
            )
            db.commit()
            new_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

            return {
                "acao": "criado",
                "processo": {
                    "id": new_id, "nome": nome, "tipo": tipo, "descricao": descricao,
                    "criticidade": criticidade, "tabelas": tabelas, "score": 0.5,
                },
            }
    finally:
        db.close()
```

- [ ] **Step 2: Add registration endpoint in `analista.py`**

Add after the chat endpoint:

```python
class RegistrarProcessoBody(BaseModel):
    descricao: str

@router.post("/processos/registrar")
async def registrar_processo(body: RegistrarProcessoBody):
    """Register or enrich a process from a free-text description."""
    import asyncio
    from backend.routers.chat import _get_services

    try:
        db_svc, vs, ks, llm, client_dir = _get_services()
    except Exception as e:
        try:
            from backend.services.llm import LLMService
            config = load_config(CONFIG_PATH)
            llm = LLMService(**config.llm)
        except Exception:
            raise HTTPException(500, f"Erro ao iniciar servicos: {str(e)[:200]}")

    # Step 1: Extract structured data from description via LLM
    extract_prompt = f"""Extraia as informacoes de processo de negocio do texto abaixo.
Retorne APENAS um JSON:
{{"nome": "Nome do Processo", "tipo": "workflow|integracao|logistica|fiscal|automacao|qualidade|outro", "descricao": "descricao limpa", "tabelas": ["TAB1", "TAB2"], "criticidade": "alta|media|baixa"}}

Texto: {body.descricao}"""

    try:
        response = await asyncio.to_thread(llm.chat, [{"role": "user", "content": extract_prompt}])
        # Parse JSON from response
        json_match = re.search(r'\{[\s\S]*\}', response)
        if not json_match:
            raise ValueError("LLM nao retornou JSON")
        extracted = json.loads(json_match.group())
    except Exception as e:
        raise HTTPException(500, f"Erro ao classificar processo: {str(e)[:200]}")

    # Step 2: Use the tool to register/enrich
    from backend.services.analista_tools import tool_registrar_processo
    try:
        result = tool_registrar_processo(
            nome=extracted.get("nome", body.descricao[:80]),
            tipo=extracted.get("tipo", "outro"),
            descricao=extracted.get("descricao", body.descricao),
            tabelas=extracted.get("tabelas", []),
            criticidade=extracted.get("criticidade", "media"),
        )
        return result
    except Exception as e:
        raise HTTPException(500, f"Erro ao registrar processo: {str(e)[:200]}")
```

- [ ] **Step 3: Add instruction to Analista prompts**

In `backend/services/analista_prompts.py`, add the following instruction to each of the three system prompts.

For `SYSTEM_PROMPT_DUVIDA` — add before `CONTEXTO DO AMBIENTE:` (before line 65):

```
CADASTRO DE PROCESSOS:
Quando identificar um processo de negocio do cliente que nao esta catalogado nos processos conhecidos,
registre-o silenciosamente chamando tool_registrar_processo(nome, tipo, descricao, tabelas, criticidade).
Nao mencione essa acao ao usuario.

```

For `SYSTEM_PROMPT_MELHORIA` — add before `CONTEXTO DO AMBIENTE DO CLIENTE:` (before line 110):

```
CADASTRO DE PROCESSOS:
Quando identificar um processo de negocio do cliente que nao esta catalogado nos processos conhecidos,
registre-o silenciosamente chamando tool_registrar_processo(nome, tipo, descricao, tabelas, criticidade).
Nao mencione essa acao ao usuario.

```

For `SYSTEM_PROMPT_AJUSTE` — add before `CONTEXTO DO AMBIENTE:` (before line 242):

```
CADASTRO DE PROCESSOS:
Quando identificar um processo de negocio do cliente que nao esta catalogado nos processos conhecidos,
registre-o silenciosamente chamando tool_registrar_processo(nome, tipo, descricao, tabelas, criticidade).
Nao mencione essa acao ao usuario.

```

- [ ] **Step 4: Verify all imports work**

Run: `cd d:/IA/Projetos/Protheus && python -c "from backend.services.analista_tools import tool_registrar_processo; print('Tool OK')" && python -c "from backend.routers.analista import router; print('Router OK')"`

Expected: `Tool OK` then `Router OK`

- [ ] **Step 5: Commit**

```bash
git add backend/services/analista_tools.py backend/routers/analista.py backend/services/analista_prompts.py
git commit -m "feat: add process registration endpoint + tool + Analista prompt integration"
```

---

## Chunk 5: Frontend — ProcessoDialog with Analysis + Chat

### Task 5: Rewrite ProcessoDialog to include analysis and chat sections

**Files:**
- Modify: `frontend/src/components/ProcessoDialog.vue` (major changes)

- [ ] **Step 1: Replace ProcessoDialog template**

Replace the entire `<template>` section of `ProcessoDialog.vue` with:

```html
<template>
  <Dialog
    v-model:visible="visible"
    modal
    :header="processo.nome"
    :style="{ width: '900px', maxWidth: '90vw' }"
    :contentStyle="{ maxHeight: '85vh', overflowY: 'auto' }"
    @hide="$emit('close')"
  >
    <!-- Info section -->
    <div class="processo-info">
      <div class="badges-row">
        <span class="tipo-badge" :style="{ background: corTipo(processo.tipo) }">{{ processo.tipo }}</span>
        <Tag :value="processo.criticidade" :severity="criticidadeSeverity" class="crit-tag" />
        <span :class="scoreClass" class="score-badge">Score: {{ processo.score?.toFixed(2) ?? '—' }}</span>
      </div>
      <p class="descricao">{{ processo.descricao }}</p>
      <div v-if="processo.tabelas && processo.tabelas.length" class="tabelas-row">
        <Chip v-for="t in processo.tabelas" :key="t" :label="t" class="tabela-chip" />
      </div>
    </div>

    <hr class="section-divider" />

    <!-- Fluxo section -->
    <div class="fluxo-section">
      <div class="section-header">
        <h4 class="section-title">Fluxo do Processo</h4>
        <div class="section-actions">
          <Button v-if="!diagramaGerado && !loadingFluxo" label="Gerar fluxo" icon="pi pi-diagram-organization" size="small" @click="gerarFluxo(false)" />
          <Button v-if="diagramaGerado && !loadingFluxo" label="Regenerar" icon="pi pi-refresh" size="small" severity="secondary" @click="gerarFluxo(true)" />
        </div>
      </div>
      <div v-if="loadingFluxo" class="skeleton-wrapper"><Skeleton height="180px" /></div>
      <div v-show="diagramaGerado && !loadingFluxo && !showFallback" ref="mermaidContainer" class="mermaid-container"></div>
      <div v-if="showFallback && !loadingFluxo" class="fallback-box">
        <p class="fallback-label">Diagrama indisponivel</p>
        <p class="fallback-text">{{ processo.descricao }}</p>
      </div>
    </div>

    <hr class="section-divider" />

    <!-- Analise Tecnica section -->
    <div class="analise-section">
      <div class="section-header">
        <h4 class="section-title">Analise Tecnica</h4>
        <div class="section-actions">
          <Button v-if="analiseMarkdown && !loadingAnalise" label="Regerar" icon="pi pi-refresh" size="small" severity="secondary" @click="gerarAnalise(true)" />
        </div>
      </div>
      <div v-if="loadingAnalise" class="skeleton-wrapper">
        <Skeleton height="40px" class="mb-2" />
        <Skeleton height="200px" />
        <p class="loading-label">Gerando analise tecnica...</p>
      </div>
      <div v-else-if="analiseMarkdown" class="analise-content" v-html="renderedAnalise"></div>
      <div v-else class="empty-analise">
        <p>Analise tecnica nao gerada ainda.</p>
        <Button label="Gerar Analise" icon="pi pi-search" size="small" @click="gerarAnalise(false)" />
      </div>
    </div>

    <hr class="section-divider" />

    <!-- Chat section -->
    <div class="chat-section">
      <div class="section-header">
        <h4 class="section-title">Chat do Processo</h4>
      </div>
      <div class="chat-messages" ref="chatContainer">
        <div v-for="msg in mensagens" :key="msg.id || msg.created_at" :class="['chat-msg', `chat-${msg.role}`]">
          <div class="msg-role">{{ msg.role === 'user' ? 'Voce' : 'Analista' }}</div>
          <div class="msg-content" v-html="msg.role === 'assistant' ? renderMd(msg.content) : msg.content"></div>
        </div>
        <div v-if="streamingText" class="chat-msg chat-assistant">
          <div class="msg-role">Analista</div>
          <div class="msg-content" v-html="renderMd(streamingText)"></div>
        </div>
      </div>
      <div class="chat-input-row">
        <InputText v-model="chatInput" placeholder="Pergunte sobre este processo..." class="chat-input" @keydown.enter="enviarChat" :disabled="chatLoading" />
        <Button icon="pi pi-send" :loading="chatLoading" @click="enviarChat" size="small" />
      </div>
    </div>

    <!-- Footer -->
    <template #footer>
      <Button label="Fechar" icon="pi pi-times" severity="secondary" @click="$emit('close')" />
    </template>
  </Dialog>
</template>
```

- [ ] **Step 2: Replace script section**

Replace the entire `<script setup>` block:

```javascript
<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import { useToast } from 'primevue/usetoast'
import Dialog from 'primevue/dialog'
import Button from 'primevue/button'
import Tag from 'primevue/tag'
import Chip from 'primevue/chip'
import Skeleton from 'primevue/skeleton'
import InputText from 'primevue/inputtext'
import axios from 'axios'
import mermaid from 'mermaid'
import { marked } from 'marked'
import { ensureInit } from '../composables/useMermaid.js'

const props = defineProps({
  processo: { type: Object, required: true },
})
const emit = defineEmits(['close'])
const toast = useToast()

const API = '/api'
const visible = ref(true)

// ── Fluxo state ──
const loadingFluxo = ref(false)
const diagramaGerado = ref(false)
const showFallback = ref(false)
const mermaidContainer = ref(null)

// ── Analise state ──
const loadingAnalise = ref(false)
const analiseMarkdown = ref(null)
const analiseJson = ref(null)

// ── Chat state ──
const mensagens = ref([])
const chatInput = ref('')
const chatLoading = ref(false)
const streamingText = ref('')
const chatContainer = ref(null)

// ── Badge helpers ──
const TIPO_CORES = {
  workflow: '#9c27b0', integracao: '#0277bd', logistica: '#e65100',
  fiscal: '#1b5e20', automacao: '#1b5e20', regulatorio: '#37474f',
  auditoria: '#4e342e', qualidade: '#00695c', relatorio: '#0097a7',
}
function corTipo(tipo) { return TIPO_CORES[tipo] || '#607d8b' }

const criticidadeSeverity = computed(() => {
  if (props.processo.criticidade === 'alta') return 'danger'
  if (props.processo.criticidade === 'media') return 'warn'
  return 'secondary'
})

const scoreClass = computed(() => {
  const s = props.processo.score
  if (s >= 0.85) return 'score-alto'
  if (s >= 0.7) return 'score-medio'
  return 'score-baixo'
})

// ── Markdown rendering ──
function renderMd(text) {
  if (!text) return ''
  return marked(text, { breaks: true })
}
const renderedAnalise = computed(() => renderMd(analiseMarkdown.value))

// ── Fluxo Mermaid ──
async function renderMermaid(mermaidStr) {
  showFallback.value = false
  const id = `mermaid-${Math.random().toString(36).slice(2, 10)}`
  ensureInit()
  try {
    const { svg } = await mermaid.render(id, mermaidStr)
    if (mermaidContainer.value) mermaidContainer.value.innerHTML = svg
    diagramaGerado.value = true
  } catch (err) {
    document.getElementById(id)?.remove()
    document.querySelectorAll('.mermaid-error, [id^="dmermaid-"]').forEach(el => el.remove())
    showFallback.value = true
  }
}

async function gerarFluxo(force = false) {
  loadingFluxo.value = true
  showFallback.value = false
  try {
    const res = await axios.post(`${API}/analista/processos/${props.processo.id}/fluxo${force ? '?force=true' : ''}`)
    await renderMermaid(res.data.fluxo_mermaid)
  } catch {
    toast.add({ severity: 'error', summary: 'Erro ao gerar fluxo.', life: 4000 })
  } finally {
    loadingFluxo.value = false
  }
}

// ── Analise Tecnica ──
async function gerarAnalise(force = false) {
  loadingAnalise.value = true
  try {
    const res = await axios.get(`${API}/analista/processos/${props.processo.id}/analise${force ? '?force=true' : ''}`)
    analiseMarkdown.value = res.data.analise_markdown
    analiseJson.value = res.data.analise_json
  } catch (err) {
    if (err.response?.status === 504) {
      toast.add({ severity: 'warn', summary: 'Analise sendo gerada por outra requisicao, aguarde.', life: 5000 })
    } else {
      toast.add({ severity: 'error', summary: 'Erro ao gerar analise tecnica.', life: 4000 })
    }
  } finally {
    loadingAnalise.value = false
  }
}

// ── Chat ──
async function carregarMensagens() {
  try {
    const res = await axios.get(`${API}/analista/processos/${props.processo.id}/mensagens`)
    mensagens.value = res.data.mensagens || []
  } catch { /* silent */ }
}

function scrollChatBottom() {
  nextTick(() => {
    if (chatContainer.value) chatContainer.value.scrollTop = chatContainer.value.scrollHeight
  })
}

async function enviarChat() {
  const msg = chatInput.value.trim()
  if (!msg || chatLoading.value) return

  chatInput.value = ''
  chatLoading.value = true
  streamingText.value = ''

  // Optimistic add
  mensagens.value.push({ role: 'user', content: msg, created_at: new Date().toISOString() })
  scrollChatBottom()

  try {
    const response = await fetch(`${API}/analista/processos/${props.processo.id}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: msg }),
    })

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (line.startsWith('data:')) {
          try {
            const payload = JSON.parse(line.slice(5).trim())
            if (payload.text) {
              streamingText.value += payload.text
              scrollChatBottom()
            }
          } catch { /* skip non-JSON lines */ }
        }
      }
    }

    // Stream complete — move streaming text to messages
    if (streamingText.value) {
      mensagens.value.push({ role: 'assistant', content: streamingText.value, created_at: new Date().toISOString() })
    }
    streamingText.value = ''
    scrollChatBottom()
  } catch (err) {
    toast.add({ severity: 'error', summary: 'Erro no chat.', life: 4000 })
  } finally {
    chatLoading.value = false
  }
}

// ── Init ──
onMounted(async () => {
  // Load fluxo if cached
  if (props.processo.fluxo_mermaid) {
    loadingFluxo.value = true
    await renderMermaid(props.processo.fluxo_mermaid)
    loadingFluxo.value = false
  }
  // Auto-load analysis
  gerarAnalise(false)
  // Load chat history
  carregarMensagens()
})
</script>
```

- [ ] **Step 3: Replace style section**

Replace the entire `<style scoped>` block:

```css
<style scoped>
.processo-info { display: flex; flex-direction: column; gap: 0.75rem; }
.badges-row { display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; }
.tipo-badge { color: #fff; border-radius: 4px; padding: 2px 8px; font-size: 0.75rem; font-weight: 600; }
.score-badge { font-weight: 700; font-size: 0.9rem; padding: 2px 8px; border-radius: 4px; background: #f5f5f5; }
.score-alto { color: #2e7d32; }
.score-medio { color: #f57f17; }
.score-baixo { color: #888; }
.descricao { margin: 0; color: #444; line-height: 1.5; }
.tabelas-row { display: flex; flex-wrap: wrap; gap: 0.4rem; }
.tabela-chip { font-size: 0.78rem; }
.section-divider { border: none; border-top: 1px solid #e0e0e0; margin: 1rem 0; }
.section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem; }
.section-title { margin: 0; font-size: 1rem; color: #333; }
.section-actions { display: flex; gap: 0.4rem; }
.skeleton-wrapper { padding: 0.5rem 0; }
.mermaid-container { overflow-x: auto; background: #fafafa; border: 1px solid #e0e0e0; border-radius: 6px; padding: 0.75rem; min-height: 60px; }
.fallback-box { background: #fff8e1; border: 1px solid #ffe082; border-radius: 6px; padding: 0.75rem 1rem; }
.fallback-label { margin: 0 0 0.4rem; font-weight: 600; color: #e65100; font-size: 0.85rem; }
.fallback-text { margin: 0; color: #555; font-size: 0.9rem; line-height: 1.5; }

/* Analise */
.analise-content { background: #fafafa; border: 1px solid #e0e0e0; border-radius: 6px; padding: 1rem; max-height: 400px; overflow-y: auto; font-size: 0.9rem; line-height: 1.6; }
.analise-content :deep(h2) { font-size: 1rem; color: #1565c0; margin-top: 1rem; margin-bottom: 0.5rem; }
.analise-content :deep(h3) { font-size: 0.9rem; color: #333; margin-top: 0.75rem; }
.analise-content :deep(ul) { padding-left: 1.2rem; }
.analise-content :deep(code) { background: #e3f2fd; padding: 1px 4px; border-radius: 3px; font-size: 0.85rem; }
.empty-analise { text-align: center; padding: 1rem; color: #888; }
.loading-label { text-align: center; color: #888; font-size: 0.85rem; margin-top: 0.5rem; }
.mb-2 { margin-bottom: 0.5rem; }

/* Chat */
.chat-section { display: flex; flex-direction: column; gap: 0.5rem; }
.chat-messages { max-height: 250px; overflow-y: auto; display: flex; flex-direction: column; gap: 0.5rem; padding: 0.5rem; background: #fafafa; border: 1px solid #e0e0e0; border-radius: 6px; min-height: 80px; }
.chat-msg { padding: 0.5rem 0.75rem; border-radius: 6px; max-width: 85%; }
.chat-user { background: #e3f2fd; align-self: flex-end; }
.chat-assistant { background: #f5f5f5; align-self: flex-start; }
.msg-role { font-size: 0.7rem; font-weight: 600; color: #888; margin-bottom: 2px; }
.msg-content { font-size: 0.85rem; line-height: 1.5; }
.msg-content :deep(p) { margin: 0.25rem 0; }
.msg-content :deep(code) { background: #e8eaf6; padding: 1px 3px; border-radius: 2px; font-size: 0.8rem; }
.chat-input-row { display: flex; gap: 0.5rem; }
.chat-input { flex: 1; }
</style>
```

- [ ] **Step 4: Verify frontend builds**

Run: `cd d:/IA/Projetos/Protheus/frontend && npm run build 2>&1 | tail -5`

Expected: Build succeeds with no errors

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ProcessoDialog.vue
git commit -m "feat(ui): ProcessoDialog with analysis section + inline chat"
```

---

## Chunk 6: Frontend — "Incluir Processo" Button

### Task 6: Add "Incluir Processo" button to ProcessosCliente.vue

**Files:**
- Modify: `frontend/src/views/ProcessosCliente.vue`

- [ ] **Step 1: Add the include button and dialog to template**

In `ProcessosCliente.vue`, add the button in `header-filters` div (after line 26, after the Redescobrir button):

```html
        <Button
          label="Incluir Processo"
          icon="pi pi-plus"
          size="small"
          @click="showIncluirDialog = true"
        />
```

Add the dialog before the closing `</div>` of the root (before `</template>`):

```html
    <Dialog
      v-model:visible="showIncluirDialog"
      modal
      header="Incluir Processo"
      :style="{ width: '500px' }"
    >
      <p style="margin-bottom: 0.75rem; color: #666; font-size: 0.9rem;">
        Descreva o processo de negocio. O sistema vai verificar se ja existe e criar ou enriquecer automaticamente.
      </p>
      <Textarea
        v-model="incluirDescricao"
        rows="4"
        style="width: 100%;"
        placeholder="Ex: Processo de abate de gado com controle de lotes, pesagem e emissao de NF..."
        :disabled="incluirLoading"
      />
      <template #footer>
        <Button label="Cancelar" severity="secondary" @click="showIncluirDialog = false" />
        <Button label="Registrar" icon="pi pi-check" :loading="incluirLoading" @click="registrarProcesso" />
      </template>
    </Dialog>
```

- [ ] **Step 2: Add imports and state**

Add imports (line 91, after existing imports):

```javascript
import Dialog from 'primevue/dialog'
import Textarea from 'primevue/textarea'
```

Add state variables (after line 101):

```javascript
const showIncluirDialog = ref(false)
const incluirDescricao = ref('')
const incluirLoading = ref(false)
```

- [ ] **Step 3: Add the registration function**

Add after the `abrirDialog` function (after line 164):

```javascript
async function registrarProcesso() {
  if (!incluirDescricao.value.trim()) return
  incluirLoading.value = true
  try {
    const res = await axios.post('/api/analista/processos/registrar', {
      descricao: incluirDescricao.value.trim(),
    })
    const acao = res.data.acao
    const nome = res.data.processo?.nome || ''
    if (acao === 'criado') {
      toast.add({ severity: 'success', summary: `Processo "${nome}" criado com sucesso`, life: 4000 })
    } else {
      toast.add({ severity: 'info', summary: `Processo "${nome}" enriquecido com novas informacoes`, life: 4000 })
    }
    showIncluirDialog.value = false
    incluirDescricao.value = ''
    await carregarProcessos()
  } catch {
    toast.add({ severity: 'error', summary: 'Erro ao registrar processo.', life: 4000 })
  } finally {
    incluirLoading.value = false
  }
}
```

- [ ] **Step 4: Verify frontend builds**

Run: `cd d:/IA/Projetos/Protheus/frontend && npm run build 2>&1 | tail -5`

Expected: Build succeeds

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/ProcessosCliente.vue
git commit -m "feat(ui): add 'Incluir Processo' button with registration dialog"
```

---

## Chunk 7: Integration Verification

### Task 7: End-to-end smoke test

- [ ] **Step 1: Start the backend**

Run: `cd d:/IA/Projetos/Protheus && python -m uvicorn backend.main:app --reload --port 8000`

Verify: Server starts without import errors.

- [ ] **Step 2: Test analysis endpoint**

Run: `curl -s http://localhost:8000/api/analista/processos | python -m json.tool | head -20`

Verify: Returns process list. Pick a process ID.

Run: `curl -s "http://localhost:8000/api/analista/processos/1/analise" | python -m json.tool | head -10`

Verify: Returns analysis (generating if first time).

- [ ] **Step 3: Test registration endpoint**

Run: `curl -s -X POST http://localhost:8000/api/analista/processos/registrar -H "Content-Type: application/json" -d '{"descricao": "Processo de abate de gado com pesagem e lotes"}' | python -m json.tool`

Verify: Returns `{ "acao": "criado" | "enriquecido", "processo": {...} }`

- [ ] **Step 4: Test frontend**

Run: `cd d:/IA/Projetos/Protheus/frontend && npm run dev`

Open browser, navigate to Processos. Click a process — verify dialog shows analysis section loading. Verify chat input works. Verify "Incluir Processo" button opens dialog.

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "chore: integration smoke test passed for processos analise tecnica"
```
