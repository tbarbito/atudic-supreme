"""
Migration 020: Base de conhecimento TDN (TOTVS Developer Network)

Cria tabelas para armazenar paginas e chunks do TDN,
permitindo busca full-text pelo agente IA e gestao do scraping.
"""


def upgrade(cursor):
    # Tabela de paginas rastreadas
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tdn_pages (
            id SERIAL PRIMARY KEY,
            source TEXT NOT NULL,
            page_title TEXT NOT NULL,
            page_url TEXT NOT NULL UNIQUE,
            breadcrumb TEXT,
            content_hash TEXT,
            content_length INTEGER DEFAULT 0,
            chunks_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending',
            error_message TEXT,
            scraped_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tdn_pages_source ON tdn_pages(source)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tdn_pages_status ON tdn_pages(status)")

    # Tabela de chunks para busca
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tdn_chunks (
            id SERIAL PRIMARY KEY,
            page_id INTEGER NOT NULL REFERENCES tdn_pages(id) ON DELETE CASCADE,
            chunk_index INTEGER NOT NULL,
            content TEXT NOT NULL,
            content_type TEXT DEFAULT 'text',
            section_title TEXT,
            tokens_approx INTEGER,
            content_hash TEXT NOT NULL,
            metadata JSONB DEFAULT '{}',
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tdn_chunks_page ON tdn_chunks(page_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tdn_chunks_type ON tdn_chunks(content_type)")
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_tdn_chunks_unique ON tdn_chunks(page_id, chunk_index)")

    # Full-text search com tsvector (portugues)
    cursor.execute("""
        ALTER TABLE tdn_chunks ADD COLUMN IF NOT EXISTS
            tsv tsvector GENERATED ALWAYS AS (
                setweight(to_tsvector('portuguese', coalesce(section_title, '')), 'A') ||
                setweight(to_tsvector('portuguese', content), 'B')
            ) STORED
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_tdn_chunks_tsv ON tdn_chunks USING gin(tsv)
    """)

    # Tabela de controle de scraping (checkpoint/resume)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tdn_scrape_runs (
            id SERIAL PRIMARY KEY,
            source TEXT NOT NULL,
            total_pages INTEGER DEFAULT 0,
            scraped_pages INTEGER DEFAULT 0,
            chunked_pages INTEGER DEFAULT 0,
            errors INTEGER DEFAULT 0,
            status TEXT DEFAULT 'running',
            started_at TIMESTAMP DEFAULT NOW(),
            finished_at TIMESTAMP
        )
    """)


def downgrade(cursor):
    cursor.execute("DROP TABLE IF EXISTS tdn_scrape_runs CASCADE")
    cursor.execute("DROP TABLE IF EXISTS tdn_chunks CASCADE")
    cursor.execute("DROP TABLE IF EXISTS tdn_pages CASCADE")
