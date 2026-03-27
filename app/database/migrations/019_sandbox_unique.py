"""
Migration 019: Adicionar UNIQUE constraint em agent_sandbox_config.environment_id

O ON CONFLICT (environment_id) usado no save de configuracao do sandbox
requer uma constraint UNIQUE que nao foi criada na migration 016.
"""


def upgrade(cursor):
    # Adicionar UNIQUE constraint se nao existir
    cursor.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'agent_sandbox_config_environment_id_key'
            ) THEN
                -- Remover duplicatas se existirem (manter o mais recente)
                DELETE FROM agent_sandbox_config a
                USING agent_sandbox_config b
                WHERE a.id < b.id
                AND a.environment_id = b.environment_id;

                ALTER TABLE agent_sandbox_config
                ADD CONSTRAINT agent_sandbox_config_environment_id_key
                UNIQUE (environment_id);
            END IF;
        END
        $$;
    """)
