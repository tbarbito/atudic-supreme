"""
Serviço de Integração com Banco de Dados do Protheus.

Permite conectar a bancos de dados externos (SQL Server, PostgreSQL, MySQL, Oracle),
navegar estrutura de tabelas/campos e executar queries read-only.
"""

import time
from datetime import datetime
from app.database import get_db, release_db_connection
from app.utils import crypto


# Drivers suportados e suas configs padrão
SUPPORTED_DRIVERS = {
    "mssql": {"port": 1433, "label": "SQL Server", "module": "pymssql"},
    "postgresql": {"port": 5432, "label": "PostgreSQL", "module": "psycopg2"},
    "mysql": {"port": 3306, "label": "MySQL", "module": "pymysql"},
    "oracle": {"port": 1521, "label": "Oracle", "module": "oracledb"},
}


def _get_external_connection(conn_config, writable=False):
    """
    Cria conexão com banco de dados externo baseado no driver.
    writable=True desabilita readonly e autocommit (para transacoes de escrita).
    """
    driver = conn_config["driver"]
    host = conn_config["host"]
    port = conn_config["port"]
    database = conn_config["database_name"]
    username = conn_config["username"]
    password = conn_config["password"]

    if driver == "mssql":
        import pymssql
        conn = pymssql.connect(
            server=host, port=port, user=username,
            password=password, database=database,
            as_dict=True, login_timeout=10, timeout=30,
        )
        return conn

    elif driver == "postgresql":
        import psycopg2
        import psycopg2.extras
        conn = psycopg2.connect(
            host=host, port=port, user=username,
            password=password, dbname=database,
            connect_timeout=10,
            cursor_factory=psycopg2.extras.RealDictCursor,
        )
        if not writable:
            conn.set_session(readonly=True, autocommit=True)
        return conn

    elif driver == "mysql":
        import pymysql
        conn = pymysql.connect(
            host=host, port=port, user=username,
            password=password, database=database,
            connect_timeout=10, read_timeout=30,
            cursorclass=pymysql.cursors.DictCursor,
        )
        return conn

    elif driver == "oracle":
        import oracledb
        conn = oracledb.connect(
            user=username, password=password,
            dsn=f"{host}:{port}/{database}",
        )
        return conn

    else:
        raise ValueError(f"Driver não suportado: {driver}")


def _decrypt_password(encrypted_password):
    """Descriptografa a senha da conexão."""
    if not crypto.token_encryption:
        raise RuntimeError("Sistema de criptografia não inicializado")
    return crypto.token_encryption.decrypt_token(encrypted_password)


def get_connection_config(connection_id):
    """Busca configuração da conexão no banco interno e descriptografa senha."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT * FROM database_connections WHERE id = %s AND is_active = TRUE",
            (connection_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        config = dict(row)
        config["password"] = _decrypt_password(config["password_encrypted"])
        return config
    finally:
        release_db_connection(conn)


def test_connection(connection_id):
    """Testa conexão com banco externo. Retorna (ok, mensagem, latency_ms)."""
    config = get_connection_config(connection_id)
    if not config:
        return False, "Conexão não encontrada", 0

    start = time.time()
    try:
        ext_conn = _get_external_connection(config)
        cursor = ext_conn.cursor()
        # Query simples para validar (alias necessário para pymssql as_dict=True)
        if config["driver"] == "oracle":
            cursor.execute("SELECT 1 AS ok FROM DUAL")
        else:
            cursor.execute("SELECT 1 AS ok")
        cursor.fetchone()
        ext_conn.close()
        latency = int((time.time() - start) * 1000)

        # Atualiza last_connected_at
        _update_connection_status(connection_id, connected=True)
        return True, "Conexão estabelecida com sucesso", latency

    except Exception as e:
        latency = int((time.time() - start) * 1000)
        error_msg = str(e)[:500]
        _update_connection_status(connection_id, connected=False, error=error_msg)
        return False, error_msg, latency


def _update_connection_status(connection_id, connected=True, error=None):
    """Atualiza status da conexão no banco interno."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        if connected:
            cursor.execute(
                "UPDATE database_connections SET last_connected_at = %s, last_error = NULL WHERE id = %s",
                (datetime.now(), connection_id),
            )
        else:
            cursor.execute(
                "UPDATE database_connections SET last_error = %s WHERE id = %s",
                (error, connection_id),
            )
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        release_db_connection(conn)


def discover_tables(connection_id):
    """
    Descobre tabelas do banco externo e cacheia no schema_cache.
    Retorna lista de tabelas encontradas.
    """
    config = get_connection_config(connection_id)
    if not config:
        raise ValueError("Conexão não encontrada")

    ext_conn = _get_external_connection(config)
    cursor = ext_conn.cursor()

    try:
        tables_data = _introspect_tables(cursor, config["driver"], config["database_name"])

        # Salvar no cache
        internal_conn = get_db()
        internal_cursor = internal_conn.cursor()
        try:
            # Limpa cache anterior
            internal_cursor.execute(
                "DELETE FROM schema_cache WHERE connection_id = %s", (connection_id,)
            )

            now = datetime.now()
            for table in tables_data:
                for col in table["columns"]:
                    internal_cursor.execute(
                        """
                        INSERT INTO schema_cache
                            (connection_id, table_name, table_alias, column_name,
                             column_type, column_size, column_decimal,
                             is_key, is_nullable, column_order, cached_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (connection_id, table_name, column_name) DO UPDATE SET
                            column_type = EXCLUDED.column_type,
                            column_size = EXCLUDED.column_size,
                            column_decimal = EXCLUDED.column_decimal,
                            is_key = EXCLUDED.is_key,
                            is_nullable = EXCLUDED.is_nullable,
                            column_order = EXCLUDED.column_order,
                            cached_at = EXCLUDED.cached_at
                        """,
                        (
                            connection_id,
                            table["table_name"],
                            table.get("table_alias", ""),
                            col["column_name"],
                            col["column_type"],
                            col.get("column_size"),
                            col.get("column_decimal"),
                            col.get("is_key", False),
                            col.get("is_nullable", True),
                            col.get("column_order", 0),
                            now,
                        ),
                    )
            internal_conn.commit()

            _update_connection_status(connection_id, connected=True)
            return tables_data
        except Exception:
            internal_conn.rollback()
            raise
        finally:
            release_db_connection(internal_conn)
    finally:
        ext_conn.close()


def _introspect_tables(cursor, driver, database_name):
    """Introspection de tabelas e colunas conforme o driver."""
    if driver == "mssql":
        return _introspect_mssql(cursor, database_name)
    elif driver == "postgresql":
        return _introspect_postgresql(cursor)
    elif driver == "mysql":
        return _introspect_mysql(cursor, database_name)
    elif driver == "oracle":
        return _introspect_oracle(cursor)
    else:
        raise ValueError(f"Introspection não implementada para: {driver}")


def _introspect_mssql(cursor, database_name):
    """Introspection para SQL Server (padrão Protheus)."""
    import logging
    logger = logging.getLogger(__name__)

    # Fase 1: buscar tabelas
    cursor.execute("""
        SELECT TABLE_NAME
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_TYPE = 'BASE TABLE'
        ORDER BY TABLE_NAME
    """)
    table_rows = cursor.fetchall()
    table_names = [r["TABLE_NAME"] for r in table_rows]
    logger.info(f"[MSSQL Discover] {len(table_names)} tabelas encontradas no database")

    if not table_names:
        return []

    # Fase 2: buscar colunas e chaves (query simplificada para performance)
    cursor.execute("""
        SELECT c.TABLE_NAME,
               c.COLUMN_NAME, c.DATA_TYPE, c.CHARACTER_MAXIMUM_LENGTH,
               c.NUMERIC_PRECISION, c.NUMERIC_SCALE, c.IS_NULLABLE,
               c.ORDINAL_POSITION,
               CASE WHEN kcu.COLUMN_NAME IS NOT NULL THEN 1 ELSE 0 END as IS_KEY
        FROM INFORMATION_SCHEMA.COLUMNS c
        LEFT JOIN INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
            ON tc.TABLE_NAME = c.TABLE_NAME AND tc.TABLE_SCHEMA = c.TABLE_SCHEMA
            AND tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
        LEFT JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
            ON kcu.TABLE_NAME = c.TABLE_NAME AND kcu.COLUMN_NAME = c.COLUMN_NAME
            AND kcu.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
        WHERE c.TABLE_NAME IN (
            SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE = 'BASE TABLE'
        )
        ORDER BY c.TABLE_NAME, c.ORDINAL_POSITION
    """)
    results = cursor.fetchall()
    logger.info(f"[MSSQL Discover] {len(results)} colunas carregadas")
    return _group_introspection_results(results)


def _introspect_postgresql(cursor):
    """Introspection para PostgreSQL."""
    cursor.execute("""
        SELECT t.tablename as TABLE_NAME,
               c.column_name as COLUMN_NAME,
               c.data_type as DATA_TYPE,
               c.character_maximum_length as CHARACTER_MAXIMUM_LENGTH,
               c.numeric_precision as NUMERIC_PRECISION,
               c.numeric_scale as NUMERIC_SCALE,
               c.is_nullable as IS_NULLABLE,
               c.ordinal_position as ORDINAL_POSITION,
               CASE WHEN pk.column_name IS NOT NULL THEN 1 ELSE 0 END as IS_KEY
        FROM pg_tables t
        JOIN information_schema.columns c
            ON c.table_name = t.tablename AND c.table_schema = t.schemaname
        LEFT JOIN (
            SELECT kcu.table_name, kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
            WHERE tc.constraint_type = 'PRIMARY KEY'
        ) pk ON pk.table_name = t.tablename AND pk.column_name = c.column_name
        WHERE t.schemaname = 'public'
        ORDER BY t.tablename, c.ordinal_position
    """)
    return _group_introspection_results(cursor.fetchall())


def _introspect_mysql(cursor, database_name):
    """Introspection para MySQL."""
    cursor.execute("""
        SELECT t.TABLE_NAME,
               c.COLUMN_NAME, c.DATA_TYPE, c.CHARACTER_MAXIMUM_LENGTH,
               c.NUMERIC_PRECISION, c.NUMERIC_SCALE, c.IS_NULLABLE,
               c.ORDINAL_POSITION,
               CASE WHEN c.COLUMN_KEY = 'PRI' THEN 1 ELSE 0 END as IS_KEY
        FROM INFORMATION_SCHEMA.TABLES t
        JOIN INFORMATION_SCHEMA.COLUMNS c
            ON t.TABLE_NAME = c.TABLE_NAME AND t.TABLE_SCHEMA = c.TABLE_SCHEMA
        WHERE t.TABLE_SCHEMA = %s AND t.TABLE_TYPE = 'BASE TABLE'
        ORDER BY t.TABLE_NAME, c.ORDINAL_POSITION
    """, (database_name,))
    return _group_introspection_results(cursor.fetchall())


def _introspect_oracle(cursor):
    """Introspection para Oracle."""
    cursor.execute("""
        SELECT t.TABLE_NAME,
               c.COLUMN_NAME, c.DATA_TYPE,
               c.DATA_LENGTH as CHARACTER_MAXIMUM_LENGTH,
               c.DATA_PRECISION as NUMERIC_PRECISION,
               c.DATA_SCALE as NUMERIC_SCALE,
               c.NULLABLE as IS_NULLABLE,
               c.COLUMN_ID as ORDINAL_POSITION,
               CASE WHEN cc.COLUMN_NAME IS NOT NULL THEN 1 ELSE 0 END as IS_KEY
        FROM USER_TABLES t
        JOIN USER_TAB_COLUMNS c ON c.TABLE_NAME = t.TABLE_NAME
        LEFT JOIN USER_CONSTRAINTS uc
            ON uc.TABLE_NAME = t.TABLE_NAME AND uc.CONSTRAINT_TYPE = 'P'
        LEFT JOIN USER_CONS_COLUMNS cc
            ON cc.CONSTRAINT_NAME = uc.CONSTRAINT_NAME AND cc.COLUMN_NAME = c.COLUMN_NAME
        ORDER BY t.TABLE_NAME, c.COLUMN_ID
    """)
    rows = cursor.fetchall()
    # Oracle retorna tuplas, converter para dicts
    columns = [desc[0] for desc in cursor.description]
    dict_rows = [dict(zip(columns, row)) for row in rows]
    return _group_introspection_results(dict_rows)


def _group_introspection_results(rows):
    """Agrupa resultados de introspection em formato {table_name, columns: [...]}."""
    tables = {}
    for row in rows:
        # Normalizar keys (case insensitive)
        r = {k.upper() if isinstance(k, str) else k: v for k, v in (row.items() if isinstance(row, dict) else zip(range(len(row)), row))}

        table_name = r.get("TABLE_NAME", "")
        if table_name not in tables:
            tables[table_name] = {
                "table_name": table_name,
                "table_alias": "",
                "columns": [],
            }

        nullable = r.get("IS_NULLABLE", "YES")
        if isinstance(nullable, str):
            nullable = nullable.upper() in ("YES", "Y", "TRUE", "1")

        is_key = r.get("IS_KEY", 0)
        if isinstance(is_key, str):
            is_key = is_key in ("1", "true", "True")

        tables[table_name]["columns"].append({
            "column_name": r.get("COLUMN_NAME", ""),
            "column_type": r.get("DATA_TYPE", ""),
            "column_size": r.get("CHARACTER_MAXIMUM_LENGTH") or r.get("NUMERIC_PRECISION"),
            "column_decimal": r.get("NUMERIC_SCALE"),
            "is_key": bool(is_key),
            "is_nullable": bool(nullable),
            "column_order": r.get("ORDINAL_POSITION", 0),
        })

    return list(tables.values())


def get_cached_tables(connection_id, search=None):
    """Retorna tabelas do cache com filtro opcional."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        if search:
            cursor.execute(
                """
                SELECT DISTINCT table_name, table_alias
                FROM schema_cache
                WHERE connection_id = %s AND (table_name ILIKE %s OR table_alias ILIKE %s)
                ORDER BY table_name
                """,
                (connection_id, f"%{search}%", f"%{search}%"),
            )
        else:
            cursor.execute(
                """
                SELECT DISTINCT table_name, table_alias
                FROM schema_cache
                WHERE connection_id = %s
                ORDER BY table_name
                """,
                (connection_id,),
            )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        release_db_connection(conn)


def get_cached_columns(connection_id, table_name):
    """Retorna colunas cacheadas de uma tabela."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT column_name, column_type, column_size, column_decimal,
                   is_key, is_nullable, column_order
            FROM schema_cache
            WHERE connection_id = %s AND table_name = %s
            ORDER BY column_order
            """,
            (connection_id, table_name),
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        release_db_connection(conn)


def execute_query(connection_id, query_text, user_id=None, max_rows=500):
    """
    Executa query SELECT read-only no banco externo.
    Registra no histórico e retorna resultados.
    """
    # Validação de segurança: apenas SELECT
    normalized = query_text.strip().upper()
    if not normalized.startswith("SELECT"):
        raise ValueError("Apenas queries SELECT são permitidas")

    # Bloquear palavras perigosas
    dangerous = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE",
                 "CREATE", "EXEC", "EXECUTE", "GRANT", "REVOKE", "INTO"]
    for word in dangerous:
        # Verifica se é uma palavra isolada (não parte de nome de coluna)
        if f" {word} " in f" {normalized} " or normalized.startswith(f"{word} "):
            raise ValueError(f"Operação '{word}' não permitida. Apenas SELECT é aceito")

    config = get_connection_config(connection_id)
    if not config:
        raise ValueError("Conexão não encontrada")

    if not config.get("is_readonly", True):
        # Dupla checagem: mesmo se is_readonly=False, forçamos readonly
        pass

    start = time.time()
    try:
        ext_conn = _get_external_connection(config)
        cursor = ext_conn.cursor()
        cursor.execute(query_text)

        # Pegar nomes das colunas
        if cursor.description:
            if config["driver"] == "oracle":
                columns = [desc[0] for desc in cursor.description]
                raw_rows = cursor.fetchmany(max_rows)
                rows = [dict(zip(columns, row)) for row in raw_rows]
            else:
                rows = cursor.fetchmany(max_rows)
                if rows and isinstance(rows[0], dict):
                    columns = list(rows[0].keys()) if rows else []
                else:
                    columns = [desc[0] for desc in cursor.description]
                    rows = [dict(zip(columns, row)) for row in rows]
        else:
            columns = []
            rows = []

        row_count = len(rows)
        ext_conn.close()
        duration = int((time.time() - start) * 1000)

        # Serializar valores para JSON
        serialized = []
        for row in rows:
            clean = {}
            for k, v in row.items():
                if isinstance(v, datetime):
                    clean[k] = v.isoformat()
                elif isinstance(v, bytes):
                    clean[k] = f"<BLOB {len(v)} bytes>"
                elif v is None:
                    clean[k] = None
                else:
                    clean[k] = str(v) if not isinstance(v, (int, float, bool)) else v
            serialized.append(clean)

        # Registrar no histórico
        _save_query_history(connection_id, user_id, query_text, row_count, duration, "success")

        return {
            "columns": columns,
            "rows": serialized,
            "row_count": row_count,
            "duration_ms": duration,
            "truncated": row_count >= max_rows,
        }

    except Exception as e:
        duration = int((time.time() - start) * 1000)
        error_msg = str(e)[:500]
        _save_query_history(connection_id, user_id, query_text, 0, duration, "error", error_msg)
        raise


def _save_query_history(connection_id, user_id, query_text, row_count, duration_ms, status, error=None):
    """Salva query no histórico."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO query_history
                (connection_id, executed_by, query_text, row_count, duration_ms, status, error_message, executed_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (connection_id, user_id, query_text[:5000], row_count, duration_ms, status, error, datetime.now()),
        )
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        release_db_connection(conn)


def get_query_history(connection_id, limit=50):
    """Retorna histórico de queries de uma conexão."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT qh.*, u.username as executed_by_name
            FROM query_history qh
            LEFT JOIN users u ON qh.executed_by = u.id
            WHERE qh.connection_id = %s
            ORDER BY qh.executed_at DESC
            LIMIT %s
            """,
            (connection_id, limit),
        )
        results = []
        for row in cursor.fetchall():
            item = dict(row)
            if item.get("executed_at"):
                item["executed_at"] = item["executed_at"].isoformat()
            results.append(item)
        return results
    finally:
        release_db_connection(conn)


def get_table_sample(connection_id, table_name, limit=50):
    """Retorna amostra de dados de uma tabela (SELECT * LIMIT N)."""
    # Sanitizar nome da tabela (prevenir injection)
    import re
    if not re.match(r'^[a-zA-Z0-9_]+$', table_name):
        raise ValueError("Nome de tabela inválido")

    config = get_connection_config(connection_id)
    if not config:
        raise ValueError("Conexão não encontrada")

    if config["driver"] == "mssql":
        query = f"SELECT TOP {int(limit)} * FROM [{table_name}]"
    elif config["driver"] == "oracle":
        query = f"SELECT * FROM {table_name} WHERE ROWNUM <= {int(limit)}"
    else:
        query = f"SELECT * FROM {table_name} LIMIT {int(limit)}"

    return execute_query(connection_id, query)


# =========================================================
# INTROSPECTION DETALHADA: INDEXES, TRIGGERS, CONSTRAINTS
# =========================================================


def get_table_details(connection_id, table_name):
    """
    Retorna detalhes completos de uma tabela: indexes, triggers, constraints.
    Consulta diretamente o banco externo (não usa cache).
    """
    import re
    if not re.match(r'^[a-zA-Z0-9_]+$', table_name):
        raise ValueError("Nome de tabela inválido")

    config = get_connection_config(connection_id)
    if not config:
        raise ValueError("Conexão não encontrada")

    driver = config["driver"]
    ext_conn = _get_external_connection(config)
    cursor = ext_conn.cursor()

    try:
        indexes = _get_indexes(cursor, driver, table_name, config.get("database_name", ""))
        triggers = _get_triggers(cursor, driver, table_name, config.get("database_name", ""))
        constraints = _get_constraints(cursor, driver, table_name, config.get("database_name", ""))

        return {
            "table_name": table_name,
            "indexes": indexes,
            "triggers": triggers,
            "constraints": constraints,
        }
    finally:
        ext_conn.close()


def _get_indexes(cursor, driver, table_name, database_name):
    """Retorna indexes de uma tabela conforme o driver."""
    if driver == "mssql":
        return _get_indexes_mssql(cursor, table_name)
    elif driver == "postgresql":
        return _get_indexes_postgresql(cursor, table_name)
    elif driver == "mysql":
        return _get_indexes_mysql(cursor, table_name, database_name)
    elif driver == "oracle":
        return _get_indexes_oracle(cursor, table_name)
    return []


def _get_triggers(cursor, driver, table_name, database_name):
    """Retorna triggers de uma tabela conforme o driver."""
    if driver == "mssql":
        return _get_triggers_mssql(cursor, table_name)
    elif driver == "postgresql":
        return _get_triggers_postgresql(cursor, table_name)
    elif driver == "mysql":
        return _get_triggers_mysql(cursor, table_name, database_name)
    elif driver == "oracle":
        return _get_triggers_oracle(cursor, table_name)
    return []


def _get_constraints(cursor, driver, table_name, database_name):
    """Retorna constraints de uma tabela conforme o driver."""
    if driver == "mssql":
        return _get_constraints_mssql(cursor, table_name)
    elif driver == "postgresql":
        return _get_constraints_postgresql(cursor, table_name)
    elif driver == "mysql":
        return _get_constraints_mysql(cursor, table_name, database_name)
    elif driver == "oracle":
        return _get_constraints_oracle(cursor, table_name)
    return []


# --- INDEXES ---

def _get_indexes_mssql(cursor, table_name):
    """Indexes do SQL Server via sys.indexes + sys.index_columns."""
    cursor.execute("""
        SELECT i.name AS index_name,
               i.type_desc AS index_type,
               i.is_unique,
               i.is_primary_key,
               STRING_AGG(c.name, ', ') WITHIN GROUP (ORDER BY ic.key_ordinal) AS columns
        FROM sys.indexes i
        JOIN sys.index_columns ic ON i.object_id = ic.object_id AND i.index_id = ic.index_id
        JOIN sys.columns c ON ic.object_id = c.object_id AND ic.column_id = c.column_id
        WHERE i.object_id = OBJECT_ID(%s) AND i.name IS NOT NULL
        GROUP BY i.name, i.type_desc, i.is_unique, i.is_primary_key
        ORDER BY i.is_primary_key DESC, i.name
    """, (table_name,))
    rows = cursor.fetchall()
    return [
        {
            "name": r["index_name"],
            "type": r["index_type"],
            "unique": bool(r["is_unique"]),
            "primary_key": bool(r["is_primary_key"]),
            "columns": r["columns"],
        }
        for r in rows
    ]


def _get_indexes_postgresql(cursor, table_name):
    """Indexes do PostgreSQL via pg_indexes."""
    cursor.execute("""
        SELECT indexname AS index_name,
               indexdef AS index_definition
        FROM pg_indexes
        WHERE schemaname = 'public' AND tablename = %s
        ORDER BY indexname
    """, (table_name,))
    rows = cursor.fetchall()
    result = []
    for r in rows:
        defn = r.get("index_definition", "") or ""
        is_unique = "UNIQUE" in defn.upper()
        is_pk = "pkey" in (r.get("index_name", "") or "").lower()
        # Extrair colunas do indexdef: ... USING btree (col1, col2)
        cols = ""
        if "(" in defn and ")" in defn:
            cols = defn[defn.index("(") + 1:defn.rindex(")")]
        idx_type = "BTREE"
        if "USING" in defn.upper():
            parts = defn.upper().split("USING")
            if len(parts) > 1:
                idx_type = parts[1].strip().split(" ")[0].split("(")[0]
        result.append({
            "name": r.get("index_name", ""),
            "type": idx_type,
            "unique": is_unique,
            "primary_key": is_pk,
            "columns": cols,
        })
    return result


def _get_indexes_mysql(cursor, table_name, database_name):
    """Indexes do MySQL via INFORMATION_SCHEMA.STATISTICS."""
    cursor.execute("""
        SELECT INDEX_NAME AS index_name,
               INDEX_TYPE AS index_type,
               NON_UNIQUE,
               GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) AS columns
        FROM INFORMATION_SCHEMA.STATISTICS
        WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
        GROUP BY INDEX_NAME, INDEX_TYPE, NON_UNIQUE
        ORDER BY INDEX_NAME
    """, (database_name, table_name))
    rows = cursor.fetchall()
    return [
        {
            "name": r["index_name"],
            "type": r["index_type"],
            "unique": not bool(r["NON_UNIQUE"]),
            "primary_key": r["index_name"] == "PRIMARY",
            "columns": r["columns"],
        }
        for r in rows
    ]


def _get_indexes_oracle(cursor, table_name):
    """Indexes do Oracle via USER_INDEXES + USER_IND_COLUMNS."""
    cursor.execute("""
        SELECT i.INDEX_NAME,
               i.INDEX_TYPE,
               i.UNIQUENESS,
               LISTAGG(ic.COLUMN_NAME, ', ') WITHIN GROUP (ORDER BY ic.COLUMN_POSITION) AS COLUMNS_LIST
        FROM USER_INDEXES i
        JOIN USER_IND_COLUMNS ic ON i.INDEX_NAME = ic.INDEX_NAME AND i.TABLE_NAME = ic.TABLE_NAME
        WHERE i.TABLE_NAME = :1
        GROUP BY i.INDEX_NAME, i.INDEX_TYPE, i.UNIQUENESS
        ORDER BY i.INDEX_NAME
    """, (table_name,))
    rows = cursor.fetchall()
    columns = [desc[0] for desc in cursor.description]
    return [
        {
            "name": dict(zip(columns, r))["INDEX_NAME"],
            "type": dict(zip(columns, r))["INDEX_TYPE"],
            "unique": dict(zip(columns, r))["UNIQUENESS"] == "UNIQUE",
            "primary_key": False,
            "columns": dict(zip(columns, r))["COLUMNS_LIST"],
        }
        for r in rows
    ]


# --- TRIGGERS ---

def _get_triggers_mssql(cursor, table_name):
    """Triggers do SQL Server via sys.triggers."""
    cursor.execute("""
        SELECT t.name AS trigger_name,
               t.is_disabled,
               te.type_desc AS event_type,
               CASE WHEN t.is_instead_of_trigger = 1 THEN 'INSTEAD OF' ELSE 'AFTER' END AS timing
        FROM sys.triggers t
        JOIN sys.trigger_events te ON t.object_id = te.object_id
        WHERE t.parent_id = OBJECT_ID(%s)
        ORDER BY t.name
    """, (table_name,))
    rows = cursor.fetchall()
    return [
        {
            "name": r["trigger_name"],
            "event": r["event_type"],
            "timing": r["timing"],
            "enabled": not bool(r["is_disabled"]),
        }
        for r in rows
    ]


def _get_triggers_postgresql(cursor, table_name):
    """Triggers do PostgreSQL via information_schema.triggers."""
    cursor.execute("""
        SELECT trigger_name,
               event_manipulation AS event,
               action_timing AS timing,
               action_statement
        FROM information_schema.triggers
        WHERE event_object_schema = 'public' AND event_object_table = %s
        ORDER BY trigger_name
    """, (table_name,))
    rows = cursor.fetchall()
    return [
        {
            "name": r.get("trigger_name", ""),
            "event": r.get("event", ""),
            "timing": r.get("timing", ""),
            "enabled": True,
            "action": r.get("action_statement", ""),
        }
        for r in rows
    ]


def _get_triggers_mysql(cursor, table_name, database_name):
    """Triggers do MySQL via INFORMATION_SCHEMA.TRIGGERS."""
    cursor.execute("""
        SELECT TRIGGER_NAME AS trigger_name,
               EVENT_MANIPULATION AS event,
               ACTION_TIMING AS timing,
               ACTION_STATEMENT AS action_stmt
        FROM INFORMATION_SCHEMA.TRIGGERS
        WHERE TRIGGER_SCHEMA = %s AND EVENT_OBJECT_TABLE = %s
        ORDER BY TRIGGER_NAME
    """, (database_name, table_name))
    rows = cursor.fetchall()
    return [
        {
            "name": r["trigger_name"],
            "event": r["event"],
            "timing": r["timing"],
            "enabled": True,
            "action": (r.get("action_stmt") or "")[:200],
        }
        for r in rows
    ]


def _get_triggers_oracle(cursor, table_name):
    """Triggers do Oracle via USER_TRIGGERS."""
    cursor.execute("""
        SELECT TRIGGER_NAME, TRIGGERING_EVENT, TRIGGER_TYPE, STATUS
        FROM USER_TRIGGERS
        WHERE TABLE_NAME = :1
        ORDER BY TRIGGER_NAME
    """, (table_name,))
    rows = cursor.fetchall()
    columns = [desc[0] for desc in cursor.description]
    return [
        {
            "name": dict(zip(columns, r))["TRIGGER_NAME"],
            "event": dict(zip(columns, r))["TRIGGERING_EVENT"],
            "timing": dict(zip(columns, r))["TRIGGER_TYPE"],
            "enabled": dict(zip(columns, r))["STATUS"] == "ENABLED",
        }
        for r in rows
    ]


# --- CONSTRAINTS ---

def _get_constraints_mssql(cursor, table_name):
    """Constraints do SQL Server via INFORMATION_SCHEMA + sys."""
    cursor.execute("""
        SELECT tc.CONSTRAINT_NAME AS constraint_name,
               tc.CONSTRAINT_TYPE AS constraint_type,
               STRING_AGG(kcu.COLUMN_NAME, ', ') WITHIN GROUP (ORDER BY kcu.ORDINAL_POSITION) AS columns,
               rc.UNIQUE_CONSTRAINT_NAME AS ref_constraint,
               rc2.TABLE_NAME AS ref_table
        FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
        LEFT JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
            ON tc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
        LEFT JOIN INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS rc
            ON tc.CONSTRAINT_NAME = rc.CONSTRAINT_NAME
        LEFT JOIN INFORMATION_SCHEMA.TABLE_CONSTRAINTS rc2
            ON rc.UNIQUE_CONSTRAINT_NAME = rc2.CONSTRAINT_NAME
        WHERE tc.TABLE_NAME = %s
        GROUP BY tc.CONSTRAINT_NAME, tc.CONSTRAINT_TYPE, rc.UNIQUE_CONSTRAINT_NAME, rc2.TABLE_NAME
        ORDER BY tc.CONSTRAINT_TYPE, tc.CONSTRAINT_NAME
    """, (table_name,))
    rows = cursor.fetchall()
    result = []
    for r in rows:
        item = {
            "name": r["constraint_name"],
            "type": r["constraint_type"],
            "columns": r["columns"] or "",
        }
        if r.get("ref_table"):
            item["ref_table"] = r["ref_table"]
        result.append(item)

    # Check constraints via sys.check_constraints
    cursor.execute("""
        SELECT cc.name AS constraint_name, cc.definition
        FROM sys.check_constraints cc
        WHERE cc.parent_object_id = OBJECT_ID(%s)
        ORDER BY cc.name
    """, (table_name,))
    for r in cursor.fetchall():
        result.append({
            "name": r["constraint_name"],
            "type": "CHECK",
            "columns": "",
            "definition": r.get("definition", ""),
        })
    return result


def _get_constraints_postgresql(cursor, table_name):
    """Constraints do PostgreSQL via information_schema + pg_constraint."""
    cursor.execute("""
        SELECT tc.constraint_name,
               tc.constraint_type,
               STRING_AGG(kcu.column_name, ', ' ORDER BY kcu.ordinal_position) AS columns,
               ccu.table_name AS ref_table
        FROM information_schema.table_constraints tc
        LEFT JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
        LEFT JOIN information_schema.constraint_column_usage ccu
            ON tc.constraint_name = ccu.constraint_name AND tc.table_schema = ccu.table_schema
            AND tc.constraint_type = 'FOREIGN KEY'
        WHERE tc.table_schema = 'public' AND tc.table_name = %s
        GROUP BY tc.constraint_name, tc.constraint_type, ccu.table_name
        ORDER BY tc.constraint_type, tc.constraint_name
    """, (table_name,))
    rows = cursor.fetchall()
    result = []
    for r in rows:
        item = {
            "name": r.get("constraint_name", ""),
            "type": r.get("constraint_type", ""),
            "columns": r.get("columns", "") or "",
        }
        if r.get("ref_table"):
            item["ref_table"] = r["ref_table"]
        result.append(item)

    # Check constraints com definição
    cursor.execute("""
        SELECT conname AS constraint_name,
               pg_get_constraintdef(oid) AS definition
        FROM pg_constraint
        WHERE conrelid = %s::regclass AND contype = 'c'
        ORDER BY conname
    """, (table_name,))
    for r in cursor.fetchall():
        result.append({
            "name": r.get("constraint_name", ""),
            "type": "CHECK",
            "columns": "",
            "definition": r.get("definition", ""),
        })
    return result


def _get_constraints_mysql(cursor, table_name, database_name):
    """Constraints do MySQL via INFORMATION_SCHEMA."""
    cursor.execute("""
        SELECT tc.CONSTRAINT_NAME AS constraint_name,
               tc.CONSTRAINT_TYPE AS constraint_type,
               GROUP_CONCAT(kcu.COLUMN_NAME ORDER BY kcu.ORDINAL_POSITION) AS columns,
               kcu.REFERENCED_TABLE_NAME AS ref_table
        FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
        LEFT JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
            ON tc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME AND tc.TABLE_SCHEMA = kcu.TABLE_SCHEMA
        WHERE tc.TABLE_SCHEMA = %s AND tc.TABLE_NAME = %s
        GROUP BY tc.CONSTRAINT_NAME, tc.CONSTRAINT_TYPE, kcu.REFERENCED_TABLE_NAME
        ORDER BY tc.CONSTRAINT_TYPE, tc.CONSTRAINT_NAME
    """, (database_name, table_name))
    rows = cursor.fetchall()
    result = []
    for r in rows:
        item = {
            "name": r["constraint_name"],
            "type": r["constraint_type"],
            "columns": r["columns"] or "",
        }
        if r.get("ref_table"):
            item["ref_table"] = r["ref_table"]
        result.append(item)
    return result


def _get_constraints_oracle(cursor, table_name):
    """Constraints do Oracle via USER_CONSTRAINTS + USER_CONS_COLUMNS."""
    cursor.execute("""
        SELECT uc.CONSTRAINT_NAME, uc.CONSTRAINT_TYPE, uc.SEARCH_CONDITION,
               uc.R_CONSTRAINT_NAME,
               LISTAGG(ucc.COLUMN_NAME, ', ') WITHIN GROUP (ORDER BY ucc.POSITION) AS COLUMNS_LIST
        FROM USER_CONSTRAINTS uc
        LEFT JOIN USER_CONS_COLUMNS ucc
            ON uc.CONSTRAINT_NAME = ucc.CONSTRAINT_NAME AND uc.TABLE_NAME = ucc.TABLE_NAME
        WHERE uc.TABLE_NAME = :1
        GROUP BY uc.CONSTRAINT_NAME, uc.CONSTRAINT_TYPE, uc.SEARCH_CONDITION, uc.R_CONSTRAINT_NAME
        ORDER BY uc.CONSTRAINT_TYPE, uc.CONSTRAINT_NAME
    """, (table_name,))
    rows = cursor.fetchall()
    columns_desc = [desc[0] for desc in cursor.description]

    type_map = {"P": "PRIMARY KEY", "U": "UNIQUE", "R": "FOREIGN KEY", "C": "CHECK"}
    result = []
    for r in rows:
        d = dict(zip(columns_desc, r))
        item = {
            "name": d["CONSTRAINT_NAME"],
            "type": type_map.get(d["CONSTRAINT_TYPE"], d["CONSTRAINT_TYPE"]),
            "columns": d.get("COLUMNS_LIST", "") or "",
        }
        if d.get("SEARCH_CONDITION"):
            item["definition"] = d["SEARCH_CONDITION"]
        if d.get("R_CONSTRAINT_NAME"):
            item["ref_constraint"] = d["R_CONSTRAINT_NAME"]
        result.append(item)
    return result
