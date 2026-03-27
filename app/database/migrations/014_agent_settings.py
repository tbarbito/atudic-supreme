"""
Migration 014: Tabela de configuracoes do agente inteligente.

Armazena preferencias do agente por ambiente (auto-ingest, chunk size, etc.).
A memoria em si fica no SQLite dedicado (memory/memory.db).
"""


def upgrade(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_settings (
            id SERIAL PRIMARY KEY,
            environment_id INTEGER,
            setting_key TEXT NOT NULL,
            setting_value TEXT,
            updated_by INTEGER,
            updated_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(environment_id, setting_key)
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_agent_settings_env
        ON agent_settings(environment_id)
    """)


def downgrade(cursor):
    cursor.execute("DROP TABLE IF EXISTS agent_settings")
