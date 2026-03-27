"""
Migration 010: Dev Workspace — Desenvolvimento Assistido
Cria tabelas branch_policies e source_impact_cache para o modulo de workspace de desenvolvimento.
"""


def upgrade(cursor):
    # Politicas de branch-ambiente
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS branch_policies (
            id SERIAL PRIMARY KEY,
            environment_id INTEGER NOT NULL,
            repo_name TEXT NOT NULL,
            branch_name TEXT NOT NULL,
            allow_push BOOLEAN DEFAULT TRUE,
            allow_pull BOOLEAN DEFAULT TRUE,
            allow_commit BOOLEAN DEFAULT TRUE,
            allow_create_branch BOOLEAN DEFAULT FALSE,
            require_approval BOOLEAN DEFAULT FALSE,
            is_default BOOLEAN DEFAULT FALSE,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(environment_id, repo_name, branch_name)
        )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_branch_policies_env ON branch_policies (environment_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_branch_policies_repo ON branch_policies (repo_name, branch_name)")

    # Cache de analise de impacto de fontes
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS source_impact_cache (
            id SERIAL PRIMARY KEY,
            environment_id INTEGER NOT NULL,
            file_path TEXT NOT NULL,
            file_hash TEXT,
            tables_referenced JSONB DEFAULT '[]',
            functions_defined JSONB DEFAULT '[]',
            includes JSONB DEFAULT '[]',
            analyzed_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_source_impact_env ON source_impact_cache (environment_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_source_impact_file ON source_impact_cache (file_path)")


def downgrade(cursor):
    cursor.execute("DROP TABLE IF EXISTS source_impact_cache")
    cursor.execute("DROP TABLE IF EXISTS branch_policies")
