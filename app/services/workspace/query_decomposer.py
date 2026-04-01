"""Query Decomposer — 5-step pipeline that bridges business questions to technical evidence.

Pipeline:
  Step 1: ENTENDER   — LLM identifies rotina, tabela, modulo, operacao, conceito
  Step 2: MAPEAR     — Query padrao.db for PEs, functions, standard flow
  Step 3: CRUZAR     — Cross-reference with client fontes/customizations
  Step 4: EVIDENCIAR — Read real code, extract key patterns
  Step 5: (caller)   — Synthesize with LLM (done by analista_pipeline)
"""
import json
import re
import sqlite3
from pathlib import Path
from typing import Optional


# ── Protheus Knowledge Base (static patterns) ──────────────────────────────

ROTINA_MAP = {
    # Financeiro
    "FINA050": {"prefixos": ["FA050", "F050"], "tabela": "SE2", "modulo": "financeiro", "nome": "Contas a Pagar"},
    "FINA040": {"prefixos": ["FA040", "F040"], "tabela": "SE1", "modulo": "financeiro", "nome": "Contas a Receber"},
    "FINA080": {"prefixos": ["FA080", "F080"], "tabela": "SE5", "modulo": "financeiro", "nome": "Baixas a Pagar"},
    "FINA070": {"prefixos": ["FA070", "F070"], "tabela": "SE5", "modulo": "financeiro", "nome": "Baixas a Receber"},
    "FINA750": {"prefixos": ["FA750", "F750"], "tabela": "SE2", "modulo": "financeiro", "nome": "Contas a Pagar (filial)"},
    # Compras
    "MATA120": {"prefixos": ["MT120", "MA120"], "tabela": "SC7", "modulo": "compras", "nome": "Pedido de Compras"},
    "MATA121": {"prefixos": ["MT121", "MA121"], "tabela": "SC7", "modulo": "compras", "nome": "Pedido de Compras (Adiantamento)"},
    "MATA110": {"prefixos": ["MT110", "MA110"], "tabela": "SC1", "modulo": "compras", "nome": "Solicitação de Compras"},
    "MATA103": {"prefixos": ["A103", "MT103", "MA103"], "tabela": "SF1", "modulo": "compras", "nome": "Documento de Entrada"},
    "MATA140": {"prefixos": ["MT140", "MA140"], "tabela": "SC7", "modulo": "compras", "nome": "Cotação de Preços"},
    "MATA094": {"prefixos": ["MT094", "MA094", "MTA094"], "tabela": "SCR", "modulo": "compras", "nome": "Aprovação de Compras"},
    # Faturamento/Vendas
    "MATA410": {"prefixos": ["MT410", "MA410"], "tabela": "SC5", "modulo": "faturamento", "nome": "Pedido de Venda"},
    "MATA460": {"prefixos": ["MT460", "MA460"], "tabela": "SF2", "modulo": "faturamento", "nome": "Nota Fiscal Saída"},
    "MATA010": {"prefixos": ["A010", "MT010", "MA010"], "tabela": "SA1", "modulo": "faturamento", "nome": "Cadastro de Clientes"},
    "MATA030": {"prefixos": ["A030", "MT030", "MA030"], "tabela": "SA1", "modulo": "faturamento", "nome": "Cadastro de Clientes (Alt)"},
    # Estoque
    "MATA250": {"prefixos": ["MT250", "MA250"], "tabela": "SD3", "modulo": "estoque", "nome": "Movimentação Interna"},
    "MATA261": {"prefixos": ["A261", "MT261"], "tabela": "SB1", "modulo": "estoque", "nome": "Cadastro de Produtos"},
    "MATA010P": {"prefixos": ["A010", "MT010"], "tabela": "SB1", "modulo": "estoque", "nome": "Cadastro de Produtos"},
    # Fiscal
    "MATA950": {"prefixos": ["MT950", "MA950"], "tabela": "SF3", "modulo": "fiscal", "nome": "Livros Fiscais"},
    # Contabilidade
    "CTBA102": {"prefixos": ["CT102", "CTB102"], "tabela": "CT2", "modulo": "contabilidade", "nome": "Lançamento Contábil"},
    # Ativo Fixo
    "ATFA010": {"prefixos": ["AF010", "ATF010"], "tabela": "SN1", "modulo": "ativo", "nome": "Cadastro Ativo Fixo"},
    "ATFA012": {"prefixos": ["AF012", "ATF012"], "tabela": "SN1", "modulo": "ativo", "nome": "Classificação Ativo Imobilizado"},
    "ATFA240": {"prefixos": ["AF240", "ATF240"], "tabela": "SN1", "modulo": "ativo", "nome": "Classificação Ativo (Individual/Lote)"},
    "ATFA040": {"prefixos": ["AF040", "ATF040"], "tabela": "SE2", "modulo": "ativo", "nome": "Baixas de Adiantamento"},
}

OPERACAO_KEYWORDS = {
    "inclusão": ["incluir", "inclusão", "incluindo", "criar", "gerar", "novo", "cadastrar", "inserir"],
    "exclusão": ["excluir", "exclusão", "deletar", "remover", "apagar", "cancelar"],
    "alteração": ["alterar", "alteração", "modificar", "mudar", "editar", "atualizar"],
    "validação": ["validar", "validação", "bloquear", "bloqueio", "impedir", "travar", "obrigar", "obrigatório"],
    "aprovação": ["aprovar", "aprovação", "alçada", "liberar", "liberação", "rejeitar"],
    "baixa": ["baixar", "baixa", "pagar", "pagamento", "quitar", "liquidar"],
    "estorno": ["estornar", "estorno", "reverter", "desfazer", "cancelar baixa"],
}

CONCEITO_MAP = {
    "adiantamento": {"e2_tipo": "PA", "rotinas": ["FINA050", "MATA121", "ATFA040"], "tabelas": ["SE2", "SC7", "FIE"]},
    "nota fiscal entrada": {"rotinas": ["MATA103"], "tabelas": ["SF1", "SD1"]},
    "nota fiscal saída": {"rotinas": ["MATA460"], "tabelas": ["SF2", "SD2"]},
    "pedido de compras": {"rotinas": ["MATA120", "MATA121"], "tabelas": ["SC7"]},
    "pedido de venda": {"rotinas": ["MATA410"], "tabelas": ["SC5", "SC6"]},
    "solicitação de compras": {"rotinas": ["MATA110"], "tabelas": ["SC1"]},
    "aprovação alçada": {"rotinas": ["MATA094"], "tabelas": ["SCR", "Z12", "DBM"]},
    "borderô": {"rotinas": ["FINA240"], "tabelas": ["SEA"]},
    "cadastro produto": {"rotinas": ["MATA010", "MATA261"], "tabelas": ["SB1"]},
    "cadastro cliente": {"rotinas": ["MATA030"], "tabelas": ["SA1"]},
    "cadastro fornecedor": {"rotinas": ["MATA020"], "tabelas": ["SA2"]},
    "ativo imobilizado": {"rotinas": ["ATFA010", "ATFA010A", "ATFA012"], "tabelas": ["SN1", "SN3"]},
    "ativo fixo": {"rotinas": ["ATFA010", "ATFA010A", "ATFA012"], "tabelas": ["SN1", "SN3"]},
    "classificação ativo": {"rotinas": ["ATFA240"], "tabelas": ["SN1", "SN3", "SNN"]},
    "depreciação": {"rotinas": ["ATFA050", "ATFA060"], "tabelas": ["SN1", "SN3"]},
    "baixa ativo": {"rotinas": ["ATFA030", "ATFA036"], "tabelas": ["SN1", "SN3"]},
    "transferência ativo": {"rotinas": ["ATFA020"], "tabelas": ["SN1", "SN4"]},
    "contas pagar": {"rotinas": ["FINA050"], "tabelas": ["SE2"]},
    "contas receber": {"rotinas": ["FINA040"], "tabelas": ["SE1"]},
    "contabilização": {"rotinas": ["CTBA102"], "tabelas": ["CT2"]},
    "livro fiscal": {"rotinas": ["MATA950"], "tabelas": ["SF3"]},
    "ordem produção": {"rotinas": ["MATA650"], "tabelas": ["SC2"]},
    "cotação": {"rotinas": ["MATA140"], "tabelas": ["SC8"]},
}


def _get_padrao_db() -> Optional[sqlite3.Connection]:
    """Get padrao.db connection."""
    padrao_path = Path("workspace/padrao/db/padrao.db")
    if not padrao_path.exists():
        return None
    return sqlite3.connect(str(padrao_path))


def _get_client_db() -> Optional[sqlite3.Connection]:
    """Get client extrairpo.db connection."""
    from app.services.workspace.config import load_config, get_client_workspace
    config = load_config(Path("config.json"))
    if not config or not config.active_client:
        return None
    client_dir = get_client_workspace(Path("workspace"), config.active_client)
    db_path = client_dir / "db" / "extrairpo.db"
    if not db_path.exists():
        return None
    return sqlite3.connect(str(db_path))


# ── Step 1: ENTENDER ────────────────────────────────────────────────────────

def _check_learned_concepts(words: list, client_db) -> dict:
    """Check if any word matches a previously learned concept.

    Returns: {found: bool, rotinas, tabelas, modulos, conceitos}
    """
    result = {"found": False, "rotinas": [], "tabelas": [], "modulos": [], "conceitos": []}
    try:
        # Ensure table exists
        client_db.execute("""
            CREATE TABLE IF NOT EXISTS conceitos_aprendidos (
                conceito TEXT PRIMARY KEY, rotinas TEXT DEFAULT '[]',
                tabelas TEXT DEFAULT '[]', modulos TEXT DEFAULT '[]',
                fonte TEXT DEFAULT 'auto', hits INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            )""")

        for word in words:
            if len(word) < 4:
                continue
            rows = client_db.execute(
                "SELECT conceito, rotinas, tabelas, modulos FROM conceitos_aprendidos WHERE LOWER(conceito) LIKE ?",
                (f"%{word}%",)
            ).fetchall()
            for r in rows:
                result["found"] = True
                result["conceitos"].append(r[0])
                try:
                    result["rotinas"].extend(json.loads(r[1]))
                    result["tabelas"].extend(json.loads(r[2]))
                    result["modulos"].extend(json.loads(r[3]))
                except (json.JSONDecodeError, TypeError):
                    pass
                # Increment hit counter
                client_db.execute(
                    "UPDATE conceitos_aprendidos SET hits = hits + 1, updated_at = datetime('now') WHERE conceito = ?",
                    (r[0],)
                )
            if result["found"]:
                client_db.commit()
    except Exception as e:
        print(f"[step1] learned concepts check error: {e}")
    return result


def _save_learned_concept(conceito: str, rotinas: list, tabelas: list, modulos: list, client_db):
    """Save a newly discovered concept for future instant lookup."""
    try:
        client_db.execute("""
            CREATE TABLE IF NOT EXISTS conceitos_aprendidos (
                conceito TEXT PRIMARY KEY, rotinas TEXT DEFAULT '[]',
                tabelas TEXT DEFAULT '[]', modulos TEXT DEFAULT '[]',
                fonte TEXT DEFAULT 'auto', hits INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            )""")
        client_db.execute(
            "INSERT OR REPLACE INTO conceitos_aprendidos (conceito, rotinas, tabelas, modulos) VALUES (?, ?, ?, ?)",
            (conceito, json.dumps(rotinas[:10]), json.dumps(tabelas[:10]), json.dumps(modulos[:5]))
        )
        client_db.commit()
    except Exception as e:
        print(f"[step1] save learned concept error: {e}")


def _dynamic_search_menus(words: list, client_db) -> list[dict]:
    """Search client menus by keywords, ranked by relevance.

    Filters out common verbs/stopwords and prioritizes multi-word matches.
    """
    _STOPWORDS = {"preciso", "fazer", "quando", "sempre", "estiver", "gerado",
                  "como", "devo", "posso", "quero", "tenho", "seria", "podemos",
                  "envio", "enviar", "email", "tela", "rotina", "campo", "sistema",
                  "módulo", "processo", "regra", "forma", "tipo", "dados"}

    # Filter to business-relevant words
    biz_words = [w for w in words if w not in _STOPWORDS and len(w) >= 4]
    if not biz_words:
        biz_words = [w for w in words if len(w) >= 4][:3]

    results = []
    seen = set()
    scored = {}

    # Try multi-word combos first (more specific)
    for i, w1 in enumerate(biz_words[:5]):
        for w2 in biz_words[i+1:5]:
            rows = client_db.execute(
                "SELECT rotina, nome, modulo FROM menus WHERE LOWER(nome) LIKE ? AND LOWER(nome) LIKE ? LIMIT 5",
                (f"%{w1}%", f"%{w2}%")
            ).fetchall()
            for r in rows:
                if r[0] not in scored:
                    scored[r[0]] = {"rotina": r[0], "nome": r[1], "modulo": r[2], "score": 2}

    # Then single word
    for word in biz_words[:4]:
        rows = client_db.execute(
            "SELECT rotina, nome, modulo FROM menus WHERE LOWER(nome) LIKE ? LIMIT 8",
            (f"%{word}%",)
        ).fetchall()
        for r in rows:
            if r[0] not in scored:
                scored[r[0]] = {"rotina": r[0], "nome": r[1], "modulo": r[2], "score": 1}

    results = sorted(scored.values(), key=lambda x: -x["score"])
    return results[:10]


def _dynamic_search_padrao_fontes(words: list, padrao_db) -> list[dict]:
    """Search padrao.db fontes by arquivo name matching keywords."""
    results = []
    seen = set()
    for word in words:
        if len(word) < 4:
            continue
        rows = padrao_db.execute(
            "SELECT arquivo, modulo, write_tables FROM fontes WHERE LOWER(arquivo) LIKE ? AND modulo IS NOT NULL LIMIT 5",
            (f"%{word}%",)
        ).fetchall()
        for r in rows:
            if r[0] not in seen:
                seen.add(r[0])
                results.append({"arquivo": r[0], "modulo": r[1], "write_tables": r[2]})
    return results


def step1_entender(message: str, llm=None) -> dict:
    """Identify rotina, tabela, modulo, operacao from the question.

    Hybrid approach:
    1. Static patterns (ROTINA_MAP, CONCEITO_MAP) for known concepts
    2. Dynamic search in menus + padrao.db for unknown concepts
    Returns: {rotinas, tabelas, modulos, operacoes, conceitos}
    """
    msg_lower = message.lower()
    msg_words = [w for w in msg_lower.split() if len(w) > 3]
    result = {
        "rotinas": [],
        "tabelas": [],
        "modulos": [],
        "operacoes": [],
        "conceitos": [],
    }

    # ── 1. Detect operations (static — these are universal) ──
    for op, keywords in OPERACAO_KEYWORDS.items():
        if any(kw in msg_lower for kw in keywords):
            result["operacoes"].append(op)

    # "bloquear/bloqueio" means protect from ALL operations
    if "bloq" in msg_lower or "impedir" in msg_lower or "travar" in msg_lower:
        for op in ["inclusão", "exclusão", "alteração", "validação"]:
            if op not in result["operacoes"]:
                result["operacoes"].append(op)

    # ── 2. Detect explicit table/rotina codes in the message ──
    table_matches = re.findall(r'\b([A-Z][A-Z0-9]{2})\b', message)
    for t in table_matches:
        if re.match(r'^[A-Z][A-Z0-9][0-9A-Z]$', t) and t not in ("COM", "NAO", "SIM", "NOS", "VOU", "DAI"):
            if t not in result["tabelas"]:
                result["tabelas"].append(t)

    rotina_matches = re.findall(r'\b((?:MATA|FINA|CTBA|ATFA|CNTA|TMKA|MNTA|SIGAFAT|SIGACOM|SIGAFIN|SIGAEST)\w*)\b', message, re.IGNORECASE)
    for r in rotina_matches:
        if r.upper() not in result["rotinas"]:
            result["rotinas"].append(r.upper())

    # ── 3. Static CONCEITO_MAP (for known business concepts) ──
    for conceito, info in CONCEITO_MAP.items():
        words = conceito.split()
        if sum(1 for w in words if w in msg_lower) >= len(words) * 0.6:
            result["conceitos"].append(conceito)
            result["rotinas"].extend(info.get("rotinas", []))
            result["tabelas"].extend(info.get("tabelas", []))

    # ── 4. Static ROTINA_MAP (for known rotina names) ──
    for rotina, info in ROTINA_MAP.items():
        if rotina.lower() in msg_lower or info["nome"].lower() in msg_lower:
            result["rotinas"].append(rotina)
            result["tabelas"].append(info["tabela"])
            result["modulos"].append(info["modulo"])

    # Infer rotinas from tabelas via ROTINA_MAP
    for rotina, info in ROTINA_MAP.items():
        if info["tabela"] in result["tabelas"] and rotina not in result["rotinas"]:
            result["rotinas"].append(rotina)
            if info["modulo"] not in result["modulos"]:
                result["modulos"].append(info["modulo"])

    # ── 5. CHECK LEARNED CONCEPTS (instant cache from previous searches) ──
    _learned_from_cache = False
    if len(result["rotinas"]) < 2:
        try:
            client_db = _get_client_db()
            if client_db:
                learned = _check_learned_concepts(msg_words, client_db)
                if learned["found"]:
                    result["rotinas"].extend(learned["rotinas"])
                    result["tabelas"].extend(learned["tabelas"])
                    result["modulos"].extend(learned["modulos"])
                    result["conceitos"].extend(learned["conceitos"])
                    _learned_from_cache = True
                client_db.close()
        except Exception:
            pass

    # ── 6. DYNAMIC SEARCH — if static + cache didn't find enough ──
    if len(result["rotinas"]) < 2 and not _learned_from_cache:
        # Search client menus by keywords
        try:
            client_db = _get_client_db()
            if client_db:
                menu_results = _dynamic_search_menus(msg_words, client_db)
                for m in menu_results[:8]:
                    if m["rotina"] not in result["rotinas"]:
                        result["rotinas"].append(m["rotina"])
                    if m["modulo"] and m["modulo"] not in result["modulos"]:
                        result["modulos"].append(m["modulo"])
                    # Extract concept from menu name
                    if m["nome"] and m["nome"] not in result["conceitos"]:
                        result["conceitos"].append(m["nome"])
                client_db.close()
        except Exception as e:
            print(f"[step1] dynamic menu search error: {e}")

        # Search padrao.db fontes by keywords
        try:
            padrao_db = _get_padrao_db()
            if padrao_db:
                padrao_results = _dynamic_search_padrao_fontes(msg_words, padrao_db)
                for p in padrao_results[:5]:
                    arq = p["arquivo"]
                    # Extract rotina from arquivo name (e.g., CNTA120.PRW → CNTA120)
                    rotina = arq.split(".")[0].upper()
                    if rotina not in result["rotinas"]:
                        result["rotinas"].append(rotina)
                    if p["modulo"] and p["modulo"] not in result["modulos"]:
                        result["modulos"].append(p["modulo"])
                    # Extract tables from write_tables
                    try:
                        wt = json.loads(p["write_tables"]) if p["write_tables"] else []
                        for t in wt:
                            if t not in result["tabelas"]:
                                result["tabelas"].append(t)
                    except (json.JSONDecodeError, TypeError):
                        pass
                padrao_db.close()
        except Exception as e:
            print(f"[step1] dynamic padrao search error: {e}")

    # ── Deduplicate ──
    result["rotinas"] = list(dict.fromkeys(result["rotinas"]))
    result["tabelas"] = list(dict.fromkeys(result["tabelas"]))
    result["modulos"] = list(dict.fromkeys(result["modulos"]))
    result["operacoes"] = list(dict.fromkeys(result["operacoes"]))
    result["conceitos"] = list(dict.fromkeys(result["conceitos"]))

    # ── 7. SAVE LEARNED CONCEPT — if dynamic search found something new ──
    if not _learned_from_cache and result["rotinas"] and result["conceitos"]:
        try:
            client_db = _get_client_db()
            if client_db:
                # Find which words from the message match the concepts found
                for word in msg_words:
                    if len(word) < 4:
                        continue
                    if any(word in c.lower() for c in result["conceitos"]):
                        _save_learned_concept(
                            word,
                            result["rotinas"][:8],
                            result["tabelas"][:8],
                            result["modulos"][:5],
                            client_db
                        )
                client_db.close()
        except Exception as e:
            print(f"[step1] save learned concept error: {e}")

    return result


# ── Step 2: MAPEAR NO PADRÃO ───────────────────────────────────────────────

def step2_mapear_padrao(entendimento: dict) -> dict:
    """Query padrao.db for PEs, functions, standard flow.

    Returns: {pes_padrao, funcoes_padrao, fluxo_padrao}
    """
    result = {
        "pes_padrao": [],
        "funcoes_padrao": [],
        "pes_por_operacao": {},
    }

    padrao_db = _get_padrao_db()
    if not padrao_db:
        return result

    try:
        # 2a. Search PEs by rotina prefixes
        for rotina in entendimento["rotinas"][:4]:
            info = ROTINA_MAP.get(rotina, {})
            prefixos = info.get("prefixos", [])

            for prefixo in prefixos:
                # Search execblocks for this prefix
                rows = padrao_db.execute(
                    "SELECT DISTINCT nome_pe, operacao, parametros, tipo_retorno_inferido, funcao, arquivo, contexto, comentario "
                    "FROM execblocks WHERE arquivo LIKE ? OR funcao LIKE ? "
                    "ORDER BY operacao, nome_pe LIMIT 50",
                    (f"%{prefixo}%", f"%{prefixo}%")
                ).fetchall()

                for r in rows:
                    pe = {
                        "nome_pe": r[0],
                        "operacao": r[1] or "",
                        "parametros": r[2] or "",
                        "tipo_retorno": r[3] or "",
                        "funcao": r[4] or "",
                        "arquivo": r[5] or "",
                        "contexto": (r[6] or "")[:300],
                        "comentario": r[7] or "",
                    }
                    if not any(p["nome_pe"] == pe["nome_pe"] for p in result["pes_padrao"]):
                        result["pes_padrao"].append(pe)

            # Also search by rotina name directly
            rows2 = padrao_db.execute(
                "SELECT DISTINCT nome_pe, operacao, parametros, tipo_retorno_inferido, funcao, arquivo "
                "FROM execblocks WHERE UPPER(arquivo) LIKE ? LIMIT 30",
                (f"%{rotina}%",)
            ).fetchall()
            for r in rows2:
                pe = {
                    "nome_pe": r[0], "operacao": r[1] or "", "parametros": r[2] or "",
                    "tipo_retorno": r[3] or "", "funcao": r[4] or "", "arquivo": r[5] or "",
                    "contexto": "", "comentario": "",
                }
                if not any(p["nome_pe"] == pe["nome_pe"] for p in result["pes_padrao"]):
                    result["pes_padrao"].append(pe)

        # 2b. Group PEs by operation for easy lookup
        for pe in result["pes_padrao"]:
            op = pe["operacao"] or "outro"
            if op not in result["pes_por_operacao"]:
                result["pes_por_operacao"][op] = []
            result["pes_por_operacao"][op].append(pe)

        # 2c. Get standard functions for the main rotinas
        for rotina in entendimento["rotinas"][:4]:
            rows = padrao_db.execute(
                "SELECT nome, tipo, assinatura, arquivo, resumo_auto FROM funcoes WHERE UPPER(arquivo) LIKE ? LIMIT 50",
                (f"%{rotina}%",)
            ).fetchall()
            for r in rows:
                result["funcoes_padrao"].append({
                    "nome": r[0], "tipo": r[1], "assinatura": r[2], "arquivo": r[3],
                    "resumo_auto": r[4] or "",
                })

        # 2d. Search padrao by resumo_auto for concepts related to the question
        conceitos = entendimento.get("conceitos", [])
        tabelas = entendimento.get("tabelas", [])
        if conceitos or tabelas:
            search_words = []
            for c in conceitos:
                search_words.extend(c.split())
            for t in tabelas[:3]:
                search_words.append(t)
            # Try 2-word combos
            result["funcoes_padrao_relevantes"] = []
            for i, w1 in enumerate(search_words[:6]):
                for w2 in search_words[i+1:6]:
                    try:
                        rows = padrao_db.execute(
                            "SELECT nome, tipo, assinatura, arquivo, resumo_auto FROM funcoes "
                            "WHERE LOWER(resumo_auto) LIKE ? AND LOWER(resumo_auto) LIKE ? "
                            "AND resumo_auto != '' LIMIT 5",
                            (f"%{w1.lower()}%", f"%{w2.lower()}%")
                        ).fetchall()
                        for r in rows:
                            if not any(f["nome"] == r[0] and f["arquivo"] == r[3]
                                       for f in result["funcoes_padrao_relevantes"]):
                                result["funcoes_padrao_relevantes"].append({
                                    "nome": r[0], "tipo": r[1], "assinatura": r[2],
                                    "arquivo": r[3], "resumo_auto": r[4] or "",
                                })
                    except Exception:
                        pass

    except Exception as e:
        print(f"[decomposer] step2 error: {e}")
    finally:
        padrao_db.close()

    return result


# ── Step 3: CRUZAR COM CLIENTE ──────────────────────────────────────────────

def step3_cruzar_cliente(entendimento: dict, mapa_padrao: dict) -> dict:
    """Cross-reference padrao PEs with client fontes/customizations.

    Returns: {pes_implementados, fontes_relacionados, fontes_por_resumo}
    """
    result = {
        "pes_implementados": [],     # PE padrão que o cliente tem fonte pra
        "fontes_relacionados": [],   # Fontes do cliente com prefixo da rotina
        "fontes_por_resumo": [],     # Fontes encontrados por resumo_auto
    }

    client_db = _get_client_db()
    if not client_db:
        return result

    try:
        # 3a. Check each padrao PE: does client have it implemented?
        for pe in mapa_padrao["pes_padrao"]:
            pe_name = pe["nome_pe"]
            # Search client fontes for this PE name
            row = client_db.execute(
                "SELECT arquivo, modulo, pontos_entrada, funcoes FROM fontes "
                "WHERE pontos_entrada LIKE ? OR LOWER(arquivo) LIKE ? LIMIT 1",
                (f'%"{pe_name}"%', f"%{pe_name.lower()}%")
            ).fetchone()
            if row:
                result["pes_implementados"].append({
                    "pe_padrao": pe_name,
                    "operacao_padrao": pe["operacao"],
                    "parametros_padrao": pe["parametros"],
                    "arquivo_cliente": row[0],
                    "modulo_cliente": row[1],
                })

        # 3b. Find client fontes with rotina prefixes
        seen_arquivos = set()
        for rotina in entendimento["rotinas"][:4]:
            info = ROTINA_MAP.get(rotina, {})
            for prefixo in info.get("prefixos", []):
                rows = client_db.execute(
                    "SELECT arquivo, modulo, pontos_entrada, write_tables, tabelas_ref FROM fontes "
                    "WHERE LOWER(arquivo) LIKE ? LIMIT 10",
                    (f"%{prefixo.lower()}%",)
                ).fetchall()
                for r in rows:
                    if r[0] not in seen_arquivos:
                        seen_arquivos.add(r[0])
                        result["fontes_relacionados"].append({
                            "arquivo": r[0],
                            "modulo": r[1],
                            "pes": json.loads(r[2]) if r[2] else [],
                            "write_tables": json.loads(r[3]) if r[3] else [],
                            "tabelas_ref": json.loads(r[4]) if r[4] else [],
                            "rotina_padrao": rotina,
                        })

        # 3c. Search by resumo_auto for concepts
        _SYNONYMS = {
            "bloquear": ["bloq", "bloqueia", "return .f"],
            "adiantamento": ["adiant", "e2_tipo", "PA", "titulo"],
            "fornecedor": ["fornec", "sa2", "se2", "pagar"],
            "financeiro": ["fina050", "fina", "se2", "pagar", "titulo"],
            "compras": ["compra", "mata121", "mata120", "sc7", "pedido"],
            "excluir": ["exclu", "delet", "exclus"],
            "exclusão": ["exclu", "delet", "exclus"],
            "incluir": ["inclu", "inclusão"],
            "alterar": ["alter", "alteração"],
            "aprovar": ["aprov", "aprovação", "alcada"],
            "pedido": ["pedido", "sc7", "mata121", "mata120", "compra"],
            "título": ["titulo", "se1", "se2", "pagar", "receber"],
            "estoque": ["estoq", "sb1", "sb2", "saldo"],
            "produto": ["produto", "sb1", "b1_cod"],
            "nota": ["nota", "sf1", "sd1", "entrada", "fiscal"],
        }

        # Expand search terms
        operacoes = entendimento.get("operacoes", [])
        conceitos = entendimento.get("conceitos", [])
        all_words = []
        for op in operacoes:
            all_words.extend(OPERACAO_KEYWORDS.get(op, []))
        for c in conceitos:
            all_words.extend(c.split())

        expanded = set(all_words)
        for w in all_words:
            for key, syns in _SYNONYMS.items():
                if w.startswith(key[:4]) or key.startswith(w[:4]):
                    expanded.update(syns)

        search_terms = list(expanded)

        # Score-based search
        if search_terms:
            scored = {}
            combos_tried = set()
            for w1 in search_terms:
                for w2 in search_terms:
                    if w1 == w2:
                        continue
                    ck = tuple(sorted([w1, w2]))
                    if ck in combos_tried:
                        continue
                    combos_tried.add(ck)
                    try:
                        rows = client_db.execute(
                            "SELECT arquivo, funcao, resumo_auto, resumo FROM funcao_docs "
                            "WHERE LOWER(resumo_auto) LIKE ? AND LOWER(resumo_auto) LIKE ? LIMIT 5",
                            (f"%{w1}%", f"%{w2}%")
                        ).fetchall()
                        for rr in rows:
                            key = f"{rr[0]}::{rr[1]}"
                            ra_lower = (rr[2] or "").lower()
                            score = sum(1 for t in search_terms if t.lower() in ra_lower)
                            if key not in scored or score > scored[key]["score"]:
                                scored[key] = {
                                    "arquivo": rr[0], "funcao": rr[1],
                                    "resumo_auto": rr[2], "resumo": rr[3],
                                    "score": score,
                                }
                    except Exception:
                        pass

            top = sorted(scored.values(), key=lambda x: -x["score"])[:10]
            result["fontes_por_resumo"] = top

    except Exception as e:
        print(f"[decomposer] step3 error: {e}")
    finally:
        client_db.close()

    return result


# ── Code Analysis Helpers ───────────────────────────────────────────────────

# Keywords to extract from code based on what the question is about
_CODE_KEYWORDS_DEFAULT = ["return .f", "lret := .f", "_lret := .f",
                          "funname()", "bloq", "exclu",
                          "supergetmv", "getmv", "mv_par"]

_CODE_KEYWORDS_DATE = ["ddatabase", "ddata", "n1_aquisic", "n3_aquisic",
                       "dtclass", "headprova", "detprova", "rodaprova",
                       "mv_par", "aquisic", "contab"]

_CODE_KEYWORDS_CONTAB = ["headprova", "detprova", "rodaprova", "ca100incl",
                          "lotecon", "lancpad", "contab", "801", "clote",
                          "ddatabase"]


def _extract_evidence_from_code(code: str, extra_keywords: list = None) -> dict:
    """Extract key patterns from source code."""
    keywords = list(_CODE_KEYWORDS_DEFAULT)
    if extra_keywords:
        keywords.extend(extra_keywords)

    codigo_chave = []
    mensagens = []
    parametros = []
    bloqueia = False

    for line in code.split("\n"):
        ls = line.strip()
        ll = ls.lower()

        # Extract Help/Alert messages
        for pattern in [r'Help\s*\([^,]*,[^,]*,[^,]*,[^,]*,\s*["\']([^"\']{10,})["\']',
                        r'FWAlert\w+\s*\(\s*["\']([^"\']{10,})["\']',
                        r'Msg(?:Alert|Stop|Info)\s*\(\s*["\']([^"\']{10,})["\']']:
            for m in re.finditer(pattern, ls):
                mensagens.append(m.group(1)[:150])

        # Extract parameters
        for m in re.finditer(r'(?:SuperGetM[Vv]|GetNewPar|GetMv)\s*\(\s*["\']([^"\']+)["\']', ls):
            if m.group(1) not in parametros:
                parametros.append(m.group(1))

        # Key code lines
        if any(k in ll for k in keywords):
            if len(ls) > 10:
                codigo_chave.append(ls[:180])
                if "return .f" in ll or "lret := .f" in ll or "_lret := .f" in ll:
                    bloqueia = True

    return {
        "codigo_chave": codigo_chave[:10],
        "mensagens": mensagens[:5],
        "parametros": parametros[:5],
        "bloqueia": bloqueia,
    }


def _get_context_keywords(entendimento: dict) -> list:
    """Get extra keywords based on what the question is about."""
    extra = []
    conceitos = entendimento.get("conceitos", [])
    msg_words = entendimento.get("_msg_words", [])

    # Date-related questions
    if any(w in msg_words for w in ["data", "datas", "database", "aquisição", "contabilização"]):
        extra.extend(_CODE_KEYWORDS_DATE)

    # Contabilization questions
    if any(w in msg_words for w in ["contabil", "contabilização", "lançamento", "lancamento", "lote"]):
        extra.extend(_CODE_KEYWORDS_CONTAB)

    return extra


# ── Step 4: EVIDENCIAR ──────────────────────────────────────────────────────

def step4_evidenciar(cruzamento: dict, mapa_padrao: dict = None, entendimento: dict = None) -> list[dict]:
    """Read real code from BOTH client AND padrao databases.

    Returns list of evidence dicts: {arquivo, funcao, resumo, codigo_chave, mensagens, parametros, bloqueia, fonte}
    """
    evidencias = []
    seen = set()
    extra_keywords = _get_context_keywords(entendimento or {})

    client_db = _get_client_db()
    padrao_db = _get_padrao_db()

    try:
        # Collect client arquivos to read
        arquivos_funcoes_cliente = []

        if client_db:
            # From PEs implemented
            for pe in cruzamento.get("pes_implementados", []):
                arq = pe["arquivo_cliente"]
                row = client_db.execute(
                    "SELECT funcao FROM funcao_docs WHERE arquivo = ? AND (funcao = ? OR funcao LIKE ?) LIMIT 1",
                    (arq, pe["pe_padrao"], f"%{pe['pe_padrao']}%")
                ).fetchone()
                if row:
                    arquivos_funcoes_cliente.append((arq, row[0]))

            # From fontes_relacionados (get main PE function)
            for fonte in cruzamento.get("fontes_relacionados", []):
                arq = fonte["arquivo"]
                for pe in fonte["pes"]:
                    arquivos_funcoes_cliente.append((arq, pe))

            # From fontes_por_resumo
            for item in cruzamento.get("fontes_por_resumo", []):
                arquivos_funcoes_cliente.append((item["arquivo"], item["funcao"]))

        # Read code evidence from CLIENT
        for arq, func in arquivos_funcoes_cliente:
            key = f"cliente::{arq}::{func}"
            if key in seen:
                continue
            seen.add(key)

            resumo_row = client_db.execute(
                "SELECT resumo, resumo_auto FROM funcao_docs WHERE arquivo = ? AND funcao = ?",
                (arq, func)
            ).fetchone()
            resumo = ""
            if resumo_row:
                resumo = resumo_row[0] if resumo_row[0] else (resumo_row[1] or "")

            chunk = client_db.execute(
                "SELECT content FROM fonte_chunks WHERE arquivo = ? AND funcao = ?",
                (arq, func)
            ).fetchone()

            ev = {"codigo_chave": [], "mensagens": [], "parametros": [], "bloqueia": False}
            if chunk and chunk[0]:
                ev = _extract_evidence_from_code(chunk[0], extra_keywords)

            evidencias.append({
                "arquivo": arq, "funcao": func, "resumo": resumo[:300],
                "fonte": "cliente", **ev,
            })

        # Read code evidence from PADRAO — key functions of identified routines
        if padrao_db and mapa_padrao:
            # Get main functions + relevant functions from padrao
            padrao_funcs_to_read = []

            # Functions from step2 funcoes_padrao_relevantes
            for f in mapa_padrao.get("funcoes_padrao_relevantes", []):
                padrao_funcs_to_read.append((f["arquivo"], f["nome"]))

            # Key functions from main rotinas (the ones that DO things)
            for f in mapa_padrao.get("funcoes_padrao", []):
                nome_lower = f["nome"].lower()
                # Prioritize: Grv (write), Lote (batch), Class (classification), Data, Cont (accounting)
                if any(k in nome_lower for k in ["grv", "lote", "class", "data", "cont", "inclu", "delet"]):
                    padrao_funcs_to_read.append((f["arquivo"], f["nome"]))

            # Deduplicate
            padrao_seen = set()
            padrao_unique = []
            for arq, func in padrao_funcs_to_read:
                key = f"{arq}::{func}"
                if key not in padrao_seen:
                    padrao_seen.add(key)
                    padrao_unique.append((arq, func))
            for arq, func in padrao_unique[:20]:
                key = f"padrao::{arq}::{func}"
                if key in seen:
                    continue
                seen.add(key)

                # Get resumo from padrao funcoes
                resumo_row = padrao_db.execute(
                    "SELECT resumo_auto FROM funcoes WHERE arquivo = ? AND nome = ?",
                    (arq, func)
                ).fetchone()
                resumo = resumo_row[0] if resumo_row and resumo_row[0] else ""

                # Get code chunk from padrao
                chunk = padrao_db.execute(
                    "SELECT content FROM fonte_chunks WHERE arquivo = ? AND funcao = ?",
                    (arq, func)
                ).fetchone()

                ev = {"codigo_chave": [], "mensagens": [], "parametros": [], "bloqueia": False}
                if chunk and chunk[0]:
                    ev = _extract_evidence_from_code(chunk[0], extra_keywords)

                if ev["codigo_chave"] or ev["mensagens"] or ev["parametros"]:
                    evidencias.append({
                        "arquivo": arq, "funcao": func, "resumo": resumo[:300],
                        "fonte": "padrão", **ev,
                    })

    except Exception as e:
        print(f"[decomposer] step4 error: {e}")
        import traceback; traceback.print_exc()
    finally:
        if client_db:
            client_db.close()
        if padrao_db:
            padrao_db.close()

    return evidencias


# ── Full Pipeline ───────────────────────────────────────────────────────────

# ── Step 3b: ANÁLISE DE CAMPO (table ecosystem) ────────────────────────────

def step3b_analise_campo(message: str, entendimento: dict) -> str:
    """When the question mentions a specific field, analyze the table ecosystem.

    For MANDATORY field changes: traces parent-child relationships to find all
    routines that write to the table (directly or via parent MVC).

    For RESIZE changes: the existing SXG analysis handles it (no changes here).

    Returns formatted context string or empty if not applicable.
    """
    msg_upper = message.upper()

    # Detect field codes in message (e.g., CNB_XTPSC, B1_COD)
    field_matches = re.findall(r'\b([A-Z][A-Z0-9]{1,2}_\w{2,})\b', msg_upper)
    if not field_matches:
        return ""

    # Detect if this is about making mandatory (vs resize which is handled by SXG)
    msg_lower = message.lower()
    is_mandatory = any(k in msg_lower for k in ["obrigatório", "obrigatorio", "obrigar", "mandatory"])
    is_resize = any(k in msg_lower for k in ["tamanho", "posição", "posições", "aumentar", "diminuir"])

    # For resize, the existing pipeline (analise_aumento_campo + SXG) handles it
    if is_resize and not is_mandatory:
        return ""

    parts = []
    client_db = _get_client_db()
    padrao_db = _get_padrao_db()
    if not client_db:
        return ""

    try:
        for campo in field_matches[:2]:
            # Extract table from field name
            tabela = campo.split("_")[0]

            # Get table info
            tab_info = client_db.execute(
                "SELECT codigo, nome FROM tabelas WHERE codigo = ?", (tabela,)
            ).fetchone()
            if not tab_info:
                continue

            parts.append(f"\n═══ ANÁLISE DE CAMPO: {campo} (tabela {tabela} — {tab_info[1]}) ═══")

            # 1. Find parent-child relationships (SX9)
            parents = client_db.execute(
                "SELECT tabela_origem, expressao_origem, expressao_destino "
                "FROM relacionamentos WHERE tabela_destino = ? LIMIT 10",
                (tabela,)
            ).fetchall()
            children = client_db.execute(
                "SELECT tabela_destino, expressao_origem, expressao_destino "
                "FROM relacionamentos WHERE tabela_origem = ? LIMIT 10",
                (tabela,)
            ).fetchall()

            if parents:
                parts.append(f"\n  TABELAS PAI (quem alimenta {tabela}):")
                parent_tables = []
                for p in parents:
                    parent_name = client_db.execute(
                        "SELECT nome FROM tabelas WHERE codigo = ?", (p[0],)
                    ).fetchone()
                    nome = parent_name[0] if parent_name else "?"
                    parts.append(f"    {p[0]} ({nome}): {p[1]} = {p[2]}")
                    parent_tables.append(p[0])

                # For each parent, find standard routines that manage it
                if padrao_db:
                    parts.append(f"\n  ROTINAS PADRÃO QUE MANIPULAM TABELAS PAI:")
                    for ptab in parent_tables[:5]:
                        # Find fontes that write to parent
                        fontes = padrao_db.execute(
                            "SELECT arquivo, write_tables FROM fontes WHERE write_tables LIKE ?",
                            (f'%"{ptab}"%',)
                        ).fetchall()
                        for f in fontes[:3]:
                            wt = json.loads(f[1]) if f[1] else []
                            # Check if this routine also handles the child table
                            handles_child = tabela in str(f[1])
                            parts.append(
                                f"    {f[0]} → grava {ptab}"
                                + (f" (TAMBÉM grava {tabela}!)" if handles_child else "")
                            )

                        # Find PEs for parent table routines
                        pes = padrao_db.execute(
                            "SELECT DISTINCT nome_pe, operacao FROM execblocks "
                            "WHERE arquivo IN (SELECT arquivo FROM fontes WHERE write_tables LIKE ?) "
                            "AND operacao IN ('inclusao', 'alteracao') LIMIT 5",
                            (f'%"{ptab}"%',)
                        ).fetchall()
                        if pes:
                            pe_str = ", ".join(f"{p[0]}({p[1]})" for p in pes)
                            parts.append(f"    PEs de {ptab}: {pe_str}")

            if children:
                parts.append(f"\n  TABELAS FILHA (dependem de {tabela}):")
                for c in children[:5]:
                    child_name = client_db.execute(
                        "SELECT nome FROM tabelas WHERE codigo = ?", (c[0],)
                    ).fetchone()
                    nome = child_name[0] if child_name else "?"
                    parts.append(f"    {c[0]} ({nome}): {c[1]} = {c[2]}")

            # 2. Find ALL routines that mention this table in padrao resumo_auto
            if padrao_db:
                parts.append(f"\n  ROTINAS PADRÃO QUE TRABALHAM COM {tabela}:")
                rows = padrao_db.execute(
                    "SELECT DISTINCT arquivo, nome, resumo_auto FROM funcoes "
                    "WHERE LOWER(resumo_auto) LIKE ? AND resumo_auto != '' LIMIT 15",
                    (f"%{tabela.lower()}%",)
                ).fetchall()
                seen_arqs = set()
                for r in rows:
                    if r[0] not in seen_arqs:
                        seen_arqs.add(r[0])
                        parts.append(f"    {r[0]}::{r[1]} — {r[2][:120]}")

            # 3. Find client fontes that work with this table
            parts.append(f"\n  FONTES DO CLIENTE QUE TRABALHAM COM {tabela}:")
            # Direct writes
            client_writes = client_db.execute(
                "SELECT arquivo, funcao, tipo, campos FROM operacoes_escrita WHERE tabela = ?",
                (tabela,)
            ).fetchall()
            if client_writes:
                for cw in client_writes:
                    parts.append(f"    ✏️ {cw[0]}::{cw[1]} → {cw[2]} {tabela}: {cw[3][:80]}")
            else:
                parts.append(f"    Nenhuma operação de escrita direta em {tabela}")

            # Fontes that read the table
            client_reads = client_db.execute(
                "SELECT arquivo, modulo FROM fontes WHERE tabelas_ref LIKE ?",
                (f'%"{tabela}"%',)
            ).fetchall()
            if client_reads:
                parts.append(f"    Fontes que lêem {tabela}: {', '.join(r[0] for r in client_reads[:8])}")

            # Client PEs for parent table routines
            if parents:
                parts.append(f"\n  PEs DO CLIENTE PARA ROTINAS DE CONTRATO:")
                for ptab in parent_tables[:5]:
                    # Find client PEs whose name matches parent table prefixes
                    client_pes = client_db.execute(
                        "SELECT arquivo, pontos_entrada FROM fontes "
                        "WHERE pontos_entrada LIKE ? OR pontos_entrada LIKE ?",
                        (f'%CN1%', f'%CN0%')
                    ).fetchall()
                    # More broadly — find all client PEs for CN* patterns
                client_pes = client_db.execute(
                    "SELECT arquivo, pontos_entrada, modulo FROM fontes "
                    "WHERE pontos_entrada LIKE '%CN%' AND pontos_entrada != '[]'"
                ).fetchall()
                for cp in client_pes:
                    pes = json.loads(cp[1]) if cp[1] else []
                    cn_pes = [p for p in pes if "CN" in p.upper()]
                    if cn_pes:
                        parts.append(f"    {cp[0]}: PEs={cn_pes}")

            # 4. If mandatory — highlight MsExecAuto risk
            if is_mandatory:
                parts.append(f"\n  ⚠️ RISCO CAMPO OBRIGATÓRIO:")
                parts.append(f"    Se rotinas padrão gravam {tabela} via MVC (cabeçalho+itens),")
                parts.append(f"    o campo {campo} precisa estar no modelo ou terá erro de validação.")
                parts.append(f"    Verificar se as rotinas acima passam {campo} no array de itens.")

    except Exception as e:
        print(f"[decomposer] step3b error: {e}")
        import traceback; traceback.print_exc()
    finally:
        if client_db:
            client_db.close()
        if padrao_db:
            padrao_db.close()

    return "\n".join(parts)


def decompose_and_investigate(message: str, llm=None) -> str:
    """Run full 4-step decomposition pipeline.

    Returns formatted context string ready for LLM consumption.
    """
    # Step 1
    entendimento = step1_entender(message, llm)
    entendimento["_msg_words"] = [w.lower() for w in message.split() if len(w) > 3]

    # Step 2
    mapa_padrao = step2_mapear_padrao(entendimento)

    # Step 3
    cruzamento = step3_cruzar_cliente(entendimento, mapa_padrao)

    # Step 3b — Field-specific analysis (table ecosystem for mandatory/new fields)
    campo_context = step3b_analise_campo(message, entendimento)

    # Step 4
    evidencias = step4_evidenciar(cruzamento, mapa_padrao, entendimento)

    # Format output — organized BY OPERATION (how a human thinks)
    parts = []

    # Header
    if entendimento["rotinas"]:
        parts.append(f"ROTINAS IDENTIFICADAS: {', '.join(entendimento['rotinas'][:5])}")
    if entendimento["conceitos"]:
        parts.append(f"CONCEITOS: {', '.join(entendimento['conceitos'])}")

    # Build evidence index by arquivo
    ev_by_arquivo = {}
    for ev in evidencias:
        ev_by_arquivo[ev["arquivo"]] = ev

    # Build PE implementation index and infer operation from suffix if missing
    _SUFFIX_TO_OP = {
        "DEL": "exclusão", "CAN": "exclusão",
        "INC": "inclusão", "UPD": "inclusão", "TOK": "validação",
        "ALT": "alteração", "GRV": "alteração", "FIM": "alteração",
        "BLQ": "validação",
    }
    pe_impl_by_name = {}
    for pe in cruzamento["pes_implementados"]:
        # Infer operation from suffix if padrao didn't have one
        if not pe["operacao_padrao"]:
            for suffix, op in _SUFFIX_TO_OP.items():
                if pe["pe_padrao"].upper().endswith(suffix):
                    pe["operacao_padrao"] = op
                    break
        pe_impl_by_name[pe["pe_padrao"]] = pe

    # Also classify fontes_relacionados PEs
    for fonte in cruzamento["fontes_relacionados"]:
        for pe_name in fonte["pes"]:
            if pe_name not in pe_impl_by_name:
                op = ""
                for suffix, op_name in _SUFFIX_TO_OP.items():
                    if pe_name.upper().endswith(suffix):
                        op = op_name
                        break
                pe_impl_by_name[pe_name] = {
                    "pe_padrao": pe_name,
                    "operacao_padrao": op,
                    "arquivo_cliente": fonte["arquivo"],
                }

    # Main section: ORGANIZED BY OPERATION
    operacoes = entendimento.get("operacoes", ["validação"])
    pe_ops_map = mapa_padrao.get("pes_por_operacao", {})

    parts.append("""
╔══════════════════════════════════════════════════════════════════╗
║  ANÁLISE POR OPERAÇÃO — O QUE O CLIENTE JÁ TEM IMPLEMENTADO   ║
║  Para cada operação, mostra: PE padrão → implementação cliente ║
╚══════════════════════════════════════════════════════════════════╝""")

    shown_pes = set()
    for op in operacoes:
        parts.append(f"\n▶ OPERAÇÃO: {op.upper()}")
        parts.append(f"  {'─' * 50}")

        # PEs padrão pra essa operação (handle accent mismatch)
        op_sem_acento = op.replace("ã", "a").replace("ç", "c")
        pes_padrao = pe_ops_map.get(op, []) or pe_ops_map.get(op_sem_acento, [])
        if pes_padrao:
            parts.append(f"  PEs padrão disponíveis: {', '.join(pe['nome_pe'] for pe in pes_padrao[:8])}")

        # Gather ALL PEs with matching operation (from both padrao and suffix inference)
        found_any = False
        for pe_name, impl in pe_impl_by_name.items():
            impl_op = impl.get("operacao_padrao", "")
            if impl_op == op and pe_name not in shown_pes:
                shown_pes.add(pe_name)
                found_any = True
                arq = impl["arquivo_cliente"]
                parts.append(f"\n  ✅ PE {pe_name} → IMPLEMENTADO em {arq}")
                ev = ev_by_arquivo.get(arq)
                if ev:
                    if ev["resumo"]:
                        parts.append(f"     Resumo: {ev['resumo']}")
                    if ev["bloqueia"]:
                        parts.append(f"     ⛔ BLOQUEIA EXECUÇÃO (Return .F.)")
                    for msg in ev["mensagens"][:3]:
                        parts.append(f"     💬 \"{msg}\"")
                    if ev["parametros"]:
                        parts.append(f"     ⚙️ Parâmetros: {', '.join(ev['parametros'])}")
                    for cl in ev["codigo_chave"][:4]:
                        parts.append(f"     📝 {cl}")

        if not found_any:
            parts.append(f"  ❌ Nenhum PE implementado pelo cliente para {op}")

    # Additional evidence from resumo search (not tied to specific operation)
    extra_evidencias = []
    shown_arquivos = set(ev_by_arquivo.keys())
    for item in cruzamento.get("fontes_por_resumo", []):
        arq = item["arquivo"]
        if arq not in shown_arquivos:
            shown_arquivos.add(arq)
            resumo = item.get("resumo") or item.get("resumo_auto", "")
            if resumo:
                extra_evidencias.append(f"  {arq}::{item['funcao']} — {resumo[:200]}")

    if extra_evidencias:
        parts.append(f"\n▶ FONTES ADICIONAIS RELACIONADOS (por análise de resumo)")
        parts.extend(extra_evidencias[:8])

    # Fontes that write to the main tables
    fontes_escrita = [f for f in cruzamento["fontes_relacionados"]
                      if f["write_tables"] and f["arquivo"] not in shown_arquivos]
    if fontes_escrita:
        parts.append(f"\n▶ FONTES QUE GRAVAM NAS TABELAS DO PROCESSO")
        for f in fontes_escrita[:8]:
            parts.append(f"  {f['arquivo']} → grava: {', '.join(f['write_tables'][:5])}")

    # Standard Protheus functions with resumo (from padrao.db)
    funcoes_rel = mapa_padrao.get("funcoes_padrao_relevantes", [])
    if funcoes_rel:
        parts.append(f"\n▶ FUNÇÕES DO PADRÃO PROTHEUS RELEVANTES (padrao.db)")
        for f in funcoes_rel[:10]:
            resumo = f.get("resumo_auto", "")
            parts.append(f"  {f['arquivo']}::{f['nome']} ({f['tipo']}) — {f['assinatura']}")
            if resumo:
                parts.append(f"     {resumo[:200]}")

    # Standard functions for main rotinas (overview)
    funcoes_padrao = mapa_padrao.get("funcoes_padrao", [])
    if funcoes_padrao:
        funcs_with_resumo = [f for f in funcoes_padrao if f.get("resumo_auto")]
        if funcs_with_resumo:
            parts.append(f"\n▶ FUNÇÕES PRINCIPAIS DA ROTINA PADRÃO")
            for f in funcs_with_resumo[:8]:
                parts.append(f"  {f['arquivo']}::{f['nome']} — {f['resumo_auto'][:150]}")

    # Evidence from PADRAO code (how the standard works)
    padrao_evidencias = [ev for ev in evidencias if ev.get("fonte") == "padrão"]
    if padrao_evidencias:
        parts.append(f"\n▶ CÓDIGO DO PADRÃO PROTHEUS (como o sistema funciona)")
        for ev in padrao_evidencias:
            parts.append(f"\n  📘 {ev['arquivo']}::{ev['funcao']} [PADRÃO]")
            if ev["resumo"]:
                parts.append(f"     Resumo: {ev['resumo']}")
            if ev["parametros"]:
                parts.append(f"     ⚙️ Parâmetros: {', '.join(ev['parametros'])}")
            if ev["codigo_chave"]:
                parts.append(f"     Código-chave:")
                for cl in ev["codigo_chave"]:
                    parts.append(f"        {cl}")

    # Add field ecosystem analysis if available
    if campo_context:
        parts.append(campo_context)

    return "\n".join(parts)
