"""
Servico de Comparacao de Dicionario e Validacao de Integridade Protheus.

- Comparar Dicionario: compara 13 tabelas de metadados entre dois bancos
- Validar Integridade: verifica consistencia SX2/SX3/SIX vs schema fisico + TOP_FIELD
"""

import logging
import re
import time
from datetime import datetime
from app.database import get_db, release_db_connection
from app.services.database_browser import get_connection_config, _get_external_connection

logger = logging.getLogger(__name__)

# 13 tabelas de metadados Protheus para comparacao
METADATA_TABLES = [
    "SIX", "SX1", "SX2", "SX3", "SX5", "SX6", "SX7",
    "SX9", "SXA", "SXB", "XXA", "XAM", "XAL",
]

# Chaves primarias logicas por tabela de metadado
TABLE_KEYS = {
    "SIX": ["INDICE", "ORDEM"],
    "SX1": ["X1_GRUPO", "X1_ORDEM"],
    "SX2": ["X2_CHAVE"],
    "SX3": ["X3_ARQUIVO", "X3_CAMPO"],
    "SX5": ["X5_FILIAL", "X5_TABELA", "X5_CHAVE"],
    "SX6": ["X6_VAR", "X6_FIL"],
    "SX7": ["X7_CAMPO", "X7_SEQUENC", "X7_REGRA"],
    "SX9": ["X9_DOM", "X9_IDENT", "X9_CDOM"],
    "SXA": ["XA_ALIAS", "XA_ORDEM"],
    "SXB": ["XB_ALIAS", "XB_TIPO"],
    "XXA": ["XXA_PERG", "XXA_ORDEM"],
    "XAM": ["XAM_ALIAS", "XAM_ORDEM"],
    "XAL": ["XAL_ALIAS", "XAL_CAMPO"],
}

# Colunas de controle interno do Protheus
# R_E_C_N_O_, R_E_C_D_E_L_, S_T_A_M_P_, I_N_S_D_T_ sempre ignorados
# D_E_L_E_T_ tratado separadamente (pode ser incluido na comparacao)
IGNORE_COLUMNS = {"R_E_C_N_O_", "R_E_C_D_E_L_", "D_E_L_E_T_", "S_T_A_M_P_", "I_N_S_D_T_"}
ALWAYS_IGNORE_COLUMNS = {"R_E_C_N_O_", "R_E_C_D_E_L_", "S_T_A_M_P_", "I_N_S_D_T_"}

# Coluna que identifica o alias/tabela Protheus em cada tabela de metadado
# Usada pelo filtro de aliases na comparacao
ALIAS_COLUMN = {
    "SIX": "INDICE",
    "SX2": "X2_CHAVE",
    "SX3": "X3_ARQUIVO",
    "SXA": "XA_ALIAS",
    "SXB": "XB_ALIAS",
    "XAM": "XAM_ALIAS",
    "XAL": "XAL_ALIAS",
}


def _make_table_name(prefix, company_code):
    """Monta nome fisico da tabela de metadado: {PREFIX}{M0_CODIGO}0."""
    return f"{prefix}{company_code}0"


def _normalize_row(row):
    """Normaliza valores de uma row para comparacao (strip strings, None→'', keys uppercase)."""
    clean = {}
    for k, v in row.items():
        key = k.strip().upper() if isinstance(k, str) else k
        if key in ALWAYS_IGNORE_COLUMNS:
            continue
        if isinstance(v, str):
            clean[key] = v.strip()
        elif v is None:
            clean[key] = ""
        elif isinstance(v, bytes):
            clean[key] = "<BLOB>"
        elif isinstance(v, datetime):
            clean[key] = v.isoformat()
        else:
            clean[key] = str(v) if not isinstance(v, (int, float, bool)) else v
    return clean


def _make_key(row, key_columns):
    """Gera chave composta a partir das colunas-chave."""
    parts = []
    for col in key_columns:
        val = row.get(col, "")
        if isinstance(val, str):
            val = val.strip()
        parts.append(str(val))
    return "|".join(parts)


def _fetch_all_rows(cursor, driver, table_name):
    """Busca todos os registros de uma tabela de metadados."""
    if driver == "mssql":
        query = f"SELECT * FROM [{table_name}]"
    elif driver == "oracle":
        query = f"SELECT * FROM {table_name}"
    elif driver == "postgresql":
        query = f"SELECT * FROM {table_name.lower()}"
    else:
        query = f'SELECT * FROM "{table_name}"'

    try:
        cursor.execute(query)
        if driver == "oracle":
            columns = [desc[0] for desc in cursor.description]
            raw_rows = cursor.fetchall()
            return [dict(zip(columns, row)) for row in raw_rows]
        else:
            return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        logger.warning(f"Erro ao buscar {table_name}: {e}")
        return None


# =========================================================
# EMPRESAS (SYS_COMPANY)
# =========================================================


def get_companies(connection_id):
    """Busca empresas disponiveis na tabela SYS_COMPANY."""
    config = get_connection_config(connection_id)
    if not config:
        raise ValueError("Conexao nao encontrada")

    ext_conn = _get_external_connection(config)
    cursor = ext_conn.cursor()
    try:
        if config["driver"] == "postgresql":
            cursor.execute("SELECT m0_codigo, m0_nome FROM sys_company ORDER BY m0_codigo")
        else:
            cursor.execute("SELECT M0_CODIGO, M0_NOME FROM SYS_COMPANY ORDER BY M0_CODIGO")

        rows = cursor.fetchall()
        if config["driver"] == "oracle":
            columns = [desc[0] for desc in cursor.description]
            rows = [dict(zip(columns, row)) for row in rows]
        else:
            rows = [dict(row) for row in rows]

        companies = []
        for row in rows:
            code = row.get("M0_CODIGO", row.get("m0_codigo", ""))
            name = row.get("M0_NOME", row.get("m0_nome", ""))
            if isinstance(code, str):
                code = code.strip()
            if isinstance(name, str):
                name = name.strip()
            if code:
                companies.append({"code": code, "name": name})

        return companies
    finally:
        ext_conn.close()


# =========================================================
# COMPARAR DICIONARIO
# =========================================================


def compare_dictionaries(conn_id_a, conn_id_b, company_code, tables=None, alias_filter=None, include_deleted=False):
    """
    Compara metadados entre dois bancos para uma empresa.

    Args:
        conn_id_a: ID da conexao A (origem/referencia)
        conn_id_b: ID da conexao B (destino/comparacao)
        company_code: codigo da empresa (M0_CODIGO)
        tables: lista de prefixos (ex: ['SX2','SX3']), None = todas 13
        alias_filter: aliases Protheus separados por virgula (ex: 'SA1,SA2,SB1')
                      filtra registros nas tabelas de metadado pela coluna de alias
        include_deleted: se True, inclui registros com D_E_L_E_T_='*'

    Returns:
        dict com resultado por tabela:
        {
            "SX2990": {
                "total_a": 245, "total_b": 243,
                "only_a": [...], "only_b": [...],
                "different": [{key, fields: [{field, val_a, val_b}]}]
            }
        }
    """
    if tables is None:
        tables = METADATA_TABLES
    else:
        tables = [t.upper() for t in tables if t.upper() in METADATA_TABLES]
        if not tables:
            raise ValueError("Nenhuma tabela valida selecionada")

    # Parse alias_filter: aliases separados por virgula (ex: "SA1, SA2, SB1")
    alias_set = set()
    if alias_filter:
        alias_set = {a.strip().upper() for a in str(alias_filter).split(",") if a.strip()}

    config_a = get_connection_config(conn_id_a)
    config_b = get_connection_config(conn_id_b)
    if not config_a:
        raise ValueError("Conexao A nao encontrada")
    if not config_b:
        raise ValueError("Conexao B nao encontrada")

    conn_a = _get_external_connection(config_a)
    conn_b = _get_external_connection(config_b)
    cursor_a = conn_a.cursor()
    cursor_b = conn_b.cursor()

    results = {}

    try:
        for prefix in tables:
            table_name = _make_table_name(prefix, company_code)
            key_columns = TABLE_KEYS.get(prefix, [])

            rows_a = _fetch_all_rows(cursor_a, config_a["driver"], table_name)
            rows_b = _fetch_all_rows(cursor_b, config_b["driver"], table_name)

            if rows_a is None and rows_b is None:
                results[table_name] = {
                    "prefix": prefix,
                    "total_a": 0, "total_b": 0,
                    "error": "Tabela nao encontrada em ambos os bancos",
                    "only_a": [], "only_b": [], "different": [],
                }
                continue

            if rows_a is None:
                rows_a = []
            if rows_b is None:
                rows_b = []

            # Normalizar rows
            norm_a = [_normalize_row(r) for r in rows_a]
            norm_b = [_normalize_row(r) for r in rows_b]

            # Filtrar registros deletados (D_E_L_E_T_ = '*') se nao incluir
            if not include_deleted:
                norm_a = [r for r in norm_a if str(r.get("D_E_L_E_T_", "")).strip() != "*"]
                norm_b = [r for r in norm_b if str(r.get("D_E_L_E_T_", "")).strip() != "*"]

            # Filtrar por alias se especificado (ex: apenas SA1, SA2)
            if alias_set:
                alias_col = ALIAS_COLUMN.get(prefix)
                if alias_col:
                    norm_a = [r for r in norm_a if str(r.get(alias_col, "")).strip().upper() in alias_set]
                    norm_b = [r for r in norm_b if str(r.get(alias_col, "")).strip().upper() in alias_set]

            # Se nao temos key_columns definidas, tentar inferir das colunas
            if not key_columns and norm_a:
                # Fallback: usar todas as colunas como chave (sem comparacao de diffs)
                key_columns = list(norm_a[0].keys())[:3]

            # Indexar por chave
            dict_a = {}
            for row in norm_a:
                key = _make_key(row, key_columns)
                dict_a[key] = row

            dict_b = {}
            for row in norm_b:
                key = _make_key(row, key_columns)
                dict_b[key] = row

            keys_a = set(dict_a.keys())
            keys_b = set(dict_b.keys())

            only_a = []
            for k in sorted(keys_a - keys_b):
                only_a.append({"key": k, "values": dict_a[k]})

            only_b = []
            for k in sorted(keys_b - keys_a):
                only_b.append({"key": k, "values": dict_b[k]})

            different = []
            # Quando include_deleted, comparar D_E_L_E_T_ tambem (mostrar dif. entre * e vazio)
            skip_cols = (IGNORE_COLUMNS - {"D_E_L_E_T_"}) if include_deleted else IGNORE_COLUMNS
            for k in sorted(keys_a & keys_b):
                row_a = dict_a[k]
                row_b = dict_b[k]
                diffs = []
                all_fields = set(row_a.keys()) | set(row_b.keys())
                for field in sorted(all_fields):
                    if field in skip_cols:
                        continue
                    va = row_a.get(field, "")
                    vb = row_b.get(field, "")
                    if str(va) != str(vb):
                        diffs.append({"field": field, "val_a": va, "val_b": vb})
                if diffs:
                    different.append({"key": k, "fields": diffs})

            results[table_name] = {
                "prefix": prefix,
                "total_a": len(norm_a),
                "total_b": len(norm_b),
                "only_a": only_a,
                "only_b": only_b,
                "different": different,
            }

        return results

    finally:
        conn_a.close()
        conn_b.close()


# =========================================================
# VALIDAR INTEGRIDADE
# =========================================================


def _row_get(row_dict, field_name, default=""):
    """Extrai campo case-insensitive de uma row (uppercase, lowercase, original)."""
    return row_dict.get(field_name, row_dict.get(field_name.lower(), row_dict.get(field_name.upper(), default)))


def _get_physical_tables(cursor, driver):
    """Lista tabelas fisicas do banco via INFORMATION_SCHEMA."""
    if driver == "mssql":
        cursor.execute("""
            SELECT TABLE_NAME
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_TYPE = 'BASE TABLE'
        """)
        rows = cursor.fetchall()
        return {str(_row_get(dict(r), "TABLE_NAME")).upper() for r in rows}

    elif driver == "postgresql":
        cursor.execute("""
            SELECT tablename
            FROM pg_tables
            WHERE schemaname = 'public'
        """)
        rows = cursor.fetchall()
        return {str(_row_get(dict(r), "tablename", _row_get(dict(r), "TABLE_NAME"))).upper() for r in rows}

    elif driver == "mysql":
        cursor.execute("""
            SELECT TABLE_NAME
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_TYPE = 'BASE TABLE'
        """)
        rows = cursor.fetchall()
        return {str(_row_get(dict(r), "TABLE_NAME")).upper() for r in rows}

    elif driver == "oracle":
        cursor.execute("SELECT TABLE_NAME FROM USER_TABLES")
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        return {dict(zip(columns, r))["TABLE_NAME"].upper() for r in rows}

    return set()


def _get_physical_columns(cursor, driver, table_name):
    """Lista colunas fisicas de uma tabela especifica."""
    if driver == "mssql":
        cursor.execute("""
            SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH,
                   NUMERIC_PRECISION, NUMERIC_SCALE
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = %s
        """, (table_name,))
        rows = cursor.fetchall()
        return {str(_row_get(dict(r), "COLUMN_NAME")).upper(): dict(r) for r in rows}

    elif driver == "postgresql":
        cursor.execute("""
            SELECT column_name, data_type, character_maximum_length,
                   numeric_precision, numeric_scale
            FROM information_schema.columns
            WHERE table_name = %s AND table_schema = 'public'
        """, (table_name.lower(),))
        rows = cursor.fetchall()
        return {str(_row_get(dict(r), "column_name")).upper(): dict(r) for r in rows}

    elif driver == "mysql":
        cursor.execute("""
            SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH,
                   NUMERIC_PRECISION, NUMERIC_SCALE
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = %s AND TABLE_SCHEMA = DATABASE()
        """, (table_name,))
        rows = cursor.fetchall()
        return {str(_row_get(dict(r), "COLUMN_NAME")).upper(): dict(r) for r in rows}

    elif driver == "oracle":
        cursor.execute("""
            SELECT COLUMN_NAME, DATA_TYPE, DATA_LENGTH, DATA_PRECISION, DATA_SCALE
            FROM USER_TAB_COLUMNS
            WHERE TABLE_NAME = :1
        """, (table_name.upper(),))
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        return {dict(zip(columns, r))["COLUMN_NAME"].upper(): dict(zip(columns, r)) for r in rows}

    return {}


def _get_all_physical_columns_bulk(cursor, driver):
    """Carrega colunas de TODAS as tabelas em 1 query. Retorna {TABLE_NAME: {COL_NAME: info}}."""
    all_cols = {}

    if driver == "mssql":
        cursor.execute("""
            SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH,
                   NUMERIC_PRECISION, NUMERIC_SCALE
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = 'dbo'
        """)
    elif driver == "postgresql":
        cursor.execute("""
            SELECT table_name, column_name, data_type, character_maximum_length,
                   numeric_precision, numeric_scale
            FROM information_schema.columns
            WHERE table_schema = 'public'
        """)
    elif driver == "mysql":
        cursor.execute("""
            SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH,
                   NUMERIC_PRECISION, NUMERIC_SCALE
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
        """)
    elif driver == "oracle":
        cursor.execute("""
            SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE, DATA_LENGTH, DATA_PRECISION, DATA_SCALE
            FROM USER_TAB_COLUMNS
        """)

    if driver == "oracle":
        columns = [desc[0] for desc in cursor.description]
        raw_rows = [dict(zip(columns, r)) for r in cursor.fetchall()]
    else:
        raw_rows = [dict(r) for r in cursor.fetchall()]

    for rd in raw_rows:
        tname = str(_row_get(rd, "TABLE_NAME", _row_get(rd, "table_name"))).upper()
        cname = str(_row_get(rd, "COLUMN_NAME", _row_get(rd, "column_name"))).upper()
        if tname not in all_cols:
            all_cols[tname] = {}
        all_cols[tname][cname] = rd

    return all_cols


def _get_physical_indexes(cursor, driver):
    """Lista todos os indices fisicos do banco."""
    indexes = {}  # {TABLE_NAME: {INDEX_NAME: [COLUMNS]}}

    if driver == "mssql":
        cursor.execute("""
            SELECT t.name AS TABLE_NAME,
                   i.name AS INDEX_NAME,
                   c.name AS COLUMN_NAME,
                   ic.key_ordinal AS KEY_ORDINAL
            FROM sys.indexes i
            JOIN sys.tables t ON i.object_id = t.object_id
            JOIN sys.index_columns ic ON i.object_id = ic.object_id AND i.index_id = ic.index_id
            JOIN sys.columns c ON ic.object_id = c.object_id AND ic.column_id = c.column_id
            WHERE i.type > 0 AND i.name IS NOT NULL
            ORDER BY t.name, i.name, ic.key_ordinal
        """)
        for row in cursor.fetchall():
            tname = row["TABLE_NAME"].upper()
            iname = row["INDEX_NAME"].upper()
            if tname not in indexes:
                indexes[tname] = {}
            if iname not in indexes[tname]:
                indexes[tname][iname] = []
            indexes[tname][iname].append(row["COLUMN_NAME"].upper())

    elif driver == "postgresql":
        cursor.execute("""
            SELECT t.relname AS table_name,
                   i.relname AS index_name,
                   a.attname AS column_name
            FROM pg_index ix
            JOIN pg_class t ON t.oid = ix.indrelid
            JOIN pg_class i ON i.oid = ix.indexrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(ix.indkey)
            WHERE n.nspname = 'public'
            ORDER BY t.relname, i.relname, array_position(ix.indkey, a.attnum)
        """)
        for row in cursor.fetchall():
            rd = dict(row)
            tname = (rd.get("table_name") or "").upper()
            iname = (rd.get("index_name") or "").upper()
            cname = (rd.get("column_name") or "").upper()
            if tname not in indexes:
                indexes[tname] = {}
            if iname not in indexes[tname]:
                indexes[tname][iname] = []
            indexes[tname][iname].append(cname)

    elif driver == "mysql":
        cursor.execute("""
            SELECT TABLE_NAME, INDEX_NAME, COLUMN_NAME, SEQ_IN_INDEX
            FROM INFORMATION_SCHEMA.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE()
            ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX
        """)
        for row in cursor.fetchall():
            rd = dict(row)
            tname = rd["TABLE_NAME"].upper()
            iname = rd["INDEX_NAME"].upper()
            cname = rd["COLUMN_NAME"].upper()
            if tname not in indexes:
                indexes[tname] = {}
            if iname not in indexes[tname]:
                indexes[tname][iname] = []
            indexes[tname][iname].append(cname)

    elif driver == "oracle":
        cursor.execute("""
            SELECT TABLE_NAME, INDEX_NAME, COLUMN_NAME, COLUMN_POSITION
            FROM USER_IND_COLUMNS
            ORDER BY TABLE_NAME, INDEX_NAME, COLUMN_POSITION
        """)
        columns = [desc[0] for desc in cursor.description]
        for raw_row in cursor.fetchall():
            row = dict(zip(columns, raw_row))
            tname = row["TABLE_NAME"].upper()
            iname = row["INDEX_NAME"].upper()
            cname = row["COLUMN_NAME"].upper()
            if tname not in indexes:
                indexes[tname] = {}
            if iname not in indexes[tname]:
                indexes[tname][iname] = []
            indexes[tname][iname].append(cname)

    return indexes


def _get_topfield_data(cursor, driver):
    """Busca todos os registros da tabela TOP_FIELD (sem sufixo de empresa)."""
    if driver == "postgresql":
        query = "SELECT field_table, field_name, field_type, field_prec, field_dec FROM top_field"
    elif driver == "oracle":
        query = "SELECT FIELD_TABLE, FIELD_NAME, FIELD_TYPE, FIELD_PREC, FIELD_DEC FROM TOP_FIELD"
    else:
        query = "SELECT FIELD_TABLE, FIELD_NAME, FIELD_TYPE, FIELD_PREC, FIELD_DEC FROM TOP_FIELD"

    try:
        cursor.execute(query)
        if driver == "oracle":
            columns = [desc[0] for desc in cursor.description]
            raw_rows = cursor.fetchall()
            rows = [dict(zip(columns, r)) for r in raw_rows]
        else:
            rows = [dict(r) for r in cursor.fetchall()]

        # Indexar por (table, field) — normalizar chaves e remover prefixo dbo.
        topfield = {}
        for row in rows:
            ft = row.get("FIELD_TABLE", row.get("field_table", ""))
            fn = row.get("FIELD_NAME", row.get("field_name", ""))
            if isinstance(ft, str):
                ft = ft.strip()
                # Remover prefixo dbo. se existir
                if ft.lower().startswith("dbo."):
                    ft = ft[4:]
            if isinstance(fn, str):
                fn = fn.strip()

            ftype = row.get("FIELD_TYPE", row.get("field_type", ""))
            fprec = row.get("FIELD_PREC", row.get("field_prec", ""))
            fdec = row.get("FIELD_DEC", row.get("field_dec", ""))

            if isinstance(ftype, str):
                ftype = ftype.strip()
            if isinstance(fprec, str):
                fprec = fprec.strip()
            if isinstance(fdec, str):
                fdec = fdec.strip()

            topfield[(ft.upper(), fn.upper())] = {
                "type": ftype,
                "prec": str(fprec) if fprec else "",
                "dec": str(fdec) if fdec else "",
                "raw_table": row.get("FIELD_TABLE", row.get("field_table", "")).strip(),
                "raw_name": row.get("FIELD_NAME", row.get("field_name", "")).strip(),
            }

        return topfield
    except Exception as e:
        logger.warning(f"Erro ao buscar TOP_FIELD: {e}")
        return None


def validate_integrity(connection_id, company_code, layers=None):
    """
    Valida integridade entre metadados Protheus e schema fisico.

    Camadas originais (1-4) + novas (F1-F5):
    1. sx2_schema — tabelas do SX2 que nao existem como tabela fisica
    2. sx3_schema — campos do SX3 que nao existem na tabela fisica
    3. sx3_topfield — campos D/N/M sem registro ou com tipo divergente
    4. six_indexes — indices do SIX sem indice fisico correspondente
    F1: schema_sx3, sx3_field_size, virtual_in_schema
    F2: sx2_unique_fields, sx2_unique_virtual, sx2_no_sx3, sx3_no_sx2, sx2_no_six, six_no_sx2
    F3: six_fields_sx3, six_virtual_memo
    F4: duplicates, sx2_sharing
    F5: sx3_ref_sxg, sx3_ref_sxa, sx3_ref_sxb

    Args:
        layers: lista de camadas a validar. None = todas.

    Returns:
        dict com resultado por camada
    """
    ALL_LAYERS = [
        "sx2_schema", "sx3_schema", "sx3_topfield", "six_indexes",
        "schema_sx3", "sx3_field_size", "virtual_in_schema",
        "sx2_unique_fields", "sx2_unique_virtual",
        "sx2_no_sx3", "sx3_no_sx2", "sx2_no_six", "six_no_sx2",
        "six_fields_sx3", "six_virtual_memo",
        "duplicates", "sx2_sharing",
        "sx3_ref_sxg", "sx3_ref_sxa", "sx3_ref_sxb",
    ]
    if layers:
        layers = [l for l in layers if l in ALL_LAYERS]
    else:
        layers = ALL_LAYERS

    config = get_connection_config(connection_id)
    if not config:
        raise ValueError("Conexao nao encontrada")

    ext_conn = _get_external_connection(config)
    cursor = ext_conn.cursor()
    driver = config["driver"]

    try:
        # Nomes das tabelas de metadados para esta empresa
        sx2_table = _make_table_name("SX2", company_code)
        sx3_table = _make_table_name("SX3", company_code)
        six_table = _make_table_name("SIX", company_code)

        # ===== CARREGAMENTO BULK (1 query cada) =====
        # Tabelas fisicas existentes no banco
        physical_tables = _get_physical_tables(cursor, driver)

        # Colunas de TODAS as tabelas em 1 query (elimina N queries individuais)
        _needs_columns = {
            "sx3_schema", "schema_sx3", "sx3_field_size",
            "virtual_in_schema", "sx2_sharing",
        }
        all_columns = None
        if _needs_columns & set(layers):
            all_columns = _get_all_physical_columns_bulk(cursor, driver)

        # Indices fisicos (1 query)
        physical_indexes = None
        if "six_indexes" in layers:
            physical_indexes = _get_physical_indexes(cursor, driver)

        # TOP_FIELD (1 query)
        topfield = None
        if "sx3_topfield" in layers:
            topfield = _get_topfield_data(cursor, driver)

        # Dados de metadados compartilhados — carrega 1x, usa em todas as layers
        _needs_shared = {
            "sx2": {"sx2_schema", "schema_sx3", "sx3_field_size",
                    "virtual_in_schema",
                    "sx2_unique_fields", "sx2_unique_virtual",
                    "sx2_no_sx3", "sx2_no_six", "six_no_sx2",
                    "duplicates", "sx2_sharing"},
            "sx3": {"sx3_schema", "sx3_topfield",
                    "schema_sx3", "sx3_field_size", "virtual_in_schema",
                    "sx2_unique_fields", "sx2_unique_virtual",
                    "sx2_no_sx3", "sx3_no_sx2",
                    "six_fields_sx3", "six_virtual_memo",
                    "duplicates",
                    "sx3_ref_sxg", "sx3_ref_sxa", "sx3_ref_sxb"},
            "six": {"six_indexes",
                    "sx2_no_six", "six_no_sx2",
                    "six_fields_sx3", "six_virtual_memo",
                    "duplicates"},
        }
        sx2_rows = None
        sx3_rows = None
        six_rows = None
        if _needs_shared["sx2"] & set(layers):
            sx2_rows = _fetch_all_rows(cursor, driver, sx2_table)
        if _needs_shared["sx3"] & set(layers):
            sx3_rows = _fetch_all_rows(cursor, driver, sx3_table)
        if _needs_shared["six"] & set(layers):
            six_rows = _fetch_all_rows(cursor, driver, six_table)

        # Tabelas de referencia cruzada (F5) — carrega 1x se necessario
        sxg_rows = None
        sxa_rows = None
        sxb_rows = None
        sx5_rows = None
        if "sx3_ref_sxg" in layers:
            sxg_rows = _fetch_all_rows(cursor, driver, _make_table_name("SXG", company_code))
        if "sx3_ref_sxa" in layers:
            sxa_rows = _fetch_all_rows(cursor, driver, _make_table_name("SXA", company_code))
        if "sx3_ref_sxb" in layers:
            sxb_rows = _fetch_all_rows(cursor, driver, _make_table_name("SXB", company_code))
            sx5_rows = _fetch_all_rows(cursor, driver, _make_table_name("SX5", company_code))

        result = {}

        # ===== 1. SX2 vs Schema =====
        if "sx2_schema" in layers:
            result["sx2_schema"] = _validate_sx2_vs_schema(
                sx2_rows, company_code, physical_tables
            )

        # ===== 2. SX3 vs Schema =====
        if "sx3_schema" in layers:
            result["sx3_schema"] = _validate_sx3_vs_schema(
                sx3_rows, company_code, physical_tables, all_columns
            )

        # ===== 3. SX3 vs TOP_FIELD =====
        if "sx3_topfield" in layers:
            result["sx3_topfield"] = _validate_sx3_vs_topfield(
                sx3_rows, company_code, physical_tables, topfield
            )

        # ===== 4. SIX vs Indexes =====
        if "six_indexes" in layers:
            result["six_indexes"] = _validate_six_vs_indexes(
                six_rows, company_code, physical_tables, physical_indexes
            )

        # ===== F1: Schema vs SX3 (direcao inversa) =====
        if "schema_sx3" in layers:
            result["schema_sx3"] = _validate_schema_vs_sx3(
                sx2_rows, sx3_rows, company_code,
                physical_tables, all_columns
            )

        # ===== F1: Tamanhos de campo SX3 vs base =====
        if "sx3_field_size" in layers:
            result["sx3_field_size"] = _validate_sx3_field_sizes(
                sx3_rows, company_code, physical_tables, all_columns
            )

        # ===== F1: Campos virtuais na base =====
        if "virtual_in_schema" in layers:
            result["virtual_in_schema"] = _validate_virtual_in_schema(
                sx3_rows, company_code, physical_tables, all_columns
            )

        # ===== F2: Chave unica SX2 sem campo no SX3 =====
        if "sx2_unique_fields" in layers:
            result["sx2_unique_fields"] = _validate_sx2_unique_fields(
                sx2_rows, sx3_rows
            )

        # ===== F2: Chave unica SX2 com campo virtual =====
        if "sx2_unique_virtual" in layers:
            result["sx2_unique_virtual"] = _validate_sx2_unique_virtual(
                sx2_rows, sx3_rows
            )

        # ===== F2: SX2 sem SX3 =====
        if "sx2_no_sx3" in layers:
            result["sx2_no_sx3"] = _validate_sx2_no_sx3(sx2_rows, sx3_rows)

        # ===== F2: SX3 sem SX2 =====
        if "sx3_no_sx2" in layers:
            result["sx3_no_sx2"] = _validate_sx3_no_sx2(sx2_rows, sx3_rows)

        # ===== F2: SX2 sem SIX =====
        if "sx2_no_six" in layers:
            result["sx2_no_six"] = _validate_sx2_no_six(sx2_rows, six_rows)

        # ===== F2: SIX sem SX2 =====
        if "six_no_sx2" in layers:
            result["six_no_sx2"] = _validate_six_no_sx2(sx2_rows, six_rows)

        # ===== F3: Campos de indices sem SX3 =====
        if "six_fields_sx3" in layers:
            result["six_fields_sx3"] = _validate_six_fields_sx3(
                six_rows, sx3_rows
            )

        # ===== F3: Campos virtuais/memo nos indices =====
        if "six_virtual_memo" in layers:
            result["six_virtual_memo"] = _validate_six_virtual_memo(
                six_rows, sx3_rows
            )

        # ===== F4: Duplicados SX2/SX3/SIX =====
        if "duplicates" in layers:
            result["duplicates"] = _validate_duplicates(
                sx2_rows, sx3_rows, six_rows
            )

        # ===== F4: Compartilhamento SX2 =====
        if "sx2_sharing" in layers:
            result["sx2_sharing"] = _validate_sx2_sharing(
                cursor, driver, sx2_rows, company_code, physical_tables
            )

        # ===== F5: SX3 ref SXG =====
        if "sx3_ref_sxg" in layers:
            result["sx3_ref_sxg"] = _validate_sx3_ref_sxg(
                sx3_rows, sxg_rows, company_code
            )

        # ===== F5: SX3 ref SXA =====
        if "sx3_ref_sxa" in layers:
            result["sx3_ref_sxa"] = _validate_sx3_ref_sxa(
                sx3_rows, sxa_rows, company_code
            )

        # ===== F5: SX3 ref SXB =====
        if "sx3_ref_sxb" in layers:
            result["sx3_ref_sxb"] = _validate_sx3_ref_sxb(
                sx3_rows, sxb_rows, sx5_rows, company_code
            )

        return result

    finally:
        ext_conn.close()


def _validate_sx2_vs_schema(sx2_rows, company_code, physical_tables):
    """
    Verifica integridade das tabelas SX2 que existem fisicamente.
    Tabelas do SX2 que NAO existem no schema sao bypass (Protheus cria sob demanda).
    So reporta problemas de tabelas que JA existem fisicamente.
    """
    if sx2_rows is None:
        return {"ok": 0, "total": 0, "skipped": 0, "error": "SX2 nao encontrada"}

    # Montar mapa SX2: nome fisico → X2_CHAVE
    sx2_tables = {}
    for row in sx2_rows:
        x2_chave = row.get("X2_CHAVE", row.get("x2_chave", ""))
        if isinstance(x2_chave, str):
            x2_chave = x2_chave.strip()
        if x2_chave:
            physical_name = f"{x2_chave}{company_code}0".upper()
            sx2_tables[physical_name] = x2_chave

    # Separar: tabelas que existem fisicamente vs que nao existem (bypass)
    existing = {}
    skipped = 0
    for phys_name, x2_chave in sx2_tables.items():
        if phys_name in physical_tables:
            existing[phys_name] = x2_chave
        else:
            skipped += 1

    return {
        "ok": len(existing),
        "total": len(sx2_tables),
        "skipped": skipped,
        "existing_tables": list(existing.keys()),
    }


def _validate_sx3_vs_schema(sx3_rows, company_code, physical_tables, all_columns):
    """
    Verifica se campos do SX3 existem fisicamente nas tabelas.
    Bypass: tabelas que nao existem no schema sao ignoradas (Protheus cria sob demanda).
    """
    if sx3_rows is None:
        return {"ok": 0, "missing_column": [], "error": "SX3 nao encontrada"}

    # Agrupar campos por tabela (apenas campos reais, X3_CONTEXT != 'V')
    table_fields = {}
    virtual_skipped = 0
    for row in sx3_rows:
        x3_context = row.get("X3_CONTEXT", row.get("x3_context", ""))
        if isinstance(x3_context, str):
            x3_context = x3_context.strip().upper()
        # V = virtual (so ISAM/tela), R ou vazio = real (existe no banco)
        if x3_context == "V":
            virtual_skipped += 1
            continue

        x3_arquivo = row.get("X3_ARQUIVO", row.get("x3_arquivo", ""))
        x3_campo = row.get("X3_CAMPO", row.get("x3_campo", ""))
        if isinstance(x3_arquivo, str):
            x3_arquivo = x3_arquivo.strip()
        if isinstance(x3_campo, str):
            x3_campo = x3_campo.strip()
        if x3_arquivo and x3_campo:
            phys_table = f"{x3_arquivo}{company_code}0".upper()
            if phys_table not in table_fields:
                table_fields[phys_table] = []
            table_fields[phys_table].append(x3_campo.upper())

    ok = 0
    missing = []
    tables_checked = 0
    tables_skipped = 0

    for table_name, expected_columns in sorted(table_fields.items()):
        # Bypass: tabela nao existe fisicamente — pular (nao e erro)
        if table_name not in physical_tables:
            tables_skipped += 1
            continue

        physical_cols = all_columns.get(table_name, {}) if all_columns else {}
        tables_checked += 1
        for col in expected_columns:
            if col in physical_cols:
                ok += 1
            else:
                missing.append({"table": table_name, "column": col, "reason": "campo_ausente"})

    return {
        "ok": ok,
        "total": ok + len(missing),
        "tables_checked": tables_checked,
        "tables_skipped": tables_skipped,
        "virtual_skipped": virtual_skipped,
        "missing_column": missing,
    }


def _validate_sx3_vs_topfield(sx3_rows, company_code, physical_tables, topfield):
    """
    Verifica se campos D/N/M do SX3 tem registro correto no TOP_FIELD.
    Bypass: tabelas que nao existem no schema sao ignoradas.
    """
    if sx3_rows is None:
        return {"ok": 0, "missing": [], "type_mismatch": [], "error": "SX3 nao encontrada"}

    if topfield is None:
        return {"ok": 0, "missing": [], "type_mismatch": [], "error": "Tabela TOP_FIELD nao encontrada"}

    # Mapeamento SX3 X3_TIPO → TOP_FIELD type
    # D, N, M: obrigatorio ter TOP_FIELD
    # C: opcional — se existir no TOP_FIELD, deve ser type 'L' (campo logico/booleano)
    TYPE_MAP = {"D": "D", "N": "P", "M": "M"}

    ok = 0
    missing_list = []
    mismatch_list = []
    skipped = 0

    for row in sx3_rows:
        # Bypass campos virtuais (X3_CONTEXT = 'V') — nao existem no banco fisico
        x3_context = row.get("X3_CONTEXT", row.get("x3_context", ""))
        if isinstance(x3_context, str):
            x3_context = x3_context.strip().upper()
        # V = virtual (so ISAM/tela), R ou vazio = real (existe no banco)
        if x3_context == "V":
            skipped += 1
            continue

        x3_tipo = row.get("X3_TIPO", row.get("x3_tipo", ""))
        if isinstance(x3_tipo, str):
            x3_tipo = x3_tipo.strip().upper()

        # Tipos validos: D, N, M (obrigatorio TOP_FIELD) e C (opcional TOP_FIELD)
        if x3_tipo not in ("D", "N", "M", "C"):
            continue

        x3_arquivo = row.get("X3_ARQUIVO", row.get("x3_arquivo", ""))
        x3_campo = row.get("X3_CAMPO", row.get("x3_campo", ""))
        x3_tamanho = row.get("X3_TAMANHO", row.get("x3_tamanho", 0))
        x3_decimal = row.get("X3_DECIMAL", row.get("x3_decimal", 0))

        if isinstance(x3_arquivo, str):
            x3_arquivo = x3_arquivo.strip()
        if isinstance(x3_campo, str):
            x3_campo = x3_campo.strip()

        if not x3_arquivo or not x3_campo:
            continue

        phys_table = f"{x3_arquivo}{company_code}0".upper()

        # Bypass: tabela nao existe fisicamente — pular
        if phys_table not in physical_tables:
            skipped += 1
            continue

        field_name = x3_campo.upper()

        tf_entry = topfield.get((phys_table, field_name))

        # Tipo C: TOP_FIELD e opcional
        # Se nao tem entrada → OK (VARCHAR normal, sem traducao)
        # Se tem entrada → deve ser type 'L' (campo logico/booleano)
        if x3_tipo == "C":
            if tf_entry is None:
                ok += 1
            else:
                actual_type = tf_entry["type"].strip().upper() if isinstance(tf_entry["type"], str) else str(tf_entry["type"])
                if actual_type == "L":
                    ok += 1
                else:
                    mismatch_list.append({
                        "table": phys_table,
                        "field": field_name,
                        "sx3_type": x3_tipo,
                        "expected": {"type": "L", "prec": "", "dec": ""},
                        "actual": tf_entry,
                    })
            continue

        # Tipos D, N, M: TOP_FIELD obrigatorio
        if tf_entry is None:
            missing_list.append({
                "table": phys_table,
                "field": field_name,
                "sx3_type": x3_tipo,
            })
            continue

        expected_type = TYPE_MAP[x3_tipo]
        actual_type = tf_entry["type"].strip().upper() if isinstance(tf_entry["type"], str) else str(tf_entry["type"])

        type_ok = actual_type == expected_type

        prec_ok = True
        dec_ok = True

        if x3_tipo == "D":
            prec_ok = str(tf_entry["prec"]) == "8"
        elif x3_tipo == "N":
            expected_prec = str(int(x3_tamanho)) if x3_tamanho else "0"
            expected_dec = str(int(x3_decimal)) if x3_decimal else "0"
            prec_ok = str(tf_entry["prec"]) == expected_prec
            dec_ok = str(tf_entry["dec"]) == expected_dec
        elif x3_tipo == "M":
            prec_ok = str(tf_entry["prec"]) == "10"

        if not type_ok or not prec_ok or not dec_ok:
            expected_prec_val = ""
            if x3_tipo == "D":
                expected_prec_val = "8"
            elif x3_tipo == "M":
                expected_prec_val = "10"
            elif x3_tipo == "N":
                expected_prec_val = str(int(x3_tamanho) if x3_tamanho else 0)

            mismatch_list.append({
                "table": phys_table,
                "field": field_name,
                "sx3_type": x3_tipo,
                "expected": {
                    "type": expected_type,
                    "prec": expected_prec_val,
                    "dec": str(int(x3_decimal) if x3_decimal else 0) if x3_tipo == "N" else "",
                },
                "actual": tf_entry,
            })
        else:
            ok += 1

    return {
        "ok": ok,
        "total": ok + len(missing_list) + len(mismatch_list),
        "skipped": skipped,
        "missing": missing_list,
        "type_mismatch": mismatch_list,
    }


def _validate_six_vs_indexes(six_rows, company_code, physical_tables, physical_indexes):
    """
    Verifica se indices do SIX existem como indices fisicos.
    Nome do indice fisico = {INDICE}{M0_CODIGO}0{ORDEM} (ex: AA39901).
    Bypass: indices de tabelas que nao existem no schema sao ignorados.
    Tambem compara campos (CHAVE) do SIX com colunas reais do indice.
    """
    if six_rows is None:
        return {"ok": 0, "missing": [], "key_mismatch": [], "error": "SIX nao encontrada"}

    if physical_indexes is None:
        return {"ok": 0, "missing": [], "key_mismatch": [], "error": "Indices fisicos nao carregados"}

    # Montar lista: cada linha SIX = 1 indice fisico ({INDICE}{M0_CODIGO}0{ORDEM})
    six_entries = []
    for row in six_rows:
        indice = row.get("INDICE", row.get("indice", ""))
        ordem = row.get("ORDEM", row.get("ordem", ""))
        chave = row.get("CHAVE", row.get("chave", ""))

        if isinstance(indice, str):
            indice = indice.strip().upper()
        if isinstance(ordem, str):
            ordem = ordem.strip().upper()
        if isinstance(chave, str):
            chave = chave.strip()

        if not indice or not ordem:
            continue

        # Nome do indice fisico: {INDICE}{M0_CODIGO}0{ORDEM}
        phys_index_name = f"{indice}{company_code}0{ordem}"
        # Tabela fisica: {INDICE}{M0_CODIGO}0
        phys_table_name = f"{indice}{company_code}0"

        # Campos esperados da CHAVE (separados por +)
        # Funcoes de conversao no metadado (DTOS, STR, etc.) envolvem o campo real
        # Ex: DTOS(AF8_DATA) → AF8_DATA, STR(EE7_KEY,10,0) → EE7_KEY
        raw_cols = [c.strip().upper() for c in chave.split("+") if c.strip()] if chave else []
        expected_cols = []
        for col in raw_cols:
            m = re.match(r'^[A-Z_]+\(([^,)]+)', col)
            if m:
                expected_cols.append(m.group(1).strip())
            else:
                expected_cols.append(col)

        six_entries.append({
            "indice": indice,
            "ordem": ordem,
            "phys_index": phys_index_name,
            "phys_table": phys_table_name,
            "expected_cols": expected_cols,
        })

    ok = 0
    missing_list = []
    key_mismatch_list = []
    skipped = 0

    for entry in six_entries:
        # Bypass: tabela nao existe fisicamente
        if entry["phys_table"] not in physical_tables:
            skipped += 1
            continue

        # Buscar indice fisico na tabela correspondente
        table_indexes = physical_indexes.get(entry["phys_table"], {})
        phys_cols = table_indexes.get(entry["phys_index"])

        if phys_cols is None:
            missing_list.append({
                "indice": entry["indice"],
                "ordem": entry["ordem"],
                "expected_index": entry["phys_index"],
                "table": entry["phys_table"],
            })
            continue

        # Comparar campos (CHAVE do SIX vs colunas reais do indice)
        # Filtrar campos implicitos do Protheus (R_E_C_N_O_, D_E_L_E_T_, etc.)
        expected = entry["expected_cols"]
        actual = [c.upper() for c in phys_cols if c.upper() not in IGNORE_COLUMNS]

        if expected and actual and expected != actual:
            key_mismatch_list.append({
                "indice": entry["indice"],
                "ordem": entry["ordem"],
                "index_name": entry["phys_index"],
                "table": entry["phys_table"],
                "expected_key": "+".join(expected),
                "actual_key": "+".join(actual),
            })
        else:
            ok += 1

    return {
        "ok": ok,
        "total": ok + len(missing_list) + len(key_mismatch_list),
        "skipped": skipped,
        "missing": missing_list,
        "key_mismatch": key_mismatch_list,
    }


# =========================================================
# VALIDACOES ADICIONAIS (F1-F5)
# =========================================================


def _get_col_value(col_dict, key_lower):
    """Helper para acessar valor de coluna independente do driver (case)."""
    return col_dict.get(key_lower, col_dict.get(key_lower.upper(), None))


def _parse_sx_field(row, field):
    """Extrai e normaliza campo string de uma row SX."""
    val = row.get(field, row.get(field.lower(), ""))
    if isinstance(val, str):
        return val.strip()
    return str(val) if val is not None else ""


def _parse_sx_num(row, field):
    """Extrai campo numerico de uma row SX."""
    val = row.get(field, row.get(field.lower(), 0))
    if val is None:
        return 0
    if isinstance(val, (int, float)):
        return val
    try:
        return int(val)
    except (ValueError, TypeError):
        return 0


def _extract_index_fields(chave):
    """Extrai campos reais de uma CHAVE SIX (separa por +, resolve funcoes)."""
    if not chave:
        return []
    raw_cols = [c.strip().upper() for c in chave.split("+") if c.strip()]
    fields = []
    for col in raw_cols:
        m = re.match(r'^[A-Z_]+\(([^,)]+)', col)
        if m:
            fields.append(m.group(1).strip())
        else:
            fields.append(col)
    return fields


# ----- F1: Schema vs SX3 bidirecional + tamanhos + virtuais -----


def _validate_schema_vs_sx3(sx2_rows, sx3_rows, company_code,
                             physical_tables, all_columns):
    """Campos fisicos da base que nao existem no SX3 (direcao inversa)."""
    if sx2_rows is None:
        return {"ok": 0, "total": 0, "issues": [],
                "error": "SX2 nao encontrada"}
    if sx3_rows is None:
        return {"ok": 0, "total": 0, "issues": [],
                "error": "SX3 nao encontrada"}

    # Montar set de tabelas Protheus que existem fisicamente
    sx2_map = {}
    for row in sx2_rows:
        x2_chave = _parse_sx_field(row, "X2_CHAVE")
        if x2_chave:
            phys = f"{x2_chave}{company_code}0".upper()
            if phys in physical_tables:
                sx2_map[phys] = x2_chave

    # Montar set de campos SX3 por tabela
    sx3_fields_by_table = {}
    for row in sx3_rows:
        x3_arquivo = _parse_sx_field(row, "X3_ARQUIVO").upper()
        x3_campo = _parse_sx_field(row, "X3_CAMPO").upper()
        if x3_arquivo and x3_campo:
            phys = f"{x3_arquivo}{company_code}0".upper()
            if phys not in sx3_fields_by_table:
                sx3_fields_by_table[phys] = set()
            sx3_fields_by_table[phys].add(x3_campo)

    ok = 0
    issues = []
    control_cols = {"R_E_C_N_O_", "R_E_C_D_E_L_", "D_E_L_E_T_", "S_T_A_M_P_", "I_N_S_D_T_"}

    for phys_table, x2_chave in sorted(sx2_map.items()):
        phys_cols = all_columns.get(phys_table, {}) if all_columns else {}
        sx3_set = sx3_fields_by_table.get(phys_table, set())

        for col_name in sorted(phys_cols.keys()):
            if col_name in control_cols:
                continue
            if col_name in sx3_set:
                ok += 1
            else:
                issues.append({
                    "table": phys_table,
                    "field": col_name,
                    "reason": "coluna_sem_sx3",
                })

    return {"ok": ok, "total": ok + len(issues), "issues": issues}


def _validate_sx3_field_sizes(sx3_rows, company_code,
                               physical_tables, all_columns):
    """Tamanhos de campo diferentes entre SX3 e base fisica."""
    if sx3_rows is None:
        return {"ok": 0, "total": 0, "issues": [],
                "error": "SX3 nao encontrada"}

    ok = 0
    issues = []

    for row in sx3_rows:
        x3_context = _parse_sx_field(row, "X3_CONTEXT").upper()
        if x3_context == "V":
            continue

        x3_arquivo = _parse_sx_field(row, "X3_ARQUIVO").upper()
        x3_campo = _parse_sx_field(row, "X3_CAMPO").upper()
        x3_tipo = _parse_sx_field(row, "X3_TIPO").upper()
        x3_tamanho = _parse_sx_num(row, "X3_TAMANHO")
        x3_decimal = _parse_sx_num(row, "X3_DECIMAL")

        if not x3_arquivo or not x3_campo:
            continue
        if x3_tipo not in ("C", "D"):
            continue
        # Tipo N e M: tamanho controlado pelo TOP_FIELD, nao pelo schema fisico

        phys_table = f"{x3_arquivo}{company_code}0".upper()
        if phys_table not in physical_tables:
            continue

        phys_cols = all_columns.get(phys_table, {}) if all_columns else {}

        col_info = phys_cols.get(x3_campo)
        if col_info is None:
            continue

        char_len = _get_col_value(col_info, "character_maximum_length")
        num_prec = _get_col_value(col_info, "numeric_precision")
        num_scale = _get_col_value(col_info, "numeric_scale")

        mismatch = None

        if x3_tipo == "C":
            if char_len is not None and int(char_len) != int(x3_tamanho):
                mismatch = {
                    "sx3_size": int(x3_tamanho),
                    "physical_size": int(char_len),
                    "detail": "character_maximum_length",
                }

        elif x3_tipo == "D":
            if char_len is not None and int(char_len) != 8:
                mismatch = {
                    "sx3_size": 8,
                    "physical_size": int(char_len),
                    "detail": "date_varchar8",
                }

        if mismatch:
            issues.append({
                "table": phys_table,
                "field": x3_campo,
                "type": x3_tipo,
                **mismatch,
            })
        else:
            ok += 1

    return {"ok": ok, "total": ok + len(issues), "issues": issues}


def _validate_virtual_in_schema(sx3_rows, company_code,
                                 physical_tables, all_columns):
    """Campos virtuais do SX3 que existem fisicamente na base."""
    if sx3_rows is None:
        return {"ok": 0, "total": 0, "issues": [],
                "error": "SX3 nao encontrada"}

    ok = 0
    issues = []

    for row in sx3_rows:
        x3_context = _parse_sx_field(row, "X3_CONTEXT").upper()
        if x3_context != "V":
            ok += 1
            continue

        x3_arquivo = _parse_sx_field(row, "X3_ARQUIVO").upper()
        x3_campo = _parse_sx_field(row, "X3_CAMPO").upper()
        if not x3_arquivo or not x3_campo:
            continue

        phys_table = f"{x3_arquivo}{company_code}0".upper()
        if phys_table not in physical_tables:
            continue

        phys_cols = all_columns.get(phys_table, {}) if all_columns else {}

        if x3_campo in phys_cols:
            issues.append({"table": phys_table, "field": x3_campo})

    return {"ok": ok, "total": ok + len(issues), "issues": issues}


# ----- F2: SX2 vs SX3 e SX2 vs SIX -----


def _validate_sx2_unique_fields(sx2_rows, sx3_rows):
    """Campos da chave unica SX2 que nao existem no SX3."""
    if sx2_rows is None:
        return {"ok": 0, "total": 0, "issues": [],
                "error": "SX2 nao encontrada"}
    if sx3_rows is None:
        return {"ok": 0, "total": 0, "issues": [],
                "error": "SX3 nao encontrada"}

    # Montar set de (arquivo, campo) do SX3
    sx3_set = set()
    for row in sx3_rows:
        arq = _parse_sx_field(row, "X3_ARQUIVO").upper()
        campo = _parse_sx_field(row, "X3_CAMPO").upper()
        if arq and campo:
            sx3_set.add((arq, campo))

    ok = 0
    issues = []

    for row in sx2_rows:
        x2_chave = _parse_sx_field(row, "X2_CHAVE").upper()
        x2_uession = _parse_sx_field(row, "X2_UNICO")
        if not x2_chave or not x2_uession:
            continue

        fields = _extract_index_fields(x2_uession)
        for field in fields:
            if (x2_chave, field) in sx3_set:
                ok += 1
            else:
                issues.append({
                    "table": x2_chave,
                    "field": field,
                    "reason": "campo_unico_sem_sx3",
                })

    return {"ok": ok, "total": ok + len(issues), "issues": issues}


def _validate_sx2_unique_virtual(sx2_rows, sx3_rows):
    """Campos da chave unica SX2 que sao virtuais no SX3."""
    if sx2_rows is None:
        return {"ok": 0, "total": 0, "issues": [],
                "error": "SX2 nao encontrada"}
    if sx3_rows is None:
        return {"ok": 0, "total": 0, "issues": [],
                "error": "SX3 nao encontrada"}

    # Montar mapa de contexto por (arquivo, campo)
    sx3_context = {}
    for row in sx3_rows:
        arq = _parse_sx_field(row, "X3_ARQUIVO").upper()
        campo = _parse_sx_field(row, "X3_CAMPO").upper()
        ctx = _parse_sx_field(row, "X3_CONTEXT").upper()
        if arq and campo:
            sx3_context[(arq, campo)] = ctx

    ok = 0
    issues = []

    for row in sx2_rows:
        x2_chave = _parse_sx_field(row, "X2_CHAVE").upper()
        x2_uession = _parse_sx_field(row, "X2_UNICO")
        if not x2_chave or not x2_uession:
            continue

        fields = _extract_index_fields(x2_uession)
        for field in fields:
            ctx = sx3_context.get((x2_chave, field), "")
            if ctx == "V":
                issues.append({
                    "table": x2_chave,
                    "field": field,
                    "reason": "campo_unico_virtual",
                })
            else:
                ok += 1

    return {"ok": ok, "total": ok + len(issues), "issues": issues}


def _validate_sx2_no_sx3(sx2_rows, sx3_rows):
    """Tabelas SX2 sem nenhuma estrutura definida no SX3."""
    if sx2_rows is None:
        return {"ok": 0, "total": 0, "issues": [],
                "error": "SX2 nao encontrada"}
    if sx3_rows is None:
        return {"ok": 0, "total": 0, "issues": [],
                "error": "SX3 nao encontrada"}

    sx3_archives = set()
    for row in sx3_rows:
        arq = _parse_sx_field(row, "X3_ARQUIVO").upper()
        if arq:
            sx3_archives.add(arq)

    ok = 0
    issues = []

    for row in sx2_rows:
        x2_chave = _parse_sx_field(row, "X2_CHAVE").upper()
        if not x2_chave:
            continue
        if x2_chave in sx3_archives:
            ok += 1
        else:
            issues.append({"table": x2_chave, "reason": "sem_sx3"})

    return {"ok": ok, "total": ok + len(issues), "issues": issues}


def _validate_sx3_no_sx2(sx2_rows, sx3_rows):
    """Estruturas SX3 sem definicao no SX2."""
    if sx2_rows is None:
        return {"ok": 0, "total": 0, "issues": [],
                "error": "SX2 nao encontrada"}
    if sx3_rows is None:
        return {"ok": 0, "total": 0, "issues": [],
                "error": "SX3 nao encontrada"}

    sx2_keys = set()
    for row in sx2_rows:
        x2_chave = _parse_sx_field(row, "X2_CHAVE").upper()
        if x2_chave:
            sx2_keys.add(x2_chave)

    sx3_archives = set()
    for row in sx3_rows:
        arq = _parse_sx_field(row, "X3_ARQUIVO").upper()
        if arq:
            sx3_archives.add(arq)

    ok = 0
    issues = []

    for arq in sorted(sx3_archives):
        if arq in sx2_keys:
            ok += 1
        else:
            issues.append({"table": arq, "reason": "sem_sx2"})

    return {"ok": ok, "total": ok + len(issues), "issues": issues}


def _validate_sx2_no_six(sx2_rows, six_rows):
    """Tabelas SX2 sem nenhum indice definido no SIX."""
    if sx2_rows is None:
        return {"ok": 0, "total": 0, "issues": [],
                "error": "SX2 nao encontrada"}
    if six_rows is None:
        return {"ok": 0, "total": 0, "issues": [],
                "error": "SIX nao encontrada"}

    six_indices = set()
    for row in six_rows:
        indice = _parse_sx_field(row, "INDICE").upper()
        if indice:
            six_indices.add(indice)

    ok = 0
    issues = []

    for row in sx2_rows:
        x2_chave = _parse_sx_field(row, "X2_CHAVE").upper()
        if not x2_chave:
            continue
        if x2_chave in six_indices:
            ok += 1
        else:
            issues.append({"table": x2_chave, "reason": "sem_six"})

    return {"ok": ok, "total": ok + len(issues), "issues": issues}


def _validate_six_no_sx2(sx2_rows, six_rows):
    """Indices SIX sem tabela definida no SX2."""
    if sx2_rows is None:
        return {"ok": 0, "total": 0, "issues": [],
                "error": "SX2 nao encontrada"}
    if six_rows is None:
        return {"ok": 0, "total": 0, "issues": [],
                "error": "SIX nao encontrada"}

    sx2_keys = set()
    for row in sx2_rows:
        x2_chave = _parse_sx_field(row, "X2_CHAVE").upper()
        if x2_chave:
            sx2_keys.add(x2_chave)

    six_indices = set()
    for row in six_rows:
        indice = _parse_sx_field(row, "INDICE").upper()
        if indice:
            six_indices.add(indice)

    ok = 0
    issues = []

    for indice in sorted(six_indices):
        if indice in sx2_keys:
            ok += 1
        else:
            issues.append({"indice": indice, "reason": "sem_sx2"})

    return {"ok": ok, "total": ok + len(issues), "issues": issues}


# ----- F3: SIX validacoes adicionais -----


def _validate_six_fields_sx3(six_rows, sx3_rows):
    """Campos de indices SIX que nao existem no SX3."""
    if six_rows is None:
        return {"ok": 0, "total": 0, "issues": [],
                "error": "SIX nao encontrada"}
    if sx3_rows is None:
        return {"ok": 0, "total": 0, "issues": [],
                "error": "SX3 nao encontrada"}

    sx3_set = set()
    for row in sx3_rows:
        arq = _parse_sx_field(row, "X3_ARQUIVO").upper()
        campo = _parse_sx_field(row, "X3_CAMPO").upper()
        if arq and campo:
            sx3_set.add((arq, campo))

    ok = 0
    issues = []

    for row in six_rows:
        indice = _parse_sx_field(row, "INDICE").upper()
        ordem = _parse_sx_field(row, "ORDEM").upper()
        chave = _parse_sx_field(row, "CHAVE")
        if not indice or not chave:
            continue

        fields = _extract_index_fields(chave)
        for field in fields:
            if (indice, field) in sx3_set:
                ok += 1
            else:
                issues.append({
                    "indice": indice,
                    "ordem": ordem,
                    "field": field,
                    "reason": "campo_indice_sem_sx3",
                })

    return {"ok": ok, "total": ok + len(issues), "issues": issues}


def _validate_six_virtual_memo(six_rows, sx3_rows):
    """Campos virtuais ou MEMO utilizados em indices SIX."""
    if six_rows is None:
        return {"ok": 0, "total": 0, "issues": [],
                "error": "SIX nao encontrada"}
    if sx3_rows is None:
        return {"ok": 0, "total": 0, "issues": [],
                "error": "SX3 nao encontrada"}

    # Mapa (arquivo, campo) → {context, tipo}
    sx3_info = {}
    for row in sx3_rows:
        arq = _parse_sx_field(row, "X3_ARQUIVO").upper()
        campo = _parse_sx_field(row, "X3_CAMPO").upper()
        ctx = _parse_sx_field(row, "X3_CONTEXT").upper()
        tipo = _parse_sx_field(row, "X3_TIPO").upper()
        if arq and campo:
            sx3_info[(arq, campo)] = {"context": ctx, "tipo": tipo}

    ok = 0
    issues = []

    for row in six_rows:
        indice = _parse_sx_field(row, "INDICE").upper()
        ordem = _parse_sx_field(row, "ORDEM").upper()
        chave = _parse_sx_field(row, "CHAVE")
        if not indice or not chave:
            continue

        fields = _extract_index_fields(chave)
        for field in fields:
            info = sx3_info.get((indice, field))
            if info is None:
                continue
            if info["context"] == "V":
                issues.append({
                    "indice": indice,
                    "ordem": ordem,
                    "field": field,
                    "reason": "virtual",
                })
            elif info["tipo"] == "M":
                issues.append({
                    "indice": indice,
                    "ordem": ordem,
                    "field": field,
                    "reason": "memo",
                })
            else:
                ok += 1

    return {"ok": ok, "total": ok + len(issues), "issues": issues}


# ----- F4: Duplicados + Compartilhamento -----


def _validate_duplicates(sx2_rows, sx3_rows, six_rows):
    """Registros duplicados em SX2, SX3 e SIX."""
    results = {"ok": 0, "total": 0, "issues": []}

    datasets = [
        ("SX2", sx2_rows, ["X2_CHAVE"]),
        ("SX3", sx3_rows, ["X3_ARQUIVO", "X3_CAMPO"]),
        ("SIX", six_rows, ["INDICE", "ORDEM"]),
    ]

    for table_name, rows, key_cols in datasets:
        if rows is None:
            continue

        # Filtrar deletados
        active_rows = []
        for row in rows:
            d = _parse_sx_field(row, "D_E_L_E_T_")
            if d != "*":
                active_rows.append(row)

        counts = {}
        for row in active_rows:
            key_parts = []
            for kc in key_cols:
                key_parts.append(_parse_sx_field(row, kc).upper())
            key = "|".join(key_parts)
            counts[key] = counts.get(key, 0) + 1

        for key, count in sorted(counts.items()):
            if count > 1:
                results["issues"].append({
                    "table_name": table_name,
                    "key_values": key,
                    "count": count,
                })
                results["total"] += count
            else:
                results["ok"] += 1
                results["total"] += 1

    return results


def _validate_sx2_sharing(cursor, driver, sx2_rows, company_code, physical_tables):
    """
    Verificacao de compartilhamento SX2 (X2_MODO) vs base fisica.
    Se X2_MODO = 'C' (compartilhado), registros da tabela fisica devem ter
    o campo ??_FILIAL = ' ' (branco). Se houver registros com filial preenchida,
    ha inconsistencia.
    """
    if sx2_rows is None:
        return {"ok": 0, "total": 0, "issues": [],
                "error": "SX2 nao encontrada"}

    has_modo = False
    if sx2_rows:
        sample = sx2_rows[0]
        if "X2_MODO" in sample or "x2_modo" in sample:
            has_modo = True

    if not has_modo:
        return {"ok": 0, "total": 0, "issues": [],
                "skipped": "X2_MODO nao encontrado no schema"}

    ok = 0
    issues = []

    for row in sx2_rows:
        x2_chave = _parse_sx_field(row, "X2_CHAVE").upper()
        x2_modo = _parse_sx_field(row, "X2_MODO").upper()
        if not x2_chave:
            continue

        if x2_modo == "C":
            # Tabela compartilhada: verificar se _FILIAL esta em branco na base
            phys_table = f"{x2_chave}{company_code}0".upper()
            if phys_table not in physical_tables:
                ok += 1
                continue

            filial_col = f"{x2_chave}_FILIAL"
            try:
                if driver == "mssql":
                    q = f"SELECT TOP 1 [{filial_col}] FROM [{phys_table}] WHERE LTRIM(RTRIM([{filial_col}])) <> ''"
                elif driver == "postgresql":
                    q = f"SELECT {filial_col.lower()} FROM {phys_table.lower()} WHERE TRIM({filial_col.lower()}) <> '' LIMIT 1"
                elif driver == "mysql":
                    q = f"SELECT `{filial_col}` FROM `{phys_table}` WHERE TRIM(`{filial_col}`) <> '' LIMIT 1"
                elif driver == "oracle":
                    q = f"SELECT \"{filial_col}\" FROM \"{phys_table}\" WHERE TRIM(\"{filial_col}\") <> '' AND ROWNUM = 1"
                else:
                    ok += 1
                    continue

                cursor.execute(q)
                has_filial = cursor.fetchone()
                if has_filial:
                    issues.append({
                        "table": x2_chave,
                        "x2_modo": "C",
                        "reason": "compartilhada_com_filial",
                    })
                else:
                    ok += 1
            except Exception:
                ok += 1  # Se falhar (ex: coluna nao existe), nao reportar
        elif x2_modo == "E":
            ok += 1
        elif x2_modo:
            issues.append({
                "table": x2_chave,
                "x2_modo": x2_modo,
                "reason": "modo_invalido",
            })
        else:
            issues.append({
                "table": x2_chave,
                "x2_modo": "",
                "reason": "modo_vazio",
            })

    return {"ok": ok, "total": ok + len(issues), "issues": issues}


# ----- F5: Referencias cruzadas (SXG, SXA, SXB) -----


def _validate_sx3_ref_sxg(sx3_rows, sxg_rows, company_code):
    """Referencias a grupos SXG que nao existem."""
    if sx3_rows is None:
        return {"ok": 0, "total": 0, "issues": [],
                "error": "SX3 nao encontrada"}

    sxg_table = _make_table_name("SXG", company_code)
    if sxg_rows is None:
        return {"ok": 0, "total": 0, "issues": [],
                "error": f"Tabela {sxg_table} nao encontrada"}

    # Montar set de grupos existentes
    sxg_groups = set()
    for row in sxg_rows:
        xg = _parse_sx_field(row, "XG_GRUPO").upper()
        if xg:
            sxg_groups.add(xg)

    ok = 0
    issues = []

    for row in sx3_rows:
        x3_grupo = _parse_sx_field(row, "X3_GRPSXG").upper()
        if not x3_grupo:
            continue
        x3_arquivo = _parse_sx_field(row, "X3_ARQUIVO").upper()
        x3_campo = _parse_sx_field(row, "X3_CAMPO").upper()

        if x3_grupo in sxg_groups:
            ok += 1
        else:
            issues.append({
                "table": x3_arquivo,
                "field": x3_campo,
                "x3_grpsxg": x3_grupo,
                "reason": "grupo_sem_sxg",
            })

    return {"ok": ok, "total": ok + len(issues), "issues": issues}


def _validate_sx3_ref_sxa(sx3_rows, sxa_rows, company_code):
    """Referencias a pastas SXA que nao existem."""
    if sx3_rows is None:
        return {"ok": 0, "total": 0, "issues": [],
                "error": "SX3 nao encontrada"}

    sxa_table = _make_table_name("SXA", company_code)
    if sxa_rows is None:
        return {"ok": 0, "total": 0, "issues": [],
                "error": f"Tabela {sxa_table} nao encontrada"}

    # Montar set de folders existentes (XA_ALIAS + XA_ORDEM)
    sxa_folders = set()
    for row in sxa_rows:
        xa_alias = _parse_sx_field(row, "XA_ALIAS").upper()
        xa_ordem = _parse_sx_field(row, "XA_ORDEM").upper()
        if xa_alias and xa_ordem:
            sxa_folders.add((xa_alias, xa_ordem))

    ok = 0
    issues = []

    for row in sx3_rows:
        x3_folder = _parse_sx_field(row, "X3_FOLDER").strip()
        if not x3_folder:
            continue
        x3_arquivo = _parse_sx_field(row, "X3_ARQUIVO").upper()
        x3_campo = _parse_sx_field(row, "X3_CAMPO").upper()

        # X3_FOLDER pode ser numerico — verificar se existe alguma
        # pasta com (X3_ARQUIVO, X3_FOLDER) no SXA
        found = (x3_arquivo, x3_folder.upper()) in sxa_folders
        if found:
            ok += 1
        else:
            issues.append({
                "table": x3_arquivo,
                "field": x3_campo,
                "x3_folder": x3_folder,
                "reason": "folder_sem_sxa",
            })

    return {"ok": ok, "total": ok + len(issues), "issues": issues}


def _validate_sx3_ref_sxb(sx3_rows, sxb_rows, sx5_rows, company_code):
    """Referencias a consultas padrao SXB/SX5 que nao existem.
    X3_F3 referencia tanto SXB (XB_ALIAS) quanto SX5 (X5_TABELA).
    Se existir em qualquer uma das duas, esta OK.
    """
    if sx3_rows is None:
        return {"ok": 0, "total": 0, "issues": [],
                "error": "SX3 nao encontrada"}

    sxb_table = _make_table_name("SXB", company_code)
    sx5_table = _make_table_name("SX5", company_code)

    sxb_aliases = set()
    if sxb_rows:
        for row in sxb_rows:
            xb_alias = _parse_sx_field(row, "XB_ALIAS").upper()
            if xb_alias:
                sxb_aliases.add(xb_alias)

    sx5_tabelas = set()
    if sx5_rows:
        for row in sx5_rows:
            x5_tabela = _parse_sx_field(row, "X5_TABELA").upper()
            if x5_tabela:
                sx5_tabelas.add(x5_tabela)

    if not sxb_rows and not sx5_rows:
        return {"ok": 0, "total": 0, "issues": [],
                "error": f"Tabelas {sxb_table} e {sx5_table} nao encontradas"}

    ok = 0
    issues = []

    for row in sx3_rows:
        x3_f3 = _parse_sx_field(row, "X3_F3").upper()
        if not x3_f3:
            continue
        x3_arquivo = _parse_sx_field(row, "X3_ARQUIVO").upper()
        x3_campo = _parse_sx_field(row, "X3_CAMPO").upper()

        if x3_f3 in sxb_aliases or x3_f3 in sx5_tabelas:
            ok += 1
        else:
            issues.append({
                "table": x3_arquivo,
                "field": x3_campo,
                "x3_f3": x3_f3,
                "reason": "consulta_sem_sxb_sx5",
            })

    return {"ok": ok, "total": ok + len(issues), "issues": issues}


# =========================================================
# HISTORICO
# =========================================================


def save_history(environment_id, operation_type, conn_a_id, conn_b_id,
                 company_code, summary, details, user_id, duration_ms):
    """Salva resultado de compare/validate no historico."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        import json
        cursor.execute("""
            INSERT INTO dictionary_history
                (environment_id, operation_type, connection_a_id, connection_b_id,
                 company_code, summary, details, executed_by, executed_at, duration_ms)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            environment_id, operation_type, conn_a_id, conn_b_id,
            company_code,
            json.dumps(summary, ensure_ascii=False, default=str),
            json.dumps(details, ensure_ascii=False, default=str),
            user_id, datetime.now(), duration_ms,
        ))
        row = cursor.fetchone()
        conn.commit()
        return dict(row)["id"] if row else None
    except Exception:
        conn.rollback()
        raise
    finally:
        release_db_connection(conn)


def get_history(environment_id, limit=20):
    """Retorna historico de operacoes de dicionario (sem details para listar)."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT dh.id, dh.environment_id, dh.operation_type,
                   dh.connection_a_id, dh.connection_b_id, dh.company_code,
                   dh.summary, dh.executed_by, dh.executed_at, dh.duration_ms,
                   u.username AS executed_by_name,
                   ca.name AS conn_a_name,
                   cb.name AS conn_b_name
            FROM dictionary_history dh
            LEFT JOIN users u ON dh.executed_by = u.id
            LEFT JOIN database_connections ca ON dh.connection_a_id = ca.id
            LEFT JOIN database_connections cb ON dh.connection_b_id = cb.id
            WHERE dh.environment_id = %s
            ORDER BY dh.executed_at DESC
            LIMIT %s
        """, (environment_id, limit))
        results = []
        for row in cursor.fetchall():
            item = dict(row)
            if item.get("executed_at"):
                item["executed_at"] = item["executed_at"].isoformat()
            results.append(item)
        return results
    finally:
        release_db_connection(conn)


def get_history_detail(history_id):
    """Retorna um registro completo do historico (com details)."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT dh.*,
                   u.username AS executed_by_name,
                   ca.name AS conn_a_name,
                   cb.name AS conn_b_name
            FROM dictionary_history dh
            LEFT JOIN users u ON dh.executed_by = u.id
            LEFT JOIN database_connections ca ON dh.connection_a_id = ca.id
            LEFT JOIN database_connections cb ON dh.connection_b_id = cb.id
            WHERE dh.id = %s
        """, (history_id,))
        row = cursor.fetchone()
        if not row:
            return None
        item = dict(row)
        if item.get("executed_at"):
            item["executed_at"] = item["executed_at"].isoformat()
        return item
    finally:
        release_db_connection(conn)


def delete_history(history_id):
    """Exclui um registro do historico."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM dictionary_history WHERE id = %s RETURNING id", (history_id,))
        row = cursor.fetchone()
        conn.commit()
        return row is not None
    except Exception:
        conn.rollback()
        raise
    finally:
        release_db_connection(conn)
