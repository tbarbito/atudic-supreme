"""Cross-Reference Index — pre-computed lookup tables for fast investigation.

Instead of querying the database dynamically for every investigation,
builds indexes on first use and caches them in memory.

Indexes:
  campo_to_fontes: {campo -> [fontes that write to it]}
  tabela_to_fontes: {tabela -> [fontes that reference it]}
  tabela_to_rotinas: {tabela -> [rotinas from ROTINA_MAP]}
  fonte_to_tables: {fonte -> [tables it writes to]}
  fonte_to_calls: {fonte -> [functions it calls]}
  pe_to_rotina: {pe_name -> rotina}
"""
import sqlite3
import json
import time
from pathlib import Path
from typing import Optional


class CrossRefIndex:
    """Lazy-initialized cross-reference indexes."""

    def __init__(self, db_path: Path, padrao_db_path: Path = None):
        self.db_path = db_path
        self.padrao_db_path = padrao_db_path
        self._built = False
        self._build_time = 0

        # Indexes
        self.tabela_to_fontes_escrita: dict[str, list[str]] = {}
        self.tabela_to_fontes_leitura: dict[str, list[str]] = {}
        self.fonte_to_write_tables: dict[str, list[str]] = {}
        self.fonte_to_calls: dict[str, list[str]] = {}
        self.campo_writers: dict[str, list[dict]] = {}  # "TABELA.CAMPO" -> [{arquivo, funcao}]
        self.pe_map: dict[str, dict] = {}  # pe_name -> {rotina, arquivo, operacao}

    def ensure_built(self):
        """Build indexes if not already built."""
        if self._built:
            return
        t0 = time.time()
        self._build_from_db()
        self._build_time = time.time() - t0
        self._built = True
        print(f"[cross_ref_index] Built in {self._build_time:.2f}s")

    def _build_from_db(self):
        """Build all indexes from the database."""
        if not self.db_path.exists():
            return

        db = sqlite3.connect(str(self.db_path))
        try:
            # 1. tabela_to_fontes from fontes table
            try:
                rows = db.execute(
                    "SELECT arquivo, write_tables, tabelas_ref, calls_u FROM fontes"
                ).fetchall()
                for arquivo, write_tables_json, tabelas_ref_json, calls_json in rows:
                    # Write tables
                    try:
                        write_tables = json.loads(write_tables_json) if write_tables_json else []
                    except (json.JSONDecodeError, TypeError):
                        write_tables = []

                    for t in write_tables:
                        self.tabela_to_fontes_escrita.setdefault(t.upper(), []).append(arquivo)
                    self.fonte_to_write_tables[arquivo] = [t.upper() for t in write_tables]

                    # Read tables
                    try:
                        ref_tables = json.loads(tabelas_ref_json) if tabelas_ref_json else []
                    except (json.JSONDecodeError, TypeError):
                        ref_tables = []

                    for t in ref_tables:
                        self.tabela_to_fontes_leitura.setdefault(t.upper(), []).append(arquivo)

                    # Function calls
                    try:
                        calls = json.loads(calls_json) if calls_json else []
                    except (json.JSONDecodeError, TypeError):
                        calls = []
                    self.fonte_to_calls[arquivo] = calls
            except Exception:
                pass

            # 2. campo_writers from operacoes_escrita
            try:
                rows = db.execute(
                    "SELECT tabela, campos, arquivo, funcao FROM operacoes_escrita"
                ).fetchall()
                for tabela, campos_json, arquivo, funcao in rows:
                    try:
                        campos = json.loads(campos_json) if campos_json else []
                    except (json.JSONDecodeError, TypeError):
                        campos = []
                    for campo in campos:
                        key = f"{tabela.upper()}.{campo.upper()}"
                        self.campo_writers.setdefault(key, []).append({
                            "arquivo": arquivo, "funcao": funcao or ""
                        })
            except Exception:
                pass

            # 3. PE map from padrao_pes
            try:
                rows = db.execute(
                    "SELECT nome, rotina, modulo, objetivo FROM padrao_pes"
                ).fetchall()
                for nome, rotina, modulo, objetivo in rows:
                    self.pe_map[nome.upper()] = {
                        "rotina": rotina or "",
                        "modulo": modulo or "",
                        "objetivo": objetivo or "",
                    }
            except Exception:
                pass

        finally:
            db.close()

    # -- Fast lookup methods --

    def get_fontes_escrita(self, tabela: str) -> list[str]:
        """Get all fontes that WRITE to a table. O(1)."""
        self.ensure_built()
        return self.tabela_to_fontes_escrita.get(tabela.upper(), [])

    def get_fontes_leitura(self, tabela: str) -> list[str]:
        """Get all fontes that READ from a table. O(1)."""
        self.ensure_built()
        return self.tabela_to_fontes_leitura.get(tabela.upper(), [])

    def get_campo_writers(self, tabela: str, campo: str) -> list[dict]:
        """Get all fontes/funcoes that write to a specific field. O(1)."""
        self.ensure_built()
        key = f"{tabela.upper()}.{campo.upper()}"
        return self.campo_writers.get(key, [])

    def get_write_tables(self, fonte: str) -> list[str]:
        """Get tables a fonte writes to. O(1)."""
        self.ensure_built()
        return self.fonte_to_write_tables.get(fonte, [])

    def get_calls(self, fonte: str) -> list[str]:
        """Get functions a fonte calls. O(1)."""
        self.ensure_built()
        return self.fonte_to_calls.get(fonte, [])

    def get_pe_info(self, pe_name: str) -> dict:
        """Get PE info. O(1)."""
        self.ensure_built()
        return self.pe_map.get(pe_name.upper(), {})

    def get_stats(self) -> dict:
        """Return index stats."""
        self.ensure_built()
        return {
            "tabelas_escrita": len(self.tabela_to_fontes_escrita),
            "tabelas_leitura": len(self.tabela_to_fontes_leitura),
            "fontes": len(self.fonte_to_write_tables),
            "campo_writers": len(self.campo_writers),
            "pes": len(self.pe_map),
            "build_time_ms": int(self._build_time * 1000),
        }


# Module-level singleton
_index: Optional[CrossRefIndex] = None


def get_index() -> CrossRefIndex:
    """Get or create the cross-reference index singleton."""
    global _index
    if _index is None:
        from app.services.workspace.config import load_config, get_client_workspace
        config = load_config(Path("config.json"))
        client_dir = get_client_workspace(Path("workspace"), config.active_client)
        db_path = client_dir / "db" / "extrairpo.db"
        from app.services.workspace.workspace_populator import _get_fontes_padrao_db_path
        padrao_path = _get_fontes_padrao_db_path()
        _index = CrossRefIndex(db_path, padrao_path)
    return _index


def reset_index():
    """Reset the index (e.g., after client switch or data reload)."""
    global _index
    _index = None
