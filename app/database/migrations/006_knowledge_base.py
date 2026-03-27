"""
Migration 006: Base de Conhecimento + Histórico de Correções + Regras de Notificação.

Cria as tabelas:
- knowledge_articles: artigos de erros conhecidos com soluções
- correction_history: histórico de correções aplicadas
- notification_rules: regras inteligentes de notificação
- alert_recurrence: cache de erros recorrentes (materializado)
"""


def upgrade(cursor):
    # ==========================================
    # 1. BASE DE CONHECIMENTO
    # ==========================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_articles (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            error_pattern TEXT,
            description TEXT,
            causes TEXT,
            solution TEXT,
            code_snippet TEXT,
            reference_url TEXT,
            tags TEXT,
            source TEXT DEFAULT 'manual',
            is_active BOOLEAN DEFAULT TRUE,
            usage_count INTEGER DEFAULT 0,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_kb_category " "ON knowledge_articles (category)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_kb_active " "ON knowledge_articles (is_active)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_kb_source " "ON knowledge_articles (source)")

    # ==========================================
    # 2. HISTÓRICO DE CORREÇÕES
    # ==========================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS correction_history (
            id SERIAL PRIMARY KEY,
            environment_id INTEGER,
            alert_id INTEGER,
            article_id INTEGER,
            error_category TEXT NOT NULL,
            error_message TEXT NOT NULL,
            source_file TEXT,
            correction_applied TEXT NOT NULL,
            lesson_learned TEXT,
            status TEXT DEFAULT 'applied',
            applied_by INTEGER,
            applied_at TIMESTAMP DEFAULT NOW(),
            validated_at TIMESTAMP,
            validated_by INTEGER,
            notes TEXT
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ch_env " "ON correction_history (environment_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ch_category " "ON correction_history (error_category)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ch_applied " "ON correction_history (applied_at DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ch_alert " "ON correction_history (alert_id)")

    # ==========================================
    # 3. REGRAS DE NOTIFICAÇÃO INTELIGENTE
    # ==========================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notification_rules (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            environment_id INTEGER,
            severity TEXT NOT NULL DEFAULT 'critical',
            category TEXT,
            min_occurrences INTEGER DEFAULT 1,
            time_window_minutes INTEGER DEFAULT 5,
            cooldown_minutes INTEGER DEFAULT 30,
            notify_email BOOLEAN DEFAULT TRUE,
            notify_whatsapp BOOLEAN DEFAULT FALSE,
            notify_webhook BOOLEAN DEFAULT FALSE,
            recipients TEXT,
            is_active BOOLEAN DEFAULT TRUE,
            last_triggered_at TIMESTAMP,
            trigger_count INTEGER DEFAULT 0,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_nr_env " "ON notification_rules (environment_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_nr_active " "ON notification_rules (is_active)")

    # ==========================================
    # 4. CACHE DE RECORRÊNCIA DE ALERTAS
    # ==========================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS alert_recurrence (
            id SERIAL PRIMARY KEY,
            environment_id INTEGER,
            category TEXT NOT NULL,
            message_hash TEXT NOT NULL,
            message_sample TEXT,
            occurrence_count INTEGER DEFAULT 1,
            first_seen_at TIMESTAMP DEFAULT NOW(),
            last_seen_at TIMESTAMP DEFAULT NOW(),
            last_alert_id INTEGER,
            suggestion_article_id INTEGER,
            UNIQUE (environment_id, category, message_hash)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ar_env_cat " "ON alert_recurrence (environment_id, category)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ar_count " "ON alert_recurrence (occurrence_count DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ar_last_seen " "ON alert_recurrence (last_seen_at DESC)")


def downgrade(cursor):
    cursor.execute("DROP TABLE IF EXISTS alert_recurrence")
    cursor.execute("DROP TABLE IF EXISTS notification_rules")
    cursor.execute("DROP TABLE IF EXISTS correction_history")
    cursor.execute("DROP TABLE IF EXISTS knowledge_articles")
