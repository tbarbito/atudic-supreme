"""Database schema and manager for the standard Protheus sources (padrao.db).

Separate from the client database — shared across all clients.
Stores metadata, functions, detailed ExecBlocks (PEs), and chunks for vectorization.
"""
import sqlite3
from pathlib import Path

PADRAO_SCHEMA = """
CREATE TABLE IF NOT EXISTS fontes (
    arquivo     TEXT PRIMARY KEY,
    caminho     TEXT,
    caminho_rel TEXT,
    tipo        TEXT,
    modulo      TEXT,
    funcoes     TEXT DEFAULT '[]',
    user_funcs  TEXT DEFAULT '[]',
    tabelas_ref TEXT DEFAULT '[]',
    write_tables TEXT DEFAULT '[]',
    reclock_tables TEXT DEFAULT '[]',
    includes    TEXT DEFAULT '[]',
    calls_u     TEXT DEFAULT '[]',
    calls_execblock TEXT DEFAULT '[]',
    fields_ref  TEXT DEFAULT '[]',
    source_type TEXT DEFAULT '',
    lines_of_code INTEGER DEFAULT 0,
    hash        TEXT,
    encoding    TEXT DEFAULT 'cp1252'
);

CREATE TABLE IF NOT EXISTS funcoes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    arquivo     TEXT NOT NULL REFERENCES fontes(arquivo),
    nome        TEXT NOT NULL,
    tipo        TEXT,
    assinatura  TEXT,
    tabelas_ref TEXT DEFAULT '[]',
    campos_ref  TEXT DEFAULT '[]',
    calls       TEXT DEFAULT '[]',
    params      TEXT DEFAULT '{}',
    linha_inicio INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_funcoes_arquivo ON funcoes(arquivo);
CREATE INDEX IF NOT EXISTS idx_funcoes_nome ON funcoes(nome);

CREATE TABLE IF NOT EXISTS execblocks (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    arquivo             TEXT NOT NULL REFERENCES fontes(arquivo),
    funcao              TEXT NOT NULL,
    nome_pe             TEXT NOT NULL,
    linha               INTEGER,
    linha_existblock    INTEGER,
    parametros          TEXT DEFAULT '',
    variavel_retorno    TEXT DEFAULT '',
    retorno_usado       INTEGER DEFAULT 0,
    tipo_retorno_inferido TEXT DEFAULT 'nil',
    comentario          TEXT DEFAULT '',
    operacao            TEXT DEFAULT '',
    contexto            TEXT DEFAULT '',
    uso_condicional     INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_eb_nome_pe ON execblocks(nome_pe);
CREATE INDEX IF NOT EXISTS idx_eb_arquivo ON execblocks(arquivo);
CREATE INDEX IF NOT EXISTS idx_eb_funcao ON execblocks(funcao);
CREATE INDEX IF NOT EXISTS idx_eb_operacao ON execblocks(operacao);

CREATE TABLE IF NOT EXISTS fonte_chunks (
    id          TEXT PRIMARY KEY,
    arquivo     TEXT NOT NULL REFERENCES fontes(arquivo),
    funcao      TEXT,
    content     TEXT,
    modulo      TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_chunks_arquivo ON fonte_chunks(arquivo);

CREATE TABLE IF NOT EXISTS ingest_meta (
    key         TEXT PRIMARY KEY,
    value       TEXT
);
"""


class PadraoDB:
    """Manages the padrao.db SQLite database for standard Protheus sources."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._conn = None

    def _ensure_dir(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._ensure_dir()
            self._conn = sqlite3.connect(str(self.db_path), timeout=30)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def initialize(self):
        """Create all tables (idempotent)."""
        conn = self.get_conn()
        conn.executescript(PADRAO_SCHEMA)
        conn.commit()

    def execute(self, sql: str, params=None):
        conn = self.get_conn()
        if params:
            return conn.execute(sql, params)
        return conn.execute(sql)

    def executemany(self, sql: str, params_list):
        conn = self.get_conn()
        return conn.executemany(sql, params_list)

    def commit(self):
        if self._conn:
            self._conn.commit()

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    def get_raw_conn(self) -> sqlite3.Connection:
        return self.get_conn()

    # ── Query helpers ─────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Return summary statistics of the padrao database."""
        conn = self.get_conn()
        stats = {}
        try:
            stats["total_fontes"] = conn.execute("SELECT COUNT(*) FROM fontes").fetchone()[0]
            stats["total_funcoes"] = conn.execute("SELECT COUNT(*) FROM funcoes").fetchone()[0]
            stats["total_execblocks"] = conn.execute("SELECT COUNT(*) FROM execblocks").fetchone()[0]
            stats["total_chunks"] = conn.execute("SELECT COUNT(*) FROM fonte_chunks").fetchone()[0]
            stats["unique_pes"] = conn.execute("SELECT COUNT(DISTINCT nome_pe) FROM execblocks").fetchone()[0]

            # Top PEs by occurrence count
            rows = conn.execute(
                "SELECT nome_pe, COUNT(*) as cnt FROM execblocks GROUP BY nome_pe ORDER BY cnt DESC LIMIT 20"
            ).fetchall()
            stats["top_pes"] = [{"nome": r[0], "count": r[1]} for r in rows]

            # Module distribution
            rows = conn.execute(
                "SELECT modulo, COUNT(*) as cnt FROM fontes WHERE modulo IS NOT NULL AND modulo != '' GROUP BY modulo ORDER BY cnt DESC"
            ).fetchall()
            stats["modulos"] = [{"modulo": r[0], "count": r[1]} for r in rows]
        except Exception:
            pass
        return stats

    def search_pe(self, nome_pe: str) -> list[dict]:
        """Search ExecBlocks by PE name (exact or partial)."""
        conn = self.get_conn()
        rows = conn.execute(
            "SELECT * FROM execblocks WHERE nome_pe LIKE ? ORDER BY arquivo, linha",
            (f"%{nome_pe.upper()}%",)
        ).fetchall()
        return [dict(r) for r in rows]

    def search_funcao(self, nome: str) -> list[dict]:
        """Search functions by name (exact or partial)."""
        conn = self.get_conn()
        rows = conn.execute(
            "SELECT * FROM funcoes WHERE UPPER(nome) LIKE ? ORDER BY arquivo",
            (f"%{nome.upper()}%",)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_pes_by_arquivo(self, arquivo: str) -> list[dict]:
        """Get all ExecBlocks in a specific source file."""
        conn = self.get_conn()
        rows = conn.execute(
            "SELECT * FROM execblocks WHERE UPPER(arquivo) = ? ORDER BY linha",
            (arquivo.upper(),)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_pes_by_modulo(self, modulo: str) -> list[dict]:
        """Get all ExecBlocks from sources in a specific module."""
        conn = self.get_conn()
        rows = conn.execute(
            """SELECT e.* FROM execblocks e
               JOIN fontes f ON e.arquivo = f.arquivo
               WHERE UPPER(f.modulo) = ?
               ORDER BY e.arquivo, e.linha""",
            (modulo.upper(),)
        ).fetchall()
        return [dict(r) for r in rows]

    def list_all_pes(self) -> list[dict]:
        """List all unique PEs with summary info."""
        conn = self.get_conn()
        rows = conn.execute(
            """SELECT nome_pe,
                      COUNT(*) as ocorrencias,
                      GROUP_CONCAT(DISTINCT arquivo) as arquivos,
                      GROUP_CONCAT(DISTINCT funcao) as funcoes,
                      GROUP_CONCAT(DISTINCT operacao) as operacoes
               FROM execblocks
               GROUP BY nome_pe
               ORDER BY nome_pe"""
        ).fetchall()
        return [dict(r) for r in rows]
