"""
Migration 012: Corrige UNIQUE de database_connections.

Remove ref_environment_id do indice unico.
UNIQUE correto: (environment_id, host, database_name)
— impede cadastrar o mesmo servidor/banco duas vezes no mesmo ambiente.
ref_environment_id e apenas um atributo (qual ambiente o banco representa).
"""


def upgrade(cursor):
    # Remover indice antigo que incluia ref_environment_id
    cursor.execute("DROP INDEX IF EXISTS idx_dbconn_unique_ref")

    # Remover duplicatas antes de criar o novo indice unico:
    # manter apenas o registro com menor id para cada (environment_id, host, database_name)
    cursor.execute("""
        DELETE FROM database_connections
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM database_connections
            GROUP BY environment_id, host, database_name
        )
    """)

    # Novo indice unico sem ref_environment_id
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_dbconn_unique_env_host_db
        ON database_connections (environment_id, host, database_name)
    """)


def downgrade(cursor):
    cursor.execute("DROP INDEX IF EXISTS idx_dbconn_unique_env_host_db")
    # Restaurar indice antigo
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_dbconn_unique_ref
        ON database_connections (environment_id, ref_environment_id, host, database_name)
        WHERE ref_environment_id IS NOT NULL
    """)
