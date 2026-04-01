# ExtraiRPO Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone Python+web application that ingests a Protheus client's data dictionary and custom source files, then provides an AI-powered knowledge base with chat interface.

**Architecture:** FastAPI backend serves a Vue 3 SPA and exposes REST/SSE endpoints. SQLite stores structured dictionary data, ChromaDB stores source file embeddings. LiteLLM abstracts AI providers. The app runs as a single process via `python run.py`.

**Tech Stack:** Python 3.11+, FastAPI, SQLite, ChromaDB, LiteLLM, Vue 3 + Vite, SSE

**Spec:** `docs/superpowers/specs/2026-03-18-extrairpo-design.md`

---

## Chunk 1: Project Foundation

### Task 1: Project Scaffold and Dependencies

**Files:**
- Create: `requirements.txt`
- Create: `run.py`
- Create: `backend/__init__.py`
- Create: `backend/app.py`
- Create: `backend/routers/__init__.py`
- Create: `backend/services/__init__.py`

- [ ] **Step 1: Create requirements.txt**

```
fastapi==0.115.0
uvicorn[standard]==0.30.0
litellm==1.50.0
chromadb==0.5.0
chardet==5.2.0
pydantic==2.9.0
python-multipart==0.0.9
sse-starlette==2.1.0
aiosqlite==0.20.0
```

- [ ] **Step 2: Create virtual environment and install**

Run: `python -m venv .venv && .venv/Scripts/activate && pip install -r requirements.txt`
Expected: All packages install successfully

- [ ] **Step 3: Create run.py entry point**

```python
import subprocess
import sys
import webbrowser
import time
import uvicorn

PORT = 8741

def main():
    print(f"ExtraiRPO starting on http://localhost:{PORT}")
    webbrowser.open(f"http://localhost:{PORT}")
    uvicorn.run("backend.app:app", host="0.0.0.0", port=PORT, reload=False)

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Create backend/app.py with FastAPI skeleton**

```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

app = FastAPI(title="ExtraiRPO", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

WORKSPACE_DIR = Path("workspace")
CONFIG_PATH = Path("config.json")

@app.get("/api/status")
async def status():
    if not CONFIG_PATH.exists():
        return {"status": "setup_pending"}
    return {"status": "ready"}

# Static frontend (will be mounted after frontend build)
frontend_dist = Path("frontend/dist")
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
```

- [ ] **Step 5: Create __init__.py files**

Create empty `backend/__init__.py`, `backend/routers/__init__.py`, `backend/services/__init__.py`

- [ ] **Step 6: Test that server starts**

Run: `python run.py`
Expected: Server starts, browser opens, `/api/status` returns `{"status": "setup_pending"}`

- [ ] **Step 7: Create .gitignore**

```
.venv/
__pycache__/
*.pyc
workspace/
config.json
node_modules/
frontend/dist/
.env
```

- [ ] **Step 8: Commit**

```bash
git init
git add .gitignore requirements.txt run.py backend/
git commit -m "feat: project scaffold with FastAPI skeleton"
```

---

### Task 2: SQLite Database Schema

**Files:**
- Create: `backend/services/database.py`
- Create: `tests/__init__.py`
- Create: `tests/test_database.py`

- [ ] **Step 1: Write test for database initialization**

```python
# tests/test_database.py
import pytest
import os
import tempfile
from pathlib import Path
from backend.services.database import Database

@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "test.db"

@pytest.fixture
def db(db_path):
    database = Database(db_path)
    database.initialize()
    return database

def test_initialize_creates_tables(db, db_path):
    assert db_path.exists()
    tables = db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    table_names = {row[0] for row in tables}
    assert "tabelas" in table_names
    assert "campos" in table_names
    assert "indices" in table_names
    assert "gatilhos" in table_names
    assert "fontes" in table_names
    assert "chat_history" in table_names
    assert "ingest_progress" in table_names

def test_insert_tabela(db):
    db.execute("INSERT INTO tabelas (codigo, nome, modo, custom) VALUES (?, ?, ?, ?)",
               ("SA1", "Clientes", "C", 0))
    row = db.execute("SELECT * FROM tabelas WHERE codigo = 'SA1'").fetchone()
    assert row[0] == "SA1"
    assert row[1] == "Clientes"

def test_campos_composite_key(db):
    db.execute("INSERT INTO tabelas (codigo, nome) VALUES ('SA1', 'Clientes')")
    db.execute("INSERT INTO campos (tabela, campo, tipo, tamanho) VALUES ('SA1', 'A1_COD', 'C', 6)")
    db.execute("INSERT INTO tabelas (codigo, nome) VALUES ('SA2', 'Fornecedores')")
    db.execute("INSERT INTO campos (tabela, campo, tipo, tamanho) VALUES ('SA2', 'A2_COD', 'C', 6)")
    rows = db.execute("SELECT * FROM campos").fetchall()
    assert len(rows) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_database.py -v`
Expected: FAIL — module `backend.services.database` not found

- [ ] **Step 3: Implement Database class**

```python
# backend/services/database.py
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS tabelas (
    codigo      TEXT PRIMARY KEY,
    nome        TEXT,
    modo        TEXT,
    custom      INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS campos (
    tabela      TEXT REFERENCES tabelas(codigo),
    campo       TEXT,
    tipo        TEXT,
    tamanho     INTEGER,
    decimal     INTEGER,
    titulo      TEXT,
    descricao   TEXT,
    validacao   TEXT,
    inicializador TEXT,
    obrigatorio INTEGER DEFAULT 0,
    custom      INTEGER DEFAULT 0,
    PRIMARY KEY (tabela, campo)
);

CREATE TABLE IF NOT EXISTS indices (
    tabela      TEXT REFERENCES tabelas(codigo),
    indice      TEXT,
    chave       TEXT,
    descricao   TEXT,
    PRIMARY KEY (tabela, indice)
);

CREATE TABLE IF NOT EXISTS gatilhos (
    campo_origem TEXT,
    sequencia   TEXT,
    campo_destino TEXT,
    regra       TEXT,
    tipo        TEXT,
    tabela      TEXT REFERENCES tabelas(codigo),
    custom      INTEGER DEFAULT 0,
    PRIMARY KEY (campo_origem, sequencia)
);

CREATE TABLE IF NOT EXISTS fontes (
    arquivo     TEXT PRIMARY KEY,
    caminho     TEXT,
    tipo        TEXT,
    modulo      TEXT,
    funcoes     TEXT,
    user_funcs  TEXT,
    pontos_entrada TEXT,
    tabelas_ref TEXT,
    includes    TEXT,
    hash        TEXT
);

CREATE TABLE IF NOT EXISTS chat_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    role        TEXT,
    content     TEXT,
    sources     TEXT,
    doc_updated TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS ingest_progress (
    item        TEXT PRIMARY KEY,
    fase        INTEGER,
    status      TEXT,
    error_msg   TEXT,
    updated_at  TEXT DEFAULT (datetime('now'))
);
"""

class Database:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._conn = None

    def initialize(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def execute(self, sql: str, params: tuple = ()):
        return self._conn.execute(sql, params)

    def executemany(self, sql: str, params_list: list):
        self._conn.executemany(sql, params_list)
        self._conn.commit()

    def commit(self):
        self._conn.commit()

    def close(self):
        if self._conn:
            self._conn.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_database.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/database.py tests/
git commit -m "feat: SQLite database with full schema"
```

---

### Task 3: Config Management

**Files:**
- Create: `backend/services/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write test for config load/save**

```python
# tests/test_config.py
import pytest
from pathlib import Path
from backend.services.config import AppConfig, load_config, save_config

def test_save_and_load_config(tmp_path):
    config_path = tmp_path / "config.json"
    config = AppConfig(
        cliente="ACME Corp",
        paths={"csv_dicionario": "C:/dados", "fontes_custom": "C:/fontes"},
        llm={"provider": "anthropic", "model": "claude-sonnet-4-20250514", "api_key": "sk-test"}
    )
    save_config(config, config_path)
    loaded = load_config(config_path)
    assert loaded.cliente == "ACME Corp"
    assert loaded.paths["csv_dicionario"] == "C:/dados"
    assert loaded.llm["provider"] == "anthropic"

def test_load_missing_config(tmp_path):
    config_path = tmp_path / "missing.json"
    result = load_config(config_path)
    assert result is None

def test_config_has_required_fields():
    with pytest.raises(Exception):
        AppConfig(cliente="", paths={}, llm={})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL

- [ ] **Step 3: Implement config module**

```python
# backend/services/config.py
import json
from pathlib import Path
from pydantic import BaseModel, field_validator
from typing import Optional

class AppConfig(BaseModel):
    cliente: str
    paths: dict  # csv_dicionario, fontes_custom, fontes_padrao (optional)
    llm: dict    # provider, model, api_key

    @field_validator("cliente")
    @classmethod
    def cliente_not_empty(cls, v):
        if not v.strip():
            raise ValueError("cliente must not be empty")
        return v.strip()

def save_config(config: AppConfig, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config.model_dump(), indent=2, ensure_ascii=False), encoding="utf-8")

def load_config(path: Path) -> Optional[AppConfig]:
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return AppConfig(**data)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_config.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/config.py tests/test_config.py
git commit -m "feat: config management with load/save"
```

---

## Chunk 2: CSV Parsers (Fase 1)

### Task 4: SX2 Parser (Tabelas)

**Files:**
- Create: `backend/services/parser_sx.py`
- Create: `tests/test_parser_sx.py`
- Create: `tests/fixtures/`

- [ ] **Step 1: Create test fixture CSV**

Create `tests/fixtures/SX2.csv`:
```csv
X2_CHAVE;X2_NOME;X2_MODO
SA1;Clientes;C
SA2;Fornecedores;C
SZ1;Custom Table;E
```

- [ ] **Step 2: Write test for SX2 parser**

```python
# tests/test_parser_sx.py
import pytest
from pathlib import Path
from backend.services.parser_sx import parse_sx2

FIXTURES = Path(__file__).parent / "fixtures"

def test_parse_sx2():
    result = parse_sx2(FIXTURES / "SX2.csv")
    assert len(result) == 3
    assert result[0]["codigo"] == "SA1"
    assert result[0]["nome"] == "Clientes"
    assert result[0]["custom"] == 0
    assert result[2]["codigo"] == "SZ1"
    assert result[2]["custom"] == 1  # SZ* is custom

def test_parse_sx2_detects_custom_tables():
    result = parse_sx2(FIXTURES / "SX2.csv")
    customs = [r for r in result if r["custom"] == 1]
    assert len(customs) == 1
    assert customs[0]["codigo"] == "SZ1"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_parser_sx.py::test_parse_sx2 -v`
Expected: FAIL

- [ ] **Step 4: Implement SX2 parser**

```python
# backend/services/parser_sx.py
import csv
import re
from pathlib import Path
from typing import List
import chardet

def _detect_encoding(file_path: Path) -> str:
    raw = file_path.read_bytes()
    result = chardet.detect(raw)
    return result["encoding"] or "cp1252"

def _detect_delimiter(file_path: Path, encoding: str) -> str:
    with open(file_path, "r", encoding=encoding, errors="replace") as f:
        first_line = f.readline()
    if ";" in first_line:
        return ";"
    return ","

def _is_custom_table(codigo: str) -> bool:
    if re.match(r"^SZ[0-9A-Z]$", codigo):
        return True
    if re.match(r"^Q[A-Z][0-9A-Z]$", codigo):
        return True
    return False

def _read_csv(file_path: Path) -> list[dict]:
    encoding = _detect_encoding(file_path)
    delimiter = _detect_delimiter(file_path, encoding)
    with open(file_path, "r", encoding=encoding, errors="replace") as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        return [row for row in reader]

def parse_sx2(file_path: Path) -> List[dict]:
    rows = _read_csv(file_path)
    result = []
    for row in rows:
        codigo = row.get("X2_CHAVE", "").strip()
        if not codigo:
            continue
        result.append({
            "codigo": codigo,
            "nome": row.get("X2_NOME", "").strip(),
            "modo": row.get("X2_MODO", "").strip(),
            "custom": 1 if _is_custom_table(codigo) else 0,
        })
    return result
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_parser_sx.py -v`
Expected: All 2 tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/services/parser_sx.py tests/test_parser_sx.py tests/fixtures/
git commit -m "feat: SX2 CSV parser with encoding detection"
```

---

### Task 5: SX3 Parser (Campos)

**Files:**
- Modify: `backend/services/parser_sx.py`
- Modify: `tests/test_parser_sx.py`

- [ ] **Step 1: Create SX3 fixture**

Create `tests/fixtures/SX3.csv`:
```csv
X3_ARQUIVO;X3_CAMPO;X3_TIPO;X3_TAMANHO;X3_DECIMAL;X3_TITULO;X3_DESCRIC;X3_VALID;X3_RELACAO;X3_OBRIGAT
SA1;A1_COD;C;6;0;Codigo;Codigo do Cliente;;;"S"
SA1;A1_NOME;C;40;0;Nome;Nome do Cliente;;;
SA1;A1_XREGIAO;C;3;0;Regiao;Regiao Custom;;;"N"
```

- [ ] **Step 2: Write test for SX3 parser**

```python
# Add to tests/test_parser_sx.py
from backend.services.parser_sx import parse_sx3

def test_parse_sx3():
    result = parse_sx3(FIXTURES / "SX3.csv")
    assert len(result) == 3
    assert result[0]["tabela"] == "SA1"
    assert result[0]["campo"] == "A1_COD"
    assert result[0]["tipo"] == "C"
    assert result[0]["tamanho"] == 6

def test_parse_sx3_detects_custom_fields():
    result = parse_sx3(FIXTURES / "SX3.csv")
    customs = [r for r in result if r["custom"] == 1]
    assert len(customs) == 1
    assert customs[0]["campo"] == "A1_XREGIAO"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_parser_sx.py::test_parse_sx3 -v`
Expected: FAIL

- [ ] **Step 4: Implement SX3 parser**

Add to `backend/services/parser_sx.py`:
```python
def _is_custom_field(campo: str) -> bool:
    parts = campo.split("_")
    if len(parts) >= 2 and parts[1].startswith("X"):
        return True
    return False

def parse_sx3(file_path: Path) -> List[dict]:
    rows = _read_csv(file_path)
    result = []
    for row in rows:
        campo = row.get("X3_CAMPO", "").strip()
        if not campo:
            continue
        result.append({
            "tabela": row.get("X3_ARQUIVO", "").strip(),
            "campo": campo,
            "tipo": row.get("X3_TIPO", "").strip(),
            "tamanho": int(row.get("X3_TAMANHO", "0").strip() or 0),
            "decimal": int(row.get("X3_DECIMAL", "0").strip() or 0),
            "titulo": row.get("X3_TITULO", "").strip(),
            "descricao": row.get("X3_DESCRIC", "").strip(),
            "validacao": row.get("X3_VALID", "").strip(),
            "inicializador": row.get("X3_RELACAO", "").strip(),
            "obrigatorio": 1 if row.get("X3_OBRIGAT", "").strip() == "S" else 0,
            "custom": 1 if _is_custom_field(campo) else 0,
        })
    return result
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_parser_sx.py -v`
Expected: All 4 tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/services/parser_sx.py tests/test_parser_sx.py tests/fixtures/SX3.csv
git commit -m "feat: SX3 CSV parser with custom field detection"
```

---

### Task 6: SIX and SX7 Parsers (Indices + Gatilhos)

**Files:**
- Modify: `backend/services/parser_sx.py`
- Modify: `tests/test_parser_sx.py`

- [ ] **Step 1: Create SIX and SX7 fixtures**

Create `tests/fixtures/SIX.csv`:
```csv
X6_FIL;X6_ARQUIVO;X6_ORDEM;X6_CHAVE;X6_DESCRI
;SA1;1;A1_FILIAL+A1_COD+A1_LOJA;Codigo+Loja
;SA1;2;A1_FILIAL+A1_NOME;Nome
```

Create `tests/fixtures/SX7.csv`:
```csv
X7_CAMPO;X7_SEQUENC;X7_CDOMIN;X7_REGRA;X7_TIPO;X7_ARQUIVO
C5_CLIENT;001;C5_XREGIAO;SA1->A1_XREGIAO;P;SC5
A1_COD;001;A1_NOME;SA1->A1_NOME;P;SA1
```

- [ ] **Step 2: Write tests**

```python
# Add to tests/test_parser_sx.py
from backend.services.parser_sx import parse_six, parse_sx7

def test_parse_six():
    result = parse_six(FIXTURES / "SIX.csv")
    assert len(result) == 2
    assert result[0]["tabela"] == "SA1"
    assert result[0]["indice"] == "1"
    assert "A1_COD" in result[0]["chave"]

def test_parse_sx7():
    result = parse_sx7(FIXTURES / "SX7.csv")
    assert len(result) == 2
    assert result[0]["campo_origem"] == "C5_CLIENT"
    assert result[0]["campo_destino"] == "C5_XREGIAO"

def test_parse_sx7_detects_custom_triggers():
    result = parse_sx7(FIXTURES / "SX7.csv")
    customs = [r for r in result if r["custom"] == 1]
    assert len(customs) == 1  # C5_XREGIAO is custom destination
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_parser_sx.py::test_parse_six -v`
Expected: FAIL

- [ ] **Step 4: Implement SIX and SX7 parsers**

Add to `backend/services/parser_sx.py`:
```python
def parse_six(file_path: Path) -> List[dict]:
    rows = _read_csv(file_path)
    result = []
    for row in rows:
        tabela = row.get("X6_ARQUIVO", "").strip()
        indice = row.get("X6_ORDEM", "").strip()
        if not tabela or not indice:
            continue
        result.append({
            "tabela": tabela,
            "indice": indice,
            "chave": row.get("X6_CHAVE", "").strip(),
            "descricao": row.get("X6_DESCRI", "").strip(),
        })
    return result

def parse_sx7(file_path: Path) -> List[dict]:
    rows = _read_csv(file_path)
    result = []
    for row in rows:
        campo_origem = row.get("X7_CAMPO", "").strip()
        if not campo_origem:
            continue
        campo_destino = row.get("X7_CDOMIN", "").strip()
        result.append({
            "campo_origem": campo_origem,
            "sequencia": row.get("X7_SEQUENC", "").strip(),
            "campo_destino": campo_destino,
            "regra": row.get("X7_REGRA", "").strip(),
            "tipo": row.get("X7_TIPO", "").strip(),
            "tabela": row.get("X7_ARQUIVO", "").strip(),
            "custom": 1 if _is_custom_field(campo_destino) else 0,
        })
    return result
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_parser_sx.py -v`
Expected: All 7 tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/services/parser_sx.py tests/test_parser_sx.py tests/fixtures/SIX.csv tests/fixtures/SX7.csv
git commit -m "feat: SIX and SX7 parsers (indices + triggers)"
```

---

## Chunk 3: Source Parser + VectorStore

### Task 7: Source File Parser (.prw/.tlpp)

**Files:**
- Create: `backend/services/parser_source.py`
- Create: `tests/test_parser_source.py`
- Create: `tests/fixtures/sample.prw`

- [ ] **Step 1: Create sample source fixture**

Create `tests/fixtures/sample.prw`:
```
#Include "Protheus.ch"
#Include "TopConn.ch"

/*/{Protheus.doc} XFAT001
Validacao customizada do pedido de venda
@author Dev
@since 01/01/2026
/*/
User Function XFAT001()
    Local cQuery := ""
    Local cAlias := GetNextAlias()

    DbSelectArea("SC5")
    cQuery := "SELECT C5_NUM, C5_CLIENTE FROM " + RetSqlName("SC5")
    MpSysOpenQuery(cQuery, cAlias)

    (cAlias)->(DbCloseArea())
    RestArea()
Return .T.

Static Function ValidaPedido(cNumPed)
    Local lRet := .T.
    DbSelectArea("SA1")
    MsExecAuto({|x,y| MATA410(x,y)}, aParam)
Return lRet
```

- [ ] **Step 2: Write tests**

```python
# tests/test_parser_source.py
import pytest
from pathlib import Path
from backend.services.parser_source import parse_source

FIXTURES = Path(__file__).parent / "fixtures"

def test_parse_source_extracts_functions():
    result = parse_source(FIXTURES / "sample.prw")
    assert "XFAT001" in result["funcoes"]
    assert "ValidaPedido" in result["funcoes"]

def test_parse_source_detects_user_functions():
    result = parse_source(FIXTURES / "sample.prw")
    assert "XFAT001" in result["user_funcs"]
    assert "ValidaPedido" not in result["user_funcs"]

def test_parse_source_extracts_tables():
    result = parse_source(FIXTURES / "sample.prw")
    assert "SC5" in result["tabelas_ref"]
    assert "SA1" in result["tabelas_ref"]

def test_parse_source_extracts_includes():
    result = parse_source(FIXTURES / "sample.prw")
    assert "Protheus.ch" in result["includes"]
    assert "TopConn.ch" in result["includes"]

def test_parse_source_detects_execauto():
    result = parse_source(FIXTURES / "sample.prw")
    assert len(result["exec_autos"]) >= 1

def test_parse_source_extracts_chunks():
    result = parse_source(FIXTURES / "sample.prw")
    assert len(result["chunks"]) >= 2  # header + 2 functions
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_parser_source.py -v`
Expected: FAIL

- [ ] **Step 4: Implement source parser**

```python
# backend/services/parser_source.py
import re
import hashlib
from pathlib import Path

def _read_file(file_path: Path) -> str:
    for enc in ["utf-8", "cp1252", "latin-1"]:
        try:
            return file_path.read_text(encoding=enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return file_path.read_text(encoding="utf-8", errors="replace")

def _extract_functions(content: str) -> list[str]:
    pattern = r"(?:Static\s+|User\s+|Main\s+)?Function\s+(\w+)"
    return re.findall(pattern, content, re.IGNORECASE)

def _extract_user_functions(content: str) -> list[str]:
    pattern = r"User\s+Function\s+(\w+)"
    return re.findall(pattern, content, re.IGNORECASE)

def _extract_tables(content: str) -> list[str]:
    tables = set()
    # DbSelectArea("XXX")
    tables.update(re.findall(r'DbSelectArea\s*\(\s*["\'](\w+)["\']\s*\)', content, re.IGNORECASE))
    # RetSqlName("XXX")
    tables.update(re.findall(r'RetSqlName\s*\(\s*["\'](\w+)["\']\s*\)', content, re.IGNORECASE))
    return sorted(tables)

def _extract_includes(content: str) -> list[str]:
    return re.findall(r'#Include\s+["\'](.+?)["\']', content, re.IGNORECASE)

def _extract_exec_autos(content: str) -> list[str]:
    return re.findall(r'MsExecAuto\s*\(.+?(MATA\d+)', content, re.IGNORECASE)

def _extract_point_of_entry(funcoes: list[str]) -> list[str]:
    pe_pattern = re.compile(r'^[A-Z]{2,3}\d{3}[A-Z]{3}$')
    known_pes = {"MT410GRV", "MT120GRV", "A010TOK", "A020TOK", "MT100LOK"}
    result = []
    for f in funcoes:
        if f.upper() in known_pes or pe_pattern.match(f.upper()):
            result.append(f)
    return result

MAX_CHUNK_CHARS = 4000  # ~1000 tokens
OVERLAP_CHARS = 400     # ~100 tokens

def _split_large_chunk(chunk: dict) -> list[dict]:
    """Split a chunk that exceeds MAX_CHUNK_CHARS into overlapping sub-chunks."""
    content = chunk["content"]
    if len(content) <= MAX_CHUNK_CHARS:
        return [chunk]
    sub_chunks = []
    start = 0
    part = 0
    while start < len(content):
        end = min(start + MAX_CHUNK_CHARS, len(content))
        sub_chunks.append({
            "id": f"{chunk['id']}_p{part}",
            "content": content[start:end],
            "funcao": chunk["funcao"],
        })
        start = end - OVERLAP_CHARS
        part += 1
    return sub_chunks

def _split_into_chunks(content: str, file_name: str) -> list[dict]:
    raw_chunks = []
    func_pattern = re.compile(
        r'((?:Static\s+|User\s+|Main\s+)?Function\s+(\w+))',
        re.IGNORECASE
    )
    matches = list(func_pattern.finditer(content))

    # Header chunk (everything before first function)
    if matches:
        header = content[:matches[0].start()].strip()
        if header:
            raw_chunks.append({"id": f"{file_name}::header", "content": header, "funcao": "_header"})

        # Function chunks
        for i, match in enumerate(matches):
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            func_content = content[start:end].strip()
            func_name = match.group(2)
            raw_chunks.append({"id": f"{file_name}::{func_name}", "content": func_content, "funcao": func_name})
    else:
        raw_chunks.append({"id": f"{file_name}::full", "content": content, "funcao": "_full"})

    # Enforce chunk size limits
    chunks = []
    for chunk in raw_chunks:
        chunks.extend(_split_large_chunk(chunk))

    return chunks

def parse_source(file_path: Path) -> dict:
    content = _read_file(file_path)
    funcoes = _extract_functions(content)
    return {
        "arquivo": file_path.name,
        "caminho": str(file_path),
        "funcoes": funcoes,
        "user_funcs": _extract_user_functions(content),
        "pontos_entrada": _extract_point_of_entry(funcoes),
        "tabelas_ref": _extract_tables(content),
        "includes": _extract_includes(content),
        "exec_autos": _extract_exec_autos(content),
        "chunks": _split_into_chunks(content, file_path.name),
        "hash": hashlib.md5(content.encode()).hexdigest(),
    }
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_parser_source.py -v`
Expected: All 6 tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/services/parser_source.py tests/test_parser_source.py tests/fixtures/sample.prw
git commit -m "feat: source file parser with regex extraction"
```

---

### Task 8: ChromaDB VectorStore

**Files:**
- Create: `backend/services/vectorstore.py`
- Create: `tests/test_vectorstore.py`

- [ ] **Step 1: Write tests**

```python
# tests/test_vectorstore.py
import pytest
from pathlib import Path
from backend.services.vectorstore import VectorStore

@pytest.fixture
def store(tmp_path):
    vs = VectorStore(tmp_path / "chroma")
    vs.initialize()
    return vs

def test_add_and_search_source(store):
    store.add_source_chunks("fontes_custom", [
        {"id": "XFAT001.prw::XFAT001", "content": "User Function XFAT001 pedido de venda faturamento", "funcao": "XFAT001", "arquivo": "XFAT001.prw", "modulo": "faturamento"}
    ])
    results = store.search("fontes_custom", "pedido de venda", n_results=1)
    assert len(results) == 1
    assert results[0]["id"] == "XFAT001.prw::XFAT001"

def test_delete_by_filter(store):
    store.add_source_chunks("knowledge_cliente", [
        {"id": "fat-1", "content": "Faturamento processo", "processo": "faturamento", "modulo": "faturamento"},
        {"id": "com-1", "content": "Compras processo", "processo": "compras", "modulo": "compras"},
    ])
    store.delete_by_filter("knowledge_cliente", {"processo": "faturamento"})
    results = store.search("knowledge_cliente", "processo", n_results=10)
    assert len(results) == 1
    assert results[0]["id"] == "com-1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_vectorstore.py -v`
Expected: FAIL

- [ ] **Step 3: Implement VectorStore**

```python
# backend/services/vectorstore.py
from pathlib import Path
import chromadb

class VectorStore:
    def __init__(self, persist_dir: Path):
        self.persist_dir = persist_dir
        self._client = None

    def initialize(self):
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(self.persist_dir))

    def _get_or_create(self, name: str):
        return self._client.get_or_create_collection(name=name)

    def add_source_chunks(self, collection_name: str, chunks: list[dict]):
        collection = self._get_or_create(collection_name)
        ids = [c["id"] for c in chunks]
        documents = [c["content"] for c in chunks]
        metadatas = [{k: v for k, v in c.items() if k not in ("id", "content")} for c in chunks]
        collection.add(ids=ids, documents=documents, metadatas=metadatas)

    def search(self, collection_name: str, query: str, n_results: int = 5, where: dict = None) -> list[dict]:
        collection = self._get_or_create(collection_name)
        kwargs = {"query_texts": [query], "n_results": n_results}
        if where:
            kwargs["where"] = where
        results = collection.query(**kwargs)
        output = []
        for i in range(len(results["ids"][0])):
            output.append({
                "id": results["ids"][0][i],
                "content": results["documents"][0][i],
                "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                "distance": results["distances"][0][i] if results["distances"] else 0,
            })
        return output

    def delete_by_filter(self, collection_name: str, where: dict):
        collection = self._get_or_create(collection_name)
        collection.delete(where=where)

    def reset_collection(self, collection_name: str):
        try:
            self._client.delete_collection(collection_name)
        except Exception:
            pass
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_vectorstore.py -v`
Expected: All 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/vectorstore.py tests/test_vectorstore.py
git commit -m "feat: ChromaDB vectorstore with search and delete"
```

---

## Chunk 4: LLM Integration + Ingestor

### Task 9: LLM Provider (LiteLLM)

**Files:**
- Create: `backend/services/llm.py`
- Create: `tests/test_llm.py`

- [ ] **Step 1: Write test (mock-based since we can't call real APIs in tests)**

```python
# tests/test_llm.py
import pytest
from unittest.mock import patch, MagicMock
from backend.services.llm import LLMService

def test_llm_service_init():
    svc = LLMService(provider="anthropic", model="claude-sonnet-4-20250514", api_key="sk-test")
    assert svc.model == "anthropic/claude-sonnet-4-20250514"

def test_llm_service_ollama_no_prefix():
    svc = LLMService(provider="ollama", model="llama3", api_key="")
    assert svc.model == "ollama/llama3"

@patch("backend.services.llm.completion")
def test_chat_returns_content(mock_completion):
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "Test response"
    mock_completion.return_value = mock_response

    svc = LLMService(provider="anthropic", model="claude-sonnet-4-20250514", api_key="sk-test")
    result = svc.chat([{"role": "user", "content": "hello"}])
    assert result == "Test response"

@patch("backend.services.llm.completion")
def test_classify_returns_dict(mock_completion):
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = '{"modulos": ["faturamento"], "gerar_doc": true}'
    mock_completion.return_value = mock_response

    svc = LLMService(provider="anthropic", model="claude-sonnet-4-20250514", api_key="sk-test")
    result = svc.classify("Como funciona o faturamento?")
    assert result["modulos"] == ["faturamento"]
    assert result["gerar_doc"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_llm.py -v`
Expected: FAIL

- [ ] **Step 3: Implement LLM service**

```python
# backend/services/llm.py
import json
from litellm import completion

CLASSIFY_PROMPT = """Analyze the user's question about a Protheus client environment.
Return a JSON object with:
- "modulos": list of related modules (compras, faturamento, financeiro, estoque, fiscal, pcp, rh, contabilidade)
- "gerar_doc": boolean, true if this question should generate/update a knowledge base document
- "slug": string, document slug if gerar_doc is true (e.g. "faturamento", "compras-aprovacao")
- "search_terms": list of keywords to search in source files and dictionary

Return ONLY valid JSON, no markdown."""

class LLMService:
    def __init__(self, provider: str, model: str, api_key: str):
        self.provider = provider
        self.api_key = api_key
        if provider == "ollama":
            self.model = f"ollama/{model}"
        elif provider == "anthropic":
            self.model = f"anthropic/{model}"
        elif provider == "openai":
            self.model = f"openai/{model}"
        else:
            self.model = model

    def _call(self, messages: list[dict], temperature: float = 0.3) -> str:
        kwargs = {"model": self.model, "messages": messages, "temperature": temperature}
        if self.api_key:
            kwargs["api_key"] = self.api_key
        response = completion(**kwargs)
        return response.choices[0].message.content

    def chat(self, messages: list[dict]) -> str:
        return self._call(messages, temperature=0.4)

    def chat_stream(self, messages: list[dict]):
        kwargs = {"model": self.model, "messages": messages, "temperature": 0.4, "stream": True}
        if self.api_key:
            kwargs["api_key"] = self.api_key
        response = completion(**kwargs)
        for chunk in response:
            delta = chunk.choices[0].delta
            if delta and delta.content:
                yield delta.content

    def classify(self, question: str) -> dict:
        messages = [
            {"role": "system", "content": CLASSIFY_PROMPT},
            {"role": "user", "content": question},
        ]
        result = self._call(messages, temperature=0.1)
        # Strip markdown fences if present
        result = result.strip()
        if result.startswith("```"):
            result = result.split("\n", 1)[1].rsplit("```", 1)[0]
        return json.loads(result)

    def generate_doc(self, context: str, processo: str, existing_doc: str = "") -> dict:
        action = "update" if existing_doc else "create"
        prompt = f"""You are a Protheus specialist. {'Update the existing document with new information.' if existing_doc else 'Create a new process document.'}

Process: {processo}
Context from client sources and dictionary:
{context}

{'Existing document to update:' + chr(10) + existing_doc if existing_doc else ''}

Generate TWO documents:
1. "humano": A human-readable markdown document describing the process step-by-step
2. "ia": A structured markdown document with YAML frontmatter for machine consumption

Return as JSON: {{"humano": "markdown content", "ia": "markdown with frontmatter"}}
Return ONLY valid JSON."""

        result = self._call([{"role": "user", "content": prompt}], temperature=0.3)
        result = result.strip()
        if result.startswith("```"):
            result = result.split("\n", 1)[1].rsplit("```", 1)[0]
        return json.loads(result)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_llm.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/llm.py tests/test_llm.py
git commit -m "feat: LLM service with LiteLLM multi-provider"
```

---

### Task 10: Ingestor Orchestrator

**Files:**
- Create: `backend/services/ingestor.py`
- Create: `tests/test_ingestor.py`
- Create: `templates/processos/mapa-modulos.json`

- [ ] **Step 1: Create mapa-modulos.json**

```json
{
  "compras":       { "tabelas": ["SC7","SC8","SA2","SCR","SCJ"], "rotinas": ["MATA120","MATA121","MATA103"] },
  "faturamento":   { "tabelas": ["SC5","SC6","SF2","SD2","SA1"], "rotinas": ["MATA410","MATA411","MATA460","MATA461"] },
  "financeiro":    { "tabelas": ["SE1","SE2","SE5","SA6","SEA"], "rotinas": ["FINA040","FINA050","FINA080"] },
  "estoque":       { "tabelas": ["SB1","SB2","SB5","SD1","SD3"], "rotinas": ["MATA240","MATA241","MATA250","MATA260"] },
  "fiscal":        { "tabelas": ["SF3","SF4","SFT","CDA","CDH"], "rotinas": ["MATA950","MATA953"] },
  "pcp":           { "tabelas": ["SC2","SG1","SG2","SD4","SHB"], "rotinas": ["MATA630","MATA650","MATA680"] },
  "rh":            { "tabelas": ["SRA","SRB","SRC","SRD","SRE"], "rotinas": ["GPEA010","GPEA020","GPEM020"] },
  "contabilidade": { "tabelas": ["CT1","CT2","CT5","CTS","CVD"], "rotinas": ["CTBA010","CTBA020","CTBA102"] }
}
```

- [ ] **Step 2: Write test for module detection**

```python
# tests/test_ingestor.py
import pytest
from pathlib import Path
from backend.services.ingestor import detect_module

def test_detect_module_by_tables():
    assert detect_module(["SC5", "SC6"], "XFAT001") == "faturamento"
    assert detect_module(["SC7", "SA2"], "XCOMP01") == "compras"

def test_detect_module_by_filename():
    assert detect_module([], "MATA410") == "faturamento"
    assert detect_module([], "FINA040") == "financeiro"

def test_detect_module_unknown():
    assert detect_module(["SZZ"], "XUTIL01") is None
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_ingestor.py -v`
Expected: FAIL

- [ ] **Step 4: Implement ingestor with module detection and orchestration**

```python
# backend/services/ingestor.py
import json
import asyncio
from pathlib import Path
from typing import Optional, AsyncGenerator
from backend.services.database import Database
from backend.services.parser_sx import parse_sx2, parse_sx3, parse_six, parse_sx7
from backend.services.parser_source import parse_source
from backend.services.vectorstore import VectorStore

MAPA_PATH = Path(__file__).parent.parent.parent / "templates" / "processos" / "mapa-modulos.json"

def _load_mapa():
    return json.loads(MAPA_PATH.read_text(encoding="utf-8"))

def detect_module(tabelas_ref: list[str], arquivo: str) -> Optional[str]:
    mapa = _load_mapa()
    # 1. Check filename against rotinas
    nome = Path(arquivo).stem.upper()
    for modulo, info in mapa.items():
        if nome in [r.upper() for r in info["rotinas"]]:
            return modulo
    # 2. Check tables
    if tabelas_ref:
        scores = {}
        for modulo, info in mapa.items():
            count = len(set(t.upper() for t in tabelas_ref) & set(t.upper() for t in info["tabelas"]))
            if count > 0:
                scores[modulo] = count
        if scores:
            return max(scores, key=scores.get)
    return None

class Ingestor:
    def __init__(self, db: Database, vectorstore: VectorStore):
        self.db = db
        self.vs = vectorstore

    async def run_fase1(self, csv_dir: Path) -> AsyncGenerator[dict, None]:
        """Parse CSVs and store in SQLite."""
        files = {"SX2": parse_sx2, "SX3": parse_sx3, "SIX": parse_six, "SX7": parse_sx7}
        for sx_name, parser_fn in files.items():
            csv_path = csv_dir / f"{sx_name}.csv"
            if not csv_path.exists():
                # Try lowercase
                csv_path = csv_dir / f"{sx_name.lower()}.csv"
            if not csv_path.exists():
                yield {"fase": 1, "item": sx_name, "status": "skipped", "msg": f"{sx_name}.csv not found"}
                continue
            try:
                rows = parser_fn(csv_path)
                self._store_sx(sx_name, rows)
                self.db.execute(
                    "INSERT OR REPLACE INTO ingest_progress (item, fase, status) VALUES (?, 1, 'done')",
                    (f"{sx_name}.csv",)
                )
                self.db.commit()
                yield {"fase": 1, "item": sx_name, "status": "done", "count": len(rows)}
            except Exception as e:
                self.db.execute(
                    "INSERT OR REPLACE INTO ingest_progress (item, fase, status, error_msg) VALUES (?, 1, 'error', ?)",
                    (f"{sx_name}.csv", str(e))
                )
                self.db.commit()
                yield {"fase": 1, "item": sx_name, "status": "error", "msg": str(e)}

    def _store_sx(self, sx_name: str, rows: list[dict]):
        if sx_name == "SX2":
            self.db.executemany(
                "INSERT OR REPLACE INTO tabelas (codigo, nome, modo, custom) VALUES (:codigo, :nome, :modo, :custom)", rows
            )
        elif sx_name == "SX3":
            self.db.executemany(
                "INSERT OR REPLACE INTO campos (tabela, campo, tipo, tamanho, decimal, titulo, descricao, validacao, inicializador, obrigatorio, custom) VALUES (:tabela, :campo, :tipo, :tamanho, :decimal, :titulo, :descricao, :validacao, :inicializador, :obrigatorio, :custom)", rows
            )
        elif sx_name == "SIX":
            self.db.executemany(
                "INSERT OR REPLACE INTO indices (tabela, indice, chave, descricao) VALUES (:tabela, :indice, :chave, :descricao)", rows
            )
        elif sx_name == "SX7":
            self.db.executemany(
                "INSERT OR REPLACE INTO gatilhos (campo_origem, sequencia, campo_destino, regra, tipo, tabela, custom) VALUES (:campo_origem, :sequencia, :campo_destino, :regra, :tipo, :tabela, :custom)", rows
            )

    async def run_fase2(self, fontes_custom: Path, fontes_padrao: Optional[Path] = None) -> AsyncGenerator[dict, None]:
        """Parse source files and index in ChromaDB."""
        for folder, tipo in [(fontes_custom, "custom"), (fontes_padrao, "padrao")]:
            if not folder or not folder.exists():
                continue
            collection = f"fontes_{tipo}"
            files = list(folder.glob("*.prw")) + list(folder.glob("*.tlpp"))
            for f in files:
                try:
                    parsed = parse_source(f)
                    modulo = detect_module(parsed["tabelas_ref"], parsed["arquivo"])
                    # Store in SQLite
                    self.db.execute(
                        "INSERT OR REPLACE INTO fontes (arquivo, caminho, tipo, modulo, funcoes, user_funcs, pontos_entrada, tabelas_ref, includes, hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (parsed["arquivo"], parsed["caminho"], tipo, modulo,
                         json.dumps(parsed["funcoes"]), json.dumps(parsed["user_funcs"]),
                         json.dumps(parsed["pontos_entrada"]), json.dumps(parsed["tabelas_ref"]),
                         json.dumps(parsed["includes"]), parsed["hash"])
                    )
                    self.db.commit()
                    # Index chunks in ChromaDB
                    chunks = []
                    for chunk in parsed["chunks"]:
                        chunks.append({
                            "id": chunk["id"],
                            "content": chunk["content"],
                            "funcao": chunk["funcao"],
                            "arquivo": parsed["arquivo"],
                            "modulo": modulo or "unknown",
                        })
                    if chunks:
                        self.vs.add_source_chunks(collection, chunks)
                    self.db.execute(
                        "INSERT OR REPLACE INTO ingest_progress (item, fase, status) VALUES (?, 2, 'done')",
                        (parsed["arquivo"],)
                    )
                    self.db.commit()
                    yield {"fase": 2, "item": parsed["arquivo"], "status": "done", "modulo": modulo}
                except Exception as e:
                    self.db.execute(
                        "INSERT OR REPLACE INTO ingest_progress (item, fase, status, error_msg) VALUES (?, 2, 'error', ?)",
                        (f.name, str(e))
                    )
                    self.db.commit()
                    yield {"fase": 2, "item": f.name, "status": "error", "msg": str(e)}

    def get_detected_modules(self) -> list[str]:
        """Returns modules detected from ingested sources and tables."""
        mapa = _load_mapa()
        detected = set()
        # From fontes
        rows = self.db.execute("SELECT DISTINCT modulo FROM fontes WHERE modulo IS NOT NULL").fetchall()
        for row in rows:
            detected.add(row[0])
        # From tabelas
        tabelas = [r[0] for r in self.db.execute("SELECT codigo FROM tabelas").fetchall()]
        for modulo, info in mapa.items():
            if set(t.upper() for t in tabelas) & set(t.upper() for t in info["tabelas"]):
                detected.add(modulo)
        return sorted(detected)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_ingestor.py -v`
Expected: All 3 tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/services/ingestor.py tests/test_ingestor.py templates/
git commit -m "feat: ingestor orchestrator with module detection"
```

---

## Chunk 4b: Fase 3 — LLM Analysis During Ingestion

### Task 10b: Fase 3 Implementation and Guardrails

**Files:**
- Modify: `backend/services/ingestor.py`
- Modify: `tests/test_ingestor.py`

- [ ] **Step 1: Write test for Fase 3**

```python
# Add to tests/test_ingestor.py
from unittest.mock import MagicMock, patch

def test_detected_modules_used_for_fase3():
    """Fase 3 should generate docs for each detected module."""
    # This is an integration-level test — mock LLM
    from backend.services.ingestor import Ingestor
    db = MagicMock()
    db.execute.return_value.fetchall.return_value = [("faturamento",)]
    vs = MagicMock()
    ingestor = Ingestor(db, vs)
    modules = ingestor.get_detected_modules()
    assert "faturamento" in modules or isinstance(modules, list)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ingestor.py::test_detected_modules_used_for_fase3 -v`
Expected: FAIL or PASS depending on mock setup

- [ ] **Step 3: Add run_fase3 to Ingestor**

Add to `backend/services/ingestor.py`:
```python
import asyncio
from backend.services.llm import LLMService
from backend.services.knowledge import KnowledgeService
from backend.services.doc_generator import save_doc

class Ingestor:
    # ... existing code ...

    async def run_fase3(
        self, llm: LLMService, knowledge_dir: Path,
        modules: list[str] = None, max_concurrent: int = 2
    ) -> AsyncGenerator[dict, None]:
        """LLM-driven analysis: generate client docs for each detected module."""
        if modules is None:
            modules = self.get_detected_modules()

        semaphore = asyncio.Semaphore(max_concurrent)
        ks = KnowledgeService(self.db)

        for modulo in modules:
            async with semaphore:
                try:
                    # Build context from dictionary + sources
                    context = ks.build_context_for_module(modulo)

                    # Add vector search results
                    source_results = self.vs.search("fontes_custom", modulo, n_results=10)
                    for r in source_results:
                        context += f"\n\nSource: {r['metadata'].get('arquivo', '')}\n{r['content']}"

                    # Generate docs via LLM (run in thread to not block event loop)
                    docs = await asyncio.to_thread(llm.generate_doc, context, modulo)

                    # Save docs
                    save_doc(knowledge_dir, modulo, "humano", docs.get("humano", ""))
                    save_doc(knowledge_dir, modulo, "ia", docs.get("ia", ""))

                    # Index in ChromaDB
                    for camada in ["humano", "ia"]:
                        content = docs.get(camada, "")
                        if content:
                            self.vs.add_source_chunks("knowledge_cliente", [{
                                "id": f"{modulo}_{camada}",
                                "content": content,
                                "processo": modulo,
                                "modulo": modulo,
                            }])

                    self.db.execute(
                        "INSERT OR REPLACE INTO ingest_progress (item, fase, status) VALUES (?, 3, 'done')",
                        (f"module_{modulo}",)
                    )
                    self.db.commit()
                    yield {"fase": 3, "item": modulo, "status": "done"}

                except Exception as e:
                    self.db.execute(
                        "INSERT OR REPLACE INTO ingest_progress (item, fase, status, error_msg) VALUES (?, 3, 'error', ?)",
                        (f"module_{modulo}", str(e))
                    )
                    self.db.commit()
                    yield {"fase": 3, "item": modulo, "status": "error", "msg": str(e)}

    def get_fase3_estimate(self) -> dict:
        """Returns module count and estimated LLM calls for Fase 3 confirmation."""
        modules = self.get_detected_modules()
        return {
            "modules": modules,
            "count": len(modules),
            "estimated_calls": len(modules) * 1,  # 1 call per module
        }
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_ingestor.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/ingestor.py tests/test_ingestor.py
git commit -m "feat: Fase 3 LLM analysis with semaphore and guardrails"
```

---

## Chunk 5: Knowledge Service + Doc Generator

### Task 11: Doc Generator

**Files:**
- Create: `backend/services/doc_generator.py`
- Create: `tests/test_doc_generator.py`

- [ ] **Step 1: Write test**

```python
# tests/test_doc_generator.py
import pytest
from pathlib import Path
from backend.services.doc_generator import save_doc, load_doc, list_docs

def test_save_and_load_humano(tmp_path):
    knowledge_dir = tmp_path / "knowledge" / "cliente"
    save_doc(knowledge_dir, "faturamento", "humano", "# Faturamento\nConteudo aqui")
    content = load_doc(knowledge_dir, "faturamento", "humano")
    assert "Faturamento" in content

def test_save_and_load_ia(tmp_path):
    knowledge_dir = tmp_path / "knowledge" / "cliente"
    save_doc(knowledge_dir, "faturamento", "ia", "---\nprocesso: faturamento\n---\nContexto")
    content = load_doc(knowledge_dir, "faturamento", "ia")
    assert "processo: faturamento" in content

def test_list_docs(tmp_path):
    knowledge_dir = tmp_path / "knowledge" / "cliente"
    save_doc(knowledge_dir, "faturamento", "humano", "# Fat")
    save_doc(knowledge_dir, "compras", "humano", "# Comp")
    docs = list_docs(knowledge_dir, "humano")
    assert len(docs) == 2
    slugs = [d["slug"] for d in docs]
    assert "faturamento" in slugs
    assert "compras" in slugs

def test_load_missing_doc(tmp_path):
    knowledge_dir = tmp_path / "knowledge" / "cliente"
    assert load_doc(knowledge_dir, "naoexiste", "humano") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_doc_generator.py -v`
Expected: FAIL

- [ ] **Step 3: Implement doc generator**

```python
# backend/services/doc_generator.py
from pathlib import Path
from typing import Optional

def save_doc(knowledge_dir: Path, slug: str, camada: str, content: str):
    dir_path = knowledge_dir / camada
    dir_path.mkdir(parents=True, exist_ok=True)
    file_path = dir_path / f"{slug}.md"
    file_path.write_text(content, encoding="utf-8")

def load_doc(knowledge_dir: Path, slug: str, camada: str) -> Optional[str]:
    file_path = knowledge_dir / camada / f"{slug}.md"
    if not file_path.exists():
        return None
    return file_path.read_text(encoding="utf-8")

def list_docs(knowledge_dir: Path, camada: str) -> list[dict]:
    dir_path = knowledge_dir / camada
    if not dir_path.exists():
        return []
    result = []
    for f in sorted(dir_path.glob("*.md")):
        result.append({
            "slug": f.stem,
            "filename": f.name,
            "size": f.stat().st_size,
        })
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_doc_generator.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/doc_generator.py tests/test_doc_generator.py
git commit -m "feat: doc generator for knowledge base markdown files"
```

---

### Task 12: Knowledge Service (Query Orchestrator)

**Files:**
- Create: `backend/services/knowledge.py`
- Create: `tests/test_knowledge.py`

- [ ] **Step 1: Write test**

```python
# tests/test_knowledge.py
import pytest
from pathlib import Path
from backend.services.database import Database
from backend.services.knowledge import KnowledgeService

@pytest.fixture
def db(tmp_path):
    d = Database(tmp_path / "test.db")
    d.initialize()
    # Insert test data
    d.execute("INSERT INTO tabelas VALUES ('SC5', 'Ped.Venda', 'C', 0)")
    d.execute("INSERT INTO campos VALUES ('SC5', 'C5_NUM', 'C', 6, 0, 'Numero', 'Numero Pedido', '', '', 0, 0)")
    d.execute("INSERT INTO campos VALUES ('SC5', 'C5_XAPROV', 'C', 1, 0, 'Aprov', 'Aprovacao Custom', '', '', 0, 1)")
    d.commit()
    return d

def test_get_table_info(db):
    ks = KnowledgeService(db)
    info = ks.get_table_info("SC5")
    assert info["codigo"] == "SC5"
    assert len(info["campos"]) == 2
    assert len(info["campos_custom"]) == 1
    assert info["campos_custom"][0]["campo"] == "C5_XAPROV"

def test_get_custom_summary(db):
    ks = KnowledgeService(db)
    summary = ks.get_custom_summary()
    assert summary["campos_custom"] == 1
    assert summary["tabelas_custom"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_knowledge.py -v`
Expected: FAIL

- [ ] **Step 3: Implement knowledge service**

```python
# backend/services/knowledge.py
import json
from backend.services.database import Database
from typing import Optional

class KnowledgeService:
    def __init__(self, db: Database):
        self.db = db

    def get_table_info(self, tabela: str) -> Optional[dict]:
        row = self.db.execute("SELECT * FROM tabelas WHERE codigo = ?", (tabela,)).fetchone()
        if not row:
            return None
        campos = self.db.execute(
            "SELECT campo, tipo, tamanho, titulo, descricao, custom FROM campos WHERE tabela = ?",
            (tabela,)
        ).fetchall()
        indices = self.db.execute(
            "SELECT indice, chave, descricao FROM indices WHERE tabela = ?",
            (tabela,)
        ).fetchall()
        gatilhos = self.db.execute(
            "SELECT campo_origem, campo_destino, regra, custom FROM gatilhos WHERE tabela = ?",
            (tabela,)
        ).fetchall()
        return {
            "codigo": row[0],
            "nome": row[1],
            "modo": row[2],
            "custom": bool(row[3]),
            "campos": [{"campo": c[0], "tipo": c[1], "tamanho": c[2], "titulo": c[3], "descricao": c[4], "custom": bool(c[5])} for c in campos],
            "campos_custom": [{"campo": c[0], "tipo": c[1], "tamanho": c[2], "titulo": c[3], "descricao": c[4]} for c in campos if c[5]],
            "indices": [{"indice": i[0], "chave": i[1], "descricao": i[2]} for i in indices],
            "gatilhos": [{"campo_origem": g[0], "campo_destino": g[1], "regra": g[2], "custom": bool(g[3])} for g in gatilhos],
            "gatilhos_custom": [{"campo_origem": g[0], "campo_destino": g[1], "regra": g[2]} for g in gatilhos if g[3]],
        }

    def get_tables_for_module(self, modulo: str) -> list[dict]:
        rows = self.db.execute(
            "SELECT DISTINCT tabelas_ref FROM fontes WHERE modulo = ?", (modulo,)
        ).fetchall()
        tables = set()
        for row in rows:
            if row[0]:
                tables.update(json.loads(row[0]))
        return [self.get_table_info(t) for t in sorted(tables) if self.get_table_info(t)]

    def get_fontes_for_module(self, modulo: str) -> list[dict]:
        rows = self.db.execute(
            "SELECT arquivo, tipo, funcoes, user_funcs, pontos_entrada, tabelas_ref FROM fontes WHERE modulo = ?",
            (modulo,)
        ).fetchall()
        return [{
            "arquivo": r[0], "tipo": r[1],
            "funcoes": json.loads(r[2]) if r[2] else [],
            "user_funcs": json.loads(r[3]) if r[3] else [],
            "pontos_entrada": json.loads(r[4]) if r[4] else [],
            "tabelas_ref": json.loads(r[5]) if r[5] else [],
        } for r in rows]

    def get_custom_summary(self) -> dict:
        campos_custom = self.db.execute("SELECT COUNT(*) FROM campos WHERE custom = 1").fetchone()[0]
        tabelas_custom = self.db.execute("SELECT COUNT(*) FROM tabelas WHERE custom = 1").fetchone()[0]
        gatilhos_custom = self.db.execute("SELECT COUNT(*) FROM gatilhos WHERE custom = 1").fetchone()[0]
        fontes_custom = self.db.execute("SELECT COUNT(*) FROM fontes WHERE tipo = 'custom'").fetchone()[0]
        return {
            "campos_custom": campos_custom,
            "tabelas_custom": tabelas_custom,
            "gatilhos_custom": gatilhos_custom,
            "fontes_custom": fontes_custom,
        }

    def build_context_for_module(self, modulo: str) -> str:
        """Build a text context about a module for LLM consumption."""
        lines = [f"## Module: {modulo}\n"]
        tables = self.get_tables_for_module(modulo)
        if tables:
            lines.append("### Tables")
            for t in tables:
                lines.append(f"\n**{t['codigo']}** — {t['nome']}")
                if t["campos_custom"]:
                    lines.append("Custom fields:")
                    for c in t["campos_custom"]:
                        lines.append(f"  - {c['campo']} ({c['tipo']}) — {c['titulo']}")
                if t["gatilhos_custom"]:
                    lines.append("Custom triggers:")
                    for g in t["gatilhos_custom"]:
                        lines.append(f"  - {g['campo_origem']} → {g['campo_destino']}: {g['regra']}")

        fontes = self.get_fontes_for_module(modulo)
        if fontes:
            lines.append("\n### Custom Sources")
            for f in fontes:
                if f["tipo"] == "custom":
                    lines.append(f"\n**{f['arquivo']}**")
                    if f["funcoes"]:
                        lines.append(f"  Functions: {', '.join(f['funcoes'])}")
                    if f["pontos_entrada"]:
                        lines.append(f"  Entry Points: {', '.join(f['pontos_entrada'])}")
        return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_knowledge.py -v`
Expected: All 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/knowledge.py tests/test_knowledge.py
git commit -m "feat: knowledge service with query orchestration"
```

---

## Chunk 6: API Routers

### Task 13: Setup Router

**Files:**
- Create: `backend/routers/setup.py`
- Modify: `backend/app.py`

- [ ] **Step 1: Implement setup router**

```python
# backend/routers/setup.py
import asyncio
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
from backend.services.config import AppConfig, save_config, load_config
from backend.services.database import Database
from backend.services.vectorstore import VectorStore
from backend.services.ingestor import Ingestor
from backend.services.llm import LLMService

router = APIRouter(prefix="/api", tags=["setup"])

WORKSPACE = Path("workspace")
CONFIG_PATH = Path("config.json")

class SetupRequest(BaseModel):
    cliente: str
    paths: dict
    llm: dict
    skip_fase3: bool = False  # User can skip LLM analysis

_ingest_progress: list[dict] = []
_ingest_running = False

def is_ingesting() -> bool:
    return _ingest_running

@router.post("/setup")
async def setup(req: SetupRequest):
    global _ingest_running
    if _ingest_running:
        raise HTTPException(400, "Ingestion already running")

    # Validate paths
    csv_path = Path(req.paths.get("csv_dicionario", ""))
    fontes_path = Path(req.paths.get("fontes_custom", ""))
    if not csv_path.exists():
        raise HTTPException(400, f"CSV directory not found: {csv_path}")
    if not fontes_path.exists():
        raise HTTPException(400, f"Custom sources directory not found: {fontes_path}")

    config = AppConfig(**req.model_dump())
    save_config(config, CONFIG_PATH)

    # Initialize workspace
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    (WORKSPACE / "knowledge" / "padrao" / "humano").mkdir(parents=True, exist_ok=True)
    (WORKSPACE / "knowledge" / "padrao" / "ia").mkdir(parents=True, exist_ok=True)
    (WORKSPACE / "knowledge" / "cliente" / "humano").mkdir(parents=True, exist_ok=True)
    (WORKSPACE / "knowledge" / "cliente" / "ia").mkdir(parents=True, exist_ok=True)
    (WORKSPACE / "db").mkdir(parents=True, exist_ok=True)

    # Copy standard process templates
    templates_dir = Path("templates") / "processos"
    if templates_dir.exists():
        for md in templates_dir.glob("*.md"):
            dest = WORKSPACE / "knowledge" / "padrao" / "humano" / md.name
            dest.write_text(md.read_text(encoding="utf-8"), encoding="utf-8")

    # Start ingestion in background
    _ingest_progress.clear()
    _ingest_running = True

    db = Database(WORKSPACE / "db" / "extrairpo.db")
    db.initialize()
    vs = VectorStore(WORKSPACE / "db" / "chroma")
    vs.initialize()
    ingestor = Ingestor(db, vs)

    async def run_ingestion():
        global _ingest_running
        try:
            # Fase 1: Parse CSVs
            async for progress in ingestor.run_fase1(csv_path):
                _ingest_progress.append(progress)
            # Fase 2: Index sources
            fontes_padrao = Path(req.paths.get("fontes_padrao", "")) if req.paths.get("fontes_padrao") else None
            async for progress in ingestor.run_fase2(fontes_path, fontes_padrao):
                _ingest_progress.append(progress)
            # Fase 3: LLM analysis (optional)
            modules = ingestor.get_detected_modules()
            estimate = ingestor.get_fase3_estimate()
            _ingest_progress.append({"fase": 3, "status": "modules_detected", **estimate})
            if not req.skip_fase3 and modules:
                llm = LLMService(**req.llm)
                knowledge_dir = WORKSPACE / "knowledge" / "cliente"
                async for progress in ingestor.run_fase3(llm, knowledge_dir, modules):
                    _ingest_progress.append(progress)
        finally:
            _ingest_running = False
            db.close()

    asyncio.create_task(run_ingestion())
    return {"status": "ingestion_started"}

@router.get("/setup/progress")
async def progress():
    async def event_generator():
        sent = 0
        while True:
            while sent < len(_ingest_progress):
                yield {"event": "progress", "data": json.dumps(_ingest_progress[sent])}
                sent += 1
            if not _ingest_running and sent >= len(_ingest_progress):
                yield {"event": "done", "data": "{}"}
                break
            await asyncio.sleep(0.3)
    return EventSourceResponse(event_generator())
```

- [ ] **Step 2: Register router in app.py**

Update `backend/app.py` to add:
```python
from backend.routers.setup import router as setup_router

app.include_router(setup_router)
```

- [ ] **Step 3: Test manually**

Run: `python run.py`
Hit `POST /api/setup` with test data via browser/curl. Verify ingestion starts and `/api/setup/progress` streams events.

- [ ] **Step 4: Commit**

```bash
git add backend/routers/setup.py backend/app.py
git commit -m "feat: setup router with ingestion orchestration"
```

---

### Task 14: Chat Router

**Files:**
- Create: `backend/routers/chat.py`
- Modify: `backend/app.py`

- [ ] **Step 1: Implement chat router**

```python
# backend/routers/chat.py
import json
import asyncio
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
from backend.services.config import load_config
from backend.services.database import Database
from backend.services.vectorstore import VectorStore
from backend.services.knowledge import KnowledgeService
from backend.services.llm import LLMService
from backend.services.doc_generator import save_doc, load_doc

router = APIRouter(prefix="/api", tags=["chat"])

WORKSPACE = Path("workspace")
CONFIG_PATH = Path("config.json")

class ChatRequest(BaseModel):
    message: str

def _get_services():
    config = load_config(CONFIG_PATH)
    if not config:
        raise HTTPException(400, "Setup not completed")
    db = Database(WORKSPACE / "db" / "extrairpo.db")
    db.initialize()
    vs = VectorStore(WORKSPACE / "db" / "chroma")
    vs.initialize()
    ks = KnowledgeService(db)
    llm = LLMService(**config.llm)
    return db, vs, ks, llm

@router.post("/chat")
async def chat(req: ChatRequest):
    db, vs, ks, llm = _get_services()

    try:
        # 1. Classify the question
        classification = llm.classify(req.message)
        modulos = classification.get("modulos", [])
        gerar_doc = classification.get("gerar_doc", False)
        slug = classification.get("slug", "")
        search_terms = classification.get("search_terms", [])

        # 2. Gather context
        context_parts = []

        # Search ChromaDB
        search_query = " ".join(search_terms) if search_terms else req.message
        source_results = vs.search("fontes_custom", search_query, n_results=5)
        sources_meta = {"tabelas": [], "fontes": [], "docs": []}

        for r in source_results:
            context_parts.append(f"Source: {r['metadata'].get('arquivo', '')}\n{r['content']}")
            if r["metadata"].get("arquivo"):
                sources_meta["fontes"].append(r["metadata"]["arquivo"])

        # SQLite context per module
        for modulo in modulos[:2]:
            module_context = ks.build_context_for_module(modulo)
            if module_context:
                context_parts.append(module_context)
            tables = ks.get_tables_for_module(modulo)
            sources_meta["tabelas"].extend([t["codigo"] for t in tables])

        # Existing knowledge
        knowledge_dir = WORKSPACE / "knowledge" / "cliente"
        for modulo in modulos[:2]:
            existing = load_doc(knowledge_dir, modulo, "ia")
            if existing:
                context_parts.append(f"Existing knowledge:\n{existing}")
                sources_meta["docs"].append(f"{modulo}.md")

        # Deduplicate
        sources_meta["tabelas"] = sorted(set(sources_meta["tabelas"]))
        sources_meta["fontes"] = sorted(set(sources_meta["fontes"]))

        # 3. Build messages
        system_prompt = """You are an expert Protheus ADVPL/TLPP analyst.
You are analyzing a specific client's Protheus environment.
Answer questions based on the provided context from the client's source files, data dictionary, and existing knowledge base.
Always be specific about what is standard Protheus vs. what is customized by this client.
Answer in Portuguese (Brazil)."""

        context = "\n\n".join(context_parts) if context_parts else "No specific context found."

        # Load recent chat history for conversational context (last 10 messages)
        history_rows = db.execute(
            "SELECT role, content FROM chat_history ORDER BY id DESC LIMIT 10"
        ).fetchall()
        history_messages = [{"role": r[0], "content": r[1]} for r in reversed(history_rows)]

        messages = [
            {"role": "system", "content": system_prompt + f"\n\nContext from client environment:\n{context}"},
        ] + history_messages + [
            {"role": "user", "content": req.message},
        ]

        # 4. Stream response
        async def event_generator():
            # Send sources first
            yield {"event": "sources", "data": json.dumps(sources_meta)}

            # Stream LLM response
            full_response = ""
            for token in llm.chat_stream(messages):
                full_response += token
                yield {"event": "token", "data": json.dumps({"content": token})}

            # Save to chat history
            db.execute(
                "INSERT INTO chat_history (role, content) VALUES ('user', ?)",
                (req.message,)
            )
            db.execute(
                "INSERT INTO chat_history (role, content, sources, doc_updated) VALUES ('assistant', ?, ?, ?)",
                (full_response, json.dumps(sources_meta), slug if gerar_doc else None)
            )
            db.commit()

            # 5. Async doc generation
            if gerar_doc and slug:
                try:
                    existing_humano = load_doc(knowledge_dir, slug, "humano") or ""
                    doc_context = f"{context}\n\nChat response:\n{full_response}"
                    docs = llm.generate_doc(doc_context, slug, existing_humano)
                    save_doc(knowledge_dir, slug, "humano", docs.get("humano", ""))
                    save_doc(knowledge_dir, slug, "ia", docs.get("ia", ""))
                    # Index in ChromaDB for future semantic search
                    vs.delete_by_filter("knowledge_cliente", {"processo": slug})
                    for camada in ["humano", "ia"]:
                        content = docs.get(camada, "")
                        if content:
                            vs.add_source_chunks("knowledge_cliente", [{
                                "id": f"{slug}_{camada}",
                                "content": content,
                                "processo": slug,
                                "modulo": slug,
                            }])
                    yield {"event": "doc_updated", "data": json.dumps({"slug": slug, "action": "updated" if existing_humano else "created"})}
                except Exception:
                    pass  # Doc generation failure should not break chat

            yield {"event": "done", "data": "{}"}

        return EventSourceResponse(event_generator())
    finally:
        db.close()

@router.get("/chat/history")
async def history():
    db = Database(WORKSPACE / "db" / "extrairpo.db")
    db.initialize()
    try:
        rows = db.execute(
            "SELECT id, role, content, sources, doc_updated, created_at FROM chat_history ORDER BY id"
        ).fetchall()
        return [{"id": r[0], "role": r[1], "content": r[2], "sources": json.loads(r[3]) if r[3] else None, "doc_updated": r[4], "created_at": r[5]} for r in rows]
    finally:
        db.close()
```

- [ ] **Step 2: Register router in app.py**

Add to `backend/app.py`:
```python
from backend.routers.chat import router as chat_router
app.include_router(chat_router)
```

- [ ] **Step 3: Commit**

```bash
git add backend/routers/chat.py backend/app.py
git commit -m "feat: chat router with SSE streaming and doc generation"
```

---

### Task 15: Docs Router

**Files:**
- Create: `backend/routers/docs.py`
- Modify: `backend/app.py`

- [ ] **Step 1: Implement docs router**

```python
# backend/routers/docs.py
import json
import shutil
import io
import zipfile
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from backend.services.config import load_config, save_config
from backend.services.doc_generator import list_docs, load_doc

router = APIRouter(prefix="/api", tags=["docs"])

WORKSPACE = Path("workspace")
CONFIG_PATH = Path("config.json")

@router.get("/docs/padrao")
async def list_padrao():
    return list_docs(WORKSPACE / "knowledge" / "padrao", "humano")

@router.get("/docs/padrao/{slug}")
async def get_padrao(slug: str):
    content = load_doc(WORKSPACE / "knowledge" / "padrao", slug, "humano")
    if content is None:
        raise HTTPException(404, "Document not found")
    return {"slug": slug, "content": content}

@router.get("/docs/cliente")
async def list_cliente():
    humano = list_docs(WORKSPACE / "knowledge" / "cliente", "humano")
    ia = list_docs(WORKSPACE / "knowledge" / "cliente", "ia")
    return {"humano": humano, "ia": ia}

@router.get("/docs/cliente/{tipo}/{slug}")
async def get_cliente(tipo: str, slug: str):
    if tipo not in ("humano", "ia"):
        raise HTTPException(400, "tipo must be 'humano' or 'ia'")
    content = load_doc(WORKSPACE / "knowledge" / "cliente", slug, tipo)
    if content is None:
        raise HTTPException(404, "Document not found")
    return {"slug": slug, "tipo": tipo, "content": content}

@router.post("/docs/cliente/{slug}/regenerar")
async def regenerar(slug: str):
    from backend.services.database import Database
    from backend.services.vectorstore import VectorStore
    from backend.services.knowledge import KnowledgeService
    from backend.services.llm import LLMService
    from backend.services.doc_generator import save_doc

    config = load_config(CONFIG_PATH)
    if not config:
        raise HTTPException(400, "Setup not completed")

    db = Database(WORKSPACE / "db" / "extrairpo.db")
    db.initialize()
    vs = VectorStore(WORKSPACE / "db" / "chroma")
    vs.initialize()
    ks = KnowledgeService(db)
    llm = LLMService(**config.llm)

    try:
        context = ks.build_context_for_module(slug)
        source_results = vs.search("fontes_custom", slug, n_results=10)
        for r in source_results:
            context += f"\n\nSource: {r['metadata'].get('arquivo', '')}\n{r['content']}"

        # Delete old knowledge chunks
        vs.delete_by_filter("knowledge_cliente", {"processo": slug})

        docs = llm.generate_doc(context, slug)
        save_doc(WORKSPACE / "knowledge" / "cliente", slug, "humano", docs.get("humano", ""))
        save_doc(WORKSPACE / "knowledge" / "cliente", slug, "ia", docs.get("ia", ""))

        # Re-index in ChromaDB
        for camada in ["humano", "ia"]:
            content = docs.get(camada, "")
            if content:
                vs.add_source_chunks("knowledge_cliente", [{
                    "id": f"{slug}_{camada}",
                    "content": content,
                    "processo": slug,
                    "modulo": slug,
                }])

        return {"status": "regenerated", "slug": slug}
    finally:
        db.close()

@router.get("/config")
async def get_config():
    config = load_config(CONFIG_PATH)
    if not config:
        return {"status": "not_configured"}
    safe = config.model_dump()
    safe["llm"]["api_key"] = "***"  # mask
    return safe

@router.put("/config")
async def update_config(data: dict):
    config = load_config(CONFIG_PATH)
    if not config:
        raise HTTPException(400, "Setup not completed")
    updated = config.model_dump()
    if "llm" in data:
        for k, v in data["llm"].items():
            if v and v != "***":
                updated["llm"][k] = v
    if "paths" in data:
        updated["paths"].update(data["paths"])
    from backend.services.config import AppConfig
    save_config(AppConfig(**updated), CONFIG_PATH)
    return {"status": "updated"}

@router.post("/config/limpar")
async def limpar():
    # Export workspace as ZIP for download before deletion
    knowledge_dir = WORKSPACE / "knowledge"
    if knowledge_dir.exists():
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in knowledge_dir.rglob("*"):
                if f.is_file():
                    zf.write(f, f.relative_to(WORKSPACE))
        buffer.seek(0)
        # Delete workspace
        shutil.rmtree(WORKSPACE, ignore_errors=True)
        if CONFIG_PATH.exists():
            CONFIG_PATH.unlink()
        return StreamingResponse(buffer, media_type="application/zip",
                                 headers={"Content-Disposition": "attachment; filename=workspace_backup.zip"})

    shutil.rmtree(WORKSPACE, ignore_errors=True)
    if CONFIG_PATH.exists():
        CONFIG_PATH.unlink()
    return {"status": "cleaned"}
```

- [ ] **Step 2: Update app.py — register router and status endpoint**

```python
# Updated backend/app.py
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from backend.routers.setup import router as setup_router, is_ingesting
from backend.routers.chat import router as chat_router
from backend.routers.docs import router as docs_router

app = FastAPI(title="ExtraiRPO", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(setup_router)
app.include_router(chat_router)
app.include_router(docs_router)

CONFIG_PATH = Path("config.json")

@app.get("/api/status")
async def status():
    if not CONFIG_PATH.exists():
        return {"status": "setup_pending"}
    if is_ingesting():
        return {"status": "ingesting"}
    workspace_db = Path("workspace/db/extrairpo.db")
    if not workspace_db.exists():
        return {"status": "setup_pending"}
    return {"status": "ready"}

frontend_dist = Path("frontend/dist")
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
```

- [ ] **Step 3: Commit**

```bash
git add backend/routers/docs.py backend/app.py
git commit -m "feat: docs router with CRUD, regenerate, config, and cleanup"
```

---

## Chunk 7: Frontend (Vue 3)

### Task 16: Vue 3 Project Setup

**Files:**
- Create: `frontend/` (Vue 3 + Vite project)

- [ ] **Step 1: Scaffold Vue project**

Run: `cd d:/IA/Projetos/Protheus && npm create vite@latest frontend -- --template vue`
Expected: Vue project created

- [ ] **Step 2: Install dependencies**

Run: `cd frontend && npm install && npm install marked axios`
Expected: Dependencies installed

- [ ] **Step 3: Verify dev server works**

Run: `cd frontend && npm run dev`
Expected: Vite dev server starts

- [ ] **Step 4: Commit**

```bash
git add frontend/
git commit -m "feat: Vue 3 + Vite frontend scaffold"
```

---

### Task 17: Frontend — Layout and Router

**Files:**
- Modify: `frontend/src/App.vue`
- Create: `frontend/src/router.js`
- Create: `frontend/src/views/SetupView.vue`
- Create: `frontend/src/views/ChatView.vue`
- Create: `frontend/src/views/PadraoView.vue`
- Create: `frontend/src/views/ClienteView.vue`
- Create: `frontend/src/views/ConfigView.vue`

- [ ] **Step 1: Install vue-router**

Run: `cd frontend && npm install vue-router@4`

- [ ] **Step 2: Create router.js**

```javascript
// frontend/src/router.js
import { createRouter, createWebHistory } from 'vue-router'
import SetupView from './views/SetupView.vue'
import ChatView from './views/ChatView.vue'
import PadraoView from './views/PadraoView.vue'
import ClienteView from './views/ClienteView.vue'
import ConfigView from './views/ConfigView.vue'

const routes = [
  { path: '/', redirect: '/setup' },
  { path: '/setup', component: SetupView },
  { path: '/chat', component: ChatView },
  { path: '/padrao', component: PadraoView },
  { path: '/cliente', component: ClienteView },
  { path: '/config', component: ConfigView },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
```

- [ ] **Step 3: Create App.vue with sidebar layout**

```vue
<!-- frontend/src/App.vue -->
<template>
  <div class="app">
    <nav class="sidebar">
      <div class="logo">ExtraiRPO</div>
      <router-link to="/setup">Setup</router-link>
      <router-link to="/chat">Chat</router-link>
      <router-link to="/padrao">Base Padrão</router-link>
      <router-link to="/cliente">Base Cliente</router-link>
      <router-link to="/config">Config</router-link>
    </nav>
    <main class="content">
      <router-view />
    </main>
  </div>
</template>

<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }
.app { display: flex; height: 100vh; }
.sidebar {
  width: 200px; background: #1a1a2e; color: white;
  display: flex; flex-direction: column; padding: 1rem;
}
.sidebar .logo { font-size: 1.3rem; font-weight: bold; margin-bottom: 2rem; color: #e94560; }
.sidebar a {
  color: #ccc; text-decoration: none; padding: 0.6rem 0.8rem;
  border-radius: 6px; margin-bottom: 0.3rem;
}
.sidebar a:hover, .sidebar a.router-link-active { background: #16213e; color: white; }
.content { flex: 1; overflow-y: auto; padding: 1.5rem; background: #f5f5f5; }
</style>
```

- [ ] **Step 4: Update main.js**

```javascript
// frontend/src/main.js
import { createApp } from 'vue'
import App from './App.vue'
import router from './router'

createApp(App).use(router).mount('#app')
```

- [ ] **Step 5: Create placeholder views**

Create each view (`SetupView.vue`, `ChatView.vue`, `PadraoView.vue`, `ClienteView.vue`, `ConfigView.vue`) as simple placeholders with `<template><div><h1>Page Name</h1></div></template>`

- [ ] **Step 6: Verify routing works**

Run: `cd frontend && npm run dev`
Expected: Sidebar navigates between views

- [ ] **Step 7: Commit**

```bash
git add frontend/src/
git commit -m "feat: frontend layout with sidebar and vue-router"
```

---

### Task 18: Frontend — Setup View

**Files:**
- Modify: `frontend/src/views/SetupView.vue`
- Create: `frontend/src/api.js`

- [ ] **Step 1: Create API helper**

```javascript
// frontend/src/api.js
import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

export default api
```

- [ ] **Step 2: Implement SetupView**

```vue
<!-- frontend/src/views/SetupView.vue -->
<template>
  <div class="setup">
    <h1>Setup — Novo Cliente</h1>
    <form @submit.prevent="startIngestion" v-if="!ingesting">
      <label>Nome do Cliente
        <input v-model="form.cliente" required />
      </label>
      <label>Pasta CSVs Dicionário
        <input v-model="form.csv_dicionario" placeholder="C:/Cliente/dicionario" required />
      </label>
      <label>Pasta Fontes Customizados
        <input v-model="form.fontes_custom" placeholder="C:/Cliente/fontes" required />
      </label>
      <label>Pasta Fontes Padrão (opcional)
        <input v-model="form.fontes_padrao" placeholder="C:/Protheus/fontes_padrao" />
      </label>
      <label>Provider IA
        <select v-model="form.provider">
          <option value="anthropic">Anthropic (Claude)</option>
          <option value="openai">OpenAI (GPT)</option>
          <option value="ollama">Ollama (Local)</option>
        </select>
      </label>
      <label>Modelo
        <input v-model="form.model" placeholder="claude-sonnet-4-20250514" />
      </label>
      <label>API Key
        <input v-model="form.api_key" type="password" :placeholder="form.provider === 'ollama' ? 'Não necessário' : 'sk-...'" />
      </label>
      <button type="submit">Iniciar</button>
      <p v-if="error" class="error">{{ error }}</p>
    </form>

    <div v-if="ingesting" class="progress">
      <h2>Ingestão em andamento...</h2>
      <div v-for="(item, i) in progressItems" :key="i" class="progress-item">
        <span :class="item.status">{{ item.status }}</span>
        {{ item.item || item.msg || '' }}
        <small v-if="item.count">{{ item.count }} registros</small>
      </div>
      <p v-if="done">Pronto! Redirecionando para o Chat...</p>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api'

const router = useRouter()
const form = ref({
  cliente: '', csv_dicionario: '', fontes_custom: '', fontes_padrao: '',
  provider: 'anthropic', model: 'claude-sonnet-4-20250514', api_key: ''
})
const ingesting = ref(false)
const progressItems = ref([])
const done = ref(false)
const error = ref('')

onMounted(async () => {
  try {
    const { data } = await api.get('/status')
    if (data.status === 'ready') router.push('/chat')
  } catch {}
})

async function startIngestion() {
  error.value = ''
  try {
    await api.post('/setup', {
      cliente: form.value.cliente,
      paths: {
        csv_dicionario: form.value.csv_dicionario,
        fontes_custom: form.value.fontes_custom,
        fontes_padrao: form.value.fontes_padrao || undefined,
      },
      llm: {
        provider: form.value.provider,
        model: form.value.model,
        api_key: form.value.api_key,
      }
    })
    ingesting.value = true
    const es = new EventSource('/api/setup/progress')
    es.addEventListener('progress', (e) => { progressItems.value.push(JSON.parse(e.data)) })
    es.addEventListener('done', () => {
      es.close()
      done.value = true
      setTimeout(() => router.push('/chat'), 1500)
    })
  } catch (e) {
    error.value = e.response?.data?.detail || 'Erro ao iniciar'
  }
}
</script>

<style scoped>
.setup { max-width: 500px; }
label { display: block; margin-bottom: 1rem; font-weight: 600; }
input, select { display: block; width: 100%; padding: 0.5rem; margin-top: 0.3rem; border: 1px solid #ccc; border-radius: 4px; }
button { background: #e94560; color: white; border: none; padding: 0.8rem 2rem; border-radius: 6px; cursor: pointer; font-size: 1rem; }
button:hover { background: #c73e54; }
.error { color: red; margin-top: 1rem; }
.progress-item { padding: 0.3rem 0; }
.done { color: green; font-weight: bold; }
.error { color: red; }
.skipped { color: orange; }
</style>
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/
git commit -m "feat: setup view with ingestion progress"
```

---

### Task 19: Frontend — Chat View

**Files:**
- Modify: `frontend/src/views/ChatView.vue`

- [ ] **Step 1: Implement ChatView with SSE streaming**

```vue
<!-- frontend/src/views/ChatView.vue -->
<template>
  <div class="chat-layout">
    <div class="chat-main">
      <div class="messages" ref="messagesEl">
        <div v-for="(msg, i) in messages" :key="i" :class="['message', msg.role]">
          <div class="bubble" v-html="msg.role === 'assistant' ? renderMd(msg.content) : msg.content"></div>
          <span v-if="msg.doc_updated" class="badge">Doc atualizado: {{ msg.doc_updated }}</span>
        </div>
        <div v-if="streaming" class="message assistant">
          <div class="bubble" v-html="renderMd(streamContent)"></div>
        </div>
      </div>
      <form @submit.prevent="send" class="input-area">
        <input v-model="input" placeholder="Pergunte sobre o ambiente do cliente..." :disabled="streaming" />
        <button type="submit" :disabled="streaming || !input.trim()">Enviar</button>
      </form>
    </div>
    <div class="sidebar-right" v-if="currentSources">
      <h3>Fontes consultadas</h3>
      <div v-if="currentSources.tabelas?.length">
        <h4>Tabelas</h4>
        <span v-for="t in currentSources.tabelas" :key="t" class="tag">{{ t }}</span>
      </div>
      <div v-if="currentSources.fontes?.length">
        <h4>Fontes</h4>
        <span v-for="f in currentSources.fontes" :key="f" class="tag">{{ f }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick, onMounted } from 'vue'
import { marked } from 'marked'
import api from '../api'

const messages = ref([])
const input = ref('')
const streaming = ref(false)
const streamContent = ref('')
const currentSources = ref(null)
const messagesEl = ref(null)

function renderMd(text) { return marked.parse(text || '') }
function scrollBottom() { nextTick(() => { if (messagesEl.value) messagesEl.value.scrollTop = messagesEl.value.scrollHeight }) }

onMounted(async () => {
  try {
    const { data } = await api.get('/chat/history')
    messages.value = data
  } catch {}
})

async function send() {
  const msg = input.value.trim()
  if (!msg) return
  messages.value.push({ role: 'user', content: msg })
  input.value = ''
  streaming.value = true
  streamContent.value = ''
  currentSources.value = null
  scrollBottom()

  const response = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message: msg })
  })

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let docUpdated = null

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      if (line.startsWith('event: ')) {
        var eventType = line.slice(7).trim()
      }
      if (line.startsWith('data: ')) {
        const data = JSON.parse(line.slice(6))
        if (eventType === 'sources') { currentSources.value = data }
        else if (eventType === 'token') { streamContent.value += data.content; scrollBottom() }
        else if (eventType === 'doc_updated') { docUpdated = data.slug }
        else if (eventType === 'done') { break }
      }
    }
  }

  messages.value.push({ role: 'assistant', content: streamContent.value, doc_updated: docUpdated })
  streaming.value = false
  streamContent.value = ''
  scrollBottom()
}
</script>

<style scoped>
.chat-layout { display: flex; height: calc(100vh - 3rem); }
.chat-main { flex: 1; display: flex; flex-direction: column; }
.messages { flex: 1; overflow-y: auto; padding: 1rem; }
.message { margin-bottom: 1rem; }
.message.user .bubble { background: #e94560; color: white; margin-left: auto; }
.message.assistant .bubble { background: white; border: 1px solid #ddd; }
.bubble { padding: 0.8rem 1rem; border-radius: 12px; max-width: 80%; display: inline-block; }
.badge { display: inline-block; background: #28a745; color: white; font-size: 0.75rem; padding: 0.2rem 0.5rem; border-radius: 10px; margin-top: 0.3rem; }
.input-area { display: flex; gap: 0.5rem; padding: 1rem; border-top: 1px solid #ddd; }
.input-area input { flex: 1; padding: 0.7rem; border: 1px solid #ccc; border-radius: 8px; }
.input-area button { background: #e94560; color: white; border: none; padding: 0.7rem 1.5rem; border-radius: 8px; cursor: pointer; }
.sidebar-right { width: 220px; padding: 1rem; border-left: 1px solid #ddd; background: white; overflow-y: auto; }
.sidebar-right h3 { margin-bottom: 1rem; font-size: 0.9rem; }
.sidebar-right h4 { margin: 0.5rem 0 0.3rem; font-size: 0.8rem; color: #666; }
.tag { display: inline-block; background: #eee; padding: 0.2rem 0.5rem; border-radius: 4px; margin: 0.1rem; font-size: 0.8rem; }
</style>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/views/ChatView.vue
git commit -m "feat: chat view with SSE streaming and sources sidebar"
```

---

### Task 20: Frontend — Padrão, Cliente, and Config Views

**Files:**
- Modify: `frontend/src/views/PadraoView.vue`
- Modify: `frontend/src/views/ClienteView.vue`
- Modify: `frontend/src/views/ConfigView.vue`

- [ ] **Step 1: Implement PadraoView**

```vue
<!-- frontend/src/views/PadraoView.vue -->
<template>
  <div class="docs-view">
    <h1>Base Padrão Protheus</h1>
    <div class="docs-layout">
      <ul class="doc-list">
        <li v-for="doc in docs" :key="doc.slug" @click="select(doc.slug)" :class="{ active: selected === doc.slug }">
          {{ doc.slug }}
        </li>
      </ul>
      <div class="doc-content" v-html="content"></div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { marked } from 'marked'
import api from '../api'

const docs = ref([])
const selected = ref('')
const content = ref('<p>Selecione um processo</p>')

onMounted(async () => {
  const { data } = await api.get('/docs/padrao')
  docs.value = data
})

async function select(slug) {
  selected.value = slug
  const { data } = await api.get(`/docs/padrao/${slug}`)
  content.value = marked.parse(data.content)
}
</script>

<style scoped>
.docs-layout { display: flex; gap: 1rem; height: calc(100vh - 8rem); }
.doc-list { width: 200px; list-style: none; padding: 0; border-right: 1px solid #ddd; }
.doc-list li { padding: 0.5rem; cursor: pointer; border-radius: 4px; }
.doc-list li:hover, .doc-list li.active { background: #e0e0e0; }
.doc-content { flex: 1; overflow-y: auto; padding: 1rem; background: white; border-radius: 8px; }
</style>
```

- [ ] **Step 2: Implement ClienteView**

```vue
<!-- frontend/src/views/ClienteView.vue -->
<template>
  <div class="docs-view">
    <h1>Base do Cliente</h1>
    <div class="tabs">
      <button :class="{ active: tab === 'humano' }" @click="tab = 'humano'; loadDocs()">Humano</button>
      <button :class="{ active: tab === 'ia' }" @click="tab = 'ia'; loadDocs()">IA</button>
    </div>
    <div class="docs-layout">
      <ul class="doc-list">
        <li v-for="doc in docs" :key="doc.slug">
          <span @click="select(doc.slug)">{{ doc.slug }}</span>
          <button class="regen" @click="regenerar(doc.slug)" title="Regenerar">↻</button>
        </li>
      </ul>
      <div class="doc-content" v-html="content"></div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { marked } from 'marked'
import api from '../api'

const tab = ref('humano')
const docs = ref([])
const selected = ref('')
const content = ref('<p>Selecione um documento</p>')

async function loadDocs() {
  const { data } = await api.get('/docs/cliente')
  docs.value = data[tab.value] || []
}

onMounted(loadDocs)

async function select(slug) {
  selected.value = slug
  const { data } = await api.get(`/docs/cliente/${tab.value}/${slug}`)
  content.value = marked.parse(data.content)
}

async function regenerar(slug) {
  content.value = '<p>Regenerando...</p>'
  await api.post(`/docs/cliente/${slug}/regenerar`)
  await select(slug)
}
</script>

<style scoped>
.tabs { margin-bottom: 1rem; }
.tabs button { padding: 0.5rem 1rem; border: 1px solid #ccc; background: white; cursor: pointer; border-radius: 4px; margin-right: 0.3rem; }
.tabs button.active { background: #e94560; color: white; border-color: #e94560; }
.docs-layout { display: flex; gap: 1rem; height: calc(100vh - 10rem); }
.doc-list { width: 200px; list-style: none; padding: 0; border-right: 1px solid #ddd; }
.doc-list li { display: flex; justify-content: space-between; padding: 0.5rem; cursor: pointer; }
.doc-list li:hover { background: #e0e0e0; }
.regen { background: none; border: none; cursor: pointer; font-size: 1.1rem; }
.doc-content { flex: 1; overflow-y: auto; padding: 1rem; background: white; border-radius: 8px; }
</style>
```

- [ ] **Step 3: Implement ConfigView**

```vue
<!-- frontend/src/views/ConfigView.vue -->
<template>
  <div class="config">
    <h1>Configurações</h1>
    <form @submit.prevent="saveConfig">
      <label>Provider IA
        <select v-model="form.provider">
          <option value="anthropic">Anthropic</option>
          <option value="openai">OpenAI</option>
          <option value="ollama">Ollama</option>
        </select>
      </label>
      <label>Modelo
        <input v-model="form.model" />
      </label>
      <label>API Key
        <input v-model="form.api_key" type="password" placeholder="Deixe vazio para manter atual" />
      </label>
      <button type="submit">Salvar</button>
    </form>
    <hr />
    <button class="danger" @click="limpar">Limpar Workspace (novo cliente)</button>
    <p v-if="msg" class="msg">{{ msg }}</p>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api'

const router = useRouter()
const form = ref({ provider: 'anthropic', model: '', api_key: '' })
const msg = ref('')

onMounted(async () => {
  try {
    const { data } = await api.get('/config')
    if (data.llm) {
      form.value.provider = data.llm.provider
      form.value.model = data.llm.model
    }
  } catch {}
})

async function saveConfig() {
  await api.put('/config', { llm: { provider: form.value.provider, model: form.value.model, api_key: form.value.api_key || undefined } })
  msg.value = 'Salvo!'
}

async function limpar() {
  if (!confirm('Isso apagará toda a base. O backup será baixado automaticamente. Continuar?')) return
  const response = await fetch('/api/config/limpar', { method: 'POST' })
  if (response.headers.get('content-type')?.includes('zip')) {
    const blob = await response.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'workspace_backup.zip'
    a.click()
  }
  router.push('/setup')
}
</script>

<style scoped>
.config { max-width: 400px; }
label { display: block; margin-bottom: 1rem; font-weight: 600; }
input, select { display: block; width: 100%; padding: 0.5rem; margin-top: 0.3rem; border: 1px solid #ccc; border-radius: 4px; }
button { background: #e94560; color: white; border: none; padding: 0.7rem 1.5rem; border-radius: 6px; cursor: pointer; }
.danger { background: #dc3545; margin-top: 1rem; }
hr { margin: 2rem 0; }
.msg { color: green; margin-top: 1rem; }
</style>
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/
git commit -m "feat: padrao, cliente, and config views"
```

---

## Chunk 8: Integration and Templates

### Task 21: Standard Process Templates

**Files:**
- Create: `templates/processos/compras.md`
- Create: `templates/processos/faturamento.md`
- Create: `templates/processos/financeiro.md`
- Create: `templates/processos/estoque.md`
- Create: `templates/processos/fiscal.md`
- Create: `templates/processos/pcp.md`
- Create: `templates/processos/rh.md`
- Create: `templates/processos/contabilidade.md`

- [ ] **Step 1: Create all 8 template files**

Each template follows this structure (example for compras):

```markdown
# Compras — Processo Padrão Protheus

## Visão Geral
O módulo de Compras (SIGACOM) gerencia todo o ciclo de aquisição de materiais e serviços.

## Fluxo Padrão
1. Solicitação de Compras (MATA110 → SC1)
2. Cotação de Preços (MATA103 → SC8)
3. Análise de Cotações / Mapa de Cotações
4. Pedido de Compras (MATA120 → SC7)
5. Aprovação de Compras (via alçadas SCR)
6. Documento de Entrada (MATA103A → SD1/SF1)
7. Classificação Fiscal

## Tabelas Principais
- SC1 — Solicitações de compra
- SC7 — Pedidos de compra
- SC8 — Cotações de compra
- SA2 — Fornecedores
- SCR — Alçadas de aprovação
- SD1 — Itens de nota fiscal de entrada
- SF1 — Notas fiscais de entrada

## Rotinas Principais
- MATA110 — Solicitação de compra
- MATA103 — Cotação de preço
- MATA120 — Pedido de compra
- MATA121 — Autorização de compra
- MATA140 — Documento de entrada

## Pontos de Entrada Comuns
- MT120GRV — Gravação do pedido de compra
- MT103BRW — Browse da cotação
- MT140LOK — Validação do documento de entrada
```

Create similar files for all 8 modules with proper standard Protheus flows.

- [ ] **Step 2: Commit**

```bash
git add templates/
git commit -m "feat: standard process templates for 8 Protheus modules"
```

---

### Task 22: Frontend Build and Final Integration

**Files:**
- Modify: `frontend/vite.config.js`
- Modify: `run.py`

- [ ] **Step 1: Configure Vite proxy for development**

```javascript
// frontend/vite.config.js
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      '/api': 'http://localhost:8741'
    }
  }
})
```

- [ ] **Step 2: Build frontend**

Run: `cd frontend && npm run build`
Expected: `frontend/dist/` created with static files

- [ ] **Step 3: Verify full integration**

Run: `python run.py`
Expected: Browser opens, Setup page loads, API calls work through FastAPI

- [ ] **Step 4: Commit**

```bash
git add frontend/vite.config.js frontend/dist/
git commit -m "feat: frontend build and full integration"
```

---

### Task 23: Final Smoke Test

- [ ] **Step 1: Start the app**

Run: `python run.py`
Expected: Browser opens at `http://localhost:8741`

- [ ] **Step 2: Test Setup flow**

Fill in Setup form with test data, click "Iniciar". Verify progress bar shows ingestion phases.

- [ ] **Step 3: Test Chat**

After ingestion, send a question. Verify streaming response and sources sidebar.

- [ ] **Step 4: Test Base Padrão**

Navigate to Base Padrão, verify templates render.

- [ ] **Step 5: Test Base Cliente**

Navigate to Base Cliente, verify generated docs (if any from Fase 3).

- [ ] **Step 6: Test Config**

Navigate to Config, change model, save. Test "Limpar workspace" downloads ZIP and resets.

- [ ] **Step 7: Final commit**

```bash
git add -A
git commit -m "feat: ExtraiRPO v0.1.0 — complete MVP"
```
