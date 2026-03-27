"""
Migration 013: Tabela de historico de comparacoes e validacoes de dicionario.

Armazena resultados de Compare e Validate para auditoria e consulta posterior.
"""


def upgrade(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dictionary_history (
            id SERIAL PRIMARY KEY,
            environment_id INTEGER,
            operation_type TEXT NOT NULL,
            connection_a_id INTEGER,
            connection_b_id INTEGER,
            company_code TEXT,
            summary JSONB,
            details JSONB,
            executed_by INTEGER,
            executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            duration_ms INTEGER
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_dict_history_env
        ON dictionary_history (environment_id)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_dict_history_type
        ON dictionary_history (operation_type)
    """)


def downgrade(cursor):
    cursor.execute("DROP TABLE IF EXISTS dictionary_history")
