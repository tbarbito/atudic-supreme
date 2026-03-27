"""
Migration 015: Configuracao de providers LLM do agente inteligente.

Armazena qual provider/modelo usar por ambiente, com API keys criptografadas.
"""


def upgrade(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS llm_provider_configs (
            id SERIAL PRIMARY KEY,
            environment_id INTEGER,
            provider_id TEXT NOT NULL,
            api_key_encrypted TEXT,
            model TEXT,
            base_url TEXT,
            options TEXT,
            is_active BOOLEAN DEFAULT TRUE,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(environment_id, provider_id)
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_llm_config_env
        ON llm_provider_configs(environment_id)
    """)


def downgrade(cursor):
    cursor.execute("DROP TABLE IF EXISTS llm_provider_configs")
