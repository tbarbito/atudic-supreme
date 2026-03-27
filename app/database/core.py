# -*- coding: utf-8 -*-
"""
Database core — Pool de conexoes PostgreSQL.

Origem: AtuDIC (Barbito) adaptado para AtuDIC Supreme.
"""

import os
import urllib.parse
import psycopg2
import psycopg2.pool
import psycopg2.extras
from psycopg2 import Error as PsycopgError

DEBUG_DB = os.getenv('DEBUG_DB', 'false').lower() == 'true'

# Configuracao PostgreSQL
raw_host = os.getenv('DB_HOST', 'localhost')

_db_password = os.getenv('DB_PASSWORD', '')
if not _db_password:
    print("[WARN] DB_PASSWORD nao definida no .env — usando fallback de desenvolvimento")
    _db_password = 'atudic_supreme_2026'

DB_CONFIG = {
    'host': raw_host,
    'port': int(os.getenv('DB_PORT', '5432')),
    'database': os.getenv('DB_NAME', 'atudic_supreme'),
    'user': os.getenv('DB_USER', 'atudic_supreme'),
    'password': _db_password,
    'client_encoding': 'UTF8'
}

# Suporte a URI postgres://
if raw_host.startswith('postgres://') or raw_host.startswith('postgresql://'):
    parsed = urllib.parse.urlparse(raw_host)
    if parsed.hostname:
        DB_CONFIG['host'] = str(parsed.hostname)
    if parsed.port is not None:
        DB_CONFIG['port'] = int(str(parsed.port))
    if parsed.username:
        DB_CONFIG['user'] = urllib.parse.unquote(str(parsed.username))
    if parsed.password:
        DB_CONFIG['password'] = urllib.parse.unquote(str(parsed.password))
    if parsed.path and parsed.path != '/':
        DB_CONFIG['database'] = str(parsed.path.lstrip('/'))
    query_params = urllib.parse.parse_qs(parsed.query)
    if 'sslmode' in query_params:
        DB_CONFIG['sslmode'] = str(query_params['sslmode'][0])

ssl_mode = os.getenv('DB_SSLMODE', '')
if ssl_mode:
    DB_CONFIG['sslmode'] = ssl_mode

# --- CONNECTION POOLING ---
_db_pool = None

POOL_MIN = int(os.getenv('DB_POOL_MIN', '2'))
POOL_MAX = int(os.getenv('DB_POOL_MAX', '30'))
POOL_WARN_THRESHOLD = 0.9


def init_pool():
    """Inicializa o pool de conexoes se ele nao existir."""
    global _db_pool
    if _db_pool is None:
        try:
            _db_pool = psycopg2.pool.ThreadedConnectionPool(
                POOL_MIN, POOL_MAX,
                connection_factory=psycopg2.extras.RealDictConnection,
                **DB_CONFIG
            )
            if DEBUG_DB:
                print(f"[OK] ThreadedConnectionPool inicializado ({POOL_MIN}-{POOL_MAX} conexoes)")
        except UnicodeDecodeError as e:
            print(f"[ERRO] Erro de encoding na resposta do PostgreSQL: {e}")
            print("[DICA] Verifique o locale do PostgreSQL (LC_MESSAGES)")
            raise
        except psycopg2.OperationalError as e:
            error_msg = str(e).lower()
            print(f"[ERRO] Erro ao init connection pool: {e}")
            if 'does not exist' in error_msg or 'database' in error_msg:
                print(f"[DICA] O banco '{DB_CONFIG['database']}' nao existe!")
                print("[DICA] Sera criado durante a primeira inicializacao.")
            raise
        except Exception as e:
            print(f"[ERRO] Erro inesperado ao criar pool: {e}")
            raise


def _check_pool_usage():
    """Loga warning se o pool estiver proximo da capacidade maxima."""
    if _db_pool is None:
        return
    try:
        used = len(_db_pool._used)
        if used >= POOL_MAX * POOL_WARN_THRESHOLD:
            print(f"[WARN] Pool de conexoes em {used}/{POOL_MAX} ({used * 100 // POOL_MAX}% ocupado)")
    except Exception:
        pass


def get_db_connection():
    """Obtem uma conexao do pool."""
    if _db_pool is None:
        init_pool()
    try:
        if _db_pool:
            conn = _db_pool.getconn()
            _check_pool_usage()
            return conn
        else:
            raise Exception("Connection pool nao foi inicializado.")
    except psycopg2.pool.PoolError as e:
        print(f"[ERRO] Pool esgotado ({POOL_MAX} conexoes em uso): {e}")
        raise
    except Exception as e:
        print(f"[ERRO] Falha ao capturar conexao do pool: {e}")
        raise


def release_db_connection(conn):
    """Devolve a conexao pro pool."""
    if _db_pool is not None and conn is not None:
        try:
            _db_pool.putconn(conn)
        except Exception as e:
            print(f"[ERRO] Falha ao devolver conexao ao pool: {e}")


# Aliases
get_db = get_db_connection


class DatabaseConnection:
    """Gerenciador de contexto para uso do pool com 'with'."""
    def __init__(self):
        self.conn = None

    def __enter__(self):
        self.conn = get_db_connection()
        return self.conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            release_db_connection(self.conn)


class TransactionContext:
    """Context manager com commit/rollback automatico.

    Uso:
        with TransactionContext() as (conn, cursor):
            cursor.execute("INSERT INTO ...")
        # commit automatico ao sair sem erro
        # rollback automatico se houver excecao
    """
    def __init__(self):
        self.conn = None

    def __enter__(self):
        self.conn = get_db_connection()
        cursor = self.conn.cursor()
        return self.conn, cursor

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            try:
                if exc_type is None:
                    self.conn.commit()
                else:
                    self.conn.rollback()
            except Exception:
                pass
            finally:
                release_db_connection(self.conn)
        return False
