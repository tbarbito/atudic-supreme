# Dashboard Performance Optimization

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce dashboard load time from ~10-30s to <1s by optimizing SQL queries, adding indexes, caching, and eliminating N+1 patterns.

**Architecture:** All changes are backend-only in `backend/routers/explorer.py` and `backend/services/database.py`. The single `/api/explorer/dashboard` endpoint is refactored to use consolidated SQL queries, proper indexes, and an in-memory cache with TTL. No frontend changes needed — same API contract.

**Tech Stack:** Python, FastAPI, SQLite3

---

## Chunk 1: Database Indexes & Connection Optimization

### Task 1: Add missing database indexes

**Files:**
- Modify: `backend/services/database.py:187-312` (add indexes after existing ones)

- [ ] **Step 1: Add indexes to SCHEMA**

Add these indexes at the end of the SCHEMA string (after line 312, before the closing `"""`):

```python
CREATE INDEX IF NOT EXISTS idx_tabelas_custom ON tabelas(custom);
CREATE INDEX IF NOT EXISTS idx_campos_custom ON campos(custom);
CREATE INDEX IF NOT EXISTS idx_campos_tabela ON campos(tabela);
CREATE INDEX IF NOT EXISTS idx_indices_custom ON indices(custom);
CREATE INDEX IF NOT EXISTS idx_gatilhos_custom ON gatilhos(custom);
CREATE INDEX IF NOT EXISTS idx_fontes_modulo ON fontes(modulo);
CREATE INDEX IF NOT EXISTS idx_diff_tipo_acao ON diff(tipo_sx, acao);
CREATE INDEX IF NOT EXISTS idx_diff_tabela ON diff(tabela);
CREATE INDEX IF NOT EXISTS idx_menus_rotina ON menus(rotina);
```

- [ ] **Step 2: Verify indexes apply to existing DBs**

The `CREATE INDEX IF NOT EXISTS` pattern means indexes are created on next `db.initialize()` call, which happens every request — so existing databases will get indexes on first load. No migration needed.

- [ ] **Step 3: Commit**

```bash
git add backend/services/database.py
git commit -m "perf: add missing database indexes for dashboard queries"
```

---

### Task 2: Optimize Database connection — skip SCHEMA re-run on every request

**Files:**
- Modify: `backend/services/database.py:315-343`

- [ ] **Step 1: Add schema version tracking to avoid re-running CREATE TABLE on every call**

Replace the `initialize` method to only run SCHEMA once per database file:

```python
_initialized_dbs: set[str] = set()

class Database:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._conn = None

    def initialize(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        key = str(self.db_path)
        if key not in _initialized_dbs:
            self._conn.executescript(SCHEMA)
            self._conn.commit()
            _initialized_dbs.add(key)
```

- [ ] **Step 2: Commit**

```bash
git add backend/services/database.py
git commit -m "perf: skip SCHEMA re-run on already-initialized databases"
```

---

## Chunk 2: Consolidate COUNT Queries

### Task 3: Replace 8 separate COUNT queries with 4 consolidated queries

**Files:**
- Modify: `backend/routers/explorer.py:250-258`

- [ ] **Step 1: Replace the 8 individual COUNT queries**

Replace lines 250-258 with consolidated queries using `SUM(CASE...)`:

```python
        # --- resumo counts (consolidated) ---
        row = db.execute(
            "SELECT count(*), SUM(CASE WHEN custom=1 THEN 1 ELSE 0 END) FROM tabelas"
        ).fetchone()
        tabelas_total, tabelas_custom = row[0], row[1] or 0

        row = db.execute(
            "SELECT count(*), SUM(CASE WHEN custom=1 THEN 1 ELSE 0 END) FROM campos"
        ).fetchone()
        campos_total, campos_custom = row[0], row[1] or 0

        row = db.execute(
            "SELECT count(*), SUM(CASE WHEN custom=1 THEN 1 ELSE 0 END) FROM indices"
        ).fetchone()
        indices_total, indices_custom = row[0], row[1] or 0

        row = db.execute(
            "SELECT count(*), SUM(CASE WHEN custom=1 THEN 1 ELSE 0 END) FROM gatilhos"
        ).fetchone()
        gatilhos_total, gatilhos_custom = row[0], row[1] or 0
```

This reduces 8 queries to 4.

- [ ] **Step 2: Commit**

```bash
git add backend/routers/explorer.py
git commit -m "perf: consolidate 8 COUNT queries into 4 using conditional aggregation"
```

---

## Chunk 3: Eliminate JSON Parsing Loops & N+1 Queries

### Task 4: Replace Python JSON array counting with SQL

**Files:**
- Modify: `backend/routers/explorer.py:261-272`

- [ ] **Step 1: Replace Python JSON loops with SQL json_each**

SQLite supports `json_each()` for counting array elements. Replace lines 261-272:

```python
        # Total functions (count JSON array elements via SQL)
        funcoes_total = db.execute(
            "SELECT count(*) FROM fontes, json_each(fontes.funcoes) "
            "WHERE funcoes IS NOT NULL AND funcoes != '' AND funcoes != '[]'"
        ).fetchone()[0]

        # PEs catalogados
        pes_catalogados = db.execute(
            "SELECT count(*) FROM fontes, json_each(fontes.pontos_entrada) "
            "WHERE pontos_entrada IS NOT NULL AND pontos_entrada != '' AND pontos_entrada != '[]'"
        ).fetchone()[0]
```

**Fallback:** If `json_each` is not available (SQLite < 3.38), keep the Python loop but wrapped in a try/except:

```python
        try:
            funcoes_total = db.execute(
                "SELECT count(*) FROM fontes, json_each(fontes.funcoes) "
                "WHERE funcoes IS NOT NULL AND funcoes != '' AND funcoes != '[]'"
            ).fetchone()[0]
        except Exception:
            funcoes_total = 0
            for row in db.execute("SELECT funcoes FROM fontes WHERE funcoes IS NOT NULL AND funcoes != '' AND funcoes != '[]'").fetchall():
                funcoes_total += len(_safe_json(row[0]))
```

Apply the same pattern for `pes_catalogados`.

- [ ] **Step 2: Commit**

```bash
git add backend/routers/explorer.py
git commit -m "perf: replace Python JSON loops with SQL json_each for function/PE counts"
```

---

### Task 5: Consolidate diff COUNT queries

**Files:**
- Modify: `backend/routers/explorer.py:300-316`

- [ ] **Step 1: Replace 3 separate diff COUNTs with one query**

Replace lines 300-316:

```python
        # Diff stats (single query)
        campos_adicionados = 0
        campos_alterados = 0
        campos_removidos = 0
        if _table_exists(db, "diff"):
            try:
                for row in db.execute(
                    "SELECT acao, count(*) FROM diff WHERE tipo_sx='campo' GROUP BY acao"
                ).fetchall():
                    if row[0] == 'adicionado':
                        campos_adicionados = row[1]
                    elif row[0] == 'alterado':
                        campos_alterados = row[1]
                    elif row[0] == 'removido':
                        campos_removidos = row[1]
            except Exception:
                pass
```

3 queries -> 1.

- [ ] **Step 2: Commit**

```bash
git add backend/routers/explorer.py
git commit -m "perf: consolidate 3 diff COUNT queries into 1 with GROUP BY"
```

---

### Task 6: Fix N+1 query in top_interacao

**Files:**
- Modify: `backend/routers/explorer.py:449-477`

- [ ] **Step 1: Batch-load all table names upfront, then look up in memory**

Replace lines 449-477:

```python
        # --- top_interacao: tables with most fonte interactions ---
        read_count = {}
        write_count = {}
        for r in db.execute("SELECT tabelas_ref, write_tables FROM fontes").fetchall():
            for t in _safe_json(r[0]):
                k = t.upper()
                read_count[k] = read_count.get(k, 0) + 1
            for t in _safe_json(r[1]):
                k = t.upper()
                write_count[k] = write_count.get(k, 0) + 1

        # Batch-load all table names (eliminates N+1)
        tabela_nomes = {}
        for row in db.execute("SELECT codigo, nome FROM tabelas").fetchall():
            tabela_nomes[row[0].upper()] = row[1] or ""

        all_tabs = set(read_count.keys()) | set(write_count.keys())
        top_interacao = []
        for k in all_tabs:
            reads = read_count.get(k, 0)
            writes = write_count.get(k, 0)
            total_i = reads + writes
            if total_i < 5:
                continue
            top_interacao.append({
                "codigo": k,
                "nome": tabela_nomes.get(k, ""),
                "leitura": reads,
                "escrita": writes,
                "total": total_i,
            })
        top_interacao.sort(key=lambda x: x["total"], reverse=True)
        top_interacao = top_interacao[:10]
```

This replaces ~500 individual queries with 1 batch query.

- [ ] **Step 2: Commit**

```bash
git add backend/routers/explorer.py
git commit -m "perf: eliminate N+1 queries in top_interacao with batch table name lookup"
```

---

## Chunk 4: Module Grouping via SQL & UPPER() Removal

### Task 7: Replace Python grouping loops with SQL GROUP BY

**Files:**
- Modify: `backend/routers/explorer.py:361-397`

- [ ] **Step 1: Use SQL GROUP BY for module font counts**

Replace the Python loop at lines 371-373:

```python
        # Module source counts via SQL
        mod_fontes = {}
        for row in db.execute("SELECT modulo, count(*) FROM fontes GROUP BY modulo").fetchall():
            mod = _normalize_modulo(row[0] or "") or "OUTROS"
            mod_fontes[mod] = mod_fontes.get(mod, 0) + row[1]
```

This moves the counting to SQL (1 query instead of loading all rows).

- [ ] **Step 2: Commit**

```bash
git add backend/routers/explorer.py
git commit -m "perf: use SQL GROUP BY for module font counts instead of Python loops"
```

---

### Task 8: Fix UPPER() in JOINs preventing index usage

**Files:**
- Modify: `backend/routers/explorer.py:403-406` and `431-434`

- [ ] **Step 1: Use COLLATE NOCASE instead of UPPER()**

Replace the record_counts JOINs:

```python
            rc_rows = db.execute(
                "SELECT rc.tabela, t.nome, rc.registros "
                "FROM record_counts rc LEFT JOIN tabelas t ON rc.tabela = t.codigo COLLATE NOCASE "
                "ORDER BY rc.registros DESC LIMIT 50"
            ).fetchall()
```

And the same for `top_registros` query at line 431-434:

```python
            rr_rows = db.execute(
                "SELECT rc.tabela, t.nome, rc.registros "
                "FROM record_counts rc LEFT JOIN tabelas t ON rc.tabela = t.codigo COLLATE NOCASE "
                "ORDER BY rc.registros DESC LIMIT 10"
            ).fetchall()
```

- [ ] **Step 2: Commit**

```bash
git add backend/routers/explorer.py
git commit -m "perf: replace UPPER() in JOINs with COLLATE NOCASE for index usage"
```

---

## Chunk 5: Response Caching

### Task 9: Add in-memory cache with TTL for dashboard endpoint

**Files:**
- Modify: `backend/routers/explorer.py:1-10` (imports) and `242-245` (endpoint)

- [ ] **Step 1: Add a simple time-based cache at module level**

Add after the imports (line 8):

```python
import time

_dashboard_cache = {}
_DASHBOARD_CACHE_TTL = 30  # seconds
```

- [ ] **Step 2: Wrap the dashboard endpoint with cache logic**

Modify the dashboard function:

```python
@router.get("/dashboard")
async def dashboard():
    """Comprehensive dashboard data in a single call."""
    config = load_config(CONFIG_PATH)
    cliente = config.active_client if config else "Unknown"
    cache_key = cliente

    now = time.time()
    if cache_key in _dashboard_cache:
        cached_at, cached_data = _dashboard_cache[cache_key]
        if now - cached_at < _DASHBOARD_CACHE_TTL:
            return cached_data

    db = _get_db()
    try:
        # ... existing logic (unchanged) ...
        result = {
            "cliente": cliente,
            "resumo": resumo,
            "modulos": modulos,
            "top_tabelas": top_tabelas,
            "top_registros": top_registros,
            "top_interacao": top_interacao,
            "top_fontes": top_fontes,
            "cobertura_resumos": cobertura_resumos,
            "distribuicao_risco": distribuicao_risco,
        }
        _dashboard_cache[cache_key] = (now, result)
        return result
    finally:
        db.close()
```

- [ ] **Step 3: Add cache invalidation endpoint**

Add after the dashboard endpoint:

```python
@router.post("/dashboard/refresh")
async def dashboard_refresh():
    """Force refresh dashboard cache."""
    _dashboard_cache.clear()
    return {"status": "cache_cleared"}
```

- [ ] **Step 4: Commit**

```bash
git add backend/routers/explorer.py
git commit -m "perf: add 30s TTL cache for dashboard endpoint"
```

---

### Task 10: Cache _load_mapa_modulos at module level

**Files:**
- Modify: `backend/routers/explorer.py:138-141`

- [ ] **Step 1: Add simple module-level cache**

Replace:

```python
_mapa_modulos_cache = None

def _load_mapa_modulos() -> dict:
    global _mapa_modulos_cache
    if _mapa_modulos_cache is not None:
        return _mapa_modulos_cache
    if MAPA_MODULOS_PATH.exists():
        _mapa_modulos_cache = json.loads(MAPA_MODULOS_PATH.read_text(encoding="utf-8"))
        return _mapa_modulos_cache
    return {}
```

- [ ] **Step 2: Commit**

```bash
git add backend/routers/explorer.py
git commit -m "perf: cache mapa_modulos JSON file read"
```

---

## Summary of Expected Impact

| Optimization | Queries Saved | Estimated Speedup |
|---|---|---|
| Consolidated COUNTs (Task 3) | 4 queries eliminated | ~200ms |
| SQL json_each (Task 4) | Eliminates Python loops over all fontes | ~1-3s |
| Consolidated diff COUNTs (Task 5) | 2 queries eliminated | ~100ms |
| N+1 fix (Task 6) | ~500 queries eliminated | ~3-10s |
| SQL GROUP BY (Task 7) | Eliminates full table scan in Python | ~500ms |
| COLLATE NOCASE (Task 8) | Enables index usage on JOINs | ~500ms |
| Dashboard cache (Task 9) | All queries on cache hit | ~10-30s on reload |
| Mapa modulos cache (Task 10) | File I/O eliminated | ~50ms |
| Database indexes (Task 1) | Speeds up all WHERE/JOIN | ~2-5s cumulative |
| Skip SCHEMA re-run (Task 2) | Eliminates executescript overhead | ~100ms |

**Total: First load ~5-15s faster. Subsequent loads (within 30s): instant from cache.**
