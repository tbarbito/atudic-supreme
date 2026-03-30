"""
Equalizador Online de Dicionario Protheus.

Sincroniza seletivamente estrutura entre dois bancos Protheus:
- Campos faltantes (ALTER TABLE + INSERT SX3 + INSERT TOP_FIELD)
- Indices faltantes (CREATE INDEX + INSERT SIX)
- Tabelas inteiras novas (CREATE TABLE + todos metadados)

Regra de ouro: fisico primeiro (DDL), metadado depois (DML).
Tudo em transacao atomica — qualquer erro = ROLLBACK completo.
"""

import hashlib
import json
import logging
import re
import time
from app.services.database_browser import get_connection_config, _get_external_connection
from app.services.dictionary_compare import (
    _fetch_all_rows,
    _get_physical_tables,
    _get_all_physical_columns_bulk,
    _get_physical_indexes,
    _get_topfield_data,
    _make_table_name,
    save_history,
    ALWAYS_IGNORE_COLUMNS,
    TABLE_KEYS,
)

logger = logging.getLogger(__name__)

# Colunas de controle Protheus — nunca incluir em INSERTs de metadados
CONTROL_COLUMNS = {"R_E_C_N_O_", "R_E_C_D_E_L_"}


# =========================================================
# HELPERS
# =========================================================


def _quote_id(name, driver):
    """Quota identificador SQL conforme driver."""
    if driver == "mssql":
        return f"[{name}]"
    if driver == "postgresql":
        return f'"{name.lower()}"'
    return f'"{name}"'


def _quote_value(value):
    """Escapa valor para SQL literal. Protheus nao aceita NULL — usa espaco."""
    if value is None or value == "":
        return "' '"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    # String — escapa aspas simples
    s = str(value).replace("'", "''")
    return f"'{s}'"


def _build_column_def(col_info, driver):
    """Monta definicao de coluna SQL a partir de INFORMATION_SCHEMA row.
    Retorna apenas o tipo SQL (ex: VARCHAR(10), NUMERIC(12,2))."""
    data_type = (col_info.get("DATA_TYPE") or col_info.get("data_type") or "").upper().strip()

    char_len = col_info.get("CHARACTER_MAXIMUM_LENGTH") or col_info.get("character_maximum_length")
    num_prec = col_info.get("NUMERIC_PRECISION") or col_info.get("numeric_precision")
    num_scale = col_info.get("NUMERIC_SCALE") or col_info.get("numeric_scale")
    # Oracle
    if not char_len:
        char_len = col_info.get("DATA_LENGTH") or col_info.get("data_length")
    if not num_prec:
        num_prec = col_info.get("DATA_PRECISION") or col_info.get("data_precision")
    if not num_scale:
        num_scale = col_info.get("DATA_SCALE") or col_info.get("data_scale")

    # Normalizar tipo base
    base = data_type
    if data_type in ("CHARACTER VARYING", "CHARACTER_VARYING"):
        base = "VARCHAR"

    # Montar tipo completo
    if base in ("VARCHAR", "NVARCHAR", "CHAR", "NCHAR"):
        length = int(char_len) if char_len and str(char_len) != "-1" else 8000
        if str(char_len) == "-1":
            return "VARCHAR(MAX)" if driver == "mssql" else "TEXT"
        return f"{base}({length})"

    elif base in ("NUMERIC", "DECIMAL"):
        p = int(num_prec) if num_prec else 18
        s = int(num_scale) if num_scale else 0
        return f"{base}({p},{s})"

    elif base in ("FLOAT", "REAL", "DOUBLE PRECISION"):
        return base

    elif base in ("INT", "INTEGER", "BIGINT", "SMALLINT", "TINYINT"):
        return base

    elif base in ("TEXT", "NTEXT"):
        return "TEXT"

    elif base == "DATETIME":
        return "TIMESTAMP" if driver == "postgresql" else "DATETIME"

    elif base in ("TIMESTAMP", "TIMESTAMP WITHOUT TIME ZONE"):
        return "DATETIME" if driver == "mssql" else "TIMESTAMP"

    elif base == "BIT":
        return "BOOLEAN" if driver == "postgresql" else "BIT"

    elif base == "BOOLEAN":
        return "BIT" if driver == "mssql" else "BOOLEAN"

    elif base in ("IMAGE", "BYTEA", "BLOB"):
        return "BYTEA" if driver == "postgresql" else "IMAGE"

    # Fallback: retornar como esta
    if char_len and int(char_len) > 0:
        return f"{base}({int(char_len)})"
    return base


# Tipos numericos que recebem DEFAULT 0
_NUMERIC_TYPES = {
    "NUMERIC",
    "DECIMAL",
    "FLOAT",
    "REAL",
    "DOUBLE PRECISION",
    "INT",
    "INTEGER",
    "BIGINT",
    "SMALLINT",
    "TINYINT",
    "BIT",
    "BOOLEAN",
}


def _build_not_null_default(col_type_str):
    """Retorna clausula NOT NULL DEFAULT adequada ao Protheus.

    Regra Protheus:
      - CHAR/VARCHAR: NOT NULL DEFAULT '<espacos do tamanho do campo>'
      - Numericos: NOT NULL DEFAULT 0
      - Demais (TEXT, IMAGE, DATETIME...): NOT NULL DEFAULT ''
    """
    upper = col_type_str.upper().strip()

    # Extrair tipo base (antes do parentese)
    base = upper.split("(")[0].strip()

    if base in _NUMERIC_TYPES:
        return "NOT NULL DEFAULT 0"

    # CHAR/VARCHAR — extrair length para default de espacos
    if base in ("VARCHAR", "NVARCHAR", "CHAR", "NCHAR"):
        # Extrair tamanho do campo — ex: VARCHAR(10) -> 10
        m = re.search(r"\((\d+)\)", upper)
        if m:
            length = int(m.group(1))
            spaces = " " * length
            return f"NOT NULL DEFAULT '{spaces}'"
        return "NOT NULL DEFAULT ' '"

    # Demais tipos (TEXT, DATETIME, IMAGE, etc.)
    return "NOT NULL DEFAULT ' '"


def _build_insert_sql(table_name, row_dict, driver):
    """Monta INSERT SQL fiel a origem.

    R_E_C_N_O_: IDENTITY/SERIAL — omitido (banco auto-gera)
    R_E_C_D_E_L_: forcar 0 (se existir na row)
    D_E_L_E_T_: forcar espaco se vazio (se existir na row)
    Demais campos: valor original da origem (nunca NULL — espaco/0)

    Somente inclui colunas de controle (D_E_L_E_T_, R_E_C_D_E_L_) se
    existirem na row de origem. TOP_FIELD e outras tabelas de controle
    nao possuem essas colunas.
    """
    cols = []
    vals = []
    table_q = _quote_id(table_name, driver)

    for k, v in sorted(row_dict.items()):
        key = k.strip() if isinstance(k, str) else k
        key_upper = key.upper()

        # R_E_C_N_O_: IDENTITY/SERIAL — banco auto-gera
        if key_upper == "R_E_C_N_O_":
            continue

        # R_E_C_D_E_L_: forcar 0
        if key_upper == "R_E_C_D_E_L_":
            cols.append(_quote_id(key_upper, driver))
            vals.append("0")
            continue

        # D_E_L_E_T_: forcar espaco se vazio/NULL
        if key_upper == "D_E_L_E_T_":
            cols.append(_quote_id(key_upper, driver))
            vals.append(_quote_value(v if v and str(v).strip() else " "))
            continue

        cols.append(_quote_id(key_upper, driver))
        vals.append(_quote_value(v))

    cols_str = ", ".join(cols)
    vals_str = ", ".join(vals)
    return f"INSERT INTO {table_q} ({cols_str}) VALUES ({vals_str})"


def _compute_token(statements):
    """Gera SHA-256 token de confirmacao a partir de lista de SQLs."""
    combined = "\n".join(s["sql"] for s in statements)
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


# Mapeamento SX3 X3_TIPO -> tipo base SQL esperado
_SX3_TYPE_MAP = {
    "C": {"VARCHAR", "NVARCHAR", "CHAR", "NCHAR"},
    "N": {"NUMERIC", "DECIMAL", "FLOAT", "REAL", "DOUBLE PRECISION", "INT", "INTEGER"},
    "D": {"VARCHAR", "NVARCHAR", "CHAR", "NCHAR"},  # Protheus armazena data como CHAR/VARCHAR
    "L": {"VARCHAR", "NVARCHAR", "CHAR", "NCHAR", "BIT", "BOOLEAN"},
    "M": {"VARCHAR", "NVARCHAR", "TEXT", "NTEXT"},
}


def _check_meta_vs_physical(sx3_row, col_info, driver, table_alias, field_name,
                            phys_table, label, warnings_list):
    """Compara definicao SX3 com coluna fisica e adiciona warnings se divergirem.

    Verifica tipo e tamanho para detectar inconsistencias entre metadado e
    objeto fisico no MESMO banco.
    """
    x3_tipo = _get_field(sx3_row, "X3_TIPO").upper()
    x3_tam = _get_field(sx3_row, "X3_TAMANHO")
    x3_dec = _get_field(sx3_row, "X3_DECIMAL")

    # Tipo fisico
    phys_type = _build_column_def(col_info, driver).upper()
    phys_base = phys_type.split("(")[0].strip()

    # Verificar tipo compativel
    expected_bases = _SX3_TYPE_MAP.get(x3_tipo, set())
    if expected_bases and phys_base not in expected_bases:
        warnings_list.append(
            f"[{label}] {table_alias}.{field_name}: SX3 tipo '{x3_tipo}' "
            f"incompativel com fisico '{phys_base}' em {phys_table}"
        )
        return  # Se tipo diverge, nao faz sentido comparar tamanho

    # Verificar tamanho para tipos caractere
    if x3_tipo == "C" and x3_tam:
        try:
            expected_len = int(x3_tam)
            # Extrair tamanho do tipo fisico
            m = re.search(r"\((\d+)\)", phys_type)
            if m:
                actual_len = int(m.group(1))
                if expected_len != actual_len:
                    warnings_list.append(
                        f"[{label}] {table_alias}.{field_name}: SX3 tamanho {expected_len} "
                        f"difere do fisico {actual_len} em {phys_table}"
                    )
        except (ValueError, TypeError):
            pass

    # Verificar precisao/escala para tipos numericos
    if x3_tipo == "N" and x3_tam:
        try:
            expected_prec = int(x3_tam)
            expected_dec = int(x3_dec) if x3_dec else 0
            m = re.search(r"\((\d+),(\d+)\)", phys_type)
            if m:
                actual_prec = int(m.group(1))
                actual_dec = int(m.group(2))
                if expected_prec != actual_prec or expected_dec != actual_dec:
                    warnings_list.append(
                        f"[{label}] {table_alias}.{field_name}: SX3 ({expected_prec},{expected_dec}) "
                        f"difere do fisico ({actual_prec},{actual_dec}) em {phys_table}"
                    )
        except (ValueError, TypeError):
            pass


def _load_source_metadata(cursor, driver, company_code, items):
    """Carrega metadados REAIS do source para garantir fidelidade.

    Retorna dict com:
        sx2: {ALIAS_UPPER: row_dict}
        sx3: {"ALIAS|CAMPO": row_dict}
        sx3_by_table: {ALIAS_UPPER: [row_dicts]}
        six: {"INDICE|ORDEM": row_dict}
        six_by_table: {INDICE_UPPER: [row_dicts]}
        other: {"TABLE|KEY": row_dict}
    """
    result = {"sx2": {}, "sx3": {}, "sx3_by_table": {}, "six": {}, "six_by_table": {}, "other": {}}

    # Identificar quais tabelas de metadado precisam ser carregadas
    needs_sx2 = False
    needs_sx3 = False
    needs_six = False
    other_tables = set()

    for item in items:
        t = item.get("type", "")
        if t == "field":
            needs_sx3 = True
        elif t == "field_diff":
            needs_sx3 = True
        elif t == "index":
            needs_six = True
        elif t == "full_table":
            needs_sx2 = True
            needs_sx3 = True
            needs_six = True
        elif t == "metadata":
            mt = item.get("meta_table", "").upper()
            if mt:
                other_tables.add(mt)
        elif t == "metadata_diff":
            mt = item.get("meta_table", "").upper()
            if mt:
                other_tables.add(mt)

    # Carregar SX2
    if needs_sx2:
        sx2_table = _make_table_name("SX2", company_code)
        try:
            rows = _fetch_all_rows(cursor, driver, sx2_table)
            for row in rows:
                alias = _get_field(row, "X2_CHAVE").upper()
                if alias:
                    result["sx2"][alias] = row
        except Exception:
            pass

    # Carregar SX3
    if needs_sx3:
        sx3_table = _make_table_name("SX3", company_code)
        try:
            rows = _fetch_all_rows(cursor, driver, sx3_table)
            for row in rows:
                arquivo = _get_field(row, "X3_ARQUIVO").upper()
                campo = _get_field(row, "X3_CAMPO").upper()
                if arquivo and campo:
                    key = f"{arquivo}|{campo}"
                    result["sx3"][key] = row
                    result["sx3_by_table"].setdefault(arquivo, []).append(row)
        except Exception:
            pass

    # Carregar SIX
    if needs_six:
        six_table = _make_table_name("SIX", company_code)
        try:
            rows = _fetch_all_rows(cursor, driver, six_table)
            for row in rows:
                indice = _get_field(row, "INDICE").upper()
                ordem = _get_field(row, "ORDEM").upper()
                if indice and ordem:
                    key = f"{indice}|{ordem}"
                    result["six"][key] = row
                    result["six_by_table"].setdefault(indice, []).append(row)
        except Exception:
            pass

    # Carregar outras tabelas de metadado (SX1, SX5, SX7, etc.)
    for mt in other_tables:
        phys = _make_table_name(mt, company_code)
        try:
            rows = _fetch_all_rows(cursor, driver, phys)
            key_cols = TABLE_KEYS.get(mt, [])
            for row in rows:
                if key_cols:
                    key_parts = []
                    for kc in key_cols:
                        key_parts.append(_get_field(row, kc).upper())
                    item_key = "|".join(key_parts)
                else:
                    # Fallback: todas as colunas como key
                    item_key = "|".join(str(v).strip() for v in row.values())
                full_key = f"{mt}|{item_key}"
                result["other"][full_key] = row
        except Exception:
            pass

    return result


# =========================================================
# PREVIEW
# =========================================================


def generate_equalize_preview(source_conn_id, target_conn_id, company_code, items):
    """
    Gera preview de SQL para equalizacao sem executar nada.

    Args:
        items: lista de itens a equalizar, cada um com:
            - type: "field", "index", "full_table", "metadata"
            - meta_table: prefixo da tabela de metadado (SX3, SIX, SX2, etc.)
            - values: dict com todos os campos do registro de metadado
            Para "field": table_alias, field_name
            Para "index": indice, ordem
            Para "full_table": table_alias
            Para "metadata": (so INSERT no metadado)

    Returns:
        dict com phase1_ddl, phase2_dml, warnings, summary, confirmation_token
    """
    source_config = get_connection_config(source_conn_id)
    target_config = get_connection_config(target_conn_id)
    if not source_config:
        raise ValueError("Conexao de origem nao encontrada")
    if not target_config:
        raise ValueError("Conexao de destino nao encontrada")

    source_driver = source_config["driver"]
    target_driver = target_config["driver"]

    source_conn = _get_external_connection(source_config)
    target_conn = _get_external_connection(target_config)
    source_cursor = source_conn.cursor()
    target_cursor = target_conn.cursor()

    try:
        # Carregar dados fisicos do source e target
        source_columns = _get_all_physical_columns_bulk(source_cursor, source_driver)
        source_indexes = _get_physical_indexes(source_cursor, source_driver)
        source_topfield = _get_topfield_data(source_cursor, source_driver)

        target_tables = _get_physical_tables(target_cursor, target_driver)
        target_columns = _get_all_physical_columns_bulk(target_cursor, target_driver)
        target_indexes = _get_physical_indexes(target_cursor, target_driver)

        # Carregar metadados REAIS do source (fidelidade total)
        source_meta = _load_source_metadata(source_cursor, source_driver, company_code, items)

        phase1_ddl = []
        phase2_dml = []
        warnings = []
        integrity_warnings = []
        counts = {"fields": 0, "indexes": 0, "tables": 0, "metadata": 0, "field_diffs": 0, "metadata_diffs": 0}

        # ===== PRE-VALIDACAO: metadado vs fisico nos dois bancos =====
        # Se ha divergencia entre metadado e fisico no MESMO banco,
        # alertar o usuario para rodar a rotina de integridade antes
        _has_field_items = any(
            it.get("type") in ("field", "field_diff") for it in items
        )
        _has_index_items = any(it.get("type") == "index" for it in items)

        if _has_field_items or _has_index_items:
            # Carregar metadados do target tambem para a verificacao
            target_meta = _load_source_metadata(target_cursor, target_driver, company_code, items)

            # Verificar campos: metadado SX3 vs coluna fisica
            for item in items:
                if item.get("type") not in ("field", "field_diff"):
                    continue
                table_alias = item.get("table_alias", "").upper()
                field_name = item.get("field_name", "").upper()
                phys_table = f"{table_alias}{company_code}0".upper()

                # Checar SOURCE: SX3 vs fisico
                sx3_key = f"{table_alias}|{field_name}"
                sx3_src = source_meta.get("sx3", {}).get(sx3_key, {})
                src_col = source_columns.get(phys_table, {}).get(field_name)
                if sx3_src and src_col:
                    _check_meta_vs_physical(
                        sx3_src, src_col, source_driver,
                        table_alias, field_name, phys_table,
                        "SOURCE", integrity_warnings,
                    )

                # Checar TARGET: SX3 vs fisico
                sx3_tgt = target_meta.get("sx3", {}).get(sx3_key, {})
                tgt_col = target_columns.get(phys_table, {}).get(field_name)
                if sx3_tgt and tgt_col:
                    _check_meta_vs_physical(
                        sx3_tgt, tgt_col, target_driver,
                        table_alias, field_name, phys_table,
                        "TARGET", integrity_warnings,
                    )

            # Verificar indices: SIX vs indice fisico
            for item in items:
                if item.get("type") != "index":
                    continue
                indice = item.get("indice", "").upper()
                ordem = item.get("ordem", "").upper()
                phys_table = f"{indice}{company_code}0".upper()
                phys_index = f"{indice}{company_code}0{ordem}".upper()

                six_key = f"{indice}|{ordem}"
                six_src = source_meta.get("six", {}).get(six_key, {})
                if six_src:
                    src_idx = source_indexes.get(phys_table, {}).get(phys_index)
                    if not src_idx:
                        integrity_warnings.append(
                            f"[SOURCE] Indice {phys_index} existe no SIX mas nao existe "
                            f"fisicamente — execute a validacao de integridade no banco de origem"
                        )

                six_tgt = target_meta.get("six", {}).get(six_key, {})
                if six_tgt:
                    tgt_idx = target_indexes.get(phys_table, {}).get(phys_index)
                    if not tgt_idx:
                        integrity_warnings.append(
                            f"[TARGET] Indice {phys_index} existe no SIX mas nao existe "
                            f"fisicamente — execute a validacao de integridade no banco de destino"
                        )

        if integrity_warnings:
            # Avisos de integridade vao no topo dos warnings
            warnings.append(
                "ATENCAO: Foram detectadas divergencias entre metadado e objeto fisico "
                "no mesmo banco. Recomenda-se executar a rotina de Integridade antes de "
                "prosseguir com a equalizacao."
            )
            warnings.extend(integrity_warnings)

        for item in items:
            item_type = item.get("type", "")
            meta_table = item.get("meta_table", "")

            if item_type == "field":
                table_alias = item.get("table_alias", "")
                field_name = item.get("field_name", "")
                # Buscar row real do SX3 no source
                sx3_key = f"{table_alias}|{field_name}".upper()
                sx3_row = source_meta.get("sx3", {}).get(sx3_key, {})
                if not sx3_row:
                    warnings.append(f"SX3 {sx3_key} nao encontrado no source — pulando")
                    continue

                result = _generate_add_field_sql(
                    source_columns,
                    source_topfield,
                    target_driver,
                    target_columns,
                    table_alias,
                    field_name,
                    company_code,
                    sx3_row,
                )
                phase1_ddl.extend(result["ddl"])
                phase2_dml.extend(result["dml"])
                warnings.extend(result["warnings"])
                counts["fields"] += 1

            elif item_type == "field_diff":
                table_alias = item.get("table_alias", "")
                field_name = item.get("field_name", "")
                diff_fields = item.get("diff_fields", [])
                # Buscar row real do SX3 no source
                sx3_key = f"{table_alias}|{field_name}".upper()
                sx3_row = source_meta.get("sx3", {}).get(sx3_key, {})
                if not sx3_row:
                    warnings.append(f"SX3 {sx3_key} nao encontrado no source — pulando")
                    continue
                if not diff_fields:
                    warnings.append(f"SX3 {sx3_key} sem campos diferentes informados — pulando")
                    continue

                result = _generate_update_field_sql(
                    source_columns,
                    source_topfield,
                    target_driver,
                    target_columns,
                    table_alias,
                    field_name,
                    company_code,
                    diff_fields,
                    sx3_row,
                )
                phase1_ddl.extend(result["ddl"])
                phase2_dml.extend(result["dml"])
                warnings.extend(result["warnings"])
                counts["field_diffs"] += 1

            elif item_type == "index":
                indice = item.get("indice", "")
                ordem = item.get("ordem", "")
                # Buscar row real do SIX no source
                six_key = f"{indice}|{ordem}".upper()
                six_row = source_meta.get("six", {}).get(six_key, {})
                if not six_row:
                    warnings.append(f"SIX {six_key} nao encontrado no source — pulando")
                    continue

                result = _generate_add_index_sql(
                    source_indexes,
                    target_driver,
                    target_indexes,
                    indice,
                    ordem,
                    company_code,
                    six_row,
                )
                phase1_ddl.extend(result["ddl"])
                phase2_dml.extend(result["dml"])
                warnings.extend(result["warnings"])
                counts["indexes"] += 1

            elif item_type == "full_table":
                table_alias = item.get("table_alias", "").upper()
                # Buscar rows reais do source
                sx2_row = source_meta.get("sx2", {}).get(table_alias, {})
                sx3_list = source_meta.get("sx3_by_table", {}).get(table_alias, [])
                six_list = source_meta.get("six_by_table", {}).get(table_alias, [])
                if not sx2_row:
                    warnings.append(f"SX2 {table_alias} nao encontrado no source — pulando")
                    continue

                result = _generate_new_table_sql(
                    source_columns,
                    source_indexes,
                    source_topfield,
                    target_driver,
                    table_alias,
                    company_code,
                    sx2_row,
                    sx3_list,
                    six_list,
                )
                phase1_ddl.extend(result["ddl"])
                phase2_dml.extend(result["dml"])
                warnings.extend(result["warnings"])
                counts["tables"] += 1

            elif item_type == "metadata":
                # Metadado puro (SX1, SX5, SX6, SX7, SX9, SXA, SXB, XXA, XAM, XAL)
                item_key = item.get("key", "")
                meta_key = f"{meta_table}|{item_key}".upper()
                meta_row = source_meta.get("other", {}).get(meta_key, {})
                if not meta_row:
                    # Fallback: usar values do frontend (caso tabela nao carregada)
                    meta_row = item.get("values", {})
                if meta_table and meta_row:
                    phys_table = _make_table_name(meta_table, company_code)
                    sql = _build_insert_sql(phys_table, meta_row, target_driver)
                    phase2_dml.append(
                        {
                            "sql": sql,
                            "description": f"INSERT metadado {meta_table}: {item_key}",
                            "phase": 2,
                        }
                    )
                    counts["metadata"] += 1

            elif item_type == "metadata_diff":
                # Metadado existente com atributos diferentes — UPDATE generico
                item_key = item.get("key", "")
                diff_fields = item.get("diff_fields", [])
                meta_key = f"{meta_table}|{item_key}".upper()
                meta_row = source_meta.get("other", {}).get(meta_key, {})
                if not meta_row:
                    warnings.append(f"{meta_table} {item_key} nao encontrado no source — pulando")
                    continue
                if not diff_fields:
                    warnings.append(f"{meta_table} {item_key} sem campos diferentes — pulando")
                    continue

                result = _generate_update_metadata_sql(
                    target_driver,
                    company_code,
                    meta_table,
                    item_key,
                    diff_fields,
                    meta_row,
                )
                phase2_dml.extend(result["dml"])
                warnings.extend(result["warnings"])
                counts["metadata_diffs"] += 1

        # Montar lista combinada para token
        all_statements = phase1_ddl + phase2_dml
        token = _compute_token(all_statements) if all_statements else ""

        return {
            "phase1_ddl": phase1_ddl,
            "phase2_dml": phase2_dml,
            "warnings": warnings,
            "summary": {
                "fields": counts["fields"],
                "field_diffs": counts["field_diffs"],
                "indexes": counts["indexes"],
                "tables": counts["tables"],
                "metadata": counts["metadata"],
                "metadata_diffs": counts["metadata_diffs"],
                "ddl_count": len(phase1_ddl),
                "dml_count": len(phase2_dml),
                "total_statements": len(all_statements),
            },
            "confirmation_token": token,
        }

    finally:
        source_conn.close()
        target_conn.close()


# =========================================================
# GERACAO DE SQL POR CENARIO
# =========================================================


def _generate_add_field_sql(
    source_columns, source_topfield, target_driver, target_columns, table_alias, field_name, company_code, sx3_values
):
    """Gera SQL para adicionar campo faltante (SX3 only_a)."""
    ddl = []
    dml = []
    warnings = []

    phys_table = f"{table_alias}{company_code}0".upper()
    field_upper = field_name.upper()

    # Verificar se campo ja existe no target (evitar duplicata)
    target_cols = target_columns.get(phys_table, {})
    if field_upper in target_cols:
        warnings.append(f"Campo {field_upper} ja existe na tabela {phys_table} do destino — DDL ignorado")
    else:
        # Ler definicao fisica do source
        source_cols = source_columns.get(phys_table, {})
        col_info = source_cols.get(field_upper)
        if col_info:
            col_type = _build_column_def(col_info, target_driver)
            nn_default = _build_not_null_default(col_type)
            table_q = _quote_id(phys_table, target_driver)
            field_q = _quote_id(field_upper, target_driver)
            if target_driver == "mssql":
                sql = f"ALTER TABLE {table_q} ADD {field_q} {col_type} {nn_default}"
            else:
                sql = f"ALTER TABLE {table_q} ADD COLUMN {field_q} {col_type} {nn_default}"
            ddl.append(
                {
                    "sql": sql,
                    "description": f"Adicionar campo {field_upper} na tabela {phys_table}",
                    "phase": 1,
                }
            )
        else:
            warnings.append(
                f"Campo {field_upper} nao encontrado fisicamente no source ({phys_table}) "
                f"— DDL nao gerado, apenas metadado"
            )

    # INSERT SX3
    sx3_table = _make_table_name("SX3", company_code)
    sx3_sql = _build_insert_sql(sx3_table, sx3_values, target_driver)
    dml.append(
        {
            "sql": sx3_sql,
            "description": f"INSERT SX3: {table_alias}.{field_upper}",
            "phase": 2,
        }
    )

    # INSERT TOP_FIELD (se aplicavel)
    x3_tipo = ""
    for k, v in sx3_values.items():
        if k.upper() == "X3_TIPO":
            x3_tipo = str(v).strip().upper()
            break

    if source_topfield and x3_tipo:
        # Buscar TOP_FIELD do source para este campo
        tf_key = (phys_table, field_upper)
        # Tentar com e sem prefixo dbo.
        tf_entry = source_topfield.get(tf_key)
        if not tf_entry:
            tf_key_dbo = (f"dbo.{phys_table}", field_upper)
            tf_entry = source_topfield.get(tf_key_dbo)

        if tf_entry:
            # Clone fiel da origem — usar valores raw originais
            tf_values = {
                "FIELD_TABLE": tf_entry.get("raw_table", phys_table),
                "FIELD_NAME": tf_entry.get("raw_name", field_upper),
                "FIELD_TYPE": tf_entry.get("type", ""),
                "FIELD_PREC": tf_entry.get("prec", ""),
                "FIELD_DEC": tf_entry.get("dec", ""),
            }
            tf_sql = _build_insert_sql("TOP_FIELD", tf_values, target_driver)
            dml.append(
                {
                    "sql": tf_sql,
                    "description": f"INSERT TOP_FIELD: {phys_table}.{field_upper} (type={tf_entry.get('type', '')})",
                    "phase": 2,
                }
            )

    # Check D_E_L_E_T_
    for k, v in sx3_values.items():
        if k.upper() == "D_E_L_E_T_" and str(v).strip() == "*":
            warnings.append(f"Campo {table_alias}.{field_upper} tem D_E_L_E_T_='*' no source")
            break

    return {"ddl": ddl, "dml": dml, "warnings": warnings}


def _build_update_sql(table_name, set_dict, where_dict, driver):
    """Monta UPDATE SQL para campos especificos.

    Args:
        table_name: nome fisico da tabela
        set_dict: {coluna: novo_valor} — colunas a atualizar
        where_dict: {coluna: valor} — clausula WHERE (chave primaria)
        driver: driver do banco destino

    Returns:
        string SQL: UPDATE table SET col=val WHERE col=val AND ...
    """
    table_q = _quote_id(table_name, driver)
    set_parts = []
    for col, val in sorted(set_dict.items()):
        col_q = _quote_id(col.upper(), driver)
        set_parts.append(f"{col_q} = {_quote_value(val)}")
    where_parts = []
    for col, val in sorted(where_dict.items()):
        col_q = _quote_id(col.upper(), driver)
        where_parts.append(f"{col_q} = {_quote_value(val)}")
    return f"UPDATE {table_q} SET {', '.join(set_parts)} WHERE {' AND '.join(where_parts)}"


def _generate_update_metadata_sql(target_driver, company_code, meta_table, key_str, diff_fields, source_row):
    """Gera UPDATE generico para qualquer tabela de metadado (SX1, SX2, SX5, SX6, SX7, SX9, SXA, SXB, SIX, XXA, XAM, XAL).

    Diferente de _generate_update_field_sql (SX3 que pode ter DDL),
    esta funcao gera apenas DML: UPDATE na tabela de metadado com os campos divergentes.

    Args:
        meta_table: prefixo da tabela (SX1, SX2, SX5, etc.)
        key_str: chave do registro (ex: "SA1|01")
        diff_fields: lista de dicts [{field, val_a, val_b}]
        source_row: row completa do source (para extrair valores de chave)
    """
    dml = []
    warnings = []

    phys_table = _make_table_name(meta_table, company_code)
    key_columns = TABLE_KEYS.get(meta_table.upper(), [])

    if not key_columns:
        warnings.append(f"Tabela {meta_table} sem chave primaria definida — UPDATE nao gerado")
        return {"ddl": [], "dml": dml, "warnings": warnings}

    # Montar SET: apenas campos divergentes
    set_dict = {}
    for f in diff_fields:
        fname = f["field"].upper()
        if fname in CONTROL_COLUMNS or fname == "D_E_L_E_T_":
            continue
        set_dict[fname] = f["val_a"]  # val_a = valor do source

    if not set_dict:
        warnings.append(f"{meta_table} {key_str}: apenas colunas de controle diferem — UPDATE nao gerado")
        return {"ddl": [], "dml": dml, "warnings": warnings}

    # Montar WHERE: chave primaria da tabela
    where_dict = {}
    for kc in key_columns:
        where_dict[kc] = _get_field(source_row, kc)

    sql = _build_update_sql(phys_table, set_dict, where_dict, target_driver)
    diff_cols = ", ".join(sorted(set_dict.keys()))
    dml.append(
        {
            "sql": sql,
            "description": f"UPDATE {meta_table}: {key_str} ({diff_cols})",
            "phase": 2,
        }
    )

    return {"ddl": [], "dml": dml, "warnings": warnings}


def _generate_update_field_sql(
    source_columns,
    source_topfield,
    target_driver,
    target_columns,
    table_alias,
    field_name,
    company_code,
    diff_fields,
    sx3_source_row,
):
    """Gera SQL para atualizar campo diferente (SX3 different).

    Diferente de _generate_add_field_sql que trata campos faltantes (INSERT),
    esta funcao trata campos que existem nos dois bancos mas com atributos
    diferentes no metadado SX3. Gera:
    - Fase 1 (DDL): ALTER TABLE ALTER COLUMN se tipo/tamanho fisico mudou
    - Fase 2 (DML): UPDATE SX3 apenas dos campos divergentes + UPDATE TOP_FIELD

    Args:
        diff_fields: lista de dicts [{field, val_a, val_b}] — campos SX3 diferentes
        sx3_source_row: row completa do SX3 no source (para extrair valores)
    """
    ddl = []
    dml = []
    warnings = []

    phys_table = f"{table_alias}{company_code}0".upper()
    field_upper = field_name.upper()

    # Verificar se tipo/tamanho fisico mudou (campos que afetam DDL)
    ddl_fields = {"X3_TIPO", "X3_TAMANHO", "X3_DECIMAL"}
    has_physical_change = any(f["field"].upper() in ddl_fields for f in diff_fields)

    if has_physical_change:
        # Ler definicao fisica do SOURCE e TARGET para comparar
        source_cols = source_columns.get(phys_table, {})
        target_cols = target_columns.get(phys_table, {})
        col_info_source = source_cols.get(field_upper)
        col_info_target = target_cols.get(field_upper)

        if not col_info_source:
            warnings.append(
                f"Campo {field_upper} nao encontrado fisicamente no source ({phys_table}) "
                f"— DDL nao gerado, apenas metadado"
            )
        elif not col_info_target:
            warnings.append(
                f"Campo {field_upper} nao encontrado fisicamente no target ({phys_table}) "
                f"— DDL nao gerado (campo nao existe no destino)"
            )
        else:
            # Comparar definicao fisica: so gera DDL se realmente diferem
            source_type = _build_column_def(col_info_source, target_driver)
            target_type = _build_column_def(col_info_target, target_driver)

            if source_type.upper() == target_type.upper():
                warnings.append(
                    f"Campo {field_upper} em {phys_table}: metadado SX3 diverge mas "
                    f"fisico ja e identico ({source_type}) — DDL ignorado"
                )
            else:
                nn_default = _build_not_null_default(source_type)
                table_q = _quote_id(phys_table, target_driver)
                field_q = _quote_id(field_upper, target_driver)

                if target_driver == "mssql":
                    # MSSQL: ALTER COLUMN nao suporta DEFAULT inline
                    # 1) Dropar default constraint existente (se houver)
                    drop_df = (
                        f"DECLARE @df NVARCHAR(256); "
                        f"SELECT @df = d.name FROM sys.default_constraints d "
                        f"JOIN sys.columns c ON d.parent_column_id = c.column_id "
                        f"AND d.parent_object_id = c.object_id "
                        f"WHERE c.name = '{field_upper}' "
                        f"AND d.parent_object_id = OBJECT_ID('{phys_table}'); "
                        f"IF @df IS NOT NULL EXEC('ALTER TABLE {table_q} DROP CONSTRAINT ' + @df)"
                    )
                    ddl.append({
                        "sql": drop_df,
                        "description": f"Remover default constraint de {field_upper} em {phys_table}",
                        "phase": 1,
                    })
                    # 2) ALTER COLUMN com tipo + NOT NULL (sem DEFAULT)
                    ddl.append({
                        "sql": f"ALTER TABLE {table_q} ALTER COLUMN {field_q} {source_type} NOT NULL",
                        "description": f"Alterar tipo do campo {field_upper} na tabela {phys_table}",
                        "phase": 1,
                    })
                    # 3) Recriar default constraint
                    default_val = _extract_default_value(nn_default)
                    df_name = f"DF_{phys_table}_{field_upper}"
                    ddl.append({
                        "sql": f"ALTER TABLE {table_q} ADD CONSTRAINT [{df_name}] DEFAULT {default_val} FOR {field_q}",
                        "description": f"Recriar default constraint para {field_upper} em {phys_table}",
                        "phase": 1,
                    })
                elif target_driver == "postgresql":
                    # PostgreSQL usa ALTER TYPE + SET NOT NULL + SET DEFAULT separados
                    sql = (
                        f"ALTER TABLE {table_q} ALTER COLUMN {field_q} TYPE {source_type}, "
                        f"ALTER COLUMN {field_q} SET NOT NULL, "
                        f"ALTER COLUMN {field_q} SET DEFAULT {_extract_default_value(nn_default)}"
                    )
                    ddl.append({
                        "sql": sql,
                        "description": f"Alterar tipo do campo {field_upper} na tabela {phys_table}",
                        "phase": 1,
                    })
                else:
                    # Oracle
                    sql = f"ALTER TABLE {table_q} MODIFY ({field_q} {source_type} {nn_default})"
                    ddl.append({
                        "sql": sql,
                        "description": f"Alterar tipo do campo {field_upper} na tabela {phys_table}",
                        "phase": 1,
                    })

    # UPDATE SX3 — apenas campos divergentes
    sx3_table = _make_table_name("SX3", company_code)
    set_dict = {}
    for f in diff_fields:
        fname = f["field"].upper()
        # Ignorar colunas de controle
        if fname in CONTROL_COLUMNS or fname == "D_E_L_E_T_":
            continue
        set_dict[fname] = f["val_a"]  # val_a = valor do source

    if set_dict:
        where_dict = {
            "X3_ARQUIVO": _get_field(sx3_source_row, "X3_ARQUIVO"),
            "X3_CAMPO": _get_field(sx3_source_row, "X3_CAMPO"),
        }
        sx3_sql = _build_update_sql(sx3_table, set_dict, where_dict, target_driver)
        diff_cols = ", ".join(sorted(set_dict.keys()))
        dml.append(
            {
                "sql": sx3_sql,
                "description": f"UPDATE SX3: {table_alias}.{field_upper} ({diff_cols})",
                "phase": 2,
            }
        )

    # UPDATE TOP_FIELD se tipo/tamanho mudou
    if has_physical_change and source_topfield:
        tf_key = (phys_table, field_upper)
        tf_entry = source_topfield.get(tf_key)
        if not tf_entry:
            tf_key_dbo = (f"dbo.{phys_table}", field_upper)
            tf_entry = source_topfield.get(tf_key_dbo)

        if tf_entry:
            tf_set = {
                "FIELD_TYPE": tf_entry.get("type", ""),
                "FIELD_PREC": tf_entry.get("prec", ""),
                "FIELD_DEC": tf_entry.get("dec", ""),
            }
            tf_where = {
                "FIELD_TABLE": tf_entry.get("raw_table", phys_table),
                "FIELD_NAME": tf_entry.get("raw_name", field_upper),
            }
            tf_sql = _build_update_sql("TOP_FIELD", tf_set, tf_where, target_driver)
            dml.append(
                {
                    "sql": tf_sql,
                    "description": f"UPDATE TOP_FIELD: {phys_table}.{field_upper}",
                    "phase": 2,
                }
            )

    return {"ddl": ddl, "dml": dml, "warnings": warnings}


def _extract_default_value(nn_default_clause):
    """Extrai apenas o valor DEFAULT de uma clausula NOT NULL DEFAULT xxx."""
    # Ex: "NOT NULL DEFAULT 0" -> "0"
    # Ex: "NOT NULL DEFAULT '   '" -> "'   '"
    idx = nn_default_clause.upper().find("DEFAULT")
    if idx >= 0:
        return nn_default_clause[idx + 8 :].strip()
    return "' '"


def _generate_add_index_sql(source_indexes, target_driver, target_indexes, indice, ordem, company_code, six_values):
    """Gera SQL para adicionar indice faltante (SIX only_a)."""
    ddl = []
    dml = []
    warnings = []

    indice_upper = indice.upper()
    ordem_upper = ordem.upper()
    phys_table = f"{indice_upper}{company_code}0".upper()
    phys_index = f"{indice_upper}{company_code}0{ordem_upper}".upper()

    # Verificar se indice ja existe no target
    target_table_indexes = target_indexes.get(phys_table, {})
    if phys_index in target_table_indexes:
        warnings.append(f"Indice {phys_index} ja existe no destino — DDL ignorado")
    else:
        # Ler colunas do indice do source
        source_table_indexes = source_indexes.get(phys_table, {})
        source_cols = source_table_indexes.get(phys_index, [])
        if source_cols:
            table_q = _quote_id(phys_table, target_driver)
            index_q = _quote_id(phys_index, target_driver)
            cols_q = ", ".join(_quote_id(c.upper(), target_driver) for c in source_cols)
            sql = f"CREATE INDEX {index_q} ON {table_q} ({cols_q})"
            ddl.append(
                {
                    "sql": sql,
                    "description": f"Criar indice {phys_index} na tabela {phys_table}",
                    "phase": 1,
                }
            )
        else:
            warnings.append(f"Indice {phys_index} nao encontrado fisicamente no source — DDL nao gerado")

    # INSERT SIX
    six_table = _make_table_name("SIX", company_code)
    six_sql = _build_insert_sql(six_table, six_values, target_driver)
    dml.append(
        {
            "sql": six_sql,
            "description": f"INSERT SIX: {indice_upper} ordem {ordem_upper}",
            "phase": 2,
        }
    )

    return {"ddl": ddl, "dml": dml, "warnings": warnings}


def _generate_new_table_sql(
    source_columns,
    source_indexes,
    source_topfield,
    target_driver,
    table_alias,
    company_code,
    sx2_values,
    sx3_list,
    six_list,
):
    """Gera SQL para criar tabela inteira nova (SX2 only_a)."""
    ddl = []
    dml = []
    warnings = []

    alias_upper = table_alias.upper()
    phys_table = f"{alias_upper}{company_code}0".upper()

    # --- CREATE TABLE ---
    source_cols = source_columns.get(phys_table, {})
    if source_cols:
        table_q = _quote_id(phys_table, target_driver)
        col_defs = []
        for col_name in sorted(source_cols.keys()):
            col_upper = col_name.upper()
            col_q = _quote_id(col_upper, target_driver)
            col_type = _build_column_def(source_cols[col_name], target_driver)
            # R_E_C_N_O_ e IDENTITY/serial — tratamento especial
            if col_upper == "R_E_C_N_O_":
                if target_driver == "mssql":
                    col_defs.append(f"    {col_q} INT IDENTITY(1,1) NOT NULL")
                else:
                    col_defs.append(f"    {col_q} SERIAL NOT NULL")
            elif col_upper == "R_E_C_D_E_L_":
                col_defs.append(f"    {col_q} INT NOT NULL DEFAULT 0")
            else:
                nn_default = _build_not_null_default(col_type)
                col_defs.append(f"    {col_q} {col_type} {nn_default}")
        cols_block = ",\n".join(col_defs)
        sql = f"CREATE TABLE {table_q} (\n{cols_block}\n)"
        ddl.append(
            {
                "sql": sql,
                "description": f"Criar tabela {phys_table} ({len(source_cols)} colunas)",
                "phase": 1,
            }
        )
    else:
        warnings.append(f"Tabela {phys_table} nao encontrada fisicamente no source — CREATE TABLE nao gerado")

    # --- CREATE INDEX para cada SIX ---
    for six_row in six_list:
        indice = ""
        ordem = ""
        for k, v in six_row.items():
            ku = k.upper()
            if ku == "INDICE":
                indice = str(v).strip().upper()
            elif ku == "ORDEM":
                ordem = str(v).strip().upper()
        if indice and ordem:
            phys_index = f"{indice}{company_code}0{ordem}".upper()
            source_table_indexes = source_indexes.get(phys_table, {})
            source_idx_cols = source_table_indexes.get(phys_index, [])
            if source_idx_cols:
                table_q = _quote_id(phys_table, target_driver)
                index_q = _quote_id(phys_index, target_driver)
                cols_q = ", ".join(_quote_id(c.upper(), target_driver) for c in source_idx_cols)
                sql = f"CREATE INDEX {index_q} ON {table_q} ({cols_q})"
                ddl.append(
                    {
                        "sql": sql,
                        "description": f"Criar indice {phys_index}",
                        "phase": 1,
                    }
                )

    # --- INSERT SX2 ---
    sx2_table = _make_table_name("SX2", company_code)
    dml.append(
        {
            "sql": _build_insert_sql(sx2_table, sx2_values, target_driver),
            "description": f"INSERT SX2: {alias_upper}",
            "phase": 2,
        }
    )

    # --- INSERT SX3 para cada campo ---
    sx3_table = _make_table_name("SX3", company_code)
    for sx3_row in sx3_list:
        dml.append(
            {
                "sql": _build_insert_sql(sx3_table, sx3_row, target_driver),
                "description": f"INSERT SX3: {alias_upper}.{_get_field(sx3_row, 'X3_CAMPO')}",
                "phase": 2,
            }
        )

    # --- INSERT SIX para cada indice ---
    six_table = _make_table_name("SIX", company_code)
    for six_row in six_list:
        dml.append(
            {
                "sql": _build_insert_sql(six_table, six_row, target_driver),
                "description": f"INSERT SIX: {_get_field(six_row, 'INDICE')} ordem {_get_field(six_row, 'ORDEM')}",
                "phase": 2,
            }
        )

    # --- INSERT TOP_FIELD para campos D/N/M/L ---
    if source_topfield:
        for sx3_row in sx3_list:
            campo = _get_field(sx3_row, "X3_CAMPO").upper()
            if not campo:
                continue
            tf_key = (phys_table, campo)
            tf_entry = source_topfield.get(tf_key)
            if not tf_entry:
                tf_key_dbo = (f"dbo.{phys_table}", campo)
                tf_entry = source_topfield.get(tf_key_dbo)
            if tf_entry:
                tf_values = {
                    "FIELD_TABLE": tf_entry.get("raw_table", phys_table),
                    "FIELD_NAME": tf_entry.get("raw_name", campo),
                    "FIELD_TYPE": tf_entry.get("type", ""),
                    "FIELD_PREC": tf_entry.get("prec", ""),
                    "FIELD_DEC": tf_entry.get("dec", ""),
                }
                dml.append(
                    {
                        "sql": _build_insert_sql("TOP_FIELD", tf_values, target_driver),
                        "description": f"INSERT TOP_FIELD: {phys_table}.{campo}",
                        "phase": 2,
                    }
                )

    return {"ddl": ddl, "dml": dml, "warnings": warnings}


def _get_field(row_dict, field_name):
    """Helper para extrair campo case-insensitive."""
    return str(row_dict.get(field_name, row_dict.get(field_name.lower(), row_dict.get(field_name.upper(), "")))).strip()


# =========================================================
# EXECUCAO
# =========================================================


def execute_equalization(
    target_conn_id, source_conn_id, company_code, sql_statements, confirmation_token, user_id, environment_id
):
    """
    Executa equalizacao em transacao atomica.

    Args:
        sql_statements: lista de dicts com "sql", "description", "phase"
        confirmation_token: hash SHA-256 gerado no preview

    Returns:
        {"success": True, "executed": N, "history_id": N}
        ou
        {"success": False, "error": "msg", "executed_before_error": N}
    """
    start = time.time()

    # Validar token
    expected_token = _compute_token(sql_statements)
    if expected_token != confirmation_token:
        raise ValueError(
            "Token de confirmacao invalido — os SQLs foram alterados apos o preview. "
            "Gere um novo preview antes de executar."
        )

    # Validar conexao target
    target_config = get_connection_config(target_conn_id)
    if not target_config:
        raise ValueError("Conexao de destino nao encontrada")

    # Abrir conexao com escrita
    target_conn = _get_external_connection(target_config, writable=True)
    target_cursor = target_conn.cursor()

    executed = 0
    try:
        # Separar por fase
        phase1 = [s for s in sql_statements if s.get("phase") == 1]
        phase2 = [s for s in sql_statements if s.get("phase") == 2]

        # Phase 1: DDL
        for stmt in phase1:
            logger.info(f"[Equalizer DDL] {stmt['description']}: {stmt['sql'][:100]}...")
            target_cursor.execute(stmt["sql"])
            executed += 1

        # Phase 2: DML
        for stmt in phase2:
            logger.info(f"[Equalizer DML] {stmt['description']}: {stmt['sql'][:100]}...")
            target_cursor.execute(stmt["sql"])
            executed += 1

        # Phase 3: Sinalizar mudança de dicionário no SYSTEM_INFO (Protheus invalida cache dos AppServers)
        phase3_count = 0
        try:
            from datetime import datetime as _dt
            _now = _dt.now()
            _mpi_date  = _now.strftime("%Y%m%d%H%M%S")                                          # 14 chars: YYYYMMDDHHmmss
            _mpi_value = f"{_now.strftime('%Y%m%d%H:%M:%S')}.{_now.microsecond // 1000:03d}"    # 21 chars: YYYYMMDDhh:mm:ss.mmm
            _mpi_key   = f"METADATA_CHANGE_{company_code}"
            _sys_sql   = (
                "UPDATE SYSTEM_INFO "
                "SET MPI_VALUE = %s, MPI_DATE = %s "
                "WHERE MPI_KEY = %s AND D_E_L_E_T_ = ' '"
            )
            target_cursor.execute(_sys_sql, (_mpi_value, _mpi_date, _mpi_key))
            phase3_count = target_cursor.rowcount
            logger.info(f"[Equalizer Phase3] SYSTEM_INFO METADATA_CHANGE_{company_code} atualizado: {_mpi_value}")
        except Exception as _e3:
            logger.warning(f"[Equalizer Phase3] Nao foi possivel atualizar SYSTEM_INFO: {_e3}")

        # COMMIT
        target_conn.commit()

        # Phase 4: TcRefresh via REST — forcar DBAccess a reconhecer campos novos
        refresh_results = _phase4_tcrefresh(target_conn_id, phase1)

        # Determinar status final: sucesso total ou parcial
        phase4_ok = refresh_results.get("success", True)
        # Parcial = DDL+DML commitados com sucesso, mas TcRefresh falhou
        is_partial = not phase4_ok and refresh_results.get("called", False)

        duration_ms = int((time.time() - start) * 1000)

        # Salvar historico
        status = "partial" if is_partial else "success"
        summary = {
            "executed": executed,
            "ddl_count": len(phase1),
            "dml_count": len(phase2),
            "metadata_change": phase3_count > 0,
            "tcrefresh": refresh_results,
            "status": status,
            "duration_ms": duration_ms,
            "source_conn_id": source_conn_id,
            "target_conn_id": target_conn_id,
        }
        details = {
            "statements": sql_statements,
        }
        history_id = save_history(
            environment_id=environment_id,
            operation_type="equalize",
            conn_a_id=source_conn_id,
            conn_b_id=target_conn_id,
            company_code=company_code,
            summary=summary,
            details=details,
            user_id=user_id,
            duration_ms=duration_ms,
        )

        return {
            "success": True,
            "status": status,
            "executed": executed,
            "duration_ms": duration_ms,
            "history_id": history_id,
            "tcrefresh": refresh_results,
        }

    except Exception as e:
        # ROLLBACK
        try:
            target_conn.rollback()
        except Exception:
            pass
        logger.error(f"[Equalizer ERROR] Rollback apos {executed} statements: {e}")
        return {
            "success": False,
            "error": str(e),
            "executed_before_error": executed,
        }

    finally:
        target_conn.close()


# =========================================================
# PHASE 4: TcRefresh via REST do AppServer Protheus
# =========================================================


_ENV_SUFFIX_MAP = {
    "Produção": "PRD",
    "Homologação": "HOM",
    "Desenvolvimento": "DEV",
    "Testes": "TST",
}


def _get_rest_credentials(environment_id):
    """
    Busca credenciais REST do Protheus nas server_variables do BiizHubOps.

    Usa as mesmas variaveis que o runner de pipelines:
        PROTHEUS_USER_<SUFFIX>      (ex: PROTHEUS_USER_PRD)
        PROTHEUS_PASSWORD_<SUFFIX>  (ex: PROTHEUS_PASSWORD_PRD)

    Onde SUFFIX vem do mapa de ambientes (Producao->PRD, Homologacao->HOM, etc).
    Fallback sem sufixo: PROTHEUS_USER / PROTHEUS_PASSWORD.

    Returns:
        tuple (user, password) ou (None, None) se nao encontrado
    """
    from app.database import get_db, release_db_connection

    conn = get_db()
    cursor = conn.cursor()
    try:
        # Buscar nome do ambiente para resolver o sufixo
        env_suffix = ""
        if environment_id:
            cursor.execute("SELECT name FROM environments WHERE id = %s", (environment_id,))
            row = cursor.fetchone()
            if row:
                env_suffix = _ENV_SUFFIX_MAP.get(row["name"], "")

        # Carregar variaveis relevantes
        cursor.execute("SELECT name, value FROM server_variables WHERE name LIKE 'PROTHEUS_USER%' OR name LIKE 'PROTHEUS_PASSWORD%'")
        variables = {r["name"]: r["value"] for r in cursor.fetchall()}

        # Tentar com sufixo primeiro (ex: PROTHEUS_USER_PRD)
        if env_suffix:
            user = variables.get(f"PROTHEUS_USER_{env_suffix}")
            pwd = variables.get(f"PROTHEUS_PASSWORD_{env_suffix}")
            if user and pwd:
                return user, pwd

        # Fallback: sem sufixo
        user = variables.get("PROTHEUS_USER")
        pwd = variables.get("PROTHEUS_PASSWORD")
        return user or None, pwd or None

    except Exception as e:
        logger.warning(f"[Equalizer] Erro ao buscar credenciais REST: {e}")
        return None, None
    finally:
        release_db_connection(conn)


_PHASE4_MAX_RETRIES = 3
_PHASE4_RETRY_DELAY_SECS = 2


def _phase4_tcrefresh(target_conn_id, phase1_stmts):
    """
    Forca o DBAccess a reconhecer campos novos chamando TcRefresh
    via REST no AppServer Protheus.

    Extrai as tabelas alteradas dos DDLs (ALTER TABLE / CREATE TABLE)
    e chama o endpoint ZATUREF no AppServer para cada uma.
    Retry automatico: ate 3 tentativas por tabela com intervalo de 2s.

    Credenciais buscadas das server_variables do BiizHubOps:
        PROTHEUS_USER_<SUFFIX> / PROTHEUS_PASSWORD_<SUFFIX>
        Fallback: PROTHEUS_USER / PROTHEUS_PASSWORD

    Retorno:
        dict com "called", "success", "tables", "errors", "skipped_reason"
    """
    import base64
    import urllib.request
    import urllib.error

    # Extrair tabelas alteradas dos DDLs
    altered_tables = set()
    for stmt in phase1_stmts:
        sql = stmt.get("sql", "").upper()
        # ALTER TABLE [SA1010] ADD ... ou CREATE TABLE [SA1010] ...
        match = re.search(r'(?:ALTER|CREATE)\s+TABLE\s+[\[\"]?(\w+)[\]\"]?', sql)
        if match:
            altered_tables.add(match.group(1))

    if not altered_tables:
        return {"called": False, "success": True, "skipped_reason": "Nenhuma tabela DDL encontrada"}

    # Buscar rest_url da conexao target
    target_config = get_connection_config(target_conn_id)
    if not target_config:
        return {"called": False, "success": False, "skipped_reason": "Conexao target nao encontrada"}

    rest_url = (target_config.get("rest_url") or "").strip()
    if not rest_url:
        return {
            "called": False,
            "success": False,
            "skipped_reason": "REST URL nao configurada na conexao — configure para ativar TcRefresh automatico",
            "tables": list(altered_tables),
        }

    # Buscar credenciais REST das server_variables (com sufixo do ambiente)
    env_id = target_config.get("environment_id")
    rest_user, rest_pass = _get_rest_credentials(env_id)

    _REST_AUTH = ""
    if rest_user and rest_pass:
        _REST_AUTH = "Basic " + base64.b64encode(f"{rest_user}:{rest_pass}".encode()).decode()
    else:
        logger.warning(
            "[Equalizer Phase4] Credenciais REST nao encontradas nas server_variables "
            "(PROTHEUS_USER/PROTHEUS_PASSWORD). Tentando sem autenticacao."
        )

    # Normalizar URL base (remover barra final)
    rest_url = rest_url.rstrip("/")

    results = {"called": True, "success": True, "url": rest_url, "tables": [], "errors": []}

    for table in sorted(altered_tables):
        table_ok = False
        last_error = None

        for attempt in range(1, _PHASE4_MAX_RETRIES + 1):
            try:
                url = f"{rest_url}/ZATUREF"
                payload = json.dumps({"tables": [table]}).encode("utf-8")
                _headers = {"Content-Type": "application/json"}
                if _REST_AUTH:
                    _headers["Authorization"] = _REST_AUTH
                req = urllib.request.Request(
                    url,
                    data=payload,
                    headers=_headers,
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    body = resp.read().decode("utf-8", errors="replace")
                    results["tables"].append({
                        "table": table,
                        "status": resp.status,
                        "response": body[:200],
                        "attempt": attempt,
                    })
                    logger.info(
                        f"[Equalizer Phase4] TcRefresh {table} -> {resp.status} "
                        f"(tentativa {attempt}/{_PHASE4_MAX_RETRIES}): {body[:100]}"
                    )
                    table_ok = True
                    break

            except urllib.error.HTTPError as he:
                err_body = ""
                try:
                    err_body = he.read().decode("utf-8", errors="replace")[:200]
                except Exception:
                    pass
                last_error = {"table": table, "status": he.code, "error": err_body, "attempt": attempt}
                logger.warning(
                    f"[Equalizer Phase4] TcRefresh {table} HTTP {he.code} "
                    f"(tentativa {attempt}/{_PHASE4_MAX_RETRIES}): {err_body}"
                )
            except Exception as e:
                last_error = {"table": table, "error": str(e)[:200], "attempt": attempt}
                logger.warning(
                    f"[Equalizer Phase4] TcRefresh {table} falhou "
                    f"(tentativa {attempt}/{_PHASE4_MAX_RETRIES}): {e}"
                )

            # Aguardar antes do retry (exceto na ultima tentativa)
            if attempt < _PHASE4_MAX_RETRIES:
                time.sleep(_PHASE4_RETRY_DELAY_SECS)

        if not table_ok:
            results["errors"].append(last_error)
            results["success"] = False

    return results
