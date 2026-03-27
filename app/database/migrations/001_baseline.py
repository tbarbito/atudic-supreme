# -*- coding: utf-8 -*-
"""
Migration 001 — Baseline AtuDIC Supreme

Cria tabelas base que nao sao criadas pelo seeds.py:
- server_variables, database_connections, alerts, pipelines, etc.
- Tabelas do agente: agent_settings, agent_audit_log
"""


def _table_exists(cursor, table):
    cursor.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_name = %s",
        (table,)
    )
    return cursor.fetchone() is not None


def _column_exists(cursor, table, column):
    cursor.execute(
        "SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s",
        (table, column)
    )
    return cursor.fetchone() is not None


def upgrade(cursor):
    """Cria tabelas base da plataforma."""

    # Variaveis do servidor
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS server_variables (
            id SERIAL PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            value TEXT NOT NULL,
            description TEXT,
            is_protected BOOLEAN DEFAULT FALSE,
            is_password BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP NOT NULL
        )
    """)

    # Conexoes de banco (para acessar Protheus)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS database_connections (
            id SERIAL PRIMARY KEY,
            environment_id INTEGER REFERENCES environments(id),
            name VARCHAR(255) NOT NULL,
            driver VARCHAR(50) NOT NULL DEFAULT 'mssql',
            host VARCHAR(255) NOT NULL,
            port INTEGER NOT NULL DEFAULT 1433,
            database_name VARCHAR(255) NOT NULL,
            username VARCHAR(255),
            password_encrypted TEXT,
            is_readonly BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP NOT NULL,
            updated_at TIMESTAMP
        )
    """)

    # Configuracoes do agente
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_settings (
            id SERIAL PRIMARY KEY,
            environment_id INTEGER REFERENCES environments(id),
            key VARCHAR(255) NOT NULL,
            value TEXT,
            updated_at TIMESTAMP,
            UNIQUE(environment_id, key)
        )
    """)

    # Auditoria do agente
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_audit_log (
            id SERIAL PRIMARY KEY,
            environment_id INTEGER,
            user_id INTEGER,
            username VARCHAR(255),
            action VARCHAR(255) NOT NULL,
            params TEXT,
            result_status VARCHAR(50),
            tokens_used INTEGER,
            iteration INTEGER,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)

    # Historico de operacoes no dicionario
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dictionary_history (
            id SERIAL PRIMARY KEY,
            environment_id INTEGER,
            operation VARCHAR(100) NOT NULL,
            conn_id_a INTEGER,
            conn_id_b INTEGER,
            company_code VARCHAR(10),
            tables_filter TEXT,
            result_summary TEXT,
            details TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            created_by INTEGER
        )
    """)

    # Indices de performance
    if _table_exists(cursor, 'agent_audit_log'):
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_agent_audit_created ON agent_audit_log(created_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_agent_audit_action ON agent_audit_log(action)")

    if _table_exists(cursor, 'dictionary_history'):
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_dict_history_created ON dictionary_history(created_at)")


def downgrade(cursor):
    """Baseline nao pode ser revertido."""
    raise NotImplementedError("A migration baseline nao pode ser revertida")
