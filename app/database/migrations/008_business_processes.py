"""
Migration 008: Modulo de Processos da Empresa.

Cria as tabelas:
- business_processes: processos de negocio do ERP Protheus
- process_tables: vinculo processo <-> tabela do banco
- process_fields: campos importantes de cada tabela vinculada
- process_flows: fluxo de dados entre processos
"""


def upgrade(cursor):
    # ==========================================
    # 1. PROCESSOS DE NEGOCIO
    # ==========================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS business_processes (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            module TEXT NOT NULL,
            module_label TEXT,
            status TEXT DEFAULT 'active',
            icon TEXT DEFAULT 'fa-cogs',
            color TEXT DEFAULT '#007bff',
            is_system BOOLEAN DEFAULT FALSE,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP,
            UNIQUE(name)
        )
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_bp_module "
        "ON business_processes (module)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_bp_status "
        "ON business_processes (status)"
    )

    # ==========================================
    # 2. TABELAS VINCULADAS AOS PROCESSOS
    # ==========================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS process_tables (
            id SERIAL PRIMARY KEY,
            process_id INTEGER NOT NULL,
            connection_id INTEGER,
            table_name TEXT NOT NULL,
            table_alias TEXT,
            table_role TEXT DEFAULT 'principal',
            description TEXT,
            sort_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW()

        )
    """)
    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_pt_unique "
        "ON process_tables (process_id, table_name, COALESCE(connection_id, 0))"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_pt_process "
        "ON process_tables (process_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_pt_conn "
        "ON process_tables (connection_id)"
    )

    # ==========================================
    # 3. CAMPOS IMPORTANTES DAS TABELAS
    # ==========================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS process_fields (
            id SERIAL PRIMARY KEY,
            process_table_id INTEGER NOT NULL,
            column_name TEXT NOT NULL,
            column_label TEXT,
            is_key BOOLEAN DEFAULT FALSE,
            is_required BOOLEAN DEFAULT FALSE,
            business_rule TEXT,
            sort_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(process_table_id, column_name)
        )
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_pf_table "
        "ON process_fields (process_table_id)"
    )

    # ==========================================
    # 4. FLUXOS ENTRE PROCESSOS
    # ==========================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS process_flows (
            id SERIAL PRIMARY KEY,
            source_process_id INTEGER NOT NULL,
            target_process_id INTEGER NOT NULL,
            source_table TEXT,
            target_table TEXT,
            flow_type TEXT DEFAULT 'data',
            description TEXT,
            sort_order INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_pflow_source "
        "ON process_flows (source_process_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_pflow_target "
        "ON process_flows (target_process_id)"
    )


def downgrade(cursor):
    cursor.execute("DROP TABLE IF EXISTS process_flows")
    cursor.execute("DROP TABLE IF EXISTS process_fields")
    cursor.execute("DROP TABLE IF EXISTS process_tables")
    cursor.execute("DROP TABLE IF EXISTS business_processes")
