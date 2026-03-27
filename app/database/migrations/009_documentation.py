"""
Migration 009: Geração Automática de Documentação
Cria tabela generated_docs para armazenar documentos gerados com versionamento.
"""


def upgrade(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS generated_docs (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            doc_type TEXT NOT NULL,
            doc_format TEXT DEFAULT 'markdown',
            content_md TEXT NOT NULL,
            metadata JSONB,
            version INTEGER DEFAULT 1,
            parent_id INTEGER,
            file_size INTEGER DEFAULT 0,
            generated_by INTEGER,
            generated_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_gendocs_type ON generated_docs (doc_type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_gendocs_date ON generated_docs (generated_at DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_gendocs_parent ON generated_docs (parent_id)")


def downgrade(cursor):
    cursor.execute("DROP TABLE IF EXISTS generated_docs")
