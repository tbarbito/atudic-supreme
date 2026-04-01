"""Parser de fontes padrão Protheus — duplicado do parser_source.py com foco em ExecBlocks.

Extrai metadados completos dos fontes padrão incluindo análise detalhada
de cada chamada ExecBlock/ExistBlock para catalogar Pontos de Entrada automaticamente.
"""
import re
import bisect
import hashlib
import json
from pathlib import Path
import chardet

MAX_CHUNK_CHARS = 4000
OVERLAP_CHARS = 400


# ── File reading ──────────────────────────────────────────────────────────────

def _read_file(file_path: Path) -> str:
    """Read source file — fast path for Protheus files (cp1252 first)."""
    raw = file_path.read_bytes()
    if not raw:
        return ""
    try:
        return raw.decode("cp1252")
    except UnicodeDecodeError:
        pass
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        pass
    detected = chardet.detect(raw[:4096])
    encoding = detected.get("encoding") or "latin-1"
    try:
        return raw.decode(encoding)
    except (UnicodeDecodeError, LookupError):
        return raw.decode("latin-1")


def _detect_encoding(file_path: Path) -> str:
    raw = file_path.read_bytes()[:4096]
    if not raw:
        return "cp1252"
    for enc in ["cp1252", "utf-8"]:
        try:
            raw.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    detected = chardet.detect(raw)
    return detected.get("encoding") or "latin-1"


# ── Line utilities ────────────────────────────────────────────────────────────

def _build_line_offsets(content: str) -> list[int]:
    offsets = [0]
    idx = content.find('\n')
    while idx != -1:
        offsets.append(idx + 1)
        idx = content.find('\n', idx + 1)
    return offsets


def _classify_lines(content: str, offsets: list[int]) -> list[int]:
    """Classify each line as CODE=0, COMMENT=1, BLANK=2."""
    num_lines = len(offsets)
    types = [0] * num_lines
    in_block = False
    for i in range(num_lines):
        start = offsets[i]
        end = offsets[i + 1] - 1 if i + 1 < num_lines else len(content)
        s = content[start:end].strip()
        if not s:
            types[i] = 2
            continue
        if in_block:
            types[i] = 1
            if '*/' in s:
                in_block = False
            continue
        if s[:2] == '//':
            types[i] = 1
        elif s[:2] == '/*':
            types[i] = 1
            if '*/' not in s[2:]:
                in_block = True
        elif s[0] == '*' or s[:2] == '*/':
            types[i] = 1
    return types


def _find_func_body_end(content: str, next_match_start: int, current_start: int = 0) -> int:
    offsets = _build_line_offsets(content)
    line_types = _classify_lines(content, offsets)
    next_line = bisect.bisect_right(offsets, next_match_start) - 1
    cur_line = bisect.bisect_right(offsets, current_start) - 1
    header_line = next_line
    for j in range(next_line - 1, cur_line, -1):
        if line_types[j] == 0:
            break
        header_line = j
    return offsets[header_line]


# ── Basic extraction (same as parser_source.py) ──────────────────────────────

def _extract_functions(content: str) -> list[str]:
    funcs = []
    funcs.extend(re.findall(r"(?:Static\s+|User\s+|Main\s+)?Function\s+(\w+)", content, re.IGNORECASE))
    funcs.extend(re.findall(r"WSMETHOD\s+(\w+)\s+WS(?:RECEIVE|SEND|SERVICE)", content, re.IGNORECASE))
    funcs.extend(re.findall(r"METHOD\s+(\w+)\s*\([^)]*\)\s*CLASS\s+\w+", content, re.IGNORECASE))
    return funcs


def _extract_user_functions(content: str) -> list[str]:
    return re.findall(r"User\s+Function\s+(\w+)", content, re.IGNORECASE)


def _extract_tables(content: str) -> list[str]:
    tables = set()
    tables.update(re.findall(r'DbSelectArea\s*\(\s*["\'](\w+)["\']\s*\)', content, re.IGNORECASE))
    tables.update(re.findall(r'RetSqlName\s*\(\s*["\'](\w+)["\']\s*\)', content, re.IGNORECASE))
    tables.update(re.findall(r'\b(S[A-Z][0-9A-Z])\s*->', content))
    tables.update(re.findall(r'\b([ZQ][A-Z][0-9A-Z])\s*->', content))
    tables.update(re.findall(r'(?:xFilial|Posicione|MsSeek|dbSetOrder|ChkFile)\s*\(\s*["\'](\w{2,3})["\']', content, re.IGNORECASE))
    valid = set()
    for t in tables:
        t = t.upper()
        if len(t) == 3 and t[0] in "SZDNQ" and t[1].isalpha():
            valid.add(t)
    return sorted(valid)


def _extract_includes(content: str) -> list[str]:
    return re.findall(r'#Include\s+["\'](.+?)["\']', content, re.IGNORECASE)


def _extract_calls_u(content: str) -> list[str]:
    calls = re.findall(r'\bU_(\w+)\s*\(', content, re.IGNORECASE)
    return sorted(set(c for c in calls))


def _extract_calls_execblock(content: str) -> list[str]:
    blocks = re.findall(r'ExecBlock\s*\(\s*["\'](\w+)', content, re.IGNORECASE)
    return sorted(set(blocks))


def _extract_fields_ref(content: str) -> list[str]:
    fields = set()
    fields.update(re.findall(r'\w{2,3}->(\w{2,3}_\w+)', content))
    fields.update(re.findall(r'Replace\s+(\w{2,3}_\w+)', content, re.IGNORECASE))
    fields.update(re.findall(r'["\'](\w{2,3}_\w+)["\']', content))
    valid = set()
    for f in fields:
        f = f.upper()
        if re.match(r'^[A-Z][A-Z0-9]_\w+$', f):
            valid.add(f)
    return sorted(valid)


def _extract_reclock_tables(content: str) -> list[str]:
    found = set()
    for m in re.findall(r'RecLock\s*\(\s*["\']\s*(\w{2,3})\s*["\']', content, re.IGNORECASE):
        found.add(m.upper())
    for m in re.findall(r'(\w{2,3})\s*->\s*\(\s*RecLock', content, re.IGNORECASE):
        found.add(m.upper())
    return sorted(t for t in found if len(t) == 3 and t[0] in "SZDNQ" and t[1].isalpha())


def _extract_write_tables(content: str) -> list[str]:
    write_tables = set()
    for match in re.findall(r'RecLock\s*\(\s*["\']\s*(\w{2,3})\s*["\']', content, re.IGNORECASE):
        write_tables.add(match.upper())
    for match in re.findall(r'(\w{2,3})\s*->\s*\(\s*RecLock', content, re.IGNORECASE):
        write_tables.add(match.upper())
    for match in re.findall(r'Replace\s+([A-Z]\w)_', content, re.IGNORECASE):
        prefix = match.upper()
        table = "S" + prefix
        if len(table) == 3:
            write_tables.add(table)
    for match in re.findall(r'(\w{2,3})->\s*\(\s*dbAppend', content, re.IGNORECASE):
        write_tables.add(match.upper())
    for match in re.findall(r'(\w{2,3})->\s*\(\s*dbDelete', content, re.IGNORECASE):
        write_tables.add(match.upper())
    return sorted(t for t in write_tables if len(t) == 3 and t[0] in "SZDNQ" and t[1].isalpha())


def _extract_params(content: str) -> dict:
    sx6 = {}
    sx1 = set()
    for m in re.finditer(
        r'SuperGetMV\s*\(\s*["\'](\w+)["\']\s*(?:,\s*[^,]*\s*,\s*(["\'][^"\']*["\']|[\w.]+))?',
        content, re.IGNORECASE
    ):
        var = m.group(1).upper()
        default = (m.group(2) or "").strip("\"'") if m.group(2) else ""
        sx6[var] = default
    for m in re.finditer(
        r'(?:GetMV|GetNewPar)\s*\(\s*["\'](\w+)["\']\s*(?:,\s*(["\'][^"\']*["\']|[\w.]+))?',
        content, re.IGNORECASE
    ):
        var = m.group(1).upper()
        if var not in sx6:
            default = (m.group(2) or "").strip("\"'") if m.group(2) else ""
            sx6[var] = default
    for m in re.finditer(r'FWMVPar\s*\(\s*["\'](\w+)["\']', content, re.IGNORECASE):
        var = m.group(1).upper()
        if var not in sx6:
            sx6[var] = ""
    for m in re.finditer(r'(?:Pergunte|FWGetSX1)\s*\(\s*["\'](\w+)["\']', content, re.IGNORECASE):
        sx1.add(m.group(1).upper())
    # Pergunte(cPerg) pattern — variable-based (very common in Protheus)
    if re.search(r'(?:Pergunte|FWGetSX1)\s*\(\s*cPerg', content, re.IGNORECASE):
        for m in re.finditer(r'\bcPerg\s*:=\s*["\'](\w+)["\']', content, re.IGNORECASE):
            sx1.add(m.group(1).upper())
    return {
        "sx6": [{"var": k, "default": v} for k, v in sorted(sx6.items())],
        "sx1": sorted(sx1),
    }


def _detect_source_type(content: str) -> str:
    if re.search(r"WSSERVICE\s+\w+", content, re.IGNORECASE):
        return "webservice"
    if re.search(r"CLASS\s+\w+", content, re.IGNORECASE):
        return "class"
    if re.search(r"User\s+Function\s+\w+", content, re.IGNORECASE):
        return "user_function"
    if re.search(r"Main\s+Function\s+\w+", content, re.IGNORECASE):
        return "main_function"
    if re.search(r"Static\s+Function\s+\w+", content, re.IGNORECASE):
        return "static_function"
    return "outro"


# ── ExecBlock extraction (NOVO — análise detalhada para PEs) ─────────────────

# Regex patterns for ExecBlock analysis
_EXISTBLOCK_RE = re.compile(
    r'(?:(\w+)\s*:=\s*)?Existblock\s*\(\s*["\'](\w+)["\']\s*(?:,\s*([^)]*))?\)',
    re.IGNORECASE
)
_EXECBLOCK_RE = re.compile(
    r'(?:(\w+)\s*:=\s*)?Execblock\s*\(\s*["\'](\w+)["\']\s*,\s*\.F\.\s*,\s*\.F\.\s*(?:,\s*(.+?))?\s*\)',
    re.IGNORECASE
)

# Function boundary regex
_FUNC_DECL_RE = re.compile(
    r'(?:Static\s+|User\s+|Main\s+)?Function\s+(\w+)',
    re.IGNORECASE
)


def _get_func_at_line(func_ranges: list[tuple], line_no: int, fallback: str) -> str:
    """Return function name that contains this line number."""
    current_func = fallback
    for start, name in func_ranges:
        if start <= line_no:
            current_func = name
        else:
            break
    return current_func


def _find_nearby_comment(lines: list[str], line_no: int, direction: str = "above") -> str:
    """Find the nearest comment near a line (above or inline).

    Looks for:
    - Inline comment on the same line: ExecBlock("MA410COR",.F.,.F.,aCores) // Cores do browse
    - Comment block above the ExistBlock/ExecBlock (up to 5 lines up)
    """
    comments = []

    # Check inline comment on the ExecBlock line itself
    if line_no < len(lines):
        line = lines[line_no]
        inline = re.search(r'//\s*(.+)', line)
        if inline:
            return inline.group(1).strip()

    # Look above for comment lines
    if direction == "above":
        for i in range(line_no - 1, max(line_no - 6, -1), -1):
            if i < 0 or i >= len(lines):
                continue
            stripped = lines[i].strip()
            if stripped.startswith('//'):
                comments.insert(0, stripped[2:].strip())
            elif stripped.startswith('/*') or stripped.startswith('*'):
                comments.insert(0, re.sub(r'^[/*]+\s*', '', stripped).strip())
            elif stripped.startswith('��') or stripped.startswith('�'):
                # Protheus box comment
                inner = re.sub(r'^[�Ŀ����ٱ]+\s*', '', stripped).strip()
                inner = re.sub(r'\s*[�Ŀ����ٱ]+$', '', inner).strip()
                if inner and not all(c in '�Ŀ����ٱ' for c in inner):
                    comments.insert(0, inner)
            else:
                break  # Hit code, stop

    return ' '.join(comments).strip()[:200] if comments else ""


def _infer_operation_from_comment(comment: str, params_str: str) -> str:
    """Try to infer the operation context from comments or parameters.

    Examples:
    - ExecBlock("M410STTS",.F.,.F.,{3}) with comment "Identificar operação da inclusão" → "inclusao"
    - ExecBlock("MT410ACE",.F.,.F.,{nOpc}) in context of Exclusão → "exclusao"
    """
    text = (comment + " " + params_str).lower()
    if any(w in text for w in ["inclus", "inserir", "insert", "inclui"]):
        return "inclusao"
    if any(w in text for w in ["alter", "modific", "update", "edita"]):
        return "alteracao"
    if any(w in text for w in ["exclu", "delet", "remov"]):
        return "exclusao"
    if any(w in text for w in ["copi", "copy", "duplic"]):
        return "copia"
    if any(w in text for w in ["visual", "view", "consult"]):
        return "visualizacao"
    if any(w in text for w in ["cor", "color", "legenda"]):
        return "cores_legenda"
    if any(w in text for w in ["filtro", "filter", "browse"]):
        return "filtro_browse"
    if any(w in text for w in ["valid", "acesso", "permiss"]):
        return "validacao"
    if any(w in text for w in ["menu", "botao", "button"]):
        return "menu_botao"
    return ""


def extract_execblocks_detailed(content: str, file_name: str) -> list[dict]:
    """Extract detailed ExecBlock/ExistBlock info for PE cataloging.

    For each ExecBlock call, captures:
    - nome_pe: PE name (e.g. MA410COR)
    - arquivo: source file
    - funcao: containing function
    - linha: line number
    - linha_existblock: line of the ExistBlock check (if paired)
    - parametros: parameters passed to ExecBlock
    - variavel_retorno: variable that receives the return (if any)
    - retorno_usado: whether return value is captured
    - tipo_retorno_inferido: inferred return type (logical, array, character, nil)
    - comentario: nearby comment explaining the PE
    - operacao: inferred operation context (inclusao, alteracao, exclusao, etc.)
    - contexto: ~10 lines around the call for reference
    - uso_condicional: whether it's used in an If (gate) pattern
    """
    lines = content.split('\n')

    # Build function boundary map
    func_ranges = []
    for i, line in enumerate(lines):
        m = _FUNC_DECL_RE.search(line)
        if m:
            func_ranges.append((i, m.group(1)))

    fallback_func = Path(file_name).stem

    # First pass: find all ExistBlock declarations (for pairing)
    existblock_map = {}  # pe_name -> {line, var, extra_params}
    for i, line in enumerate(lines):
        m = _EXISTBLOCK_RE.search(line)
        if m:
            var = m.group(1) or ""
            pe_name = m.group(2).upper()
            extra = m.group(3) or ""
            if pe_name not in existblock_map:
                existblock_map[pe_name] = []
            existblock_map[pe_name].append({
                "line": i,
                "var": var,
                "extra_params": extra.strip(),
            })

    # Second pass: find all ExecBlock calls with full context
    results = []
    seen_pe_in_func = {}  # (pe_name, funcao) -> count — to track multiple calls

    for i, line in enumerate(lines):
        m = _EXECBLOCK_RE.search(line)
        if m:
            var_retorno = m.group(1) or ""
            pe_name = m.group(2).upper()
            params_raw = m.group(3) or ""

            funcao = _get_func_at_line(func_ranges, i, fallback_func)

            # Track occurrences of same PE in same function
            key = (pe_name, funcao)
            seen_pe_in_func[key] = seen_pe_in_func.get(key, 0) + 1

            # Find paired ExistBlock (closest one above this line)
            linha_existblock = None
            if pe_name in existblock_map:
                for eb in existblock_map[pe_name]:
                    if eb["line"] < i and (i - eb["line"]) < 60:
                        linha_existblock = eb["line"] + 1

            # Get nearby comment
            # First check above the ExistBlock (if paired), then above ExecBlock
            comment = ""
            if linha_existblock:
                comment = _find_nearby_comment(lines, linha_existblock - 1, "above")
            if not comment:
                comment = _find_nearby_comment(lines, i, "above")

            # Infer return type from variable name and usage
            tipo_retorno = "nil"
            if var_retorno:
                vr_lower = var_retorno.lower()
                if vr_lower.startswith("l") or vr_lower.startswith("lcontinua") or vr_lower.startswith("lok"):
                    tipo_retorno = "logical"
                elif vr_lower.startswith("a"):
                    tipo_retorno = "array"
                elif vr_lower.startswith("c"):
                    tipo_retorno = "character"
                elif vr_lower.startswith("n"):
                    tipo_retorno = "numeric"
                else:
                    tipo_retorno = "variant"

            # Check if used conditionally (If lVar / If ExecBlock / If !ExecBlock)
            uso_condicional = False
            if var_retorno:
                # Check if the variable is used in a condition nearby
                for j in range(max(0, i - 3), min(len(lines), i + 5)):
                    l = lines[j].strip().upper()
                    if re.search(rf'\bIF\b.*\b{re.escape(var_retorno.upper())}\b', l):
                        uso_condicional = True
                        break
            # Also check if ExecBlock itself is inside an If
            line_stripped = lines[i].strip().upper()
            if line_stripped.startswith('IF ') or line_stripped.startswith('IF('):
                uso_condicional = True

            # Infer operation from comment and params
            operacao = _infer_operation_from_comment(comment, params_raw)

            # Extract context (5 lines before, the line, 5 lines after)
            ctx_start = max(0, i - 5)
            ctx_end = min(len(lines), i + 6)
            contexto = '\n'.join(lines[ctx_start:ctx_end])

            results.append({
                "nome_pe": pe_name,
                "arquivo": file_name,
                "funcao": funcao,
                "linha": i + 1,
                "linha_existblock": linha_existblock,
                "parametros": params_raw.strip(),
                "variavel_retorno": var_retorno,
                "retorno_usado": bool(var_retorno),
                "tipo_retorno_inferido": tipo_retorno,
                "comentario": comment,
                "operacao": operacao,
                "contexto": contexto[:1000],
                "uso_condicional": uso_condicional,
            })

    return results


# ── Chunking ──────────────────────────────────────────────────────────────────

def _split_large_chunk(chunk: dict) -> list[dict]:
    content = chunk["content"]
    if len(content) <= MAX_CHUNK_CHARS:
        return [chunk]
    sub_chunks = []
    start = 0
    part = 0
    step = MAX_CHUNK_CHARS - OVERLAP_CHARS
    while start < len(content):
        end = min(start + MAX_CHUNK_CHARS, len(content))
        sub_chunks.append({
            "id": f"{chunk['id']}_p{part}",
            "content": content[start:end],
            "funcao": chunk["funcao"],
        })
        start += step
        part += 1
    return sub_chunks


def _split_into_chunks(content: str, file_name: str) -> list[dict]:
    """Split source into function-level chunks."""
    offsets = _build_line_offsets(content)
    line_types = _classify_lines(content, offsets)

    func_pattern = re.compile(
        r'((?:Static\s+|User\s+|Main\s+)?Function\s+(\w+)'
        r'|WSMETHOD\s+(\w+)\s+WS(?:RECEIVE|SEND)'
        r'|METHOD\s+(\w+)\s*\([^)]*\)\s*CLASS\s+\w+)',
        re.IGNORECASE
    )

    func_matches = []
    for m in func_pattern.finditer(content):
        line_no = bisect.bisect_right(offsets, m.start()) - 1
        name = m.group(2) or m.group(3) or m.group(4) or "unknown"
        func_matches.append((line_no, name))

    if not func_matches:
        return _split_large_chunk({"id": f"{file_name}::full", "content": content, "funcao": "_full"})

    header_starts = []
    for idx, (func_line, _name) in enumerate(func_matches):
        prev_limit = func_matches[idx - 1][0] if idx > 0 else -1
        header_line = func_line
        for j in range(func_line - 1, prev_limit, -1):
            lt = line_types[j]
            if lt == 0:
                break
            header_line = j
        header_starts.append(header_line)

    raw_chunks = []
    first_header_off = offsets[header_starts[0]]
    file_header = content[:first_header_off].strip()
    if file_header:
        raw_chunks.append({"id": f"{file_name}::header", "content": file_header, "funcao": "_header"})

    for i, (_func_line, name) in enumerate(func_matches):
        start_off = offsets[header_starts[i]]
        if i + 1 < len(func_matches):
            end_off = offsets[header_starts[i + 1]]
        else:
            end_off = len(content)
        chunk_content = content[start_off:end_off].strip()
        raw_chunks.append({"id": f"{file_name}::{name}", "content": chunk_content, "funcao": name})

    chunks = []
    for chunk in raw_chunks:
        chunks.extend(_split_large_chunk(chunk))
    return chunks


# ── Function block extraction (for funcao_docs) ──────────────────────────────

_FUNC_SIG_RE = re.compile(
    r'((?:Static\s+|User\s+|Main\s+)?Function\s+(\w+)\s*(\([^)]*\))?)',
    re.IGNORECASE
)


def _extract_func_blocks(content: str) -> list[dict]:
    """Split source into per-function blocks with signatures."""
    matches = list(_FUNC_SIG_RE.finditer(content))
    if not matches:
        return []

    blocks = []
    for i, match in enumerate(matches):
        start = match.start()
        end = _find_func_body_end(content, matches[i + 1].start(), start) if i + 1 < len(matches) else len(content)
        body = content[start:end]

        sig_match = _FUNC_SIG_RE.match(body)
        if sig_match:
            full_sig = sig_match.group(1).strip()
            func_name = sig_match.group(2)
            params = sig_match.group(3) or "()"
            assinatura = f"{func_name}{params}"
        else:
            func_name = match.group(2)
            full_sig = match.group(1).strip()
            assinatura = func_name + "()"

        # Detect function type
        tipo = "function"
        sig_upper = full_sig.upper()
        if sig_upper.startswith("STATIC"):
            tipo = "static"
        elif sig_upper.startswith("USER"):
            tipo = "user_function"
        elif sig_upper.startswith("MAIN"):
            tipo = "main_function"

        blocks.append({
            "funcao": func_name,
            "tipo": tipo,
            "assinatura": assinatura,
            "body": body,
        })
    return blocks


# ── Main parse function ──────────────────────────────────────────────────────

def parse_padrao_source(file_path: Path, include_chunks: bool = False) -> dict:
    """Parse a standard Protheus source file with detailed ExecBlock analysis.

    Returns all metadata from parser_source.py PLUS:
    - execblocks_detailed: list of detailed ExecBlock info dicts
    """
    content = _read_file(file_path)
    if not content:
        return {
            "arquivo": file_path.name,
            "caminho": str(file_path),
            "funcoes": [], "user_funcs": [], "tabelas_ref": [],
            "write_tables": [], "reclock_tables": [], "includes": [],
            "calls_u": [], "calls_execblock": [], "fields_ref": [],
            "execblocks_detailed": [], "lines_of_code": 0,
            "hash": "", "encoding": "cp1252", "source_type": "outro",
        }

    funcoes = _extract_functions(content)
    lines_of_code = len([l for l in content.splitlines() if l.strip() and not l.strip().startswith("//")])
    source_type = _detect_source_type(content)

    # Extract function blocks in the same pass (avoid re-reading the file)
    func_blocks_raw = _extract_func_blocks(content)
    func_blocks = []
    for block in func_blocks_raw:
        func_blocks.append({
            "funcao": block["funcao"],
            "tipo": block["tipo"],
            "assinatura": block["assinatura"],
            "tabelas_ref": _extract_tables(block["body"]),
            "campos_ref": _extract_fields_ref(block["body"]),
            "calls": _extract_calls_u(block["body"]),
            "params": _extract_params(block["body"]),
        })

    result = {
        "arquivo": file_path.name,
        "caminho": str(file_path),
        "source_type": source_type,
        "funcoes": funcoes,
        "user_funcs": _extract_user_functions(content),
        "tabelas_ref": _extract_tables(content),
        "write_tables": _extract_write_tables(content),
        "reclock_tables": _extract_reclock_tables(content),
        "includes": _extract_includes(content),
        "calls_u": _extract_calls_u(content),
        "calls_execblock": _extract_calls_execblock(content),
        "fields_ref": _extract_fields_ref(content),
        "execblocks_detailed": extract_execblocks_detailed(content, file_path.name),
        "func_blocks": func_blocks,
        "lines_of_code": lines_of_code,
        "encoding": _detect_encoding(file_path),
        "hash": hashlib.md5(content.encode(errors="replace")).hexdigest(),
    }
    if include_chunks:
        result["chunks"] = _split_into_chunks(content, file_path.name)
    return result
