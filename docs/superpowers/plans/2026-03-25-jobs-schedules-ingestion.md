# Jobs & Schedules Ingestion — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ingest Job and Schedule CSVs into SQLite, link rotinas to fontes via vinculos, and show in Explorer.

**Architecture:** New tables `jobs` and `schedules` in database.py, new parsers `parse_jobs()` and `parse_schedules()` in parser_sx.py, vinculo generation in build_vinculos.py, and two new Explorer endpoints + tree nodes.

**Tech Stack:** Python, SQLite, FastAPI, Vue.js (PrimeVue Tree)

---

## Chunk 1: Database Schema + Parsers

### Task 1: Add jobs and schedules tables to schema

**Files:**
- Modify: `backend/services/database.py:322` (before closing `"""` of SCHEMA)

- [ ] **Step 1: Add the two CREATE TABLE statements to SCHEMA**

Add before the closing `"""` in the SCHEMA string (line 323):

```sql
CREATE TABLE IF NOT EXISTS jobs (
    arquivo_ini  TEXT,
    sessao       TEXT,
    rotina       TEXT,
    refresh_rate INTEGER,
    parametros   TEXT DEFAULT '',
    PRIMARY KEY (arquivo_ini, sessao)
);
CREATE INDEX IF NOT EXISTS idx_jobs_rotina ON jobs(rotina);

CREATE TABLE IF NOT EXISTS schedules (
    codigo              TEXT,
    rotina              TEXT,
    empresa_filial      TEXT,
    environment         TEXT DEFAULT '',
    modulo              INTEGER DEFAULT 0,
    status              TEXT DEFAULT '',
    tipo_recorrencia    TEXT DEFAULT '',
    detalhe_recorrencia TEXT DEFAULT '',
    execucoes_dia       INTEGER,
    intervalo           TEXT DEFAULT '',
    hora_inicio         TEXT DEFAULT '',
    data_criacao        TEXT DEFAULT '',
    ultima_execucao     TEXT DEFAULT '',
    ultima_hora         TEXT DEFAULT '',
    recorrencia_raw     TEXT DEFAULT '',
    PRIMARY KEY (codigo, empresa_filial)
);
CREATE INDEX IF NOT EXISTS idx_schedules_rotina ON schedules(rotina);
CREATE INDEX IF NOT EXISTS idx_schedules_status ON schedules(status);
```

- [ ] **Step 2: Commit**

```bash
git add backend/services/database.py
git commit -m "feat: add jobs and schedules tables to database schema"
```

---

### Task 2: Add parse_jobs() parser

**Files:**
- Modify: `backend/services/parser_sx.py` (add function after existing parsers, before `parse_mpmenu`)

- [ ] **Step 1: Add parse_jobs function**

Add before `parse_mpmenu` in parser_sx.py:

```python
def parse_jobs(file_path: Path) -> List[dict]:
    """Parse job_detalhado_bash.csv — AppServer job sessions."""
    rows = _read_csv(file_path)
    result = []
    for row in rows:
        arquivo = row.get("Arquivo", "").strip()
        sessao = row.get("Sessao", "").strip()
        if not arquivo or not sessao:
            continue
        rate_raw = row.get("RefreshRate", "").strip()
        try:
            refresh_rate = int(rate_raw) if rate_raw and rate_raw != "N/A" else None
        except ValueError:
            refresh_rate = None
        result.append({
            "arquivo_ini": arquivo,
            "sessao": sessao,
            "rotina": row.get("Rotina_Main", "").strip(),
            "refresh_rate": refresh_rate,
            "parametros": row.get("Parametros", "").strip(),
        })
    return result
```

- [ ] **Step 2: Commit**

```bash
git add backend/services/parser_sx.py
git commit -m "feat: add parse_jobs parser for AppServer job CSVs"
```

---

### Task 3: Add parse_schedules() parser

**Files:**
- Modify: `backend/services/parser_sx.py` (add after parse_jobs)

- [ ] **Step 1: Add parse_schedules function**

```python
def _extract_function_name(rotina_raw: str) -> str:
    """Extract clean function name from schedule rotina field.

    Examples:
        "U_MGFWSC28('','01','010041')" -> "U_MGFWSC28"
        "U_MGFFINCB()"                 -> "U_MGFFINCB"
        "AUTONFEMON"                   -> "AUTONFEMON"
        "U_XGLPPTSCHED(1,1)"          -> "U_XGLPPTSCHED"
        "FINA435"                      -> "FINA435"
    """
    import re
    m = re.match(r'^([A-Za-z_]\w+)', rotina_raw.strip())
    return m.group(1) if m else rotina_raw.strip()


def parse_schedules(file_path: Path) -> List[dict]:
    """Parse schedule_decodificado.csv — Protheus scheduled tasks."""
    rows = _read_csv(file_path)
    result = []
    for row in rows:
        codigo = row.get("Codigo", "").strip()
        empresa = row.get("Empresa_Filial", "").strip()
        if not codigo:
            continue
        rotina_raw = row.get("Rotina", "").strip()
        rotina = _extract_function_name(rotina_raw)
        exec_raw = row.get("Execucoes_Dia", "").strip()
        try:
            execucoes = int(exec_raw) if exec_raw and exec_raw != "N/A" else None
        except ValueError:
            execucoes = None
        mod_raw = row.get("Modulo", "").strip()
        try:
            modulo = int(mod_raw) if mod_raw else 0
        except ValueError:
            modulo = 0
        result.append({
            "codigo": codigo,
            "rotina": rotina,
            "empresa_filial": empresa,
            "environment": row.get("Environment", "").strip(),
            "modulo": modulo,
            "status": row.get("Status", "").strip(),
            "tipo_recorrencia": row.get("Tipo_Recorrencia", "").strip(),
            "detalhe_recorrencia": row.get("Detalhe_Recorrencia", "").strip(),
            "execucoes_dia": execucoes,
            "intervalo": row.get("Intervalo_HH_MM", "").strip(),
            "hora_inicio": row.get("Hora_Inicio", "").strip(),
            "data_criacao": row.get("Data_Criacao", "").strip(),
            "ultima_execucao": row.get("Ultima_Execucao", "").strip(),
            "ultima_hora": row.get("Ultima_Hora", "").strip(),
            "recorrencia_raw": row.get("Recorrencia_Raw", "").strip(),
        })
    return result
```

- [ ] **Step 2: Commit**

```bash
git add backend/services/parser_sx.py
git commit -m "feat: add parse_schedules parser with function name extraction"
```

---

## Chunk 2: Ingestor + Vinculos Integration

### Task 4: Integrate parsers into ingestor Phase 1

**Files:**
- Modify: `backend/services/ingestor.py:10` (import line)
- Modify: `backend/services/ingestor.py:216` (end of run_fase1, after mpmenu block)

- [ ] **Step 1: Update import**

In `ingestor.py` line 10, add `parse_jobs, parse_schedules` to the import:

```python
from backend.services.parser_sx import parse_sx2, parse_sx3, parse_six, parse_sx7, parse_sx1, parse_sx5, parse_sx6, parse_sx9, parse_sxa, parse_sxb, parse_mpmenu, parse_jobs, parse_schedules
```

- [ ] **Step 2: Add job ingestion block after mpmenu block (after line 216)**

```python
        # ── jobs ──
        job_csv = csv_dir / "job_detalhado_bash.csv"
        if not job_csv.exists():
            job_csv = csv_dir / "job_detalhado.csv"
        if job_csv.exists():
            try:
                job_rows = parse_jobs(job_csv)
                conn = self.db.get_raw_conn()
                conn.execute("DELETE FROM jobs")
                conn.executemany(
                    "INSERT OR REPLACE INTO jobs (arquivo_ini, sessao, rotina, refresh_rate, parametros) "
                    "VALUES (:arquivo_ini, :sessao, :rotina, :refresh_rate, :parametros)",
                    job_rows)
                conn.commit()
                del job_rows
                gc.collect()
                self.db.execute(
                    "INSERT OR REPLACE INTO ingest_progress (item, fase, status) VALUES (?, 1, 'done')",
                    ("jobs",))
                self.db.commit()
                yield {"fase": 1, "item": "jobs", "status": "done", "count": conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]}
            except Exception as e:
                self.db.execute(
                    "INSERT OR REPLACE INTO ingest_progress (item, fase, status, error_msg) VALUES (?, 1, 'error', ?)",
                    ("jobs", str(e)))
                self.db.commit()
                yield {"fase": 1, "item": "jobs", "status": "error", "msg": str(e)}
        else:
            yield {"fase": 1, "item": "jobs", "status": "skipped", "msg": "job CSV not found"}

        # ── schedules ──
        sched_csv = csv_dir / "schedule_decodificado.csv"
        if not sched_csv.exists():
            sched_csv = csv_dir / "schedule_decodificado.csv"
        if sched_csv.exists():
            try:
                sched_rows = parse_schedules(sched_csv)
                conn = self.db.get_raw_conn()
                conn.execute("DELETE FROM schedules")
                conn.executemany(
                    "INSERT OR REPLACE INTO schedules (codigo, rotina, empresa_filial, environment, modulo, status, "
                    "tipo_recorrencia, detalhe_recorrencia, execucoes_dia, intervalo, hora_inicio, "
                    "data_criacao, ultima_execucao, ultima_hora, recorrencia_raw) "
                    "VALUES (:codigo, :rotina, :empresa_filial, :environment, :modulo, :status, "
                    ":tipo_recorrencia, :detalhe_recorrencia, :execucoes_dia, :intervalo, :hora_inicio, "
                    ":data_criacao, :ultima_execucao, :ultima_hora, :recorrencia_raw)",
                    sched_rows)
                conn.commit()
                del sched_rows
                gc.collect()
                self.db.execute(
                    "INSERT OR REPLACE INTO ingest_progress (item, fase, status) VALUES (?, 1, 'done')",
                    ("schedules",))
                self.db.commit()
                yield {"fase": 1, "item": "schedules", "status": "done", "count": conn.execute("SELECT COUNT(*) FROM schedules").fetchone()[0]}
            except Exception as e:
                self.db.execute(
                    "INSERT OR REPLACE INTO ingest_progress (item, fase, status, error_msg) VALUES (?, 1, 'error', ?)",
                    ("schedules", str(e)))
                self.db.commit()
                yield {"fase": 1, "item": "schedules", "status": "error", "msg": str(e)}
        else:
            yield {"fase": 1, "item": "schedules", "status": "skipped", "msg": "schedule CSV not found"}
```

- [ ] **Step 3: Commit**

```bash
git add backend/services/ingestor.py
git commit -m "feat: integrate jobs and schedules into Phase 1 ingestion"
```

---

### Task 5: Add job/schedule vinculos to build_vinculos.py

**Files:**
- Modify: `backend/services/build_vinculos.py:170` (before `# INSERT ALL`)

- [ ] **Step 1: Add `_extract_function_name` import or inline, then add two vinculo blocks**

At the top of `build_vinculos.py`, after existing imports, add:

```python
def _extract_function_name(rotina_raw: str) -> str:
    """Extract clean function name from rotina field."""
    m = re.match(r'^([A-Za-z_]\w+)', rotina_raw.strip())
    return m.group(1) if m else rotina_raw.strip()
```

Before the `# INSERT ALL` comment (line 172), add:

```python
    # 10. job_executa_funcao
    print("10. job_executa_funcao...")
    c = len(vinculos)
    try:
        for arquivo_ini, sessao, rotina in db.execute(
                "SELECT arquivo_ini, sessao, rotina FROM jobs WHERE rotina != ''").fetchall():
            func_name = _extract_function_name(rotina)
            vinculos.append(('job_executa_funcao', 'job', sessao, 'funcao', func_name, '', f'ini={arquivo_ini}', 3))
    except Exception:
        pass  # Table may not exist
    print(f"   {len(vinculos) - c}")

    # 11. schedule_executa_funcao
    print("11. schedule_executa_funcao...")
    c = len(vinculos)
    try:
        for codigo, rotina, empresa, status in db.execute(
                "SELECT codigo, rotina, empresa_filial, status FROM schedules WHERE rotina != ''").fetchall():
            func_name = _extract_function_name(rotina)
            vinculos.append(('schedule_executa_funcao', 'schedule', codigo, 'funcao', func_name, '', f'filial={empresa}|{status}', 3))
    except Exception:
        pass  # Table may not exist
    print(f"   {len(vinculos) - c}")
```

- [ ] **Step 2: Commit**

```bash
git add backend/services/build_vinculos.py
git commit -m "feat: add job_executa_funcao and schedule_executa_funcao vinculos"
```

---

## Chunk 3: Explorer Backend Endpoints

### Task 6: Add /explorer/jobs endpoint

**Files:**
- Modify: `backend/routers/explorer.py` (add new endpoint after `/menu/{rotina}` around line 3510)

- [ ] **Step 1: Add jobs endpoint**

```python
@router.get("/jobs")
async def explorer_jobs():
    """Return job data grouped by arquivo_ini for Explorer tree."""
    db = _get_db()
    try:
        if not _table_exists(db, "jobs"):
            return {"total": 0, "groups": []}

        rows = db.execute(
            "SELECT arquivo_ini, sessao, rotina, refresh_rate, parametros FROM jobs ORDER BY arquivo_ini, sessao"
        ).fetchall()

        # Group by arquivo_ini
        groups = {}
        for arquivo_ini, sessao, rotina, refresh_rate, parametros in rows:
            if arquivo_ini not in groups:
                groups[arquivo_ini] = []

            # Try to find linked fonte
            fonte_arquivo = None
            func_name = re.match(r'^([A-Za-z_]\w+)', rotina or '')
            if func_name:
                func_name = func_name.group(1).upper()
                fonte_row = db.execute(
                    "SELECT arquivo FROM fontes WHERE upper(funcoes) LIKE ? OR upper(user_funcs) LIKE ?",
                    (f'%"{func_name}"%', f'%"{func_name}"%')
                ).fetchone()
                if fonte_row:
                    fonte_arquivo = fonte_row[0]

            rate_label = f"{refresh_rate}s" if refresh_rate else "N/A"
            groups[arquivo_ini].append({
                "sessao": sessao,
                "rotina": rotina,
                "refresh_rate": refresh_rate,
                "refresh_label": rate_label,
                "parametros": parametros if parametros != "N/A" else "",
                "fonte_arquivo": fonte_arquivo,
            })

        result = []
        for ini, sessions in sorted(groups.items()):
            result.append({
                "arquivo_ini": ini,
                "sessions": sessions,
                "count": len(sessions),
            })

        return {"total": len(rows), "groups": result}
    finally:
        db.close()
```

- [ ] **Step 2: Commit**

```bash
git add backend/routers/explorer.py
git commit -m "feat: add GET /explorer/jobs endpoint"
```

---

### Task 7: Add /explorer/schedules endpoint

**Files:**
- Modify: `backend/routers/explorer.py` (add after jobs endpoint)

- [ ] **Step 1: Add schedules endpoint**

```python
@router.get("/schedules")
async def explorer_schedules():
    """Return schedule data grouped by status for Explorer tree."""
    db = _get_db()
    try:
        if not _table_exists(db, "schedules"):
            return {"total": 0, "groups": []}

        rows = db.execute(
            "SELECT codigo, rotina, empresa_filial, environment, modulo, status, "
            "tipo_recorrencia, detalhe_recorrencia, execucoes_dia, intervalo, "
            "hora_inicio, data_criacao, ultima_execucao, ultima_hora "
            "FROM schedules ORDER BY status, rotina"
        ).fetchall()

        # Group by status
        by_status = {"Ativo": [], "Inativo": []}
        for (codigo, rotina, empresa, env, modulo, status, tipo_rec,
             detalhe, exec_dia, intervalo, hora_ini, data_cri, ult_exec, ult_hora) in rows:

            bucket = by_status.get(status, by_status.setdefault(status, []))

            # Try to find linked fonte
            fonte_arquivo = None
            func_name = rotina.upper() if rotina else ""
            if func_name:
                fonte_row = db.execute(
                    "SELECT arquivo FROM fontes WHERE upper(funcoes) LIKE ? OR upper(user_funcs) LIKE ?",
                    (f'%"{func_name}"%', f'%"{func_name}"%')
                ).fetchone()
                if fonte_row:
                    fonte_arquivo = fonte_row[0]

            # Build frequency label
            freq_parts = []
            if tipo_rec:
                freq_parts.append(tipo_rec)
            if exec_dia:
                freq_parts.append(f"{exec_dia}x/dia")
            if intervalo and intervalo != "N/A" and intervalo != "00:00":
                freq_parts.append(f"cada {intervalo}")
            if hora_ini and hora_ini != "N/A":
                freq_parts.append(f"inicio {hora_ini}")
            freq_label = " | ".join(freq_parts) if freq_parts else ""

            bucket.append({
                "codigo": codigo,
                "rotina": rotina,
                "empresa_filial": empresa,
                "environment": env,
                "modulo": modulo,
                "status": status,
                "tipo_recorrencia": tipo_rec,
                "detalhe_recorrencia": detalhe,
                "execucoes_dia": exec_dia,
                "intervalo": intervalo,
                "hora_inicio": hora_ini,
                "data_criacao": data_cri,
                "ultima_execucao": ult_exec,
                "ultima_hora": ult_hora,
                "freq_label": freq_label,
                "fonte_arquivo": fonte_arquivo,
            })

        result = []
        for status_key in ["Ativo", "Inativo"]:
            items = by_status.get(status_key, [])
            if items:
                result.append({
                    "status": status_key,
                    "items": items,
                    "count": len(items),
                })
        # Other statuses
        for status_key, items in by_status.items():
            if status_key not in ("Ativo", "Inativo") and items:
                result.append({
                    "status": status_key,
                    "items": items,
                    "count": len(items),
                })

        total = sum(len(g["items"]) for g in result)
        return {"total": total, "groups": result}
    finally:
        db.close()
```

- [ ] **Step 2: Commit**

```bash
git add backend/routers/explorer.py
git commit -m "feat: add GET /explorer/schedules endpoint"
```

---

### Task 8: Add jobs/schedules counts to /explorer/stats and /explorer/modules

**Files:**
- Modify: `backend/routers/explorer.py`

- [ ] **Step 1: In the `/stats` endpoint (around line 618), add counts for jobs and schedules**

After the existing counts (vinculos, menus, etc.), add:

```python
        jobs_total = 0
        if _table_exists(db, "jobs"):
            jobs_total = db.execute("SELECT count(*) FROM jobs").fetchone()[0]
        schedules_total = 0
        schedules_ativos = 0
        if _table_exists(db, "schedules"):
            schedules_total = db.execute("SELECT count(*) FROM schedules").fetchone()[0]
            schedules_ativos = db.execute("SELECT count(*) FROM schedules WHERE status='Ativo'").fetchone()[0]
```

And include in the returned dict:
```python
            "jobs": {"total": jobs_total},
            "schedules": {"total": schedules_total, "ativos": schedules_ativos},
```

- [ ] **Step 2: In the `/modules` endpoint (around line 862), add Jobs and Schedules as top-level tree nodes**

After the Webservices block (around line 877), add:

```python
        # ── Add Jobs group ──
        jobs_count = 0
        if _table_exists(db, "jobs"):
            jobs_count = db.execute("SELECT count(*) FROM jobs").fetchone()[0]
        if jobs_count > 0:
            result.append({
                "key": "_JOBS",
                "label": f"Jobs ({jobs_count})",
                "type": "jobs_root",
                "leaf": True,
                "icon": "pi pi-cog",
                "data": {"total": jobs_count},
            })

        # ── Add Schedules group ──
        sched_count = 0
        if _table_exists(db, "schedules"):
            sched_count = db.execute("SELECT count(*) FROM schedules").fetchone()[0]
        if sched_count > 0:
            sched_ativos = db.execute("SELECT count(*) FROM schedules WHERE status='Ativo'").fetchone()[0]
            result.append({
                "key": "_SCHEDULES",
                "label": f"Schedules ({sched_count})",
                "type": "schedules_root",
                "leaf": True,
                "icon": "pi pi-calendar",
                "data": {"total": sched_count, "ativos": sched_ativos},
            })
```

- [ ] **Step 3: Commit**

```bash
git add backend/routers/explorer.py
git commit -m "feat: add jobs/schedules counts to stats and modules endpoints"
```

---

## Chunk 4: Explorer Frontend

### Task 9: Add Jobs and Schedules panels to ExplorerView

**Files:**
- Modify: `frontend/src/views/ExplorerView.vue`

- [ ] **Step 1: Add data refs and load functions**

In the `<script setup>` section, add reactive refs and load functions for jobs and schedules data. When the user clicks a `_JOBS` or `_SCHEDULES` tree node, fetch the data from the corresponding endpoint and display in the detail panel.

Add after existing data refs:
```javascript
const jobsData = ref(null)
const schedulesData = ref(null)
```

Add load functions:
```javascript
async function loadJobs() {
  try {
    const res = await api.get('/explorer/jobs')
    jobsData.value = res.data
  } catch {
    toast.add({ severity: 'error', summary: 'Erro ao carregar Jobs', life: 3000 })
  }
}

async function loadSchedules() {
  try {
    const res = await api.get('/explorer/schedules')
    schedulesData.value = res.data
  } catch {
    toast.add({ severity: 'error', summary: 'Erro ao carregar Schedules', life: 3000 })
  }
}
```

- [ ] **Step 2: Handle tree node selection for jobs/schedules**

In the `onNodeSelect` handler, add cases for `jobs_root` and `schedules_root` types:

```javascript
if (node.type === 'jobs_root') {
  loadJobs()
  detail.value = { cat: 'jobs', label: 'Jobs', items: [] }
  return
}
if (node.type === 'schedules_root') {
  loadSchedules()
  detail.value = { cat: 'schedules', label: 'Schedules', items: [] }
  return
}
```

- [ ] **Step 3: Add detail panel templates for jobs and schedules**

In the template `<div>` that renders detail content, add blocks for `detail.cat === 'jobs'` and `detail.cat === 'schedules'`.

Jobs panel — table grouped by INI file:
```html
<div v-if="detail.cat === 'jobs' && jobsData">
  <h3>Jobs AppServer ({{ jobsData.total }} sessoes)</h3>
  <div v-for="group in jobsData.groups" :key="group.arquivo_ini" style="margin-bottom: 1.5rem;">
    <h4 style="margin-bottom:0.5rem;">{{ group.arquivo_ini }} ({{ group.count }})</h4>
    <DataTable :value="group.sessions" size="small" stripedRows>
      <Column field="sessao" header="Sessao" />
      <Column field="rotina" header="Rotina" />
      <Column field="refresh_label" header="Refresh" />
      <Column field="parametros" header="Parametros" />
      <Column header="Fonte">
        <template #body="{ data }">
          <a v-if="data.fonte_arquivo" href="#" @click.prevent="selectFonte(data.fonte_arquivo)">
            {{ data.fonte_arquivo }}
          </a>
          <span v-else style="color:#94a3b8;">-</span>
        </template>
      </Column>
    </DataTable>
  </div>
</div>
```

Schedules panel — table grouped by status:
```html
<div v-if="detail.cat === 'schedules' && schedulesData">
  <h3>Schedules ({{ schedulesData.total }})</h3>
  <div v-for="group in schedulesData.groups" :key="group.status" style="margin-bottom: 1.5rem;">
    <h4 style="margin-bottom:0.5rem;">
      <span :style="{ color: group.status === 'Ativo' ? '#16a34a' : '#dc2626' }">
        {{ group.status }}
      </span>
      ({{ group.count }})
    </h4>
    <DataTable :value="group.items" size="small" stripedRows
               :paginator="group.items.length > 20" :rows="20">
      <Column field="rotina" header="Rotina" />
      <Column field="freq_label" header="Frequencia" />
      <Column field="empresa_filial" header="Emp/Filial" />
      <Column field="hora_inicio" header="Hora Inicio" />
      <Column field="ultima_execucao" header="Ult. Exec." />
      <Column header="Fonte">
        <template #body="{ data }">
          <a v-if="data.fonte_arquivo" href="#" @click.prevent="selectFonte(data.fonte_arquivo)">
            {{ data.fonte_arquivo }}
          </a>
          <span v-else style="color:#94a3b8;">-</span>
        </template>
      </Column>
    </DataTable>
  </div>
</div>
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/ExplorerView.vue
git commit -m "feat: add Jobs and Schedules panels to Explorer view"
```

---

## Chunk 5: Test & Verify

### Task 10: End-to-end test

- [ ] **Step 1: Start backend and verify tables are created**

```bash
cd d:/IA/Projetos/Protheus
python -c "
from backend.services.database import Database
from pathlib import Path
db = Database(Path('workspace/clients/test/db/extrairpo.db'))
db.initialize()
tables = db.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()
print([t[0] for t in tables])
assert 'jobs' in [t[0] for t in tables]
assert 'schedules' in [t[0] for t in tables]
print('OK: tables exist')
db.close()
"
```

- [ ] **Step 2: Test parsers directly**

```bash
python -c "
from backend.services.parser_sx import parse_jobs, parse_schedules
from pathlib import Path
jobs = parse_jobs(Path('D:/Clientes/CSV/job_detalhado_bash.csv'))
scheds = parse_schedules(Path('D:/Clientes/CSV/schedule_decodificado.csv'))
print(f'Jobs: {len(jobs)} rows')
print(f'Schedules: {len(scheds)} rows')
print(f'Sample job: {jobs[0]}')
print(f'Sample schedule: {scheds[0]}')
# Verify function name extraction
assert scheds[0]['rotina'].find('(') == -1, 'Rotina should not contain parentheses'
print('OK: parsers work')
"
```

- [ ] **Step 3: Test full ingest via API or run the pipeline**

Run the app and trigger phase 1 ingest pointing to `D:/Clientes/CSV/`. Verify jobs and schedules appear in ingest_progress with status 'done'.

- [ ] **Step 4: Verify Explorer endpoints**

```bash
curl http://localhost:8000/api/explorer/jobs | python -m json.tool | head -20
curl http://localhost:8000/api/explorer/schedules | python -m json.tool | head -20
```

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "feat: jobs & schedules ingestion — complete pipeline with Explorer integration"
```
