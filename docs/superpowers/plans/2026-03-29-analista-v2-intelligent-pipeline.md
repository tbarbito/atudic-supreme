# Analista V2 — Pipeline Inteligente de Investigação

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Substituir o pipeline linear do Analista por investigação iterativa com resolução semântica e acesso ao padrão + especialista em código.

**Architecture:** 5 fases (Compreensão → Resolução Semântica → Decisão de Rota → Investigação Iterativa → Resposta/Código). Novos módulos: `semantic_resolver.py`, `padrao_tools.py`, `code_specialist.py`. Refatoração do loop de chat em `analista.py`.

**Tech Stack:** Python 3, FastAPI, SQLite (extrairpo.db + padrao.db), SSE streaming, LLM function-calling via prompt estruturado.

**Spec:** `docs/superpowers/specs/2026-03-29-analista-v2-intelligent-pipeline-design.md`

---

## Chunk 0: Benchmark — Cenários de Teste de Regressão

Benchmark com 11 cenários que validam V1 (não quebrou) e V2 (funciona).

### Task 0: Benchmark já criado em `tests/test_benchmark_analista_v2.py`

**Files:**
- Created: `tests/test_benchmark_analista_v2.py`

**Cenários V1 (regressão — MUST NOT BREAK):**
- Cenário 1: Campo explícito (`C5_LIBEROK`) → regex detecta, operações retornam
- Cenário 2: Sinônimo V1 (`pedido de venda`) → resolver_contexto resolve
- Cenário 8: Mapear processo (`SC5.C5_LIBEROK`) → tool retorna estados/satélites
- Cenário 9: Classificador/Orchestrator → entity extraction funciona
- Cenário 10: Clarificação → ambiguidade detection funciona

**Cenários V2 (novo — MUST WORK):**
- Cenário 3: Resolução semântica (`aprovação do pedido`) → menus, propósitos, campos
- Cenário 4: Padrao tools (`MATA410`) → fonte, PEs, funções do padrão
- Cenário 5: Client tools extras → ler fonte, buscar menus, propósitos
- Cenário 6: Investigation loop → parsing, execução, tool descriptions
- Cenário 7: Code specialist → prompts, diagnóstico, geração
- Cenário 11: Smoke import → todos os módulos novos importáveis

**Como rodar:**
```bash
# Testes unitários (sem DB real)
python -m pytest tests/test_benchmark_analista_v2.py -v -k "not skip_no_dbs"

# Testes completos (com DB real — requer workspace/clients/marfrig/db/extrairpo.db)
python -m pytest tests/test_benchmark_analista_v2.py -v

# Só regressão V1
python -m pytest tests/test_benchmark_analista_v2.py -v -k "V1"

# Só novos V2
python -m pytest tests/test_benchmark_analista_v2.py -v -k "V2"
```

- [ ] **Step 1: Rodar benchmark ANTES de qualquer implementação V2**

Run: `cd d:/IA/Projetos/Protheus && python -m pytest tests/test_benchmark_analista_v2.py -v -k "V1"`
Expected: Cenários V1 passam (baseline). Cenários V2 falham (módulos não existem).

- [ ] **Step 2: Commit benchmark**

```bash
git add tests/test_benchmark_analista_v2.py
git commit -m "test(analista-v2): add benchmark — 11 scenarios for V1 regression + V2 validation"
```

---

## Chunk 1: Ferramentas do Padrão (padrao_tools.py)

Expor o padrao.db como ferramentas consultáveis pelo analista.

### Task 1: Criar `backend/services/padrao_tools.py` — acesso ao padrao.db

**Files:**
- Create: `backend/services/padrao_tools.py`
- Reference: `backend/services/padrao_database.py` (PadraoDB class)
- Reference: `backend/routers/padrao.py:394` (PADRAO_DB_PATH)
- Test: `tests/test_padrao_tools.py`

- [ ] **Step 1: Write failing tests for padrao_tools**

```python
# tests/test_padrao_tools.py
"""Tests for padrao_tools — standard source query tools."""
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path


@pytest.fixture
def mock_padrao_db():
    """Mock PadraoDB with sample data."""
    db = MagicMock()
    db.get_conn.return_value = db
    return db


class TestToolFontePadrao:
    def test_returns_metadata_and_functions(self, mock_padrao_db):
        from backend.services.padrao_tools import tool_fonte_padrao
        mock_padrao_db.execute.return_value.fetchone.return_value = {
            "arquivo": "MATA410.prw", "modulo": "faturamento",
            "lines_of_code": 5000, "tipo": "prw",
        }
        mock_padrao_db.execute.return_value.fetchall.return_value = [
            {"nome": "A410Grava", "tipo": "static", "assinatura": "A410Grava()"},
        ]
        with patch("backend.services.padrao_tools._get_padrao_db", return_value=mock_padrao_db):
            result = tool_fonte_padrao("MATA410")
        assert result["arquivo"] == "MATA410.prw"
        assert len(result["funcoes"]) >= 1

    def test_not_found_returns_empty(self, mock_padrao_db):
        from backend.services.padrao_tools import tool_fonte_padrao
        mock_padrao_db.execute.return_value.fetchone.return_value = None
        with patch("backend.services.padrao_tools._get_padrao_db", return_value=mock_padrao_db):
            result = tool_fonte_padrao("NAOEXISTE")
        assert result.get("encontrado") is False


class TestToolPesDisponiveis:
    def test_returns_execblocks_for_routine(self, mock_padrao_db):
        from backend.services.padrao_tools import tool_pes_disponiveis
        mock_padrao_db.execute.return_value.fetchall.return_value = [
            {"nome_pe": "MA410COR", "funcao": "A410Grava", "arquivo": "MATA410.prw",
             "parametros": "{aCols, aHeader}", "tipo_retorno_inferido": "array",
             "linha": 245, "operacao": "inclusao", "contexto": "antes da gravação"},
        ]
        with patch("backend.services.padrao_tools._get_padrao_db", return_value=mock_padrao_db):
            result = tool_pes_disponiveis("MATA410")
        assert len(result) >= 1
        assert result[0]["nome_pe"] == "MA410COR"


class TestToolCodigoPe:
    def test_returns_source_snippet(self, mock_padrao_db):
        from backend.services.padrao_tools import tool_codigo_pe
        mock_padrao_db.search_pe.return_value = [
            {"nome_pe": "MA410COR", "arquivo": "MATA410.prw", "funcao": "A410Grava", "linha": 245}
        ]
        mock_padrao_db.execute.return_value.fetchone.return_value = {"caminho": "/fake/path"}
        with patch("backend.services.padrao_tools._get_padrao_db", return_value=mock_padrao_db):
            with patch("builtins.open", side_effect=FileNotFoundError):
                result = tool_codigo_pe("MA410COR")
        assert len(result) >= 1


class TestToolBuscarFuncaoPadrao:
    def test_searches_by_name(self, mock_padrao_db):
        from backend.services.padrao_tools import tool_buscar_funcao_padrao
        mock_padrao_db.search_funcao.return_value = [
            {"nome": "A410Grava", "tipo": "static", "arquivo": "MATA410.prw",
             "assinatura": "A410Grava()", "linha_inicio": 200},
        ]
        with patch("backend.services.padrao_tools._get_padrao_db", return_value=mock_padrao_db):
            result = tool_buscar_funcao_padrao("A410Grava")
        assert len(result) >= 1
        assert result[0]["nome"] == "A410Grava"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd d:/IA/Projetos/Protheus && python -m pytest tests/test_padrao_tools.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.services.padrao_tools'`

- [ ] **Step 3: Implement `padrao_tools.py`**

```python
# backend/services/padrao_tools.py
"""Tools to query the standard Protheus source database (padrao.db).

These tools expose padrao.db data for the Analista pipeline —
standard source metadata, ExecBlocks (PEs), functions, and source code snippets.
"""
import json
from pathlib import Path
from backend.services.padrao_database import PadraoDB

PADRAO_DB_PATH = Path("workspace") / "padrao" / "db" / "padrao.db"


def _get_padrao_db() -> PadraoDB:
    db = PadraoDB(PADRAO_DB_PATH)
    db.initialize()
    return db


def tool_fonte_padrao(arquivo: str) -> dict:
    """Get metadata and functions for a standard source file.

    Args:
        arquivo: Source filename (e.g., 'MATA410' or 'MATA410.prw')

    Returns:
        {arquivo, modulo, lines_of_code, tipo, funcoes: [{nome, tipo, assinatura}], encontrado}
    """
    if not PADRAO_DB_PATH.exists():
        return {"encontrado": False, "msg": "padrao.db not found"}

    db = _get_padrao_db()
    try:
        # Normalize: add .prw if not present, try both cases
        arquivo_clean = arquivo.strip()
        if "." not in arquivo_clean:
            arquivo_clean += ".prw"

        fonte = db.execute(
            "SELECT arquivo, modulo, lines_of_code, tipo FROM fontes WHERE UPPER(arquivo) LIKE ?",
            (f"%{arquivo_clean.upper().replace('.PRW', '')}%",)
        ).fetchone()

        if not fonte:
            return {"encontrado": False, "arquivo": arquivo}

        funcoes = db.execute(
            "SELECT nome, tipo, assinatura, linha_inicio FROM funcoes WHERE arquivo = ? ORDER BY linha_inicio",
            (fonte["arquivo"],)
        ).fetchall()

        return {
            "encontrado": True,
            "arquivo": fonte["arquivo"],
            "modulo": fonte["modulo"] or "",
            "lines_of_code": fonte["lines_of_code"] or 0,
            "tipo": fonte["tipo"] or "",
            "funcoes": [
                {"nome": f["nome"], "tipo": f["tipo"], "assinatura": f["assinatura"] or "",
                 "linha": f["linha_inicio"] or 0}
                for f in funcoes
            ],
        }
    finally:
        db.close()


def tool_pes_disponiveis(rotina: str) -> list[dict]:
    """List all ExecBlocks (entry points) available in a standard routine.

    Args:
        rotina: Routine name (e.g., 'MATA410')

    Returns:
        List of {nome_pe, funcao, arquivo, parametros, tipo_retorno_inferido, linha, operacao, contexto}
    """
    if not PADRAO_DB_PATH.exists():
        return []

    db = _get_padrao_db()
    try:
        rotina_clean = rotina.strip().upper()
        if "." not in rotina_clean:
            rotina_clean += ".PRW"

        # Search in execblocks by arquivo
        rows = db.execute(
            "SELECT nome_pe, funcao, arquivo, parametros, tipo_retorno_inferido, "
            "linha, operacao, contexto, comentario "
            "FROM execblocks WHERE UPPER(arquivo) LIKE ? ORDER BY linha",
            (f"%{rotina_clean.replace('.PRW', '')}%",)
        ).fetchall()

        return [
            {
                "nome_pe": r["nome_pe"],
                "funcao": r["funcao"],
                "arquivo": r["arquivo"],
                "parametros": r["parametros"] or "",
                "tipo_retorno": r["tipo_retorno_inferido"] or "nil",
                "linha": r["linha"] or 0,
                "operacao": r["operacao"] or "",
                "contexto": r["contexto"] or "",
                "comentario": r["comentario"] or "",
            }
            for r in rows
        ]
    finally:
        db.close()


def tool_codigo_pe(nome_pe: str) -> list[dict]:
    """Get the source code snippet around where a PE is called in the standard source.

    Args:
        nome_pe: PE name (e.g., 'MA410COR')

    Returns:
        List of {nome_pe, arquivo, funcao, linha, codigo, parametros, tipo_retorno}
    """
    if not PADRAO_DB_PATH.exists():
        return []

    db = _get_padrao_db()
    try:
        pes = db.search_pe(nome_pe)
        if not pes:
            return []

        results = []
        for pe in pes[:5]:  # Limit to 5 occurrences
            fonte = db.execute(
                "SELECT caminho FROM fontes WHERE arquivo = ?", (pe["arquivo"],)
            ).fetchone()

            codigo = "[Arquivo não encontrado]"
            if fonte:
                file_path = Path(fonte["caminho"])
                if file_path.exists():
                    try:
                        from backend.services.padrao_parser import _read_file
                        content = _read_file(file_path)
                        lines = content.split('\n')
                        pe_line = pe["linha"] - 1
                        start = max(0, pe_line - 10)
                        end = min(len(lines), pe_line + 20)
                        code_lines = []
                        for idx in range(start, end):
                            marker = " >>> " if idx == pe_line else "     "
                            code_lines.append(f"{idx + 1:5d}{marker}{lines[idx]}")
                        codigo = '\n'.join(code_lines)
                    except Exception:
                        codigo = "[Erro ao ler arquivo]"

            results.append({
                "nome_pe": pe["nome_pe"],
                "arquivo": pe["arquivo"],
                "funcao": pe["funcao"],
                "linha": pe["linha"],
                "parametros": pe.get("parametros", ""),
                "tipo_retorno": pe.get("tipo_retorno_inferido", "nil"),
                "operacao": pe.get("operacao", ""),
                "codigo": codigo,
            })

        return results
    finally:
        db.close()


def tool_buscar_funcao_padrao(nome: str) -> list[dict]:
    """Search functions in the standard source database.

    Args:
        nome: Function name or partial name

    Returns:
        List of {nome, tipo, arquivo, assinatura, linha}
    """
    if not PADRAO_DB_PATH.exists():
        return []

    db = _get_padrao_db()
    try:
        results = db.search_funcao(nome)
        return [
            {
                "nome": r["nome"],
                "tipo": r.get("tipo", ""),
                "arquivo": r["arquivo"],
                "assinatura": r.get("assinatura", ""),
                "linha": r.get("linha_inicio", 0),
            }
            for r in results[:20]  # Limit results
        ]
    finally:
        db.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd d:/IA/Projetos/Protheus && python -m pytest tests/test_padrao_tools.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/padrao_tools.py tests/test_padrao_tools.py
git commit -m "feat(analista-v2): add padrao_tools — standard source query tools"
```

---

## Chunk 2: Resolução Semântica (semantic_resolver.py)

Substituir o dicionário de sinônimos hardcoded por busca real nos dados do ambiente do cliente.

### Task 2: Criar `backend/services/semantic_resolver.py`

**Files:**
- Create: `backend/services/semantic_resolver.py`
- Reference: `backend/services/analista_tools.py:474` (tool_resolver_contexto atual)
- Reference: `backend/services/database.py` (Database class, tabelas menus/propositos)
- Test: `tests/test_semantic_resolver.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_semantic_resolver.py
"""Tests for semantic_resolver — resolve vague user messages to Protheus entities."""
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_db():
    db = MagicMock()
    return db


class TestBuscarMenus:
    def test_finds_menu_by_keyword(self, mock_db):
        from backend.services.semantic_resolver import _buscar_menus
        mock_db.execute.return_value.fetchall.return_value = [
            ("SIGAGCT", "MATA440", "Liberação de Pedidos", "Atualizações > Vendas"),
        ]
        result = _buscar_menus(db=mock_db, termos=["liberação", "pedido"])
        assert len(result) >= 1
        assert result[0]["rotina"] == "MATA440"


class TestBuscarPropositos:
    def test_finds_fonte_by_proposito(self, mock_db):
        from backend.services.semantic_resolver import _buscar_propositos
        mock_db.execute.return_value.fetchall.return_value = [
            ("MGFFAT16.prw", '{"humano": "validações de crédito para aprovação de pedido"}'),
        ]
        result = _buscar_propositos(db=mock_db, termos=["aprovação", "pedido"])
        assert len(result) >= 1
        assert "MGFFAT16" in result[0]["arquivo"]


class TestBuscarCamposPorTitulo:
    def test_finds_campo_by_title(self, mock_db):
        from backend.services.semantic_resolver import _buscar_campos_por_titulo
        mock_db.execute.return_value.fetchall.return_value = [
            ("SC5", "C5_LIBEROK", "Liberado", "C", "1"),
        ]
        result = _buscar_campos_por_titulo(db=mock_db, termos=["liberado"])
        assert len(result) >= 1
        assert result[0]["campo"] == "C5_LIBEROK"


class TestResolverSemantico:
    def test_full_resolution_with_candidates(self, mock_db):
        from backend.services.semantic_resolver import resolver_semantico
        # Mock menus
        mock_db.execute.return_value.fetchall.side_effect = [
            # menus
            [("SIGAGCT", "MATA440", "Liberação de Pedidos", "Atualizações > Vendas")],
            # propositos
            [("MGFFAT16.prw", '{"humano": "aprovação de pedido de venda"}')],
            # processos
            [],
            # campos
            [("SC5", "C5_LIBEROK", "Liberado", "C", "1")],
        ]
        with patch("backend.services.semantic_resolver._get_db", return_value=mock_db):
            result = resolver_semantico("problema na aprovação do pedido de venda")

        assert len(result["candidatos"]) >= 1
        assert result["resolvido"] is True

    def test_no_candidates_returns_empty(self, mock_db):
        from backend.services.semantic_resolver import resolver_semantico
        mock_db.execute.return_value.fetchall.return_value = []
        with patch("backend.services.semantic_resolver._get_db", return_value=mock_db):
            result = resolver_semantico("xyzzy foobar")
        assert result["resolvido"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd d:/IA/Projetos/Protheus && python -m pytest tests/test_semantic_resolver.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement `semantic_resolver.py`**

```python
# backend/services/semantic_resolver.py
"""Semantic resolver — translate vague user messages into concrete Protheus entities.

Uses 5 data sources from the client environment:
1. Menus (43K entries) — match routine names by keyword
2. Propósitos (8K fonte summaries) — semantic match on AI-generated descriptions
3. Processos detectados — known client workflows
4. Campos por título — field names matching keywords
5. Padrão (padrao.db) — standard routines by name

Returns ranked candidates: [{tabela, campo, rotina, fontes, confiança, descrição}]
"""
import json
import re
from pathlib import Path
from backend.services.config import load_config, get_client_workspace
from backend.services.database import Database

WORKSPACE = Path("workspace")
CONFIG_PATH = Path("config.json")

# Words to exclude from search
_STOPWORDS = {
    "tem", "uma", "um", "que", "de", "do", "da", "dos", "das", "no", "na",
    "nos", "nas", "ao", "para", "por", "com", "sem", "mas", "acho", "algo",
    "assim", "isso", "esta", "pode", "verificar", "parece", "usuario", "tela",
    "salva", "salvar", "alterado", "alterar", "campo", "rotina", "programa",
    "fonte", "quando", "nao", "valor", "tipo", "tambem", "deveria", "antes",
    "depois", "ainda", "sempre", "nunca", "estou", "problema", "erro",
    "como", "qual", "onde", "porque", "esta", "estamos", "preciso",
}


def _get_db() -> Database:
    config = load_config(CONFIG_PATH)
    client_dir = get_client_workspace(WORKSPACE, config.active_client)
    db_path = client_dir / "db" / "extrairpo.db"
    db = Database(db_path)
    db.initialize()
    return db


def _extrair_termos(mensagem: str) -> list[str]:
    """Extract meaningful search terms from user message."""
    words = re.findall(r'\b(\w{3,})\b', mensagem.lower())
    return [w for w in words if w not in _STOPWORDS]


def _buscar_menus(db: Database, termos: list[str]) -> list[dict]:
    """Search menus table for routines matching terms."""
    results = []
    seen_rotinas = set()

    for termo in termos:
        rows = db.execute(
            "SELECT modulo, rotina, nome, menu FROM menus "
            "WHERE LOWER(nome) LIKE ? ORDER BY nome LIMIT 10",
            (f"%{termo}%",)
        ).fetchall()

        for r in rows:
            rotina = r[1]
            if rotina not in seen_rotinas:
                seen_rotinas.add(rotina)
                # Find tables this routine writes
                fonte = db.execute(
                    "SELECT write_tables, tabelas_ref FROM fontes WHERE UPPER(arquivo) LIKE ? LIMIT 1",
                    (f"%{rotina.upper()}%",)
                ).fetchone()
                write_tables = []
                if fonte and fonte[0]:
                    try:
                        write_tables = json.loads(fonte[0])
                    except (json.JSONDecodeError, TypeError):
                        pass

                results.append({
                    "tipo": "menu",
                    "rotina": rotina,
                    "nome": r[2],
                    "modulo": r[0],
                    "menu_path": r[3] or "",
                    "tabelas": write_tables,
                })

    return results


def _buscar_propositos(db: Database, termos: list[str]) -> list[dict]:
    """Search fonte propósitos (AI-generated summaries) for matching terms."""
    results = []
    seen = set()

    # Build LIKE clauses for each term
    conditions = " AND ".join(["LOWER(proposito) LIKE ?"] * len(termos))
    params = tuple(f"%{t}%" for t in termos)

    if not termos:
        return []

    # Try all terms together first (highest precision)
    rows = db.execute(
        f"SELECT chave, proposito FROM propositos WHERE {conditions} LIMIT 10",
        params
    ).fetchall()

    # If no results with all terms, try pairs
    if not rows and len(termos) >= 2:
        for i in range(len(termos)):
            for j in range(i + 1, len(termos)):
                pair_rows = db.execute(
                    "SELECT chave, proposito FROM propositos "
                    "WHERE LOWER(proposito) LIKE ? AND LOWER(proposito) LIKE ? LIMIT 5",
                    (f"%{termos[i]}%", f"%{termos[j]}%")
                ).fetchall()
                rows.extend(pair_rows)

    for r in rows:
        arquivo = r[0]
        if arquivo in seen:
            continue
        seen.add(arquivo)

        proposito_text = ""
        try:
            p = json.loads(r[1])
            proposito_text = p.get("humano", "")[:200]
        except (json.JSONDecodeError, TypeError):
            proposito_text = (r[1] or "")[:200]

        # Get fonte metadata
        fonte = db.execute(
            "SELECT modulo, write_tables FROM fontes WHERE UPPER(arquivo) = ? LIMIT 1",
            (arquivo.upper(),)
        ).fetchone()

        tabelas = []
        if fonte and fonte[1]:
            try:
                tabelas = json.loads(fonte[1])
            except (json.JSONDecodeError, TypeError):
                pass

        results.append({
            "tipo": "proposito",
            "arquivo": arquivo,
            "proposito": proposito_text,
            "modulo": fonte[0] if fonte else "",
            "tabelas": tabelas,
        })

    return results[:10]


def _buscar_campos_por_titulo(db: Database, termos: list[str]) -> list[dict]:
    """Search fields by title/description matching terms."""
    results = []
    seen = set()

    for termo in termos:
        if len(termo) < 4:  # Skip very short terms
            continue
        rows = db.execute(
            "SELECT tabela, campo, titulo, tipo, tamanho FROM campos "
            "WHERE (LOWER(titulo) LIKE ? OR LOWER(campo) LIKE ?) "
            "AND custom = 0 LIMIT 10",
            (f"%{termo}%", f"%{termo}%")
        ).fetchall()
        for r in rows:
            key = f"{r[0]}.{r[1]}"
            if key not in seen:
                seen.add(key)
                results.append({
                    "tipo": "campo",
                    "tabela": r[0],
                    "campo": r[1],
                    "titulo": r[2] or "",
                    "tipo_campo": r[3] or "",
                    "tamanho": r[4] or "",
                })

    return results[:20]


def _buscar_processos(db: Database, termos: list[str]) -> list[dict]:
    """Search detected client processes."""
    results = []

    try:
        count = db.execute("SELECT COUNT(*) FROM processos_detectados").fetchone()[0]
        if count == 0:
            return []
    except Exception:
        return []

    for termo in termos:
        rows = db.execute(
            "SELECT nome, tipo, descricao, tabelas, score FROM processos_detectados "
            "WHERE LOWER(nome) LIKE ? OR LOWER(descricao) LIKE ? "
            "ORDER BY score DESC LIMIT 5",
            (f"%{termo}%", f"%{termo}%")
        ).fetchall()
        for r in rows:
            tabelas = []
            try:
                tabelas = json.loads(r[3]) if r[3] else []
            except (json.JSONDecodeError, TypeError):
                pass
            results.append({
                "tipo": "processo",
                "nome": r[0],
                "tipo_processo": r[1],
                "descricao": (r[2] or "")[:150],
                "tabelas": tabelas,
                "score": r[4] or 0,
            })

    return results[:5]


def _agrupar_candidatos(menus, propositos, processos, campos) -> list[dict]:
    """Group results from all sources into ranked candidates.

    A candidate is a {tabela, rotina, fontes, confiança, descrição} that represents
    one possible interpretation of what the user meant.

    Candidates that appear in multiple sources get boosted confidence.
    """
    # Build a map: tabela → evidence
    tabela_evidence = {}

    for m in menus:
        for tab in m.get("tabelas", []):
            tab = tab.upper()
            if tab not in tabela_evidence:
                tabela_evidence[tab] = {"fontes_evidencia": [], "rotinas": set(), "modulos": set(), "descricoes": []}
            tabela_evidence[tab]["fontes_evidencia"].append("menu")
            tabela_evidence[tab]["rotinas"].add(m["rotina"])
            tabela_evidence[tab]["modulos"].add(m.get("modulo", ""))
            tabela_evidence[tab]["descricoes"].append(f"Menu: {m['nome']} ({m.get('menu_path', '')})")

    for p in propositos:
        for tab in p.get("tabelas", []):
            tab = tab.upper()
            if tab not in tabela_evidence:
                tabela_evidence[tab] = {"fontes_evidencia": [], "rotinas": set(), "modulos": set(), "descricoes": []}
            tabela_evidence[tab]["fontes_evidencia"].append("proposito")
            tabela_evidence[tab]["descricoes"].append(f"Fonte: {p['arquivo']} — {p['proposito'][:100]}")

    for proc in processos:
        for tab in proc.get("tabelas", []):
            tab = tab.upper()
            if tab not in tabela_evidence:
                tabela_evidence[tab] = {"fontes_evidencia": [], "rotinas": set(), "modulos": set(), "descricoes": []}
            tabela_evidence[tab]["fontes_evidencia"].append("processo")
            tabela_evidence[tab]["descricoes"].append(f"Processo: {proc['nome']} — {proc['descricao'][:100]}")

    for c in campos:
        tab = c["tabela"].upper()
        if tab not in tabela_evidence:
            tabela_evidence[tab] = {"fontes_evidencia": [], "rotinas": set(), "modulos": set(), "descricoes": []}
        tabela_evidence[tab]["fontes_evidencia"].append("campo")
        tabela_evidence[tab]["descricoes"].append(f"Campo: {c['campo']} ({c['titulo']})")

    # Score candidates: more sources = higher confidence
    candidatos = []
    for tab, ev in tabela_evidence.items():
        n_sources = len(set(ev["fontes_evidencia"]))
        confianca = min(1.0, 0.3 + (n_sources * 0.2))

        # Get table name
        campos_do_tab = [c for c in campos if c["tabela"].upper() == tab]

        candidatos.append({
            "tabela": tab,
            "rotinas": sorted(ev["rotinas"]),
            "modulos": sorted(ev["modulos"] - {""}),
            "campos_relevantes": [c["campo"] for c in campos_do_tab[:5]],
            "confianca": round(confianca, 2),
            "evidencias": len(ev["fontes_evidencia"]),
            "descricao": ev["descricoes"][0] if ev["descricoes"] else "",
            "todas_descricoes": ev["descricoes"][:5],
        })

    # Sort by confidence (desc), then by evidence count
    candidatos.sort(key=lambda x: (-x["confianca"], -x["evidencias"]))

    return candidatos[:10]


def resolver_semantico(mensagem: str, entidades_explicitas: dict = None) -> dict:
    """Main entry point: resolve a vague user message into concrete Protheus entities.

    Args:
        mensagem: Raw user message
        entidades_explicitas: Already-detected entities from classifier (optional)

    Returns:
        {
            resolvido: bool,
            termos: [str],
            candidatos: [{tabela, rotinas, campos_relevantes, confianca, descricao}],
            menus: [...],
            propositos: [...],
            processos: [...],
            campos: [...],
        }
    """
    termos = _extrair_termos(mensagem)
    if not termos:
        return {"resolvido": False, "termos": [], "candidatos": []}

    db = _get_db()
    try:
        menus = _buscar_menus(db, termos)
        propositos = _buscar_propositos(db, termos)
        processos = _buscar_processos(db, termos)
        campos = _buscar_campos_por_titulo(db, termos)

        candidatos = _agrupar_candidatos(menus, propositos, processos, campos)

        return {
            "resolvido": len(candidatos) > 0,
            "termos": termos,
            "candidatos": candidatos,
            "menus": menus,
            "propositos": propositos,
            "processos": processos,
            "campos": campos,
        }
    finally:
        db.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd d:/IA/Projetos/Protheus && python -m pytest tests/test_semantic_resolver.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/semantic_resolver.py tests/test_semantic_resolver.py
git commit -m "feat(analista-v2): add semantic_resolver — resolve vague messages to entities"
```

---

## Chunk 3: Ferramentas Extras do Cliente

Novas tools para ler fonte cliente e buscar menus/propósitos via analista_tools.

### Task 3: Adicionar tools em `backend/services/analista_tools.py`

**Files:**
- Modify: `backend/services/analista_tools.py` (append new functions at end)
- Test: `tests/test_analista_tools_new.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_analista_tools_new.py
"""Tests for new analista tools: ler_fonte_cliente, buscar_menus, buscar_propositos."""
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_db():
    db = MagicMock()
    return db


class TestToolLerFonteCliente:
    def test_reads_chunk_content(self, mock_db):
        from backend.services.analista_tools import tool_ler_fonte_cliente
        mock_db.execute.return_value.fetchone.return_value = (
            "A010TOK.PRW::A010TOK", "A010TOK.PRW", "A010TOK",
            "User Function A010TOK\n  local lRet := .T.\n  Return lRet"
        )
        with patch("backend.services.analista_tools._get_db", return_value=mock_db):
            result = tool_ler_fonte_cliente("A010TOK.PRW", "A010TOK")
        assert "User Function" in result["content"]

    def test_not_found_returns_empty(self, mock_db):
        from backend.services.analista_tools import tool_ler_fonte_cliente
        mock_db.execute.return_value.fetchone.return_value = None
        with patch("backend.services.analista_tools._get_db", return_value=mock_db):
            result = tool_ler_fonte_cliente("NAOEXISTE.prw", "NAOEXISTE")
        assert result.get("encontrado") is False


class TestToolBuscarMenus:
    def test_finds_menu_by_term(self, mock_db):
        from backend.services.analista_tools import tool_buscar_menus
        mock_db.execute.return_value.fetchall.return_value = [
            ("SIGAGCT", "MATA440", "Liberação de Pedidos", "Atualizações > Vendas", 1),
        ]
        with patch("backend.services.analista_tools._get_db", return_value=mock_db):
            result = tool_buscar_menus("liberação pedido")
        assert len(result) >= 1


class TestToolBuscarPropositos:
    def test_finds_fonte_by_proposito(self, mock_db):
        from backend.services.analista_tools import tool_buscar_propositos
        mock_db.execute.return_value.fetchall.return_value = [
            ("MGFFAT16.prw", '{"humano": "aprovação de pedido de venda"}'),
        ]
        with patch("backend.services.analista_tools._get_db", return_value=mock_db):
            result = tool_buscar_propositos("aprovação pedido")
        assert len(result) >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd d:/IA/Projetos/Protheus && python -m pytest tests/test_analista_tools_new.py -v`
Expected: FAIL — functions not defined

- [ ] **Step 3: Append new tools to `analista_tools.py`**

Add at the end of `backend/services/analista_tools.py`:

```python
# ─────────────────────── V2 Tools: Source Reading & Search ───────────────────────


def tool_ler_fonte_cliente(arquivo: str, funcao: str = "") -> dict:
    """Read actual source code chunk from client fonte_chunks.

    Args:
        arquivo: Source filename (e.g., 'MGFFAT16.prw')
        funcao: Specific function name (optional — if empty, returns all chunks for file)

    Returns:
        {encontrado, arquivo, funcao, content} or {encontrado: False}
    """
    db = _get_db()
    try:
        if funcao:
            row = db.execute(
                "SELECT id, arquivo, funcao, content FROM fonte_chunks "
                "WHERE UPPER(arquivo) = ? AND UPPER(funcao) = ? LIMIT 1",
                (arquivo.upper(), funcao.upper())
            ).fetchone()
            if row:
                return {"encontrado": True, "arquivo": row[1], "funcao": row[2], "content": row[3]}
        else:
            rows = db.execute(
                "SELECT funcao, content FROM fonte_chunks WHERE UPPER(arquivo) = ? ORDER BY id",
                (arquivo.upper(),)
            ).fetchall()
            if rows:
                combined = "\n\n".join(f"// === {r[0]} ===\n{r[1]}" for r in rows)
                return {"encontrado": True, "arquivo": arquivo, "funcao": "(all)", "content": combined[:6000]}

        return {"encontrado": False, "arquivo": arquivo, "funcao": funcao}
    finally:
        db.close()


def tool_buscar_menus(termo: str) -> list[dict]:
    """Search client menus by keyword.

    Args:
        termo: Search term (e.g., 'liberação pedido')

    Returns:
        List of {modulo, rotina, nome, menu_path}
    """
    db = _get_db()
    try:
        words = [w for w in termo.lower().split() if len(w) >= 3]
        if not words:
            return []

        conditions = " AND ".join(["LOWER(nome) LIKE ?"] * len(words))
        params = tuple(f"%{w}%" for w in words)

        rows = db.execute(
            f"SELECT modulo, rotina, nome, menu FROM menus WHERE {conditions} ORDER BY nome LIMIT 15",
            params
        ).fetchall()

        return [
            {"modulo": r[0], "rotina": r[1], "nome": r[2], "menu_path": r[3] or ""}
            for r in rows
        ]
    finally:
        db.close()


def tool_buscar_propositos(termo: str) -> list[dict]:
    """Search fonte propósitos (AI-generated summaries) by keyword.

    Args:
        termo: Search term (e.g., 'aprovação pedido')

    Returns:
        List of {arquivo, proposito, modulo}
    """
    db = _get_db()
    try:
        words = [w for w in termo.lower().split() if len(w) >= 3]
        if not words:
            return []

        conditions = " AND ".join(["LOWER(proposito) LIKE ?"] * len(words))
        params = tuple(f"%{w}%" for w in words)

        rows = db.execute(
            f"SELECT chave, substr(proposito, 1, 300) FROM propositos WHERE {conditions} LIMIT 10",
            params
        ).fetchall()

        results = []
        for r in rows:
            proposito_text = ""
            try:
                p = json.loads(r[1])
                proposito_text = p.get("humano", "")[:200]
            except (json.JSONDecodeError, TypeError):
                proposito_text = (r[1] or "")[:200]

            fonte = db.execute(
                "SELECT modulo FROM fontes WHERE UPPER(arquivo) = ? LIMIT 1",
                (r[0].upper(),)
            ).fetchone()

            results.append({
                "arquivo": r[0],
                "proposito": proposito_text,
                "modulo": fonte[0] if fonte else "",
            })

        return results
    finally:
        db.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd d:/IA/Projetos/Protheus && python -m pytest tests/test_analista_tools_new.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/analista_tools.py tests/test_analista_tools_new.py
git commit -m "feat(analista-v2): add client tools — ler_fonte, buscar_menus, buscar_propositos"
```

---

## Chunk 4: Investigação Iterativa (investigation_loop.py)

O loop onde o LLM decide qual ferramenta chamar a cada passo.

### Task 4: Criar `backend/services/investigation_loop.py`

**Files:**
- Create: `backend/services/investigation_loop.py`
- Reference: `backend/services/analista_tools.py` (existing tools)
- Reference: `backend/services/padrao_tools.py` (new tools from Task 1)
- Test: `tests/test_investigation_loop.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_investigation_loop.py
"""Tests for investigation_loop — iterative LLM-driven investigation."""
import pytest
import json
from unittest.mock import MagicMock, AsyncMock, patch


class TestParseToolCall:
    def test_parses_valid_tool_call(self):
        from backend.services.investigation_loop import _parse_tool_call
        llm_response = '{"tool": "quem_grava", "args": {"tabela": "SC6", "campo": "C6_DESCONT"}}'
        result = _parse_tool_call(llm_response)
        assert result["tool"] == "quem_grava"
        assert result["args"]["tabela"] == "SC6"

    def test_parses_pronto(self):
        from backend.services.investigation_loop import _parse_tool_call
        result = _parse_tool_call('{"tool": "pronto"}')
        assert result["tool"] == "pronto"

    def test_handles_invalid_json(self):
        from backend.services.investigation_loop import _parse_tool_call
        result = _parse_tool_call("I think we should look at SC6")
        assert result["tool"] == "pronto"  # Fallback: respond directly


class TestExecuteTool:
    def test_executes_known_tool(self):
        from backend.services.investigation_loop import _execute_tool
        with patch("backend.services.investigation_loop.TOOL_MAP") as mock_map:
            mock_map.__contains__ = lambda s, k: True
            mock_map.__getitem__ = lambda s, k: lambda **kw: {"result": "ok"}
            result = _execute_tool("quem_grava", {"tabela": "SC6"})
            assert "result" in result

    def test_unknown_tool_returns_error(self):
        from backend.services.investigation_loop import _execute_tool
        result = _execute_tool("nonexistent_tool", {})
        assert "error" in result or "erro" in str(result).lower()


class TestBuildToolDescriptions:
    def test_returns_formatted_tool_list(self):
        from backend.services.investigation_loop import build_tool_descriptions
        desc = build_tool_descriptions()
        assert "quem_grava" in desc
        assert "fonte_padrao" in desc
        assert "pronto" in desc
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd d:/IA/Projetos/Protheus && python -m pytest tests/test_investigation_loop.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement `investigation_loop.py`**

```python
# backend/services/investigation_loop.py
"""Iterative investigation loop — LLM decides which tool to call at each step.

The LLM receives minimal initial context and requests specific tools
in a loop (max MAX_STEPS). Each tool result accumulates in context.
When the LLM has enough information, it signals 'pronto' to exit.
"""
import json
import asyncio
from typing import AsyncGenerator

from backend.services import analista_tools as at
from backend.services import padrao_tools as pt

MAX_STEPS = 5

# ── Tool registry ──────────────────────────────────────────────────────────

TOOL_MAP = {
    # Client tools
    "quem_grava": lambda **kw: at.tool_quem_grava_campo(kw.get("tabela", ""), kw.get("campo", "")),
    "info_tabela": lambda **kw: at.tool_info_tabela(kw.get("tabela", "")),
    "operacoes_escrita": lambda **kw: at.tool_operacoes_tabela(kw.get("tabela", "")),
    "rastrear_condicao": lambda **kw: at.tool_investigar_condicao(
        kw.get("arquivo", ""), kw.get("funcao", ""), kw.get("variavel", "")
    ),
    "ver_parametro": lambda **kw: at.tool_buscar_parametros(termo=kw.get("nome", ""), tabela=""),
    "ver_fonte_cliente": lambda **kw: at.tool_ler_fonte_cliente(kw.get("arquivo", ""), kw.get("funcao", "")),
    "buscar_pes_cliente": lambda **kw: at.tool_buscar_pes(rotina=kw.get("rotina", ""), modulo=kw.get("modulo", "")),
    "mapear_processo": lambda **kw: at.tool_mapear_processo(kw.get("tabela", ""), kw.get("campo", "")),
    "buscar_menus": lambda **kw: at.tool_buscar_menus(kw.get("termo", "")),
    "buscar_propositos": lambda **kw: at.tool_buscar_propositos(kw.get("termo", "")),
    "processos_cliente": lambda **kw: at.tool_processos_cliente(kw.get("tabelas")),
    "jobs_schedules": lambda **kw: {
        "jobs": at.tool_buscar_jobs(rotina=kw.get("rotina", "")),
        "schedules": at.tool_buscar_schedules(rotina=kw.get("rotina", "")),
    },
    # Padrão tools
    "fonte_padrao": lambda **kw: pt.tool_fonte_padrao(kw.get("arquivo", "")),
    "pes_disponiveis": lambda **kw: pt.tool_pes_disponiveis(kw.get("rotina", "")),
    "codigo_pe": lambda **kw: pt.tool_codigo_pe(kw.get("nome_pe", "")),
    "buscar_funcao_padrao": lambda **kw: pt.tool_buscar_funcao_padrao(kw.get("nome", "")),
}

TOOL_DESCRIPTIONS = {
    "quem_grava": {"desc": "Quem grava em tabela/campo (pontos de escrita)", "args": "tabela, campo?"},
    "info_tabela": {"desc": "Metadata da tabela (campos, índices, custom)", "args": "tabela"},
    "operacoes_escrita": {"desc": "Resumo de todas operações de escrita na tabela", "args": "tabela"},
    "rastrear_condicao": {"desc": "Backward trace: de onde vem uma variável de condição", "args": "arquivo, funcao, variavel"},
    "ver_parametro": {"desc": "Consultar parâmetro SX6 (valor atual + descrição)", "args": "nome"},
    "ver_fonte_cliente": {"desc": "Ler código real de fonte do cliente", "args": "arquivo, funcao?"},
    "buscar_pes_cliente": {"desc": "PEs implementados pelo cliente", "args": "rotina?, modulo?"},
    "mapear_processo": {"desc": "Mapa COMPLETO do processo (estados, satélites, companheiros)", "args": "tabela, campo"},
    "buscar_menus": {"desc": "Buscar rotinas nos menus do cliente", "args": "termo"},
    "buscar_propositos": {"desc": "Buscar fontes por propósito/descrição", "args": "termo"},
    "processos_cliente": {"desc": "Processos de negócio detectados", "args": "tabelas?"},
    "jobs_schedules": {"desc": "Jobs e schedules da rotina", "args": "rotina"},
    "fonte_padrao": {"desc": "Metadata + funções de fonte PADRÃO Protheus", "args": "arquivo"},
    "pes_disponiveis": {"desc": "PEs disponíveis na rotina PADRÃO (ExecBlocks reais)", "args": "rotina"},
    "codigo_pe": {"desc": "Código fonte onde PE é chamado no PADRÃO", "args": "nome_pe"},
    "buscar_funcao_padrao": {"desc": "Buscar função no padrão (assinatura, arquivo)", "args": "nome"},
    "pronto": {"desc": "Já tenho informação suficiente para responder", "args": ""},
}


def build_tool_descriptions() -> str:
    """Build formatted tool list for LLM prompt."""
    lines = []
    for name, info in TOOL_DESCRIPTIONS.items():
        args = f"({info['args']})" if info['args'] else ""
        lines.append(f"- {name}{args}: {info['desc']}")
    return "\n".join(lines)


INVESTIGATION_PROMPT = """Voce e um investigador tecnico de ambientes TOTVS Protheus.
Seu objetivo e investigar o problema/requisicao do usuario usando as ferramentas disponiveis.

CONTEXTO INICIAL:
{initial_context}

FERRAMENTAS DISPONIVEIS:
{tool_descriptions}

INSTRUCOES:
1. Analise o contexto e decida qual ferramenta chamar para investigar
2. Chame UMA ferramenta por vez
3. Analise o resultado e decida se precisa de mais dados
4. Quando tiver informacao suficiente, chame "pronto"
5. Seja EFICIENTE — nao busque tudo, busque so o que precisa
6. Se encontrar escrita condicional, rastreie a condicao
7. Se precisar entender rotina padrao, consulte fonte_padrao ou pes_disponiveis
8. Nao busque mais que {max_steps} ferramentas

RESULTADOS ANTERIORES:
{accumulated_results}

Responda APENAS com JSON:
{{"tool": "nome_da_ferramenta", "args": {{"param": "valor"}}}}

Ou se ja tem tudo:
{{"tool": "pronto"}}"""


def _parse_tool_call(llm_response: str) -> dict:
    """Parse LLM response into a tool call."""
    text = llm_response.strip()

    # Try to extract JSON from response
    try:
        # Handle markdown-wrapped JSON
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        parsed = json.loads(text)
        if "tool" in parsed:
            return parsed
    except (json.JSONDecodeError, IndexError):
        pass

    # Try to find JSON in text
    import re
    match = re.search(r'\{[^}]+\}', text, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group())
            if "tool" in parsed:
                return parsed
        except json.JSONDecodeError:
            pass

    # Fallback: assume ready to answer
    return {"tool": "pronto"}


def _execute_tool(tool_name: str, args: dict) -> dict:
    """Execute a tool by name with given arguments."""
    if tool_name not in TOOL_MAP:
        return {"erro": f"Ferramenta '{tool_name}' nao encontrada"}

    try:
        result = TOOL_MAP[tool_name](**args)
        return result
    except Exception as e:
        return {"erro": f"Erro ao executar {tool_name}: {str(e)[:200]}"}


def _truncate_result(result: dict, max_chars: int = 2000) -> str:
    """Serialize and truncate a tool result for context accumulation."""
    text = json.dumps(result, ensure_ascii=False, default=str)
    if len(text) > max_chars:
        text = text[:max_chars] + "... [truncado]"
    return text


async def run_investigation(
    llm,
    initial_context: str,
    modo: str = "ajuste",
) -> AsyncGenerator[dict, None]:
    """Run the iterative investigation loop.

    Yields SSE-compatible events:
        {"type": "status", "step": "Buscando quem grava no C5_LIBEROK..."}
        {"type": "tool_result", "tool": "quem_grava", "summary": "3 pontos encontrados"}
        {"type": "complete", "context": "accumulated context for final LLM call"}

    Args:
        llm: LLMService instance
        initial_context: Starting context (from classification + resolution)
        modo: Conversation mode (ajuste, melhoria, duvida)
    """
    accumulated = []
    tool_descriptions = build_tool_descriptions()

    for step in range(MAX_STEPS):
        # Build prompt with accumulated context
        acc_text = "\n\n".join(accumulated) if accumulated else "Nenhum resultado ainda."
        prompt = INVESTIGATION_PROMPT.format(
            initial_context=initial_context,
            tool_descriptions=tool_descriptions,
            accumulated_results=acc_text,
            max_steps=MAX_STEPS,
        )

        # Ask LLM which tool to call
        try:
            response = await asyncio.to_thread(
                llm._call,
                [{"role": "user", "content": prompt}],
                temperature=0.1,
                use_gen=True,
                timeout=30,
            )
        except Exception as e:
            yield {"type": "status", "step": f"Erro na análise: {str(e)[:100]}"}
            break

        decision = _parse_tool_call(response)
        tool_name = decision.get("tool", "pronto")
        tool_args = decision.get("args", {})

        if tool_name == "pronto":
            break

        # Status update
        desc = TOOL_DESCRIPTIONS.get(tool_name, {}).get("desc", tool_name)
        args_summary = ", ".join(f"{k}={v}" for k, v in tool_args.items()) if tool_args else ""
        yield {"type": "status", "step": f"Investigando: {desc} ({args_summary})..."}

        # Execute tool
        result = await asyncio.to_thread(_execute_tool, tool_name, tool_args)

        # Accumulate result
        result_text = _truncate_result(result)
        accumulated.append(f"=== {tool_name}({args_summary}) ===\n{result_text}")

        yield {
            "type": "tool_result",
            "tool": tool_name,
            "args": tool_args,
            "summary": result_text[:300],
        }

    # Return complete accumulated context
    final_context = "\n\n".join(accumulated) if accumulated else initial_context
    yield {"type": "complete", "context": final_context}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd d:/IA/Projetos/Protheus && python -m pytest tests/test_investigation_loop.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/investigation_loop.py tests/test_investigation_loop.py
git commit -m "feat(analista-v2): add investigation_loop — iterative LLM-driven tool calling"
```

---

## Chunk 5: Especialista em Código (code_specialist.py)

Serviço que recebe dossiê focado e gera/analisa/corrige código ADVPL.

### Task 5: Criar `backend/services/code_specialist.py`

**Files:**
- Create: `backend/services/code_specialist.py`
- Reference: `ADVPL/Skills ADVPL/.claude/skills/advpl.md` (ADVPL knowledge)
- Reference: `ADVPL/Skills ADVPL/Exemplos/` (code examples for few-shot)
- Test: `tests/test_code_specialist.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_code_specialist.py
"""Tests for code_specialist — ADVPL code analysis and generation."""
import pytest
from unittest.mock import MagicMock, patch


class TestBuildSpecialistPrompt:
    def test_includes_advpl_rules(self):
        from backend.services.code_specialist import _build_specialist_prompt
        prompt = _build_specialist_prompt("diagnosticar", {})
        assert "GetArea" in prompt
        assert "RestArea" in prompt
        assert "notação húngara" in prompt or "hungara" in prompt

    def test_includes_dossie_context(self):
        from backend.services.code_specialist import _build_specialist_prompt
        dossie = {"rotina": "MATA410", "problema": "type mismatch"}
        prompt = _build_specialist_prompt("diagnosticar", dossie)
        assert "MATA410" in prompt
        assert "type mismatch" in prompt


class TestCodeSpecialist:
    def test_diagnosticar_returns_analysis(self):
        from backend.services.code_specialist import code_specialist
        mock_llm = MagicMock()
        mock_llm._call.return_value = "O problema está na linha 245..."
        result = code_specialist(
            llm=mock_llm,
            modo="diagnosticar",
            dossie={"codigo": "User Function Test()\nReturn", "problema": "type mismatch"},
        )
        assert "diagnostico" in result or "resposta" in result

    def test_gerar_returns_code(self):
        from backend.services.code_specialist import code_specialist
        mock_llm = MagicMock()
        mock_llm._call.return_value = "```advpl\nUser Function MA410COR()\nReturn\n```"
        result = code_specialist(
            llm=mock_llm,
            modo="gerar",
            dossie={"tipo": "pe", "nome": "MA410COR", "spec": "Validar desconto"},
        )
        assert "codigo" in result or "resposta" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd d:/IA/Projetos/Protheus && python -m pytest tests/test_code_specialist.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement `code_specialist.py`**

```python
# backend/services/code_specialist.py
"""Code Specialist — ADVPL/TLPP code analysis, diagnosis and generation.

This service is invoked by the Analista when the investigation
determines that code needs to be read, diagnosed, corrected, or created.

It uses ADVPL knowledge from the skills docs and code examples.
"""
from pathlib import Path

ADVPL_DOCS_DIR = Path("ADVPL/Skills ADVPL/docs")
ADVPL_EXAMPLES_DIR = Path("ADVPL/Skills ADVPL/Exemplos")


def _load_advpl_rules() -> str:
    """Load core ADVPL rules from the skill file."""
    skill_path = Path("ADVPL/Skills ADVPL/.claude/skills/advpl.md")
    if not skill_path.exists():
        return ""

    content = skill_path.read_text(encoding="utf-8")

    # Extract key sections: boas práticas, o que não fazer, convenções
    sections = []
    in_section = False
    current = []

    for line in content.split("\n"):
        if "## Boas práticas" in line or "## O que NÃO fazer" in line or "## Convenção" in line or "## Padrões por tipo" in line:
            if current:
                sections.append("\n".join(current))
            current = [line]
            in_section = True
        elif line.startswith("## ") and in_section:
            sections.append("\n".join(current))
            current = []
            in_section = False
        elif in_section:
            current.append(line)

    if current:
        sections.append("\n".join(current))

    return "\n\n".join(sections)


def _load_example(tipo: str) -> str:
    """Load a relevant code example for few-shot prompting."""
    if not ADVPL_EXAMPLES_DIR.exists():
        return ""

    # Map tipo to example files
    examples = {
        "pe": ["A300STRU.prw", "DAMDFE.prw"],
        "mvc": ["custom.mvc.customers.tlpp", "custom.mvc.quote.tlpp"],
        "tlpp": ["custom.mvc.monitors.tlpp"],
    }

    files = examples.get(tipo, list(examples.values())[0])
    for fname in files:
        fpath = ADVPL_EXAMPLES_DIR / fname
        if fpath.exists():
            content = fpath.read_text(encoding="utf-8", errors="replace")
            return content[:3000]  # First 3K chars as example

    return ""


SPECIALIST_PROMPTS = {
    "diagnosticar": """Voce e um debugger especialista em ADVPL/TLPP para TOTVS Protheus.

REGRAS ADVPL:
{advpl_rules}

DOSSIE DO PROBLEMA:
Rotina: {rotina}
Fonte: {arquivo}
Funcao: {funcao}
Problema reportado: {problema}

CODIGO:
{codigo}

CONTEXTO ADICIONAL:
{contexto}

INSTRUCOES:
1. Leia o codigo linha por linha
2. Identifique a causa raiz do problema
3. Explique o fluxo que leva ao erro
4. Proponha a correcao EXATA com codigo

Responda com:
## Diagnostico
[causa raiz]

## Fluxo do Problema
[passo a passo]

## Correcao Proposta
```advpl
[codigo corrigido]
```""",

    "gerar": """Voce e um desenvolvedor senior ADVPL/TLPP para TOTVS Protheus.

REGRAS ADVPL:
{advpl_rules}

ESPECIFICACAO:
Tipo: {tipo}
Nome: {nome}
Objetivo: {spec}

CONTEXTO:
{contexto}

PEs DISPONIVEIS (parametros reais do fonte padrao):
{pes_info}

EXEMPLO DE REFERENCIA:
{exemplo}

INSTRUCOES:
1. Gere codigo ADVPL completo e funcional
2. Siga TODAS as boas praticas (GetArea/RestArea, notacao hungara, Local no topo)
3. Use os parametros REAIS do PE (PARAMIXB conforme documentado acima)
4. Inclua comentarios explicativos
5. Inclua tratamento de erro adequado

Responda com o codigo completo dentro de ```advpl ... ```""",

    "ajustar": """Voce e um desenvolvedor senior ADVPL/TLPP para TOTVS Protheus.

REGRAS ADVPL:
{advpl_rules}

CODIGO ATUAL:
{codigo}

DIAGNOSTICO:
{diagnostico}

AJUSTE NECESSARIO:
{ajuste}

INSTRUCOES:
1. Aplique o ajuste mantendo o estilo existente do codigo
2. Nao altere partes que nao precisam mudar
3. Siga boas praticas ADVPL
4. Explique cada alteracao feita

Responda com:
## Alteracoes
[lista de mudancas]

## Codigo Ajustado
```advpl
[codigo completo com ajuste]
```""",
}


def _build_specialist_prompt(modo: str, dossie: dict) -> str:
    """Build the specialist prompt with ADVPL rules and dossiê context."""
    template = SPECIALIST_PROMPTS.get(modo, SPECIALIST_PROMPTS["diagnosticar"])
    advpl_rules = _load_advpl_rules()

    # Fill template with dossiê fields (use empty string for missing keys)
    fields = {
        "advpl_rules": advpl_rules[:4000],
        "rotina": dossie.get("rotina", ""),
        "arquivo": dossie.get("arquivo", ""),
        "funcao": dossie.get("funcao", ""),
        "problema": dossie.get("problema", ""),
        "codigo": dossie.get("codigo", "")[:6000],
        "contexto": dossie.get("contexto", "")[:2000],
        "tipo": dossie.get("tipo", ""),
        "nome": dossie.get("nome", ""),
        "spec": dossie.get("spec", ""),
        "pes_info": dossie.get("pes_info", ""),
        "exemplo": _load_example(dossie.get("tipo", "pe"))[:2000],
        "diagnostico": dossie.get("diagnostico", ""),
        "ajuste": dossie.get("ajuste", ""),
    }

    return template.format(**fields)


def code_specialist(llm, modo: str, dossie: dict) -> dict:
    """Invoke the code specialist.

    Args:
        llm: LLMService instance
        modo: 'diagnosticar' | 'gerar' | 'ajustar'
        dossie: Context dict with relevant fields per modo

    Returns:
        {resposta: str, codigo: str (if generated)}
    """
    prompt = _build_specialist_prompt(modo, dossie)

    response = llm._call(
        [{"role": "user", "content": prompt}],
        temperature=0.2,
        use_gen=False,  # Use stronger chat model
        timeout=90,
    )

    # Extract code blocks if present
    import re
    code_blocks = re.findall(r'```(?:advpl|tlpp)?\s*\n(.*?)```', response, re.DOTALL)
    codigo = code_blocks[0].strip() if code_blocks else ""

    return {
        "resposta": response,
        "codigo": codigo,
        "modo": modo,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd d:/IA/Projetos/Protheus && python -m pytest tests/test_code_specialist.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/code_specialist.py tests/test_code_specialist.py
git commit -m "feat(analista-v2): add code_specialist — ADVPL analysis and generation"
```

---

## Chunk 6: Integração no Pipeline do Analista

Refatorar `analista.py` para usar as novas fases.

### Task 6: Integrar resolução semântica no fluxo de chat

**Files:**
- Modify: `backend/routers/analista.py` (~lines 1260-1310, onde resolver roda)
- Reference: `backend/services/semantic_resolver.py` (novo)

- [ ] **Step 1: Add import of semantic_resolver at top of analista.py**

No topo do arquivo `backend/routers/analista.py` (junto dos imports existentes, ~line 16):

```python
from backend.services.semantic_resolver import resolver_semantico
```

- [ ] **Step 2: Replace resolver call in chat flow**

In `backend/routers/analista.py`, find the block starting at ~line 1295 where `tool_resolver_contexto` is called (`if not campos_msg:`). Replace the resolver section with the new semantic resolver:

Find the existing code block:
```python
            if not campos_msg:
                yield {"event": "status", "data": json.dumps({"step": "Identificando contexto da pergunta..."})}
                try:
                    ctx = await asyncio.to_thread(tool_resolver_contexto, body.message)
                    if ctx.get("contexto_resolvido"):
```

Replace the entire `if not campos_msg:` block (from ~line 1295 to where the resolver results are used) with:

```python
            if not campos_msg:
                yield {"event": "status", "data": json.dumps({"step": "Analisando contexto no ambiente do cliente..."})}
                try:
                    # V2: Semantic resolution — search menus, propósitos, processos, campos
                    sem_result = await asyncio.to_thread(resolver_semantico, body.message)

                    if sem_result.get("resolvido") and sem_result.get("candidatos"):
                        candidatos = sem_result["candidatos"]

                        # Decision: 1 clear candidate → use it; N candidates → ask
                        if len(candidatos) == 1 or candidatos[0]["confianca"] >= 0.7:
                            # Use top candidate
                            top = candidatos[0]
                            if top.get("tabelas") or top.get("rotinas"):
                                tabelas = [top["tabela"]] if not tabelas else tabelas
                                if top.get("rotinas"):
                                    tool_results_parts.append(
                                        f"ROTINA IDENTIFICADA: {', '.join(top['rotinas'])}"
                                    )
                                if top.get("campos_relevantes"):
                                    tool_results_parts.append(
                                        f"CAMPOS RELEVANTES: {', '.join(top['campos_relevantes'])}"
                                    )
                                for desc in top.get("todas_descricoes", [])[:3]:
                                    tool_results_parts.append(f"  → {desc}")

                        elif len(candidatos) >= 2:
                            # Multiple candidates — ask intelligent clarification
                            opcoes_text = []
                            for i, c in enumerate(candidatos[:5], 1):
                                desc = c.get("descricao", c["tabela"])
                                tabs = c["tabela"]
                                rotinas = ", ".join(c.get("rotinas", [])) or "—"
                                opcoes_text.append(f"{i}. {desc} (tabela: {tabs}, rotina: {rotinas})")

                            clarification = (
                                f"Encontrei {len(candidatos)} contextos possiveis no seu ambiente:\n"
                                + "\n".join(opcoes_text)
                                + "\n\nQual desses se aplica ao seu caso?"
                            )
                            # Use clarification as system prompt override
                            usou_clarificacao = True
                            clarificacao_texto = clarification

                    # Fallback: also run original resolver for cross-match
                    if not tabelas:
                        ctx = await asyncio.to_thread(tool_resolver_contexto, body.message)
                        if ctx.get("contexto_resolvido"):
                            cross_campos = [c for c in ctx.get("campos_encontrados", []) if c.get("_cross")]
                            if cross_campos:
                                tabelas = list(set(c["tabela"] for c in cross_campos))
                            elif ctx.get("tabelas_encontradas"):
                                tabelas = [t["codigo"] for t in ctx["tabelas_encontradas"][:3]]

                except Exception as e:
                    print(f"[chat] semantic resolver error: {e}")
```

- [ ] **Step 3: Test manually with server running**

Run: `cd d:/IA/Projetos/Protheus && python -m uvicorn backend.app:app --port 8741 --reload`
Test: Open browser, go to Peça ao Analista, create ajuste conversation, type "problema na aprovação do pedido"
Expected: Should see "Analisando contexto no ambiente do cliente..." status, then either direct investigation or clarification question with real options.

- [ ] **Step 4: Commit**

```bash
git add backend/routers/analista.py
git commit -m "feat(analista-v2): integrate semantic_resolver in chat pipeline"
```

### Task 7: Integrar investigation_loop no fluxo de chat

**Files:**
- Modify: `backend/routers/analista.py` (~lines 1440-1760, investigation + context building)

- [ ] **Step 1: Add import**

```python
from backend.services.investigation_loop import run_investigation
```

- [ ] **Step 2: Add investigation mode toggle**

After the semantic resolution block and ambiguity check, before the current "fetch all tools" block, add a feature flag and the iterative investigation path:

```python
            # V2: Iterative investigation (when tables are resolved and no clarification needed)
            USE_ITERATIVE = True  # Feature flag — set False to fallback to V1

            if USE_ITERATIVE and tabelas and not usou_clarificacao:
                yield {"event": "status", "data": json.dumps({"step": "Investigando..."})}

                # Build minimal initial context
                initial_ctx_parts = [
                    f"MODO: {modo_val}",
                    f"PERGUNTA: {body.message}",
                    f"TABELAS: {', '.join(tabelas)}",
                ]
                if campos_msg:
                    initial_ctx_parts.append(f"CAMPOS EXPLICITOS: {', '.join(campos_msg)}")
                if modulos:
                    initial_ctx_parts.append(f"MODULOS: {', '.join(modulos)}")

                initial_context = "\n".join(initial_ctx_parts)

                # Run iterative loop
                investigation_context = ""
                async for event in run_investigation(llm, initial_context, modo_val):
                    if event["type"] == "status":
                        yield {"event": "status", "data": json.dumps({"step": event["step"]})}
                    elif event["type"] == "tool_result":
                        pass  # Internal tracking — status already yielded
                    elif event["type"] == "complete":
                        investigation_context = event["context"]

                # Use investigation result as context
                tool_results_text = investigation_context or "Nenhum dado de investigação encontrado."
                context = tool_results_text[:8000]

            else:
                # V1 fallback: fetch all tools (existing code)
                # ... (keep existing code in else block)
```

Note: The existing fetch-all code (~lines 1440-1760) goes inside the `else` block. This is a gradual migration — the flag allows switching back to V1 if issues arise.

- [ ] **Step 3: Test manually**

Run server and test with: "Quem grava no C5_LIBEROK?"
Expected: See iterative status messages ("Investigando: Quem grava em tabela/campo..."), then response based on focused data.

- [ ] **Step 4: Commit**

```bash
git add backend/routers/analista.py
git commit -m "feat(analista-v2): integrate investigation_loop with V1 fallback flag"
```

### Task 8: Integrar code_specialist como ferramenta disponível

**Files:**
- Modify: `backend/services/investigation_loop.py` (add code_specialist to TOOL_MAP)

- [ ] **Step 1: Add code specialist tools to investigation loop**

In `backend/services/investigation_loop.py`, add to TOOL_MAP and TOOL_DESCRIPTIONS:

```python
from backend.services.code_specialist import code_specialist as _code_specialist

# Add to TOOL_MAP:
"analisar_fonte": lambda **kw: _code_specialist(
    llm=kw.get("_llm"), modo="diagnosticar",
    dossie={"codigo": kw.get("codigo", ""), "problema": kw.get("problema", ""),
            "rotina": kw.get("rotina", ""), "arquivo": kw.get("arquivo", "")}
),
"gerar_codigo": lambda **kw: _code_specialist(
    llm=kw.get("_llm"), modo="gerar",
    dossie={"tipo": kw.get("tipo", "pe"), "nome": kw.get("nome", ""),
            "spec": kw.get("spec", ""), "contexto": kw.get("contexto", "")}
),

# Add to TOOL_DESCRIPTIONS:
"analisar_fonte": {"desc": "Analisar codigo ADVPL para diagnosticar problema", "args": "codigo, problema, rotina?, arquivo?"},
"gerar_codigo": {"desc": "Gerar codigo ADVPL novo (PE, User Function, MVC)", "args": "tipo, nome, spec, contexto?"},
```

Note: The LLM instance needs to be passed through the loop. Update `run_investigation` to pass `llm` via `_llm` key in tool args when calling code specialist tools.

- [ ] **Step 2: Update run_investigation to pass LLM to code tools**

In `_execute_tool`, detect code specialist tools and inject llm:

```python
def _execute_tool(tool_name: str, args: dict, llm=None) -> dict:
    """Execute a tool by name with given arguments."""
    if tool_name not in TOOL_MAP:
        return {"erro": f"Ferramenta '{tool_name}' nao encontrada"}

    try:
        # Inject llm for code specialist tools
        if tool_name in ("analisar_fonte", "gerar_codigo") and llm:
            args["_llm"] = llm
        result = TOOL_MAP[tool_name](**args)
        return result
    except Exception as e:
        return {"erro": f"Erro ao executar {tool_name}: {str(e)[:200]}"}
```

And update the call in `run_investigation`:

```python
result = await asyncio.to_thread(_execute_tool, tool_name, tool_args, llm)
```

- [ ] **Step 3: Test manually**

Test with melhoria mode: "Preciso criar um PE no MATA410 para validar desconto"
Expected: Investigation loop may call `pes_disponiveis(MATA410)` then `gerar_codigo(tipo=pe, ...)`.

- [ ] **Step 4: Commit**

```bash
git add backend/services/investigation_loop.py
git commit -m "feat(analista-v2): integrate code_specialist in investigation loop"
```

---

## Chunk 7: Expor tools do padrão nas rotas API

Para uso direto pelo frontend (Explorer, etc.) além do pipeline do analista.

### Task 9: Adicionar rotas de padrão tools em `padrao.py`

**Files:**
- Modify: `backend/routers/padrao.py` (add new endpoints)

- [ ] **Step 1: Add new endpoints for padrao tools**

At the end of `backend/routers/padrao.py`, add:

```python
# ── Padrao Tools: direct API access ─────────────────────────────────────

@router.get("/fontes/funcao_padrao/{nome}")
async def search_funcao_padrao_api(nome: str):
    """Search functions in the standard source database."""
    from backend.services.padrao_tools import tool_buscar_funcao_padrao
    results = tool_buscar_funcao_padrao(nome)
    return {"funcoes": results, "total": len(results)}


@router.get("/fontes/fonte_padrao/{arquivo}")
async def get_fonte_padrao_api(arquivo: str):
    """Get metadata and functions for a standard source file."""
    from backend.services.padrao_tools import tool_fonte_padrao
    return tool_fonte_padrao(arquivo)


@router.get("/fontes/pes_disponiveis/{rotina}")
async def get_pes_disponiveis_api(rotina: str):
    """List all PEs available in a standard routine."""
    from backend.services.padrao_tools import tool_pes_disponiveis
    results = tool_pes_disponiveis(rotina)
    return {"pes": results, "total": len(results)}
```

- [ ] **Step 2: Test with curl**

```bash
curl http://localhost:8741/api/padrao/fontes/fonte_padrao/MATA410
curl http://localhost:8741/api/padrao/fontes/pes_disponiveis/MATA410
curl http://localhost:8741/api/padrao/fontes/funcao_padrao/A410Grava
```

- [ ] **Step 3: Commit**

```bash
git add backend/routers/padrao.py
git commit -m "feat(analista-v2): expose padrao_tools as API endpoints"
```

---

## Resumo de Arquivos

### Criados (5 arquivos novos):
| Arquivo | Responsabilidade |
|---------|-----------------|
| `backend/services/padrao_tools.py` | Ferramentas de consulta ao padrao.db |
| `backend/services/semantic_resolver.py` | Resolução semântica de mensagens vagas |
| `backend/services/investigation_loop.py` | Loop iterativo de investigação com LLM |
| `backend/services/code_specialist.py` | Análise e geração de código ADVPL |
| `tests/test_padrao_tools.py` | Testes das padrao_tools |
| `tests/test_semantic_resolver.py` | Testes do resolver semântico |
| `tests/test_investigation_loop.py` | Testes do loop de investigação |
| `tests/test_code_specialist.py` | Testes do especialista em código |
| `tests/test_analista_tools_new.py` | Testes das novas client tools |

### Modificados (2 arquivos):
| Arquivo | Mudança |
|---------|---------|
| `backend/routers/analista.py` | Integrar semantic_resolver + investigation_loop no chat flow |
| `backend/routers/padrao.py` | Novos endpoints API para padrao_tools |
| `backend/services/analista_tools.py` | 3 novas tools (ler_fonte, buscar_menus, buscar_propositos) |

### Não modificados (preservados):
- `backend/services/analista_prompts.py` — system prompts por modo mantidos
- `backend/services/clarificacao.py` — mantido como fallback
- `backend/services/analista_orchestrator.py` — classificador mantido
- Frontend — sem mudanças (SSE events já suportados)
