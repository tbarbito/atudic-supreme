"""
Migration 005: User Environments - Controle de acesso por ambiente.

Cria tabela de junção user_environments para vincular usuários a ambientes específicos.
- Root admin (username='admin') tem acesso implícito a todos os ambientes.
- Todos os demais usuários precisam de pelo menos 1 ambiente vinculado.
- Ao criar, usuários existentes recebem acesso a todos os ambientes.
"""


def upgrade(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_environments (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            environment_id INTEGER NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            UNIQUE (user_id, environment_id)
        )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_env_user ON user_environments (user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_env_env ON user_environments (environment_id)")

    # Vincular todos os usuários existentes (exceto root) a todos os ambientes
    # Em banco novo, users/environments são criados pelo seeds.py e podem não estar visíveis
    # ainda para esta conexão. Usa SAVEPOINT interno para recuperar o estado da transação
    # caso o INSERT falhe, sem abortar toda a migration.
    cursor.execute("SAVEPOINT sp_seed_user_env")
    try:
        cursor.execute("""
            INSERT INTO user_environments (user_id, environment_id, created_at)
            SELECT u.id, e.id, NOW()
            FROM users u
            CROSS JOIN environments e
            WHERE u.username != 'admin'
            ON CONFLICT (user_id, environment_id) DO NOTHING
        """)
        cursor.execute("RELEASE SAVEPOINT sp_seed_user_env")
    except Exception:
        cursor.execute("ROLLBACK TO SAVEPOINT sp_seed_user_env")
        # Ignora: tabelas de seeds.py não visíveis em banco novo


def downgrade(cursor):
    cursor.execute("DROP TABLE IF EXISTS user_environments")
