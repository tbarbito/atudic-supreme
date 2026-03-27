# -*- coding: utf-8 -*-
"""Origem: ExtraiRPO (Joni) — Parser de codigo-fonte ADVPL/TLPP."""

import re
import bisect
import hashlib
from pathlib import Path
import chardet

MAX_CHUNK_CHARS = 4000
OVERLAP_CHARS = 400


def _build_line_offsets(content: str) -> list[int]:
    """Build array of start-of-line offsets. O(n) single pass, zero copies."""
    offsets = [0]
    idx = content.find('\n')
    while idx != -1:
        offsets.append(idx + 1)
        idx = content.find('\n', idx + 1)
    return offsets


def _classify_lines(content: str, offsets: list[int]) -> list[int]:
    """Classify each line as CODE=0, COMMENT=1, BLANK=2.

    Single forward pass. Uses strip() on each line (small, bounded string).
    """
    num_lines = len(offsets)
    types = [0] * num_lines
    in_block = False

    for i in range(num_lines):
        start = offsets[i]
        end = offsets[i + 1] - 1 if i + 1 < num_lines else len(content)
        s = content[start:end].strip()

        if not s:
            types[i] = 2  # blank
            continue

        if in_block:
            types[i] = 1  # comment
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
        # else: types[i] = 0 (code, already default)

    return types


def _find_func_body_end(content: str, next_match_start: int, current_start: int = 0) -> int:
    """Find where current function body ends (before next function's header).

    Compatibility wrapper for ingestor.py — uses line offset table internally.
    """
    offsets = _build_line_offsets(content)
    line_types = _classify_lines(content, offsets)
    next_line = bisect.bisect_right(offsets, next_match_start) - 1
    cur_line = bisect.bisect_right(offsets, current_start) - 1

    # Walk backward from next function's declaration
    header_line = next_line
    for j in range(next_line - 1, cur_line, -1):
        if line_types[j] == 0:  # code — stop
            break
        header_line = j

    return offsets[header_line]


def _read_file(file_path: Path) -> str:
    """Read source file — fast path for Protheus files.

    99% of ADVPL/TLPP files are cp1252. Try that first (no chardet overhead).
    Only fall back to chardet if cp1252 fails.
    """
    raw = file_path.read_bytes()
    if not raw:
        return ""
    # Fast path: try cp1252 first (covers 99% of Protheus files)
    try:
        return raw.decode("cp1252")
    except UnicodeDecodeError:
        pass
    # Fast path 2: try utf-8
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        pass
    # Slow path: chardet only as last resort
    detected = chardet.detect(raw[:4096])  # Only scan first 4KB, not entire file
    encoding = detected.get("encoding") or "latin-1"
    try:
        return raw.decode(encoding)
    except (UnicodeDecodeError, LookupError):
        return raw.decode("latin-1")  # latin-1 never fails (maps all 256 bytes)


def _extract_functions(content: str) -> list[str]:
    """Extract all function-like declarations: Functions, WSMETHODs, METHODs."""
    funcs = []
    # Standard functions
    funcs.extend(re.findall(r"(?:Static\s+|User\s+|Main\s+)?Function\s+(\w+)", content, re.IGNORECASE))
    # WebService methods (implementation): WSMETHOD Name WSRECEIVE ... WSSERVICE ServiceName
    funcs.extend(re.findall(r"WSMETHOD\s+(\w+)\s+WS(?:RECEIVE|SEND|SERVICE)", content, re.IGNORECASE))
    # Class methods: METHOD Name(?...) CLASS ClassName
    funcs.extend(re.findall(r"METHOD\s+(\w+)\s*\([^)]*\)\s*CLASS\s+\w+", content, re.IGNORECASE))
    return funcs


def _extract_user_functions(content: str) -> list[str]:
    pattern = r"User\s+Function\s+(\w+)"
    return re.findall(pattern, content, re.IGNORECASE)


def _extract_ws_structures(content: str) -> dict:
    """Extract WebService declarations: WSSTRUCT, WSSERVICE, WSMETHOD."""
    result = {"ws_structs": [], "ws_services": [], "ws_methods": []}

    # WSSTRUCT Name (exclude WSSTRUCT/WSSERVICE/WSMETHOD as names)
    reserved = {"WSSTRUCT", "WSSERVICE", "WSMETHOD", "WSDATA", "WSRECEIVE", "WSSEND", "ENDWSSERVICE", "ENDWSSTRUCT"}
    for m in re.finditer(r"WSSTRUCT\s+(\w+)", content, re.IGNORECASE):
        name = m.group(1)
        if name.upper() in reserved:
            continue
        # Get WSDATA fields
        start = m.end()
        fields = []
        for line in content[start:start+2000].split("\n"):
            line = line.strip()
            fm = re.match(r"WSDATA\s+(\w+)\s+as\s+(\w+)", line, re.IGNORECASE)
            if fm:
                fields.append({"nome": fm.group(1), "tipo": fm.group(2)})
            elif line and not line.startswith("//") and not line.startswith("WSDATA"):
                break
        result["ws_structs"].append({"nome": name, "campos": fields})

    # WSSERVICE Name
    for m in re.finditer(r"WSSERVICE\s+(\w+)", content, re.IGNORECASE):
        name = m.group(1)
        if name.upper() in reserved:
            continue
        # Get WSDATA and WSMETHOD declarations
        start = m.end()
        methods = []
        data = []
        for line in content[start:start+2000].split("\n"):
            line = line.strip()
            mm = re.match(r"WSMETHOD\s+(\w+)", line, re.IGNORECASE)
            if mm:
                methods.append(mm.group(1))
            dm = re.match(r"WSDATA\s+(\w+)\s+as\s+(\w+)", line, re.IGNORECASE)
            if dm:
                data.append({"nome": dm.group(1), "tipo": dm.group(2)})
            if re.match(r"ENDWSSERVICE|END\s+WSSERVICE", line, re.IGNORECASE):
                break
        result["ws_services"].append({"nome": name, "metodos": methods, "dados": data})

    # WSMETHOD implementations: WSMETHOD Name WSRECEIVE x WSSEND y WSSERVICE z
    for m in re.finditer(
        r"WSMETHOD\s+(\w+)\s+WSRECEIVE\s+(\w+)\s+WSSEND\s+(\w+)\s+WSSERVICE\s+(\w+)",
        content, re.IGNORECASE
    ):
        result["ws_methods"].append({
            "nome": m.group(1),
            "receive": m.group(2),
            "send": m.group(3),
            "service": m.group(4),
        })

    return result


def _extract_tables(content: str) -> list[str]:
    tables = set()
    # DbSelectArea("SA1"), RetSqlName("SA1")
    tables.update(re.findall(r'DbSelectArea\s*\(\s*["\'](\w+)["\']\s*\)', content, re.IGNORECASE))
    tables.update(re.findall(r'RetSqlName\s*\(\s*["\'](\w+)["\']\s*\)', content, re.IGNORECASE))
    # Alias references: SA1->, SC5->, SE1-> etc
    tables.update(re.findall(r'\b(S[A-Z][0-9A-Z])\s*->', content))
    # Also detect custom tables: ZA1->, QA1->
    tables.update(re.findall(r'\b([ZQ][A-Z][0-9A-Z])\s*->', content))
    # xFilial("SA1"), Posicione("SA1", ...)
    tables.update(re.findall(r'(?:xFilial|Posicione|MsSeek|dbSetOrder|ChkFile)\s*\(\s*["\'](\w{2,3})["\']', content, re.IGNORECASE))
    # Filter valid Protheus table codes
    valid = set()
    for t in tables:
        t = t.upper()
        if len(t) == 3 and t[0] in "SZDNQ" and t[1].isalpha():
            valid.add(t)
    return sorted(valid)


def _extract_includes(content: str) -> list[str]:
    return re.findall(r'#Include\s+["\'](.+?)["\']', content, re.IGNORECASE)


def _extract_exec_autos(content: str) -> list[str]:
    return re.findall(r'MsExecAuto\s*\(.+?(MATA\d+)', content, re.IGNORECASE)


def _is_valid_table(name: str) -> bool:
    return len(name) == 3 and name[0] in "SZDNQ" and name[1].isalpha()


def _extract_reclock_tables(content: str) -> list[str]:
    """Detect tables accessed via RecLock (direct write, no automatic validation)."""
    found = set()
    # RecLock("SA1", ...) or SA1->(RecLock("SA1",...))
    for m in re.findall(r'RecLock\s*\(\s*["\']\s*(\w{2,3})\s*["\']', content, re.IGNORECASE):
        found.add(m.upper())
    # ALIAS->(RecLock(...)) — table inferred from alias
    for m in re.findall(r'(\w{2,3})\s*->\s*\(\s*RecLock', content, re.IGNORECASE):
        found.add(m.upper())
    return sorted(t for t in found if _is_valid_table(t))


def _extract_write_tables(content: str) -> list[str]:
    """Detect tables where the code performs WRITE operations (all patterns)."""
    write_tables = set()
    # RecLock — already covered by _extract_reclock_tables but keep here for write_tables completeness
    for match in re.findall(r'RecLock\s*\(\s*["\']\s*(\w{2,3})\s*["\']', content, re.IGNORECASE):
        write_tables.add(match.upper())
    for match in re.findall(r'(\w{2,3})\s*->\s*\(\s*RecLock', content, re.IGNORECASE):
        write_tables.add(match.upper())
    # Replace <FIELD>
    for match in re.findall(r'Replace\s+([A-Z]\w)_', content, re.IGNORECASE):
        prefix = match.upper()
        table = "S" + prefix
        if len(table) == 3:
            write_tables.add(table)
    # dbAppend/dbDelete after alias
    for match in re.findall(r'(\w{2,3})->\s*\(\s*dbAppend', content, re.IGNORECASE):
        write_tables.add(match.upper())
    for match in re.findall(r'(\w{2,3})->\s*\(\s*dbDelete', content, re.IGNORECASE):
        write_tables.add(match.upper())
    return sorted(t for t in write_tables if _is_valid_table(t))


def _extract_point_of_entry(user_funcs: list[str]) -> list[str]:
    """Detect Protheus Points of Entry from User Function names only.
    PEs are always User Functions — Static/Main Functions are never PEs."""
    pe_patterns = [
        re.compile(r'^[A-Z]{2}\d{3}[A-Z]{2,5}$'),   # MT410GRV, CN120PED
        re.compile(r'^[A-Z]\d{3}[A-Z]{2,6}$'),       # A010TOK, A020DELE
        re.compile(r'^MTA?\d{3}[A-Z]{2,5}$'),        # MTA461LNK, MT100LOK
        re.compile(r'^[A-Z]{3,4}\d{3}[A-Z_]{2,}$'),  # MATA410BRW, CRM980MDEF
        re.compile(r'^[A-Z]{4}\d{2,3}[A-Z]{2,}$'),   # FATA410PE, COMA120VLD
    ]
    result = []
    for f in user_funcs:
        fu = f.upper()
        for pattern in pe_patterns:
            if pattern.match(fu):
                result.append(f)
                break
    return result


def _extract_calls_u(content: str) -> list[str]:
    """Extract calls to User Functions (U_xxx) — for call graph."""
    calls = re.findall(r'\bU_(\w+)\s*\(', content, re.IGNORECASE)
    return sorted(set(c for c in calls))


def _extract_calls_execblock(content: str) -> list[str]:
    """Extract ExecBlock/MsExecAuto calls — indirect function calls."""
    blocks = re.findall(r'ExecBlock\s*\(\s*["\'](\w+)', content, re.IGNORECASE)
    return sorted(set(blocks))


def _extract_fields_ref(content: str) -> list[str]:
    """Extract specific field references (SA1->A1_NOME, Replace A1_NOME, etc.)."""
    fields = set()
    # Alias->Field: SA1->A1_NOME, SC5->C5_NUM
    fields.update(re.findall(r'\w{2,3}->(\w{2,3}_\w+)', content))
    # Replace FIELD
    fields.update(re.findall(r'Replace\s+(\w{2,3}_\w+)', content, re.IGNORECASE))
    # Field in quotes/variables: "A1_NOME", 'C5_NUM'
    fields.update(re.findall(r'["\'](\w{2,3}_\w+)["\']', content))
    # Filter: must match Protheus field pattern (XX_XXXXXX)
    valid = set()
    for f in fields:
        f = f.upper()
        if re.match(r'^[A-Z][A-Z0-9]_\w+$', f):
            valid.add(f)
    return sorted(valid)


def _extract_params(content: str) -> dict:
    """Extract SX6 parameters and SX1 groups from function code.

    Returns: {"sx6": [{"var": "MV_XXX", "default": "valor"}], "sx1": ["GRP"]}
    """
    sx6 = {}
    sx1 = set()

    # SuperGetMV("MV_XXX", default_lógico, "default_valor")
    for m in re.finditer(
        r'SuperGetMV\s*\(\s*["\'](\w+)["\']\s*(?:,\s*[^,]*\s*,\s*(["\'][^"\']*["\']|[\w.]+))?',
        content, re.IGNORECASE
    ):
        var = m.group(1).upper()
        default = (m.group(2) or "").strip("\"'") if m.group(2) else ""
        sx6[var] = default

    # GetMV("MV_XXX") / GetNewPar("MV_XXX", default)
    for m in re.finditer(
        r'(?:GetMV|GetNewPar)\s*\(\s*["\'](\w+)["\']\s*(?:,\s*(["\'][^"\']*["\']|[\w.]+))?',
        content, re.IGNORECASE
    ):
        var = m.group(1).upper()
        if var not in sx6:
            default = (m.group(2) or "").strip("\"'") if m.group(2) else ""
            sx6[var] = default

    # FWMVPar("MV_XXX")
    for m in re.finditer(r'FWMVPar\s*\(\s*["\'](\w+)["\']', content, re.IGNORECASE):
        var = m.group(1).upper()
        if var not in sx6:
            sx6[var] = ""

    # Pergunte("GRP") / FWGetSX1("GRP")
    for m in re.finditer(r'(?:Pergunte|FWGetSX1)\s*\(\s*["\'](\w+)["\']', content, re.IGNORECASE):
        sx1.add(m.group(1).upper())

    result = {
        "sx6": [{"var": k, "default": v} for k, v in sorted(sx6.items())],
        "sx1": sorted(sx1),
    }
    return result


def _extract_operacoes_escrita(content: str, file_name: str) -> list[dict]:
    """Extract structured write operations from source code.

    Detects RecLock (insert/update), TcSqlExec (direct SQL), dbDelete,
    and maps which fields are assigned inside each block.
    Returns list of dicts with: funcao, tipo, tabela, campos, origens, condicao, linha.
    """
    operacoes = []
    lines = content.split('\n')

    # --- Find function boundaries for context ---
    func_ranges = []  # (start_line, name)
    func_re = re.compile(
        r'(?:Static\s+|User\s+|Main\s+)?Function\s+(\w+)',
        re.IGNORECASE
    )
    for i, line in enumerate(lines):
        m = func_re.search(line)
        if m:
            func_ranges.append((i, m.group(1)))

    def _get_func_at_line(line_no: int) -> str:
        """Return function name that contains this line."""
        current_func = file_name.replace('.prw', '').replace('.PRW', '').replace('.tlpp', '').replace('.TLPP', '')
        for start, name in func_ranges:
            if start <= line_no:
                current_func = name
            else:
                break
        return current_func

    # --- Detect IF conditions surrounding a line ---
    def _find_enclosing_condition(line_no: int) -> str:
        """Walk backward to find the nearest IF/ELSE condition."""
        indent_at_line = len(lines[line_no]) - len(lines[line_no].lstrip()) if line_no < len(lines) else 0
        for j in range(line_no - 1, max(line_no - 30, -1), -1):
            if j < 0 or j >= len(lines):
                continue
            stripped = lines[j].strip().upper()
            line_indent = len(lines[j]) - len(lines[j].lstrip())
            if line_indent < indent_at_line or j == line_no - 1:
                if stripped.startswith('IF ') or stripped.startswith('IF('):
                    cond = lines[j].strip()
                    # Clean up: remove IF prefix
                    cond = re.sub(r'^(?:IF|ELSEIF)\s+', '', cond, flags=re.IGNORECASE).strip()
                    return cond[:120]
                elif stripped.startswith('ELSE'):
                    # Walk further back to find the IF
                    for k in range(j - 1, max(j - 30, -1), -1):
                        if k < 0 or k >= len(lines):
                            continue
                        s2 = lines[k].strip().upper()
                        if s2.startswith('IF ') or s2.startswith('IF('):
                            cond = lines[k].strip()
                            cond = re.sub(r'^IF\s+', '', cond, flags=re.IGNORECASE).strip()
                            return f"NOT ({cond[:100]})"
                        elif s2.startswith('ENDIF') or s2.startswith('END IF'):
                            break
                    return "ELSE"
        return ""

    # --- Pattern 1: RecLock blocks ---
    reclock_re = re.compile(
        r'RecLock\s*\(\s*["\'](\w+)["\']\s*,\s*\.(T|F)\.\s*\)',
        re.IGNORECASE
    )
    for i, line in enumerate(lines):
        m = reclock_re.search(line)
        if m:
            tabela = m.group(1).upper()
            is_insert = m.group(2).upper() == 'T'
            campos = []
            origens = {}

            # Scan forward for field assignments until MsUnlock/MsUnLock/dbCommit
            for j in range(i + 1, min(i + 80, len(lines))):
                if j >= len(lines):
                    break
                sl = lines[j].strip()
                su = sl.upper()
                if 'MSUNLOCK' in su or 'MSUNLCK' in su or 'DBCOMMIT' in su or 'DBRUNLOCK' in su:
                    break
                # Match: TABLE->FIELD := VALUE or TABLE->(FIELD := VALUE)
                fm = re.match(
                    r'(?:\w+->)?(\w+_\w+)\s*:=\s*(.+)',
                    sl, re.IGNORECASE
                )
                if fm:
                    campo = fm.group(1).upper()
                    valor = fm.group(2).strip().rstrip(',')
                    # Classify origin
                    if campo.startswith(tabela[:2]) or campo.startswith(tabela[1:3]):
                        campos.append(campo)
                        # Classify value source
                        if re.match(r'^["\'].*["\']$', valor):
                            origens[campo] = f"literal:{valor[:50]}"
                        elif re.match(r'^M->', valor):
                            origens[campo] = f"tela:{valor[:50]}"
                        elif re.match(r'^[\d.]+$', valor):
                            origens[campo] = f"literal:{valor}"
                        elif '->' in valor:
                            origens[campo] = f"tabela:{valor[:50]}"
                        elif re.search(r'U_\w+|[A-Z]\w+\(', valor):
                            origens[campo] = f"funcao:{valor[:50]}"
                        else:
                            origens[campo] = f"variavel:{valor[:50]}"

            if campos:
                operacoes.append({
                    "funcao": _get_func_at_line(i),
                    "tipo": "reclock_inc" if is_insert else "reclock_alt",
                    "tabela": tabela,
                    "campos": campos,
                    "origens": origens,
                    "condicao": _find_enclosing_condition(i),
                    "linha": i + 1,
                })

    # --- Pattern 2: TcSqlExec with UPDATE/INSERT/DELETE ---
    sql_re = re.compile(
        r'TcSqlExec\s*\(',
        re.IGNORECASE
    )
    for i, line in enumerate(lines):
        if sql_re.search(line):
            # Try to find the SQL string (may span multiple lines)
            sql_block = ' '.join(lines[max(0, i-5):min(len(lines), i+3)])
            # Detect UPDATE
            um = re.search(r'UPDATE\s+\S*?(\w{3})(?:\d+)?\s+SET\s+(.+?)(?:WHERE|$)', sql_block, re.IGNORECASE)
            if um:
                tabela = um.group(1).upper()
                set_clause = um.group(2)
                campos = re.findall(r'(\w+_\w+)\s*=', set_clause)
                campos = [c.upper() for c in campos]
                if campos:
                    operacoes.append({
                        "funcao": _get_func_at_line(i),
                        "tipo": "sql_update",
                        "tabela": tabela,
                        "campos": campos,
                        "origens": {},
                        "condicao": "",
                        "linha": i + 1,
                    })
            # Detect DELETE
            dm = re.search(r'DELETE\s+(?:FROM\s+)?\S*?(\w{3})(?:\d+)?', sql_block, re.IGNORECASE)
            if dm and not um:
                tabela = dm.group(1).upper()
                operacoes.append({
                    "funcao": _get_func_at_line(i),
                    "tipo": "sql_delete",
                    "tabela": tabela,
                    "campos": [],
                    "origens": {},
                    "condicao": "",
                    "linha": i + 1,
                })

    # --- Pattern 3: dbDelete ---
    for i, line in enumerate(lines):
        m = re.search(r'(\w{2,3})->\s*\(\s*dbDelete', line, re.IGNORECASE)
        if m:
            operacoes.append({
                "funcao": _get_func_at_line(i),
                "tipo": "db_delete",
                "tabela": m.group(1).upper(),
                "campos": [],
                "origens": {},
                "condicao": _find_enclosing_condition(i),
                "linha": i + 1,
            })

    return operacoes


def _split_large_chunk(chunk: dict) -> list[dict]:
    content = chunk["content"]
    if len(content) <= MAX_CHUNK_CHARS:
        return [chunk]
    sub_chunks = []
    start = 0
    part = 0
    step = MAX_CHUNK_CHARS - OVERLAP_CHARS  # 3600 — guaranteed forward progress
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


def _detect_source_type(content: str) -> str:
    """Detect the type of Protheus source file."""
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


def _split_into_chunks(content: str, file_name: str) -> list[dict]:
    """Split source into function-level chunks. Memory-efficient: uses line offset
    table + integer classification instead of string copies."""
    # ── 1. Build line index (single pass, only ints) ──
    offsets = _build_line_offsets(content)
    line_types = _classify_lines(content, offsets)
    num_lines = len(offsets)

    # ── 2. Find function declarations via regex, convert to line numbers ──
    func_pattern = re.compile(
        r'((?:Static\s+|User\s+|Main\s+)?Function\s+(\w+)'
        r'|WSMETHOD\s+(\w+)\s+WS(?:RECEIVE|SEND)'
        r'|METHOD\s+(\w+)\s*\([^)]*\)\s*CLASS\s+\w+)',
        re.IGNORECASE
    )

    func_matches = []  # list of (line_number, name)
    for m in func_pattern.finditer(content):
        line_no = bisect.bisect_right(offsets, m.start()) - 1
        name = m.group(2) or m.group(3) or m.group(4) or "unknown"
        func_matches.append((line_no, name))

    if not func_matches:
        return [_split_large_chunk({"id": f"{file_name}::full", "content": content, "funcao": "_full"})][0]

    # ── 3. For each function, walk backward using line_types (ints only) ──
    header_starts = []
    for idx, (func_line, _name) in enumerate(func_matches):
        prev_limit = func_matches[idx - 1][0] if idx > 0 else -1
        header_line = func_line
        for j in range(func_line - 1, prev_limit, -1):
            lt = line_types[j]
            if lt == 0:  # code — stop
                break
            # comment (1) or blank (2) — include in header
            header_line = j
        header_starts.append(header_line)

    # ── 4. Build chunks using offsets (only final string slices) ──
    raw_chunks = []

    # File header (before first function's header)
    first_header_off = offsets[header_starts[0]]
    file_header = content[:first_header_off].strip()
    if file_header:
        raw_chunks.append({"id": f"{file_name}::header", "content": file_header, "funcao": "_header"})

    # Each function chunk
    for i, (_func_line, name) in enumerate(func_matches):
        start_off = offsets[header_starts[i]]
        if i + 1 < len(func_matches):
            end_off = offsets[header_starts[i + 1]]
        else:
            end_off = len(content)
        chunk_content = content[start_off:end_off].strip()
        raw_chunks.append({"id": f"{file_name}::{name}", "content": chunk_content, "funcao": name})

    # ── 5. Split oversized chunks ──
    chunks = []
    for chunk in raw_chunks:
        chunks.extend(_split_large_chunk(chunk))
    return chunks


def _detect_encoding(file_path: Path) -> str:
    """Detect file encoding without reading full content."""
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


def parse_source(file_path: Path, include_chunks: bool = False) -> dict:
    """Parse an ADVPL/TLPP source file.

    Extracts: functions, user functions, PEs, tables (read/write),
    includes, ExecAutos, call graph (calls_u, calls_execblock),
    field references, encoding, and optionally chunks for indexing.
    """
    content = _read_file(file_path)
    funcoes = _extract_functions(content)
    lines_of_code = len([l for l in content.splitlines() if l.strip() and not l.strip().startswith("//")])

    source_type = _detect_source_type(content)
    ws_structures = _extract_ws_structures(content) if source_type == "webservice" else {}

    result = {
        "arquivo": file_path.name,
        "caminho": str(file_path),
        "source_type": source_type,
        "funcoes": funcoes,
        "user_funcs": _extract_user_functions(content),
        "pontos_entrada": _extract_point_of_entry(_extract_user_functions(content)),
        "tabelas_ref": _extract_tables(content),
        "write_tables": _extract_write_tables(content),
        "reclock_tables": _extract_reclock_tables(content),
        "includes": _extract_includes(content),
        "exec_autos": _extract_exec_autos(content),
        "calls_u": _extract_calls_u(content),
        "calls_execblock": _extract_calls_execblock(content),
        "fields_ref": _extract_fields_ref(content),
        "ws_structures": ws_structures,
        "lines_of_code": lines_of_code,
        "encoding": _detect_encoding(file_path),
        "hash": hashlib.md5(content.encode(errors="replace")).hexdigest(),
        "operacoes_escrita": _extract_operacoes_escrita(content, file_path.name),
    }
    if include_chunks:
        result["chunks"] = _split_into_chunks(content, file_path.name)
    return result
