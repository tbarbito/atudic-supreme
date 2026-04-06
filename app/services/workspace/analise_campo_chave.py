"""Análise de impacto para aumento de campo chave (SXG-aware).

Quando o usuário quer aumentar o tamanho de um campo que é compartilhado
via grupo SXG (ex: B1_COD, A1_COD), esta tool mapeia:
1. Campos no mesmo grupo SXG (mudam automaticamente)
2. Campos com F3 na tabela mas FORA do grupo (risco — alterar manualmente)
3. Fontes com PadR/PADR chumbado (risco — trunca o valor)
4. Fontes com TamSX3 dinâmico (ok — se adaptam)
5. Índices que podem estourar o limite de 250 chars
6. MsExecAuto e integrações afetadas
7. Campos custom sem grupo SXG que referenciam o campo
"""
import json
import re
import sqlite3
from pathlib import Path


def _get_db():
    from app.services.workspace.config import load_config, get_client_workspace
    from app.services.workspace.workspace_db import Database
    config = load_config(Path("config.json"))
    if not config or not config.active_client:
        return None
    client_dir = get_client_workspace(Path("workspace"), config.active_client)
    db_path = client_dir / "db" / "extrairpo.db"
    if not db_path.exists():
        return None
    db = Database(db_path)
    db.initialize()
    return db


def _safe_json(val):
    if not val:
        return []
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return []


def tool_analise_aumento_campo(tabela: str, campo: str, novo_tamanho: int = 0) -> dict:
    """Análise completa de impacto para aumento de tamanho de campo chave.

    Args:
        tabela: Tabela do campo (ex: SB1)
        campo: Campo a aumentar (ex: B1_COD)
        novo_tamanho: Novo tamanho desejado (0 = apenas análise)

    Returns:
        dict com seções: grupo_sxg, campos_grupo, campos_fora_grupo,
        padr_chumbado, tamsx3_ok, indices_risco, msexecauto, integracoes
    """
    db = _get_db()
    if not db:
        return {"erro": "Database not available"}

    try:
        # ── 1. Get campo info ─────────────────────────────────────────
        campo_info = db.execute(
            "SELECT campo, tipo, tamanho, titulo, f3, grpsxg FROM campos WHERE tabela=? AND campo=?",
            (tabela.upper(), campo.upper())
        ).fetchone()

        if not campo_info:
            return {"erro": f"Campo {tabela}.{campo} não encontrado"}

        campo_nome = campo_info[0]
        tipo = campo_info[1]
        tamanho_atual = campo_info[2]
        titulo = campo_info[3]
        f3 = campo_info[4] or ""
        grupo_sxg = campo_info[5] or ""

        result = {
            "campo": campo_nome,
            "tabela": tabela.upper(),
            "titulo": titulo,
            "tipo": tipo,
            "tamanho_atual": tamanho_atual,
            "novo_tamanho": novo_tamanho,
            "grupo_sxg": grupo_sxg,
        }

        # ── 2. Campos no mesmo grupo SXG ──────────────────────────────
        campos_grupo = []
        if grupo_sxg:
            rows = db.execute(
                "SELECT tabela, campo, titulo, tamanho, f3, custom FROM campos WHERE grpsxg=? ORDER BY tabela, campo",
                (grupo_sxg,)
            ).fetchall()
            for r in rows:
                campos_grupo.append({
                    "tabela": r[0], "campo": r[1], "titulo": r[2],
                    "tamanho": r[3], "f3": r[4] or "", "custom": r[5],
                })

            # Group info
            grp_info = db.execute(
                "SELECT total_campos FROM grupos_campo WHERE grupo=?", (grupo_sxg,)
            ).fetchone()
            result["grupo_info"] = {
                "grupo": grupo_sxg,
                "total_campos": grp_info[0] if grp_info else len(campos_grupo),
                "descricao": f"Grupo {grupo_sxg} — {len(campos_grupo)} campos mudam automaticamente via Configurador",
            }

            # Campos do grupo com tamanho DIFERENTE do atual (já inconsistentes)
            inconsistentes = [c for c in campos_grupo if c["tamanho"] != tamanho_atual]
            result["campos_inconsistentes"] = inconsistentes

        result["campos_grupo"] = campos_grupo
        result["total_campos_grupo"] = len(campos_grupo)

        # ── 3. Campos FORA do grupo mas com F3 na tabela ──────────────
        # Esses são o maior risco — referenciam o campo mas não mudam automaticamente
        campos_fora = []
        rows = db.execute(
            "SELECT tabela, campo, titulo, tamanho, custom, grpsxg FROM campos "
            "WHERE f3=? AND (grpsxg IS NULL OR grpsxg = '' OR grpsxg != ?)",
            (tabela.upper(), grupo_sxg)
        ).fetchall()
        for r in rows:
            campos_fora.append({
                "tabela": r[0], "campo": r[1], "titulo": r[2],
                "tamanho": r[3], "custom": r[4],
                "grupo_atual": r[5] or "NENHUM",
                "risco": "TAMANHO DIFERENTE" if r[3] != tamanho_atual else "Sem grupo SXG",
            })
        result["campos_fora_grupo"] = campos_fora
        result["total_campos_fora"] = len(campos_fora)

        # ── 4. Campos custom Z* que referenciam produto via F3 ──────
        # ONLY include campos that have F3 pointing to the analyzed table
        # (previously matched by name "COD"/"PROD" which gave 95% false positives)
        prefixo_campo = campo_nome[3:]  # ex: B1_COD → COD, B1_PRODUTO → PRODUTO
        campos_suspeitos = []
        if len(prefixo_campo) >= 3:
            # Primary: F3 = tabela (high confidence)
            rows = db.execute(
                "SELECT tabela, campo, titulo, tamanho, f3, grpsxg FROM campos "
                "WHERE custom=1 AND tipo='C' AND f3=? "
                "AND (grpsxg IS NULL OR grpsxg = '' OR grpsxg != ?)",
                (tabela.upper(), grupo_sxg)
            ).fetchall()
            for r in rows:
                campos_suspeitos.append({
                    "tabela": r[0], "campo": r[1], "titulo": r[2],
                    "tamanho": r[3], "f3": r[4] or "NENHUM",
                    "grupo": r[5] or "NENHUM",
                })
        result["campos_suspeitos_custom"] = campos_suspeitos

        # ── 5. PadR e Space() chumbado nos fontes ─────────────────────
        # Search for PadR(variable, SIZE) and Space(SIZE) hardcoded
        # Must check multiple sizes: current, common intermediate (15, 20, 23), and target
        padr_chumbado = []
        seen_padr = set()
        novo_tamanho_arg = result.get("novo_tamanho", 0)
        # Check sizes that would cause problems (anything < target or hardcoded)
        sizes_to_check = set()
        sizes_to_check.add(tamanho_atual)
        if novo_tamanho_arg:
            sizes_to_check.add(novo_tamanho_arg)
        # Common intermediate sizes for product codes
        for common_size in [15, 20, 23, 25, 30]:
            if common_size != novo_tamanho_arg:
                sizes_to_check.add(common_size)

        # Get fontes that reference this table (for broader search)
        fontes_da_tabela = set()
        try:
            for row in db.execute(
                "SELECT arquivo FROM fontes WHERE tabelas_ref LIKE ? OR write_tables LIKE ?",
                (f'%"{tabela}"%', f'%"{tabela}"%')
            ).fetchall():
                fontes_da_tabela.add(row[0])
        except Exception:
            pass

        try:
            for check_size in sorted(sizes_to_check):
                all_patterns = []
                # PadR patterns
                for p in [f"%PadR(%{check_size})%", f"%PadR(%, {check_size})%",
                          f"%PADR(%{check_size})%", f"%PADR(%, {check_size})%"]:
                    all_patterns.append(("PadR", p))
                # Space patterns
                for p in [f"%Space({check_size})%", f"%SPACE({check_size})%",
                          f"%space({check_size})%"]:
                    all_patterns.append(("Space", p))
                # SubStr patterns — SubStr(x, 1, SIZE) truncates the value
                for p in [f"%SubStr(%,{check_size})%", f"%SubStr(%, {check_size})%",
                          f"%SUBSTR(%,{check_size})%", f"%SUBSTR(%, {check_size})%",
                          f"%substr(%,{check_size})%", f"%substr(%, {check_size})%"]:
                    all_patterns.append(("SubStr", p))
                # Replicate patterns — Replicate(" ", SIZE) builds fixed-size key
                for p in [f"%Replicate(%{check_size})%", f"%REPLICATE(%{check_size})%",
                          f"%replicate(%{check_size})%"]:
                    all_patterns.append(("Replicate", p))
                # ParamBox with Space(SIZE) — fixed-size input field
                # Only check sizes that match the field being analyzed
                if check_size == tamanho_atual:
                    for p in [f"%aParamBox%Space({check_size})%", f"%aparambox%Space({check_size})%",
                              f"%aParamBox%SPACE({check_size})%"]:
                        all_patterns.append(("ParamBox", p))

                # Helper: extract code lines AND determine real confidence per-LINE
                def _extract_and_classify(arquivo, funcao, search_type, search_size):
                    """Get lines with the pattern and classify confidence per LINE.

                    Returns: (lines, real_confidence)
                    - 'alta': the LINE itself mentions the field/table
                    - 'media': the line has the pattern but doesn't mention the field
                    """
                    try:
                        chunks = db.execute(
                            "SELECT content FROM fonte_chunks WHERE arquivo=? ORDER BY CASE WHEN funcao=? THEN 0 ELSE 1 END",
                            (arquivo, funcao)
                        ).fetchall()
                        lines = []
                        line_mentions_field = False
                        st_lower = search_type.lower()
                        campo_lower = campo_nome.lower()
                        prefix_lower = prefixo_campo.lower()
                        tabela_lower = tabela.lower()
                        # Aliases for the table (e.g. SB1 -> B1_, "SB1")
                        table_indicators = [campo_lower, prefix_lower, tabela_lower, f'"{tabela_lower}"']

                        for chunk in chunks:
                            if not chunk[0]:
                                continue
                            for line in chunk[0].split("\n"):
                                ls = line.strip()
                                ll = ls.lower()
                                if st_lower in ll and str(search_size) in ls and len(ls) > 10:
                                    # Check if THIS LINE mentions the field/table
                                    if any(ind in ll for ind in table_indicators):
                                        line_mentions_field = True
                                    if ls not in lines:
                                        lines.append(ls[:180])
                                    if len(lines) >= 3:
                                        return lines, "alta" if line_mentions_field else "media"
                        return lines, "alta" if line_mentions_field else "media"
                    except Exception:
                        return [], "media"

                for tipo, pattern in all_patterns:
                    # Pass 1: Search in chunks that mention field/table
                    rows = db.execute(
                        "SELECT DISTINCT arquivo, funcao FROM fonte_chunks "
                        "WHERE content LIKE ? AND (LOWER(content) LIKE ? OR LOWER(content) LIKE ?)",
                        (pattern, f"%{campo_nome.lower()}%", f"%{prefixo_campo.lower()}%")
                    ).fetchall()
                    for r in rows:
                        key = f"{r[0]}::{r[1]}::{tipo.lower()}::{check_size}"
                        if key not in seen_padr:
                            seen_padr.add(key)
                            code_lines, real_confidence = _extract_and_classify(r[0], r[1] or "", tipo, check_size)
                            # Only include if we actually found matching lines
                            if code_lines:
                                padr_chumbado.append({
                                    "arquivo": r[0], "funcao": r[1] or "",
                                    "tipo": tipo, "tamanho": check_size,
                                    "confianca": real_confidence,
                                    "trechos": code_lines,
                                })

                    # Pass 2: Search in fontes that reference the table (medium confidence)
                    if fontes_da_tabela and check_size in (tamanho_atual, 15, 23):
                        rows2 = db.execute(
                            "SELECT DISTINCT arquivo, funcao FROM fonte_chunks "
                            "WHERE content LIKE ? AND arquivo IN ({})".format(
                                ",".join(f"'{a}'" for a in list(fontes_da_tabela)[:200])
                            ),
                            (pattern,)
                        ).fetchall()
                        for r in rows2:
                            key = f"{r[0]}::{r[1]}::{tipo.lower()}::{check_size}"
                            if key not in seen_padr:
                                seen_padr.add(key)
                                code_lines, _ = _extract_and_classify(r[0], r[1] or "", tipo, check_size)
                                if not code_lines:
                                    continue
                                padr_chumbado.append({
                                    "arquivo": r[0], "funcao": r[1] or "",
                                    "tipo": tipo, "tamanho": check_size,
                                    "confianca": "media",
                                    "trechos": code_lines,
                                })
        except Exception:
            pass
        result["padr_chumbado"] = padr_chumbado
        result["total_padr_chumbado"] = len(padr_chumbado)

        # ── 6. TamSX3 dinâmico (OK — se adaptam) ─────────────────────
        tamsx3_ok = []
        try:
            rows = db.execute(
                "SELECT DISTINCT arquivo FROM fonte_chunks "
                "WHERE LOWER(content) LIKE ?",
                (f"%tamsx3%{campo_nome.lower()}%",)
            ).fetchall()
            for r in rows:
                tamsx3_ok.append(r[0])
        except Exception:
            pass
        result["tamsx3_dinamico"] = tamsx3_ok
        result["total_tamsx3_ok"] = len(tamsx3_ok)

        # ── 7. Índices que podem estourar ─────────────────────────────
        indices_risco = []
        if novo_tamanho > 0:
            delta = novo_tamanho - tamanho_atual
            # Get all campos in the group to know which field names to look for
            campos_in_group = set(c["campo"] for c in campos_grupo)

            # Check all indices
            idx_rows = db.execute(
                "SELECT tabela, ordem, chave, custom FROM indices"
            ).fetchall()
            for r in idx_rows:
                chave = r[2] or ""
                # Check if any campo in this index is in the group
                campos_idx = [c.strip() for c in chave.replace("+", ",").split(",") if c.strip()]
                campos_affected = [c for c in campos_idx if c in campos_in_group]
                if not campos_affected:
                    continue

                # Estimate key length (approximate — fields have different sizes)
                # Count how many group fields are in this index
                n_group_fields = len(campos_affected)
                estimated_growth = n_group_fields * delta
                # Rough key length: count chars in the key expression
                key_len_approx = len(chave.replace("+", "").replace(" ", ""))
                new_key_len = key_len_approx + estimated_growth

                if new_key_len > 200:  # Warning threshold
                    indices_risco.append({
                        "tabela": r[0], "ordem": r[1],
                        "chave": chave[:100], "custom": r[3],
                        "campos_afetados": campos_affected,
                        "crescimento": estimated_growth,
                        "tamanho_estimado": new_key_len,
                        "risco": "PODE ESTOURAR" if new_key_len > 250 else "PROXIMO DO LIMITE",
                    })
        result["indices_risco"] = indices_risco
        result["total_indices_risco"] = len(indices_risco)

        # ── 8. MsExecAuto que passam esse campo ──────────────────────
        msexecauto = []
        # Map table to common routines
        _table_routine_map = {
            "SB1": ["MATA010"], "SA1": ["MATA030"], "SA2": ["MATA020"],
            "SC5": ["MATA410"], "SC7": ["MATA120"], "SF1": ["MATA103"],
        }
        routines = _table_routine_map.get(tabela.upper(), [])
        for rotina in routines:
            try:
                rows = db.execute(
                    "SELECT DISTINCT arquivo FROM fonte_chunks "
                    "WHERE LOWER(content) LIKE ? AND LOWER(content) LIKE ?",
                    (f"%msexecauto%", f"%{rotina.lower()}%")
                ).fetchall()
                for r in rows:
                    msexecauto.append({
                        "arquivo": r[0],
                        "rotina": rotina,
                        "risco": f"MsExecAuto({rotina}) — pode enviar campo com tamanho antigo",
                    })
            except Exception:
                pass
        result["msexecauto"] = msexecauto
        result["total_msexecauto"] = len(msexecauto)

        # ── 9. Integrações/WebServices que gravam na tabela ───────────
        integracoes = []
        try:
            rows = db.execute(
                "SELECT arquivo, modulo FROM fontes "
                "WHERE write_tables LIKE ? AND "
                "(UPPER(arquivo) LIKE '%WS%' OR UPPER(arquivo) LIKE '%INT%' "
                "OR UPPER(arquivo) LIKE '%API%' OR UPPER(arquivo) LIKE '%EDI%')",
                (f'%"{tabela.upper()}"%',)
            ).fetchall()
            for r in rows:
                integracoes.append({"arquivo": r[0], "modulo": r[1] or ""})
        except Exception:
            pass
        result["integracoes"] = integracoes
        result["total_integracoes"] = len(integracoes)

        # ── Summary ──────────────────────────────────────────────────
        result["resumo"] = {
            "mudam_automaticamente": len(campos_grupo),
            "precisam_ajuste_manual": len(campos_fora),
            "suspeitos_custom": len(campos_suspeitos),
            "padr_chumbado": len(padr_chumbado),
            "tamsx3_ok": len(tamsx3_ok),
            "indices_risco": len(indices_risco),
            "msexecauto": len(msexecauto),
            "integracoes": len(integracoes),
        }

        return result

    finally:
        db.close()
