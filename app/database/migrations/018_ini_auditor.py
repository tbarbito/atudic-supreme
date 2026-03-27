"""
Migration 018: Módulo Auditor de arquivos INI Protheus.

Tabelas para auditoria de configuração de servidores Protheus:
- ini_audits: histórico de uploads e análises
- ini_best_practices: regras de boas práticas por seção/chave
- ini_audit_results: resultados detalhados por chave analisada
"""


def upgrade(cursor):
    # Tabela de auditorias (histórico de uploads)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ini_audits (
            id SERIAL PRIMARY KEY,
            environment_id INTEGER,
            user_id INTEGER,
            filename VARCHAR(255) NOT NULL,
            ini_type VARCHAR(50) NOT NULL,
            raw_content TEXT NOT NULL,
            parsed_json TEXT,
            total_sections INTEGER DEFAULT 0,
            total_keys INTEGER DEFAULT 0,
            score NUMERIC(5,2),
            llm_summary TEXT,
            llm_provider VARCHAR(50),
            llm_model VARCHAR(100),
            status VARCHAR(20) DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_ini_audits_env
        ON ini_audits(environment_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_ini_audits_user
        ON ini_audits(user_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_ini_audits_type
        ON ini_audits(ini_type)
    """)

    # Tabela de boas práticas (regras)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ini_best_practices (
            id SERIAL PRIMARY KEY,
            ini_type VARCHAR(50) NOT NULL,
            section VARCHAR(100) NOT NULL,
            key_name VARCHAR(100) NOT NULL,
            recommended_value TEXT,
            value_type VARCHAR(20) DEFAULT 'string',
            min_value TEXT,
            max_value TEXT,
            enum_values TEXT,
            severity VARCHAR(20) DEFAULT 'info',
            description TEXT,
            tdn_url TEXT,
            is_required BOOLEAN DEFAULT FALSE,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(ini_type, section, key_name)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_bp_ini_type
        ON ini_best_practices(ini_type)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_bp_severity
        ON ini_best_practices(severity)
    """)

    # Tabela de resultados por chave
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ini_audit_results (
            id SERIAL PRIMARY KEY,
            audit_id INTEGER NOT NULL REFERENCES ini_audits(id) ON DELETE CASCADE,
            best_practice_id INTEGER REFERENCES ini_best_practices(id),
            section VARCHAR(100) NOT NULL,
            key_name VARCHAR(100) NOT NULL,
            current_value TEXT,
            recommended_value TEXT,
            severity VARCHAR(20) DEFAULT 'info',
            status VARCHAR(20) DEFAULT 'mismatch',
            llm_insight TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_results_audit
        ON ini_audit_results(audit_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_results_status
        ON ini_audit_results(status)
    """)


def downgrade(cursor):
    cursor.execute("DROP TABLE IF EXISTS ini_audit_results")
    cursor.execute("DROP TABLE IF EXISTS ini_best_practices")
    cursor.execute("DROP TABLE IF EXISTS ini_audits")
