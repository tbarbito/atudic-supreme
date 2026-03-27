"""
Migration 016: ReAct Agent — audit log e sandbox config.

Suporte ao loop ReAct multi-step com auditoria completa de acoes
do agente e configuracao de sandbox por ambiente.
"""


def upgrade(cursor):
    # Tabela de auditoria de acoes do agente
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_audit_log (
            id SERIAL PRIMARY KEY,
            user_id INTEGER,
            username VARCHAR(100),
            environment_id INTEGER,
            session_id TEXT,
            action VARCHAR(100) NOT NULL,
            params TEXT,
            result_status VARCHAR(20) NOT NULL,
            result_summary TEXT,
            tokens_used INTEGER DEFAULT 0,
            iteration INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_user
        ON agent_audit_log(user_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_env
        ON agent_audit_log(environment_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_action
        ON agent_audit_log(action)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_created
        ON agent_audit_log(created_at)
    """)

    # Configuracao de sandbox por ambiente
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_sandbox_config (
            id SERIAL PRIMARY KEY,
            environment_id INTEGER,
            allowed_paths TEXT,
            blocked_commands TEXT,
            max_iterations INTEGER DEFAULT 10,
            token_budget INTEGER DEFAULT 50000,
            command_timeout INTEGER DEFAULT 30,
            react_enabled BOOLEAN DEFAULT FALSE,
            system_tools_enabled BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Seed: criar config padrao para cada ambiente existente
    # Em banco novo, environments é criado pelo seeds.py e pode não estar visível ainda.
    # Usa SAVEPOINT interno para recuperar o estado da transação sem abortar a migration.
    cursor.execute("SAVEPOINT sp_seed_sandbox")
    try:
        cursor.execute("SELECT id FROM environments")
        env_ids = [row["id"] for row in cursor.fetchall()]
        for env_id in env_ids:
            cursor.execute(
                """
                INSERT INTO agent_sandbox_config (environment_id)
                VALUES (%s)
                ON CONFLICT (environment_id) DO NOTHING
                """,
                (env_id,)
            )
        cursor.execute("RELEASE SAVEPOINT sp_seed_sandbox")
    except Exception:
        cursor.execute("ROLLBACK TO SAVEPOINT sp_seed_sandbox")
        # Ignora: tabela environments não visível em banco novo
