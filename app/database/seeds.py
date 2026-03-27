# -*- coding: utf-8 -*-
"""
Seeds — Inicializacao do banco de dados AtuDIC Supreme.

Cria banco automaticamente se nao existir + tabelas base + dados iniciais.
Origem: AtuDIC (Barbito) adaptado para AtuDIC Supreme.
"""

import os
from datetime import datetime
from .core import get_db, release_db_connection, DB_CONFIG
import psycopg2
from psycopg2 import Error as PsycopgError


def create_database_if_not_exists():
    """Verifica se o banco de dados existe e cria se necessario."""
    os.environ.setdefault('LC_MESSAGES', 'C')

    db_name = DB_CONFIG['database']
    print(f"[INFO] Verificando se o banco '{db_name}' existe...")

    # Tentar conectar direto
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        conn.close()
        print(f"[OK] Banco '{db_name}' ja existe")
        return True
    except UnicodeDecodeError:
        print(f"[AVISO] Erro de encoding na resposta do PostgreSQL (locale Windows)")
    except psycopg2.OperationalError as e:
        error_msg = str(e).lower()
        if 'does not exist' not in error_msg:
            print(f"[ERRO] Erro de conexao ao banco: {e}")
            return False

    # Banco nao existe — criar
    print(f"[INFO] Banco '{db_name}' nao existe, tentando criar...")

    for maint_db in ['postgres', 'defaultdb']:
        admin_config = DB_CONFIG.copy()
        admin_config['database'] = maint_db
        admin_config['client_encoding'] = 'UTF8'

        try:
            conn = psycopg2.connect(**admin_config)
            conn.autocommit = True
            cursor = conn.cursor()
            cursor.execute(f"""
                CREATE DATABASE {db_name}
                WITH OWNER = {DB_CONFIG['user']}
                ENCODING = 'UTF8'
                LC_COLLATE = 'C'
                LC_CTYPE = 'C'
                TEMPLATE = template0
            """)
            print(f"[OK] Banco '{db_name}' criado com sucesso usando '{maint_db}'")
            cursor.close()
            conn.close()
            return True
        except UnicodeDecodeError:
            print(f"[AVISO] Erro de encoding ao conectar em '{maint_db}'")
            continue
        except psycopg2.OperationalError as e:
            if 'does not exist' in str(e).lower():
                continue
            print(f"[ERRO] Erro ao tentar criar banco com '{maint_db}': {e}")
        except Exception as e:
            print(f"[ERRO] Erro ao tentar criar banco com '{maint_db}': {e}")

    print(f"[ERRO] Nao foi possivel criar o banco '{db_name}'")
    return False


def init_db():
    """Inicializa o banco de dados com as tabelas base."""

    if not create_database_if_not_exists():
        print("[ERRO] Nao foi possivel criar o banco de dados!")
        print("[DICA] Crie o banco manualmente: CREATE DATABASE atudic_supreme;")
        raise Exception("Banco de dados nao existe e nao pode ser criado")

    conn = get_db()
    cursor = conn.cursor()

    # Tabela de ambientes
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS environments (
            id SERIAL PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            created_at TIMESTAMP NOT NULL
        )
    """)

    # Ambientes padrao
    cursor.execute("SELECT COUNT(*) FROM environments")
    if cursor.fetchone()['count'] == 0:
        now = datetime.now()
        cursor.executemany(
            "INSERT INTO environments (name, description, created_at) VALUES (%s, %s, %s)",
            [
                ('Producao', 'Ambiente de producao principal', now),
                ('Homologacao', 'Ambiente de homologacao para validacoes', now),
                ('Desenvolvimento', 'Ambiente para desenvolvimento', now),
            ]
        )
        print("[OK] Ambientes padrao criados")

    # Tabela de usuarios
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(255) UNIQUE NOT NULL,
            name VARCHAR(255) NOT NULL,
            email VARCHAR(255) NOT NULL,
            password VARCHAR(255) NOT NULL,
            password_salt VARCHAR(255),
            profile VARCHAR(50) NOT NULL DEFAULT 'viewer',
            active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP NOT NULL,
            last_login TIMESTAMP,
            session_token VARCHAR(255),
            last_activity TIMESTAMP,
            session_timeout_minutes INTEGER DEFAULT 0
        )
    """)

    # Tabela de workspaces (registro no PG — dados no SQLite)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS workspaces (
            id SERIAL PRIMARY KEY,
            slug VARCHAR(255) UNIQUE NOT NULL,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            client_name VARCHAR(255),
            mode VARCHAR(50) DEFAULT 'offline',
            db_connection_id INTEGER,
            company_code VARCHAR(10) DEFAULT '01',
            created_at TIMESTAMP NOT NULL,
            updated_at TIMESTAMP,
            created_by INTEGER REFERENCES users(id)
        )
    """)

    # Tabela de historico de operacoes do workspace
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS workspace_history (
            id SERIAL PRIMARY KEY,
            workspace_id INTEGER REFERENCES workspaces(id),
            operation VARCHAR(100) NOT NULL,
            details TEXT,
            stats TEXT,
            created_at TIMESTAMP NOT NULL,
            created_by INTEGER REFERENCES users(id)
        )
    """)

    conn.commit()
    release_db_connection(conn)
    print("[OK] Banco de dados inicializado com sucesso")
