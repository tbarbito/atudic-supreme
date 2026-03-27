"""
Migration 002: Tabela de histórico de alterações de variáveis de servidor.

Registra quem alterou, valor anterior/novo, e quando.
"""


def upgrade(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS server_variables_audit (
            id SERIAL PRIMARY KEY,
            variable_id INTEGER,
            variable_name TEXT NOT NULL,
            change_type TEXT NOT NULL,
            old_value TEXT,
            new_value TEXT,
            changed_by TEXT NOT NULL,
            changed_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_variable_audit_variable_id
        ON server_variables_audit(variable_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_variable_audit_changed_at
        ON server_variables_audit(changed_at DESC)
    """)


def downgrade(cursor):
    cursor.execute("DROP TABLE IF EXISTS server_variables_audit")
