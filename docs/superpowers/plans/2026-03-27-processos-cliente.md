# Processos do Cliente — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Criar página "Processos do Cliente" com DataTable + Dialog de detalhe com diagrama Mermaid gerado por LLM.

**Architecture:** Backend-first: migration da coluna `fluxo_mermaid`, endpoint de geração de diagrama via LLM, e atualização da query de listagem. Frontend: nova rota Vue, DataTable PrimeVue com filtros, Dialog com renderização Mermaid e navegação para o Analista.

**Tech Stack:** Python/FastAPI, SQLite, litellm (LLM), Vue 3 + PrimeVue 4 (Aura), mermaid.js, Axios

---

## Chunk 1: Backend

### Task 1: Adicionar coluna `fluxo_mermaid` ao banco de dados

**Files:**
- Modify: `backend/services/database.py:370-386` (SCHEMA), `backend/services/database.py:395-402` (initialize)

**Contexto:** A tabela `processos_detectados` está definida no SCHEMA (linha 370). Precisa ganhar a coluna `fluxo_mermaid` tanto para novos bancos (no SCHEMA) quanto para bancos existentes (migration via ALTER TABLE fora do guard `_initialized_dbs`).

- [ ] **Step 1: Adicionar a coluna ao SCHEMA**

No arquivo `backend/services/database.py`, localizar o bloco `CREATE TABLE IF NOT EXISTS processos_detectados` (linha 370). A linha `validado INTEGER DEFAULT 0,` está antes de `created_at`. Adicionar `fluxo_mermaid TEXT DEFAULT NULL,` após `validado`:

```python
# Trecho atual (linhas 378-383):
    score       REAL DEFAULT 0.0,
    validado    INTEGER DEFAULT 0,
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now'))
);

# Trecho após edição:
    score       REAL DEFAULT 0.0,
    validado    INTEGER DEFAULT 0,
    fluxo_mermaid TEXT DEFAULT NULL,
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now'))
);
```

- [ ] **Step 2: Adicionar migration para bancos existentes**

No método `initialize()` (linha 395), após o bloco `if key not in _initialized_dbs:` (que termina na linha 402), adicionar:

```python
    def initialize(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        key = str(self.db_path)
        if key not in _initialized_dbs:
            self._conn.executescript(SCHEMA)
            self._conn.commit()
            _initialized_dbs.add(key)
        # Migration idempotente — SQLite serializa writes, sem race condition
        try:
            self._conn.execute(
                "ALTER TABLE processos_detectados ADD COLUMN fluxo_mermaid TEXT DEFAULT NULL"
            )
            self._conn.commit()
        except Exception:
            pass  # coluna já existe
```

- [ ] **Step 3: Verificar manualmente**

```bash
cd d:/IA/Projetos/Protheus
python -c "
from pathlib import Path
from backend.services.database import Database
db = Database(Path('test_migration.db'))
db.initialize()
row = db.execute('PRAGMA table_info(processos_detectados)').fetchall()
cols = [r[1] for r in row]
print(cols)
assert 'fluxo_mermaid' in cols, 'COLUNA NAO ENCONTRADA'
print('OK — fluxo_mermaid presente')
db.close()
"
```

Expected: lista de colunas incluindo `fluxo_mermaid`, seguida de `OK — fluxo_mermaid presente`

- [ ] **Step 4: Limpar arquivo temporário e commitar**

```bash
rm test_migration.db
git add backend/services/database.py
git commit -m "feat: adiciona coluna fluxo_mermaid a processos_detectados"
```

---

### Task 2: Expor `fluxo_mermaid` no `tool_processos_cliente()`

**Files:**
- Modify: `backend/services/analista_tools.py:1513-1529`

**Contexto:** A função `tool_processos_cliente()` faz um SELECT que não inclui `fluxo_mermaid`. O `GET /analista/processos` usa essa função. Sem essa mudança, o frontend jamais vê o campo.

- [ ] **Step 1: Escrever o teste que falha**

No arquivo `tests/test_analista_tools_processos.py` (já existe), adicionar ao final:

```python
def test_tool_retorna_fluxo_mermaid(mock_db_com_processos):
    """tool_processos_cliente deve incluir fluxo_mermaid no dict retornado."""
    from unittest.mock import patch
    with patch("backend.services.analista_tools._get_db", return_value=mock_db_com_processos):
        result = tool_processos_cliente()
    assert "fluxo_mermaid" in result["processos"][0]
```

- [ ] **Step 2: Rodar o teste para confirmar que falha**

```bash
cd d:/IA/Projetos/Protheus
python -m pytest tests/test_analista_tools_processos.py::test_tool_retorna_fluxo_mermaid -v
```

Expected: FAILED — KeyError ou AssertionError

- [ ] **Step 3: Atualizar SELECT e dict em `tool_processos_cliente()`**

Em `backend/services/analista_tools.py`, atualizar linha 1513-1528:

```python
        rows = db.execute(
            "SELECT id, nome, tipo, descricao, criticidade, tabelas, score, fluxo_mermaid "
            "FROM processos_detectados ORDER BY score DESC"
        ).fetchall()

        processos = []
        for r in rows:
            tabs = _safe_json(r[5])
            if tabelas:
                tabs_upper = {t.upper() for t in tabs}
                filtro_upper = {t.upper() for t in tabelas}
                if not tabs_upper.intersection(filtro_upper):
                    continue
            processos.append({
                "id": r[0], "nome": r[1], "tipo": r[2], "descricao": r[3],
                "criticidade": r[4], "tabelas": tabs, "score": r[6],
                "fluxo_mermaid": r[7],
            })
```

- [ ] **Step 4: Rodar o teste para confirmar que passa**

```bash
python -m pytest tests/test_analista_tools_processos.py -v
```

Expected: todos PASSED

- [ ] **Step 5: Commitar**

```bash
git add backend/services/analista_tools.py tests/test_analista_tools_processos.py
git commit -m "feat: expoe fluxo_mermaid em tool_processos_cliente"
```

---

### Task 3: Criar `gerar_fluxo_processo()` e endpoint no analista

**Files:**
- Modify: `backend/routers/analista.py:372` (após `listar_processos_cliente`)
- Create: `tests/test_processos_fluxo.py`

**Contexto:** A função `gerar_fluxo_processo(db, llm, processo_id, force)` é síncrona e será testada diretamente. O endpoint `POST /processos/{id}/fluxo` a chama via `asyncio.to_thread`. O novo endpoint vai logo após `listar_processos_cliente` (linha 382) e antes do `@router.post("/conversas/{conversa_id}/chat")` (linha 385).

- [ ] **Step 1: Escrever os testes que falham**

Criar arquivo `tests/test_processos_fluxo.py`:

```python
# tests/test_processos_fluxo.py
import pytest
from unittest.mock import MagicMock
from backend.services.database import Database


@pytest.fixture
def db_com_processo(tmp_path):
    db = Database(tmp_path / "test.db")
    db.initialize()  # SCHEMA + migration fluxo_mermaid
    db.execute(
        "INSERT INTO processos_detectados (nome, tipo, descricao, criticidade, tabelas, score) "
        "VALUES (?,?,?,?,?,?)",
        ("Integração Taura WMS", "integracao", "Pedidos ao Taura", "alta", '["SC5","ZZE"]', 0.92),
    )
    db.commit()
    return db


@pytest.fixture
def mock_llm():
    llm = MagicMock()
    llm.chat.return_value = "flowchart TD\nA-->B"
    return llm


def test_fluxo_gera_e_salva(db_com_processo, mock_llm):
    from backend.routers.analista import gerar_fluxo_processo
    result = gerar_fluxo_processo(db_com_processo, mock_llm, 1, False)
    assert result is not None
    assert "flowchart" in result
    saved = db_com_processo.execute(
        "SELECT fluxo_mermaid FROM processos_detectados WHERE id=1"
    ).fetchone()[0]
    assert saved is not None
    assert "flowchart" in saved


def test_fluxo_retorna_cache(db_com_processo, mock_llm):
    from backend.routers.analista import gerar_fluxo_processo
    db_com_processo.execute(
        "UPDATE processos_detectados SET fluxo_mermaid=? WHERE id=1",
        ("flowchart TD\nX-->Y",),
    )
    db_com_processo.commit()
    result = gerar_fluxo_processo(db_com_processo, mock_llm, 1, False)
    assert mock_llm.chat.call_count == 0
    assert result == "flowchart TD\nX-->Y"


def test_fluxo_force_regenera(db_com_processo, mock_llm):
    from backend.routers.analista import gerar_fluxo_processo
    db_com_processo.execute(
        "UPDATE processos_detectados SET fluxo_mermaid=? WHERE id=1",
        ("flowchart TD\nX-->Y",),
    )
    db_com_processo.commit()
    result = gerar_fluxo_processo(db_com_processo, mock_llm, 1, True)
    assert mock_llm.chat.call_count == 1
    assert "flowchart" in result


def test_fluxo_processo_nao_encontrado(db_com_processo, mock_llm):
    from backend.routers.analista import gerar_fluxo_processo
    result = gerar_fluxo_processo(db_com_processo, mock_llm, 9999, False)
    assert result is None
```

- [ ] **Step 2: Rodar os testes para confirmar que falham**

```bash
python -m pytest tests/test_processos_fluxo.py -v
```

Expected: FAILED — ImportError (`cannot import name 'gerar_fluxo_processo'`)

- [ ] **Step 3: Implementar `gerar_fluxo_processo()` e o endpoint em `analista.py`**

No arquivo `backend/routers/analista.py`, adicionar após a função `listar_processos_cliente` (linha 382), antes do comentário/decorator `@router.post("/conversas/{conversa_id}/chat")`:

```python
def gerar_fluxo_processo(db, llm, processo_id: int, force: bool) -> str | None:
    """Sync function: generates Mermaid diagram for a process via LLM and caches it."""
    import re

    row = db.execute(
        "SELECT id, nome, tipo, descricao, criticidade, tabelas, score, fluxo_mermaid "
        "FROM processos_detectados WHERE id = ?",
        (processo_id,),
    ).fetchone()

    if row is None:
        return None

    # row[7] = fluxo_mermaid
    if row[7] is not None and not force:
        return row[7]

    prompt = (
        f'Gere um diagrama Mermaid `flowchart TD` para o processo "{row[1]}" do tipo "{row[2]}".\n'
        f"Descrição: {row[3]}\n"
        f"Tabelas envolvidas: {row[5]}\n"
        f"Criticidade: {row[4]}\n"
        f"Represente as etapas principais do processo de forma clara. "
        f"Retorne APENAS o código Mermaid, sem explicações."
    )
    messages = [{"role": "user", "content": prompt}]
    text = llm.chat(messages)

    # Extract Mermaid code
    match = re.search(r"```(?:mermaid)?\s*([\s\S]*?)```", text)
    if match:
        mermaid_str = match.group(1).strip()
    elif text.strip().startswith(("flowchart", "graph")):
        mermaid_str = text.strip()
    else:
        raise ValueError("Resposta do LLM não é um diagrama Mermaid válido")

    db.execute(
        "UPDATE processos_detectados SET fluxo_mermaid = ? WHERE id = ?",
        (mermaid_str, processo_id),
    )
    db.commit()
    return mermaid_str


@router.post("/processos/{processo_id}/fluxo")
async def gerar_fluxo_processo_endpoint(processo_id: int, force: bool = False):
    """Generate (or return cached) Mermaid flow diagram for a detected process."""
    import asyncio
    from backend.routers.chat import _get_services

    db = _get_db()
    try:
        db_svc, vs, ks, llm, client_dir = _get_services()
    except Exception as e:
        raise HTTPException(500, f"Erro ao iniciar serviços: {str(e)[:200]}")

    try:
        result = await asyncio.to_thread(gerar_fluxo_processo, db, llm, processo_id, force)
    except ValueError as e:
        raise HTTPException(500, f"Erro ao gerar fluxo: {str(e)}")
    except Exception as e:
        raise HTTPException(500, f"Erro ao gerar fluxo: {str(e)[:300]}")
    finally:
        db.close()

    if result is None:
        raise HTTPException(404, "Processo não encontrado")

    return {"fluxo_mermaid": result}
```

- [ ] **Step 4: Rodar os testes para confirmar que passam**

```bash
python -m pytest tests/test_processos_fluxo.py -v
```

Expected: 4 testes PASSED

- [ ] **Step 5: Rodar suite completa de testes para garantir sem regressão**

```bash
python -m pytest tests/ -v --tb=short
```

Expected: todos PASSED (ou apenas os pré-existentes que já falhavam antes)

- [ ] **Step 6: Commitar**

```bash
git add backend/routers/analista.py tests/test_processos_fluxo.py
git commit -m "feat: endpoint POST /processos/{id}/fluxo + gerar_fluxo_processo()"
```

---

## Chunk 2: Frontend

### Task 4: Exportar `ensureInit` e adicionar rota `/processos`

**Files:**
- Modify: `frontend/src/composables/useMermaid.js:5`
- Modify: `frontend/src/router.js:13`

**Contexto:** `ensureInit` existe mas não é exportada. `ProcessoDialog.vue` vai precisar dela. A rota nova usa `meta.label` para aparecer automaticamente no sidebar.

- [ ] **Step 1: Exportar `ensureInit` em `useMermaid.js`**

Em `frontend/src/composables/useMermaid.js`, linha 5, alterar:

```js
// antes:
function ensureInit() {

// depois:
export function ensureInit() {
```

Os callers internos (ex: `renderMermaidBlocks`) continuam funcionando — eles chamam `ensureInit()` diretamente dentro do mesmo arquivo.

- [ ] **Step 2: Adicionar rota `/processos` em `router.js`**

Em `frontend/src/router.js`:

1. Adicionar import após linha 7:
```js
import ProcessosView from './views/ProcessosCliente.vue'
```

2. Adicionar rota após linha 13 (após `/analista`):
```js
  { path: '/processos', component: ProcessosView, meta: { label: 'Processos', icon: 'pi pi-list' } },
```

O arquivo final ficará:
```js
import { createRouter, createWebHistory } from 'vue-router'
import DashboardView from './views/DashboardView.vue'
import SetupView from './views/SetupView.vue'
import PadraoView from './views/PadraoView.vue'
import ExplorerView from './views/ExplorerView.vue'
import ConfigView from './views/ConfigView.vue'
import AnalistaView from './views/AnalistaView.vue'
import ProcessosView from './views/ProcessosCliente.vue'

const routes = [
  { path: '/', redirect: '/setup' },
  { path: '/setup', component: SetupView, meta: { label: 'Setup', icon: 'pi pi-cog' } },
  { path: '/dashboard', component: DashboardView, meta: { label: 'Dashboard', icon: 'pi pi-chart-bar' } },
  { path: '/analista', component: AnalistaView, meta: { label: 'Peça ao Analista', icon: 'pi pi-user' } },
  { path: '/processos', component: ProcessosView, meta: { label: 'Processos', icon: 'pi pi-list' } },
  { path: '/padrao', component: PadraoView, meta: { label: 'Base Padrão', icon: 'pi pi-book' } },
  { path: '/explorer', component: ExplorerView, meta: { label: 'Explorer', icon: 'pi pi-sitemap' } },
  { path: '/config', component: ConfigView, meta: { label: 'Configurações', icon: 'pi pi-sliders-h' } },
]

export default createRouter({ history: createWebHistory(), routes })
```

**Nota:** O arquivo `ProcessosCliente.vue` ainda não existe — o servidor de dev vai mostrar erro de import. Isso é esperado e será resolvido na próxima task.

- [ ] **Step 3: Commitar**

```bash
git add frontend/src/composables/useMermaid.js frontend/src/router.js
git commit -m "feat: exporta ensureInit e adiciona rota /processos"
```

---

### Task 5: Criar `ProcessosCliente.vue`

**Files:**
- Create: `frontend/src/views/ProcessosCliente.vue`

**Contexto:** Página principal. Busca `GET /analista/processos` ao montar, mostra DataTable PrimeVue com filtros de tipo/criticidade e botão "Redescobrir". Click na linha abre `ProcessoDialog`. Os filtros são feitos no frontend (client-side filtering sobre os dados já carregados).

**Cores dos badges de tipo:** workflow=#9c27b0, integracao=#0277bd, logistica=#e65100, fiscal=#1b5e20, automacao=#1b5e20, regulatorio=#37474f, auditoria=#4e342e, qualidade=#00695c — demais tipos: #607d8b

- [ ] **Step 1: Criar o componente**

Criar `frontend/src/views/ProcessosCliente.vue`:

```vue
<template>
  <div class="processos-container">
    <div class="processos-header">
      <div class="header-left">
        <h2>Processos do Cliente</h2>
        <span class="total-badge" v-if="processos.length">{{ processos.length }} processos</span>
      </div>
      <div class="header-filters">
        <select v-model="filtroTipo" class="filtro-select">
          <option value="">Todos os tipos</option>
          <option v-for="t in tiposDisponiveis" :key="t" :value="t">{{ t }}</option>
        </select>
        <select v-model="filtroCriticidade" class="filtro-select">
          <option value="">Toda criticidade</option>
          <option value="alta">alta</option>
          <option value="media">media</option>
          <option value="baixa">baixa</option>
        </select>
        <Button
          label="Redescobrir"
          icon="pi pi-refresh"
          :loading="redescobrir_loading"
          @click="redescobrir"
          size="small"
          severity="secondary"
        />
      </div>
    </div>

    <div v-if="loading" class="loading-msg">Carregando processos...</div>

    <div v-else-if="processosFiltrados.length === 0" class="empty-msg">
      Nenhum processo descoberto. Clique em <strong>Redescobrir</strong> para analisar o cliente.
    </div>

    <DataTable
      v-else
      :value="processosFiltrados"
      :rows="20"
      :paginator="processosFiltrados.length > 20"
      stripedRows
      @row-click="abrirDialog"
      class="processos-table"
      rowHover
    >
      <Column field="nome" header="Nome" style="min-width:200px">
        <template #body="{ data }">
          <span class="nome-link">{{ data.nome }}</span>
        </template>
      </Column>

      <Column field="tipo" header="Tipo" style="width:130px">
        <template #body="{ data }">
          <span class="tipo-badge" :style="{ background: corTipo(data.tipo) }">{{ data.tipo }}</span>
        </template>
      </Column>

      <Column field="criticidade" header="Criticidade" style="width:110px">
        <template #body="{ data }">
          <span class="crit-badge" :class="`crit-${data.criticidade}`">{{ data.criticidade }}</span>
        </template>
      </Column>

      <Column field="score" header="Score" style="width:80px">
        <template #body="{ data }">
          <span :class="scoreClass(data.score)">{{ data.score.toFixed(2) }}</span>
        </template>
      </Column>

      <Column field="tabelas" header="Tabelas" style="min-width:150px">
        <template #body="{ data }">
          <span v-for="t in data.tabelas.slice(0, 3)" :key="t" class="tabela-chip">{{ t }}</span>
          <span v-if="data.tabelas.length > 3" class="tabela-chip tabela-mais">+{{ data.tabelas.length - 3 }}</span>
        </template>
      </Column>
    </DataTable>

    <ProcessoDialog
      v-if="processoSelecionado"
      :processo="processoSelecionado"
      @close="processoSelecionado = null"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useToast } from 'primevue/usetoast'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Button from 'primevue/button'
import axios from 'axios'
import ProcessoDialog from '../components/ProcessoDialog.vue'

const toast = useToast()
const processos = ref([])
const loading = ref(true)
const redescobrir_loading = ref(false)
const filtroTipo = ref('')
const filtroCriticidade = ref('')
const processoSelecionado = ref(null)

const tiposDisponiveis = computed(() => {
  const tipos = new Set(processos.value.map(p => p.tipo))
  return [...tipos].sort()
})

const processosFiltrados = computed(() => {
  return processos.value.filter(p => {
    if (filtroTipo.value && p.tipo !== filtroTipo.value) return false
    if (filtroCriticidade.value && p.criticidade !== filtroCriticidade.value) return false
    return true
  })
})

const TIPO_CORES = {
  workflow: '#9c27b0',
  integracao: '#0277bd',
  logistica: '#e65100',
  fiscal: '#1b5e20',
  automacao: '#1b5e20',
  regulatorio: '#37474f',
  auditoria: '#4e342e',
  qualidade: '#00695c',
}

function corTipo(tipo) {
  return TIPO_CORES[tipo] || '#607d8b'
}

function scoreClass(score) {
  if (score >= 0.85) return 'score score-alto'
  if (score >= 0.7) return 'score score-medio'
  return 'score score-baixo'
}

async function carregarProcessos() {
  loading.value = true
  try {
    const res = await axios.get('/api/analista/processos')
    processos.value = res.data.processos || []
  } catch {
    toast.add({ severity: 'error', summary: 'Erro ao carregar processos', life: 3000 })
  } finally {
    loading.value = false
  }
}

async function redescobrir() {
  redescobrir_loading.value = true
  try {
    await axios.post('/api/analista/processos/descobrir', null, { timeout: 120000 })
    await carregarProcessos()
    toast.add({ severity: 'success', summary: 'Processos atualizados', life: 3000 })
  } catch {
    toast.add({ severity: 'error', summary: 'Erro ao redescobrir processos. Tente novamente.', life: 4000 })
  } finally {
    redescobrir_loading.value = false
  }
}

function abrirDialog(event) {
  processoSelecionado.value = event.data
}

onMounted(carregarProcessos)
</script>

<style scoped>
.processos-container { padding: 1.5rem; height: calc(100vh - 4rem); display: flex; flex-direction: column; gap: 1rem; overflow: hidden; }
.processos-header { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.5rem; }
.header-left { display: flex; align-items: center; gap: 0.75rem; }
.header-left h2 { margin: 0; color: #333; }
.total-badge { background: #00a1e0; color: #fff; border-radius: 12px; padding: 2px 10px; font-size: 0.8rem; font-weight: 600; }
.header-filters { display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; }
.filtro-select { border: 1px solid #d0d0d0; border-radius: 6px; padding: 0.35rem 0.5rem; font-size: 0.85rem; background: #fff; cursor: pointer; }
.processos-table { flex: 1; overflow-y: auto; }
.nome-link { color: #00a1e0; cursor: pointer; font-weight: 500; }
.tipo-badge { color: #fff; border-radius: 4px; padding: 2px 8px; font-size: 0.75rem; font-weight: 600; }
.crit-badge { border-radius: 4px; padding: 2px 8px; font-size: 0.75rem; font-weight: 600; color: #fff; }
.crit-alta { background: #b71c1c; }
.crit-media { background: #e65100; }
.crit-baixa { background: #888; }
.score { font-weight: 700; font-size: 0.9rem; }
.score-alto { color: #2e7d32; }
.score-medio { color: #f57f17; }
.score-baixo { color: #888; }
.tabela-chip { background: #e3f2fd; color: #1565c0; border-radius: 4px; padding: 1px 6px; font-size: 0.75rem; margin-right: 3px; display: inline-block; }
.tabela-mais { background: #eeeeee; color: #555; }
.loading-msg, .empty-msg { color: #666; padding: 2rem; text-align: center; }
</style>
```

- [ ] **Step 2: Verificar que o frontend compila sem erros**

```bash
cd d:/IA/Projetos/Protheus/frontend
npm run build 2>&1 | tail -20
```

Expected: build completo sem erros (warnings de unused vars são aceitáveis)

- [ ] **Step 3: Commitar**

```bash
git add frontend/src/views/ProcessosCliente.vue
git commit -m "feat: ProcessosCliente.vue — DataTable com filtros e redescobrir"
```

---

### Task 6: Criar `ProcessoDialog.vue`

**Files:**
- Create: `frontend/src/components/ProcessoDialog.vue`

**Contexto:** Dialog de detalhe. Recebe o objeto `processo` como prop. Renderiza Mermaid se `fluxo_mermaid` não null. Botões: "Gerar fluxo", "Regenerar", "Perguntar ao Analista", "Fechar". A renderização Mermaid usa `ensureInit()` de `useMermaid.js`.

- [ ] **Step 1: Criar o componente**

Criar `frontend/src/components/ProcessoDialog.vue`:

```vue
<template>
  <Dialog
    :visible="true"
    :header="processo.nome"
    :modal="true"
    :style="{ width: '780px', maxWidth: '95vw' }"
    @hide="$emit('close')"
  >
    <!-- Seção: Informações -->
    <div class="info-grid">
      <div class="info-item">
        <label>Tipo</label>
        <span class="tipo-badge" :style="{ background: corTipo(processo.tipo) }">{{ processo.tipo }}</span>
      </div>
      <div class="info-item">
        <label>Criticidade</label>
        <span class="crit-badge" :class="`crit-${processo.criticidade}`">{{ processo.criticidade }}</span>
      </div>
      <div class="info-item">
        <label>Score</label>
        <span :class="scoreClass(processo.score)" class="score">{{ processo.score.toFixed(2) }}</span>
      </div>
    </div>

    <div class="descricao-section">
      <label>Descrição</label>
      <p>{{ processo.descricao || 'Sem descrição disponível.' }}</p>
    </div>

    <div class="tabelas-section">
      <label>Tabelas envolvidas</label>
      <div class="tabelas-chips">
        <span v-for="t in processo.tabelas" :key="t" class="tabela-chip">{{ t }}</span>
      </div>
    </div>

    <!-- Seção: Fluxo Mermaid -->
    <div class="fluxo-section">
      <div class="fluxo-header">
        <label>Fluxo do Processo</label>
        <div class="fluxo-actions">
          <Button
            v-if="!fluxoAtual && !gerando"
            label="Gerar fluxo"
            icon="pi pi-play"
            size="small"
            @click="gerarFluxo(false)"
          />
          <Button
            v-if="fluxoAtual"
            label="Regenerar"
            icon="pi pi-refresh"
            size="small"
            severity="secondary"
            :loading="gerando"
            @click="gerarFluxo(true)"
          />
        </div>
      </div>

      <!-- Loading skeleton -->
      <div v-if="gerando" class="fluxo-skeleton">
        <div class="skeleton-line" v-for="i in 5" :key="i" :style="{ width: `${60 + i * 8}%` }"></div>
      </div>

      <!-- Diagrama Mermaid -->
      <div v-else-if="fluxoAtual && !fluxoErro" ref="mermaidContainer" class="mermaid-container"></div>

      <!-- Fallback -->
      <div v-else-if="fluxoErro" class="fluxo-fallback">
        <p class="fallback-aviso">⚠ Diagrama indisponível</p>
        <p>{{ processo.descricao }}</p>
      </div>

      <!-- Estado vazio -->
      <div v-else-if="!fluxoAtual && !gerando" class="fluxo-vazio">
        Clique em <strong>Gerar fluxo</strong> para criar o diagrama deste processo.
      </div>
    </div>

    <template #footer>
      <Button label="Perguntar ao Analista" icon="pi pi-comments" @click="irParaAnalista" severity="info" />
      <Button label="Fechar" icon="pi pi-times" @click="$emit('close')" severity="secondary" />
    </template>
  </Dialog>
</template>

<script setup>
import { ref, onMounted, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { useToast } from 'primevue/usetoast'
import Dialog from 'primevue/dialog'
import Button from 'primevue/button'
import axios from 'axios'
import mermaid from 'mermaid'
import { ensureInit } from '../composables/useMermaid.js'

const props = defineProps({
  processo: { type: Object, required: true }
})
const emit = defineEmits(['close'])

const router = useRouter()
const toast = useToast()

const fluxoAtual = ref(props.processo.fluxo_mermaid || null)
const gerando = ref(false)
const fluxoErro = ref(false)
const mermaidContainer = ref(null)

async function renderMermaid(code) {
  await nextTick()
  if (!mermaidContainer.value) return
  const id = `mermaid-${Math.random().toString(36).slice(2, 10)}`
  ensureInit()
  try {
    const { svg } = await mermaid.render(id, code)
    mermaidContainer.value.innerHTML = svg
    fluxoErro.value = false
  } catch (err) {
    document.getElementById(id)?.remove()
    document.querySelectorAll('.mermaid-error, [id^="dmermaid-"]').forEach(el => el.remove())
    fluxoErro.value = true
  }
}

async function gerarFluxo(force) {
  gerando.value = true
  fluxoErro.value = false
  try {
    const url = `/api/analista/processos/${props.processo.id}/fluxo${force ? '?force=true' : ''}`
    const res = await axios.post(url)
    fluxoAtual.value = res.data.fluxo_mermaid
    await renderMermaid(fluxoAtual.value)
  } catch {
    toast.add({ severity: 'error', summary: 'Erro ao gerar fluxo. Tente novamente.', life: 4000 })
    fluxoErro.value = true
  } finally {
    gerando.value = false
  }
}

function irParaAnalista() {
  router.push({ path: '/analista', query: { processo: props.processo.nome } })
  emit('close')
}

// Cores (mesmo mapeamento de ProcessosCliente.vue)
const TIPO_CORES = {
  workflow: '#9c27b0', integracao: '#0277bd', logistica: '#e65100',
  fiscal: '#1b5e20', automacao: '#1b5e20', regulatorio: '#37474f',
  auditoria: '#4e342e', qualidade: '#00695c',
}
function corTipo(tipo) { return TIPO_CORES[tipo] || '#607d8b' }
function scoreClass(score) {
  if (score >= 0.85) return 'score-alto'
  if (score >= 0.7) return 'score-medio'
  return 'score-baixo'
}

onMounted(async () => {
  if (fluxoAtual.value) {
    await renderMermaid(fluxoAtual.value)
  }
})
</script>

<style scoped>
.info-grid { display: flex; gap: 1.5rem; margin-bottom: 1rem; flex-wrap: wrap; }
.info-item { display: flex; flex-direction: column; gap: 4px; }
.info-item label { font-size: 0.75rem; color: #888; text-transform: uppercase; font-weight: 600; }
.tipo-badge { color: #fff; border-radius: 4px; padding: 3px 10px; font-size: 0.8rem; font-weight: 600; display: inline-block; }
.crit-badge { border-radius: 4px; padding: 3px 10px; font-size: 0.8rem; font-weight: 600; color: #fff; display: inline-block; }
.crit-alta { background: #b71c1c; }
.crit-media { background: #e65100; }
.crit-baixa { background: #888; }
.score { font-weight: 700; }
.score-alto { color: #2e7d32; }
.score-medio { color: #f57f17; }
.score-baixo { color: #888; }
.descricao-section, .tabelas-section, .fluxo-section { margin-bottom: 1.25rem; }
.descricao-section label, .tabelas-section label, .fluxo-section label { font-size: 0.75rem; color: #888; text-transform: uppercase; font-weight: 600; display: block; margin-bottom: 6px; }
.tabelas-chips { display: flex; flex-wrap: wrap; gap: 5px; }
.tabela-chip { background: #e3f2fd; color: #1565c0; border-radius: 4px; padding: 2px 8px; font-size: 0.8rem; }
.fluxo-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem; }
.fluxo-header label { margin-bottom: 0; }
.fluxo-actions { display: flex; gap: 0.5rem; }
.mermaid-container { background: #f8f9fa; border-radius: 8px; padding: 1rem; overflow-x: auto; min-height: 120px; }
.mermaid-container :deep(svg) { max-width: 100%; }
.fluxo-skeleton { display: flex; flex-direction: column; gap: 8px; padding: 1rem; background: #f8f9fa; border-radius: 8px; }
.skeleton-line { height: 14px; background: linear-gradient(90deg, #e0e0e0 25%, #f0f0f0 50%, #e0e0e0 75%); border-radius: 4px; animation: shimmer 1.5s infinite; }
@keyframes shimmer { 0% { background-position: -200px 0; } 100% { background-position: 200px 0; } }
.fluxo-fallback { background: #fff3e0; border-radius: 8px; padding: 1rem; color: #666; }
.fallback-aviso { color: #e65100; font-weight: 600; margin-bottom: 0.5rem; }
.fluxo-vazio { color: #aaa; font-style: italic; padding: 1rem 0; }
</style>
```

- [ ] **Step 2: Verificar que o frontend compila sem erros**

```bash
cd d:/IA/Projetos/Protheus/frontend
npm run build 2>&1 | tail -20
```

Expected: build completo sem erros

- [ ] **Step 3: Commitar**

```bash
git add frontend/src/components/ProcessoDialog.vue
git commit -m "feat: ProcessoDialog.vue — detalhe + Mermaid + Perguntar ao Analista"
```

---

### Task 7: Pré-preencher `AnalistaView.vue` com query param `?processo`

**Files:**
- Modify: `frontend/src/views/AnalistaView.vue:677` (imports), `frontend/src/views/AnalistaView.vue:1576` (onMounted)

**Contexto:** Quando o usuário clica "Perguntar ao Analista" no `ProcessoDialog`, navega para `/analista?processo=<nome>`. O `AnalistaView` precisa ler esse param e pré-preencher `userMessage` (o `ref('')` da linha 800).

- [ ] **Step 1: Adicionar import de `useRoute`**

Em `frontend/src/views/AnalistaView.vue`, linha 677, o import atual é:
```js
import { ref, computed, nextTick, onMounted, watch } from 'vue'
```

Adicionar abaixo (nova linha após linha 677):
```js
import { useRoute } from 'vue-router'
```

- [ ] **Step 2: Adicionar leitura do query param no `onMounted`**

O `onMounted` atual (linha 1576) é:
```js
onMounted(() => {
  loadConversas()
  loadProjetos()
  loadAll()
})
```

Alterar para:
```js
onMounted(() => {
  loadConversas()
  loadProjetos()
  loadAll()
  const route = useRoute()
  if (route.query.processo) {
    userMessage.value = `Me explique o processo: ${route.query.processo}`
  }
})
```

- [ ] **Step 3: Verificar que o frontend compila sem erros**

```bash
cd d:/IA/Projetos/Protheus/frontend
npm run build 2>&1 | tail -20
```

Expected: build completo sem erros

- [ ] **Step 4: Commitar**

```bash
git add frontend/src/views/AnalistaView.vue
git commit -m "feat: AnalistaView pre-preenche userMessage via query param ?processo"
```

---

## Verificação final

- [ ] **Rodar todos os testes backend**

```bash
cd d:/IA/Projetos/Protheus
python -m pytest tests/ -v --tb=short
```

Expected: todos PASSED

- [ ] **Testar manualmente o fluxo completo**

1. Iniciar o servidor: `python -m uvicorn backend.main:app --reload`
2. Iniciar o frontend: `cd frontend && npm run dev`
3. Navegar para `http://localhost:5173/processos`
4. Verificar que a sidebar mostra "Processos" com ícone pi-list
5. Verificar DataTable com filtros funcionando
6. Clicar num processo → Dialog abre com informações
7. Clicar "Gerar fluxo" → diagrama Mermaid aparece após ~10s
8. Fechar e reabrir o mesmo processo → diagrama já aparece (cache)
9. Clicar "Perguntar ao Analista" → navega para /analista com texto pré-preenchido

- [ ] **Commitar qualquer ajuste final**

```bash
git add -A
git commit -m "feat: Processos do Cliente — page complete"
```
