"""
Migration 011: Adiciona ref_environment_id e connection_role em database_connections.

- ref_environment_id: ambiente de referencia da conexao (permite cadastrar
  conexoes de outros ambientes para consulta/comparacao)
- connection_role: label livre para identificar o papel da conexao (ex: Protheus, BI, Legado)
- UNIQUE corrigido na migration 012 para (environment_id, host, database_name)
"""


def upgrade(cursor):
    # Adicionar coluna ref_environment_id (FK para environments)
    cursor.execute("""
        ALTER TABLE database_connections
        ADD COLUMN IF NOT EXISTS ref_environment_id INTEGER
    """)

    # Adicionar coluna connection_role (label livre)
    cursor.execute("""
        ALTER TABLE database_connections
        ADD COLUMN IF NOT EXISTS connection_role TEXT DEFAULT 'Protheus'
    """)

    # Preencher ref_environment_id com environment_id para conexoes existentes
    cursor.execute("""
        UPDATE database_connections
        SET ref_environment_id = environment_id
        WHERE ref_environment_id IS NULL
    """)

    # Indice para busca por ambiente de referencia
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_dbconn_ref_env
        ON database_connections (ref_environment_id)
    """)

    # Unique constraint: mesmo ambiente, mesmo ref, mesmo servidor, mesmo banco
    # Usar DO NOTHING para nao falhar se ja existir
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_dbconn_unique_ref
        ON database_connections (environment_id, ref_environment_id, host, database_name)
        WHERE ref_environment_id IS NOT NULL
    """)


def downgrade(cursor):
    cursor.execute("DROP INDEX IF EXISTS idx_dbconn_unique_ref")
    cursor.execute("DROP INDEX IF EXISTS idx_dbconn_ref_env")
    cursor.execute("ALTER TABLE database_connections DROP COLUMN IF EXISTS connection_role")
    cursor.execute("ALTER TABLE database_connections DROP COLUMN IF EXISTS ref_environment_id")
