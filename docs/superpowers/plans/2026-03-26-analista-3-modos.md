# Analista 3 Modos — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the 7-type demand system with 3 intention-based modes (Dúvidas, Melhorias, Ajustes) with specialized prompts, new API endpoints, and redesigned UI.

**Architecture:** Reuse existing tables (`analista_demandas`, `analista_mensagens`, `analista_artefatos`) with `tipo` field accepting new values (duvida, melhoria, ajuste). New endpoints under `/api/analista/conversas`. Frontend replaces list+wizard with 3-section card layout and mode-specific chat views.

**Tech Stack:** Python/FastAPI (backend), Vue 3 + PrimeVue (frontend), SQLite (database), SSE streaming (chat)

**Spec:** `docs/superpowers/specs/2026-03-26-analista-3-modos-design.md`

---

## File Structure

### Backend — Modified files:
- `backend/services/analista_prompts.py` — Replace single SYSTEM_PROMPT with 3 mode-specific prompts
- `backend/services/analista_schema.py` — Add migration for `modo` column, new status values
- `backend/routers/analista.py` — Add `/conversas` endpoints, mode-aware chat pipeline

### Frontend — Modified files:
- `frontend/src/views/AnalistaView.vue` — Redesign list view (3 sections), simplify chat modes

---

## Chunk 1: Backend — Prompts and Schema

### Task 1: Create 3 mode-specific prompts

**Files:**
- Modify: `backend/services/analista_prompts.py`

- [ ] **Step 1: Replace SYSTEM_PROMPT with 3 mode prompts**

Open `backend/services/analista_prompts.py` and replace the single `SYSTEM_PROMPT` with three:

```python
SYSTEM_PROMPT_DUVIDA = """Voce e um consultor tecnico senior de ambientes TOTVS Protheus.
O usuario e um consultor funcional que precisa ENTENDER o ambiente do cliente.

COMO RESPONDER:
- Consulte os dados reais do ambiente usando as ferramentas disponiveis
- Responda com informacoes CONCRETAS (nomes de fontes, campos, tabelas reais)
- Quando listar fontes: "ARQUIVO.prw (modulo, LOC linhas) — proposito"
- Quando listar campos: "CAMPO (tipo, tamanho) — titulo"
- Se nao encontrar dados, diga claramente "nao encontrei no ambiente"

VOCE PODE:
- Consultar qualquer tabela, campo, fonte, gatilho, parametro do ambiente
- Explicar como processos funcionam baseado nos dados reais
- Listar quem grava em qual campo e sob qual condicao (operacoes_escrita)
- Mostrar processos detectados do cliente
- Explicar padroes Protheus (MVC, PE, ExecAuto, etc.)

NAO FACA:
- Nao gere artefatos (campos, gatilhos, specs) a menos que pecam
- Nao proponha mudancas a menos que pecam
- Nao invente dados — use sempre as ferramentas

CONTEXTO DO AMBIENTE:
{context}

{tool_results}
"""

SYSTEM_PROMPT_MELHORIA = """Voce e um arquiteto tecnico senior de ambientes TOTVS Protheus.
O usuario e um consultor funcional que precisa CRIAR ou ALTERAR algo no ambiente.

REGRA #1 — NAO PERGUNTE, ANALISE E RESPONDA:
Quando o usuario diz "quero", "preciso", "vou fazer" — ELE JA DECIDIU.
Voce NAO deve perguntar "por que?", "qual o cenario?", "qual a regra de negocio?".
Em vez disso, VA DIRETO para a analise tecnica usando os dados do contexto.

PIPELINE DE TRABALHO:
1. COMPREENDER — Entenda o escopo, decomponha em artefatos necessarios
2. INVESTIGAR — Busque dados do ambiente (processos, ExecAutos, gatilhos, integracoes)
3. ANALISAR — Cruze informacoes, identifique riscos e dependencias
4. DECIDIR — Defina lista completa de artefatos necessarios (incluindo implicitos)
5. EXECUTAR — Gere specs completas de cada artefato

REGRAS DE ANALISE:
- Ao criar campo: verificar ExecAutos e RecLocks que gravam na tabela (operacoes_escrita)
- Ao criar campo obrigatorio: listar TODOS os pontos de inclusao que vao quebrar
- Ao criar gatilho: verificar sequencias ja usadas, copiar padrao de seek existente
- Identificar artefatos IMPLICITOS (ex: campo na SC6 pra gatilho funcionar)
- Listar processos do cliente que afetam as tabelas envolvidas
- Use BOM SENSO: ignore relatorios e leituras, foque em quem ESCREVE

FORMATO DE RESPOSTA:
- Texto conversacional limpo. Sem tabelas enormes, sem dumps de dados.
- Quando listar fontes de risco: "ARQUIVO.prw (modulo, LOC linhas)"
- Quando sugerir artefatos para o projeto, inclua ao final da mensagem:
###ARTEFATOS###
[{{"tipo": "campo|gatilho|pe|fonte|parametro|tabela|indice", "nome": "NOME", "tabela": "SA1", "acao": "criar|alterar", "descricao": "breve"}}]

CONTEXTO DO AMBIENTE:
{context}

ARTEFATOS JA DEFINIDOS:
{artefatos}

{tool_results}
"""

SYSTEM_PROMPT_AJUSTE = """Voce e um debugger tecnico senior de ambientes TOTVS Protheus.
O usuario e um consultor funcional que tem um PROBLEMA para resolver.

PIPELINE DE INVESTIGACAO:
1. ENTENDER — O que esta errado? Qual tabela, campo, fonte, rotina?
2. RASTREAR — Usar operacoes_escrita para encontrar TODOS os pontos que gravam
3. DIAGNOSTICAR — Seguir cadeia: quem chama quem, de onde vem o dado, qual condicao controla
4. PROPOR — Solucao com evidencias concretas

FERRAMENTAS DE INVESTIGACAO:
- operacoes_escrita: mostra quem grava em qual campo, origem do valor, condicao IF
- fonte_chunks: codigo fonte das funcoes
- funcao_docs: quem chama quem (chama/chamada_por)
- vinculos: grafo de relacionamentos (fonte->tabela, funcao->fonte)
- propositos: o que cada fonte faz

COMO RASTREAR:
1. "Quem grava no campo X?" -> operacoes_escrita WHERE campo LIKE '%X%'
2. "De onde vem o valor?" -> ver coluna 'origens' (tela, variavel, funcao, tabela, literal)
3. "Sob qual condicao?" -> ver coluna 'condicao' (IF que controla o RecLock)
4. "Quem chama essa funcao?" -> funcao_docs.chamada_por + vinculos
5. "Essa funcao e um Job/WS?" -> cruzar com jobs/schedules

FORMATO DE RESPOSTA:
- Apresente a cadeia de rastreamento passo a passo
- Mostre evidencias concretas (arquivo, funcao, linha, condicao)
- Destaque a CAUSA RAIZ com clareza
- Proponha solucao pratica

NAO FACA:
- Nao chute causas sem evidencia
- Nao proponha solucao sem antes rastrear
- Nao ignore pontos de escrita — liste TODOS

CONTEXTO DO AMBIENTE:
{context}

{tool_results}
"""
```

Keep existing template constants (`TEMPLATE_GERENCIAL`, `TEMPLATE_TECNICO_CAMPO`, etc.) unchanged.

Keep old `SYSTEM_PROMPT` as `SYSTEM_PROMPT_LEGADO` for backwards compatibility with old project chat.

- [ ] **Step 2: Add prompt selector helper**

Add at the end of `analista_prompts.py`:

```python
def get_system_prompt(modo: str) -> str:
    """Return the appropriate system prompt for the given mode."""
    prompts = {
        "duvida": SYSTEM_PROMPT_DUVIDA,
        "melhoria": SYSTEM_PROMPT_MELHORIA,
        "ajuste": SYSTEM_PROMPT_AJUSTE,
    }
    return prompts.get(modo, SYSTEM_PROMPT_MELHORIA)
```

- [ ] **Step 3: Commit**

```bash
git add backend/services/analista_prompts.py
git commit -m "feat: 3 prompts especializados (duvida, melhoria, ajuste)"
```

### Task 2: Schema migration

**Files:**
- Modify: `backend/services/analista_schema.py`

- [ ] **Step 1: Add modo column migration**

In `ensure_analista_tables()`, after the existing ALTER TABLE block, add:

```python
    # ── Migrations for 3-mode redesign ──
    for _sql in [
        "ALTER TABLE analista_demandas ADD COLUMN modo TEXT DEFAULT 'melhoria'",
    ]:
        try:
            db.execute(_sql)
            db.commit()
        except Exception:
            pass
```

- [ ] **Step 2: Add data migration function**

Add after `migrate_projetos_to_demandas`:

```python
def migrate_demandas_to_modos(db: Database) -> int:
    """Set modo for existing demandas based on their tipo.

    bug -> ajuste, everything else -> melhoria.
    Returns number of rows updated.
    """
    db.execute("""
        UPDATE analista_demandas
        SET modo = CASE
            WHEN tipo = 'bug' THEN 'ajuste'
            ELSE 'melhoria'
        END
        WHERE modo IS NULL OR modo = 'melhoria'
        AND tipo NOT IN ('duvida', 'melhoria', 'ajuste')
    """)
    count = db.execute("SELECT changes()").fetchone()[0]
    db.commit()
    return count
```

- [ ] **Step 3: Commit**

```bash
git add backend/services/analista_schema.py
git commit -m "feat: schema migration — add modo column to analista_demandas"
```

---

## Chunk 2: Backend — New /conversas endpoints

### Task 3: Create /conversas API endpoints

**Files:**
- Modify: `backend/routers/analista.py`

- [ ] **Step 1: Add imports and models**

At the top of `analista.py`, after existing imports, the `migrate_demandas_to_modos` import will be added to `_ensure_tables`. Add new Pydantic models after existing ones:

```python
class ConversaCreate(BaseModel):
    modo: str  # duvida, melhoria, ajuste
    nome: str = ""
    descricao: str = ""
```

- [ ] **Step 2: Add _ensure_tables update**

In `_ensure_tables()`, add the migration call:

```python
def _ensure_tables(db: Database):
    global _migration_done
    ensure_analista_tables(db)
    seed_diretrizes(db)
    if not _migration_done:
        n = migrate_projetos_to_demandas(db)
        if n > 0:
            print(f"[analista] Migrated {n} projetos -> demandas")
        from backend.services.analista_schema import migrate_demandas_to_modos
        m = migrate_demandas_to_modos(db)
        if m > 0:
            print(f"[analista] Migrated {m} demandas -> modos")
        _migration_done = True
```

- [ ] **Step 3: Add GET /conversas endpoint**

```python
@router.get("/conversas")
async def list_conversas(modo: str = None):
    """List conversations, optionally filtered by modo (duvida|melhoria|ajuste)."""
    db = _get_db()
    try:
        _ensure_tables(db)
        if modo:
            rows = db.execute(
                "SELECT id, tipo, nome, descricao, status, modo, created_at, updated_at "
                "FROM analista_demandas WHERE modo=? ORDER BY updated_at DESC",
                (modo,)
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT id, tipo, nome, descricao, status, modo, created_at, updated_at "
                "FROM analista_demandas ORDER BY updated_at DESC"
            ).fetchall()

        conversas = []
        for r in rows:
            msg_count = db.execute(
                "SELECT COUNT(*) FROM analista_mensagens WHERE demanda_id=?", (r[0],)
            ).fetchone()[0]
            art_count = db.execute(
                "SELECT COUNT(*) FROM analista_artefatos WHERE demanda_id=?", (r[0],)
            ).fetchone()[0]
            conversas.append({
                "id": r[0], "tipo": r[1], "nome": r[2], "descricao": r[3] or "",
                "status": r[4], "modo": r[5] or "melhoria",
                "created_at": r[6], "updated_at": r[7],
                "mensagens": msg_count, "artefatos": art_count,
            })
        return conversas
    finally:
        db.close()
```

- [ ] **Step 4: Add POST /conversas endpoint**

```python
@router.post("/conversas")
async def create_conversa(body: ConversaCreate):
    """Create a new conversation in the specified mode."""
    db = _get_db()
    try:
        _ensure_tables(db)
        modo = body.modo if body.modo in ("duvida", "melhoria", "ajuste") else "melhoria"
        nome = body.nome or f"Nova {modo.capitalize()}"
        db.execute(
            "INSERT INTO analista_demandas (tipo, nome, descricao, status, modo, confianca) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (modo, nome, body.descricao, "ativo", modo, 1.0),
        )
        db.commit()
        cid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        return {"id": cid, "nome": nome, "modo": modo, "status": "ativo"}
    finally:
        db.close()
```

- [ ] **Step 5: Add DELETE /conversas/{id} endpoint**

```python
@router.delete("/conversas/{conversa_id}")
async def delete_conversa(conversa_id: int):
    """Delete a conversation and its messages/artifacts."""
    db = _get_db()
    try:
        _ensure_tables(db)
        db.execute("DELETE FROM analista_mensagens WHERE demanda_id=?", (conversa_id,))
        db.execute("DELETE FROM analista_artefatos WHERE demanda_id=?", (conversa_id,))
        db.execute("DELETE FROM analista_demandas WHERE id=?", (conversa_id,))
        db.commit()
        return {"ok": True}
    finally:
        db.close()
```

- [ ] **Step 6: Add mode-aware chat endpoint**

Add a new `/conversas/{id}/chat` endpoint that selects the prompt based on `modo`:

```python
@router.post("/conversas/{conversa_id}/chat")
async def chat_conversa(conversa_id: int, body: ChatMessage):
    """SSE streaming chat for a conversation — uses mode-specific prompt."""
    from backend.routers.chat import _get_services
    from backend.services.analista_prompts import get_system_prompt
    from backend.services.analista_tools import (
        tool_analise_impacto, tool_buscar_pes,
        tool_buscar_fontes_tabela, tool_info_tabela,
        tool_buscar_parametros, tool_buscar_perguntas, tool_buscar_tabela_generica,
        tool_buscar_jobs, tool_buscar_schedules,
        tool_quem_grava_campo, tool_operacoes_tabela,
    )

    db_svc, vs, ks, llm, client_dir = _get_services()
    db = _get_db()

    try:
        _ensure_tables(db)

        # Get conversation and its mode
        row = db.execute(
            "SELECT id, modo, nome, descricao FROM analista_demandas WHERE id=?",
            (conversa_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Conversa não encontrada")

        conversa_id_val = row[0]
        modo = row[1] or "melhoria"

        # Save user message
        db.execute(
            "INSERT INTO analista_mensagens (demanda_id, projeto_id, role, content) VALUES (?, 0, 'user', ?)",
            (conversa_id_val, body.message),
        )
        db.commit()

        # Auto-set title from first message if still default
        if row[2] and row[2].startswith("Nova "):
            titulo = body.message[:80].replace("\n", " ")
            db.execute("UPDATE analista_demandas SET nome=? WHERE id=?", (titulo, conversa_id_val))
            db.commit()
    finally:
        db.close()

    # --- The SSE generator reuses existing investigation pipeline from chat_demanda ---
    # Copy the same event_generator pattern from chat_demanda but:
    # 1. Use get_system_prompt(modo) instead of SYSTEM_PROMPT
    # 2. For 'duvida' mode: skip artefact extraction (no ###ARTEFATOS### parsing)
    # 3. For 'ajuste' mode: prioritize operacoes_escrita in investigation
    # (Implementation: extract the existing event_generator from chat_demanda
    #  into a shared function _build_chat_generator(conversa_id, message, modo)
    #  that both endpoints can use)

    # For now, delegate to existing chat_demanda logic with modo-aware prompt
    # This will be refactored in a follow-up task
```

NOTE: The full SSE generator is complex (~200 lines). The implementation should extract the existing `event_generator` from `chat_demanda` into a shared helper `_build_chat_generator(conversa_id, message, modo, db_services)` that:
- Selects prompt via `get_system_prompt(modo)`
- For `duvida`: skips `###ARTEFATOS###` extraction
- For `ajuste`: adds `operacoes_escrita` queries in investigation phase
- For `melhoria`: keeps existing behavior (investigation + artefacts)

- [ ] **Step 7: Commit**

```bash
git add backend/routers/analista.py backend/services/analista_schema.py
git commit -m "feat: /conversas endpoints — CRUD + mode-aware chat"
```

---

## Chunk 3: Frontend — 3-section card layout

### Task 4: Redesign AnalistaView list mode

**Files:**
- Modify: `frontend/src/views/AnalistaView.vue`

- [ ] **Step 1: Replace list-view template**

Replace the existing `mode === 'list'` section (lines ~5-55) with:

```html
<div v-if="mode === 'list'" class="list-view">
  <div class="list-header">
    <h2>Peça ao Analista</h2>
    <div class="header-actions">
      <Button icon="pi pi-question-circle" label="Dúvida" severity="info" @click="criarConversa('duvida')" />
      <Button icon="pi pi-plus" label="Melhoria" severity="success" @click="criarConversa('melhoria')" />
      <Button icon="pi pi-wrench" label="Ajuste" severity="warn" @click="criarConversa('ajuste')" />
    </div>
  </div>

  <!-- Dúvidas -->
  <section class="card-section">
    <h3 class="section-title">
      <i class="pi pi-question-circle" style="color:#3b82f6"></i> Dúvidas
    </h3>
    <div class="cards-grid">
      <div v-for="c in conversasDuvida" :key="c.id" class="demanda-card card-duvida" @click="openConversa(c)">
        <div class="card-header">
          <strong>{{ c.nome || 'Sem título' }}</strong>
          <Tag value="Dúvida" severity="info" />
        </div>
        <p class="card-desc">{{ c.descricao || 'Sem descrição' }}</p>
        <div class="card-footer">
          <span><i class="pi pi-comments"></i> {{ c.mensagens }}</span>
          <span class="card-date">{{ formatDate(c.updated_at || c.created_at) }}</span>
        </div>
      </div>
      <div v-if="!conversasDuvida.length && !loading" class="empty-state">
        <p>Nenhuma dúvida registrada.</p>
      </div>
    </div>
  </section>

  <!-- Melhorias -->
  <section class="card-section">
    <h3 class="section-title">
      <i class="pi pi-plus-circle" style="color:#22c55e"></i> Melhorias
    </h3>
    <div class="cards-grid">
      <div v-for="c in conversasMelhoria" :key="c.id" class="demanda-card card-melhoria" @click="openConversa(c)">
        <div class="card-header">
          <strong>{{ c.nome || 'Sem título' }}</strong>
          <Tag value="Melhoria" severity="success" />
        </div>
        <p class="card-desc">{{ c.descricao || 'Sem descrição' }}</p>
        <div class="card-footer">
          <span><i class="pi pi-box"></i> {{ c.artefatos }}</span>
          <span class="card-date">{{ formatDate(c.updated_at || c.created_at) }}</span>
        </div>
      </div>
      <div v-if="!conversasMelhoria.length && !loading" class="empty-state">
        <p>Nenhuma melhoria registrada.</p>
      </div>
    </div>
  </section>

  <!-- Ajustes -->
  <section class="card-section">
    <h3 class="section-title">
      <i class="pi pi-wrench" style="color:#f59e0b"></i> Ajustes
    </h3>
    <div class="cards-grid">
      <div v-for="c in conversasAjuste" :key="c.id" class="demanda-card card-ajuste" @click="openConversa(c)">
        <div class="card-header">
          <strong>{{ c.nome || 'Sem título' }}</strong>
          <Tag value="Ajuste" severity="warn" />
        </div>
        <p class="card-desc">{{ c.descricao || 'Sem descrição' }}</p>
        <div class="card-footer">
          <span><i class="pi pi-comments"></i> {{ c.mensagens }}</span>
          <span class="card-date">{{ formatDate(c.updated_at || c.created_at) }}</span>
        </div>
      </div>
      <div v-if="!conversasAjuste.length && !loading" class="empty-state">
        <p>Nenhum ajuste registrado.</p>
      </div>
    </div>
  </section>

  <!-- Legado (collapsed) -->
  <section v-if="projetos.length" class="card-section" style="margin-top:2rem;">
    <h3 class="section-title" style="cursor:pointer;opacity:0.6" @click="showLegado = !showLegado">
      <i :class="showLegado ? 'pi pi-chevron-down' : 'pi pi-chevron-right'"></i> Legado ({{ projetos.length }})
    </h3>
    <div v-if="showLegado" class="cards-grid">
      <div v-for="p in projetos" :key="p.id" class="demanda-card legacy-card" @click="openLegacyProject(p)">
        <div class="card-header">
          <strong>{{ p.nome }}</strong>
          <Tag value="Legado" severity="secondary" />
        </div>
        <p class="card-desc">{{ p.descricao || 'Sem descrição' }}</p>
        <div class="card-footer">
          <span><i class="pi pi-comments"></i> {{ p.mensagens }}</span>
          <span><i class="pi pi-box"></i> {{ p.artefatos }}</span>
          <span class="card-date">{{ formatDate(p.updated_at) }}</span>
        </div>
      </div>
    </div>
  </section>
</div>
```

- [ ] **Step 2: Add computed properties and methods**

In the `<script setup>` section, add:

```javascript
// State
const conversas = ref([])
const showLegado = ref(false)

// Computed — filter conversas by mode
const conversasDuvida = computed(() => conversas.value.filter(c => c.modo === 'duvida'))
const conversasMelhoria = computed(() => conversas.value.filter(c => c.modo === 'melhoria'))
const conversasAjuste = computed(() => conversas.value.filter(c => c.modo === 'ajuste'))

// Load conversas
async function loadConversas() {
  loading.value = true
  try {
    const res = await fetch('/api/analista/conversas')
    conversas.value = await res.json()
  } catch (e) {
    console.error('Erro ao carregar conversas:', e)
  } finally {
    loading.value = false
  }
}

// Create new conversa
async function criarConversa(modo) {
  let nome = ''
  let descricao = ''

  if (modo === 'melhoria') {
    // Simple prompt for scope name
    nome = prompt('Nome da melhoria:') || ''
    if (!nome) return
    descricao = prompt('Descreva o escopo:') || ''
  } else if (modo === 'ajuste') {
    descricao = prompt('Descreva o problema:') || ''
    if (!descricao) return
    nome = descricao.slice(0, 80)
  }
  // duvida: no prompt needed, goes straight to chat

  try {
    const res = await fetch('/api/analista/conversas', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ modo, nome, descricao }),
    })
    const data = await res.json()
    // Open the new conversation
    openConversa({ ...data, modo })
  } catch (e) {
    console.error('Erro ao criar conversa:', e)
  }
}

// Open conversa — go to chat mode
function openConversa(conversa) {
  activeConversa.value = conversa
  mode.value = 'chat'
  loadMensagens(conversa.id)
  if (conversa.modo === 'melhoria') {
    loadArtefatos(conversa.id)
  }
}
```

- [ ] **Step 3: Update chat view to use /conversas/{id}/chat endpoint**

The existing chat panel can be reused with minimal changes:
- Use `/api/analista/conversas/${id}/chat` for SSE
- Use `/api/analista/conversas/${id}/mensagens` for history (reuse demanda endpoints initially)
- Show artefacts panel only for `modo === 'melhoria'`
- Show back button that returns to list and reloads

- [ ] **Step 4: Add card styles**

```css
.card-duvida { border-left: 3px solid #3b82f6; }
.card-melhoria { border-left: 3px solid #22c55e; }
.card-ajuste { border-left: 3px solid #f59e0b; }

.header-actions {
  display: flex;
  gap: 0.5rem;
}
```

- [ ] **Step 5: Update onMounted to load conversas**

```javascript
onMounted(() => {
  loadConversas()
  loadProjetos()  // keep for legado section
})
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/views/AnalistaView.vue
git commit -m "feat: UI 3 modos — cards por seção + chat mode-aware"
```

---

## Chunk 4: Integration and polish

### Task 5: Wire up the SSE chat generator

**Files:**
- Modify: `backend/routers/analista.py`

- [ ] **Step 1: Extract shared chat generator**

Extract the SSE `event_generator` logic from `chat_demanda` into a shared function:

```python
async def _chat_event_generator(conversa_id, message, modo, db_svc, vs, ks, llm):
    """Shared SSE generator for all chat modes."""
    from backend.services.analista_prompts import get_system_prompt
    # ... (move existing event_generator body here)
    # Key changes:
    # 1. system = get_system_prompt(modo).format(context=..., artefatos=..., tool_results=...)
    # 2. if modo == 'duvida': skip ###ARTEFATOS### parsing
    # 3. if modo == 'ajuste': add operacoes_escrita queries in investigation
```

- [ ] **Step 2: Update chat_conversa to use shared generator**

```python
@router.post("/conversas/{conversa_id}/chat")
async def chat_conversa(conversa_id: int, body: ChatMessage):
    # ... (setup code from Task 3 Step 6)
    async def event_generator():
        async for event in _chat_event_generator(
            conversa_id, body.message, modo, db_svc, vs, ks, llm
        ):
            yield event
    return EventSourceResponse(event_generator())
```

- [ ] **Step 3: Test all 3 modes manually**

1. Create a "Dúvida" → send message → verify response is consultive (no artefacts)
2. Create a "Melhoria" → send scope → verify artefacts are generated
3. Create an "Ajuste" → describe problem → verify investigation pipeline runs

- [ ] **Step 4: Commit**

```bash
git add backend/routers/analista.py
git commit -m "feat: shared chat generator — mode-aware SSE pipeline"
```

### Task 6: Final integration

- [ ] **Step 1: Verify backwards compatibility**

Ensure old endpoints still work:
- `GET /api/analista/demandas` — should still return existing demandas
- `GET /api/analista/projetos` — should still return existing projetos
- `POST /api/analista/demandas/{id}/chat` — should still work with old SYSTEM_PROMPT

- [ ] **Step 2: Build frontend**

```bash
cd frontend && npm run build
```

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "feat: Analista 3 modos — build final"
```
