"""
Database utility module.

This module handles database configuration and connection.
"""
import os
import psycopg2
from psycopg2 import IntegrityError, Error as PsycopgError
import psycopg2.pool
import psycopg2.extras
DEBUG_DB = os.getenv('DEBUG_DB', 'false').lower() == 'true'

import urllib.parse

# Configurações do PostgreSQL
# Permite que o DB_HOST seja uma URI completa (postgres://user:pass@host:port/dbname)
raw_host = os.getenv('DB_HOST', 'localhost')

# Dicionário base — sem defaults para credenciais em produção
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

# Se o host vier como uma URI do tipo postgres://, faremos o parse para sobrescrever os valores
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
    
    # Se na URI tiver SSL mode (ex: ?sslmode=require), podemos puxar de lá também
    query_params = urllib.parse.parse_qs(parsed.query)
    if 'sslmode' in query_params:
         DB_CONFIG['sslmode'] = str(query_params['sslmode'][0])

# Se configurado SSL_MODE via .env, adiciona ou sobrescreve no dicionário
ssl_mode = os.getenv('DB_SSLMODE', '')
if ssl_mode:
    DB_CONFIG['sslmode'] = ssl_mode

import psycopg2.extras

# --- CONNECTION POOLING ---
# Instância global do pool
_db_pool = None

POOL_MIN = int(os.getenv('DB_POOL_MIN', '2'))
POOL_MAX = int(os.getenv('DB_POOL_MAX', '30'))
POOL_WARN_THRESHOLD = 0.9  # log warning quando pool > 90% ocupado


def init_pool():
    """Inicializa o pool de conexoes se ele nao existir"""
    global _db_pool
    if _db_pool is None:
        try:
            if DEBUG_DB:
                 debug_config = {k: v for k, v in DB_CONFIG.items() if k != 'password'}
                 print(f"[DEBUG] Inicializando Connection Pool: {debug_config}")

            # ThreadedConnectionPool é thread-safe (SimpleConnectionPool não é)
            # Necessário porque runners, SSE e scheduler rodam em threads separadas
            _db_pool = psycopg2.pool.ThreadedConnectionPool(
                POOL_MIN, POOL_MAX,
                connection_factory=psycopg2.extras.RealDictConnection,
                **DB_CONFIG
            )

            if DEBUG_DB:
                print(f"[OK] ThreadedConnectionPool inicializado ({POOL_MIN}-{POOL_MAX} conexões)")
        except UnicodeDecodeError as e:
            # PostgreSQL no Windows com locale pt-BR pode retornar mensagens
            # em cp1252 que psycopg2 não consegue decodificar como UTF-8
            print(f"[ERRO] Erro de encoding na resposta do PostgreSQL: {e}")
            print("[DICA] Verifique o locale do PostgreSQL (LC_MESSAGES)")
            raise
        except psycopg2.OperationalError as e:
             debug_config = {k: v for k, v in DB_CONFIG.items() if k != 'password'}
             error_msg = str(e).lower()
             print(f"[ERRO] Erro ao init connection pool: {e}")

             if 'does not exist' in error_msg or 'database' in error_msg:
                 print(f"[DICA] O banco '{DB_CONFIG['database']}' nao existe!")
                 print("[DICA] O banco sera criado durante a primeira inicializacao.")
             raise
        except Exception as e:
            print(f"[ERRO] Erro inesperado ao criar pool: {e}")
            raise

def _check_pool_usage():
    """Loga warning se o pool estiver próximo da capacidade máxima."""
    if _db_pool is None:
        return
    try:
        # _used é dict de conexões emprestadas (chave=id(conn), valor=conn)
        used = len(_db_pool._used)
        if used >= POOL_MAX * POOL_WARN_THRESHOLD:
            print(f"[WARN] Pool de conexões em {used}/{POOL_MAX} ({used * 100 // POOL_MAX}% ocupado)")
    except Exception:
        pass  # atributos internos podem variar entre versões


def get_db_connection():
    """Obtem uma conexao do pool"""
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
        print(f"[ERRO] Pool esgotado ({POOL_MAX} conexões em uso): {e}")
        raise
    except Exception as e:
        print(f"[ERRO] Falha ao capturar conexao do pool: {e}")
        raise

def release_db_connection(conn):
    """Devolve a conexao pro pool"""
    if _db_pool is not None and conn is not None:
        try:
             _db_pool.putconn(conn)
        except Exception as e:
             print(f"[ERRO] Falha ao devolver conexao ao pool: {e}")

class DatabaseConnection:
    """Gerenciador de contexto para uso do pool com o operador 'with' """
    def __init__(self):
        self.conn = None
        
    def __enter__(self):
        self.conn = get_db_connection()
        return self.conn
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            release_db_connection(self.conn)

class TransactionContext:
    """Context manager com commit/rollback automático.

    Uso:
        with TransactionContext() as (conn, cursor):
            cursor.execute("INSERT INTO ...")
            cursor.execute("UPDATE ...")
        # commit automático ao sair sem erro
        # rollback automático se houver exceção

    O conn é devolvido ao pool automaticamente no finally.
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
        return False  # não suprime exceções


def get_db():
    """
    Retorna uma conexao do pool de conexões.
    Utilizando RealDictConnection na base, os cursores já atuarão como dicionários.
    Lembre-se de retornar as conexões ao pool após o uso (ex: release_db_connection(conn)).
    """
    try:
        return get_db_connection()
    except Exception as e:
        print(f"[ERRO] Falha de conexao generica get_db: {e}")
        raise
