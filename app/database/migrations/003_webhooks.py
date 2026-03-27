"""
Migration 003: Tabela de webhooks configuráveis.

Permite que eventos do sistema disparem chamadas HTTP para URLs externas.
"""


def upgrade(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS webhooks (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            url TEXT NOT NULL,
            events TEXT NOT NULL,
            headers TEXT DEFAULT '{}',
            is_active BOOLEAN DEFAULT TRUE,
            created_by TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)


def downgrade(cursor):
    cursor.execute("DROP TABLE IF EXISTS webhooks")
