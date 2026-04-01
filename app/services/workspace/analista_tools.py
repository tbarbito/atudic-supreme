"""Internal tools for the Analista AI — wraps existing analysis functions."""
import json
import re as _re_mod
from pathlib import Path
from app.services.workspace.config import load_config, get_client_workspace
from app.services.workspace.workspace_db import Database

WORKSPACE = Path("workspace")
CONFIG_PATH = Path("config.json")


def _get_db() -> Database:
    config = load_config(CONFIG_PATH)
    client_dir = get_client_workspace(WORKSPACE, config.active_client)
    db_path = client_dir / "db" / "extrairpo.db"
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


def tool_analise_impacto(tabela: str, campo: str = "", alteracao: str = "novo_campo") -> dict:
    """Run impact analysis for a table/field change. Returns filtered results (write-only)."""
    db = _get_db()
    try:
        # Get fontes that WRITE to this table (bom senso: ignore read-only)
        fontes_rows = db.execute(
            "SELECT arquivo, modulo, write_tables, pontos_entrada, lines_of_code "
            "FROM fontes WHERE write_tables LIKE ?",
            (f'%"{tabela}"%',),
        ).fetchall()

        fontes = []
        for r in fontes_rows:
            fontes.append({
                "arquivo": r[0],
                "modulo": r[1] or "",
                "write_tables": _safe_json(r[2]),
                "pontos_entrada": _safe_json(r[3]),
                "loc": r[4] or 0,
            })

        # Get triggers related to this table
        gatilhos = []
        gat_rows = db.execute(
            "SELECT campo_origem, campo_destino, regra, tipo FROM gatilhos WHERE tabela=?",
            (tabela,),
        ).fetchall()
        for g in gat_rows:
            gatilhos.append({
                "campo_origem": g[0], "campo_destino": g[1],
                "regra": g[2] or "", "tipo": g[3] or "",
            })

        # Get existing custom fields
        campos_custom = []
        cc_rows = db.execute(
            "SELECT campo, tipo, tamanho, titulo, descricao FROM campos WHERE upper(tabela)=? AND custom=1",
            (tabela.upper(),),
        ).fetchall()
        for c in cc_rows:
            campos_custom.append({
                "campo": c[0], "tipo": c[1], "tamanho": c[2],
                "titulo": c[3] or "", "descricao": c[4] or "",
            })

        # Get fontes with ExecBlock calls that write to this table
        # (ExecBlock/MsExecAuto are indirect calls that may skip validations)
        exec_autos = []
        ea_rows = db.execute(
            "SELECT arquivo, modulo, calls_execblock, lines_of_code "
            "FROM fontes WHERE calls_execblock IS NOT NULL AND calls_execblock != '[]' "
            "AND write_tables LIKE ?",
            (f'%"{tabela}"%',),
        ).fetchall()
        for r in ea_rows:
            execs = _safe_json(r[2])
            if execs:
                exec_autos.append({
                    "arquivo": r[0], "modulo": r[1] or "",
                    "exec_autos": execs, "loc": r[3] or 0,
                })

        # Also search for MsExecAuto pattern in source content via includes
        # Fontes that call ExecBlock to routines related to this table
        ea_rows2 = db.execute(
            "SELECT arquivo, modulo, calls_execblock, lines_of_code "
            "FROM fontes WHERE calls_execblock IS NOT NULL AND calls_execblock != '[]' "
            "AND arquivo NOT IN (SELECT arquivo FROM fontes WHERE write_tables LIKE ?)",
            (f'%"{tabela}"%',),
        ).fetchall()
        for r in ea_rows2:
            execs = _safe_json(r[2])
            # Check if any execblock name relates to table routines (MATA120, etc)
            relevant = [e for e in execs if any(kw in e.upper() for kw in ["MATA", "MATC", "MATX", tabela[:2]])]
            if relevant:
                exec_autos.append({
                    "arquivo": r[0], "modulo": r[1] or "",
                    "exec_autos": relevant, "loc": r[3] or 0,
                })

        # Search for MsExecAuto calls to routines that manage this table
        # Critical for mandatory field analysis — these automated calls may not handle new required fields
        _table_routine_map = {
            "SA1": ["MATA030"], "SA2": ["MATA020"], "SB1": ["MATA010"],
            "SC5": ["MATA410"], "SC6": ["MATA410"], "SC7": ["MATA120"],
            "SC1": ["MATA110"], "SF1": ["MATA103"], "SF2": ["MATA460"],
            "SE1": ["FINA040"], "SE2": ["FINA050"], "SA3": ["MATA040"],
            "SA4": ["MATA050"], "SD1": ["MATA101", "MATA103"], "SD2": ["MATA461"],
        }
        msexecauto_fontes = []
        routines = _table_routine_map.get(tabela.upper(), [])
        if routines:
            for rotina in routines:
                ea_chunks = db.execute(
                    "SELECT DISTINCT arquivo FROM fonte_chunks "
                    "WHERE LOWER(content) LIKE ? AND LOWER(content) LIKE ?",
                    (f"%msexecauto%", f"%{rotina.lower()}%"),
                ).fetchall()
                for r in ea_chunks:
                    if not any(x["arquivo"] == r[0] for x in msexecauto_fontes):
                        msexecauto_fontes.append({
                            "arquivo": r[0],
                            "rotina_chamada": rotina,
                            "risco": f"MsExecAuto({rotina}) — campo obrigatório não tratado pode causar erro",
                        })

        # Get webservices/integrations that write to this table
        integracoes = []
        ws_rows = db.execute(
            "SELECT arquivo, modulo, write_tables, lines_of_code "
            "FROM fontes WHERE write_tables LIKE ? AND "
            "(upper(arquivo) LIKE '%WS%' OR upper(arquivo) LIKE '%INTEG%' "
            "OR upper(arquivo) LIKE '%API%' OR upper(arquivo) LIKE '%REST%' "
            "OR upper(arquivo) LIKE '%EDI%')",
            (f'%"{tabela}"%',),
        ).fetchall()
        for r in ws_rows:
            integracoes.append({
                "arquivo": r[0], "modulo": r[1] or "", "loc": r[3] or 0,
            })

        # Get field info if specific campo provided
        campo_info = {}
        if campo:
            ci_row = db.execute(
                "SELECT campo, tipo, tamanho, titulo, descricao, validacao, "
                "inicializador, obrigatorio, vlduser "
                "FROM campos WHERE upper(tabela)=? AND upper(campo)=?",
                (tabela.upper(), campo.upper()),
            ).fetchone()
            if ci_row:
                campo_info = {
                    "campo": ci_row[0], "tipo": ci_row[1], "tamanho": ci_row[2],
                    "titulo": ci_row[3] or "", "descricao": ci_row[4] or "",
                    "validacao": ci_row[5] or "", "inicializador": ci_row[6] or "",
                    "obrigatorio": ci_row[7], "vlduser": ci_row[8] or "",
                }

        # Get structured write operations from operacoes_escrita
        ops_escrita = []
        try:
            if campo:
                op_rows = db.execute(
                    "SELECT arquivo, funcao, tipo, campos, origens, condicao, linha "
                    "FROM operacoes_escrita WHERE upper(tabela)=? AND campos LIKE ?",
                    (tabela.upper(), f'%{campo.upper()}%'),
                ).fetchall()
            else:
                op_rows = db.execute(
                    "SELECT arquivo, funcao, tipo, campos, origens, condicao, linha "
                    "FROM operacoes_escrita WHERE upper(tabela)=? AND tipo IN ('reclock_inc','reclock_alt') "
                    "ORDER BY arquivo LIMIT 30",
                    (tabela.upper(),),
                ).fetchall()
            for r in op_rows:
                origens = _safe_json(r[4])
                if isinstance(origens, list):
                    origens = {}
                entry = {
                    "arquivo": r[0], "funcao": r[1], "tipo": r[2],
                    "campos": _safe_json(r[3]),
                    "condicao": r[5] or "",
                    "linha": r[6] or 0,
                }
                if campo:
                    entry["origem_campo"] = origens.get(campo.upper(), "")
                ops_escrita.append(entry)
        except Exception:
            pass  # Table may not exist in older databases

        return {
            "tabela": tabela,
            "campo_info": campo_info,
            "fontes_escrita": fontes,
            "exec_autos": exec_autos,
            "msexecauto_fontes": msexecauto_fontes,
            "integracoes": integracoes,
            "gatilhos": gatilhos,
            "campos_custom": campos_custom,
            "operacoes_escrita": ops_escrita,
            "total_fontes_escrita": len(fontes),
            "total_exec_autos": len(exec_autos),
            "total_msexecauto": len(msexecauto_fontes),
            "total_integracoes": len(integracoes),
            "total_operacoes_escrita": len(ops_escrita),
        }
    finally:
        db.close()


def tool_buscar_pes(rotina: str = "", modulo: str = "") -> list[dict]:
    """Find standard PEs for a routine or module."""
    db = _get_db()
    try:
        if rotina:
            rows = db.execute(
                "SELECT nome, objetivo, modulo, rotina FROM padrao_pes WHERE upper(rotina) LIKE ?",
                (f"%{rotina.upper()}%",),
            ).fetchall()
        elif modulo:
            rows = db.execute(
                "SELECT nome, objetivo, modulo, rotina FROM padrao_pes WHERE upper(modulo) LIKE ?",
                (f"%{modulo.upper()}%",),
            ).fetchall()
        else:
            rows = []
        return [{"nome": r[0], "objetivo": r[1] or "", "modulo": r[2] or "", "rotina": r[3] or ""} for r in rows]
    finally:
        db.close()


def tool_buscar_fontes_tabela(tabela: str, modo: str = "escrita") -> list[dict]:
    """Find fontes that read or write a table. modo: 'escrita'|'leitura'|'todos'."""
    db = _get_db()
    try:
        if modo == "escrita":
            rows = db.execute(
                "SELECT arquivo, modulo, write_tables, pontos_entrada, lines_of_code "
                "FROM fontes WHERE write_tables LIKE ?",
                (f'%"{tabela}"%',),
            ).fetchall()
        elif modo == "leitura":
            rows = db.execute(
                "SELECT arquivo, modulo, write_tables, pontos_entrada, lines_of_code "
                "FROM fontes WHERE tabelas_ref LIKE ? AND write_tables NOT LIKE ?",
                (f'%"{tabela}"%', f'%"{tabela}"%'),
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT arquivo, modulo, write_tables, pontos_entrada, lines_of_code "
                "FROM fontes WHERE tabelas_ref LIKE ? OR write_tables LIKE ?",
                (f'%"{tabela}"%', f'%"{tabela}"%'),
            ).fetchall()

        result = []
        for r in rows:
            # Get overview if exists
            overview = ""
            pr = db.execute("SELECT proposito FROM propositos WHERE chave=?", (r[0],)).fetchone()
            if pr and pr[0]:
                try:
                    parsed = json.loads(pr[0])
                    overview = parsed.get("humano", "")
                except (json.JSONDecodeError, TypeError):
                    overview = pr[0][:200] if pr[0] else ""

            result.append({
                "arquivo": r[0],
                "modulo": r[1] or "",
                "write_tables": _safe_json(r[2]),
                "pes": _safe_json(r[3]),
                "loc": r[4] or 0,
                "overview": overview,
            })
        return result
    finally:
        db.close()


def tool_buscar_parametros(termo: str = "", tabela: str = "") -> list[dict]:
    """Search SX6 parameters by name or by table (finds params used by fontes that reference the table)."""
    db = _get_db()
    try:
        results = []

        if termo:
            # Direct search in parametros (SX6) — include filial variations
            rows = db.execute(
                "SELECT variavel, tipo, descricao, conteudo, custom, filial FROM parametros "
                "WHERE upper(variavel) LIKE ? OR upper(descricao) LIKE ? "
                "ORDER BY variavel, filial LIMIT 50",
                (f"%{termo.upper()}%", f"%{termo.upper()}%"),
            ).fetchall()
            # Group by variable, show filial variations
            seen_vars = {}
            for r in rows:
                var = r[0]
                filial = (r[5] or "").strip()
                padrao = db.execute(
                    "SELECT conteudo FROM padrao_parametros WHERE variavel=? LIMIT 1",
                    (var,),
                ).fetchone()
                if var not in seen_vars:
                    seen_vars[var] = {
                        "variavel": var, "tipo": r[1] or "", "descricao": r[2] or "",
                        "conteudo": r[3] or "", "custom": r[4],
                        "valor_padrao": padrao[0] if padrao else "",
                        "filiais": {},
                    }
                if filial:
                    seen_vars[var]["filiais"][filial] = r[3] or ""
                else:
                    seen_vars[var]["conteudo"] = r[3] or ""

            for var, info in seen_vars.items():
                if info["filiais"]:
                    info["tem_variacao_filial"] = True
                    info["total_filiais"] = len(info["filiais"])
                    # Show filial values summary
                    vals = set(info["filiais"].values())
                    if len(vals) == 1:
                        info["filiais_resumo"] = f"Todas {len(info['filiais'])} filiais: {list(vals)[0]}"
                    else:
                        info["filiais_resumo"] = "; ".join(
                            f"filial {f}={v}" for f, v in sorted(info["filiais"].items())[:8]
                        )
                results.append(info)

        if tabela:
            # Find params used by fontes that write to this table
            fonte_rows = db.execute(
                "SELECT arquivo FROM fontes WHERE write_tables LIKE ? OR tabelas_ref LIKE ?",
                (f'%"{tabela}"%', f'%"{tabela}"%'),
            ).fetchall()
            param_vars = set()
            for fr in fonte_rows:
                fd_rows = db.execute(
                    "SELECT params FROM funcao_docs WHERE arquivo=? AND params IS NOT NULL",
                    (fr[0],),
                ).fetchall()
                for fd in fd_rows:
                    params = _safe_json(fd[0])
                    if isinstance(params, dict):
                        for p in params.get("sx6", []):
                            param_vars.add(p.get("var", ""))

            # Fetch details for found params — include filial variations
            for var in sorted(param_vars):
                if not var:
                    continue
                if termo and var in (seen_vars if 'seen_vars' in dir() else {}):
                    continue  # Already added by termo search
                rows_param = db.execute(
                    "SELECT variavel, tipo, descricao, conteudo, custom, filial FROM parametros WHERE variavel=? ORDER BY filial",
                    (var,),
                ).fetchall()
                if rows_param:
                    r = rows_param[0]
                    padrao = db.execute(
                        "SELECT conteudo FROM padrao_parametros WHERE variavel=? LIMIT 1",
                        (r[0],),
                    ).fetchone()
                    entry = {
                        "variavel": r[0], "tipo": r[1] or "", "descricao": r[2] or "",
                        "conteudo": r[3] or "", "custom": r[4],
                        "valor_padrao": padrao[0] if padrao else "",
                        "usado_por_tabela": tabela,
                    }
                    # Add filial variations
                    filiais = {}
                    for rp in rows_param:
                        fil = (rp[5] or "").strip()
                        if fil:
                            filiais[fil] = rp[3] or ""
                        else:
                            entry["conteudo"] = rp[3] or ""
                    if filiais:
                        entry["tem_variacao_filial"] = True
                        entry["total_filiais"] = len(filiais)
                        entry["filiais"] = filiais
                    results.append(entry)

        # Deduplicate
        seen = set()
        unique = []
        for r in results:
            if r["variavel"] not in seen:
                seen.add(r["variavel"])
                unique.append(r)

        return unique
    finally:
        db.close()


def tool_buscar_perguntas(grupo: str = "", termo: str = "") -> list[dict]:
    """Search SX1 question groups by group code or search term."""
    db = _get_db()
    try:
        if grupo:
            rows = db.execute(
                "SELECT grupo, ordem, pergunta, tipo, tamanho FROM perguntas "
                "WHERE upper(grupo) LIKE ? ORDER BY grupo, ordem LIMIT 30",
                (f"%{grupo.upper()}%",),
            ).fetchall()
        elif termo:
            rows = db.execute(
                "SELECT grupo, ordem, pergunta, tipo, tamanho FROM perguntas "
                "WHERE upper(pergunta) LIKE ? ORDER BY grupo, ordem LIMIT 20",
                (f"%{termo.upper()}%",),
            ).fetchall()
        else:
            rows = []

        results = []
        for r in rows:
            results.append({
                "grupo": r[0] or "", "ordem": r[1] or "",
                "pergunta": r[2] or "", "tipo": r[3] or "", "tamanho": r[4] or "",
            })
        return results
    finally:
        db.close()


def tool_buscar_tabela_generica(tabela: str = "", termo: str = "") -> list[dict]:
    """Search SX5 generic tables (combo lists). tabela=code (ZZ, etc) or termo=search."""
    db = _get_db()
    try:
        if tabela:
            rows = db.execute(
                "SELECT tabela, chave, descricao FROM tabelas_genericas "
                "WHERE upper(tabela) LIKE ? ORDER BY tabela, chave LIMIT 30",
                (f"%{tabela.upper()}%",),
            ).fetchall()
        elif termo:
            rows = db.execute(
                "SELECT tabela, chave, descricao FROM tabelas_genericas "
                "WHERE upper(descricao) LIKE ? ORDER BY tabela, chave LIMIT 20",
                (f"%{termo.upper()}%",),
            ).fetchall()
        else:
            rows = []

        return [{"tabela": r[0] or "", "chave": r[1] or "", "descricao": r[2] or ""} for r in rows]
    finally:
        db.close()


def tool_buscar_jobs(rotina: str = "", arquivo_ini: str = "") -> list[dict]:
    """Search jobs by routine name or INI file. Strips U_ prefix for matching."""
    db = _get_db()
    try:
        if rotina:
            # Strip U_ prefix for broader matching
            clean = rotina.upper()
            if clean.startswith("U_"):
                clean = clean[2:]
            rows = db.execute(
                "SELECT arquivo_ini, sessao, rotina, refresh_rate, parametros FROM jobs "
                "WHERE upper(rotina) LIKE ? OR upper(rotina) LIKE ? ORDER BY arquivo_ini",
                (f"%{rotina.upper()}%", f"%{clean}%"),
            ).fetchall()
        elif arquivo_ini:
            rows = db.execute(
                "SELECT arquivo_ini, sessao, rotina, refresh_rate, parametros FROM jobs "
                "WHERE upper(arquivo_ini) LIKE ? ORDER BY sessao",
                (f"%{arquivo_ini.upper()}%",),
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT arquivo_ini, sessao, rotina, refresh_rate, parametros FROM jobs "
                "ORDER BY arquivo_ini LIMIT 50"
            ).fetchall()
        return [{"arquivo_ini": r[0], "sessao": r[1], "rotina": r[2],
                 "refresh_rate": r[3], "parametros": r[4]} for r in rows]
    except Exception:
        return []
    finally:
        db.close()


def tool_buscar_schedules(rotina: str = "", status: str = "", codigo: str = "") -> list[dict]:
    """Search schedules by routine, status, or code. Strips U_ prefix for matching."""
    db = _get_db()
    try:
        if rotina:
            clean = rotina.upper()
            if clean.startswith("U_"):
                clean = clean[2:]
            rows = db.execute(
                "SELECT codigo, rotina, empresa_filial, environment, status, "
                "tipo_recorrencia, detalhe_recorrencia, execucoes_dia, intervalo, "
                "hora_inicio, ultima_execucao FROM schedules "
                "WHERE upper(rotina) LIKE ? OR upper(rotina) LIKE ? ORDER BY status, rotina",
                (f"%{rotina.upper()}%", f"%{clean}%"),
            ).fetchall()
        elif status:
            rows = db.execute(
                "SELECT codigo, rotina, empresa_filial, environment, status, "
                "tipo_recorrencia, detalhe_recorrencia, execucoes_dia, intervalo, "
                "hora_inicio, ultima_execucao FROM schedules "
                "WHERE upper(status) LIKE ? ORDER BY rotina",
                (f"%{status.upper()}%",),
            ).fetchall()
        elif codigo:
            rows = db.execute(
                "SELECT codigo, rotina, empresa_filial, environment, status, "
                "tipo_recorrencia, detalhe_recorrencia, execucoes_dia, intervalo, "
                "hora_inicio, ultima_execucao FROM schedules "
                "WHERE codigo LIKE ? ORDER BY empresa_filial",
                (f"%{codigo}%",),
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT codigo, rotina, empresa_filial, environment, status, "
                "tipo_recorrencia, detalhe_recorrencia, execucoes_dia, intervalo, "
                "hora_inicio, ultima_execucao FROM schedules "
                "ORDER BY status, rotina LIMIT 50"
            ).fetchall()
        return [{
            "codigo": r[0], "rotina": r[1], "empresa_filial": r[2],
            "environment": r[3], "status": r[4], "tipo_recorrencia": r[5],
            "detalhe_recorrencia": r[6], "execucoes_dia": r[7],
            "intervalo": r[8], "hora_inicio": r[9], "ultima_execucao": r[10],
        } for r in rows]
    except Exception:
        return []
    finally:
        db.close()


def tool_resolver_contexto(mensagem: str) -> dict:
    """Resolve vague user descriptions into specific tables, fields and routines.

    Uses a 5-step pipeline:
    1. Keywords: detect action type + context type
    2. Synonyms: instant lookup for common terms
    3. Menu→Routine→Tables chain: find routine, get its tables
    4. Field search: find field by title in resolved tables
    5. Cross-search: table name × field title combination

    Returns: tabelas, campos, rotinas, context_type, action_type.
    """
    db = _get_db()
    try:
        msg_lower = mensagem.lower()
        result = {
            "tabelas_encontradas": [],
            "campos_encontrados": [],
            "rotinas_encontradas": [],
            "context_type": "",
            "action_type": "",
            "info_extra": {},
            "contexto_resolvido": False,
        }

        # ── Step 0: Extract meaningful words ──
        stopwords = {"tem", "uma", "um", "que", "de", "do", "da", "dos", "das", "no", "na",
                      "nos", "nas", "ao", "para", "por", "com", "sem", "mas", "acho",
                      "algo", "assim", "isso", "esta", "pode", "verificar", "parece",
                      "usuario", "tela", "salva", "salvar", "alterado", "alterar", "campo",
                      "rotina", "programa", "fonte", "quando", "nao", "valor", "tipo",
                      "tambem", "deveria", "antes", "depois", "ainda", "sempre", "nunca"}
        words = [w for w in _re_mod.findall(r'\b(\w{3,})\b', msg_lower) if w not in stopwords]

        # ── Step 1: Classify action + context by keywords ──
        ACTION_KW = {
            "nao_salva": ["nao salva", "nao grava", "perde valor", "volta valor",
                          "nao atualiza", "nao persiste", "nao salvo", "nao gravou",
                          "nao esta alterando", "nao altera"],
            "nao_processa": ["nao processa", "job parado", "nao roda", "parou de rodar",
                             "schedule parado", "nao executa", "esta parado", "parou"],
            "nao_preenche": ["nao preenche", "fica vazio", "gatilho nao", "nao dispara",
                             "nao carrega", "nao busca"],
            "erro": ["erro", "fatal", "travou", "bugado", "crash", "dump",
                     "error", "falha"],
            "nao_valida": ["nao deixa salvar", "validacao", "obrigatorio",
                           "campo obrigatorio", "bloqueando"],
            "nao_integra": ["nao integra", "ws nao", "api nao", "nao envia",
                            "nao recebe", "integracao parou"],
        }
        CONTEXT_KW = {
            "tela": ["tela", "cadastro", "browse", "inclusao", "alteracao"],
            "gravacao": ["quando salva", "ao salvar", "quando grava", "ao gravar",
                         "ao incluir", "ao alterar", "depois de salvar", "apos salvar",
                         "quando salvo", "salvo o"],
            "job": ["job", "schedule", "agendamento", "automatico", "batch",
                     "appserver", "refresh"],
            "gatilho": ["gatilho", "trigger", "preenche sozinho", "automaticamente"],
            "integracao": ["integracao", "webservice", "api", "edi", "sfa",
                           "salesforce", "taura", "tms"],
            "validacao": ["validacao", "nao deixa", "bloqueio", "obrigatorio"],
            "inicializador": ["campo vazio", "deveria ter valor", "inicializador"],
        }

        for action, keywords in ACTION_KW.items():
            if any(kw in msg_lower for kw in keywords):
                result["action_type"] = action
                break

        for ctx, keywords in CONTEXT_KW.items():
            if any(kw in msg_lower for kw in keywords):
                result["context_type"] = ctx
                break

        # ── Step 2: Synonym lookup ──
        SINONIMOS = {
            "pedido de venda": {"rotina": "MATA410", "tabelas": ["SC5", "SC6"]},
            "pedido de compra": {"rotina": "MATA120", "tabelas": ["SC7"]},
            "solicitacao de compra": {"rotina": "MATA110", "tabelas": ["SC1"]},
            "nota fiscal saida": {"rotina": "MATA460", "tabelas": ["SF2", "SD2"]},
            "nota fiscal entrada": {"rotina": "MATA103", "tabelas": ["SF1", "SD1"]},
            "nota de saida": {"rotina": "MATA460", "tabelas": ["SF2", "SD2"]},
            "nota de entrada": {"rotina": "MATA103", "tabelas": ["SF1", "SD1"]},
            "cadastro de cliente": {"rotina": "MATA030", "tabelas": ["SA1"]},
            "cadastro de fornecedor": {"rotina": "MATA020", "tabelas": ["SA2"]},
            "cadastro de produto": {"rotina": "MATA010", "tabelas": ["SB1"]},
            "contas a receber": {"rotina": "FINA040", "tabelas": ["SE1"]},
            "contas a pagar": {"rotina": "FINA050", "tabelas": ["SE2"]},
            "ordem de producao": {"rotina": "MATA650", "tabelas": ["SC2"]},
            "titulo a receber": {"rotina": "FINA040", "tabelas": ["SE1"]},
            "titulo a pagar": {"rotina": "FINA050", "tabelas": ["SE2"]},
        }

        tabelas_found = set()
        rotinas_found = set()
        campos_found = []
        sinonimo_match = False

        for termo, info in SINONIMOS.items():
            if termo in msg_lower:
                sinonimo_match = True
                if info.get("rotina"):
                    rotinas_found.add((info["rotina"], termo.title(), ""))
                for tab in info.get("tabelas", []):
                    trow = db.execute("SELECT codigo, nome FROM tabelas WHERE codigo=?", (tab,)).fetchone()
                    tabelas_found.add((tab, trow[1] if trow else ""))
                break

        # ── Step 3: Menu → Routine → Tables chain ──
        if not sinonimo_match:
            # Search menus by keywords
            for word in words:
                rows = db.execute(
                    "SELECT DISTINCT rotina, nome, modulo FROM menus "
                    "WHERE LOWER(nome) LIKE ? LIMIT 5",
                    (f"%{word}%",),
                ).fetchall()
                for r in rows:
                    rotinas_found.add((r[0], r[1], r[2]))

            # From routines found → get their tables via fontes.write_tables
            for rot, rot_nome, rot_mod in rotinas_found:
                frow = db.execute(
                    "SELECT write_tables, tabelas_ref FROM fontes WHERE upper(arquivo) LIKE ? LIMIT 1",
                    (f"%{rot.upper()}%",),
                ).fetchone()
                if frow:
                    for tab in _safe_json(frow[0]):
                        trow = db.execute("SELECT codigo, nome FROM tabelas WHERE codigo=?", (tab,)).fetchone()
                        tabelas_found.add((tab, trow[1] if trow else ""))

            # Also search table names directly
            for word in words:
                rows = db.execute(
                    "SELECT codigo, nome FROM tabelas WHERE LOWER(nome) LIKE ? LIMIT 10",
                    (f"%{word}%",),
                ).fetchall()
                for r in rows:
                    tabelas_found.add((r[0], r[1]))

        # ── Step 3b: Context-specific searches ──
        ctx = result["context_type"]
        if ctx == "job":
            for word in words:
                rows = db.execute(
                    "SELECT arquivo_ini, sessao, rotina FROM jobs WHERE LOWER(rotina) LIKE ? LIMIT 5",
                    (f"%{word}%",),
                ).fetchall()
                if rows:
                    result["info_extra"]["jobs"] = [
                        {"arquivo": r[0], "sessao": r[1], "rotina": r[2]} for r in rows
                    ]
                    for r in rows:
                        # Get tables from job routine
                        frow = db.execute(
                            "SELECT write_tables FROM fontes WHERE upper(arquivo) LIKE ? LIMIT 1",
                            (f"%{r[2].replace('U_','').upper()}%",),
                        ).fetchone()
                        if frow:
                            for tab in _safe_json(frow[0]):
                                trow = db.execute("SELECT codigo, nome FROM tabelas WHERE codigo=?", (tab,)).fetchone()
                                tabelas_found.add((tab, trow[1] if trow else ""))

        elif ctx == "gravacao":
            # "quando salvo" → find PEs for the routine
            for rot, rot_nome, rot_mod in list(rotinas_found)[:3]:
                pes = db.execute(
                    "SELECT nome, objetivo, rotina FROM padrao_pes WHERE upper(rotina) LIKE ? LIMIT 10",
                    (f"%{rot.upper()}%",),
                ).fetchall()
                if pes:
                    result["info_extra"]["pes_disponiveis"] = [
                        {"nome": p[0], "objetivo": p[1] or "", "rotina": p[2] or ""} for p in pes
                    ]
                # Also find implemented PEs in fontes
                impl_pes = db.execute(
                    "SELECT arquivo, pontos_entrada FROM fontes "
                    "WHERE pontos_entrada LIKE ? AND pontos_entrada != '[]' LIMIT 10",
                    (f"%{rot.upper()[:4]}%",),
                ).fetchall()
                if impl_pes:
                    result["info_extra"]["pes_implementados"] = [
                        {"arquivo": p[0], "pes": _safe_json(p[1])} for p in impl_pes
                    ]

        elif ctx == "gatilho":
            # Search triggers for the fields/tables found
            for word in words:
                rows = db.execute(
                    "SELECT campo_origem, campo_destino, regra, tipo, tabela FROM gatilhos "
                    "WHERE LOWER(campo_destino) LIKE ? OR LOWER(campo_origem) LIKE ? LIMIT 5",
                    (f"%{word}%", f"%{word}%"),
                ).fetchall()
                if rows:
                    result["info_extra"]["gatilhos"] = [
                        {"origem": r[0], "destino": r[1], "regra": r[2], "tabela": r[4]} for r in rows
                    ]

        # ── Step 4: Search fields in resolved tables ──
        if tabelas_found:
            tab_codes = [t[0] for t in tabelas_found]
            placeholders = ",".join("?" * len(tab_codes))
            for word in words:
                rows = db.execute(
                    f"SELECT tabela, campo, titulo, descricao, tipo, tamanho FROM campos "
                    f"WHERE tabela IN ({placeholders}) AND "
                    f"(LOWER(titulo) LIKE ? OR LOWER(descricao) LIKE ?) LIMIT 10",
                    tab_codes + [f"%{word}%", f"%{word}%"],
                ).fetchall()
                for r in rows:
                    campos_found.append({
                        "tabela": r[0], "campo": r[1], "titulo": r[2] or "",
                        "descricao": r[3] or "", "tipo": r[4] or "", "tamanho": r[5] or 0,
                    })

        # ── Step 5: Cross-search (table name × field title) ──
        if len(words) >= 2:
            for i, w1 in enumerate(words):
                for j, w2 in enumerate(words):
                    if i == j:
                        continue
                    cross_rows = db.execute(
                        "SELECT c.tabela, c.campo, c.titulo, c.descricao, c.tipo, c.tamanho "
                        "FROM campos c JOIN tabelas t ON t.codigo = c.tabela "
                        "WHERE LOWER(t.nome) LIKE ? AND (LOWER(c.titulo) LIKE ? OR LOWER(c.descricao) LIKE ?) "
                        "LIMIT 5",
                        (f"%{w1}%", f"%{w2}%", f"%{w2}%"),
                    ).fetchall()
                    for r in cross_rows:
                        campos_found.append({
                            "tabela": r[0], "campo": r[1], "titulo": r[2] or "",
                            "descricao": r[3] or "", "tipo": r[4] or "", "tamanho": r[5] or 0,
                            "_cross": True,
                        })
                        tabelas_found.add((r[0], ""))

        # ── Deduplicate and prioritize ──
        seen = {}
        unique_campos = []
        for c in campos_found:
            key = f"{c['tabela']}.{c['campo']}"
            titulo_lower = (c.get("titulo", "") or "").lower()
            desc_lower = (c.get("descricao", "") or "").lower()
            score = sum(1 for w in words if w in titulo_lower or w in desc_lower)
            c["_score"] = score
            if key not in seen:
                seen[key] = len(unique_campos)
                unique_campos.append(c)
            elif c.get("_cross") and not unique_campos[seen[key]].get("_cross"):
                unique_campos[seen[key]] = c
        unique_campos.sort(key=lambda x: (-int(x.get("_cross", False)), -x.get("_score", 0)))

        # Prioritize tables by keyword match count
        tab_scores = {}
        for t_code, t_nome in tabelas_found:
            score = sum(1 for w in words if w in (t_nome or "").lower())
            tab_scores[(t_code, t_nome)] = score
        sorted_tabs = sorted(tabelas_found, key=lambda t: -tab_scores.get(t, 0))

        result["tabelas_encontradas"] = [{"codigo": t[0], "nome": t[1]} for t in sorted_tabs]
        result["campos_encontrados"] = unique_campos[:15]
        result["rotinas_encontradas"] = [
            {"rotina": r[0], "nome": r[1], "modulo": r[2]} for r in sorted(rotinas_found)
        ][:5]
        result["contexto_resolvido"] = bool(tabelas_found or campos_found or rotinas_found)

        return result
    finally:
        db.close()


def tool_quem_grava_campo(tabela: str, campo: str = "") -> list[dict]:
    """Find all write operations for a table or specific field using operacoes_escrita.

    Returns structured results: who writes, what conditions control it,
    where the value comes from, and what other fields are written together.
    """
    db = _get_db()
    try:
        if campo:
            rows = db.execute(
                "SELECT arquivo, funcao, tipo, tabela, campos, origens, condicao, linha "
                "FROM operacoes_escrita WHERE upper(tabela)=? AND campos LIKE ?",
                (tabela.upper(), f'%{campo.upper()}%'),
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT arquivo, funcao, tipo, tabela, campos, origens, condicao, linha "
                "FROM operacoes_escrita WHERE upper(tabela)=? "
                "ORDER BY tipo, arquivo, funcao",
                (tabela.upper(),),
            ).fetchall()

        results = []
        for r in rows:
            campos_list = _safe_json(r[4])
            origens_dict = _safe_json(r[5])
            if isinstance(origens_dict, list):
                origens_dict = {}

            entry = {
                "arquivo": r[0],
                "funcao": r[1],
                "tipo": r[2],
                "tabela": r[3],
                "campos": campos_list,
                "total_campos": len(campos_list),
                "condicao": r[6] or "",
                "linha": r[7] or 0,
            }

            # If searching for specific field, include its origin
            if campo:
                campo_upper = campo.upper()
                entry["origem_campo"] = origens_dict.get(campo_upper, "")

            # Get proposito do fonte if available
            prop = db.execute(
                "SELECT proposito FROM propositos WHERE chave=?", (r[0],)
            ).fetchone()
            if prop and prop[0]:
                try:
                    p = json.loads(prop[0])
                    entry["proposito"] = p.get("humano", "")[:150]
                except (json.JSONDecodeError, TypeError):
                    entry["proposito"] = (prop[0] or "")[:150]
            else:
                entry["proposito"] = ""

            results.append(entry)

        return results
    finally:
        db.close()


def tool_operacoes_tabela(tabela: str) -> dict:
    """Get summary of all write operations on a table from operacoes_escrita.

    Returns: total operations by type, list of fontes, conditional writes,
    and fields most frequently written.
    """
    db = _get_db()
    try:
        rows = db.execute(
            "SELECT arquivo, funcao, tipo, campos, condicao, linha "
            "FROM operacoes_escrita WHERE upper(tabela)=?",
            (tabela.upper(),),
        ).fetchall()

        if not rows:
            return {"tabela": tabela, "total_operacoes": 0, "msg": "Nenhuma operacao encontrada"}

        # Count by type
        por_tipo = {}
        fontes_set = set()
        condicionais = []
        campo_freq = {}

        for r in rows:
            tipo = r[2]
            por_tipo[tipo] = por_tipo.get(tipo, 0) + 1
            fontes_set.add(r[0])
            if r[4]:  # has condition
                condicionais.append({
                    "arquivo": r[0], "funcao": r[1], "tipo": tipo,
                    "condicao": r[4][:100], "linha": r[5],
                })
            for c in _safe_json(r[3]):
                campo_freq[c] = campo_freq.get(c, 0) + 1

        # Top campos mais escritos
        top_campos = sorted(campo_freq.items(), key=lambda x: -x[1])[:15]

        return {
            "tabela": tabela,
            "total_operacoes": len(rows),
            "por_tipo": por_tipo,
            "total_fontes": len(fontes_set),
            "fontes": sorted(fontes_set),
            "escritas_condicionais": condicionais[:20],
            "campos_mais_escritos": [{"campo": c, "vezes": v} for c, v in top_campos],
        }
    finally:
        db.close()


def tool_investigar_condicao(arquivo: str, funcao: str, variavel_condicao: str) -> dict:
    """Backward trace: investigate a condition variable used in a RecLock.

    Finds the variable definition, extracts dependencies (parameters, fields,
    functions), and resolves current values from the database.
    """
    db = _get_db()
    try:
        var_name = variavel_condicao.strip()
        result = {
            "variavel": var_name,
            "arquivo": arquivo,
            "funcao_uso": funcao,
            "definicao_encontrada": False,
            "expressao": "",
            "dependencias": [],
            "blocos_alternativos": [],
        }

        # 1. Search for variable definition in ALL chunks of this file
        #    (Private vars may be defined in a different function)
        chunks = db.execute(
            "SELECT funcao, content FROM fonte_chunks WHERE arquivo=? ORDER BY id",
            (arquivo,),
        ).fetchall()

        all_code = ""
        definition_func = ""
        definition_line = ""
        definition_expr = ""

        for chunk_func, chunk_content in chunks:
            if not chunk_content:
                continue
            all_code += chunk_content + "\n"

            # Search for: varName := expression
            import re as _re
            patterns = [
                _re.compile(
                    r'(?:Private|Local|Static)?\s*' + _re.escape(var_name) + r'\s*:=\s*(.+)',
                    _re.IGNORECASE
                ),
                _re.compile(
                    r'\b' + _re.escape(var_name) + r'\s*:=\s*(.+)',
                    _re.IGNORECASE
                ),
            ]
            for pat in patterns:
                for line in chunk_content.split('\n'):
                    m = pat.search(line)
                    if m:
                        expr = m.group(1).strip()
                        # Skip if it's just using the var, not defining it
                        if len(expr) > 2 and not expr.startswith('//'):
                            definition_func = chunk_func
                            definition_expr = expr
                            result["definicao_encontrada"] = True
                            result["expressao"] = expr[:300]
                            result["funcao_definicao"] = chunk_func
                            break
                if result["definicao_encontrada"]:
                    break

        if not result["definicao_encontrada"]:
            return result

        # 2. Extract dependencies from the expression
        import re as _re

        # 2a. Parameters (GetMV, SuperGetMV, GetNewPar, FWMVPar)
        param_patterns = [
            r"GetMV\s*\(\s*['\"](\w+)['\"]",
            r"SuperGetMV\s*\(\s*['\"](\w+)['\"]",
            r"GetNewPar\s*\(\s*['\"](\w+)['\"]",
            r"FWMVPar\s*\(\s*['\"](\w+)['\"]",
        ]

        # Search scope: params need wider scope (GetMV may be lines before)
        # but fields/functions should be scoped to the expression + nearby lines
        search_text_wide = definition_expr  # for params
        search_text_narrow = definition_expr  # for fields/functions

        for chunk_func, chunk_content in chunks:
            if chunk_func == definition_func and chunk_content:
                search_text_wide += "\n" + chunk_content
                # Narrow: find the definition line and grab nearby lines
                # Include lines that reassign the var (e.g., Rondônia override)
                clines = chunk_content.split('\n')
                narrow_lines = []
                for li, cl in enumerate(clines):
                    cl_stripped = cl.strip()
                    # Include: definition line, reassignment, and IF blocks around it
                    if var_name in cl and (':=' in cl or var_name.lower() in cl_stripped.lower()):
                        start = max(0, li - 3)
                        end = min(len(clines), li + 5)
                        narrow_lines.extend(clines[start:end])
                if narrow_lines:
                    search_text_narrow = '\n'.join(narrow_lines)

        found_params = set()
        for pp in param_patterns:
            for pm in _re.finditer(pp, search_text_wide, _re.IGNORECASE):
                param_name = pm.group(1).upper()
                if param_name not in found_params:
                    found_params.add(param_name)
                    # Lookup current value
                    prow = db.execute(
                        "SELECT variavel, tipo, descricao, conteudo FROM parametros WHERE upper(variavel)=? LIMIT 1",
                        (param_name,),
                    ).fetchone()
                    dep = {
                        "nome": param_name,
                        "tipo": "parametro",
                        "origem": f"GetMV('{param_name}')",
                    }
                    if prow:
                        dep["valor_atual"] = prow[3] or "(vazio)"
                        dep["descricao"] = prow[2] or ""
                        dep["tipo_param"] = prow[1] or ""
                    else:
                        dep["valor_atual"] = "(não encontrado no SX6)"
                    result["dependencias"].append(dep)

        # 2b. Table fields (ALIAS->CAMPO) — narrow scope (only near definition)
        field_refs = _re.findall(r'(\w{2,3})->(\w+)', search_text_narrow)
        seen_fields = set()
        for alias, campo in field_refs:
            alias = alias.upper()
            campo = campo.upper()
            key = f"{alias}.{campo}"
            if key in seen_fields:
                continue
            seen_fields.add(key)
            # Skip M-> (screen variables)
            if alias == "M":
                continue
            crow = db.execute(
                "SELECT campo, tipo, tamanho, titulo, descricao, cbox FROM campos "
                "WHERE upper(tabela)=? AND upper(campo)=? LIMIT 1",
                (alias, campo),
            ).fetchone()
            dep = {
                "nome": f"{alias}->{campo}",
                "tipo": "campo_tabela",
                "tabela": alias,
                "campo": campo,
            }
            if crow:
                dep["titulo"] = crow[3] or ""
                dep["descricao"] = crow[4] or ""
                dep["tipo_campo"] = f"{crow[1]}({crow[2]})"
                if crow[5]:
                    dep["cbox"] = crow[5]
            result["dependencias"].append(dep)

        # 2c. Function calls (U_xxx) — V2/V3: deep dive + multi-fonte
        func_calls = _re.findall(r'U_(\w+)\s*\(', search_text_narrow, _re.IGNORECASE)
        seen_funcs = set()
        for fc in func_calls:
            fc_upper = fc.upper()
            if fc_upper in seen_funcs:
                continue
            seen_funcs.add(fc_upper)

            dep = {
                "nome": f"U_{fc}",
                "tipo": "funcao",
            }

            # V1: basic info from funcao_docs
            frow = db.execute(
                "SELECT funcao, arquivo, resumo, tabelas_ref, campos_ref, chama, chamada_por, params "
                "FROM funcao_docs WHERE upper(funcao)=? LIMIT 1",
                (fc_upper,),
            ).fetchone()

            if frow:
                dep["arquivo"] = frow[1] or ""
                resumo = frow[2] or ""
                if resumo:
                    try:
                        r_parsed = json.loads(resumo)
                        dep["resumo"] = r_parsed.get("humano", "")[:200]
                        if r_parsed.get("ia"):
                            ia = r_parsed["ia"]
                            dep["acao"] = ia.get("acao", "")
                            dep["retorno_tipo"] = ia.get("retorno_tipo", "")
                            dep["retorno_desc"] = ia.get("retorno_descricao", "")[:100]
                    except (json.JSONDecodeError, TypeError):
                        dep["resumo"] = resumo[:200]
                dep["tabelas_ref"] = _safe_json(frow[3])
                dep["campos_ref"] = _safe_json(frow[4])[:10]
                dep["chama"] = _safe_json(frow[5])[:5]
                dep["chamada_por"] = _safe_json(frow[6])[:5]

                # V2: extract params used by this function
                func_params = _safe_json(frow[7])
                if isinstance(func_params, dict):
                    sx6_params = func_params.get("sx6", [])
                    for sp in sx6_params[:5]:
                        sp_var = sp.get("var", "")
                        if sp_var:
                            prow = db.execute(
                                "SELECT variavel, descricao, conteudo FROM parametros "
                                "WHERE upper(variavel)=? LIMIT 1",
                                (sp_var.upper(),),
                            ).fetchone()
                            dep.setdefault("parametros_usados", []).append({
                                "variavel": sp_var,
                                "valor_atual": prow[2] if prow else "(não encontrado)",
                                "descricao": prow[1][:80] if prow else "",
                            })

            # V2: get function code snippet to understand return logic
            func_chunk = db.execute(
                "SELECT content FROM fonte_chunks WHERE upper(funcao)=? LIMIT 1",
                (fc_upper,),
            ).fetchone()
            if func_chunk and func_chunk[0]:
                code = func_chunk[0]
                # Extract return statements
                returns = _re.findall(r'\breturn\s+(.+)', code, _re.IGNORECASE)
                if returns:
                    dep["retornos"] = [r.strip()[:80] for r in returns[:3]]

                # Extract key logic patterns in the function
                # dbSeek / Posicione = looks up another table
                seeks = _re.findall(r'(?:dbSeek|Posicione)\s*\(["\']?(\w{2,3})', code, _re.IGNORECASE)
                if seeks:
                    dep["consulta_tabelas"] = list(set(s.upper() for s in seeks))

                # Field comparisons (ALIAS->CAMPO == 'value')
                comparisons = _re.findall(r'(\w{2,3})->(\w+)\s*==\s*["\']([^"\']+)["\']', code)
                if comparisons:
                    dep["verificacoes"] = [
                        f"{a}->{c} == '{v}'" for a, c, v in comparisons[:5]
                    ]

            # V2: get proposito if available
            if not dep.get("resumo"):
                prop_row = db.execute(
                    "SELECT proposito FROM propositos WHERE chave=?",
                    (dep.get("arquivo", ""),),
                ).fetchone()
                if prop_row and prop_row[0]:
                    try:
                        p = json.loads(prop_row[0])
                        dep["resumo"] = p.get("humano", "")[:200]
                    except (json.JSONDecodeError, TypeError):
                        dep["resumo"] = (prop_row[0] or "")[:200]

            # V3: Multi-fonte — follow calls into OTHER files (depth 1)
            sub_calls = dep.get("chama", [])
            func_arquivo = dep.get("arquivo", "")
            if sub_calls and func_arquivo:
                dep["sub_funcoes"] = []
                for sc in sub_calls[:3]:  # max 3 sub-calls to avoid explosion
                    sc_upper = sc.upper()
                    if sc_upper in seen_funcs:
                        continue
                    seen_funcs.add(sc_upper)

                    sc_row = db.execute(
                        "SELECT funcao, arquivo, resumo, tabelas_ref, campos_ref, params "
                        "FROM funcao_docs WHERE upper(funcao)=? LIMIT 1",
                        (sc_upper,),
                    ).fetchone()
                    if not sc_row:
                        continue

                    sub = {
                        "nome": f"U_{sc}",
                        "arquivo": sc_row[1] or "",
                        "cross_file": (sc_row[1] or "").upper() != func_arquivo.upper(),
                    }

                    sc_resumo = sc_row[2] or ""
                    if sc_resumo:
                        try:
                            sr = json.loads(sc_resumo)
                            sub["resumo"] = sr.get("humano", "")[:150]
                        except (json.JSONDecodeError, TypeError):
                            sub["resumo"] = sc_resumo[:150]

                    sub["tabelas_ref"] = _safe_json(sc_row[3])[:5]
                    sub["campos_ref"] = _safe_json(sc_row[4])[:5]

                    # Resolve params used by sub-function
                    sc_params = _safe_json(sc_row[5])
                    if isinstance(sc_params, dict):
                        for sp in sc_params.get("sx6", [])[:3]:
                            sp_var = sp.get("var", "")
                            if sp_var:
                                prow = db.execute(
                                    "SELECT variavel, descricao, conteudo FROM parametros "
                                    "WHERE upper(variavel)=? LIMIT 1",
                                    (sp_var.upper(),),
                                ).fetchone()
                                sub.setdefault("parametros", []).append({
                                    "variavel": sp_var,
                                    "valor_atual": prow[2] if prow else "?",
                                    "descricao": prow[1][:60] if prow else "",
                                })

                    # Get code snippet for return logic
                    sc_chunk = db.execute(
                        "SELECT content FROM fonte_chunks WHERE upper(funcao)=? LIMIT 1",
                        (sc_upper,),
                    ).fetchone()
                    if sc_chunk and sc_chunk[0]:
                        sc_code = sc_chunk[0]
                        sc_returns = _re.findall(r'\breturn\s+(.+)', sc_code, _re.IGNORECASE)
                        if sc_returns:
                            sub["retornos"] = [r.strip()[:60] for r in sc_returns[:3]]
                        sc_seeks = _re.findall(r'(?:dbSeek|Posicione)\s*\(["\']?(\w{2,3})', sc_code, _re.IGNORECASE)
                        if sc_seeks:
                            sub["consulta_tabelas"] = list(set(s.upper() for s in sc_seeks))
                        sc_comps = _re.findall(r'(\w{2,3})->(\w+)\s*==\s*["\']([^"\']+)["\']', sc_code)
                        if sc_comps:
                            sub["verificacoes"] = [f"{a}->{c} == '{v}'" for a, c, v in sc_comps[:3]]

                    dep["sub_funcoes"].append(sub)

            result["dependencias"].append(dep)

        # 2d. Pertinence operator ($ — very common in Protheus)
        pertinence = _re.findall(r'(\w+)\s*\$\s*(\w+)', definition_expr)
        for left, right in pertinence:
            # Check if right side is a variable we already found as parameter
            found = False
            for dep in result["dependencias"]:
                if dep["nome"].upper() == right.upper():
                    dep["usado_em"] = f"{left} $ {right} (pertinência)"
                    found = True
            if not found:
                result["dependencias"].append({
                    "nome": right,
                    "tipo": "variavel_local",
                    "usado_em": f"{left} $ {right} (pertinência)",
                    "nota": "Verificar definição desta variável no mesmo fonte",
                })

        # 3. Check if variable is reassigned elsewhere (e.g., Rondônia override)
        reassign_pattern = _re.compile(
            r'\b' + _re.escape(var_name) + r'\s*:=\s*(.+)',
            _re.IGNORECASE
        )
        reassign_count = 0
        for line in all_code.split('\n'):
            if reassign_pattern.search(line):
                reassign_count += 1
                if reassign_count > 1:  # First is the original definition
                    expr = reassign_pattern.search(line).group(1).strip()
                    result["blocos_alternativos"].append({
                        "expressao": expr[:200],
                        "contexto": line.strip()[:200],
                    })

        # 4. Find what the NOT(condition) block writes (the alternative path)
        ops_not = db.execute(
            "SELECT funcao, campos, condicao FROM operacoes_escrita "
            "WHERE arquivo=? AND condicao LIKE ? LIMIT 5",
            (arquivo, f"%NOT%{var_name}%"),
        ).fetchall()
        if not ops_not:
            ops_not = db.execute(
                "SELECT funcao, campos, condicao FROM operacoes_escrita "
                "WHERE arquivo=? AND funcao=? AND condicao LIKE '%NOT%' LIMIT 5",
                (arquivo, funcao),
            ).fetchall()
        for op in ops_not:
            result["blocos_alternativos"].append({
                "funcao": op[0],
                "campos_gravados": _safe_json(op[1]),
                "condicao": op[2] or "",
                "nota": "Este bloco executa quando a condição é FALSA",
            })

        return result
    finally:
        db.close()


def tool_mapear_processo(tabela: str, campo: str) -> dict:
    """Map a complete business process from a field with multiple write points.

    Performs lateral expansion:
    1. All write points for the field
    2. Companion fields (written together — same RecLock blocks)
    3. Satellite tables (other tables written by same sources)
    4. Process states (literal values written to the field)
    5. Source roles in the flow (what each program does)
    6. Complexity classification
    """
    db = _get_db()
    try:
        campo = campo.upper()
        tabela = tabela.upper()

        result = {
            "campo": campo,
            "tabela": tabela,
            "processo": {},
            "estados": [],
            "campos_companheiros": [],
            "tabelas_satelite": [],
            "fontes_no_fluxo": [],
            "complexidade": "simples",
        }

        # ── 1. All write points for this field ──
        ops = db.execute(
            "SELECT arquivo, funcao, tipo, campos, origens, condicao, linha "
            "FROM operacoes_escrita WHERE upper(tabela)=? AND campos LIKE ? "
            "ORDER BY arquivo, linha",
            (tabela, f'%{campo}%'),
        ).fetchall()

        if not ops:
            return result

        # ── 2. Companion fields (co-occurrence analysis) ──
        all_campos_in_ops = {}  # campo → count of ops it appears in
        total_ops = len(ops)
        arquivos_set = set()

        for op in ops:
            arquivo = op[0]
            arquivos_set.add(arquivo)
            campos_list = _safe_json(op[3])
            seen_in_op = set()  # avoid counting duplicates within same op
            for c in campos_list:
                if c != campo and c not in seen_in_op:
                    seen_in_op.add(c)
                    all_campos_in_ops[c] = all_campos_in_ops.get(c, 0) + 1

        # Companion = appears in 30%+ of the same ops
        threshold = max(2, int(total_ops * 0.3))
        companions = []
        for c, count in sorted(all_campos_in_ops.items(), key=lambda x: -x[1]):
            if count >= threshold:
                # Get field info
                crow = db.execute(
                    "SELECT titulo, tipo, tamanho, cbox FROM campos "
                    "WHERE upper(tabela)=? AND upper(campo)=? LIMIT 1",
                    (tabela, c.upper()),
                ).fetchone()
                companions.append({
                    "campo": c,
                    "titulo": crow[0] if crow else "",
                    "tipo": crow[1] if crow else "",
                    "cbox": crow[3] if crow else "",
                    "co_ocorrencia": round(count / total_ops * 100),
                    "vezes": count,
                })
        result["campos_companheiros"] = companions[:10]

        # ── 3. Satellite tables (written OR referenced by same sources) ──
        satelites = {}  # tabela → {"escritas": set, "leituras": set}
        for arquivo in arquivos_set:
            frow = db.execute(
                "SELECT write_tables, tabelas_ref FROM fontes WHERE upper(arquivo)=? LIMIT 1",
                (arquivo.upper(),),
            ).fetchone()
            if frow:
                for t in _safe_json(frow[0]):
                    t_upper = t.upper()
                    if t_upper != tabela:
                        satelites.setdefault(t_upper, {"escritas": set(), "leituras": set()})
                        satelites[t_upper]["escritas"].add(arquivo)
                for t in _safe_json(frow[1]):
                    t_upper = t.upper()
                    if t_upper != tabela and t_upper not in ("SM0", "SX1", "SX2", "SX3", "SX5", "SX6", "SX7", "SX9", "SIX"):
                        satelites.setdefault(t_upper, {"escritas": set(), "leituras": set()})
                        satelites[t_upper]["leituras"].add(arquivo)

        # Satellite = referenced by 2+ sources, prioritize custom tables and written tables
        sat_list = []
        for sat_tab, refs in sorted(satelites.items(), key=lambda x: -(len(x[1]["escritas"]) * 3 + len(x[1]["leituras"]))):
            total_refs = len(refs["escritas"]) + len(refs["leituras"])
            if total_refs >= 2 or len(refs["escritas"]) >= 1:
                trow = db.execute(
                    "SELECT codigo, nome, custom FROM tabelas WHERE upper(codigo)=?",
                    (sat_tab,),
                ).fetchone()
                sat_campos_count = db.execute(
                    "SELECT COUNT(*) FROM campos WHERE upper(tabela)=?", (sat_tab,)
                ).fetchone()[0]
                relacao = "escrita" if refs["escritas"] else "leitura"
                sat_list.append({
                    "tabela": sat_tab,
                    "nome": trow[1] if trow else "",
                    "custom": trow[2] if trow else 0,
                    "total_campos": sat_campos_count,
                    "fontes_escrita": len(refs["escritas"]),
                    "fontes_leitura": len(refs["leituras"]),
                    "relacao": relacao,
                    "arquivos": sorted(refs["escritas"] | refs["leituras"]),
                })
        result["tabelas_satelite"] = sat_list[:8]

        # ── 4. Process states (literal values written to the field) ──
        estados = {}  # value → list of (arquivo, funcao, acao)
        for op in ops:
            origens = _safe_json(op[4])
            if isinstance(origens, list):
                origens = {}
            valor_raw = origens.get(campo, "")
            if valor_raw.startswith("literal:"):
                valor = valor_raw.replace("literal:", "").strip("'\"")
                estados.setdefault(valor, []).append({
                    "arquivo": op[0], "funcao": op[1], "tipo": op[2],
                })

        state_list = []
        for valor, fontes in estados.items():
            # Try to infer meaning from value
            significado = ""
            if valor.upper() in ("B", "S"):
                significado = "Bloqueado/Sim"
            elif valor.upper() in ("L", "N"):
                significado = "Liberado/Não"
            state_list.append({
                "valor": valor,
                "significado": significado,
                "gravado_por": fontes,
                "total_fontes": len(fontes),
            })
        result["estados"] = state_list

        # ── 5. Source roles in the flow ──
        fontes_info = []
        for arquivo in sorted(arquivos_set):
            # Get source info
            frow = db.execute(
                "SELECT modulo, lines_of_code, user_funcs, pontos_entrada FROM fontes "
                "WHERE upper(arquivo)=? LIMIT 1",
                (arquivo.upper(),),
            ).fetchone()

            # Get proposito
            prop = ""
            prow = db.execute(
                "SELECT proposito FROM propositos WHERE chave=?", (arquivo,)
            ).fetchone()
            if prow and prow[0]:
                try:
                    p = json.loads(prow[0])
                    prop = p.get("humano", "")[:200]
                except (json.JSONDecodeError, TypeError):
                    prop = (prow[0] or "")[:200]

            # What does this source do to the field? (B or L)
            acoes = []
            ops_deste = [op for op in ops if op[0] == arquivo]
            for op in ops_deste:
                origens = _safe_json(op[4])
                if isinstance(origens, list):
                    origens = {}
                valor_raw = origens.get(campo, "")
                tipo_op = op[2]
                condicao = op[5] or ""
                acoes.append({
                    "funcao": op[1],
                    "tipo": tipo_op,
                    "valor_gravado": valor_raw,
                    "condicao": condicao[:80],
                    "linha": op[6],
                })

            # What other tables does this source write?
            outras_tabelas = []
            if frow:
                for sat in result["tabelas_satelite"]:
                    if arquivo in sat.get("arquivos", []):
                        outras_tabelas.append(sat["tabela"])

            fontes_info.append({
                "arquivo": arquivo,
                "modulo": frow[0] if frow else "",
                "loc": frow[1] if frow else 0,
                "proposito": prop,
                "acoes": acoes,
                "tabelas_satelite": outras_tabelas,
                "user_funcs": _safe_json(frow[2])[:5] if frow else [],
                "pes": _safe_json(frow[3]) if frow else [],
            })

        result["fontes_no_fluxo"] = fontes_info

        # ── 6. Complexity classification ──
        n_fontes = len(arquivos_set)
        n_satelites = len(sat_list)
        n_estados = len(state_list)
        n_companions = len(companions)

        if n_fontes >= 5 and n_satelites >= 2:
            result["complexidade"] = "alta"
        elif n_fontes >= 3 or n_satelites >= 1:
            result["complexidade"] = "media"
        else:
            result["complexidade"] = "simples"

        result["processo"] = {
            "total_pontos_escrita": total_ops,
            "total_fontes": n_fontes,
            "total_tabelas_satelite": n_satelites,
            "total_estados": n_estados,
            "total_campos_companheiros": n_companions,
        }

        return result
    finally:
        db.close()


def tool_info_tabela(tabela: str) -> dict:
    """Get table info: name, fields count, custom fields, indices."""
    db = _get_db()
    try:
        row = db.execute(
            "SELECT codigo, nome FROM tabelas WHERE upper(codigo)=?", (tabela.upper(),)
        ).fetchone()
        if not row:
            return {"tabela": tabela, "existe": False}

        total = db.execute("SELECT COUNT(*) FROM campos WHERE upper(tabela)=?", (tabela.upper(),)).fetchone()[0]
        custom = db.execute("SELECT COUNT(*) FROM campos WHERE upper(tabela)=? AND custom=1", (tabela.upper(),)).fetchone()[0]
        indices = db.execute("SELECT COUNT(*) FROM indices WHERE upper(tabela)=?", (tabela.upper(),)).fetchone()[0]

        return {
            "tabela": row[0], "nome": row[1], "existe": True,
            "total_campos": total, "campos_custom": custom, "indices": indices,
        }
    finally:
        db.close()


def tool_processos_cliente(tabelas: list | None = None) -> dict:
    """List detected business processes for the client (cached).

    Args:
        tabelas: Optional list of table codes to filter by (e.g. ['SC5', 'SZV']).
                 Returns only processes that involve those tables.
    """
    db = _get_db()
    try:
        count = db.execute("SELECT COUNT(*) FROM processos_detectados").fetchone()[0]
        if count == 0:
            return {"total": 0, "processos": [], "status": "sem_cache"}

        rows = db.execute(
            "SELECT id, nome, tipo, descricao, criticidade, tabelas, score, fluxo_mermaid "
            "FROM processos_detectados ORDER BY score DESC"
        ).fetchall()

        processos = []
        for r in rows:
            tabs = _safe_json(r[5])
            if tabelas:
                tabs_upper = {t.upper() for t in tabs}
                filtro_upper = {t.upper() for t in tabelas}
                if not tabs_upper.intersection(filtro_upper):
                    continue
            processos.append({
                "id": r[0], "nome": r[1], "tipo": r[2], "descricao": r[3],
                "criticidade": r[4], "tabelas": tabs, "score": r[6],
                "fluxo_mermaid": r[7],
            })

        return {"total": len(processos), "processos": processos, "status": "ok"}
    finally:
        db.close()


def tool_registrar_processo(
    nome: str, tipo: str, descricao: str,
    tabelas: list[str] | None = None, criticidade: str = "media",
) -> dict:
    """Register or enrich a client business process.
    If a similar process exists (by name), enriches it. Otherwise creates new.
    Used silently by the Analista during conversations.
    """
    import json as _json

    db = _get_db()
    try:
        tabelas = tabelas or []

        # Stage 1: Cheap text match
        termos = nome.lower().split()
        candidatos = []
        for termo in termos:
            if len(termo) < 3:
                continue
            rows = db.execute(
                "SELECT id, nome, tipo, descricao, tabelas, score FROM processos_detectados "
                "WHERE lower(nome) LIKE ? OR lower(descricao) LIKE ? "
                "ORDER BY score DESC LIMIT 10",
                (f"%{termo}%", f"%{termo}%"),
            ).fetchall()
            for r in rows:
                if r[0] not in [c["id"] for c in candidatos]:
                    candidatos.append({
                        "id": r[0], "nome": r[1], "tipo": r[2],
                        "descricao": r[3], "tabelas": _safe_json(r[4]), "score": r[5],
                    })

        # Stage 2: Simplified from spec's LLM-based matching to avoid nested LLM calls
        # from within tool execution context. Uses substring match instead of LLM scoring.
        best_match = None
        if candidatos:
            nome_lower = nome.lower().strip()
            for c in candidatos:
                c_nome_lower = c["nome"].lower().strip()
                if c_nome_lower == nome_lower or nome_lower in c_nome_lower or c_nome_lower in nome_lower:
                    best_match = c
                    break

        if best_match:
            existing_tabs = set(best_match["tabelas"])
            new_tabs = existing_tabs | set(tabelas)
            new_desc = best_match["descricao"]
            if descricao and descricao not in new_desc:
                new_desc = f"{new_desc}\n{descricao}".strip()

            db.execute(
                "UPDATE processos_detectados SET tabelas=?, descricao=?, updated_at=datetime('now') WHERE id=?",
                (_json.dumps(list(new_tabs)), new_desc, best_match["id"]),
            )
            db.commit()

            return {
                "acao": "enriquecido",
                "processo": {**best_match, "tabelas": list(new_tabs), "descricao": new_desc},
            }
        else:
            db.execute(
                "INSERT INTO processos_detectados (nome, tipo, descricao, criticidade, tabelas, metodo, score) "
                "VALUES (?, ?, ?, ?, ?, 'manual', 0.5)",
                (nome, tipo, descricao, criticidade, _json.dumps(tabelas)),
            )
            db.commit()
            new_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

            return {
                "acao": "criado",
                "processo": {
                    "id": new_id, "nome": nome, "tipo": tipo, "descricao": descricao,
                    "criticidade": criticidade, "tabelas": tabelas, "score": 0.5,
                },
            }
    finally:
        db.close()


def investigar_campo_escrita(tabela: str, campo: str) -> dict:
    """Investigate the complete write chain for a specific field.

    Traces: field → write operations → conditions → variables → parameters → values.
    Pure SQL/regex, no LLM calls.

    Args:
        tabela: Table code (e.g., 'ZZM')
        campo: Field name (e.g., 'ZZM_VLDESC') — can be partial (e.g., 'VLDESC')
    """
    import re as _re

    db = _get_db()
    try:
        # Normalize campo name
        campo_upper = campo.upper()
        if not campo_upper.startswith(tabela.upper()[:3]):
            campo_upper = f"{tabela.upper()[:3]}_{campo_upper}"

        # 1. Get campo info from SX3
        campo_info = {}
        row = db.execute(
            "SELECT campo, tipo, tamanho, decimal, titulo, descricao, validacao, vlduser "
            "FROM campos WHERE upper(campo) = ?",
            (campo_upper,),
        ).fetchone()
        if row:
            campo_info = {
                "campo": row[0], "tipo": row[1], "tamanho": row[2], "decimal": row[3],
                "titulo": row[4], "descricao": row[5], "validacao": row[6] or "", "vlduser": row[7] or "",
            }
        else:
            # Try partial match
            row = db.execute(
                "SELECT campo, tipo, tamanho, decimal, titulo, descricao, validacao, vlduser "
                "FROM campos WHERE upper(tabela) = ? AND upper(campo) LIKE ?",
                (tabela.upper(), f"%{campo.upper().replace(tabela.upper()[:3] + '_', '')}%"),
            ).fetchone()
            if row:
                campo_upper = row[0].upper()
                campo_info = {
                    "campo": row[0], "tipo": row[1], "tamanho": row[2], "decimal": row[3],
                    "titulo": row[4], "descricao": row[5], "validacao": row[6] or "", "vlduser": row[7] or "",
                }

        # 2. Find all write operations for this table
        ops_rows = db.execute(
            "SELECT arquivo, funcao, tipo, campos, origens, condicao, linha "
            "FROM operacoes_escrita WHERE upper(tabela) = ?",
            (tabela.upper(),),
        ).fetchall()

        operacoes = []
        for op in ops_rows:
            campos_list = _safe_json(op[3])
            origens_dict = {}
            try:
                origens_dict = json.loads(op[4]) if op[4] else {}
            except Exception:
                pass

            # Check if this specific campo is in this operation
            campo_in_op = any(campo_upper in c.upper() for c in campos_list)

            op_data = {
                "arquivo": op[0],
                "funcao": op[1],
                "tipo": op[2],
                "condicao": op[5] or "",
                "linha": op[6],
                "grava_campo": campo_in_op,
                "campos_gravados": campos_list,
                "origem_campo": origens_dict.get(campo_info.get("campo", campo_upper), ""),
                "variaveis_condicao": [],
            }

            # 3. Extract variables from condition and trace them
            if op[5]:
                op_data["variaveis_condicao"] = _trace_condition_variables(
                    db, op[0], op[5]
                )

            operacoes.append(op_data)

        # 4. Build diagnostic
        ops_that_write = [o for o in operacoes if o["grava_campo"]]
        ops_that_dont = [o for o in operacoes if not o["grava_campo"] and o["condicao"]]
        all_params = set()
        conditions_that_block = []
        for op in ops_that_write:
            if op["condicao"]:
                conditions_that_block.append(
                    f"{op['condicao']} (em {op['funcao']}, {op['arquivo']})"
                )
            for vc in op["variaveis_condicao"]:
                for p in vc.get("parametros_envolvidos", []):
                    all_params.add(p["nome"])

        diagnostico = {
            "grava_sempre": any(not o["condicao"] for o in ops_that_write),
            "condicional": any(o["condicao"] for o in ops_that_write),
            "total_operacoes": len(operacoes),
            "operacoes_que_gravam": len(ops_that_write),
            "operacoes_que_nao_gravam": len(ops_that_dont),
            "condicoes_que_controlam": conditions_that_block,
            "parametros_chave": sorted(all_params),
        }

        return {
            "tabela": tabela,
            "campo": campo_info.get("campo", campo_upper),
            "campo_info": campo_info,
            "operacoes": operacoes,
            "diagnostico": diagnostico,
        }
    finally:
        db.close()


def investigar_problema(tabela: str, campo: str = "", acao: str = "nao_salva") -> dict:
    """High-level investigation wrapper that combines graph context + directed field investigation.

    Used by the Analista to answer "field X doesn't save" type questions.

    Args:
        tabela: Table code (e.g., 'ZZM')
        campo: Field name (e.g., 'ZZM_VLDESC') — optional, if empty investigates the table generally
        acao: Problem type — 'nao_salva', 'nao_atualiza', 'erro', 'nao_processa'
    """
    import json as _json

    result = {
        "tabela": tabela,
        "campo": campo,
        "acao": acao,
        "campo_investigacao": None,
        "graph_context": "",
        "processos_vinculados": [],
        "contexto_llm": "",
    }

    # 1. Graph context for ecosystem overview (lightweight)
    try:
        db = _get_db()
        from app.services.workspace.graph_traversal import traverse_graph, format_context_for_llm
        ctx = traverse_graph(db, tabela, "tabela", max_depth=1)  # depth=1 for overview only
        result["graph_context"] = format_context_for_llm(ctx)

        # Find linked processes
        proc_result = tool_processos_cliente(tabelas=[tabela])
        result["processos_vinculados"] = [
            {"id": p["id"], "nome": p["nome"], "tipo": p["tipo"]}
            for p in proc_result.get("processos", [])
        ]
        db.close()
    except Exception:
        pass

    # 2. Directed field investigation (the deep part)
    if campo:
        try:
            result["campo_investigacao"] = investigar_campo_escrita(tabela, campo)
        except Exception:
            pass

    # 3. Build focused LLM context
    parts = []

    # Ecosystem summary (compact)
    if result["graph_context"]:
        # Only include tables and parameters sections, not the full graph
        for line in result["graph_context"].split("\n"):
            if line.startswith("###") or line.startswith("CONTEXTO"):
                parts.append(line)
            elif line.startswith("Leitura:") or line.startswith("Escrita:"):
                parts.append(line)

    # Processes
    if result["processos_vinculados"]:
        parts.append(f"\nPROCESSOS: {', '.join(p['nome'] for p in result['processos_vinculados'][:5])}")

    # Campo investigation (the focused part)
    inv = result["campo_investigacao"]
    if inv:
        ci = inv.get("campo_info", {})
        parts.append(f"\n### CAMPO INVESTIGADO: {inv['campo']}")
        if ci:
            parts.append(f"Tipo: {ci.get('tipo')}, Tamanho: {ci.get('tamanho')}, Titulo: {ci.get('titulo')}")

        diag = inv.get("diagnostico", {})
        parts.append(f"Operacoes totais na tabela: {diag.get('total_operacoes', 0)}")
        parts.append(f"Operacoes que GRAVAM este campo: {diag.get('operacoes_que_gravam', 0)}")
        if diag.get("condicoes_que_controlam"):
            parts.append("Condicoes que controlam a gravacao:")
            for c in diag["condicoes_que_controlam"]:
                parts.append(f"  - {c}")
        if diag.get("parametros_chave"):
            parts.append(f"Parametros chave: {', '.join(diag['parametros_chave'][:10])}")

        # Detail each operation that writes the field
        for op in inv.get("operacoes", []):
            if not op["grava_campo"]:
                continue
            parts.append(f"\n#### ESCRITA: {op['funcao']} ({op['arquivo']}) — {op['tipo']}")
            if op["condicao"]:
                parts.append(f"Condicao: {op['condicao']}")
            if op["origem_campo"]:
                parts.append(f"Origem do valor: {op['origem_campo']}")

            for vc in op["variaveis_condicao"]:
                # Show the trace chain (recursive variable resolution)
                if vc.get("trace_chain"):
                    parts.append(f"Rastreamento da variavel '{vc['variavel']}':")
                    for tc in vc["trace_chain"]:
                        indent = "  " * (tc["depth"] + 1)
                        parts.append(f"{indent}{tc['var']} := {tc['def'][:150]}")
                elif vc["definicao"]:
                    parts.append(f"Variavel '{vc['variavel']}' definida como: {vc['definicao'][:250]}")
                # All parameters found in the chain (already filtered by recursive trace)
                for p in vc["parametros_envolvidos"][:10]:
                    via = f" (via U_{p['via_funcao']})" if p.get("via_funcao") else ""
                    parts.append(f"  Parametro {p['nome']} = {p['valor'][:80]} — {p['descricao'][:80]}{via}")
                for f in vc["funcoes_chamadas"]:
                    parts.append(f"  Chama funcao: U_{f}")

        # Detail each U_ function called in the condition chain
        all_funcs_seen = set()
        for op in inv.get("operacoes", []):
            if not op["grava_campo"]:
                continue
            for vc in op["variaveis_condicao"]:
                for f in vc["funcoes_chamadas"]:
                    if f not in all_funcs_seen:
                        all_funcs_seen.add(f)
                        try:
                            db = _get_db()
                            func_detail = _extract_function_logic(db, f)
                            db.close()
                            if func_detail.get("resumo"):
                                parts.append(f"\n#### Funcao U_{f} ({func_detail['arquivo']}):")
                                parts.append(func_detail["resumo"])
                                if func_detail.get("condicoes"):
                                    parts.append("Condicoes na funcao:")
                                    for c in func_detail["condicoes"][:4]:
                                        parts.append(f"  {c}")
                        except Exception:
                            pass

        # Also show operations that DON'T write the field (for contrast)
        non_writing = [o for o in inv.get("operacoes", []) if not o["grava_campo"] and o["condicao"]]
        if non_writing and acao in ("nao_salva", "nao_atualiza"):
            parts.append(f"\n#### OPERACOES QUE NAO GRAVAM {inv['campo']} (blocos alternativos):")
            for op in non_writing[:5]:
                campos_str = ", ".join(op["campos_gravados"][:5])
                parts.append(f"  {op['funcao']} ({op['arquivo']}): cond={op['condicao'][:60]} grava=[{campos_str}]")

    result["contexto_llm"] = "\n".join(parts)
    return result


def _extract_function_logic(db, func_name: str) -> dict:
    """Extract structured logic summary from a function's source code.
    Pure code analysis, no LLM. ~15ms per function.

    Returns:
        {
            "nome": "EmiteRondonia",
            "arquivo": "MGFTAE15.PRW",
            "assinatura": "EmiteRondonia(_cFilial, _cForn, _cLojf)",
            "parametros_usados": [{"nome": "MGF_TAE15R", "valor": "RO", "descricao": "..."}],
            "tabelas_consultadas": ["SA2", "SM0"],
            "campos_verificados": ["A2_TIPO", "A2_EST"],
            "condicoes": ["SA2->A2_TIPO == 'F' .and. SA2->A2_EST $ _cUFROND"],
            "retorno": "_lRet (.T./.F.)",
            "comentarios": "Se Fornecedor for PF de Rondônia → .T., PJ de Rondônia → .F.",
            "resumo": "Verifica se fornecedor (PF/PJ) de Rondônia pode emitir doc. PF=sim, PJ=não."
        }
    """
    import re as _re

    result = {
        "nome": func_name,
        "arquivo": "",
        "assinatura": "",
        "parametros_usados": [],
        "tabelas_consultadas": [],
        "campos_verificados": [],
        "condicoes": [],
        "retorno": "",
        "comentarios": "",
        "resumo": "",
        "codigo": "",
    }

    # Find which file defines this function
    f_row = db.execute(
        "SELECT destino FROM vinculos WHERE tipo='funcao_definida_em' AND upper(origem) = ?",
        (func_name.upper(),),
    ).fetchone()
    if not f_row:
        return result
    result["arquivo"] = f_row[0]

    # Get funcao_docs info
    fd_row = db.execute(
        "SELECT assinatura, resumo, tabelas_ref, campos_ref, retorno FROM funcao_docs WHERE funcao = ?",
        (func_name,),
    ).fetchone()
    if fd_row:
        result["assinatura"] = fd_row[0] or ""
        result["tabelas_consultadas"] = json.loads(fd_row[2]) if fd_row[2] else []
        result["campos_verificados"] = json.loads(fd_row[3]) if fd_row[3] else []
        result["retorno"] = fd_row[4] or ""

    # Extract the function's source code
    chunks = db.execute(
        "SELECT content FROM fonte_chunks WHERE arquivo = ?",
        (f_row[0],),
    ).fetchall()

    func_lines = []
    in_func = False
    for chunk in chunks:
        for line in chunk[0].split('\n'):
            lu = line.strip().upper()
            if func_name.upper() in lu and ('FUNCTION' in lu):
                in_func = True
            elif in_func and (lu.startswith('USER FUNCTION') or lu.startswith('STATIC FUNCTION')):
                in_func = False
                break
            elif in_func and lu == 'RETURN':
                func_lines.append(line)
                in_func = False
                break
            if in_func:
                func_lines.append(line)
        if func_lines and not in_func:
            break

    if not func_lines:
        return result

    source = '\n'.join(func_lines)
    result["codigo"] = source[:2000]

    # Extract comments (between /* */ or after //)
    comments = []
    in_comment = False
    for line in func_lines:
        stripped = line.strip()
        if '/*' in stripped:
            in_comment = True
        if in_comment:
            clean = stripped.replace('/*', '').replace('*/', '').strip()
            if clean and len(clean) > 5:
                comments.append(clean)
        if '*/' in stripped:
            in_comment = False
        elif stripped.startswith('//'):
            clean = stripped[2:].strip()
            if clean and len(clean) > 5:
                comments.append(clean)
    result["comentarios"] = ' | '.join(comments[:5])

    # Extract parameters (GetMV/SuperGetMV)
    param_pat = _re.compile(
        r'(?:GetMV|SuperGetMV|GetNewPar)\s*\(\s*[\"\x27]((?:MV_|MGF_)\w+)',
        _re.IGNORECASE
    )
    for m in param_pat.finditer(source):
        param = m.group(1).upper()
        if not any(p["nome"] == param for p in result["parametros_usados"]):
            p_row = db.execute(
                "SELECT conteudo, descricao FROM parametros WHERE upper(variavel) = ?",
                (param,),
            ).fetchone()
            result["parametros_usados"].append({
                "nome": param,
                "valor": p_row[0] if p_row else "",
                "descricao": p_row[1] if p_row else "",
            })

    # Extract conditions (IF/ELSEIF lines)
    for line in func_lines:
        stripped = line.strip()
        su = stripped.upper()
        if su.startswith('IF ') or su.startswith('ELSEIF ') or su.startswith('ELSE'):
            cond = stripped[:150]
            result["condicoes"].append(cond)

    # Extract return variable
    for line in reversed(func_lines):
        stripped = line.strip().upper()
        if stripped.startswith('RETURN'):
            result["retorno"] = line.strip()[6:].strip()[:80]
            break

    # Build structured resume
    parts = []
    if result["assinatura"]:
        parts.append(f"Funcao {result['assinatura']}")
    if result["comentarios"]:
        parts.append(f"Proposito: {result['comentarios'][:200]}")
    if result["parametros_usados"]:
        p_list = ', '.join(f"{p['nome']}={p['valor'][:20]}" for p in result["parametros_usados"])
        parts.append(f"Parametros: {p_list}")
    if result["tabelas_consultadas"]:
        parts.append(f"Consulta: {', '.join(result['tabelas_consultadas'])}")
    if result["campos_verificados"]:
        parts.append(f"Campos: {', '.join(result['campos_verificados'][:10])}")
    if result["condicoes"]:
        parts.append(f"Logica: {' | '.join(result['condicoes'][:3])}")
    if result["retorno"]:
        parts.append(f"Retorna: {result['retorno']}")
    result["resumo"] = '. '.join(parts)

    # Update funcao_docs.resumo if currently empty
    if fd_row and not fd_row[1] and result["resumo"]:
        try:
            db.execute(
                "UPDATE funcao_docs SET resumo = ?, retorno = ?, updated_at = datetime('now') WHERE funcao = ?",
                (result["resumo"][:500], result["retorno"][:100], func_name),
            )
            db.commit()
        except Exception:
            pass

    return result


def _trace_condition_variables(db, arquivo: str, condicao: str) -> list:
    """Trace variables in a condition back to their definitions using recursive var_map.

    Builds a variable definition map for the fonte (~10ms), then recursively traces
    each variable in the condition until reaching GetMV parameters or literals.

    For 'bEmite' this produces:
      bEmite → IIF(ZZM_FILIAL $ cFILDUPL, ...)
        cFILDUPL → GetMV('MGF_TAE15A') = "010048"
        cFILNFE → GetMV('MGF_TAE17') = "010005;010064;010068"
      bEmite → U_EmiteRondonia(...)
        EmiteRondonia uses MGF_TAE15R = "RO"
    """
    import re as _re

    SKIP_WORDS = {
        'AND', 'OR', 'NOT', 'IF', 'ELSE', 'ENDIF', 'TRUE', 'FALSE',
        'NIL', 'EOF', 'EMPTY', 'LEN', 'VAL', 'STR', 'STOD', 'DTOC', 'DTOS',
        'IIF', 'MSGRLOCK', 'DBSEEK', 'XFILIAL', 'PADR', 'SUBSTR', 'ALLTRIM',
        'TAMSXS', 'RECLOCK', 'MSUNLOCK', 'MSGBOX', 'MSGYESNO', 'QRY',
        'PRIVATE', 'LOCAL', 'PUBLIC', 'STATIC', 'CRIAVAR', 'ARRAY',
    }

    param_pat = _re.compile(
        r'(?:GetMV|SuperGetMV|GetNewPar)\s*\(\s*[\"\x27]((?:MV_|MGF_)\w+)',
        _re.IGNORECASE
    )
    func_pat = _re.compile(r'\bU_(\w+)\s*\(', _re.IGNORECASE)

    def _build_var_map(arq: str) -> dict:
        """Build variable definition map for a fonte. ~10ms per fonte.
        Captures ALL assignments for each variable (a var can be reassigned)."""
        var_map = {}
        try:
            chunks = db.execute(
                "SELECT content FROM fonte_chunks WHERE arquivo = ?", (arq,)
            ).fetchall()
            for chunk in chunks:
                for line in chunk[0].split('\n'):
                    m = _re.match(r'.*?\b([a-zA-Z_]\w+)\s*:=\s*(.+)', line)
                    if m:
                        var_name = m.group(1)
                        definition = m.group(2).strip()[:300]
                        params = [p.upper() for p in param_pat.findall(definition)]
                        funcs = func_pat.findall(definition)
                        entry = {'def': definition, 'params': params, 'funcs': funcs}

                        if var_name not in var_map:
                            # First definition — store as primary
                            var_map[var_name] = entry
                            var_map[var_name]['extra_defs'] = []
                        else:
                            # Additional assignment — store if different and has new info
                            existing = var_map[var_name]
                            if definition != existing['def']:
                                existing['extra_defs'].append(entry)
                                # Merge params and funcs from all definitions
                                for p in params:
                                    if p not in existing['params']:
                                        existing['params'].append(p)
                                for f in funcs:
                                    if f not in existing['funcs']:
                                        existing['funcs'].append(f)
        except Exception:
            pass
        return var_map

    def _trace_var(var_name: str, var_map: dict, depth: int = 0, visited: set = None) -> list:
        """Recursively trace a variable through its definition chain."""
        if visited is None:
            visited = set()
        if var_name in visited or depth > 4:
            return []
        visited.add(var_name)

        info = var_map.get(var_name)
        if not info:
            return []

        # Include extra definitions (reassignments like bEmite := U_EmiteRondonia)
        extra_defs_text = ""
        for ed in info.get('extra_defs', []):
            if ed['funcs'] or ed['params']:
                extra_defs_text += f" | tambem: {ed['def'][:150]}"

        node = {
            'depth': depth,
            'var': var_name,
            'def': info['def'] + extra_defs_text,
            'params': info['params'],
            'funcs': info['funcs'],
        }
        result = [node]

        # Find variables referenced in this definition and trace them
        ref_tokens = _re.findall(r'\b([a-zA-Z_]\w+)\b', info['def'])
        for ref in ref_tokens:
            if (ref.upper() not in SKIP_WORDS and ref != var_name
                    and ref in var_map and ref not in visited
                    and len(ref) > 2
                    and not (len(ref) > 3 and ref[2] == '_' and ref[:2].isalpha())):  # skip fields like A1_COD
                result.extend(_trace_var(ref, var_map, depth + 1, visited))

        return result

    # ── Extract condition variables ──
    tokens = _re.findall(r'\b([a-zA-Z_]\w+)\b', condicao)
    cond_vars = []
    seen = set()
    for token in tokens:
        t_upper = token.upper()
        if t_upper in SKIP_WORDS or t_upper in seen or len(token) < 3:
            continue
        if len(token) > 3 and token[2] == '_' and token[:2].isalpha():
            continue  # skip fields
        seen.add(t_upper)
        cond_vars.append(token)

    # ── Build var_map for the main fonte ──
    var_map = _build_var_map(arquivo)

    # ── Trace each condition variable ──
    results = []
    all_params = []
    all_funcs = []

    for var in cond_vars[:5]:
        trace = _trace_var(var, var_map)
        if not trace:
            continue

        var_info = {
            "variavel": var,
            "definicao": trace[0]['def'] if trace else "",
            "parametros_envolvidos": [],
            "funcoes_chamadas": [],
            "trace_chain": [],  # the full trace for context
        }

        # Collect all params and funcs from the trace chain
        for node in trace:
            var_info["trace_chain"].append({
                "var": node['var'],
                "def": node['def'][:200],
                "depth": node['depth'],
            })
            for param in node['params']:
                if param not in [p['nome'] for p in var_info['parametros_envolvidos']]:
                    p_row = db.execute(
                        "SELECT conteudo, descricao FROM parametros WHERE upper(variavel) = ?",
                        (param,),
                    ).fetchone()
                    var_info["parametros_envolvidos"].append({
                        "nome": param,
                        "valor": p_row[0] if p_row else "(não encontrado)",
                        "descricao": p_row[1] if p_row else "",
                    })
            for func in node['funcs']:
                if func not in var_info['funcoes_chamadas']:
                    var_info['funcoes_chamadas'].append(func)

        # ── Follow U_ functions: use _extract_function_logic (isolates function body) ──
        for func_name in var_info['funcoes_chamadas'][:3]:
            func_detail = _extract_function_logic(db, func_name)
            if func_detail.get("parametros_usados"):
                for p in func_detail["parametros_usados"]:
                    if p["nome"] not in [pp['nome'] for pp in var_info['parametros_envolvidos']]:
                        var_info["parametros_envolvidos"].append({
                            "nome": p["nome"],
                            "valor": p["valor"] or "(não encontrado)",
                            "descricao": p["descricao"] or "",
                            "via_funcao": func_name,
                        })

        if var_info["definicao"] or var_info["parametros_envolvidos"]:
            results.append(var_info)

    return results


# ─────────────────────── V2 Tools: Source Reading & Search ───────────────────────


def tool_ler_fonte_cliente(arquivo: str, funcao: str = "") -> dict:
    """Read actual source code chunk from client fonte_chunks.

    Args:
        arquivo: Source filename (e.g., 'MGFFAT16.prw')
        funcao: Specific function name (optional — if empty, returns all chunks for file)

    Returns:
        {encontrado, arquivo, funcao, content} or {encontrado: False}
    """
    db = _get_db()
    try:
        if funcao:
            row = db.execute(
                "SELECT id, arquivo, funcao, content FROM fonte_chunks "
                "WHERE UPPER(arquivo) = ? AND UPPER(funcao) = ? LIMIT 1",
                (arquivo.upper(), funcao.upper())
            ).fetchone()
            if row:
                return {"encontrado": True, "arquivo": row[1], "funcao": row[2], "content": row[3]}
        else:
            rows = db.execute(
                "SELECT funcao, content FROM fonte_chunks WHERE UPPER(arquivo) = ? ORDER BY id",
                (arquivo.upper(),)
            ).fetchall()
            if rows:
                combined = "\n\n".join(f"// === {r[0]} ===\n{r[1]}" for r in rows)
                return {"encontrado": True, "arquivo": arquivo, "funcao": "(all)", "content": combined[:6000]}

        return {"encontrado": False, "arquivo": arquivo, "funcao": funcao}
    finally:
        db.close()


def tool_buscar_texto_fonte(arquivo: str, texto: str, contexto: int = 15) -> dict:
    """Search for a text pattern inside a source file and return surrounding code.

    Reads the actual file from disk (not chunks) to find any text pattern.
    Useful for searching tags, variables, comments that may not be in chunks.

    Args:
        arquivo: Source filename (e.g., 'nfesefaz.prw')
        texto: Text to search for (case-insensitive)
        contexto: Lines of context before and after each match (default 15)

    Returns:
        {encontrado, arquivo, total_ocorrencias, ocorrencias: [{linha, funcao, trecho}]}
    """
    import re
    from pathlib import Path
    from app.services.workspace.parser_source import _read_file

    # Find the file
    search_dirs = [
        Path("D:/Clientes/Customizados"),
        Path("workspace"),
    ]
    file_path = None
    for d in search_dirs:
        if d.exists():
            candidates = list(d.rglob(f"*{arquivo}*"))
            if candidates:
                file_path = candidates[0]
                break

    if not file_path or not file_path.exists():
        # Try fonte_chunks as fallback
        db = _get_db()
        try:
            rows = db.execute(
                "SELECT funcao, content FROM fonte_chunks WHERE UPPER(arquivo) = ? ORDER BY id",
                (arquivo.upper(),)
            ).fetchall()
            if rows:
                combined = "\n".join(r[1] for r in rows)
                lines = combined.split("\n")
                ocorrencias = []
                texto_lower = texto.lower()
                for i, line in enumerate(lines):
                    if texto_lower in line.lower():
                        start = max(0, i - contexto)
                        end = min(len(lines), i + contexto + 1)
                        trecho = "\n".join(f"{j+1:5d}  {lines[j][:150]}" for j in range(start, end))
                        ocorrencias.append({"linha": i + 1, "funcao": "", "trecho": trecho})
                return {
                    "encontrado": bool(ocorrencias), "arquivo": arquivo,
                    "total_ocorrencias": len(ocorrencias),
                    "ocorrencias": ocorrencias[:5],
                    "fonte": "chunks",
                }
        finally:
            db.close()
        return {"encontrado": False, "arquivo": arquivo, "total_ocorrencias": 0, "ocorrencias": []}

    try:
        content = _read_file(file_path)
        lines = content.split("\n")
        texto_lower = texto.lower()

        # Find function boundaries for context
        func_pattern = re.compile(r'(?:Static\s+|User\s+|Main\s+)?Function\s+(\w+)', re.IGNORECASE)
        func_ranges = []
        for i, line in enumerate(lines):
            m = func_pattern.search(line)
            if m:
                func_ranges.append((i, m.group(1)))

        def _get_func(line_no):
            func = arquivo
            for start, name in func_ranges:
                if start <= line_no:
                    func = name
                else:
                    break
            return func

        ocorrencias = []
        for i, line in enumerate(lines):
            if texto_lower in line.lower():
                start = max(0, i - contexto)
                end = min(len(lines), i + contexto + 1)
                trecho_lines = []
                for j in range(start, end):
                    marker = ">>>" if j == i else "   "
                    trecho_lines.append(f"{j+1:5d} {marker} {lines[j][:150]}")
                ocorrencias.append({
                    "linha": i + 1,
                    "funcao": _get_func(i),
                    "trecho": "\n".join(trecho_lines),
                })

        return {
            "encontrado": bool(ocorrencias), "arquivo": arquivo,
            "total_ocorrencias": len(ocorrencias),
            "ocorrencias": ocorrencias[:5],  # max 5 matches
            "fonte": "disco",
        }
    except Exception as e:
        return {"encontrado": False, "arquivo": arquivo, "erro": str(e)[:200]}


def tool_buscar_menus(termo: str) -> list[dict]:
    """Search client menus by keyword.

    Args:
        termo: Search term (e.g., 'liberação pedido')

    Returns:
        List of {modulo, rotina, nome, menu_path}
    """
    db = _get_db()
    try:
        words = [w for w in termo.lower().split() if len(w) >= 3]
        if not words:
            return []

        conditions = " AND ".join(["LOWER(nome) LIKE ?"] * len(words))
        params = tuple(f"%{w}%" for w in words)

        rows = db.execute(
            f"SELECT modulo, rotina, nome, menu FROM menus WHERE {conditions} ORDER BY nome LIMIT 15",
            params
        ).fetchall()

        return [
            {"modulo": r[0], "rotina": r[1], "nome": r[2], "menu_path": r[3] or ""}
            for r in rows
        ]
    finally:
        db.close()


def tool_buscar_propositos(termo: str) -> list[dict]:
    """Search fonte propósitos (AI-generated summaries) by keyword.

    Args:
        termo: Search term (e.g., 'aprovação pedido')

    Returns:
        List of {arquivo, proposito, modulo}
    """
    db = _get_db()
    try:
        words = [w for w in termo.lower().split() if len(w) >= 3]
        if not words:
            return []

        conditions = " AND ".join(["LOWER(proposito) LIKE ?"] * len(words))
        params = tuple(f"%{w}%" for w in words)

        rows = db.execute(
            f"SELECT chave, substr(proposito, 1, 300) FROM propositos WHERE {conditions} LIMIT 10",
            params
        ).fetchall()

        results = []
        for r in rows:
            proposito_text = ""
            try:
                p = json.loads(r[1])
                proposito_text = p.get("humano", "")[:200]
            except (json.JSONDecodeError, TypeError):
                proposito_text = (r[1] or "")[:200]

            fonte = db.execute(
                "SELECT modulo FROM fontes WHERE UPPER(arquivo) = ? LIMIT 1",
                (r[0].upper(),)
            ).fetchone()

            results.append({
                "arquivo": r[0],
                "proposito": proposito_text,
                "modulo": fonte[0] if fonte else "",
            })

        return results
    finally:
        db.close()
