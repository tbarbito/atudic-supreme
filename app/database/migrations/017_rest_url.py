"""
Migration 017: Adiciona rest_url em database_connections.

Permite configurar a URL REST do AppServer Protheus para que o equalizador
possa forcar o TcRefresh apos a equalizacao, garantindo que o DBAccess
reconheca os campos novos imediatamente (sem necessidade de reiniciar).
"""


def upgrade(cursor):
    cursor.execute("""
        ALTER TABLE database_connections
        ADD COLUMN IF NOT EXISTS rest_url TEXT
    """)


def downgrade(cursor):
    cursor.execute("ALTER TABLE database_connections DROP COLUMN IF EXISTS rest_url")
