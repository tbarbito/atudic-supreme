"""Auto-resumo generator — extracts meaningful summaries from source code metadata and patterns.

No LLM needed. Generates searchable descriptions from:
- Write operations (RecLock tables + fields)
- Help/Alert messages (explain WHY something blocks)
- Parameters used (SuperGetMV)
- Conditional behavior (FunName checks)
- PE names and types
- Return .F. patterns (blocks/validations)
"""
import json
import re
import sqlite3
from pathlib import Path


def _extract_messages(content: str) -> list[str]:
    """Extract Help, Alert, MsgStop messages from code."""
    msgs = []
    # Help messages
    for m in re.finditer(r'Help\s*\([^,]*,[^,]*,[^,]*,[^,]*,\s*["\']([^"\']{10,})["\']', content):
        msgs.append(m.group(1).strip()[:120])
    # FWAlert messages
    for m in re.finditer(r'FWAlert(?:Warning|Error|Success)\s*\(\s*["\']([^"\']{10,})["\']', content):
        msgs.append(m.group(1).strip()[:120])
    # MsgStop/MsgAlert/MsgInfo
    for m in re.finditer(r'Msg(?:Stop|Alert|Info)\s*\(\s*["\']([^"\']{10,})["\']', content):
        msgs.append(m.group(1).strip()[:120])
    return msgs


def _extract_parameters(content: str) -> list[str]:
    """Extract SuperGetMV parameter names."""
    params = []
    for m in re.finditer(r'SuperGetM[Vv]\s*\(\s*["\']([^"\']+)["\']', content):
        params.append(m.group(1).strip())
    return list(set(params))


def _extract_funname_checks(content: str) -> list[str]:
    """Extract FunName() conditional checks — shows which routine context matters."""
    checks = []
    for m in re.finditer(r'FunName\s*\(\s*\)\s*(?:\$|==)\s*["\']([^"\']+)["\']', content):
        checks.append(m.group(1).strip())
    return list(set(checks))


def _has_block_pattern(content: str) -> bool:
    """Check if function blocks execution (Return .F.)"""
    return bool(re.search(r'(?:Return|lRet\s*:=)\s*\.F\.', content, re.IGNORECASE))


def _extract_field_checks(content: str) -> list[str]:
    """Extract field comparisons like E2_TIPO == 'PA'."""
    checks = []
    for m in re.finditer(r'(\w{2,3}_\w+)\s*(?:==|!=|<>)\s*["\'](\w+)["\']', content):
        checks.append(f"{m.group(1)}={m.group(2)}")
    return list(set(checks[:8]))


def generate_auto_resumo(funcao: str, tipo: str, assinatura: str,
                          tabelas_ref: list, campos_ref: list,
                          chama: list, params_data: dict,
                          content: str, write_tables: list = None,
                          pontos_entrada: list = None) -> str:
    """Generate automatic resumo for a single function."""
    parts = []

    # Type identification
    tipo_lower = (tipo or "").lower()
    if "user function" in tipo_lower:
        # Check if it's a PE by name patterns
        pe_patterns = ["_PE", "TOK", "BLQ", "INC", "ALT", "DEL", "GRV", "FIM", "END", "BUT", "ROT", "FIN"]
        is_pe = any(p in funcao.upper() for p in pe_patterns)
        if is_pe:
            parts.append(f"PE {funcao}")
        else:
            parts.append(f"User Function {funcao}")
    elif "static" in tipo_lower:
        parts.append(f"Static {funcao}")
    else:
        parts.append(f"{tipo} {funcao}" if tipo else funcao)

    # Write operations
    if write_tables:
        parts.append(f"Grava: {', '.join(write_tables[:5])}")

    # Read tables
    if tabelas_ref:
        reads = [t for t in tabelas_ref if t not in (write_tables or [])]
        if reads:
            parts.append(f"Lê: {', '.join(reads[:5])}")

    # FunName checks — contextual behavior
    if content:
        funname_checks = _extract_funname_checks(content)
        if funname_checks:
            parts.append(f"Contexto: {', '.join(funname_checks[:3])}")

        # Field checks
        field_checks = _extract_field_checks(content)
        if field_checks:
            parts.append(f"Valida: {', '.join(field_checks[:5])}")

        # Block pattern
        if _has_block_pattern(content):
            parts.append("BLOQUEIA execução")

        # Messages — the most valuable part
        messages = _extract_messages(content)
        if messages:
            for msg in messages[:3]:
                parts.append(f'Msg: "{msg}"')

        # Parameters
        params_code = _extract_parameters(content)
        if params_code:
            parts.append(f"Params: {', '.join(params_code[:4])}")

    # Params from funcao_docs
    if params_data:
        sx6 = params_data.get("sx6", [])
        if sx6:
            param_names = [p["var"] for p in sx6[:3]]
            if param_names and not any("Params:" in p for p in parts):
                parts.append(f"Params: {', '.join(param_names)}")

    # Functions called
    if chama:
        parts.append(f"Chama: {', '.join(chama[:4])}")

    # PEs implemented
    if pontos_entrada:
        parts.append(f"PEs: {', '.join(pontos_entrada[:3])}")

    return ". ".join(parts)


def generate_all_auto_resumos(db_path: Path) -> dict:
    """Generate auto-resumos for ALL functions in funcao_docs.

    Returns summary: {total, updated, errors}
    """
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")

    # Get all functions
    funcs = conn.execute("""
        SELECT fd.arquivo, fd.funcao, fd.tipo, fd.assinatura,
               fd.tabelas_ref, fd.campos_ref, fd.chama, fd.params
        FROM funcao_docs fd
    """).fetchall()

    # Get write_tables and pontos_entrada per arquivo from fontes
    fonte_meta = {}
    for row in conn.execute("SELECT arquivo, write_tables, pontos_entrada FROM fontes").fetchall():
        try:
            wt = json.loads(row[1]) if row[1] else []
        except (json.JSONDecodeError, TypeError):
            wt = []
        try:
            pe = json.loads(row[2]) if row[2] else []
        except (json.JSONDecodeError, TypeError):
            pe = []
        fonte_meta[row[0]] = {"write_tables": wt, "pontos_entrada": pe}

    # Get code content from chunks (indexed by arquivo+funcao)
    chunk_content = {}
    for row in conn.execute("SELECT arquivo, funcao, content FROM fonte_chunks").fetchall():
        chunk_content[(row[0], row[1])] = row[2] or ""

    total = len(funcs)
    updated = 0
    errors = 0
    batch = []

    for row in funcs:
        arquivo, funcao, tipo, assinatura = row[0], row[1], row[2], row[3]
        try:
            tabs_ref = json.loads(row[4]) if row[4] else []
        except (json.JSONDecodeError, TypeError):
            tabs_ref = []
        try:
            campos_ref = json.loads(row[5]) if row[5] else []
        except (json.JSONDecodeError, TypeError):
            campos_ref = []
        try:
            chama = json.loads(row[6]) if row[6] else []
        except (json.JSONDecodeError, TypeError):
            chama = []
        try:
            params = json.loads(row[7]) if row[7] else {}
        except (json.JSONDecodeError, TypeError):
            params = {}

        content = chunk_content.get((arquivo, funcao), "")
        meta = fonte_meta.get(arquivo, {})

        try:
            resumo = generate_auto_resumo(
                funcao=funcao,
                tipo=tipo,
                assinatura=assinatura,
                tabelas_ref=tabs_ref,
                campos_ref=campos_ref,
                chama=chama,
                params_data=params,
                content=content,
                write_tables=meta.get("write_tables", []),
                pontos_entrada=meta.get("pontos_entrada", []),
            )
            batch.append((resumo, arquivo, funcao))
            updated += 1
        except Exception as e:
            errors += 1

        if len(batch) >= 500:
            conn.executemany(
                "UPDATE funcao_docs SET resumo_auto = ? WHERE arquivo = ? AND funcao = ?",
                batch
            )
            conn.commit()
            batch = []

    if batch:
        conn.executemany(
            "UPDATE funcao_docs SET resumo_auto = ? WHERE arquivo = ? AND funcao = ?",
            batch
        )
        conn.commit()

    # Now generate proposito_auto per arquivo (concatenation of resumo_auto)
    arquivos = conn.execute("""
        SELECT arquivo, GROUP_CONCAT(funcao || ': ' || resumo_auto, ' | ')
        FROM funcao_docs
        WHERE resumo_auto IS NOT NULL AND resumo_auto != ''
        GROUP BY arquivo
    """).fetchall()

    for arq_row in arquivos:
        arquivo, concat = arq_row
        # Truncate to 2000 chars
        proposito_auto = concat[:2000] if concat else ""
        conn.execute(
            "INSERT OR REPLACE INTO propositos (chave, proposito_auto, proposito) "
            "VALUES (?, ?, COALESCE((SELECT proposito FROM propositos WHERE chave = ?), ''))",
            (arquivo, proposito_auto, arquivo)
        )

    conn.commit()
    prop_count = conn.execute("SELECT COUNT(*) FROM propositos WHERE proposito_auto != ''").fetchone()[0]

    conn.close()
    return {"total": total, "updated": updated, "errors": errors, "propositos": prop_count}


def generate_padrao_auto_resumos(padrao_db_path: Path) -> dict:
    """Generate auto-resumos for ALL functions in padrao.db funcoes table.

    Adapts the same logic for the standard Protheus source database.
    Adds resumo_auto column to funcoes table if not exists.

    Returns summary: {total, updated, errors}
    """
    conn = sqlite3.connect(str(padrao_db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    # Add resumo_auto column if not exists
    try:
        conn.execute("ALTER TABLE funcoes ADD COLUMN resumo_auto TEXT DEFAULT ''")
        conn.commit()
        print("[padrao-resumo] Added resumo_auto column to funcoes")
    except Exception:
        pass  # already exists

    # Get all functions
    funcs = conn.execute("""
        SELECT f.arquivo, f.nome, f.tipo, f.assinatura,
               f.tabelas_ref, f.campos_ref, f.calls, f.params
        FROM funcoes f
    """).fetchall()

    # Get write_tables per arquivo from fontes
    fonte_meta = {}
    for row in conn.execute("SELECT arquivo, write_tables FROM fontes").fetchall():
        try:
            wt = json.loads(row[1]) if row[1] else []
        except (json.JSONDecodeError, TypeError):
            wt = []
        fonte_meta[row[0]] = {"write_tables": wt}

    # Get execblocks per arquivo (PEs defined in each file)
    execblock_meta = {}
    for row in conn.execute("SELECT arquivo, nome_pe, operacao FROM execblocks").fetchall():
        if row[0] not in execblock_meta:
            execblock_meta[row[0]] = []
        execblock_meta[row[0]].append({"nome_pe": row[1], "operacao": row[2] or ""})

    # Get code content from chunks
    chunk_content = {}
    for row in conn.execute("SELECT arquivo, funcao, content FROM fonte_chunks").fetchall():
        chunk_content[(row[0], row[1])] = row[2] or ""

    total = len(funcs)
    updated = 0
    errors = 0
    batch = []

    for row in funcs:
        arquivo, funcao, tipo, assinatura = row[0], row[1], row[2], row[3]
        try:
            tabs_ref = json.loads(row[4]) if row[4] else []
        except (json.JSONDecodeError, TypeError):
            tabs_ref = []
        try:
            campos_ref = json.loads(row[5]) if row[5] else []
        except (json.JSONDecodeError, TypeError):
            campos_ref = []
        try:
            chama = json.loads(row[6]) if row[6] else []
        except (json.JSONDecodeError, TypeError):
            chama = []
        try:
            params = json.loads(row[7]) if row[7] else {}
        except (json.JSONDecodeError, TypeError):
            params = {}

        content = chunk_content.get((arquivo, funcao), "")
        meta = fonte_meta.get(arquivo, {})

        # Get PEs defined in this file
        pes_in_file = [eb["nome_pe"] for eb in execblock_meta.get(arquivo, [])]

        try:
            resumo = generate_auto_resumo(
                funcao=funcao,
                tipo=tipo,
                assinatura=assinatura,
                tabelas_ref=tabs_ref,
                campos_ref=campos_ref,
                chama=chama,
                params_data=params,
                content=content,
                write_tables=meta.get("write_tables", []),
                pontos_entrada=pes_in_file[:5] if pes_in_file else None,
            )
            batch.append((resumo, arquivo, funcao))
            updated += 1
        except Exception:
            errors += 1

        if len(batch) >= 1000:
            conn.executemany(
                "UPDATE funcoes SET resumo_auto = ? WHERE arquivo = ? AND nome = ?",
                batch
            )
            conn.commit()
            batch = []
            if updated % 10000 == 0:
                print(f"[padrao-resumo] Progress: {updated:,}/{total:,}")

    if batch:
        conn.executemany(
            "UPDATE funcoes SET resumo_auto = ? WHERE arquivo = ? AND nome = ?",
            batch
        )
        conn.commit()

    conn.execute("PRAGMA synchronous=FULL")
    conn.commit()
    conn.close()
    return {"total": total, "updated": updated, "errors": errors}
