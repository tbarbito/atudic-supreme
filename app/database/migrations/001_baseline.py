"""
Migration 001 — Baseline

Representa o estado atual do schema incluindo todas as colunas
que foram adicionadas via migrações inline no seeds.py.

Como essas colunas já existem em bancos em produção, o upgrade
verifica a existência antes de tentar adicionar (idempotente).
"""


# Colunas que foram adicionadas incrementalmente via seeds.py
COLUMN_MIGRATIONS = [
    ("releases", "deploy_command_id", "INTEGER"),
    ("server_services", "environment_id", "INTEGER"),
    ("server_services", "server_name", "TEXT DEFAULT 'localhost'"),
    ("server_services", "display_name", "TEXT"),
    ("server_services", "is_active", "BOOLEAN DEFAULT TRUE"),
    ("service_actions", "force_stop", "BOOLEAN DEFAULT FALSE"),
    ("server_variables", "is_protected", "BOOLEAN DEFAULT FALSE"),
    ("server_variables", "is_password", "BOOLEAN DEFAULT FALSE"),
    ("commands", "is_protected", "BOOLEAN DEFAULT FALSE"),
    ("pipelines", "is_protected", "BOOLEAN DEFAULT FALSE"),
    ("pipeline_schedules", "notify_emails", "TEXT"),
    ("pipeline_schedules", "notify_whatsapp", "TEXT"),
    ("service_actions", "notify_emails", "TEXT"),
    ("service_actions", "notify_whatsapp", "TEXT"),
    ("users", "reset_token", "VARCHAR(255)"),
    ("users", "reset_token_expires", "TIMESTAMP"),
]

# Índices de performance
INDICES = [
    ("idx_pipeline_runs_pipeline", "pipeline_runs", "pipeline_id"),
    ("idx_pipeline_runs_status", "pipeline_runs", "status"),
    ("idx_pipeline_runs_started", "pipeline_runs", "started_at"),
    ("idx_releases_pipeline", "releases", "pipeline_id"),
    ("idx_releases_run", "releases", "run_id"),
    ("idx_releases_status", "releases", "status"),
    ("idx_releases_started", "releases", "started_at"),
]


def _table_exists(cursor, table):
    cursor.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_name = %s",
        (table,)
    )
    return cursor.fetchone() is not None


def _column_exists(cursor, table, column):
    cursor.execute(
        "SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s",
        (table, column)
        )
    return cursor.fetchone() is not None


def upgrade(cursor):
    """Garante que todas as colunas e índices do baseline existem."""
    for table, col, type_def in COLUMN_MIGRATIONS:
        if not _table_exists(cursor, table):
            continue  # Tabela ainda não existe, será criada por migration posterior
        if not _column_exists(cursor, table, col):
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col} {type_def}")

    for idx_name, table, column in INDICES:
        if not _table_exists(cursor, table):
            continue
        cursor.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table}({column})")


def downgrade(cursor):
    """Baseline não pode ser revertido."""
    raise NotImplementedError("A migration baseline não pode ser revertida")
