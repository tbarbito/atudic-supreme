# Descoberta de Processos do Cliente — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir o pipeline de descoberta automática de processos de negócio do cliente, cacheado na tabela `processos_detectados`, integrado ao contexto do Analista.

**Architecture:** Pipeline SQL-first em 4 passos (clustering campos, gatilhos, fontes+satélites, jobs) seguido de 1 chamada LLM que nomeia e classifica os processos. Resultado salvo em `processos_detectados` e consumido pelo Analista como contexto prévio antes de responder.

**Tech Stack:** Python, SQLite (`database.py` schema), FastAPI (endpoints em `analista.py`), Anthropic SDK (`LLMService`), pytest (fixtures com `tmp_path`).

---

## Chunk 1: Schema + Serviço SQL (passos 1–4)

### Task 1: Adicionar `processos_detectados` ao schema

**Files:**
- Modify: `backend/services/database.py` (final do SCHEMA, antes do `"""`)

- [ ] **Step 1: Escrever o teste**

```python
# tests/test_database.py — adicionar ao fim do arquivo
def test_processos_detectados_table_exists(db):
    tables = db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    table_names = {row[0] for row in tables}
    assert "processos_detectados" in table_names

def test_processos_detectados_insert(db):
    db.execute(
        "INSERT INTO processos_detectados (nome, tipo, tabelas, evidencias, score) "
        "VALUES (?,?,?,?,?)",
        ("Aprovação de Pedido", "workflow", '["SC5","SZV"]', '{}', 0.9),
    )
    row = db.execute("SELECT nome, tipo, score FROM processos_detectados").fetchone()
    assert row[0] == "Aprovação de Pedido"
    assert row[2] == 0.9
```

- [ ] **Step 2: Rodar para confirmar falha**

```
pytest tests/test_database.py::test_processos_detectados_table_exists -v
```
Expected: FAIL — `assert "processos_detectados" in table_names`

- [ ] **Step 3: Adicionar ao SCHEMA em `database.py`**

Adicionar antes do fechamento `"""` do SCHEMA (depois de `idx_schedules_status`):

```sql
CREATE TABLE IF NOT EXISTS processos_detectados (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    nome        TEXT NOT NULL,
    tipo        TEXT NOT NULL,
    descricao   TEXT DEFAULT '',
    criticidade TEXT DEFAULT 'media',
    tabelas     TEXT DEFAULT '[]',
    evidencias  TEXT DEFAULT '{}',
    metodo      TEXT DEFAULT 'pipeline',
    score       REAL DEFAULT 0.0,
    validado    INTEGER DEFAULT 0,
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_processos_tipo ON processos_detectados(tipo);
CREATE INDEX IF NOT EXISTS idx_processos_validado ON processos_detectados(validado);
```

- [ ] **Step 4: Rodar testes**

```
pytest tests/test_database.py -v
```
Expected: todos PASS incluindo os 2 novos.

- [ ] **Step 5: Commit**

```bash
git add backend/services/database.py tests/test_database.py
git commit -m "feat: add processos_detectados table to schema"
```

---

### Task 2: Criar `backend/services/descoberta_processos.py` — passos 1–4

Este arquivo contém as 4 funções SQL puras que extraem dados brutos da base do cliente. Sem LLM, sem I/O externo.

**Files:**
- Create: `backend/services/descoberta_processos.py`
- Create: `tests/test_descoberta_processos.py`

- [ ] **Step 1: Escrever os testes (fixtures + passo 1)**

```python
# tests/test_descoberta_processos.py
import json
import pytest
from pathlib import Path
from backend.services.database import Database
from backend.services.descoberta_processos import (
    passo1_clustering_campos,
    passo2_gatilhos,
    passo3_fontes_satelite,
    passo4_jobs,
)


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "test.db")
    database.initialize()
    return database


@pytest.fixture
def db_com_dados(db):
    """Banco com dados mínimos para os 4 passos."""
    # Tabelas custom
    db.execute("INSERT INTO tabelas VALUES ('ZZE','INTEGRACAO TAURA',NULL,1)")
    db.execute("INSERT INTO tabelas VALUES ('SC5','Pedidos de Venda',NULL,0)")
    db.execute("INSERT INTO tabelas VALUES ('SZV','Bloqueios',NULL,1)")

    # Campos custom — nível 1 (tabela custom com 6 campos)
    for i in range(6):
        db.execute(
            "INSERT INTO campos (tabela,campo,tipo,tamanho,titulo,custom,cbox) VALUES (?,?,?,?,?,?,?)",
            ("ZZE", f"ZZE_C{i:02}", "C", 10, f"Campo {i}", 1, ""),
        )
    # Campos custom — nível 2 (cbox com 3 estados)
    db.execute(
        "INSERT INTO campos (tabela,campo,tipo,tamanho,titulo,custom,cbox) VALUES (?,?,?,?,?,?,?)",
        ("SC5", "C5_ZSTATUS", "C", 1, "Status Aprovação", 1, "P=Pendente;A=Aprovado;R=Reprovado"),
    )
    # Campos custom — nível 3 (título com palavra-chave)
    db.execute(
        "INSERT INTO campos (tabela,campo,tipo,tamanho,titulo,custom,cbox) VALUES (?,?,?,?,?,?,?)",
        ("SC5", "C5_ZAPROV", "C", 1, "Aprovado", 1, ""),
    )
    # Diff
    for i in range(25):
        db.execute(
            "INSERT INTO diff (tipo_sx,tabela,campo,acao) VALUES (?,?,?,?)",
            ("campo", "SC5", f"C5_Z{i:03}", "adicionado"),
        )
    # Gatilhos custom
    db.execute(
        "INSERT INTO gatilhos (campo_origem,sequencia,campo_destino,regra,custom) VALUES (?,?,?,?,?)",
        ("C5_CLIENTE","010","C5_ZAPROV","U_MGFFAT33()","",),
    )
    for i in range(5):
        db.execute(
            "INSERT INTO gatilhos (campo_origem,sequencia,campo_destino,regra,custom) VALUES (?,?,?,?,?)",
            ("C5_CLIENTE", f"0{i+2}0", f"C5_Z{i:03}", "", 1),
        )
    # Fontes com write_tables e tabelas_ref
    db.execute(
        "INSERT INTO fontes (arquivo,modulo,write_tables,tabelas_ref,lines_of_code) VALUES (?,?,?,?,?)",
        ("MGFFAT53.prw","MATA410",'["SC5","SZV"]','["SZT"]',1200),
    )
    db.execute(
        "INSERT INTO fontes (arquivo,modulo,write_tables,tabelas_ref,lines_of_code) VALUES (?,?,?,?,?)",
        ("MGFFAT64.prw","MATA410",'["SC5","SZV"]','[]',800),
    )
    # Jobs
    db.execute(
        "INSERT INTO jobs (arquivo_ini,sessao,rotina,refresh_rate) VALUES (?,?,?,?)",
        ("MGFFAT53.prw","S001","MGFFAT53",30),
    )
    db.commit()
    return db


# ── Passo 1 ──
def test_passo1_detecta_tabela_custom(db_com_dados):
    result = passo1_clustering_campos(db_com_dados)
    tabelas_custom = result["nivel1_tabelas_custom"]
    codigos = [t["tabela"] for t in tabelas_custom]
    assert "ZZE" in codigos


def test_passo1_detecta_cbox_estados(db_com_dados):
    result = passo1_clustering_campos(db_com_dados)
    cbox = result["nivel2_cbox_estados"]
    campos = [c["campo"] for c in cbox]
    assert "C5_ZSTATUS" in campos


def test_passo1_detecta_titulo_keywords(db_com_dados):
    result = passo1_clustering_campos(db_com_dados)
    titulos = result["nivel3_titulos"]
    assert any(g["processo"] == "WORKFLOW_APROVACAO" for g in titulos)


def test_passo1_detecta_diff(db_com_dados):
    result = passo1_clustering_campos(db_com_dados)
    diffs = result["nivel5_diff"]
    assert any(d["tabela"] == "SC5" for d in diffs)


# ── Passo 2 ──
def test_passo2_detecta_super_trigger(db_com_dados):
    result = passo2_gatilhos(db_com_dados)
    assert "C5_CLIENTE" in result["super_triggers"]
    assert result["super_triggers"]["C5_CLIENTE"]["qtd_destinos"] >= 5


def test_passo2_detecta_funcoes_u(db_com_dados):
    result = passo2_gatilhos(db_com_dados)
    assert "U_MGFFAT33" in result["funcoes_chamadas"]


# ── Passo 3 ──
def test_passo3_detecta_satelite(db_com_dados):
    result = passo3_fontes_satelite(db_com_dados)
    satelites = result["satelites"]
    assert any(s["tabela"] == "SZV" for s in satelites)


def test_passo3_agrupa_por_cluster(db_com_dados):
    result = passo3_fontes_satelite(db_com_dados)
    # SC5 deve ter pelo menos 2 fontes de escrita
    sc5_cluster = next((c for c in result["clusters_tabela"] if c["tabela"] == "SC5"), None)
    assert sc5_cluster is not None
    assert sc5_cluster["total_fontes"] >= 2


# ── Passo 4 ──
def test_passo4_classifica_criticidade(db_com_dados):
    result = passo4_jobs(db_com_dados)
    jobs = result["jobs_criticos"]
    mgffat = next((j for j in jobs if "MGFFAT53" in j["arquivo"]), None)
    assert mgffat is not None
    assert mgffat["criticidade"] == "critico"  # refresh_rate=30 < 60
```

- [ ] **Step 2: Rodar para confirmar falha**

```
pytest tests/test_descoberta_processos.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.services.descoberta_processos'`

- [ ] **Step 3: Implementar `descoberta_processos.py`**

```python
# backend/services/descoberta_processos.py
"""Pipeline de descoberta automática de processos do cliente — SQL puro (passos 1-4)."""
import json
import re


def _safe_json(val):
    if not val:
        return []
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return []


# ──────────────────────────────────────────────────────────────
# PASSO 1 — Clustering de campos: 5 níveis SQL
# ──────────────────────────────────────────────────────────────

def passo1_clustering_campos(db) -> dict:
    """Detecta macro-processos via 5 níveis semânticos nos dados do cliente."""

    # Nível 1 — tabelas custom com >= 5 campos
    nivel1 = []
    rows = db.execute(
        "SELECT t.codigo, t.nome, COUNT(c.campo) as total_campos "
        "FROM tabelas t LEFT JOIN campos c ON c.tabela = t.codigo "
        "WHERE t.custom=1 GROUP BY t.codigo HAVING total_campos >= 5 "
        "ORDER BY total_campos DESC"
    ).fetchall()
    for r in rows:
        nivel1.append({"tabela": r[0], "nome": r[1], "total_campos": r[2]})

    # Nível 2 — cbox com 3+ estados (máquinas de estado)
    nivel2 = []
    rows = db.execute(
        "SELECT tabela, campo, titulo, cbox, "
        "  LENGTH(cbox) - LENGTH(REPLACE(cbox, ';', '')) + 1 as num_estados "
        "FROM campos "
        "WHERE custom=1 AND cbox IS NOT NULL AND LENGTH(TRIM(cbox)) > 3 "
        "  AND LENGTH(cbox) - LENGTH(REPLACE(cbox, ';', '')) >= 2 "
        "ORDER BY num_estados DESC LIMIT 50"
    ).fetchall()
    for r in rows:
        nivel2.append({
            "tabela": r[0], "campo": r[1], "titulo": r[2],
            "cbox": r[3], "num_estados": r[4],
        })

    # Nível 3 — títulos com keywords de processo
    nivel3_sql = """
        SELECT
            CASE
                WHEN LOWER(titulo) LIKE '%aprov%' OR LOWER(titulo) LIKE '%liber%' THEN 'WORKFLOW_APROVACAO'
                WHEN LOWER(titulo) LIKE '%bloq%' THEN 'CONTROLE_BLOQUEIO'
                WHEN LOWER(titulo) LIKE '%integr%' THEN 'INTEGRACAO'
                WHEN LOWER(titulo) LIKE '%envia%' OR LOWER(titulo) LIKE '%reenvi%' THEN 'ENVIO_INTEGRACAO'
                WHEN LOWER(titulo) LIKE '%status%' THEN 'STATUS_PROCESSO'
                WHEN LOWER(titulo) LIKE '%log de%' OR LOWER(titulo) LIKE '%histor%' THEN 'AUDITORIA_LOG'
                WHEN LOWER(titulo) LIKE '%taura%' THEN 'TAURA_WMS'
                WHEN LOWER(titulo) LIKE '%tms%' THEN 'TMS_TRANSPORTE'
                WHEN LOWER(titulo) LIKE '%frete%' OR LOWER(titulo) LIKE '%embarg%' THEN 'LOGISTICA'
                WHEN LOWER(titulo) LIKE '%fiscal%' OR LOWER(titulo) LIKE '%nf%' THEN 'FISCAL'
                WHEN LOWER(titulo) LIKE '%qualidade%' OR LOWER(titulo) LIKE '%inspecao%' THEN 'QUALIDADE'
                WHEN LOWER(titulo) LIKE '%salesforce%' OR LOWER(titulo) LIKE '%sf%' THEN 'SALESFORCE'
                WHEN LOWER(titulo) LIKE '%ecommerce%' OR LOWER(titulo) LIKE '%e-commerce%' THEN 'ECOMMERCE'
            END as processo,
            COUNT(*) as qtd_campos,
            GROUP_CONCAT(DISTINCT tabela) as tabelas
        FROM campos
        WHERE custom=1 AND titulo IS NOT NULL
        GROUP BY processo
        HAVING processo IS NOT NULL
        ORDER BY qtd_campos DESC
    """
    nivel3 = []
    for r in db.execute(nivel3_sql).fetchall():
        nivel3.append({
            "processo": r[0], "qtd_campos": r[1],
            "tabelas": (r[2] or "").split(","),
        })

    # Nível 4 — prefixo repetido em tabelas padrão (4+ campos com mesmo prefixo)
    nivel4 = []
    rows = db.execute(
        "SELECT tabela, SUBSTR(campo, 4, 3) as prefixo, COUNT(*) as qtd "
        "FROM campos WHERE custom=1 AND LENGTH(campo) >= 7 "
        "GROUP BY tabela, prefixo HAVING qtd >= 4 ORDER BY qtd DESC LIMIT 30"
    ).fetchall()
    for r in rows:
        nivel4.append({"tabela": r[0], "prefixo": r[1], "qtd_campos": r[2]})

    # Nível 5 — diff padrão vs cliente (tabelas muito modificadas)
    nivel5 = []
    rows = db.execute(
        "SELECT tabela, "
        "  SUM(CASE WHEN acao='adicionado' THEN 1 ELSE 0 END) as adicionados, "
        "  SUM(CASE WHEN acao='alterado' THEN 1 ELSE 0 END) as alterados, "
        "  COUNT(*) as total_diffs "
        "FROM diff WHERE tipo_sx='campo' "
        "GROUP BY tabela HAVING total_diffs >= 20 ORDER BY total_diffs DESC LIMIT 20"
    ).fetchall()
    for r in rows:
        nivel5.append({
            "tabela": r[0], "adicionados": r[1],
            "alterados": r[2], "total_diffs": r[3],
        })

    return {
        "nivel1_tabelas_custom": nivel1,
        "nivel2_cbox_estados": nivel2,
        "nivel3_titulos": nivel3,
        "nivel4_prefixos": nivel4,
        "nivel5_diff": nivel5,
    }


# ──────────────────────────────────────────────────────────────
# PASSO 2 — Mapa de gatilhos e cadeias
# ──────────────────────────────────────────────────────────────

def passo2_gatilhos(db) -> dict:
    """Extrai super-triggers, funções U_ e tabelas consultadas."""

    # Super-triggers: campos que disparam 5+ gatilhos custom
    super_triggers = {}
    rows = db.execute(
        "SELECT campo_origem, COUNT(*) as qtd, "
        "  GROUP_CONCAT(DISTINCT regra) as regras "
        "FROM gatilhos WHERE custom=1 OR proprietario!='S' "
        "GROUP BY campo_origem HAVING qtd >= 3 ORDER BY qtd DESC LIMIT 20"
    ).fetchall()
    for r in rows:
        regras_raw = r[2] or ""
        funcoes = re.findall(r'U_\w+', regras_raw)
        super_triggers[r[0]] = {
            "qtd_destinos": r[1],
            "funcoes": list(set(funcoes)),
        }

    # Funções U_ chamadas em gatilhos (todas, ordenadas por frequência)
    funcoes_counter: dict[str, int] = {}
    rows = db.execute(
        "SELECT regra FROM gatilhos WHERE regra IS NOT NULL AND regra != ''"
    ).fetchall()
    for r in rows:
        for f in re.findall(r'U_\w+', r[0]):
            funcoes_counter[f] = funcoes_counter.get(f, 0) + 1
    funcoes_sorted = sorted(funcoes_counter.items(), key=lambda x: -x[1])

    # Alias consultados via seek nos gatilhos (tabelas dependentes)
    aliases = {}
    rows = db.execute(
        "SELECT alias, COUNT(*) as qtd FROM gatilhos "
        "WHERE alias IS NOT NULL AND alias != '' "
        "GROUP BY alias ORDER BY qtd DESC LIMIT 20"
    ).fetchall()
    for r in rows:
        aliases[r[0]] = r[1]

    # Total gatilhos custom
    total = db.execute(
        "SELECT COUNT(*) FROM gatilhos WHERE custom=1"
    ).fetchone()[0]

    return {
        "total_gatilhos_custom": total,
        "super_triggers": super_triggers,
        "funcoes_chamadas": [f for f, _ in funcoes_sorted[:20]],
        "aliases_consultados": aliases,
    }


# ──────────────────────────────────────────────────────────────
# PASSO 3 — Fontes de escrita + tabelas satélite
# ──────────────────────────────────────────────────────────────

def passo3_fontes_satelite(db) -> dict:
    """Agrupa fontes por tabela que escrevem e identifica satélites."""

    # Cluster por tabela: todos os fontes que a escrevem
    clusters: dict[str, dict] = {}
    rows = db.execute(
        "SELECT arquivo, write_tables, tabelas_ref, lines_of_code FROM fontes "
        "WHERE write_tables IS NOT NULL AND write_tables != '[]'"
    ).fetchall()

    satelite_counter: dict[str, set] = {}  # tabela_satelite -> set of arquivos

    for arquivo, write_raw, ref_raw, loc in rows:
        write_tabs = _safe_json(write_raw)
        ref_tabs = _safe_json(ref_raw)

        for tab in write_tabs:
            tab_upper = tab.upper()
            if tab_upper not in clusters:
                clusters[tab_upper] = {"tabela": tab_upper, "fontes": [], "total_fontes": 0}
            clusters[tab_upper]["fontes"].append(arquivo)
            clusters[tab_upper]["total_fontes"] += 1

            # Satélites: outras tabelas escritas pelo mesmo arquivo
            for other in write_tabs:
                other_upper = other.upper()
                if other_upper != tab_upper:
                    satelite_counter.setdefault(other_upper, set()).add(arquivo)

    # Satélites com 2+ fontes em comum
    satelites = []
    for tab, arquivos in sorted(satelite_counter.items(), key=lambda x: -len(x[1])):
        if len(arquivos) >= 2:
            trow = db.execute(
                "SELECT nome, custom FROM tabelas WHERE upper(codigo)=?", (tab,)
            ).fetchone()
            satelites.append({
                "tabela": tab,
                "nome": trow[0] if trow else "",
                "custom": trow[1] if trow else 0,
                "total_fontes_compartilhados": len(arquivos),
                "arquivos": sorted(arquivos)[:5],
            })

    # Top clusters (tabelas com mais fontes de escrita)
    clusters_list = sorted(clusters.values(), key=lambda x: -x["total_fontes"])

    return {
        "clusters_tabela": clusters_list[:30],
        "satelites": satelites[:20],
    }


# ──────────────────────────────────────────────────────────────
# PASSO 4 — Jobs, schedules e criticidade
# ──────────────────────────────────────────────────────────────

def passo4_jobs(db) -> dict:
    """Cruza fontes com jobs/schedules e classifica criticidade."""

    def _criticidade(refresh_rate, instancias):
        if refresh_rate is not None and refresh_rate < 60:
            return "critico"
        if refresh_rate is not None and refresh_rate < 300:
            return "alto"
        if instancias and instancias > 3:
            return "alto"
        if refresh_rate is not None and refresh_rate < 1800:
            return "medio"
        return "baixo"

    jobs_rows = db.execute(
        "SELECT arquivo_ini, sessao, rotina, refresh_rate, COUNT(*) as instancias "
        "FROM jobs GROUP BY rotina ORDER BY instancias DESC, refresh_rate ASC"
    ).fetchall()

    jobs_criticos = []
    for r in jobs_rows:
        crit = _criticidade(r[3], r[4])
        jobs_criticos.append({
            "arquivo": r[0],
            "rotina": r[2],
            "refresh_rate": r[3],
            "instancias": r[4],
            "criticidade": crit,
        })

    schedules_rows = db.execute(
        "SELECT rotina, execucoes_dia, status, tipo_recorrencia "
        "FROM schedules WHERE status != 'inativo' "
        "ORDER BY execucoes_dia DESC LIMIT 30"
    ).fetchall()

    schedules = []
    for r in schedules_rows:
        schedules.append({
            "rotina": r[0],
            "execucoes_dia": r[1],
            "status": r[2],
            "tipo_recorrencia": r[3],
        })

    return {
        "jobs_criticos": jobs_criticos,
        "schedules_ativos": schedules,
    }
```

- [ ] **Step 4: Rodar os testes**

```
pytest tests/test_descoberta_processos.py -v
```
Expected: todos PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/services/descoberta_processos.py tests/test_descoberta_processos.py
git commit -m "feat: descoberta_processos passos 1-4 SQL puro"
```

---

## Chunk 2: Orquestrador + LLM (passo 5) + Tool

### Task 3: Passo 5 (LLM) + orquestrador `descobrir_processos()`

**Files:**
- Modify: `backend/services/descoberta_processos.py` (adicionar ao fim)
- Modify: `tests/test_descoberta_processos.py` (adicionar testes)

- [ ] **Step 1: Escrever os testes do orquestrador**

```python
# tests/test_descoberta_processos.py — adicionar ao fim

from unittest.mock import MagicMock
from backend.services.descoberta_processos import descobrir_processos


def test_descobrir_processos_salva_no_banco(db_com_dados):
    mock_llm = MagicMock()
    mock_llm.complete.return_value = json.dumps([
        {
            "nome": "Integração Taura WMS",
            "tipo": "integracao",
            "descricao": "Pedidos enviados ao Taura com controle de status",
            "criticidade": "alta",
            "tabelas": ["SC5", "ZZE"],
            "score": 0.92,
        }
    ])

    result = descobrir_processos(db_com_dados, mock_llm)

    assert len(result) >= 1
    assert result[0]["nome"] == "Integração Taura WMS"

    # Verifica se salvou no banco
    rows = db_com_dados.execute("SELECT nome, tipo, score FROM processos_detectados").fetchall()
    assert len(rows) >= 1
    assert rows[0][0] == "Integração Taura WMS"


def test_descobrir_processos_usa_cache(db_com_dados):
    """Segunda chamada não deve chamar LLM."""
    mock_llm = MagicMock()
    mock_llm.complete.return_value = json.dumps([
        {"nome": "Teste", "tipo": "workflow", "descricao": "",
         "criticidade": "media", "tabelas": [], "score": 0.5}
    ])

    descobrir_processos(db_com_dados, mock_llm)
    call_count_after_first = mock_llm.complete.call_count

    descobrir_processos(db_com_dados, mock_llm)
    assert mock_llm.complete.call_count == call_count_after_first  # não chamou de novo


def test_descobrir_processos_force_recalcula(db_com_dados):
    """force=True deve recalcular mesmo com cache."""
    mock_llm = MagicMock()
    mock_llm.complete.return_value = json.dumps([
        {"nome": "Teste", "tipo": "workflow", "descricao": "",
         "criticidade": "media", "tabelas": [], "score": 0.5}
    ])

    descobrir_processos(db_com_dados, mock_llm)
    descobrir_processos(db_com_dados, mock_llm, force=True)
    assert mock_llm.complete.call_count == 2
```

- [ ] **Step 2: Confirmar falha**

```
pytest tests/test_descoberta_processos.py::test_descobrir_processos_salva_no_banco -v
```
Expected: FAIL — `ImportError: cannot import name 'descobrir_processos'`

- [ ] **Step 3: Implementar passo 5 + orquestrador**

Adicionar ao fim de `backend/services/descoberta_processos.py`:

```python
# ──────────────────────────────────────────────────────────────
# PASSO 5 — Classificação e nomeação via LLM (1 chamada)
# ──────────────────────────────────────────────────────────────

_PASSO5_PROMPT = """Você é um especialista em sistemas ERP Protheus.
Analise os dados estruturados abaixo extraídos do ambiente do cliente e identifique os macro-processos de negócio.

DADOS EXTRAÍDOS:
{dados}

INSTRUÇÕES:
- Cada processo deve ter um nome claro em português (ex: "Integração Taura WMS", "Aprovação de Pedido de Venda")
- Combine evidências de múltiplos níveis para nomear corretamente
- Tipos válidos: workflow, integracao, pricing, fiscal, logistica, regulatorio, auditoria, qualidade, automacao, outro
- Score de 0 a 1 indicando confiança na detecção
- Ignore clusters genéricos (ex: apenas "log de alterações" com score < 0.5)
- Retorne APENAS o JSON, sem explicações

FORMATO DE SAÍDA (JSON array):
[
  {{
    "nome": "Nome do Processo",
    "tipo": "workflow|integracao|pricing|fiscal|logistica|regulatorio|auditoria|qualidade|automacao|outro",
    "descricao": "Uma frase descrevendo o processo",
    "criticidade": "alta|media|baixa",
    "tabelas": ["SC5", "SZV"],
    "score": 0.85
  }}
]"""


def _passo5_llm(dados: dict, llm) -> list[dict]:
    """Chama LLM uma vez para nomear e classificar os processos detectados."""
    dados_compacto = {
        "tabelas_custom": dados["passo1"]["nivel1_tabelas_custom"][:15],
        "maquinas_estado": dados["passo1"]["nivel2_cbox_estados"][:10],
        "clusters_titulo": dados["passo1"]["nivel3_titulos"],
        "prefixos_sistemas": dados["passo1"]["nivel4_prefixos"][:10],
        "tabelas_modificadas": dados["passo1"]["nivel5_diff"][:10],
        "super_triggers": list(dados["passo2"]["super_triggers"].keys())[:10],
        "funcoes_u": dados["passo2"]["funcoes_chamadas"][:15],
        "satelites": [s["tabela"] for s in dados["passo3"]["satelites"][:10]],
        "jobs_criticos": [
            {"rotina": j["rotina"], "criticidade": j["criticidade"]}
            for j in dados["passo4"]["jobs_criticos"][:10]
        ],
    }
    prompt = _PASSO5_PROMPT.format(dados=json.dumps(dados_compacto, ensure_ascii=False, indent=2))
    response = llm.complete(prompt)
    try:
        processos = json.loads(response)
        if not isinstance(processos, list):
            return []
        return processos
    except (json.JSONDecodeError, TypeError):
        return []


# ──────────────────────────────────────────────────────────────
# ORQUESTRADOR PRINCIPAL
# ──────────────────────────────────────────────────────────────

def descobrir_processos(db, llm, force: bool = False) -> list[dict]:
    """
    Roda o pipeline completo de descoberta (passos 1-5) e salva em processos_detectados.
    Usa cache — não recalcula se já existem registros, a menos que force=True.
    """
    # Checar cache
    if not force:
        count = db.execute("SELECT COUNT(*) FROM processos_detectados").fetchone()[0]
        if count > 0:
            rows = db.execute(
                "SELECT id, nome, tipo, descricao, criticidade, tabelas, score "
                "FROM processos_detectados ORDER BY score DESC"
            ).fetchall()
            return [
                {"id": r[0], "nome": r[1], "tipo": r[2], "descricao": r[3],
                 "criticidade": r[4], "tabelas": _safe_json(r[5]), "score": r[6]}
                for r in rows
            ]

    # Rodar passos 1-4
    dados = {
        "passo1": passo1_clustering_campos(db),
        "passo2": passo2_gatilhos(db),
        "passo3": passo3_fontes_satelite(db),
        "passo4": passo4_jobs(db),
    }

    # Passo 5: LLM
    processos = _passo5_llm(dados, llm)

    if not processos:
        return []

    # Limpar resultados anteriores e salvar novos
    db.execute("DELETE FROM processos_detectados")
    for p in processos:
        tabelas_json = json.dumps(p.get("tabelas", []), ensure_ascii=False)
        evidencias_json = json.dumps({
            "nivel1": [t["tabela"] for t in dados["passo1"]["nivel1_tabelas_custom"][:5]],
            "nivel3": [g["processo"] for g in dados["passo1"]["nivel3_titulos"][:5]],
        }, ensure_ascii=False)
        db.execute(
            "INSERT INTO processos_detectados "
            "(nome, tipo, descricao, criticidade, tabelas, evidencias, score) "
            "VALUES (?,?,?,?,?,?,?)",
            (
                p.get("nome", ""),
                p.get("tipo", "outro"),
                p.get("descricao", ""),
                p.get("criticidade", "media"),
                tabelas_json,
                evidencias_json,
                float(p.get("score", 0.5)),
            ),
        )
    db.commit()

    # Retornar os registros salvos (com IDs)
    rows = db.execute(
        "SELECT id, nome, tipo, descricao, criticidade, tabelas, score "
        "FROM processos_detectados ORDER BY score DESC"
    ).fetchall()
    return [
        {"id": r[0], "nome": r[1], "tipo": r[2], "descricao": r[3],
         "criticidade": r[4], "tabelas": _safe_json(r[5]), "score": r[6]}
        for r in rows
    ]
```

- [ ] **Step 4: Verificar que LLMService tem `.complete()`**

```
grep -n "def complete" backend/services/llm.py
```

Se não existir, verificar o método de geração de texto não-streaming e ajustar a chamada no `_passo5_llm`. O método correto pode ser `.chat()`, `.generate()` ou similar — usar o mesmo que outros serviços usam para chamadas não-streaming.

- [ ] **Step 5: Rodar os testes**

```
pytest tests/test_descoberta_processos.py -v
```
Expected: todos PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/services/descoberta_processos.py tests/test_descoberta_processos.py
git commit -m "feat: passo 5 LLM + orquestrador descobrir_processos com cache"
```

---

### Task 4: `tool_processos_cliente()` em `analista_tools.py`

**Files:**
- Modify: `backend/services/analista_tools.py` (adicionar ao fim)

- [ ] **Step 1: Escrever o teste**

```python
# tests/test_analista_tools_processos.py (novo arquivo)
import json
import pytest
from unittest.mock import patch, MagicMock
from backend.services.analista_tools import tool_processos_cliente


@pytest.fixture
def mock_db_com_processos(tmp_path):
    from backend.services.database import Database
    db = Database(tmp_path / "test.db")
    db.initialize()
    db.execute(
        "INSERT INTO processos_detectados (nome, tipo, descricao, criticidade, tabelas, score) "
        "VALUES (?,?,?,?,?,?)",
        ("Aprovação de Pedido", "workflow", "Motor de regras bloqueia pedidos", "alta", '["SC5","SZV"]', 0.9),
    )
    db.execute(
        "INSERT INTO processos_detectados (nome, tipo, descricao, criticidade, tabelas, score) "
        "VALUES (?,?,?,?,?,?)",
        ("Integração Taura", "integracao", "Envio de pedidos ao WMS", "alta", '["SC5","ZZE"]', 0.85),
    )
    db.commit()
    return db


def test_tool_processos_cliente_retorna_todos(mock_db_com_processos, tmp_path):
    with patch("backend.services.analista_tools._get_db", return_value=mock_db_com_processos):
        result = tool_processos_cliente()
    assert len(result["processos"]) == 2
    assert result["total"] == 2


def test_tool_processos_cliente_filtra_tabela(mock_db_com_processos, tmp_path):
    with patch("backend.services.analista_tools._get_db", return_value=mock_db_com_processos):
        result = tool_processos_cliente(tabelas=["SZV"])
    processos = result["processos"]
    # Deve retornar apenas "Aprovação de Pedido" (que tem SZV)
    assert len(processos) == 1
    assert processos[0]["nome"] == "Aprovação de Pedido"


def test_tool_processos_cliente_sem_dados(tmp_path):
    from backend.services.database import Database
    db = Database(tmp_path / "empty.db")
    db.initialize()
    with patch("backend.services.analista_tools._get_db", return_value=db):
        result = tool_processos_cliente()
    assert result["total"] == 0
    assert result["processos"] == []
    assert result["status"] == "sem_cache"
```

- [ ] **Step 2: Confirmar falha**

```
pytest tests/test_analista_tools_processos.py -v
```
Expected: FAIL — `ImportError: cannot import name 'tool_processos_cliente'`

- [ ] **Step 3: Implementar a tool**

Adicionar ao fim de `backend/services/analista_tools.py`:

```python
def tool_processos_cliente(tabelas: list[str] | None = None) -> dict:
    """List detected business processes for the client (cached).

    Args:
        tabelas: Optional list of table codes to filter by (e.g. ['SC5', 'SZV']).
                 Returns only processes that involve those tables.
    """
    db = _get_db()
    try:
        count = db.execute("SELECT COUNT(*) FROM processos_detectados").fetchone()[0]
        if count == 0:
            return {"total": 0, "processos": [], "status": "sem_cache"}

        rows = db.execute(
            "SELECT id, nome, tipo, descricao, criticidade, tabelas, score "
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
            })

        return {"total": len(processos), "processos": processos, "status": "ok"}
    finally:
        db.close()
```

- [ ] **Step 4: Rodar os testes**

```
pytest tests/test_analista_tools_processos.py -v
```
Expected: todos PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/services/analista_tools.py tests/test_analista_tools_processos.py
git commit -m "feat: tool_processos_cliente — consulta cache de processos detectados"
```

---

## Chunk 3: Endpoints + Context Injection

### Task 5: Endpoints REST

**Files:**
- Modify: `backend/routers/analista.py` (adicionar 2 endpoints antes do `@router.post("/conversas/{conversa_id}/chat")`)

- [ ] **Step 1: Adicionar os endpoints**

Localizar o trecho `@router.post("/conversas/{conversa_id}/chat")` em [analista.py:351](backend/routers/analista.py#L351) e inserir **antes** dele:

```python
@router.post("/processos/descobrir")
async def descobrir_processos_cliente(force: bool = False):
    """Trigger the discovery pipeline (passos 1-5). Runs once per client, cached."""
    import asyncio
    from backend.services.descoberta_processos import descobrir_processos
    from backend.routers.chat import _get_services

    try:
        db_svc, vs, ks, llm, client_dir = _get_services()
    except Exception as e:
        raise HTTPException(500, f"Erro ao iniciar serviços: {str(e)[:200]}")

    try:
        processos = await asyncio.to_thread(descobrir_processos, db_svc, llm, force)
        return {"total": len(processos), "processos": processos}
    except Exception as e:
        raise HTTPException(500, f"Erro no pipeline de descoberta: {str(e)[:300]}")
    finally:
        db_svc.close()


@router.get("/processos")
def listar_processos_cliente(tipo: str = "", criticidade: str = ""):
    """List cached detected processes. Filters: tipo, criticidade."""
    from backend.services.analista_tools import tool_processos_cliente
    db = _get_db()
    try:
        _ensure_tables(db)
        result = tool_processos_cliente()
        processos = result["processos"]
        if tipo:
            processos = [p for p in processos if p["tipo"] == tipo]
        if criticidade:
            processos = [p for p in processos if p["criticidade"] == criticidade]
        return {"total": len(processos), "processos": processos, "status": result["status"]}
    finally:
        db.close()
```

- [ ] **Step 2: Verificar que LLMService tem método compatível com `_passo5_llm`**

Ler `backend/services/llm.py` e confirmar o nome do método de chamada não-streaming. Se for diferente de `.complete()`, ajustar em `descoberta_processos.py` para usar o método correto.

- [ ] **Step 3: Testar os endpoints manualmente**

```bash
# Listar (deve retornar status=sem_cache se ainda não rodou)
curl -s http://localhost:8000/api/analista/processos | python -m json.tool

# Rodar pipeline
curl -s -X POST "http://localhost:8000/api/analista/processos/descobrir" | python -m json.tool

# Listar novamente (deve ter dados)
curl -s http://localhost:8000/api/analista/processos | python -m json.tool
```

- [ ] **Step 4: Commit**

```bash
git add backend/routers/analista.py
git commit -m "feat: endpoints /processos/descobrir e /processos"
```

---

### Task 6: Injeção no contexto do Analista

Quando o Analista responde sobre uma tabela, ele já deve saber quais processos a envolvem. Isso é feito injetando os processos relevantes no `tool_results_parts` no início da `event_generator`.

**Files:**
- Modify: `backend/routers/analista.py` (dentro da `event_generator`, logo após `tabelas` ser resolvido)

- [ ] **Step 1: Localizar o ponto de injeção**

No [analista.py](backend/routers/analista.py), dentro de `event_generator()`, encontrar o trecho onde `tabelas` já foi resolvido (após o bloco de `tool_resolver_contexto`, por volta da linha 530). É logo antes do loop `for tab in tabelas[:3]:`.

- [ ] **Step 2: Adicionar injeção de processos**

Inserir logo após `tool_results_parts` ser inicializado e `tabelas` estar populado (antes do loop de investigação):

```python
# Injetar processos detectados relevantes para as tabelas identificadas
if tabelas:
    try:
        from backend.services.analista_tools import tool_processos_cliente
        proc_result = await asyncio.to_thread(tool_processos_cliente, tabelas)
        if proc_result["processos"]:
            proc_lines = ["=== PROCESSOS DO CLIENTE NESTAS TABELAS ==="]
            for p in proc_result["processos"][:5]:
                tabs_str = ", ".join(p["tabelas"][:4])
                proc_lines.append(
                    f"- {p['nome']} ({p['tipo']}, {p['criticidade']}) "
                    f"[tabelas: {tabs_str}]: {p['descricao']}"
                )
            tool_results_parts.insert(0, "\n".join(proc_lines))
    except Exception:
        pass  # Processos são contexto adicional — falha silenciosa
```

**Onde exatamente inserir:** Buscar em [analista.py](backend/routers/analista.py) por `for tab in tabelas[:3]:` e inserir o bloco imediatamente antes.

- [ ] **Step 3: Verificar que os 3 endpoints de chat recebem a injeção**

O arquivo tem 3 funções de chat (`chat_conversa`, `chat_melhoria`, `chat_ajuste` ou equivalentes). Verificar com:
```
grep -n "for tab in tabelas" backend/routers/analista.py
```
Aplicar a injeção em cada ocorrência (geralmente 3 vezes — uma por modo de chat).

- [ ] **Step 4: Teste de integração manual**

Com a base Marfrig carregada:
1. Rodar `POST /analista/processos/descobrir` para popular o cache
2. Abrir o Analista e perguntar: "quero criar um campo na SC5"
3. Verificar que o contexto do LLM inclui a seção `=== PROCESSOS DO CLIENTE NESTAS TABELAS ===`

- [ ] **Step 5: Commit final**

```bash
git add backend/routers/analista.py
git commit -m "feat: injetar processos_detectados no contexto do Analista"
```

---

## Notas de implementação

### LLMService — verificar método correto para passo 5

Antes de Task 3, ler `backend/services/llm.py` para confirmar o método não-streaming:
- Se existe `.complete(prompt)` → usar direto
- Se só existe `.chat(messages)` → chamar com `[{"role": "user", "content": prompt}]`
- Ajustar `_passo5_llm` em `descoberta_processos.py` conforme necessário

### Onde inserir cada adição em `analista.py`

| O que | Onde buscar | O que adicionar |
|---|---|---|
| Endpoints | Antes de `@router.post("/conversas/{conversa_id}/chat")` | 2 novos endpoints |
| Injeção contexto | Antes de `for tab in tabelas[:3]:` (3 ocorrências) | Bloco `tool_processos_cliente` |

### Cache invalidation (futuro)

A invalidação do cache não está neste plano. Por ora: `force=True` via endpoint apaga e recalcula. No futuro, invalidar automaticamente após re-ingest.
