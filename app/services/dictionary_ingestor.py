"""
Ingestor de Dicionario Protheus.

Importa definicoes de dicionario a partir de arquivo externo (.json ou .md)
e aplica no banco de destino usando o mesmo pipeline do equalizador:
- Fase 1 (DDL): ALTER TABLE / CREATE TABLE / CREATE INDEX
- Fase 2 (DML): INSERT/UPDATE SX2, SX3, SIX, TOP_FIELD, metadados
- Fase 3 (Signal): UPDATE SYSTEM_INFO para invalidar cache do AppServer
- Fase 4 (TcRefresh): REST ZATUREF para refresh do DBAccess

Diferenca para o equalizador: a origem dos dados e um arquivo em vez de banco.
As funcoes de geracao de SQL sao 100% reutilizadas do equalizador.
"""

import hashlib
import json
import logging
import os
import re
import time
import uuid

from app.services.database_browser import get_connection_config, _get_external_connection
from app.services.dictionary_compare import (
    _get_physical_tables,
    _get_all_physical_columns_bulk,
    _get_physical_indexes,
    _get_topfield_data,
    _make_table_name,
    _fetch_all_rows,
    save_history,
    ALWAYS_IGNORE_COLUMNS,
    TABLE_KEYS,
)
from app.services.dictionary_equalizer import (
    _quote_id,
    _quote_value,
    _build_column_def,
    _build_not_null_default,
    _build_insert_sql,
    _compute_token,
    _generate_add_field_sql,
    _generate_add_index_sql,
    _generate_new_table_sql,
    _generate_update_field_sql,
    _generate_update_metadata_sql,
    _get_field,
    _check_meta_vs_physical,
    execute_equalization,
    CONTROL_COLUMNS,
)
from app.services.protheus_metadata_schema import (
    filter_valid_columns,
    get_valid_columns,
    METADATA_SCHEMA,
)

logger = logging.getLogger(__name__)

# Diretorio temporario para arquivos de ingestao enviados via upload
INGEST_UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "ingest_uploads")

# Campos de controle Protheus — nunca devem estar nos valores de metadado importados
_CONTROL_FIELDS = {"R_E_C_N_O_", "R_E_C_D_E_L_", "S_T_A_M_P_", "I_N_S_D_T_"}

# Charset alfanumerico Protheus para X3_ORDEM: 0-9, A-Z (base 36)
_ORDEM_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _next_x3_ordem(current_ordem):
    """Incrementa X3_ORDEM no formato alfanumerico Protheus (base 36, 2 digitos).

    Sequencia: 01 02 ... 09 0A 0B ... 0Z 10 11 ... 99 9A ... 9Z A0 A1 ... ZZ
    """
    if not current_ordem or len(str(current_ordem).strip()) < 2:
        return "01"

    s = str(current_ordem).strip().upper()
    # Converter para valor numerico base-36
    high = _ORDEM_CHARS.index(s[0]) if s[0] in _ORDEM_CHARS else 0
    low = _ORDEM_CHARS.index(s[1]) if s[1] in _ORDEM_CHARS else 0

    # Incrementar
    low += 1
    if low >= 36:
        low = 0
        high += 1

    if high >= 36:
        logger.warning("[Ingestor] X3_ORDEM overflow (apos ZZ), reiniciando em 01")
        return "01"

    return f"{_ORDEM_CHARS[high]}{_ORDEM_CHARS[low]}"


def _get_max_x3_ordem(target_meta, table_alias):
    """Busca o maior X3_ORDEM para uma tabela no metadado do destino."""
    sx3_rows = target_meta.get("sx3_by_table", {}).get(table_alias.upper(), [])
    if not sx3_rows:
        return None

    max_ordem = None
    for row in sx3_rows:
        ordem = str(_get_field(row, "X3_ORDEM")).strip().upper()
        if ordem and (max_ordem is None or ordem > max_ordem):
            max_ordem = ordem

    return max_ordem


# =========================================================
# PARSERS
# =========================================================


def _sanitize_metadata_row(row_dict, table_prefix=None):
    """Remove campos de controle e colunas invalidas de uma row de metadado.

    R_E_C_N_O_ e R_E_C_D_E_L_ sao gerados pelo banco.
    S_T_A_M_P_ e I_N_S_D_T_ sao gerados pelo DBAccess.
    D_E_L_E_T_ e mantido — forcado para espaco se vazio.

    Se table_prefix informado (ex: 'SX3'), filtra colunas que nao existem
    no schema real do Protheus (previne 'Invalid column name').
    """
    if table_prefix:
        filtered, removed = filter_valid_columns(table_prefix, row_dict)
        if removed:
            logger.warning(
                "[Ingestor] Colunas removidas de %s (nao existem no schema): %s",
                table_prefix, ", ".join(removed),
            )
        # Garantir D_E_L_E_T_ como espaco
        if "D_E_L_E_T_" in filtered:
            v = filtered["D_E_L_E_T_"]
            if not v or not str(v).strip():
                filtered["D_E_L_E_T_"] = " "
        return filtered

    # Fallback sem schema: apenas remove campos de controle
    cleaned = {}
    for k, v in row_dict.items():
        key_upper = k.strip().upper() if isinstance(k, str) else k
        if key_upper in _CONTROL_FIELDS:
            continue
        if key_upper == "D_E_L_E_T_":
            cleaned[key_upper] = v if v and str(v).strip() else " "
            continue
        cleaned[key_upper] = v
    return cleaned


def parse_json_file(file_content):
    """Faz parse de arquivo JSON no formato atudic-ingest.

    Args:
        file_content: string ou bytes do conteudo JSON

    Returns:
        dict com metadata (version, source, company_code) e items normalizados

    Raises:
        ValueError: se formato invalido
    """
    if isinstance(file_content, bytes):
        file_content = file_content.decode("utf-8")

    try:
        data = json.loads(file_content)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON invalido: {e}")

    if not isinstance(data, dict):
        raise ValueError("Arquivo JSON deve ser um objeto na raiz")

    # Validar formato
    fmt = data.get("format", "")
    if fmt and fmt != "atudic-ingest":
        raise ValueError(f"Formato '{fmt}' nao reconhecido. Esperado: 'atudic-ingest'")

    items = data.get("items", [])
    if not isinstance(items, list) or not items:
        raise ValueError("Campo 'items' deve ser uma lista nao vazia")

    # Normalizar items
    normalized = []
    warnings = []

    for i, item in enumerate(items):
        item_type = item.get("type", "").strip().lower()
        if not item_type:
            warnings.append(f"Item {i}: campo 'type' ausente — ignorado")
            continue

        if item_type == "field":
            norm = _normalize_field_item(item, i, warnings)
        elif item_type == "field_diff":
            norm = _normalize_field_diff_item(item, i, warnings)
        elif item_type == "index":
            norm = _normalize_index_item(item, i, warnings)
        elif item_type == "full_table":
            norm = _normalize_full_table_item(item, i, warnings)
        elif item_type == "metadata":
            norm = _normalize_metadata_item(item, i, warnings)
        elif item_type == "metadata_diff":
            norm = _normalize_metadata_diff_item(item, i, warnings)
        else:
            warnings.append(f"Item {i}: tipo '{item_type}' nao reconhecido — ignorado")
            continue

        if norm:
            normalized.append(norm)

    if not normalized:
        raise ValueError("Nenhum item valido encontrado no arquivo")

    metadata = {
        "version": data.get("version", "1.0"),
        "format": "atudic-ingest",
        "source_environment": data.get("source_environment", ""),
        "source_driver": data.get("source_driver", ""),
        "exported_at": data.get("exported_at", ""),
        "exported_by": data.get("exported_by", ""),
        "company_code": data.get("company_code", ""),
    }

    return {"metadata": metadata, "items": normalized, "parse_warnings": warnings}


def _normalize_field_item(item, idx, warnings):
    """Normaliza item tipo 'field' do JSON."""
    table_alias = str(item.get("table_alias", "")).strip().upper()
    field_name = str(item.get("field_name", "")).strip().upper()

    if not table_alias or not field_name:
        warnings.append(f"Item {idx} (field): table_alias e field_name obrigatorios — ignorado")
        return None

    sx3 = item.get("sx3", {})
    if not sx3:
        warnings.append(f"Item {idx} (field): bloco 'sx3' ausente — ignorado")
        return None

    sx3_clean = _sanitize_metadata_row(sx3, "SX3")
    # Garantir campos essenciais
    sx3_clean.setdefault("X3_ARQUIVO", table_alias)
    sx3_clean.setdefault("X3_CAMPO", field_name)

    # Defaults para campos de controle Protheus quando vazios/ausentes
    _SX3_FIELD_DEFAULTS = {
        "X3_USADO": "x       x       x       x       x       x       x       x       x       x       x       x       x       x       x x     ",
        "X3_RESERV": "xxxxxx x        ",
        "X3_OBRIGAT": "        ",
    }
    for col, default_val in _SX3_FIELD_DEFAULTS.items():
        current = sx3_clean.get(col)
        if not current or not str(current).strip():
            sx3_clean[col] = default_val

    result = {
        "type": "field",
        "table_alias": table_alias,
        "field_name": field_name,
        "sx3": sx3_clean,
    }

    # Physical info para gerar DDL quando nao ha banco de origem
    physical = item.get("physical", {})
    if physical:
        result["physical"] = physical

    # TOP_FIELD
    top_field = item.get("top_field", {})
    if top_field:
        result["top_field"] = top_field

    return result


def _normalize_field_diff_item(item, idx, warnings):
    """Normaliza item tipo 'field_diff' do JSON."""
    table_alias = str(item.get("table_alias", "")).strip().upper()
    field_name = str(item.get("field_name", "")).strip().upper()
    diff_fields = item.get("diff_fields", [])

    if not table_alias or not field_name:
        warnings.append(f"Item {idx} (field_diff): table_alias e field_name obrigatorios — ignorado")
        return None
    if not diff_fields:
        warnings.append(f"Item {idx} (field_diff): diff_fields vazio — ignorado")
        return None

    sx3 = item.get("sx3", {})
    if not sx3:
        warnings.append(f"Item {idx} (field_diff): bloco 'sx3' ausente — ignorado")
        return None

    sx3_clean = _sanitize_metadata_row(sx3, "SX3")

    return {
        "type": "field_diff",
        "table_alias": table_alias,
        "field_name": field_name,
        "diff_fields": diff_fields,
        "sx3": sx3_clean,
        "physical": item.get("physical", {}),
        "top_field": item.get("top_field", {}),
    }


def _normalize_index_item(item, idx, warnings):
    """Normaliza item tipo 'index' do JSON."""
    indice = str(item.get("indice", "")).strip().upper()
    ordem = str(item.get("ordem", "")).strip().upper()

    if not indice or not ordem:
        warnings.append(f"Item {idx} (index): indice e ordem obrigatorios — ignorado")
        return None

    six = item.get("six", {})
    if not six:
        warnings.append(f"Item {idx} (index): bloco 'six' ausente — ignorado")
        return None

    six_clean = _sanitize_metadata_row(six, "SIX")
    six_clean.setdefault("INDICE", indice)
    six_clean.setdefault("ORDEM", ordem)

    return {
        "type": "index",
        "indice": indice,
        "ordem": ordem,
        "six": six_clean,
        "physical": item.get("physical", {}),
    }


def _normalize_full_table_item(item, idx, warnings):
    """Normaliza item tipo 'full_table' do JSON."""
    table_alias = str(item.get("table_alias", "")).strip().upper()

    if not table_alias:
        warnings.append(f"Item {idx} (full_table): table_alias obrigatorio — ignorado")
        return None

    sx2 = item.get("sx2", {})
    if not sx2:
        warnings.append(f"Item {idx} (full_table): bloco 'sx2' ausente — ignorado")
        return None

    fields = item.get("fields", [])
    indexes = item.get("indexes", [])

    if not fields:
        warnings.append(f"Item {idx} (full_table): lista 'fields' vazia — tabela sem campos")

    sx2_clean = _sanitize_metadata_row(sx2, "SX2")
    sx2_clean.setdefault("X2_CHAVE", table_alias)

    # Normalizar campos
    norm_fields = []
    for f in fields:
        sx3 = f.get("sx3", {})
        if sx3:
            norm_fields.append({
                "sx3": _sanitize_metadata_row(sx3, "SX3"),
                "top_field": f.get("top_field", {}),
            })

    # Normalizar indices
    norm_indexes = []
    for ix in indexes:
        six = ix.get("six", {})
        if six:
            norm_indexes.append({
                "six": _sanitize_metadata_row(six, "SIX"),
                "physical_columns": ix.get("physical_columns", []),
            })

    return {
        "type": "full_table",
        "table_alias": table_alias,
        "sx2": sx2_clean,
        "fields": norm_fields,
        "indexes": norm_indexes,
        "physical": item.get("physical", {}),
    }


def _normalize_metadata_item(item, idx, warnings):
    """Normaliza item tipo 'metadata' do JSON."""
    meta_table = str(item.get("meta_table", "")).strip().upper()
    key = item.get("key", "")
    values = item.get("values", {})

    if not meta_table:
        warnings.append(f"Item {idx} (metadata): meta_table obrigatorio — ignorado")
        return None
    if not values:
        warnings.append(f"Item {idx} (metadata): values vazio — ignorado")
        return None

    return {
        "type": "metadata",
        "meta_table": meta_table,
        "key": key,
        "values": _sanitize_metadata_row(values, meta_table),
    }


def _normalize_metadata_diff_item(item, idx, warnings):
    """Normaliza item tipo 'metadata_diff' do JSON."""
    meta_table = str(item.get("meta_table", "")).strip().upper()
    key = item.get("key", "")
    diff_fields = item.get("diff_fields", [])
    values = item.get("values", {})

    if not meta_table:
        warnings.append(f"Item {idx} (metadata_diff): meta_table obrigatorio — ignorado")
        return None
    if not diff_fields:
        warnings.append(f"Item {idx} (metadata_diff): diff_fields vazio — ignorado")
        return None
    if not values:
        warnings.append(f"Item {idx} (metadata_diff): values ausente — ignorado")
        return None

    return {
        "type": "metadata_diff",
        "meta_table": meta_table,
        "key": key,
        "diff_fields": diff_fields,
        "values": _sanitize_metadata_row(values, meta_table),
    }


# =========================================================
# PARSER MARKDOWN
# =========================================================


def parse_markdown_file(file_content):
    """Faz parse de arquivo Markdown no formato atudic-ingest.

    Extrai blocos de definicao de campo, indice, tabela e metadado
    a partir de headers e tabelas Markdown.

    Args:
        file_content: string ou bytes do conteudo MD

    Returns:
        dict com metadata, items e parse_warnings
    """
    if isinstance(file_content, bytes):
        file_content = file_content.decode("utf-8")

    lines = file_content.split("\n")
    metadata = {
        "version": "1.0",
        "format": "atudic-ingest",
        "source_environment": "",
        "source_driver": "",
        "exported_at": "",
        "exported_by": "",
        "company_code": "",
    }
    items = []
    warnings = []

    # Extrair metadata do cabecalho (linhas podem comecar com '- ')
    for line in lines[:20]:
        line_stripped = re.sub(r"^[-*]\s*", "", line.strip())
        m = re.match(r"\*{0,2}Ambiente de origem:?\*{0,2}\s*(.*)", line_stripped, re.IGNORECASE)
        if m:
            metadata["source_environment"] = m.group(1).strip()
            continue
        m = re.match(r"\*{0,2}Driver:?\*{0,2}\s*(.*)", line_stripped, re.IGNORECASE)
        if m:
            metadata["source_driver"] = m.group(1).strip()
            continue
        m = re.match(r"\*{0,2}Empresa:?\*{0,2}\s*(.*)", line_stripped, re.IGNORECASE)
        if m:
            metadata["company_code"] = m.group(1).strip()
            continue
        m = re.match(r"\*{0,2}Exportado em:?\*{0,2}\s*(.*)", line_stripped, re.IGNORECASE)
        if m:
            metadata["exported_at"] = m.group(1).strip()
            continue
        m = re.match(r"\*{0,2}Exportado por:?\*{0,2}\s*(.*)", line_stripped, re.IGNORECASE)
        if m:
            metadata["exported_by"] = m.group(1).strip()
            continue

    # Identificar blocos por headers ##
    current_block_type = None
    current_block_header = ""
    current_section = None
    current_table_data = {}
    block_items = []

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Detectar header de bloco ## (Campo, Indice, Tabela, Metadado)
        block_match = re.match(r"^##\s+(Campo|Indice|Índice|Tabela Completa|Tabela|Metadado):\s*(.*)", line, re.IGNORECASE)
        if block_match:
            # Salvar bloco anterior
            if current_block_type:
                _flush_md_block(current_block_type, current_block_header, block_items, items, warnings)
            block_type_raw = block_match.group(1).strip().lower()
            if block_type_raw in ("campo",):
                current_block_type = "field"
            elif block_type_raw in ("indice", "índice"):
                current_block_type = "index"
            elif block_type_raw in ("tabela completa", "tabela"):
                current_block_type = "full_table"
            elif block_type_raw in ("metadado",):
                current_block_type = "metadata"
            current_block_header = block_match.group(2).strip()
            block_items = []
            current_section = None
            i += 1
            continue

        # Detectar sub-secao ### dentro de um bloco
        section_match = re.match(r"^###\s+(.*)", line)
        if section_match and current_block_type:
            current_section = section_match.group(1).strip().lower()
            i += 1
            continue

        # Detectar tabela Markdown | Campo | Valor |
        if line.startswith("|") and current_block_type:
            # Parsear tabela markdown
            table_rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                row = lines[i].strip()
                cells = [c.strip() for c in row.split("|")[1:-1]]  # remove primeira e ultima vazia
                if cells and not all(c.replace("-", "").strip() == "" for c in cells):
                    table_rows.append(cells)
                i += 1

            if len(table_rows) >= 1:
                block_items.append({
                    "section": current_section or "",
                    "table_rows": table_rows,
                })
            continue

        # Detectar lista com - **Colunas:** ...
        list_match = re.match(r"^-\s+\*{0,2}Colunas:?\*{0,2}\s*(.*)", line, re.IGNORECASE)
        if list_match and current_block_type:
            cols_str = list_match.group(1).strip()
            cols = [c.strip() for c in cols_str.split(",") if c.strip()]
            block_items.append({
                "section": current_section or "",
                "columns_list": cols,
            })

        i += 1

    # Flush ultimo bloco
    if current_block_type:
        _flush_md_block(current_block_type, current_block_header, block_items, items, warnings)

    if not items:
        raise ValueError("Nenhum item valido encontrado no arquivo Markdown")

    return {"metadata": metadata, "items": items, "parse_warnings": warnings}


def _flush_md_block(block_type, header, block_items, items_out, warnings):
    """Converte um bloco Markdown parseado em item normalizado."""
    if block_type == "field":
        _flush_md_field(header, block_items, items_out, warnings)
    elif block_type == "index":
        _flush_md_index(header, block_items, items_out, warnings)
    elif block_type == "full_table":
        _flush_md_full_table(header, block_items, items_out, warnings)
    elif block_type == "metadata":
        _flush_md_metadata(header, block_items, items_out, warnings)


def _parse_md_table_to_dict(table_rows):
    """Converte rows de tabela MD (2 colunas key|value) em dict.

    Pula a primeira row se for header generico (ex: Campo SX3 | Valor).
    """
    result = {}
    _header_values = {"valor", "value", "atributo", "campo", "campo sx3", "campo six", "campo sx2"}

    for i, row in enumerate(table_rows):
        if len(row) >= 2:
            key = row[0].strip()
            value = row[1].strip()
            # Pular header: primeira row com valor generico
            if i == 0 and (key.lower() in _header_values or value.lower() in _header_values):
                continue
            if value.lower() == "(espaco)" or value.lower() == "(espaço)":
                value = " "
            if key:
                result[key] = value
    return result


def _flush_md_field(header, block_items, items_out, warnings):
    """Processa bloco Campo do Markdown."""
    # Header: "SA1.A1_XNOVO" ou "A1_XNOVO"
    parts = header.split(".")
    if len(parts) == 2:
        table_alias = parts[0].strip().upper()
        field_name = parts[1].strip().upper()
    else:
        warnings.append(f"Campo '{header}': formato esperado 'ALIAS.CAMPO' — ignorado")
        return

    sx3 = {}
    top_field = {}
    physical = {}

    for item in block_items:
        section = item.get("section", "")
        table_rows = item.get("table_rows", [])

        if "sx3" in section or "metadado sx3" in section:
            sx3 = _parse_md_table_to_dict(table_rows)
        elif "top_field" in section:
            top_field = _parse_md_table_to_dict(table_rows)
        elif "fisica" in section or "physical" in section or "estrutura" in section:
            physical = _parse_md_table_to_dict(table_rows)

    if not sx3:
        warnings.append(f"Campo {table_alias}.{field_name}: SX3 nao encontrado no MD — ignorado")
        return

    sx3_clean = _sanitize_metadata_row(sx3, "SX3")
    sx3_clean.setdefault("X3_ARQUIVO", table_alias)
    sx3_clean.setdefault("X3_CAMPO", field_name)

    result = {
        "type": "field",
        "table_alias": table_alias,
        "field_name": field_name,
        "sx3": sx3_clean,
    }
    if physical:
        result["physical"] = physical
    if top_field:
        result["top_field"] = top_field

    items_out.append(result)


def _flush_md_index(header, block_items, items_out, warnings):
    """Processa bloco Indice do Markdown."""
    # Header: "SA1 Ordem F" ou "SA1 F"
    m = re.match(r"(\w+)\s+(?:Ordem\s+)?(\w+)", header, re.IGNORECASE)
    if not m:
        warnings.append(f"Indice '{header}': formato esperado 'ALIAS Ordem X' — ignorado")
        return

    indice = m.group(1).strip().upper()
    ordem = m.group(2).strip().upper()

    six = {}
    physical_columns = []

    for item in block_items:
        section = item.get("section", "")
        table_rows = item.get("table_rows", [])
        cols_list = item.get("columns_list", [])

        if "six" in section or "metadado" in section:
            six = _parse_md_table_to_dict(table_rows)
        if cols_list:
            physical_columns = cols_list

    if not six:
        warnings.append(f"Indice {indice} Ordem {ordem}: SIX nao encontrado no MD — ignorado")
        return

    six_clean = _sanitize_metadata_row(six, "SIX")
    six_clean.setdefault("INDICE", indice)
    six_clean.setdefault("ORDEM", ordem)

    result = {
        "type": "index",
        "indice": indice,
        "ordem": ordem,
        "six": six_clean,
    }
    if physical_columns:
        result["physical"] = {"columns": physical_columns}

    items_out.append(result)


def _flush_md_full_table(header, block_items, items_out, warnings):
    """Processa bloco Tabela Completa do Markdown."""
    table_alias = header.strip().upper()
    if not table_alias:
        warnings.append("Tabela Completa: alias vazio — ignorado")
        return

    sx2 = {}
    fields = []
    indexes = []

    for item in block_items:
        section = item.get("section", "")
        table_rows = item.get("table_rows", [])

        if "sx2" in section:
            sx2 = _parse_md_table_to_dict(table_rows)
        elif "campos" in section or "sx3" in section:
            # Tabelas completas no MD podem ter campos inline
            sx3 = _parse_md_table_to_dict(table_rows)
            if sx3:
                fields.append({"sx3": _sanitize_metadata_row(sx3, "SX3")})
        elif "indices" in section or "six" in section:
            six = _parse_md_table_to_dict(table_rows)
            if six:
                indexes.append({"six": _sanitize_metadata_row(six, "SIX")})

    if not sx2:
        warnings.append(f"Tabela {table_alias}: SX2 nao encontrado no MD — ignorado")
        return

    sx2_clean = _sanitize_metadata_row(sx2, "SX2")
    sx2_clean.setdefault("X2_CHAVE", table_alias)

    items_out.append({
        "type": "full_table",
        "table_alias": table_alias,
        "sx2": sx2_clean,
        "fields": fields,
        "indexes": indexes,
        "physical": {},
    })


def _flush_md_metadata(header, block_items, items_out, warnings):
    """Processa bloco Metadado do Markdown."""
    # Header: "SX7 — SA1|A1_COD|01" ou "SX5 — 01|ZZ|01"
    parts = re.split(r"\s*[—-]\s*", header, maxsplit=1)
    if len(parts) == 2:
        meta_table = parts[0].strip().upper()
        key = parts[1].strip()
    else:
        meta_table = header.strip().upper()
        key = ""

    values = {}
    for item in block_items:
        table_rows = item.get("table_rows", [])
        values.update(_parse_md_table_to_dict(table_rows))

    if not values:
        warnings.append(f"Metadado {meta_table}: valores nao encontrados no MD — ignorado")
        return

    items_out.append({
        "type": "metadata",
        "meta_table": meta_table,
        "key": key,
        "values": _sanitize_metadata_row(values, meta_table),
    })


# =========================================================
# PARSER DISPATCHER
# =========================================================


def parse_ingest_file(file_content, filename=""):
    """Detecta formato e faz parse do arquivo de ingestao.

    Args:
        file_content: string ou bytes
        filename: nome do arquivo (para deteccao por extensao)

    Returns:
        dict com metadata, items, parse_warnings
    """
    if isinstance(file_content, bytes):
        content_str = file_content.decode("utf-8", errors="replace")
    else:
        content_str = file_content

    ext = os.path.splitext(filename)[1].lower() if filename else ""

    # Detectar formato
    if ext == ".json":
        return parse_json_file(content_str)
    elif ext in (".md", ".markdown"):
        return parse_markdown_file(content_str)
    else:
        # Auto-detect: tenta JSON primeiro, depois MD
        content_stripped = content_str.strip()
        if content_stripped.startswith("{") or content_stripped.startswith("["):
            try:
                return parse_json_file(content_str)
            except ValueError:
                pass
        return parse_markdown_file(content_str)


def save_uploaded_file(file_content, filename):
    """Salva arquivo enviado via upload para processamento posterior.

    Returns:
        caminho absoluto do arquivo salvo
    """
    os.makedirs(INGEST_UPLOAD_DIR, exist_ok=True)

    # Gerar nome unico para evitar colisoes
    safe_name = re.sub(r"[^\w.\-]", "_", filename)
    unique_name = f"{uuid.uuid4().hex[:8]}_{safe_name}"
    filepath = os.path.join(INGEST_UPLOAD_DIR, unique_name)

    if isinstance(file_content, str):
        file_content = file_content.encode("utf-8")

    with open(filepath, "wb") as f:
        f.write(file_content)

    return filepath


# =========================================================
# PREVIEW — Gera SQL sem executar
# =========================================================


def _build_physical_from_sx3(sx3_row, company_code):
    """Constroi informacao fisica a partir dos metadados SX3 quando nao ha banco de origem.

    Monta um col_info compativel com INFORMATION_SCHEMA para que as funcoes
    do equalizador possam gerar DDL correto.
    """
    x3_tipo = str(sx3_row.get("X3_TIPO", "C")).strip().upper()
    x3_tamanho = sx3_row.get("X3_TAMANHO", 10)
    x3_decimal = sx3_row.get("X3_DECIMAL", 0)

    try:
        x3_tamanho = int(x3_tamanho)
    except (ValueError, TypeError):
        x3_tamanho = 10
    try:
        x3_decimal = int(x3_decimal)
    except (ValueError, TypeError):
        x3_decimal = 0

    if x3_tipo == "C":
        return {
            "DATA_TYPE": "VARCHAR",
            "CHARACTER_MAXIMUM_LENGTH": x3_tamanho,
            "NUMERIC_PRECISION": None,
            "NUMERIC_SCALE": None,
        }
    elif x3_tipo == "N":
        return {
            "DATA_TYPE": "NUMERIC",
            "CHARACTER_MAXIMUM_LENGTH": None,
            "NUMERIC_PRECISION": x3_tamanho,
            "NUMERIC_SCALE": x3_decimal,
        }
    elif x3_tipo == "D":
        return {
            "DATA_TYPE": "VARCHAR",
            "CHARACTER_MAXIMUM_LENGTH": 8,
            "NUMERIC_PRECISION": None,
            "NUMERIC_SCALE": None,
        }
    elif x3_tipo == "L":
        return {
            "DATA_TYPE": "VARCHAR",
            "CHARACTER_MAXIMUM_LENGTH": 1,
            "NUMERIC_PRECISION": None,
            "NUMERIC_SCALE": None,
        }
    elif x3_tipo == "M":
        return {
            "DATA_TYPE": "VARCHAR",
            "CHARACTER_MAXIMUM_LENGTH": 10,
            "NUMERIC_PRECISION": None,
            "NUMERIC_SCALE": None,
        }
    else:
        return {
            "DATA_TYPE": "VARCHAR",
            "CHARACTER_MAXIMUM_LENGTH": x3_tamanho,
            "NUMERIC_PRECISION": None,
            "NUMERIC_SCALE": None,
        }


def _detect_topfield_table_format(target_topfield, phys_table):
    """Detecta o formato de FIELD_TABLE usado no target (com ou sem 'dbo.' prefix).

    O Protheus no MSSQL normalmente grava 'dbo.SA1990' no TOP_FIELD,
    mas em alguns ambientes pode ser apenas 'SA1990'.
    Esta funcao verifica o target e retorna o formato correto.
    """
    if not target_topfield:
        return phys_table

    # Tentar encontrar qualquer entrada para esta tabela
    # Primeiro com dbo.
    for key in target_topfield:
        table_part = key[0] if isinstance(key, tuple) else ""
        if table_part.upper() == phys_table.upper():
            # Encontrou sem dbo. — usar sem prefixo
            raw = target_topfield[key].get("raw_table", "")
            return raw if raw else phys_table

    # Tentar com dbo. prefix
    for key in target_topfield:
        table_part = key[0] if isinstance(key, tuple) else ""
        if table_part.upper() == f"DBO.{phys_table}".upper():
            raw = target_topfield[key].get("raw_table", "")
            return raw.replace(raw.split(".")[-1], phys_table) if raw else f"dbo.{phys_table}"

    # Heuristica: verificar se a maioria das entradas usa dbo.
    dbo_count = 0
    total = 0
    for key in target_topfield:
        table_part = key[0] if isinstance(key, tuple) else ""
        if table_part:
            total += 1
            if "." in table_part:
                dbo_count += 1
        if total >= 20:
            break

    if total > 0 and dbo_count > total / 2:
        return f"dbo.{phys_table}"

    return phys_table


def _build_topfield_values(item, phys_table, field_name, target_topfield, target_driver):
    """Constroi valores para INSERT TOP_FIELD com formato correto.

    Regras (alinhadas com o equalizador):
    1. Apenas tipos N, D, L, M geram TOP_FIELD — tipo C NUNCA gera
    2. FIELD_TABLE: sempre derivado do phys_table do destino (nunca do arquivo)
       — detecta se o target usa prefixo 'dbo.' e replica
    3. FIELD_NAME: sempre o nome do campo no destino
    4. FIELD_TYPE/PREC/DEC: do arquivo se disponivel, senao derivado do SX3
    """
    sx3 = item.get("sx3", {})
    x3_tipo = str(sx3.get("X3_TIPO", "")).strip().upper()

    # Regra do equalizador: tipo C nao tem TOP_FIELD
    if x3_tipo not in ("N", "D", "L", "M"):
        return None

    top_field = item.get("top_field", {})

    # Determinar formato correto de FIELD_TABLE no target
    tf_table = _detect_topfield_table_format(target_topfield, phys_table)

    if top_field:
        return {
            "FIELD_TABLE": tf_table,
            "FIELD_NAME": field_name,  # Sempre o nome real, nao do arquivo
            "FIELD_TYPE": top_field.get("FIELD_TYPE", x3_tipo),
            "FIELD_PREC": top_field.get("FIELD_PREC", ""),
            "FIELD_DEC": top_field.get("FIELD_DEC", ""),
        }

    # Sem top_field no arquivo — derivar do SX3
    col_info = _build_physical_from_sx3(sx3, "")
    return {
        "FIELD_TABLE": tf_table,
        "FIELD_NAME": field_name,
        "FIELD_TYPE": x3_tipo,
        "FIELD_PREC": str(col_info.get("CHARACTER_MAXIMUM_LENGTH") or col_info.get("NUMERIC_PRECISION") or ""),
        "FIELD_DEC": str(col_info.get("NUMERIC_SCALE") or "0"),
    }


def generate_ingest_preview(target_conn_id, company_code, parsed_data):
    """
    Gera preview de SQL para ingestao sem executar.

    Reutiliza as funcoes de geracao de SQL do equalizador, mas a origem
    dos dados vem do arquivo importado em vez de um banco de dados.

    Args:
        target_conn_id: ID da conexao de destino
        company_code: codigo da empresa Protheus (ex: '01')
        parsed_data: resultado de parse_ingest_file()

    Returns:
        dict com phase1_ddl, phase2_dml, warnings, summary, confirmation_token, file_metadata
    """
    target_config = get_connection_config(target_conn_id)
    if not target_config:
        raise ValueError("Conexao de destino nao encontrada")

    target_driver = target_config["driver"]

    target_conn = _get_external_connection(target_config)
    target_cursor = target_conn.cursor()

    try:
        # Carregar estado fisico do target para validacao de duplicatas
        target_columns = _get_all_physical_columns_bulk(target_cursor, target_driver)
        target_indexes = _get_physical_indexes(target_cursor, target_driver)
        target_topfield = _get_topfield_data(target_cursor, target_driver)

        # Carregar metadados existentes do target para validacao
        items = parsed_data["items"]
        target_meta = _load_target_metadata(target_cursor, target_driver, company_code, items)

        phase1_ddl = []
        phase2_dml = []
        warnings = list(parsed_data.get("parse_warnings", []))
        counts = {
            "fields": 0, "field_diffs": 0, "indexes": 0,
            "tables": 0, "metadata": 0, "metadata_diffs": 0,
            "skipped_duplicates": 0,
        }

        # Tracker de X3_ORDEM por tabela para auto-incremento no batch
        _ordem_tracker = {}

        for item in items:
            item_type = item.get("type", "")

            if item_type == "field":
                result = _ingest_field(item, target_driver, target_columns, target_topfield, target_meta, company_code, warnings, _ordem_tracker)
                if result:
                    phase1_ddl.extend(result["ddl"])
                    phase2_dml.extend(result["dml"])
                    counts["fields"] += 1
                else:
                    counts["skipped_duplicates"] += 1

            elif item_type == "field_diff":
                result = _ingest_field_diff(item, target_driver, target_columns, target_topfield, target_meta, company_code, warnings)
                if result:
                    phase1_ddl.extend(result.get("ddl", []))
                    phase2_dml.extend(result.get("dml", []))
                    counts["field_diffs"] += 1

            elif item_type == "index":
                result = _ingest_index(item, target_driver, target_indexes, target_meta, company_code, warnings)
                if result:
                    phase1_ddl.extend(result["ddl"])
                    phase2_dml.extend(result["dml"])
                    counts["indexes"] += 1
                else:
                    counts["skipped_duplicates"] += 1

            elif item_type == "full_table":
                result = _ingest_full_table(item, target_driver, target_columns, target_indexes, target_topfield, target_meta, company_code, warnings)
                if result:
                    phase1_ddl.extend(result["ddl"])
                    phase2_dml.extend(result["dml"])
                    counts["tables"] += 1

            elif item_type == "metadata":
                result = _ingest_metadata(item, target_driver, target_meta, company_code, warnings)
                if result:
                    phase2_dml.extend(result["dml"])
                    counts["metadata"] += 1
                else:
                    counts["skipped_duplicates"] += 1

            elif item_type == "metadata_diff":
                result = _ingest_metadata_diff(item, target_driver, target_meta, company_code, warnings)
                if result:
                    phase2_dml.extend(result["dml"])
                    counts["metadata_diffs"] += 1

        # Token de confirmacao
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
                "skipped_duplicates": counts["skipped_duplicates"],
                "ddl_count": len(phase1_ddl),
                "dml_count": len(phase2_dml),
                "total_statements": len(all_statements),
            },
            "confirmation_token": token,
            "file_metadata": parsed_data.get("metadata", {}),
        }

    finally:
        target_conn.close()


# =========================================================
# GERACAO DE SQL POR TIPO DE ITEM (com validacao de duplicatas)
# =========================================================


def _load_target_metadata(cursor, driver, company_code, items):
    """Carrega metadados existentes do target para validacao de duplicatas.

    Usa a mesma estrutura do _load_source_metadata do equalizador.
    """
    result = {"sx2": {}, "sx3": {}, "sx3_by_table": {}, "six": {}, "six_by_table": {}, "other": {}}

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
        elif t in ("metadata", "metadata_diff"):
            mt = item.get("meta_table", "").upper()
            if mt:
                other_tables.add(mt)

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

    if needs_sx3:
        sx3_table = _make_table_name("SX3", company_code)
        try:
            rows = _fetch_all_rows(cursor, driver, sx3_table)
            for row in rows:
                arquivo = _get_field(row, "X3_ARQUIVO").upper()
                campo = _get_field(row, "X3_CAMPO").upper()
                # Ignorar deletados
                delet = _get_field(row, "D_E_L_E_T_")
                if delet == "*":
                    continue
                if arquivo and campo:
                    key = f"{arquivo}|{campo}"
                    result["sx3"][key] = row
                    result["sx3_by_table"].setdefault(arquivo, []).append(row)
        except Exception:
            pass

    if needs_six:
        six_table = _make_table_name("SIX", company_code)
        try:
            rows = _fetch_all_rows(cursor, driver, six_table)
            for row in rows:
                indice = _get_field(row, "INDICE").upper()
                ordem = _get_field(row, "ORDEM").upper()
                delet = _get_field(row, "D_E_L_E_T_")
                if delet == "*":
                    continue
                if indice and ordem:
                    key = f"{indice}|{ordem}"
                    result["six"][key] = row
                    result["six_by_table"].setdefault(indice, []).append(row)
        except Exception:
            pass

    for mt in other_tables:
        table_name = _make_table_name(mt, company_code)
        key_columns = TABLE_KEYS.get(mt, [])
        try:
            rows = _fetch_all_rows(cursor, driver, table_name)
            for row in rows:
                delet = _get_field(row, "D_E_L_E_T_")
                if delet == "*":
                    continue
                key_parts = [_get_field(row, kc) for kc in key_columns]
                full_key = f"{mt}|{'|'.join(key_parts)}".upper()
                result["other"][full_key] = row
        except Exception:
            pass

    return result


def _ingest_field(item, target_driver, target_columns, target_topfield, target_meta, company_code, warnings, ordem_tracker=None):
    """Gera SQL para campo individual importado de arquivo.

    Validacoes:
    1. Verifica se campo ja existe no SX3 do target (duplicata de metadado)
    2. Verifica se coluna ja existe fisicamente no target
    3. Gera DDL + DML apenas se nao existir
    4. Auto-incrementa X3_ORDEM a partir do maior valor no destino
    """
    table_alias = item["table_alias"]
    field_name = item["field_name"]
    sx3_values = item["sx3"]

    # X3_CAMPO e a fonte da verdade para o nome do campo no SX3
    sx3_campo = str(sx3_values.get("X3_CAMPO", field_name)).strip().upper()

    # Avisar se field_name e X3_CAMPO divergem (possivel erro no arquivo)
    if sx3_campo != field_name.strip().upper():
        warnings.append(
            f"Campo {table_alias}: field_name='{field_name}' difere de X3_CAMPO='{sx3_campo}' "
            f"— usando X3_CAMPO como referencia para metadado e DDL"
        )
        # Sincronizar: usar X3_CAMPO como nome real do campo
        field_name = sx3_campo
        sx3_values["X3_CAMPO"] = sx3_campo

    # Auto-incrementar X3_ORDEM: busca o maior do destino e incrementa
    if ordem_tracker is not None:
        alias_upper = table_alias.upper()
        if alias_upper not in ordem_tracker:
            # Primeira vez para esta tabela — buscar max do destino
            ordem_tracker[alias_upper] = _get_max_x3_ordem(target_meta, alias_upper)

        next_ordem = _next_x3_ordem(ordem_tracker[alias_upper])
        sx3_values["X3_ORDEM"] = next_ordem
        ordem_tracker[alias_upper] = next_ordem
        logger.info("[Ingestor] X3_ORDEM auto-incrementado para %s.%s: %s", table_alias, field_name, next_ordem)

    phys_table = f"{table_alias}{company_code}0".upper()

    # Verificar duplicata no metadado SX3 — checar por X3_CAMPO (valor real do INSERT)
    sx3_meta = target_meta.get("sx3", {})
    sx3_key = f"{table_alias}|{sx3_campo}".upper()
    if sx3_key in sx3_meta:
        warnings.append(f"Campo {table_alias}.{sx3_campo}: ja existe no SX3 do destino — ignorado (use Equalizador para atualizar)")
        return None

    ddl = []
    dml = []

    # Verificar se coluna ja existe fisicamente (usar sx3_campo como nome real)
    target_cols = target_columns.get(phys_table, {})
    if sx3_campo in target_cols:
        warnings.append(f"Campo {sx3_campo} ja existe fisicamente na tabela {phys_table} — DDL ignorado, apenas metadado")
    else:
        # Gerar DDL: montar col_info a partir do arquivo ou do SX3
        physical = item.get("physical", {})
        if physical and physical.get("data_type") or physical.get("DATA_TYPE"):
            col_info = {
                "DATA_TYPE": physical.get("data_type", physical.get("DATA_TYPE", "VARCHAR")),
                "CHARACTER_MAXIMUM_LENGTH": physical.get("character_maximum_length", physical.get("CHARACTER_MAXIMUM_LENGTH")),
                "NUMERIC_PRECISION": physical.get("numeric_precision", physical.get("NUMERIC_PRECISION")),
                "NUMERIC_SCALE": physical.get("numeric_scale", physical.get("NUMERIC_SCALE")),
            }
        else:
            col_info = _build_physical_from_sx3(sx3_values, company_code)

        col_type = _build_column_def(col_info, target_driver)
        nn_default = _build_not_null_default(col_type)
        table_q = _quote_id(phys_table, target_driver)
        field_q = _quote_id(field_name, target_driver)

        if target_driver == "mssql":
            sql = f"ALTER TABLE {table_q} ADD {field_q} {col_type} {nn_default}"
        else:
            sql = f"ALTER TABLE {table_q} ADD COLUMN {field_q} {col_type} {nn_default}"

        ddl.append({
            "sql": sql,
            "description": f"Adicionar campo {field_name} na tabela {phys_table} (ingest)",
            "phase": 1,
        })

    # INSERT SX3
    sx3_table = _make_table_name("SX3", company_code)
    sx3_sql = _build_insert_sql(sx3_table, sx3_values, target_driver)
    dml.append({
        "sql": sx3_sql,
        "description": f"INSERT SX3: {table_alias}.{field_name} (ingest)",
        "phase": 2,
    })

    # INSERT TOP_FIELD — derivar FIELD_TABLE/FIELD_NAME do destino (nunca do arquivo)
    tf_values = _build_topfield_values(item, phys_table, field_name, target_topfield, target_driver)
    if tf_values:
        tf_sql = _build_insert_sql("TOP_FIELD", tf_values, target_driver)
        dml.append({
            "sql": tf_sql,
            "description": f"INSERT TOP_FIELD: {tf_values['FIELD_TABLE']}.{field_name} (ingest)",
            "phase": 2,
        })

    # Check D_E_L_E_T_
    d = str(sx3_values.get("D_E_L_E_T_", "")).strip()
    if d == "*":
        warnings.append(f"Campo {table_alias}.{field_name}: D_E_L_E_T_='*' no arquivo — registro marcado como deletado")

    return {"ddl": ddl, "dml": dml}


def _ingest_field_diff(item, target_driver, target_columns, target_topfield, target_meta, company_code, warnings):
    """Gera SQL para atualizacao de campo existente importado de arquivo."""
    table_alias = item["table_alias"]
    field_name = item["field_name"]
    diff_fields = item["diff_fields"]
    sx3_values = item["sx3"]

    # Verificar se campo existe no target
    sx3_key = f"{table_alias}|{field_name}".upper()
    if sx3_key not in target_meta.get("sx3", {}):
        warnings.append(f"Campo {table_alias}.{field_name}: nao existe no SX3 do destino — use tipo 'field' para adicionar")
        return None

    phys_table = f"{table_alias}{company_code}0".upper()

    # Montar source_columns fake a partir do physical/sx3 do arquivo
    source_columns = {}
    physical = item.get("physical", {})
    if physical:
        col_info = {
            "DATA_TYPE": physical.get("data_type", physical.get("DATA_TYPE", "VARCHAR")),
            "CHARACTER_MAXIMUM_LENGTH": physical.get("character_maximum_length", physical.get("CHARACTER_MAXIMUM_LENGTH")),
            "NUMERIC_PRECISION": physical.get("numeric_precision", physical.get("NUMERIC_PRECISION")),
            "NUMERIC_SCALE": physical.get("numeric_scale", physical.get("NUMERIC_SCALE")),
        }
    else:
        col_info = _build_physical_from_sx3(sx3_values, company_code)
    source_columns[phys_table] = {field_name: col_info}

    # Montar source_topfield fake — com formato correto do target
    source_topfield = {}
    top_field = item.get("top_field", {})
    if top_field:
        tf_table = _detect_topfield_table_format(target_topfield, phys_table)
        source_topfield[(phys_table, field_name)] = {
            "raw_table": tf_table,
            "raw_name": field_name,
            "type": top_field.get("FIELD_TYPE", ""),
            "prec": str(top_field.get("FIELD_PREC", "")),
            "dec": str(top_field.get("FIELD_DEC", "")),
        }

    result = _generate_update_field_sql(
        source_columns, source_topfield, target_driver, target_columns,
        table_alias, field_name, company_code, diff_fields, sx3_values,
    )

    # Anotar como ingest na descricao
    for stmt in result.get("ddl", []) + result.get("dml", []):
        if not stmt["description"].endswith("(ingest)"):
            stmt["description"] += " (ingest)"

    warnings.extend(result.get("warnings", []))
    return result


def _ingest_index(item, target_driver, target_indexes, target_meta, company_code, warnings):
    """Gera SQL para indice importado de arquivo."""
    indice = item["indice"]
    ordem = item["ordem"]
    six_values = item["six"]

    phys_table = f"{indice}{company_code}0".upper()
    phys_index = f"{indice}{company_code}0{ordem}".upper()

    # Verificar duplicata no metadado SIX
    six_key = f"{indice}|{ordem}".upper()
    if six_key in target_meta.get("six", {}):
        warnings.append(f"Indice {indice} Ordem {ordem}: ja existe no SIX do destino — ignorado")
        return None

    ddl = []
    dml = []

    # Verificar se indice ja existe fisicamente
    target_table_indexes = target_indexes.get(phys_table, {})
    if phys_index in target_table_indexes:
        warnings.append(f"Indice {phys_index} ja existe fisicamente no destino — DDL ignorado, apenas metadado")
    else:
        # Obter colunas do indice: do physical ou da CHAVE do SIX
        physical = item.get("physical", {})
        index_columns = physical.get("columns", [])

        if not index_columns:
            # Tentar extrair da CHAVE do SIX: "A1_FILIAL+A1_XNOVO"
            chave = str(six_values.get("CHAVE", "")).strip()
            if chave:
                index_columns = [c.strip().upper() for c in chave.split("+") if c.strip()]

        if index_columns:
            table_q = _quote_id(phys_table, target_driver)
            index_q = _quote_id(phys_index, target_driver)
            cols_q = ", ".join(_quote_id(c.upper(), target_driver) for c in index_columns)
            sql = f"CREATE INDEX {index_q} ON {table_q} ({cols_q})"
            ddl.append({
                "sql": sql,
                "description": f"Criar indice {phys_index} na tabela {phys_table} (ingest)",
                "phase": 1,
            })
        else:
            warnings.append(f"Indice {phys_index}: sem colunas — DDL nao gerado, apenas metadado")

    # INSERT SIX
    six_table = _make_table_name("SIX", company_code)
    six_sql = _build_insert_sql(six_table, six_values, target_driver)
    dml.append({
        "sql": six_sql,
        "description": f"INSERT SIX: {indice} ordem {ordem} (ingest)",
        "phase": 2,
    })

    return {"ddl": ddl, "dml": dml}


def _ingest_full_table(item, target_driver, target_columns, target_indexes, target_topfield, target_meta, company_code, warnings):
    """Gera SQL para tabela completa importada de arquivo."""
    table_alias = item["table_alias"]
    sx2_values = item["sx2"]
    fields = item.get("fields", [])
    indexes = item.get("indexes", [])

    phys_table = f"{table_alias}{company_code}0".upper()

    # Verificar se tabela ja existe no SX2
    if table_alias in target_meta.get("sx2", {}):
        warnings.append(f"Tabela {table_alias}: ja existe no SX2 do destino — ignorada (use Equalizador para atualizar)")
        return None

    ddl = []
    dml = []

    # --- CREATE TABLE ---
    physical = item.get("physical", {})
    physical_columns = physical.get("columns", [])

    if phys_table in target_columns:
        warnings.append(f"Tabela {phys_table} ja existe fisicamente no destino — CREATE TABLE ignorado, apenas metadados")
    else:
        col_defs = []
        # Adicionar R_E_C_N_O_ e R_E_C_D_E_L_ (colunas de controle Protheus)
        recno_q = _quote_id("R_E_C_N_O_", target_driver)
        recdel_q = _quote_id("R_E_C_D_E_L_", target_driver)
        delet_q = _quote_id("D_E_L_E_T_", target_driver)

        if target_driver == "mssql":
            col_defs.append(f"    {recno_q} INT IDENTITY(1,1) NOT NULL")
        else:
            col_defs.append(f"    {recno_q} SERIAL NOT NULL")
        col_defs.append(f"    {recdel_q} INT NOT NULL DEFAULT 0")
        col_defs.append(f"    {delet_q} VARCHAR(1) NOT NULL DEFAULT ' '")

        # Adicionar D_E_L_E_T_ e colunas de filial
        # Adicionar campos do SX3
        for f in fields:
            sx3 = f.get("sx3", {})
            campo = str(sx3.get("X3_CAMPO", "")).strip().upper()
            if not campo or campo in ("R_E_C_N_O_", "R_E_C_D_E_L_", "D_E_L_E_T_"):
                continue

            col_info = _build_physical_from_sx3(sx3, company_code)
            col_type = _build_column_def(col_info, target_driver)
            nn_default = _build_not_null_default(col_type)
            col_q = _quote_id(campo, target_driver)
            col_defs.append(f"    {col_q} {col_type} {nn_default}")

        if col_defs:
            table_q = _quote_id(phys_table, target_driver)
            cols_block = ",\n".join(col_defs)
            sql = f"CREATE TABLE {table_q} (\n{cols_block}\n)"
            ddl.append({
                "sql": sql,
                "description": f"Criar tabela {phys_table} ({len(col_defs)} colunas) (ingest)",
                "phase": 1,
            })

    # --- CREATE INDEX para cada indice ---
    for ix in indexes:
        six = ix.get("six", {})
        indice = str(six.get("INDICE", table_alias)).strip().upper()
        ordem = str(six.get("ORDEM", "")).strip().upper()
        if not ordem:
            continue

        phys_index = f"{indice}{company_code}0{ordem}".upper()
        phys_idx_table = f"{indice}{company_code}0".upper()

        # Obter colunas
        index_columns = ix.get("physical_columns", [])
        if not index_columns:
            chave = str(six.get("CHAVE", "")).strip()
            if chave:
                index_columns = [c.strip().upper() for c in chave.split("+") if c.strip()]

        if index_columns:
            table_q = _quote_id(phys_idx_table, target_driver)
            index_q = _quote_id(phys_index, target_driver)
            cols_q = ", ".join(_quote_id(c.upper(), target_driver) for c in index_columns)
            sql = f"CREATE INDEX {index_q} ON {table_q} ({cols_q})"
            ddl.append({
                "sql": sql,
                "description": f"Criar indice {phys_index} (ingest)",
                "phase": 1,
            })

    # --- INSERT SX2 ---
    sx2_table = _make_table_name("SX2", company_code)
    dml.append({
        "sql": _build_insert_sql(sx2_table, sx2_values, target_driver),
        "description": f"INSERT SX2: {table_alias} (ingest)",
        "phase": 2,
    })

    # --- INSERT SX3 para cada campo ---
    sx3_table = _make_table_name("SX3", company_code)
    for f in fields:
        sx3 = f.get("sx3", {})
        if sx3:
            dml.append({
                "sql": _build_insert_sql(sx3_table, sx3, target_driver),
                "description": f"INSERT SX3: {table_alias}.{sx3.get('X3_CAMPO', '?')} (ingest)",
                "phase": 2,
            })

    # --- INSERT SIX para cada indice ---
    six_table = _make_table_name("SIX", company_code)
    for ix in indexes:
        six = ix.get("six", {})
        if six:
            dml.append({
                "sql": _build_insert_sql(six_table, six, target_driver),
                "description": f"INSERT SIX: {six.get('INDICE', '?')} ordem {six.get('ORDEM', '?')} (ingest)",
                "phase": 2,
            })

    # --- INSERT TOP_FIELD para campos que precisam ---
    for f in fields:
        sx3 = f.get("sx3", {})
        campo = str(sx3.get("X3_CAMPO", "")).strip().upper()
        if not campo:
            continue

        # Montar item fake para _build_topfield_values
        fake_item = {"top_field": f.get("top_field", {}), "sx3": sx3}
        tf_values = _build_topfield_values(fake_item, phys_table, campo, target_topfield, target_driver)
        if tf_values:
            dml.append({
                "sql": _build_insert_sql("TOP_FIELD", tf_values, target_driver),
                "description": f"INSERT TOP_FIELD: {tf_values['FIELD_TABLE']}.{campo} (ingest)",
                "phase": 2,
            })

    return {"ddl": ddl, "dml": dml}


def _ingest_metadata(item, target_driver, target_meta, company_code, warnings):
    """Gera SQL para metadado generico importado de arquivo."""
    meta_table = item["meta_table"]
    key = item.get("key", "")
    values = item["values"]

    # Verificar duplicata
    full_key = f"{meta_table}|{key}".upper()
    if full_key in target_meta.get("other", {}):
        warnings.append(f"Metadado {meta_table} chave '{key}': ja existe no destino — ignorado")
        return None

    # Para SX3/SIX/SX2, verificar nas chaves especificas
    if meta_table == "SX3":
        arquivo = _get_field(values, "X3_ARQUIVO")
        campo = _get_field(values, "X3_CAMPO")
        sx3_key = f"{arquivo}|{campo}".upper()
        if sx3_key in target_meta.get("sx3", {}):
            warnings.append(f"SX3 {sx3_key}: ja existe no destino — ignorado")
            return None
    elif meta_table == "SIX":
        indice = _get_field(values, "INDICE")
        ordem = _get_field(values, "ORDEM")
        six_key = f"{indice}|{ordem}".upper()
        if six_key in target_meta.get("six", {}):
            warnings.append(f"SIX {six_key}: ja existe no destino — ignorado")
            return None
    elif meta_table == "SX2":
        alias = _get_field(values, "X2_CHAVE")
        if alias.upper() in target_meta.get("sx2", {}):
            warnings.append(f"SX2 {alias}: ja existe no destino — ignorado")
            return None

    phys_table = _make_table_name(meta_table, company_code)
    sql = _build_insert_sql(phys_table, values, target_driver)

    return {
        "dml": [{
            "sql": sql,
            "description": f"INSERT {meta_table}: {key} (ingest)",
            "phase": 2,
        }],
    }


def _ingest_metadata_diff(item, target_driver, target_meta, company_code, warnings):
    """Gera SQL para atualizacao de metadado existente importado de arquivo."""
    meta_table = item["meta_table"]
    key = item.get("key", "")
    diff_fields = item["diff_fields"]
    values = item["values"]

    result = _generate_update_metadata_sql(
        target_driver, company_code, meta_table, key, diff_fields, values,
    )

    # Anotar como ingest
    for stmt in result.get("dml", []):
        if not stmt["description"].endswith("(ingest)"):
            stmt["description"] += " (ingest)"

    warnings.extend(result.get("warnings", []))
    return result


# =========================================================
# EXECUCAO — Reutiliza execute_equalization do equalizador
# =========================================================


def execute_ingestion(target_conn_id, company_code, sql_statements, confirmation_token, user_id, environment_id, file_metadata=None):
    """
    Executa ingestao — delega para execute_equalization com operation_type='ingest'.

    O pipeline de execucao e identico ao do equalizador:
    - Fase 1 (DDL) + Fase 2 (DML) em transacao atomica
    - Fase 3 (SYSTEM_INFO signal)
    - Fase 4 (TcRefresh via REST)

    A unica diferenca e o operation_type salvo no historico.
    """
    start = time.time()

    # Reutilizar execute_equalization passando source_conn_id = target_conn_id
    # (nao ha source real — o arquivo ja foi processado no preview)
    result = execute_equalization(
        target_conn_id=target_conn_id,
        source_conn_id=target_conn_id,  # mesmo conn — sem source real
        company_code=company_code,
        sql_statements=sql_statements,
        confirmation_token=confirmation_token,
        user_id=user_id,
        environment_id=environment_id,
    )

    # Atualizar historico: trocar operation_type de 'equalize' para 'ingest'
    if result.get("history_id"):
        try:
            from app.database import get_db, release_db_connection
            conn = get_db()
            cursor = conn.cursor()
            # Atualizar operation_type e incluir file_metadata no summary
            update_data = {"operation_type": "ingest"}
            if file_metadata:
                update_data["file_metadata"] = file_metadata

            cursor.execute(
                "UPDATE dictionary_history SET operation_type = %s WHERE id = %s",
                ("ingest", result["history_id"]),
            )

            # Atualizar summary com file_metadata
            if file_metadata:
                cursor.execute(
                    "UPDATE dictionary_history SET summary = summary || %s::jsonb WHERE id = %s",
                    (json.dumps({"file_metadata": file_metadata}), result["history_id"]),
                )

            conn.commit()
            release_db_connection(conn)
        except Exception as e:
            logger.warning(f"[Ingestor] Falha ao atualizar historico: {e}")

    return result
