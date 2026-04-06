# backend/services/padrao_tools.py
"""Tools to query the standard Protheus source database (padrao.db).

These tools expose padrao.db data for the Analista pipeline —
standard source metadata, ExecBlocks (PEs), functions, and source code snippets.
"""
import json
from pathlib import Path
from app.services.workspace.padrao_database import PadraoDB

def _resolve_padrao_db_path() -> Path:
    """Resolve path do padrao.db usando mesma logica do workspace_populator."""
    import sys
    if getattr(sys, 'frozen', False):
        base = Path(sys.executable).parent
    else:
        base = Path(__file__).parent.parent.parent.parent
    return base / "db" / "padrao.db"

PADRAO_DB_PATH = _resolve_padrao_db_path()


def _get_padrao_db() -> PadraoDB:
    db = PadraoDB(PADRAO_DB_PATH)
    db.initialize()
    return db


def tool_fonte_padrao(arquivo: str) -> dict:
    """Get metadata and functions for a standard source file.

    Args:
        arquivo: Source filename (e.g., 'MATA410' or 'MATA410.prw')

    Returns:
        {arquivo, modulo, lines_of_code, tipo, funcoes: [{nome, tipo, assinatura}], encontrado}
    """
    if not PADRAO_DB_PATH.exists():
        return {"encontrado": False, "msg": "padrao.db not found"}

    db = _get_padrao_db()
    try:
        # Normalize: add .prw if not present, try both cases
        arquivo_clean = arquivo.strip()
        if "." not in arquivo_clean:
            arquivo_clean += ".prw"

        fonte = db.execute(
            "SELECT arquivo, modulo, lines_of_code, tipo FROM fontes WHERE UPPER(arquivo) LIKE ?",
            (f"%{arquivo_clean.upper().replace('.PRW', '')}%",)
        ).fetchone()

        if not fonte:
            return {"encontrado": False, "arquivo": arquivo}

        funcoes = db.execute(
            "SELECT nome, tipo, assinatura, linha_inicio FROM funcoes WHERE arquivo = ? ORDER BY linha_inicio",
            (fonte["arquivo"],)
        ).fetchall()

        return {
            "encontrado": True,
            "arquivo": fonte["arquivo"],
            "modulo": fonte["modulo"] or "",
            "lines_of_code": fonte["lines_of_code"] or 0,
            "tipo": fonte["tipo"] or "",
            "funcoes": [
                {"nome": f["nome"], "tipo": f["tipo"], "assinatura": (f["assinatura"] if "assinatura" in f.keys() else "") or "",
                 "linha": (f["linha_inicio"] if "linha_inicio" in f.keys() else 0) or 0}
                for f in funcoes
            ],
        }
    finally:
        db.close()


def tool_pes_disponiveis(rotina: str) -> list[dict]:
    """List all ExecBlocks (entry points) available in a standard routine.

    Args:
        rotina: Routine name (e.g., 'MATA410')

    Returns:
        List of {nome_pe, funcao, arquivo, parametros, tipo_retorno_inferido, linha, operacao, contexto}
    """
    if not PADRAO_DB_PATH.exists():
        return []

    db = _get_padrao_db()
    try:
        rotina_clean = rotina.strip().upper()
        if "." not in rotina_clean:
            rotina_clean += ".PRW"

        # Search in execblocks by arquivo
        rows = db.execute(
            "SELECT nome_pe, funcao, arquivo, parametros, tipo_retorno_inferido, "
            "linha, operacao, contexto, comentario "
            "FROM execblocks WHERE UPPER(arquivo) LIKE ? ORDER BY linha",
            (f"%{rotina_clean.replace('.PRW', '')}%",)
        ).fetchall()

        def _row_to_dict(r):
            d = dict(r) if hasattr(r, 'keys') else r
            return d

        return [
            {
                "nome_pe": _row_to_dict(r).get("nome_pe", ""),
                "funcao": _row_to_dict(r).get("funcao", ""),
                "arquivo": _row_to_dict(r).get("arquivo", ""),
                "parametros": _row_to_dict(r).get("parametros", "") or "",
                "tipo_retorno": _row_to_dict(r).get("tipo_retorno_inferido", "nil") or "nil",
                "linha": _row_to_dict(r).get("linha", 0) or 0,
                "operacao": _row_to_dict(r).get("operacao", "") or "",
                "contexto": _row_to_dict(r).get("contexto", "") or "",
                "comentario": _row_to_dict(r).get("comentario", "") or "",
            }
            for r in rows
        ]
    finally:
        db.close()


def tool_codigo_pe(nome_pe: str) -> list[dict]:
    """Get the source code snippet around where a PE is called in the standard source.

    Args:
        nome_pe: PE name (e.g., 'MA410COR')

    Returns:
        List of {nome_pe, arquivo, funcao, linha, codigo, parametros, tipo_retorno}
    """
    if not PADRAO_DB_PATH.exists():
        return []

    db = _get_padrao_db()
    try:
        pes = db.search_pe(nome_pe)
        if not pes:
            return []

        results = []
        for pe in pes[:5]:  # Limit to 5 occurrences
            fonte = db.execute(
                "SELECT caminho FROM fontes WHERE arquivo = ?", (pe["arquivo"],)
            ).fetchone()

            codigo = "[Arquivo não encontrado]"
            if fonte:
                file_path = Path(fonte["caminho"])
                if file_path.exists():
                    try:
                        from app.services.workspace.padrao_parser import _read_file
                        content = _read_file(file_path)
                        lines = content.split('\n')
                        pe_line = pe["linha"] - 1
                        start = max(0, pe_line - 10)
                        end = min(len(lines), pe_line + 20)
                        code_lines = []
                        for idx in range(start, end):
                            marker = " >>> " if idx == pe_line else "     "
                            code_lines.append(f"{idx + 1:5d}{marker}{lines[idx]}")
                        codigo = '\n'.join(code_lines)
                    except Exception:
                        codigo = "[Erro ao ler arquivo]"

            results.append({
                "nome_pe": pe["nome_pe"],
                "arquivo": pe["arquivo"],
                "funcao": pe["funcao"],
                "linha": pe["linha"],
                "parametros": pe.get("parametros", ""),
                "tipo_retorno": pe.get("tipo_retorno_inferido", "nil"),
                "operacao": pe.get("operacao", ""),
                "codigo": codigo,
            })

        return results
    finally:
        db.close()


def tool_buscar_funcao_padrao(nome: str) -> list[dict]:
    """Search functions in the standard source database.

    Args:
        nome: Function name or partial name

    Returns:
        List of {nome, tipo, arquivo, assinatura, linha}
    """
    if not PADRAO_DB_PATH.exists():
        return []

    db = _get_padrao_db()
    try:
        results = db.search_funcao(nome)
        return [
            {
                "nome": r["nome"],
                "tipo": r.get("tipo", ""),
                "arquivo": r["arquivo"],
                "assinatura": r.get("assinatura", ""),
                "linha": r.get("linha_inicio", 0),
            }
            for r in results[:20]  # Limit results
        ]
    finally:
        db.close()
