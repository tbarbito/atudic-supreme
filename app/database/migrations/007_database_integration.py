"""
Migration 007: Integração com Banco de Dados do Protheus.

Cria as tabelas:
- database_connections: conexões com bancos de dados externos (Protheus)
- schema_cache: cache de estrutura de tabelas/campos descobertos
"""


def upgrade(cursor):
    # ==========================================
    # 1. CONEXÕES COM BANCOS DE DADOS
    # ==========================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS database_connections (
            id SERIAL PRIMARY KEY,
            environment_id INTEGER,
            name TEXT NOT NULL,
            driver TEXT NOT NULL DEFAULT 'mssql',
            host TEXT NOT NULL,
            port INTEGER NOT NULL DEFAULT 1433,
            database_name TEXT NOT NULL,
            username TEXT NOT NULL,
            password_encrypted TEXT NOT NULL,
            extra_params TEXT,
            is_active BOOLEAN DEFAULT TRUE,
            is_readonly BOOLEAN DEFAULT TRUE,
            last_connected_at TIMESTAMP,
            last_error TEXT,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP
        )
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_dbconn_env "
        "ON database_connections (environment_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_dbconn_active "
        "ON database_connections (is_active)"
    )

    # ==========================================
    # 2. CACHE DE SCHEMA (TABELAS E CAMPOS)
    # ==========================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_cache (
            id SERIAL PRIMARY KEY,
            connection_id INTEGER NOT NULL,
            table_name TEXT NOT NULL,
            table_alias TEXT,
            table_description TEXT,
            column_name TEXT NOT NULL,
            column_type TEXT,
            column_size INTEGER,
            column_decimal INTEGER,
            is_key BOOLEAN DEFAULT FALSE,
            is_nullable BOOLEAN DEFAULT TRUE,
            column_order INTEGER DEFAULT 0,
            cached_at TIMESTAMP DEFAULT NOW(),
            UNIQUE (connection_id, table_name, column_name)
        )
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_schema_conn "
        "ON schema_cache (connection_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_schema_table "
        "ON schema_cache (connection_id, table_name)"
    )

    # ==========================================
    # 3. HISTÓRICO DE QUERIES EXECUTADAS
    # ==========================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS query_history (
            id SERIAL PRIMARY KEY,
            connection_id INTEGER NOT NULL,
            executed_by INTEGER,
            query_text TEXT NOT NULL,
            row_count INTEGER,
            duration_ms INTEGER,
            status TEXT DEFAULT 'success',
            error_message TEXT,
            executed_at TIMESTAMP DEFAULT NOW()
        )
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_qhist_conn "
        "ON query_history (connection_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_qhist_date "
        "ON query_history (executed_at DESC)"
    )


def downgrade(cursor):
    cursor.execute("DROP TABLE IF EXISTS query_history")
    cursor.execute("DROP TABLE IF EXISTS schema_cache")
    cursor.execute("DROP TABLE IF EXISTS database_connections")
