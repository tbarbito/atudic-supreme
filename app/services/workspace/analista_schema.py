"""Schema definitions and migration helpers for the Analista module (v2)."""
from app.services.workspace.workspace_db import Database


def ensure_analista_tables(db: Database):
    """Create all analista tables (existing + new) if they don't exist."""

    # ── Existing tables ── (kept exactly as-is)
    db.execute("""CREATE TABLE IF NOT EXISTS analista_projetos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        descricao TEXT,
        status TEXT DEFAULT 'rascunho',
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    )""")

    db.execute("""CREATE TABLE IF NOT EXISTS analista_mensagens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        projeto_id INTEGER NOT NULL REFERENCES analista_projetos(id),
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        tool_data TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    )""")

    db.execute("""CREATE TABLE IF NOT EXISTS analista_artefatos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        projeto_id INTEGER NOT NULL REFERENCES analista_projetos(id),
        tipo TEXT NOT NULL,
        nome TEXT NOT NULL,
        tabela TEXT,
        acao TEXT DEFAULT 'criar',
        spec TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    )""")

    db.execute("""CREATE TABLE IF NOT EXISTS analista_documentos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        projeto_id INTEGER NOT NULL REFERENCES analista_projetos(id),
        tipo TEXT NOT NULL,
        titulo TEXT NOT NULL,
        conteudo TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now'))
    )""")

    # ── Migrations: add columns when they don't exist yet ──
    for _sql in [
        "ALTER TABLE analista_artefatos ADD COLUMN spec_json TEXT",
        # demanda_id allows mensagens/artefatos to be linked to analista_demandas
        "ALTER TABLE analista_mensagens ADD COLUMN demanda_id INTEGER",
        "ALTER TABLE analista_artefatos ADD COLUMN demanda_id INTEGER",
        # 3-mode redesign: duvida, melhoria, ajuste
        "ALTER TABLE analista_demandas ADD COLUMN modo TEXT DEFAULT 'melhoria'",
    ]:
        try:
            db.execute(_sql)
            db.commit()
        except Exception:
            pass  # Column already exists — safe to ignore

    # ── New tables ──

    db.execute("""CREATE TABLE IF NOT EXISTS analista_demandas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tipo TEXT NOT NULL,
        nome TEXT NOT NULL,
        descricao TEXT,
        status TEXT DEFAULT 'classificando',
        entidades_json TEXT,
        research_json TEXT,
        confianca REAL,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    )""")

    db.execute("""CREATE TABLE IF NOT EXISTS analista_diretrizes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tipo_demanda TEXT,
        categoria TEXT,
        titulo TEXT NOT NULL,
        conteudo TEXT NOT NULL,
        fonte TEXT,
        ativo INTEGER DEFAULT 1,
        created_at TEXT DEFAULT (datetime('now'))
    )""")

    db.execute("""CREATE TABLE IF NOT EXISTS analista_outputs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        demanda_id INTEGER REFERENCES analista_demandas(id),
        formato TEXT NOT NULL,
        conteudo TEXT NOT NULL,
        titulo TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    )""")

    db.commit()


def migrate_demandas_to_modos(db: Database) -> int:
    """Set modo for existing demandas based on their tipo.

    bug -> ajuste, everything else -> melhoria.
    Returns number of rows updated.
    """
    db.execute("""
        UPDATE analista_demandas
        SET modo = CASE
            WHEN tipo = 'bug' THEN 'ajuste'
            WHEN tipo IN ('duvida', 'melhoria', 'ajuste') THEN tipo
            ELSE 'melhoria'
        END
        WHERE modo IS NULL
    """)
    count = db.execute("SELECT changes()").fetchone()[0]
    db.commit()
    return count


def migrate_projetos_to_demandas(db: Database) -> int:
    """Copy analista_projetos rows that are not yet in analista_demandas.

    Returns the number of records migrated.

    TODO (Phase 1.4): call this function during application startup so that
    any existing analista_projetos rows are automatically migrated to
    analista_demandas before the new endpoints start serving requests.
    """
    db.execute("""
        INSERT INTO analista_demandas (id, tipo, nome, descricao, status, created_at, updated_at)
        SELECT id, 'projeto', nome, descricao, status, created_at, updated_at
        FROM analista_projetos
        WHERE id NOT IN (SELECT id FROM analista_demandas)
    """)
    # Capture changes() BEFORE commit — SQLite resets it after each transaction.
    count = db.execute("SELECT changes()").fetchone()[0]
    db.commit()
    return count
