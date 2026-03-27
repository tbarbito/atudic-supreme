"""
Migration 004: Observability - Tabelas para monitoramento de logs do Protheus.

Cria tabelas para:
- log_monitor_configs: Configuração de monitoramento por ambiente.
  O campo log_path aceita: nome do arquivo (ex: 'console.log') que será
  combinado com LOG_DIR_{SUFFIX} das server_variables, caminho completo,
  ou variáveis {{LOG_DIR}}/arquivo.log que serão resolvidas automaticamente.
- log_alerts: Alertas parseados dos console.log e error.log do Protheus
"""


def upgrade(cursor):
    # Configuração de monitoramento de logs por ambiente
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS log_monitor_configs (
            id SERIAL PRIMARY KEY,
            environment_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            log_type TEXT NOT NULL DEFAULT 'console',
            log_path TEXT NOT NULL,
            os_type TEXT NOT NULL DEFAULT 'windows',
            is_active BOOLEAN DEFAULT TRUE,
            check_interval_seconds INTEGER DEFAULT 60,
            last_read_position BIGINT DEFAULT 0,
            last_read_at TIMESTAMP,
            created_by INTEGER,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP
        )
    """)

    # Alertas parseados dos logs
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS log_alerts (
            id SERIAL PRIMARY KEY,
            config_id INTEGER NOT NULL,
            environment_id INTEGER NOT NULL,
            severity TEXT NOT NULL,
            category TEXT NOT NULL,
            message TEXT NOT NULL,
            raw_line TEXT,
            source_file TEXT,
            line_number BIGINT,
            thread_id TEXT,
            username TEXT,
            computer_name TEXT,
            occurred_at TIMESTAMP,
            acknowledged BOOLEAN DEFAULT FALSE,
            acknowledged_by INTEGER,
            acknowledged_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            details JSONB
        )
    """)

    # Indices para performance em queries frequentes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_log_alerts_env ON log_alerts (environment_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_log_alerts_severity ON log_alerts (severity)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_log_alerts_category ON log_alerts (category)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_log_alerts_occurred ON log_alerts (occurred_at DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_log_alerts_ack ON log_alerts (acknowledged)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_log_alerts_config ON log_alerts (config_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_log_monitor_env ON log_monitor_configs (environment_id)")


def downgrade(cursor):
    cursor.execute("DROP TABLE IF EXISTS log_alerts")
    cursor.execute("DROP TABLE IF EXISTS log_monitor_configs")
