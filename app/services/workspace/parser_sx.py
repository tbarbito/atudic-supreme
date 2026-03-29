# -*- coding: utf-8 -*-
"""Origem: ExtraiRPO (Joni) — Parser de CSVs SX Protheus."""

import csv
import re
from pathlib import Path
from typing import List
import chardet

csv.field_size_limit(10_000_000)  # 10MB — some SX fields are very large


def _find_file_ci(directory: Path, filename: str) -> Path:
    """Busca arquivo case-insensitive (modo offline CSV). Retorna Path ou None."""
    exact = directory / filename
    if exact.exists():
        return exact
    lower = filename.lower()
    try:
        for f in directory.iterdir():
            if f.name.lower() == lower:
                return f
    except Exception:
        pass
    return None


def _detect_encoding(file_path: Path) -> str:
    raw = file_path.read_bytes()[:4096]  # Only scan first 4KB
    # Check for BOM (UTF-8-BOM)
    if raw[:3] == b'\xef\xbb\xbf':
        return "utf-8-sig"
    result = chardet.detect(raw)
    return result["encoding"] or "cp1252"


def _detect_delimiter(file_path: Path, encoding: str) -> str:
    with open(file_path, "r", encoding=encoding, errors="replace") as f:
        first_line = f.readline()
    if ";" in first_line:
        return ";"
    return ","


def _is_custom_table(codigo: str) -> bool:
    if re.match(r"^SZ[0-9A-Z]$", codigo):
        return True
    if re.match(r"^Q[A-Z][0-9A-Z]$", codigo):
        return True
    # Also detect Z-prefixed tables (Z1, Z2, ZA, etc.)
    if re.match(r"^Z[0-9A-Z][0-9A-Z]?$", codigo):
        return True
    return False


def _is_custom_field(campo: str) -> bool:
    parts = campo.split("_")
    if len(parts) >= 2 and parts[1].startswith("X"):
        return True
    return False


def _sanitize_text(text: str) -> str:
    """Remove surrogate characters and other invalid Unicode that SQLite can't handle."""
    # Remove surrogate pairs (U+D800 to U+DFFF)
    return text.encode("utf-8", errors="replace").decode("utf-8", errors="replace")


def _read_csv(file_path: Path) -> list[dict]:
    encoding = _detect_encoding(file_path)
    delimiter = _detect_delimiter(file_path, encoding)
    with open(file_path, "r", encoding=encoding, errors="replace") as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        rows = []
        for row in reader:
            # Sanitize all string values to remove invalid Unicode; treat None as empty
            clean = {k: _sanitize_text(v) if isinstance(v, str) else (v or "") for k, v in row.items()}
            rows.append(clean)
        return rows


def _safe_int(value: str) -> int:
    """Safely convert a string to int, handling empty/invalid values."""
    try:
        return int(value.strip().strip('"') or 0)
    except (ValueError, AttributeError):
        return 0


def parse_sx2(file_path: Path) -> List[dict]:
    rows = _read_csv(file_path)
    result = []
    for row in rows:
        codigo = row.get("X2_CHAVE", "").strip()
        if not codigo:
            continue
        result.append({
            "codigo": codigo,
            "nome": row.get("X2_NOME", "").strip(),
            "modo": row.get("X2_MODO", "").strip(),
            "custom": 1 if _is_custom_table(codigo) else 0,
        })
    return result


def parse_sx3(file_path: Path) -> List[dict]:
    """Parse SX3 (Fields/Campos). Extracts field metadata including F3, CBOX, validations."""
    rows = _read_csv(file_path)
    result = []
    for row in rows:
        campo = row.get("X3_CAMPO", "").strip()
        if not campo:
            continue
        # Robust obrigatorio parsing
        # X3_OBRIGAT is a context mask: 'x' or 'xxxx' means required,
        # '' means not required. Legacy values: 'S', 'SIM', '1', '.T.'
        obrig_raw = row.get("X3_OBRIGAT", "").strip().strip('"').strip()
        obrigatorio = 1 if (obrig_raw.lower().startswith("x") or obrig_raw.upper() in ("S", "SIM", "1", ".T.")) else 0
        # Proprietario for better custom detection
        proprietario = row.get("X3_PROPRI", "").strip().strip('"')
        is_custom = 1 if _is_custom_field(campo) else 0
        # If proprietario is explicitly not "S" (standard), mark as custom
        if proprietario and proprietario != "S":
            is_custom = 1
        result.append({
            "tabela": row.get("X3_ARQUIVO", "").strip(),
            "campo": campo,
            "tipo": row.get("X3_TIPO", "").strip(),
            "tamanho": _safe_int(row.get("X3_TAMANHO", "0")),
            "decimal": _safe_int(row.get("X3_DECIMAL", "0")),
            "titulo": row.get("X3_TITULO", "").strip(),
            "descricao": row.get("X3_DESCRIC", "").strip(),
            "validacao": row.get("X3_VALID", "").strip(),
            "inicializador": row.get("X3_RELACAO", "").strip(),
            "obrigatorio": obrigatorio,
            "custom": is_custom,
            # New fields
            "f3": row.get("X3_F3", "").strip(),
            "cbox": row.get("X3_CBOX", "").strip(),
            "vlduser": row.get("X3_VLDUSER", "").strip(),
            "when_expr": row.get("X3_WHEN", "").strip(),
            "proprietario": proprietario,
            "browse": row.get("X3_BROWSE", "").strip(),
            "trigger_flag": row.get("X3_TRIGGER", "").strip(),
            "visual": row.get("X3_VISUAL", "").strip(),
            "context": row.get("X3_CONTEXT", "").strip(),
            "folder": row.get("X3_FOLDER", "").strip(),
        })
    return result


def parse_six(file_path: Path) -> List[dict]:
    """Parse SIX (Indices). Note: SIX columns have NO prefix (INDICE, ORDEM, CHAVE, etc.)."""
    rows = _read_csv(file_path)
    result = []
    for row in rows:
        # SIX uses columns WITHOUT X6_ prefix
        tabela = row.get("INDICE", "").strip()
        ordem = row.get("ORDEM", "").strip()
        if not tabela or not ordem:
            continue
        proprietario = row.get("PROPRI", "").strip()
        result.append({
            "tabela": tabela,
            "ordem": ordem,
            "chave": row.get("CHAVE", "").strip(),
            "descricao": row.get("DESCRICAO", "").strip(),
            "proprietario": proprietario,
            "f3": row.get("F3", "").strip(),
            "nickname": row.get("NICKNAME", "").strip(),
            "showpesq": row.get("SHOWPESQ", "").strip(),
            "custom": 1 if proprietario and proprietario != "S" else 0,
        })
    return result


def parse_sx7(file_path: Path) -> List[dict]:
    """Parse SX7 (Triggers/Gatilhos). Extracts full trigger info including condition and owner."""
    rows = _read_csv(file_path)
    result = []
    for row in rows:
        campo_origem = row.get("X7_CAMPO", "").strip()
        if not campo_origem:
            continue
        campo_destino = row.get("X7_CDOMIN", "").strip()
        proprietario = row.get("X7_PROPRI", "").strip()
        is_custom = 1 if _is_custom_field(campo_destino) else 0
        if proprietario and proprietario != "S":
            is_custom = 1
        result.append({
            "campo_origem": campo_origem,
            "sequencia": row.get("X7_SEQUENC", "").strip(),
            "campo_destino": campo_destino,
            "regra": row.get("X7_REGRA", "").strip(),
            "tipo": row.get("X7_TIPO", "").strip(),
            "tabela": row.get("X7_ALIAS", "").strip() or row.get("X7_ARQUIVO", "").strip(),
            "condicao": row.get("X7_CONDIC", "").strip(),
            "proprietario": proprietario,
            "seek": row.get("X7_SEEK", "").strip(),
            "alias": row.get("X7_ALIAS", "").strip(),
            "ordem": row.get("X7_ORDEM", "").strip(),
            "chave": row.get("X7_CHAVE", "").strip(),
            "custom": is_custom,
        })
    return result


def parse_sx1(file_path: Path) -> List[dict]:
    rows = _read_csv(file_path)
    result = []
    for row in rows:
        grupo = row.get("X1_GRUPO", "").strip()
        ordem = row.get("X1_ORDEM", "").strip()
        if not grupo or not ordem:
            continue
        result.append({
            "grupo": grupo,
            "ordem": ordem,
            "pergunta": row.get("X1_PERGUNT", "").strip(),
            "variavel": row.get("X1_VARIAVL", "").strip(),
            "tipo": row.get("X1_TIPO", "").strip(),
            "tamanho": _safe_int(row.get("X1_TAMANHO", "0")),
            "decimal": _safe_int(row.get("X1_DECIMAL", "0")),
            "f3": row.get("X1_F3", "").strip(),
            "validacao": row.get("X1_VALID", "").strip(),
            "conteudo_padrao": row.get("X1_DEF01", "").strip(),
        })
    return result


def parse_sx5(file_path: Path) -> List[dict]:
    rows = _read_csv(file_path)
    result = []
    for row in rows:
        tabela = row.get("X5_TABELA", "").strip()
        chave = row.get("X5_CHAVE", "").strip()
        if not tabela or not chave:
            continue
        result.append({
            "filial": row.get("X5_FILIAL", "").strip(),
            "tabela": tabela,
            "chave": chave,
            "descricao": row.get("X5_DESCRI", "").strip(),
            "custom": 1 if tabela.startswith("Z") or tabela.startswith("X") else 0,
        })
    return result


def parse_sx6(file_path: Path) -> List[dict]:
    """Parse SX6 (Parameters/MV_). Note: SX6 is parameters, NOT indices."""
    rows = _read_csv(file_path)
    result = []
    for row in rows:
        variavel = row.get("X6_VAR", "").strip()
        if not variavel:
            continue
        descricao = (row.get("X6_DESCRIC", "").strip() + " " + row.get("X6_DESC1", "").strip()).strip()
        proprietario = row.get("X6_PROPRI", "").strip()
        result.append({
            "filial": row.get("X6_FIL", "").strip(),
            "variavel": variavel,
            "tipo": row.get("X6_TIPO", "").strip(),
            "descricao": descricao,
            "conteudo": row.get("X6_CONTEUD", "").strip(),
            "proprietario": proprietario,
            "custom": 1 if proprietario != "S" else 0,
        })
    return result


def parse_sx9(file_path: Path) -> List[dict]:
    rows = _read_csv(file_path)
    result = []
    for row in rows:
        tabela_origem = row.get("X9_DOM", "").strip()
        tabela_destino = row.get("X9_CDOM", "").strip()
        if not tabela_origem or not tabela_destino:
            continue
        proprietario = row.get("X9_PROPRI", "").strip()
        result.append({
            "tabela_origem": tabela_origem,
            "identificador": row.get("X9_IDENT", "").strip(),
            "tabela_destino": tabela_destino,
            "expressao_origem": row.get("X9_EXPDOM", "").strip(),
            "expressao_destino": row.get("X9_EXPCDOM", "").strip(),
            "proprietario": proprietario,
            "condicao_sql": row.get("X9_CONDSQL", "").strip(),
            "custom": 1 if proprietario != "S" else 0,
        })
    return result


def parse_sxa(file_path: Path) -> List[dict]:
    rows = _read_csv(file_path)
    result = []
    for row in rows:
        alias = row.get("XA_ALIAS", "").strip()
        ordem = row.get("XA_ORDEM", "").strip()
        if not alias or not ordem:
            continue
        result.append({
            "alias": alias,
            "ordem": ordem,
            "descricao": row.get("XA_DESCRIC", "").strip(),
            "proprietario": row.get("XA_PROPRI", "").strip(),
            "agrupamento": row.get("XA_AGRUP", "").strip(),
        })
    return result


def parse_sxb(file_path: Path) -> List[dict]:
    rows = _read_csv(file_path)
    result = []
    for row in rows:
        alias = row.get("XB_ALIAS", "").strip()
        sequencia = row.get("XB_SEQ", "").strip()
        if not alias or not sequencia:
            continue
        result.append({
            "alias": alias,
            "tipo": row.get("XB_TIPO", "").strip(),
            "sequencia": sequencia,
            "coluna": row.get("XB_COLUNA", "").strip(),
            "descricao": row.get("XB_DESCRI", "").strip(),
            "conteudo": row.get("XB_CONTEM", "").strip(),
        })
    return result


# ---------------------------------------------------------------------------
# mpmenu CSV parser (no headers, semicolon sep, utf-8-sig)
# ---------------------------------------------------------------------------

_MPMENU_MENU_COLS = [
    "M_ID", "M_NAME", "M_VERSION", "M_NUMITENS", "M_HASH",
    "M_VISIBLE", "M_ARQMENU", "D_E_L_E_T_", "M_ORDER", "_pad",
]
_MPMENU_ITEM_COLS = [
    "I_ID_MENU", "I_ID", "I_FATHER", "I_ORDER", "I_ID_FUNC",
    "I_VISIBLE", "I_TYPE", "I_ACCELERATOR", "I_BITMAP", "I_ENABLED",
    "I_TOOLTIP", "I_UUID", "I_SHORTCUT", "I_INFOBAR",
    "_pad1", "_pad2", "D_E_L_E_T_", "I_NEWORDER", "_pad3",
]
_MPMENU_FUNC_COLS = [
    "F_ID", "F_FUNCTION", "F_TYPE", "D_E_L_E_T_", "F_ORDER", "_pad",
]
_MPMENU_I18N_COLS = [
    "N_ID", "N_PAREN_ID", "N_LANG", "N_DESC", "N_WHATSTHIS",
    "D_E_L_E_T_", "N_STATUSBAR", "N_ORDER", "_pad",
]


def _read_mpmenu_csv(file_path: Path, columns: list[str]) -> list[dict]:
    """Read a headerless semicolon-delimited mpmenu CSV.

    Tries utf-8-sig first (BOM), then cp1252 for Portuguese accents.
    """
    rows = []
    ncols = len(columns)
    # Try utf-8-sig first, fall back to cp1252 for accented chars
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            with open(file_path, "r", encoding=enc, errors="replace") as f:
                f.read(100)  # test read
            break
        except UnicodeDecodeError:
            continue
    with open(file_path, "r", encoding=enc, errors="replace") as f:
        reader = csv.reader(f, delimiter=";")
        for raw in reader:
            if len(raw) < ncols:
                raw.extend([""] * (ncols - len(raw)))
            row = {}
            for i, col in enumerate(columns):
                val = raw[i].strip().strip('"').strip() if i < len(raw) else ""
                row[col] = _sanitize_text(val)
            # Filter deleted records
            if row.get("D_E_L_E_T_", "").strip() not in ("", " "):
                continue
            rows.append(row)
    return rows


def _extract_function_name(rotina_raw: str) -> str:
    """Extract clean function name from schedule rotina field.

    Examples:
        "U_MGFWSC28('','01','010041')" -> "U_MGFWSC28"
        "U_MGFFINCB()"                 -> "U_MGFFINCB"
        "AUTONFEMON"                   -> "AUTONFEMON"
        "U_XGLPPTSCHED(1,1)"          -> "U_XGLPPTSCHED"
        "FINA435"                      -> "FINA435"
    """
    m = re.match(r'^([A-Za-z_]\w+)', rotina_raw.strip())
    return m.group(1) if m else rotina_raw.strip()


def parse_jobs(file_path: Path) -> List[dict]:
    """Parse job_detalhado_bash.csv — AppServer job sessions."""
    rows = _read_csv(file_path)
    result = []
    for row in rows:
        arquivo = row.get("Arquivo", "").strip()
        sessao = row.get("Sessao", "").strip()
        if not arquivo or not sessao:
            continue
        rate_raw = row.get("RefreshRate", "").strip()
        try:
            refresh_rate = int(rate_raw) if rate_raw and rate_raw != "N/A" else None
        except ValueError:
            refresh_rate = None
        result.append({
            "arquivo_ini": arquivo,
            "sessao": sessao,
            "rotina": row.get("Rotina_Main", "").strip(),
            "refresh_rate": refresh_rate,
            "parametros": row.get("Parametros", "").strip(),
        })
    return result


def parse_schedules(file_path: Path) -> List[dict]:
    """Parse schedule_decodificado.csv — Protheus scheduled tasks."""
    rows = _read_csv(file_path)
    result = []
    for row in rows:
        codigo = row.get("Codigo", "").strip()
        empresa = row.get("Empresa_Filial", "").strip()
        if not codigo:
            continue
        rotina_raw = row.get("Rotina", "").strip()
        rotina = _extract_function_name(rotina_raw)
        exec_raw = row.get("Execucoes_Dia", "").strip()
        try:
            execucoes = int(exec_raw) if exec_raw and exec_raw != "N/A" else None
        except ValueError:
            execucoes = None
        mod_raw = row.get("Modulo", "").strip()
        try:
            modulo = int(mod_raw) if mod_raw else 0
        except ValueError:
            modulo = 0
        result.append({
            "codigo": codigo,
            "rotina": rotina,
            "empresa_filial": empresa,
            "environment": row.get("Environment", "").strip(),
            "modulo": modulo,
            "status": row.get("Status", "").strip(),
            "tipo_recorrencia": row.get("Tipo_Recorrencia", "").strip(),
            "detalhe_recorrencia": row.get("Detalhe_Recorrencia", "").strip(),
            "execucoes_dia": execucoes,
            "intervalo": row.get("Intervalo_HH_MM", "").strip(),
            "hora_inicio": row.get("Hora_Inicio", "").strip(),
            "data_criacao": row.get("Data_Criacao", "").strip(),
            "ultima_execucao": row.get("Ultima_Execucao", "").strip(),
            "ultima_hora": row.get("Ultima_Hora", "").strip(),
            "recorrencia_raw": row.get("Recorrencia_Raw", "").strip(),
        })
    return result


def parse_mpmenu(csv_dir: Path) -> List[dict]:
    """Parse all 4 mpmenu CSVs and return flat menu-item list with hierarchy paths.

    Returns list of dicts: {modulo, rotina, nome, menu, ordem}
    """
    menu_path = _find_file_ci(csv_dir, "mpmenu_menu.csv")
    item_path = _find_file_ci(csv_dir, "mpmenu_item.csv")
    func_path = _find_file_ci(csv_dir, "mpmenu_function.csv")
    i18n_path = _find_file_ci(csv_dir, "mpmenu_i18n.csv")

    for p in (menu_path, item_path, func_path, i18n_path):
        if not p or not p.exists():
            raise FileNotFoundError(f"mpmenu file not found: {p}")

    # 1. Modules: M_ID → M_NAME
    menus_raw = _read_mpmenu_csv(menu_path, _MPMENU_MENU_COLS)
    module_map = {}  # M_ID → module name (e.g. "SIGACOM")
    for m in menus_raw:
        module_map[m["M_ID"]] = m["M_NAME"]
    del menus_raw

    # 2. Functions: build map by BOTH F_ID (hash) and line number (R_E_C_N_O_)
    #    I_ID_FUNC in items can be either the hash F_ID or a numeric R_E_C_N_O_
    funcs_raw = _read_mpmenu_csv(func_path, _MPMENU_FUNC_COLS)
    func_map = {}  # key → function name (e.g. "MATA120")
    for i, f in enumerate(funcs_raw, 1):
        if f["F_FUNCTION"]:
            func_map[f["F_ID"]] = f["F_FUNCTION"]          # by hash
            func_map[str(i)] = f["F_FUNCTION"]              # by line number
            func_map[f"{i:010d}"] = f["F_FUNCTION"]         # by padded line number
    del funcs_raw

    # 3. i18n: N_PAREN_ID → N_DESC (Portuguese only, N_LANG=1)
    i18n_raw = _read_mpmenu_csv(i18n_path, _MPMENU_I18N_COLS)
    name_map = {}  # N_PAREN_ID → description
    for n in i18n_raw:
        if n["N_LANG"] == "1":
            desc = n["N_DESC"].replace("&", "").strip()
            if desc:
                name_map[n["N_PAREN_ID"]] = desc
    del i18n_raw

    # 4. Items: build hierarchy and resolve
    items_raw = _read_mpmenu_csv(item_path, _MPMENU_ITEM_COLS)

    # Index items by I_ID
    item_by_id = {}
    for it in items_raw:
        item_by_id[it["I_ID"]] = it

    def _build_path(item_id: str, seen: set = None) -> list[str]:
        """Walk up I_FATHER chain to build menu path (bottom-up)."""
        if seen is None:
            seen = set()
        parts = []
        current = item_id
        while current and current in item_by_id:
            if current in seen:
                break  # cycle guard
            seen.add(current)
            it = item_by_id[current]
            label = name_map.get(current, "")
            if label:
                parts.append(label)
            father = it["I_FATHER"]
            # Stop when father == menu root (I_ID_MENU) or self-referencing
            if father == it["I_ID_MENU"] or father == current:
                break
            current = father
        parts.reverse()
        return parts

    import logging as _log
    _logger = _log.getLogger(__name__)
    print(f"[parse_mpmenu] {len(module_map)} menus, {len(func_map)} funcs, {len(name_map)} i18n, {len(items_raw)} items")
    func_keys_sample = list(func_map.keys())[:5]
    item_func_ids_sample = [it["I_ID_FUNC"] for it in items_raw if it["I_ID_FUNC"]][:5]
    print(f"[parse_mpmenu] func_map keys amostra: {func_keys_sample}")
    print(f"[parse_mpmenu] item I_ID_FUNC amostra: {item_func_ids_sample}")

    result = []
    _skipped_no_func = 0
    _skipped_no_match = 0
    for it in items_raw:
        func_id = it["I_ID_FUNC"]
        if not func_id:
            _skipped_no_func += 1
            continue
        if func_id not in func_map:
            _skipped_no_match += 1
            continue
        rotina = func_map[func_id]
        modulo = module_map.get(it["I_ID_MENU"], "")
        nome = name_map.get(it["I_ID"], "")
        path_parts = _build_path(it["I_ID"])
        menu_path_str = " > ".join(path_parts) if path_parts else nome

        try:
            ordem = int(it["I_ORDER"])
        except (ValueError, TypeError):
            ordem = 0

        result.append({
            "modulo": modulo,
            "rotina": rotina,
            "nome": nome,
            "menu": menu_path_str,
            "ordem": ordem,
        })

    del items_raw, item_by_id
    print(f"[parse_mpmenu] {len(result)} menus encontrados, {_skipped_no_func} skipped (sem func_id), {_skipped_no_match} skipped (func_id nao encontrado)")
    if _skipped_no_match > 0 and len(result) == 0:
        print("[parse_mpmenu] TODOS os items foram rejeitados — possivel incompatibilidade de formato de func_id")
    return result


# ---------------------------------------------------------------------------
# Padrão CSV parsers (headerless, semicolon-delimited, utf-8-sig BOM)
# ---------------------------------------------------------------------------

def _read_padrao_csv(file_path: Path, columns: list[str]) -> list[dict]:
    """Read a headerless semicolon-delimited padrão CSV into list of dicts.

    Uses utf-8-sig encoding (BOM). Values are stripped and sanitized.
    Column names are mapped positionally from the provided list.
    """
    rows = []
    ncols = len(columns)
    with open(file_path, "r", encoding="utf-8-sig", errors="replace") as f:
        reader = csv.reader(f, delimiter=";")
        for raw in reader:
            if len(raw) < ncols:
                raw.extend([""] * (ncols - len(raw)))
            row = {}
            for i, col in enumerate(columns):
                if col.startswith("_pad"):
                    continue
                val = raw[i].strip() if i < len(raw) else ""
                row[col] = _sanitize_text(val)
            rows.append(row)
    return rows


def _iter_padrao_csv(file_path: Path, columns: list[str]):
    """Generator version of _read_padrao_csv for large files.

    Yields one dict per CSV row — never loads entire file into memory.
    """
    ncols = len(columns)
    with open(file_path, "r", encoding="utf-8-sig", errors="replace") as f:
        reader = csv.reader(f, delimiter=";")
        for raw in reader:
            if len(raw) < ncols:
                raw.extend([""] * (ncols - len(raw)))
            row = {}
            for i, col in enumerate(columns):
                if col.startswith("_pad"):
                    continue
                val = raw[i].strip() if i < len(raw) else ""
                row[col] = _sanitize_text(val)
            yield row


# ── SX2 padrão column order ──
_PADRAO_SX2_COLS = [
    "X2_CHAVE", "X2_PATH", "X2_ARQUIVO", "X2_NOME", "X2_NOMESPA",
    "X2_NOMEENG", "X2_ROTINA", "X2_MODO", "X2_MODOUN", "X2_MODOEMP",
    "_pad10", "_pad11", "X2_PESSION", "_pad13", "_pad14",
    "_pad15", "_pad16", "_pad17", "_pad18", "_pad19",
    "_pad20", "_pad21", "_pad22", "_pad23", "_pad24",
    "_pad25", "_pad26", "_pad27", "_pad28",
]

# ── SX3 padrão column order ──
_PADRAO_SX3_COLS = [
    "X3_ARQUIVO", "X3_ORDEM", "X3_CAMPO", "X3_TIPO", "X3_TAMANHO",
    "X3_DECIMAL", "X3_TITULO", "X3_TITSPA", "X3_TITENG", "X3_DESCRIC",
    "X3_DESCSPA", "X3_DESCENG", "X3_PICTURE", "X3_VALID", "X3_USADO",
    "X3_RELACAO", "X3_F3", "X3_NIVEL", "X3_RESERV", "X3_CHECK",
    "X3_TRIGGER", "X3_PROPRI", "X3_BROWSE", "X3_VISUAL", "X3_CONTEXT",
    "X3_OBRIGAT", "X3_WHEN", "X3_CBOX", "X3_CBOXSPA", "X3_CBOXENG",
    "X3_PICTVAR", "X3_VLDUSER", "X3_FOLDER",
    # Remaining columns (not used but must be counted for positional mapping)
    "_pad33", "_pad34", "_pad35", "_pad36", "_pad37", "_pad38",
    "_pad39", "_pad40", "_pad41", "_pad42", "_pad43", "_pad44",
    "_pad45", "_pad46", "_pad47", "_pad48",
]

# ── SIX padrão column order ──
_PADRAO_SIX_COLS = [
    "INDICE", "ORDEM", "CHAVE", "DESCRICAO", "DESCSPA", "DESCENG",
    "PROPRI", "F3", "NICKNAME", "SHOWPESQ",
    "_pad10", "_pad11", "_pad12", "_pad13", "_pad14",
]

# ── SX7 padrão column order ──
_PADRAO_SX7_COLS = [
    "X7_CAMPO", "X7_SEQUENC", "X7_REGRA", "X7_CDOMIN", "X7_TIPO",
    "X7_SEEK", "X7_ALIAS", "X7_ORDEM", "X7_CONDIC", "X7_CHAVE",
    "X7_PROPRI",
    "_pad11", "_pad12", "_pad13",
]

# ── SX6 padrão column order ──
_PADRAO_SX6_COLS = [
    "X6_FIL", "X6_VAR", "X6_TIPO",
    "X6_DESCRIC", "X6_DESCSPA", "X6_DESCENG",
    "X6_DESC1", "X6_DESC1SPA", "X6_DESC1ENG",
    "X6_DESC2", "X6_DESC2SPA", "X6_DESC2ENG",
    "X6_CONTEUD", "X6_CONTEUDSPA", "X6_CONTEUDENG",
    "X6_PROPRI",
    "_pad16", "_pad17", "_pad18", "_pad19",
    "X6_CONTEUD2", "X6_CONTEUD2SPA", "X6_CONTEUD2ENG",
    "_pad23", "_pad24", "_pad25", "_pad26",
]


def parse_padrao_sx2(file_path: Path) -> List[dict]:
    """Parse padrão SX2 CSV (headerless, semicolon-delimited).

    Returns same format as parse_sx2: [{codigo, nome, modo, custom}, ...]
    """
    rows = _read_padrao_csv(file_path, _PADRAO_SX2_COLS)
    result = []
    for row in rows:
        codigo = row.get("X2_CHAVE", "").strip()
        if not codigo:
            continue
        result.append({
            "codigo": codigo,
            "nome": row.get("X2_NOME", "").strip(),
            "modo": row.get("X2_MODO", "").strip(),
            "custom": 0,  # padrão tables are never custom
        })
    return result


def parse_padrao_sx3(file_path: Path) -> List[dict]:
    """Parse padrão SX3 CSV (headerless, semicolon-delimited).

    MEMORY EFFICIENT: uses generator to process 374MB file line-by-line.
    Returns same format as parse_sx3.
    """
    result = []
    for row in _iter_padrao_csv(file_path, _PADRAO_SX3_COLS):
        campo = row.get("X3_CAMPO", "").strip()
        if not campo:
            continue

        # Obrigatorio: same 'x' pattern logic as client parser
        obrig_raw = row.get("X3_OBRIGAT", "").strip()
        obrigatorio = 1 if (
            obrig_raw.lower().startswith("x")
            or obrig_raw.upper() in ("S", "SIM", "1", ".T.")
        ) else 0

        proprietario = row.get("X3_PROPRI", "").strip()

        result.append({
            "tabela": row.get("X3_ARQUIVO", "").strip(),
            "campo": campo,
            "tipo": row.get("X3_TIPO", "").strip(),
            "tamanho": _safe_int(row.get("X3_TAMANHO", "0")),
            "decimal": _safe_int(row.get("X3_DECIMAL", "0")),
            "titulo": row.get("X3_TITULO", "").strip(),
            "descricao": row.get("X3_DESCRIC", "").strip(),
            "validacao": row.get("X3_VALID", "").strip(),
            "inicializador": row.get("X3_RELACAO", "").strip(),
            "obrigatorio": obrigatorio,
            "custom": 0,  # padrão fields are never custom
            "f3": row.get("X3_F3", "").strip(),
            "cbox": row.get("X3_CBOX", "").strip(),
            "vlduser": row.get("X3_VLDUSER", "").strip(),
            "when_expr": row.get("X3_WHEN", "").strip(),
            "proprietario": proprietario,
            "browse": row.get("X3_BROWSE", "").strip(),
            "trigger_flag": row.get("X3_TRIGGER", "").strip(),
            "visual": row.get("X3_VISUAL", "").strip(),
            "context": row.get("X3_CONTEXT", "").strip(),
            "folder": row.get("X3_FOLDER", "").strip(),
        })
    return result


def parse_padrao_six(file_path: Path) -> List[dict]:
    """Parse padrão SIX CSV (headerless, semicolon-delimited).

    Returns same format as parse_six.
    """
    rows = _read_padrao_csv(file_path, _PADRAO_SIX_COLS)
    result = []
    for row in rows:
        tabela = row.get("INDICE", "").strip()
        ordem = row.get("ORDEM", "").strip()
        if not tabela or not ordem:
            continue
        proprietario = row.get("PROPRI", "").strip()
        result.append({
            "tabela": tabela,
            "ordem": ordem,
            "chave": row.get("CHAVE", "").strip(),
            "descricao": row.get("DESCRICAO", "").strip(),
            "proprietario": proprietario,
            "f3": row.get("F3", "").strip(),
            "nickname": row.get("NICKNAME", "").strip(),
            "showpesq": row.get("SHOWPESQ", "").strip(),
            "custom": 0,  # padrão indices are never custom
        })
    return result


def parse_padrao_sx7(file_path: Path) -> List[dict]:
    """Parse padrão SX7 CSV (headerless, semicolon-delimited).

    Returns same format as parse_sx7.
    """
    rows = _read_padrao_csv(file_path, _PADRAO_SX7_COLS)
    result = []
    for row in rows:
        campo_origem = row.get("X7_CAMPO", "").strip()
        if not campo_origem:
            continue
        campo_destino = row.get("X7_CDOMIN", "").strip()
        proprietario = row.get("X7_PROPRI", "").strip()
        result.append({
            "campo_origem": campo_origem,
            "sequencia": row.get("X7_SEQUENC", "").strip(),
            "campo_destino": campo_destino,
            "regra": row.get("X7_REGRA", "").strip(),
            "tipo": row.get("X7_TIPO", "").strip(),
            "tabela": row.get("X7_ALIAS", "").strip(),
            "condicao": row.get("X7_CONDIC", "").strip(),
            "proprietario": proprietario,
            "seek": row.get("X7_SEEK", "").strip(),
            "alias": row.get("X7_ALIAS", "").strip(),
            "ordem": row.get("X7_ORDEM", "").strip(),
            "chave": row.get("X7_CHAVE", "").strip(),
            "custom": 0,  # padrão triggers are never custom
        })
    return result


def parse_padrao_sx6(file_path: Path) -> List[dict]:
    """Parse padrão SX6 CSV (headerless, semicolon-delimited).

    Returns same format as parse_sx6.
    """
    rows = _read_padrao_csv(file_path, _PADRAO_SX6_COLS)
    result = []
    for row in rows:
        variavel = row.get("X6_VAR", "").strip()
        if not variavel:
            continue
        descricao = (
            row.get("X6_DESCRIC", "").strip()
            + " " + row.get("X6_DESC1", "").strip()
        ).strip()
        proprietario = row.get("X6_PROPRI", "").strip()
        result.append({
            "filial": row.get("X6_FIL", "").strip(),
            "variavel": variavel,
            "tipo": row.get("X6_TIPO", "").strip(),
            "descricao": descricao,
            "conteudo": row.get("X6_CONTEUD", "").strip(),
            "proprietario": proprietario,
            "custom": 0,  # padrão parameters are never custom
        })
    return result
