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
    """Get padrao.db connection (fontes padrao Protheus)."""
    from app.services.workspace.workspace_populator import _get_fontes_padrao_db_path
    padrao_path = _get_fontes_padrao_db_path()
    if not padrao_path.exists():
        return None
    return sqlite3.connect(str(padrao_path))


_client_db_path_cache: Optional[str] = None

def _get_client_db() -> Optional[sqlite3.Connection]:
    """Get client extrairpo.db connection."""
    global _client_db_path_cache
    if _client_db_path_cache:
        p = Path(_client_db_path_cache)
        if p.exists():
            return sqlite3.connect(str(p))
        _client_db_path_cache = None
    from app.services.workspace.config import load_config, get_client_workspace
    config = load_config(Path("config.json"))
    if not config or not config.active_client:
        return None
    client_dir = get_client_workspace(Path("workspace"), config.active_client)
    db_path = client_dir / "db" / "extrairpo.db"
    if not db_path.exists():
        return None
    _client_db_path_cache = str(db_path)
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
    # Skip dynamic search for trigger-specific questions (step3c handles them)
    _is_trigger_query = any(k in msg_lower for k in ["gatilho", "trigger", "sx7", "sequência", "sequencia"])
    if len(result["rotinas"]) < 2 and not _learned_from_cache and not _is_trigger_query:
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

    # Only process rotinas that are in ROTINA_MAP (known, with meaningful prefixes)
    # Unknown rotinas from dynamic search cause slow full-table scans on 730k rows
    known_rotinas = [r for r in entendimento["rotinas"][:4] if r in ROTINA_MAP]
    # Also accept rotinas matching common Protheus patterns (e.g., MATA120, FINA050)
    for r in entendimento["rotinas"][:4]:
        if r not in known_rotinas and re.match(r'^(MATA|FINA|CTBA|ATFA|CNTA|TMKA|MNTA)\d{3}$', r):
            known_rotinas.append(r)
    known_rotinas = known_rotinas[:4]

    try:
        # 2a. Search PEs by rotina prefixes
        for rotina in known_rotinas:
            info = ROTINA_MAP.get(rotina, {})
            prefixos = info.get("prefixos", [])

            for prefixo in prefixos:
                # Use prefix match (LIKE 'X%') instead of contains ('%X%') for performance
                rows = padrao_db.execute(
                    "SELECT DISTINCT nome_pe, operacao, parametros, tipo_retorno_inferido, funcao, arquivo, contexto, comentario "
                    "FROM execblocks WHERE arquivo LIKE ? OR funcao LIKE ? "
                    "ORDER BY operacao, nome_pe LIMIT 50",
                    (f"{prefixo}%", f"{prefixo}%")
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

            # Also search by rotina name directly — prefix match only
            rows2 = padrao_db.execute(
                "SELECT DISTINCT nome_pe, operacao, parametros, tipo_retorno_inferido, funcao, arquivo "
                "FROM execblocks WHERE UPPER(arquivo) LIKE ? LIMIT 30",
                (f"{rotina}%",)
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

        # 2c. Get standard functions for the main rotinas — prefix match only
        for rotina in known_rotinas:
            rows = padrao_db.execute(
                "SELECT nome, tipo, assinatura, arquivo, resumo_auto FROM funcoes WHERE UPPER(arquivo) LIKE ? LIMIT 50",
                (f"{rotina}%",)
            ).fetchall()
            for r in rows:
                result["funcoes_padrao"].append({
                    "nome": r[0], "tipo": r[1], "assinatura": r[2], "arquivo": r[3],
                    "resumo_auto": r[4] or "",
                })

        # 2d. Search padrao by resumo_auto for concepts — limit combos to avoid slow scans
        conceitos = entendimento.get("conceitos", [])
        tabelas = entendimento.get("tabelas", [])
        if conceitos or tabelas:
            search_words = []
            for c in conceitos:
                search_words.extend(c.split())
            for t in tabelas[:3]:
                search_words.append(t)
            # Limit to max 3 combos to avoid N^2 full-table scans on 730k rows
            result["funcoes_padrao_relevantes"] = []
            combos_tried = 0
            for i, w1 in enumerate(search_words[:4]):
                for w2 in search_words[i+1:4]:
                    if combos_tried >= 3:
                        break
                    combos_tried += 1
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

            # Volumetria real da tabela
            from app.services.workspace.analista_tools import get_uso_tabela
            uso = get_uso_tabela(client_db, tabela)
            uso_label = f" | {uso['descricao_uso']}" if uso.get('descricao_uso') else ""
            parts.append(f"\n═══ ANÁLISE DE CAMPO: {campo} (tabela {tabela} — {tab_info[1]}{uso_label}) ═══")

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


# ── Step 3c: ANÁLISE DE GATILHO ESPECÍFICO ──────────────────────────────────

def _analise_comportamento_regra(regra: str, tipo: str, tabela_seek: str, alias: str, seek: str, chave: str) -> dict:
    """Analisa O QUE o gatilho faz baseado na regra.

    Retorna: {tipo_acao, descricao, funcao_chamada, campos_lidos, tabelas_envolvidas}
    """
    import re as _re
    result = {
        "tipo_acao": "",
        "descricao": "",
        "funcao_chamada": "",
        "campos_lidos": [],
        "tabelas_envolvidas": [],
    }

    if not regra:
        return result

    # Detectar função customizada
    func_match = _re.findall(r'U_(\w+)', regra)
    if func_match:
        result["tipo_acao"] = "funcao_customizada"
        result["funcao_chamada"] = func_match[0]
        result["descricao"] = f"Chama função customizada U_{func_match[0]}"

    # Detectar leitura de campos (ALIAS->CAMPO)
    campos_lidos = _re.findall(r'(\w{2,3})->(\w+)', regra)
    for alias_ref, campo_ref in campos_lidos:
        result["campos_lidos"].append(f"{alias_ref}->{campo_ref}")
        if alias_ref not in result["tabelas_envolvidas"]:
            result["tabelas_envolvidas"].append(alias_ref)

    # Detectar posicionamento em tabela
    if tipo == "P" and tabela_seek:
        result["tipo_acao"] = result["tipo_acao"] or "posicionamento"
        result["descricao"] = (result["descricao"] or "") + f". Posiciona na tabela {tabela_seek} (alias {alias})"
        if tabela_seek not in result["tabelas_envolvidas"]:
            result["tabelas_envolvidas"].append(tabela_seek)

    # Detectar preenchimento direto (sem função)
    if not func_match:
        if tipo == "E":
            result["tipo_acao"] = "preenchimento_direto"
            result["descricao"] = f"Preenche diretamente com: {regra}"
        elif "IIF(" in regra.upper() or "IF(" in regra.upper():
            result["tipo_acao"] = "condicional"
            result["descricao"] = f"Preenchimento condicional: {regra}"
        elif _re.search(r'\w+->\w+', regra):
            result["tipo_acao"] = "leitura_campo"
            result["descricao"] = f"Lê campo de outra tabela: {regra}"

    # Detectar funções padrão
    padrao_funcs = _re.findall(r'\b(Posicione|MsSeek|dbSeek|Reclock|MSExecAuto|FWExecView)\b', regra, _re.IGNORECASE)
    if padrao_funcs:
        result["descricao"] += f". Usa funções padrão: {', '.join(set(padrao_funcs))}"

    return result


def step3c_analise_gatilho(message: str) -> str:
    """Análise de impacto de gatilho com raciocínio de consultor.

    Fluxo:
    1. Encontrar o gatilho (SX7)
    2. Entender O QUE ele faz (posiciona tabela? chama função? regra direta?)
    3. Verificar campo destino: obrigatório? tem validação? inicializador?
    4. Se chama função: verificar se faz algo EXTRA (preenche outros campos)
    5. Verificar outros gatilhos que preenchem o mesmo campo destino
    6. Montar análise de impacto estruturada
    """
    import re as _re

    # Detect trigger references: "gatilho C7_PRODUTO 512", "sequência 512", "seq 512"
    campo_match = _re.findall(r'\b([A-Z][A-Z0-9]{1,2}_\w+)\b', message.upper())
    seq_match = _re.findall(r'(?:seq(?:u[eê]ncia)?|sequencia)\s*[=:]?\s*(\d{1,4})', message.lower())
    if not seq_match:
        seq_match = _re.findall(r'\b(\d{3})\b', message)  # 3-digit numbers as fallback

    if not campo_match or not seq_match:
        return ""

    # Check if message is about a trigger
    msg_lower = message.lower()
    if not any(k in msg_lower for k in ["gatilho", "trigger", "seq", "sequência", "sequencia", "sx7"]):
        return ""

    client_db = _get_client_db()
    if not client_db:
        return ""

    parts = []
    try:
        for campo in campo_match[:2]:
            for seq in seq_match[:2]:
                # ── 1. ENCONTRAR O GATILHO ──
                row = client_db.execute(
                    "SELECT campo_origem, sequencia, campo_destino, regra, tipo, tabela, "
                    "condicao, proprietario, seek, alias, ordem, chave, custom "
                    "FROM gatilhos WHERE campo_origem = ? AND sequencia = ?",
                    (campo, seq)
                ).fetchone()
                if not row:
                    row = client_db.execute(
                        "SELECT campo_origem, sequencia, campo_destino, regra, tipo, tabela, "
                        "condicao, proprietario, seek, alias, ordem, chave, custom "
                        "FROM gatilhos WHERE campo_origem = ? AND sequencia = ?",
                        (campo, seq.zfill(3))
                    ).fetchone()
                if not row:
                    continue

                campo_origem = row[0]
                sequencia = row[1]
                campo_destino = row[2]
                regra = row[3] or ""
                tipo = row[4] or ""
                tabela_seek = row[5] or ""
                condicao = row[6] or ""
                proprietario = row[7] or ""
                seek_flag = row[8] or ""
                alias = row[9] or ""
                ordem = row[10] or ""
                chave = row[11] or ""

                tipo_desc = {"P": "Posicionamento", "E": "Preenchimento"}.get(tipo, tipo)
                prop_desc = "Customizado" if proprietario == "U" else "Padrão"

                parts.append(f"\n╔══════════════════════════════════════════════════════════════╗")
                parts.append(f"║  ANÁLISE DE IMPACTO: GATILHO {campo_origem} seq {sequencia}")
                parts.append(f"╚══════════════════════════════════════════════════════════════╝")

                parts.append(f"\n── 1. DADOS DO GATILHO ──")
                parts.append(f"  Campo Origem: {campo_origem}")
                parts.append(f"  Campo Destino (contradomínio): {campo_destino}")
                parts.append(f"  Regra: {regra}")
                parts.append(f"  Tipo: {tipo} ({tipo_desc})")
                parts.append(f"  Proprietário: {proprietario} ({prop_desc})")
                if tabela_seek:
                    parts.append(f"  Tabela Seek: {tabela_seek} (alias {alias})")
                    parts.append(f"  Chave de busca: {chave}")
                if condicao:
                    parts.append(f"  Condição de execução: {condicao}")
                else:
                    parts.append(f"  Condição: SEMPRE executa (sem condição)")

                # ── 2. ENTENDER O QUE O GATILHO FAZ ──
                comportamento = _analise_comportamento_regra(regra, tipo, tabela_seek, alias, seek_flag, chave)
                parts.append(f"\n── 2. O QUE ESTE GATILHO FAZ ──")
                if comportamento["descricao"]:
                    parts.append(f"  Comportamento: {comportamento['descricao']}")
                if comportamento["campos_lidos"]:
                    parts.append(f"  Campos lidos pela regra: {', '.join(comportamento['campos_lidos'])}")
                if comportamento["tabelas_envolvidas"]:
                    parts.append(f"  Tabelas envolvidas: {', '.join(comportamento['tabelas_envolvidas'])}")

                # ── 3. ANÁLISE DO CAMPO DESTINO ──
                parts.append(f"\n── 3. CAMPO DESTINO: {campo_destino} ──")
                tabela_destino = campo_destino.split("_")[0] if "_" in campo_destino else ""

                campo_info = client_db.execute(
                    "SELECT tabela, tipo, tamanho, titulo, descricao, validacao, "
                    "inicializador, obrigatorio, vlduser, trigger_flag, f3 "
                    "FROM campos WHERE campo = ? LIMIT 1",
                    (campo_destino,)
                ).fetchone()

                if campo_info:
                    is_obrigatorio = campo_info[7] == 1 or str(campo_info[7]).upper() == "S"
                    parts.append(f"  Tabela: {campo_info[0]}")
                    parts.append(f"  Título: {campo_info[3]} — {campo_info[4]}")
                    parts.append(f"  Tipo: {campo_info[1]}, Tamanho: {campo_info[2]}")
                    parts.append(f"  Obrigatório: {'⚠️ SIM' if is_obrigatorio else 'Não'}")
                    if campo_info[5]:
                        parts.append(f"  Validação do campo: {campo_info[5]}")
                    if campo_info[6]:
                        parts.append(f"  Inicializador padrão: {campo_info[6]}")
                    else:
                        parts.append(f"  Inicializador padrão: (nenhum — campo ficará vazio sem o gatilho)")
                    if campo_info[8]:
                        parts.append(f"  Validação de usuário (VldUser): {campo_info[8]}")
                    if campo_info[10]:
                        parts.append(f"  Consulta F3: {campo_info[10]}")
                else:
                    parts.append(f"  (Campo não encontrado no dicionário)")

                # ── 4. FUNÇÃO CUSTOMIZADA — ANÁLISE PROFUNDA ──
                func_name = comportamento.get("funcao_chamada")
                func_row = None
                if func_name:
                    parts.append(f"\n── 4. FUNÇÃO CUSTOMIZADA: U_{func_name} ──")

                    func_row = client_db.execute(
                        "SELECT arquivo, funcao, resumo_auto, resumo FROM funcao_docs WHERE funcao = ?",
                        (func_name,)
                    ).fetchone()
                    if func_row:
                        parts.append(f"  Arquivo: {func_row[0]}")
                        resumo = func_row[3] if func_row[3] else (func_row[2] or "")
                        if resumo:
                            parts.append(f"  Resumo: {resumo}")

                        # Get the actual code
                        chunk = client_db.execute(
                            "SELECT content FROM fonte_chunks WHERE arquivo = ? AND funcao = ?",
                            (func_row[0], func_name)
                        ).fetchone()
                        if chunk and chunk[0]:
                            code = chunk[0]

                            # Detectar campos que a função preenche ALÉM do campo destino
                            # Padrões: M->CAMPO := valor, _FIELD("CAMPO", valor)
                            campos_preenchidos = set()
                            for m in _re.findall(r'M->(\w+)\s*:=', code):
                                if m != campo_destino:
                                    campos_preenchidos.add(m)
                            for m in _re.findall(r'FWFieldPut\s*\(\s*["\'](\w+)["\']', code, _re.IGNORECASE):
                                if m != campo_destino:
                                    campos_preenchidos.add(m)

                            if campos_preenchidos:
                                parts.append(f"\n  ⚠️ CAMPOS EXTRAS preenchidos pela função (além de {campo_destino}):")
                                for cp in sorted(campos_preenchidos):
                                    # Check if extra field is mandatory
                                    cp_info = client_db.execute(
                                        "SELECT titulo, obrigatorio FROM campos WHERE campo = ? LIMIT 1",
                                        (cp,)
                                    ).fetchone()
                                    obrig = ""
                                    if cp_info and (cp_info[1] == 1 or str(cp_info[1]).upper() == "S"):
                                        obrig = " [OBRIGATÓRIO]"
                                    parts.append(f"    - {cp}{obrig}" + (f" ({cp_info[0]})" if cp_info else ""))

                            # Detectar se bloqueia execução (Return .F.)
                            if _re.search(r'Return\s*\(\s*\.F\.', code, _re.IGNORECASE):
                                parts.append(f"\n  ⚠️ FUNÇÃO PODE BLOQUEAR: contém Return(.F.) — impede a operação")

                            # Detectar parâmetros MV_ usados
                            params = _re.findall(r'(?:GetNewPar|SuperGetMv|GetMV)\s*\(\s*["\'](\w+)["\']', code, _re.IGNORECASE)
                            if params:
                                parts.append(f"  Parâmetros MV_ consultados: {', '.join(set(params))}")

                            # Detectar tabelas acessadas
                            tabelas_code = set(_re.findall(r'(?:dbSelectArea|dbSetOrder|MSSeek)\s*\(\s*["\'](\w{2,3})["\']', code, _re.IGNORECASE))
                            if tabelas_code:
                                parts.append(f"  Tabelas acessadas pelo código: {', '.join(sorted(tabelas_code))}")

                            parts.append(f"\n  CÓDIGO FONTE:")
                            parts.append(f"  ```advpl")
                            line_count = 0
                            for line in code.split("\n"):
                                ls = line.rstrip()
                                if ls.strip():
                                    parts.append(f"  {ls}")
                                    line_count += 1
                                    if line_count >= 50:
                                        parts.append(f"  // ... (truncado)")
                                        break
                            parts.append(f"  ```")

                    # Outros fontes que chamam esta função
                    callers = client_db.execute(
                        "SELECT DISTINCT arquivo, funcao FROM funcao_docs "
                        "WHERE (resumo_auto LIKE ? OR resumo LIKE ?) AND arquivo != ? LIMIT 10",
                        (f"%{func_name}%", f"%{func_name}%", func_row[0] if func_row else "")
                    ).fetchall()
                    if callers:
                        parts.append(f"\n  Outros fontes que chamam U_{func_name}:")
                        for c in callers:
                            parts.append(f"    - {c[0]}::{c[1]}")

                # ── 5. OUTROS GATILHOS NO MESMO CAMPO DESTINO ──
                outros_destino = client_db.execute(
                    "SELECT campo_origem, sequencia, regra, tipo, proprietario FROM gatilhos "
                    "WHERE campo_destino = ? AND NOT (campo_origem = ? AND sequencia = ?)",
                    (campo_destino, campo, seq)
                ).fetchall()
                if outros_destino:
                    parts.append(f"\n── 5. OUTROS GATILHOS QUE PREENCHEM {campo_destino} ──")
                    for og in outros_destino:
                        og_prop = "Custom" if og[4] == "U" else "Padrão"
                        parts.append(f"  - {og[0]} seq {og[1]} ({og_prop}): {og[2][:100]}")
                    parts.append(f"  → Estes gatilhos continuarão funcionando após exclusão")
                else:
                    parts.append(f"\n── 5. OUTROS GATILHOS QUE PREENCHEM {campo_destino} ──")
                    parts.append(f"  ⚠️ NENHUM — este é o ÚNICO gatilho que preenche {campo_destino}")

                # Outros gatilhos que usam a mesma função
                if func_name:
                    other_gats = client_db.execute(
                        "SELECT campo_origem, sequencia, campo_destino FROM gatilhos "
                        "WHERE regra LIKE ? AND NOT (campo_origem = ? AND sequencia = ?)",
                        (f"%{func_name}%", campo, seq)
                    ).fetchall()
                    if other_gats:
                        parts.append(f"\n  Outros gatilhos que usam U_{func_name}:")
                        for g in other_gats:
                            parts.append(f"    - {g[0]} seq {g[1]} → {g[2]}")

                # ── 6. RESUMO DE IMPACTO (para o LLM formular a resposta) ──
                parts.append(f"\n── 6. RESUMO DE IMPACTO PARA ANÁLISE ──")
                parts.append(f"  Ao excluir o gatilho {campo_origem} seq {sequencia}:")
                parts.append(f"  - O campo {campo_destino}" + (f" ({campo_info[3]})" if campo_info else "") + " NÃO será mais preenchido automaticamente")

                if campo_info:
                    if not campo_info[6]:  # sem inicializador
                        parts.append(f"  - O campo ficará VAZIO — não há inicializador padrão")
                    else:
                        parts.append(f"  - O campo usará o inicializador padrão: {campo_info[6]}")

                    if is_obrigatorio:
                        parts.append(f"  - ⚠️ CAMPO OBRIGATÓRIO — usuário TERÁ que preencher manualmente")
                    else:
                        parts.append(f"  - Campo não é obrigatório — pode ficar vazio mas pode impactar processos")

                    if campo_info[5]:  # tem validação
                        parts.append(f"  - Campo tem validação ({campo_info[5]}) — preencher incorretamente causará erro")

                if not outros_destino:
                    parts.append(f"  - ⚠️ Não há outro gatilho alternativo para preencher {campo_destino}")

                if func_name and func_row:
                    parts.append(f"  - A função U_{func_name} do arquivo {func_row[0]} deixará de ser chamada por este gatilho")
                    if campos_preenchidos:
                        parts.append(f"  - ⚠️ Campos extras que também perdem preenchimento automático: {', '.join(sorted(campos_preenchidos))}")

    except Exception as e:
        print(f"[decomposer] step3c gatilho error: {e}")
        import traceback; traceback.print_exc()
    finally:
        client_db.close()

    return "\n".join(parts)


# ── Step 3d: ANÁLISE DE CAMPO OBRIGATÓRIO ─────────────────────────────────

def step3d_analise_campo_obrigatorio(message: str) -> str:
    """Análise de impacto de tornar campo obrigatório com raciocínio de consultor.

    Cadeia:
    1. Verificar se campo já é obrigatório ou não
    2. Encontrar programas que gravam na tabela com MsExecAuto (vão quebrar)
    3. Verificar se esses programas são chamados em Jobs, WS, REST, telas, PEs
    4. Encontrar programas que usam Reclock na tabela e se tratam o campo
    """
    import re as _re

    # Detect field + table: "campo C7_CC", "C7_CC obrigatório", "campo XX_YY na tabela ZZZ"
    campo_match = _re.findall(r'\b([A-Z][A-Z0-9]{1,2}_\w+)\b', message.upper())
    if not campo_match:
        return ""

    # Must be about mandatory
    msg_lower = message.lower()
    if not any(k in msg_lower for k in ["obrigatório", "obrigatorio", "obrigatoria", "mandatory"]):
        return ""

    client_db = _get_client_db()
    if not client_db:
        return ""

    parts = []
    try:
        for campo in campo_match[:2]:
            # ── 1. VERIFICAR SE JÁ É OBRIGATÓRIO ──
            campo_info = client_db.execute(
                "SELECT tabela, campo, tipo, tamanho, titulo, descricao, validacao, "
                "inicializador, obrigatorio, vlduser, trigger_flag, f3, proprietario "
                "FROM campos WHERE campo = ? LIMIT 1",
                (campo,)
            ).fetchone()
            if not campo_info:
                continue

            tabela = campo_info[0]
            titulo = campo_info[4] or ""
            descricao = campo_info[5] or ""
            validacao = campo_info[6] or ""
            inicializador = campo_info[7] or ""
            is_obrigatorio = campo_info[8] == 1 or str(campo_info[8]).upper() == "S"
            vlduser = campo_info[9] or ""
            trigger_flag = campo_info[10] or ""
            f3 = campo_info[11] or ""
            proprietario = campo_info[12] or ""

            parts.append(f"\n╔══════════════════════════════════════════════════════════════╗")
            parts.append(f"║  ANÁLISE DE IMPACTO: TORNAR {campo} OBRIGATÓRIO")
            parts.append(f"╚══════════════════════════════════════════════════════════════╝")

            parts.append(f"\n── 1. SITUAÇÃO ATUAL DO CAMPO ──")
            parts.append(f"  Campo: {campo} ({titulo} — {descricao})")
            parts.append(f"  Tabela: {tabela}")
            parts.append(f"  Tipo: {campo_info[2]}, Tamanho: {campo_info[3]}")
            if is_obrigatorio:
                parts.append(f"  ⚠️ JÁ É OBRIGATÓRIO — não precisa alterar")
            else:
                parts.append(f"  Status atual: OPCIONAL")
            parts.append(f"  Proprietário: {proprietario} ({'Customizado' if proprietario == 'U' else 'Padrão'})")
            if validacao:
                parts.append(f"  Validação: {validacao}")
            if vlduser:
                parts.append(f"  Validação de usuário: {vlduser}")
            if inicializador:
                parts.append(f"  Inicializador: {inicializador}")
            else:
                parts.append(f"  Inicializador: (nenhum)")
            if trigger_flag == "S":
                parts.append(f"  Possui gatilho: SIM")
            if f3:
                parts.append(f"  Consulta F3: {f3}")

            if is_obrigatorio:
                parts.append(f"\n  O campo já é obrigatório. Análise de impacto não se aplica.")
                continue

            # ── 2. PROGRAMAS COM MSEXECAUTO QUE GRAVAM NA TABELA ──
            # Esses VÃO QUEBRAR se não passarem o campo no array
            parts.append(f"\n── 2. MSEXECAUTO QUE GRAVAM EM {tabela} (RISCO CRÍTICO) ──")
            parts.append(f"  Se tornar obrigatório, qualquer MsExecAuto que grava em {tabela}")
            parts.append(f"  sem enviar {campo} no array VAI GERAR ERRO em produção.")

            # Find all fonte_chunks that have MsExecAuto AND reference the table's main routine
            # First, find the main routines for this table
            rotina_map_tabela = {v["tabela"]: k for k, v in ROTINA_MAP.items() if "tabela" in v}
            rotina_principal = rotina_map_tabela.get(tabela, "")

            msexecauto_fontes = []
            if rotina_principal:
                rows = client_db.execute(
                    "SELECT DISTINCT fc.arquivo, fc.funcao, fd.resumo_auto "
                    "FROM fonte_chunks fc "
                    "LEFT JOIN funcao_docs fd ON fc.arquivo = fd.arquivo AND fc.funcao = fd.funcao "
                    "WHERE fc.content LIKE '%MsExecAuto%' AND fc.content LIKE ?",
                    (f"%{rotina_principal}%",)
                ).fetchall()
                for r in rows:
                    msexecauto_fontes.append(r)

            # Also search by table alias patterns (e.g., MATA120 for SC7)
            if not msexecauto_fontes:
                # Try generic: any MsExecAuto that also references the table
                rows = client_db.execute(
                    "SELECT DISTINCT fc.arquivo, fc.funcao, fd.resumo_auto "
                    "FROM fonte_chunks fc "
                    "LEFT JOIN funcao_docs fd ON fc.arquivo = fd.arquivo AND fc.funcao = fd.funcao "
                    "WHERE fc.content LIKE '%MsExecAuto%' AND fc.content LIKE ?",
                    (f"%{tabela}%",)
                ).fetchall()
                for r in rows:
                    msexecauto_fontes.append(r)

            if msexecauto_fontes:
                for mf in msexecauto_fontes:
                    arquivo, funcao, resumo = mf
                    parts.append(f"\n  ⚠️ {arquivo}::{funcao}")
                    if resumo:
                        parts.append(f"     Resumo: {resumo[:150]}")

                    # Check if this MsExecAuto already passes the field
                    chunk = client_db.execute(
                        "SELECT content FROM fonte_chunks WHERE arquivo = ? AND funcao = ?",
                        (arquivo, funcao)
                    ).fetchone()
                    if chunk and chunk[0]:
                        code = chunk[0]
                        if campo in code:
                            parts.append(f"     ✅ JÁ REFERENCIA {campo} no código — verificar se envia no array")
                        else:
                            parts.append(f"     ❌ NÃO REFERENCIA {campo} — ALTO RISCO de erro")

                        # Check if called in Job/Schedule/WS context
                        func_callers = client_db.execute(
                            "SELECT DISTINCT arquivo FROM fonte_chunks WHERE content LIKE ? AND arquivo != ?",
                            (f"%{funcao}%", arquivo)
                        ).fetchall()
                        if func_callers:
                            caller_names = [c[0] for c in func_callers]
                            parts.append(f"     Chamado por: {', '.join(caller_names[:5])}")

                # Check if any of these are in Jobs or Schedules
                msexec_arquivos = [mf[0].split('.')[0] for mf in msexecauto_fontes]
                jobs_found = []
                schedules_found = []
                for arq in msexec_arquivos:
                    jr = client_db.execute(
                        "SELECT rotina, sessao FROM jobs WHERE rotina LIKE ?", (f"%{arq}%",)
                    ).fetchall()
                    jobs_found.extend([(arq, j[0], j[1]) for j in jr])

                    sr = client_db.execute(
                        "SELECT rotina, empresa_filial, tipo_recorrencia FROM schedules WHERE rotina LIKE ?",
                        (f"%{arq}%",)
                    ).fetchall()
                    schedules_found.extend([(arq, s[0], s[1], s[2]) for s in sr])

                if jobs_found:
                    parts.append(f"\n  🔴 MSEXECAUTO EM JOBS (execução automática):")
                    for j in jobs_found:
                        parts.append(f"     {j[0]} → Job: {j[1]} (sessão {j[2]})")
                if schedules_found:
                    parts.append(f"\n  🔴 MSEXECAUTO EM SCHEDULES (execução agendada):")
                    for s in schedules_found:
                        parts.append(f"     {s[0]} → Schedule: {s[1]} ({s[2]}, {s[3]})")
                if not jobs_found and not schedules_found:
                    parts.append(f"\n  Nenhum MsExecAuto encontrado em Jobs ou Schedules")
            else:
                parts.append(f"  Nenhum MsExecAuto encontrado para {tabela}")

            # ── 3. PROGRAMAS COM RECLOCK NA TABELA ──
            parts.append(f"\n── 3. PROGRAMAS QUE GRAVAM VIA RECLOCK EM {tabela} ──")
            parts.append(f"  Programas que fazem RecLock em {tabela} e podem precisar tratar {campo}.")

            reclock_fontes = client_db.execute(
                "SELECT arquivo, modulo, lines_of_code FROM fontes WHERE reclock_tables LIKE ?",
                (f'%{tabela}%',)
            ).fetchall()

            if reclock_fontes:
                for rf in reclock_fontes:
                    arquivo_rec = rf[0]
                    modulo_rec = rf[1] or ""
                    loc = rf[2] or 0

                    # Check if this fonte references the field in its code
                    has_field = client_db.execute(
                        "SELECT COUNT(*) FROM fonte_chunks WHERE arquivo = ? AND content LIKE ?",
                        (arquivo_rec, f"%{campo}%")
                    ).fetchone()[0] > 0

                    status = "✅ Referencia" if has_field else "❌ NÃO referencia"
                    parts.append(f"  {status} {campo}: {arquivo_rec} ({modulo_rec}, {loc} LOC)")

                    # Check if this program is in a Job/Schedule
                    arq_base = arquivo_rec.split('.')[0]
                    jr = client_db.execute(
                        "SELECT rotina, sessao FROM jobs WHERE rotina LIKE ?", (f"%{arq_base}%",)
                    ).fetchall()
                    for j in jr:
                        parts.append(f"     🔴 Em JOB: {j[0]} (sessão {j[1]})")
                    sr = client_db.execute(
                        "SELECT rotina, tipo_recorrencia FROM schedules WHERE rotina LIKE ?",
                        (f"%{arq_base}%",)
                    ).fetchall()
                    for s in sr:
                        parts.append(f"     🔴 Em SCHEDULE: {s[0]} ({s[1]})")

                    # Check if it's a PE (ponto de entrada)
                    pe_info = client_db.execute(
                        "SELECT funcao, resumo_auto FROM funcao_docs WHERE arquivo = ? AND "
                        "(resumo_auto LIKE '%User Function%' OR resumo_auto LIKE '%PE %')",
                        (arquivo_rec,)
                    ).fetchall()
                    for pi in pe_info[:3]:
                        parts.append(f"     📌 Função: {pi[0]} — {(pi[1] or '')[:80]}")
            else:
                parts.append(f"  Nenhum programa com RecLock em {tabela}")

            # ── 4. GATILHOS QUE PREENCHEM ESTE CAMPO ──
            parts.append(f"\n── 4. GATILHOS QUE PREENCHEM {campo} ──")
            gatilhos = client_db.execute(
                "SELECT campo_origem, sequencia, regra, tipo, proprietario FROM gatilhos "
                "WHERE campo_destino = ?",
                (campo,)
            ).fetchall()
            if gatilhos:
                parts.append(f"  Se há gatilho preenchendo, talvez o campo já seja populado")
                parts.append(f"  automaticamente e o impacto de obrigatoriedade é menor.")
                for g in gatilhos:
                    prop = "Custom" if g[4] == "U" else "Padrão"
                    parts.append(f"  - {g[0]} seq {g[1]} ({prop}, tipo {g[3]}): {g[2][:100]}")
            else:
                parts.append(f"  NENHUM gatilho preenche {campo}")
                parts.append(f"  → Usuário/programa terá que informar manualmente em TODA operação")

            # ── 5. RESUMO DE IMPACTO ──
            qtd_msexec = len(msexecauto_fontes)
            qtd_reclock = len(reclock_fontes)
            qtd_reclock_sem = sum(1 for rf in reclock_fontes if client_db.execute(
                "SELECT COUNT(*) FROM fonte_chunks WHERE arquivo = ? AND content LIKE ?",
                (rf[0], f"%{campo}%")
            ).fetchone()[0] == 0) if reclock_fontes else 0

            parts.append(f"\n── 5. RESUMO DE IMPACTO ──")
            parts.append(f"  Ao tornar {campo} ({titulo}) obrigatório em {tabela}:")
            if qtd_msexec > 0:
                parts.append(f"  🔴 {qtd_msexec} MsExecAuto precisam ser revisados — RISCO de erro em produção")
            if qtd_reclock > 0:
                parts.append(f"  🟡 {qtd_reclock} programas com RecLock em {tabela}")
                if qtd_reclock_sem > 0:
                    parts.append(f"     ❌ {qtd_reclock_sem} deles NÃO referenciam {campo} — precisam análise")
            if gatilhos:
                parts.append(f"  🟢 Existe(m) {len(gatilhos)} gatilho(s) preenchendo — reduz risco em operações de tela")
            else:
                parts.append(f"  🟡 Sem gatilho — todo preenchimento será manual")
            if jobs_found or schedules_found:
                parts.append(f"  🔴 Há processos automáticos (Jobs/Schedules) que podem quebrar")

    except Exception as e:
        print(f"[decomposer] step3d campo_obrigatorio error: {e}")
        import traceback; traceback.print_exc()
    finally:
        client_db.close()

    return "\n".join(parts)


# ── Step 3e: ANÁLISE DE AUMENTO DE CAMPO ──────────────────────────────────

def step3e_analise_aumento_campo(message: str) -> str:
    """Análise de impacto de alterar tamanho de campo com raciocínio de consultor.

    Cadeia:
    1. Identificar campo, tabela e novo tamanho
    2. Verificar grupo SXG (campos que mudam automaticamente)
    3. Campos fora do grupo com F3 (precisam ajuste manual)
    4. PadR/Space chumbado nos fontes (vão truncar)
    5. Índices que podem estourar
    6. MsExecAuto que enviam campo com tamanho antigo
    """
    import re as _re

    # Detect field
    campo_match = _re.findall(r'\b([A-Z][A-Z0-9]{1,2}_\w+)\b', message.upper())
    if not campo_match:
        return ""

    # Detect new size: "de 11 para 15", "para 20", "15 caracteres", "15 posições"
    size_match = _re.findall(r'para\s+(\d+)', message.lower())
    if not size_match:
        size_match = _re.findall(r'(\d+)\s*(?:caracter|posiç|posico)', message.lower())
    novo_tamanho = int(size_match[0]) if size_match else 0

    # Detect table from field prefix or explicit mention
    tabela_match = _re.findall(r'\b(S[A-Z][A-Z0-9])\b', message.upper())

    # Infer table from field prefix if not explicitly mentioned
    campo = campo_match[0]
    if not tabela_match:
        # C7_ → SC7, B1_ → SB1, D1_ → SD1
        prefix = campo.split("_")[0]
        if len(prefix) == 2:
            tabela_match = [f"S{prefix}"]

    tabela = tabela_match[0] if tabela_match else ""
    if not tabela:
        return ""

    # Call the existing comprehensive tool
    try:
        from app.services.workspace.analise_campo_chave import tool_analise_aumento_campo
        result = tool_analise_aumento_campo(tabela, campo, novo_tamanho)
    except Exception as e:
        print(f"[decomposer] step3e error calling tool: {e}")
        return ""

    if not result or "erro" in result:
        return ""

    # Format as consultant reasoning
    parts = []
    parts.append(f"\n╔══════════════════════════════════════════════════════════════╗")
    parts.append(f"║  ANÁLISE DE IMPACTO: ALTERAR TAMANHO DE {campo}")
    parts.append(f"╚══════════════════════════════════════════════════════════════╝")

    # ── 1. SITUAÇÃO ATUAL ──
    parts.append(f"\n── 1. SITUAÇÃO ATUAL DO CAMPO ──")
    parts.append(f"  Campo: {result['campo']} ({result.get('titulo', '')})")
    parts.append(f"  Tabela: {result['tabela']}")
    parts.append(f"  Tipo: {result.get('tipo', '')}")
    parts.append(f"  Tamanho atual: {result['tamanho_atual']}")
    if novo_tamanho:
        parts.append(f"  Novo tamanho desejado: {novo_tamanho}")
        parts.append(f"  Delta: +{novo_tamanho - result['tamanho_atual']} posições")

    # ── 2. GRUPO SXG ──
    grupo = result.get("grupo_sxg", "")
    campos_grupo = result.get("campos_grupo", [])
    parts.append(f"\n── 2. GRUPO SXG ──")
    if grupo:
        gi = result.get("grupo_info", {})
        parts.append(f"  Grupo: {grupo} — {gi.get('descricao', '')}")
        parts.append(f"  ✅ {len(campos_grupo)} campos mudam AUTOMATICAMENTE via Configurador")
        tabelas_afetadas = sorted(set(c["tabela"] for c in campos_grupo))
        if len(tabelas_afetadas) > 20:
            parts.append(f"  Tabelas afetadas ({len(tabelas_afetadas)}): {', '.join(tabelas_afetadas[:20])}... +{len(tabelas_afetadas)-20} outras")
        else:
            parts.append(f"  Tabelas afetadas ({len(tabelas_afetadas)}): {', '.join(tabelas_afetadas)}")

        inconsistentes = result.get("campos_inconsistentes", [])
        if inconsistentes:
            parts.append(f"\n  ⚠️ {len(inconsistentes)} campos JÁ INCONSISTENTES (tamanho diferente do grupo):")
            for ci in inconsistentes[:10]:
                parts.append(f"    {ci['tabela']}.{ci['campo']} = {ci['tamanho']} (esperado: {result['tamanho_atual']})")
    else:
        parts.append(f"  ⚠️ Campo NÃO pertence a nenhum grupo SXG")
        parts.append(f"  Alteração precisará ser feita MANUALMENTE em cada tabela")

    # ── 3. CAMPOS FORA DO GRUPO (RISCO) ──
    campos_fora = result.get("campos_fora_grupo", [])
    parts.append(f"\n── 3. CAMPOS FORA DO GRUPO COM F3 (RISCO — AJUSTE MANUAL) ──")
    if campos_fora:
        parts.append(f"  ⚠️ {len(campos_fora)} campos referenciam {tabela} via F3 mas NÃO estão no grupo {grupo}")
        parts.append(f"  Esses NÃO mudam automaticamente — precisam ajuste MANUAL:")
        for cf in campos_fora[:20]:
            parts.append(f"    {cf['tabela']}.{cf['campo']} ({cf['titulo']}) — tam {cf['tamanho']}, grupo: {cf['grupo_atual']}")
        if len(campos_fora) > 20:
            parts.append(f"    ... +{len(campos_fora)-20} outros")
    else:
        parts.append(f"  Nenhum campo fora do grupo referencia {tabela}")

    # Campos custom suspeitos
    suspeitos = result.get("campos_suspeitos_custom", [])
    if suspeitos:
        parts.append(f"\n  🟡 {len(suspeitos)} campos CUSTOMIZADOS apontam F3 para {tabela}:")
        for cs in suspeitos[:15]:
            parts.append(f"    {cs['tabela']}.{cs['campo']} ({cs['titulo']}) — tam {cs['tamanho']}, grupo: {cs['grupo']}")

    # ── 4. PADR/SPACE CHUMBADO (RISCO CRÍTICO) ──
    padr = result.get("padr_chumbado", [])
    parts.append(f"\n── 4. PADR/SPACE CHUMBADO NOS FONTES (RISCO — VÃO TRUNCAR) ──")
    if padr:
        alta = [p for p in padr if p.get("confianca") == "alta"]
        media = [p for p in padr if p.get("confianca") != "alta"]
        if alta:
            parts.append(f"  🔴 {len(alta)} ocorrências de ALTA CONFIANÇA (mencionam o campo/tabela):")
            for p in alta[:15]:
                parts.append(f"    {p['arquivo']}::{p['funcao']} — {p['tipo']}({p['tamanho']})")
                for t in p.get("trechos", [])[:2]:
                    parts.append(f"      → {t}")
        if media:
            parts.append(f"  🟡 {len(media)} ocorrências de MÉDIA CONFIANÇA (mesmo tamanho mas sem menção direta):")
            for p in media[:10]:
                parts.append(f"    {p['arquivo']}::{p['funcao']} — {p['tipo']}({p['tamanho']})")
                for t in p.get("trechos", [])[:1]:
                    parts.append(f"      → {t}")
    else:
        parts.append(f"  ✅ Nenhum PadR/Space chumbado encontrado")

    # TamSX3 dinâmico (ok)
    tamsx3 = result.get("tamsx3_dinamico", [])
    if tamsx3:
        parts.append(f"\n  ✅ {len(tamsx3)} fontes usam TamSX3 dinâmico (se adaptam automaticamente):")
        for t in tamsx3[:10]:
            parts.append(f"    {t}")

    # ── 5. ÍNDICES ──
    indices = result.get("indices_risco", [])
    parts.append(f"\n── 5. ÍNDICES QUE PODEM ESTOURAR ──")
    if indices:
        for idx in indices:
            parts.append(f"  ⚠️ {idx['tabela']} índice {idx['ordem']}: {idx['risco']}")
            parts.append(f"    Chave: {idx['chave']}")
            parts.append(f"    Campos afetados: {', '.join(idx['campos_afetados'])}")
            parts.append(f"    Crescimento: +{idx['crescimento']} chars → estimado {idx['tamanho_estimado']} (limite 250)")
    else:
        if novo_tamanho:
            parts.append(f"  ✅ Nenhum índice em risco de estourar com o novo tamanho")
        else:
            parts.append(f"  (Informe o novo tamanho para verificar índices)")

    # ── 6. MSEXECAUTO ──
    msexec = result.get("msexecauto", [])
    parts.append(f"\n── 6. MSEXECAUTO (PODEM ENVIAR TAMANHO ANTIGO) ──")
    if msexec:
        parts.append(f"  ⚠️ {len(msexec)} MsExecAuto encontrados:")
        for m in msexec:
            parts.append(f"    {m['arquivo']} — {m['risco']}")
    else:
        parts.append(f"  Nenhum MsExecAuto encontrado para a tabela")

    # ── 7. INTEGRAÇÕES ──
    integr = result.get("integracoes", [])
    if integr:
        parts.append(f"\n── 7. INTEGRAÇÕES ──")
        parts.append(f"  ⚠️ {len(integr)} integrações gravam em {tabela}:")
        for i in integr:
            parts.append(f"    {i['arquivo']} ({i['modulo']})")

    # ── 8. RESUMO DE IMPACTO ──
    res = result.get("resumo", {})
    parts.append(f"\n── RESUMO DE IMPACTO ──")
    parts.append(f"  Ao alterar {campo} de {result['tamanho_atual']} para {novo_tamanho or '?'} posições:")
    if grupo:
        parts.append(f"  ✅ {res.get('mudam_automaticamente', 0)} campos mudam automaticamente (grupo SXG {grupo})")
    parts.append(f"  🟡 {res.get('precisam_ajuste_manual', 0)} campos precisam ajuste MANUAL (fora do grupo)")
    parts.append(f"  🟡 {res.get('suspeitos_custom', 0)} campos custom suspeitos")
    if res.get('padr_chumbado', 0):
        parts.append(f"  🔴 {res['padr_chumbado']} PadR/Space chumbados (vão TRUNCAR)")
    if res.get('indices_risco', 0):
        parts.append(f"  🔴 {res['indices_risco']} índices em risco de estourar")
    if res.get('msexecauto', 0):
        parts.append(f"  🟡 {res['msexecauto']} MsExecAuto para revisar")
    if res.get('integracoes', 0):
        parts.append(f"  🟡 {res['integracoes']} integrações para revisar")

    return "\n".join(parts)


def decompose_and_investigate(message: str, llm=None) -> str:
    """Run full 4-step decomposition pipeline.

    Returns formatted context string ready for LLM consumption.
    """
    msg_lower = message.lower()

    # ── FAST PATH: Trigger-specific queries go straight to SX7 ──
    _is_trigger_query = (
        any(k in msg_lower for k in ["gatilho", "trigger", "sx7"])
        and re.search(r'\b[A-Z][A-Z0-9]{1,2}_\w+', message)
    )
    if _is_trigger_query:
        print(f"[decomposer] FAST PATH: trigger query detected")
        gatilho_context = step3c_analise_gatilho(message)
        if gatilho_context:
            return gatilho_context
        # If step3c found nothing, fall through to full pipeline

    # ── FAST PATH: Mandatory field impact ──
    _is_mandatory_query = (
        any(k in msg_lower for k in ["obrigatório", "obrigatorio", "obrigatoria", "mandatory"])
        and re.search(r'\b[A-Z][A-Z0-9]{1,2}_\w+', message)
    )
    if _is_mandatory_query:
        print(f"[decomposer] FAST PATH: mandatory field query detected")
        mandatory_context = step3d_analise_campo_obrigatorio(message)
        if mandatory_context:
            return mandatory_context

    # ── FAST PATH: Field size change ──
    _is_size_query = (
        any(k in msg_lower for k in ["aumentar", "aumento", "ampliar", "tamanho", "posições",
                                      "posicoes", "expandir", "reduzir", "caracteres"])
        and re.search(r'\b[A-Z][A-Z0-9]{1,2}_\w+', message)
    )
    if _is_size_query:
        print(f"[decomposer] FAST PATH: field size change query detected")
        size_context = step3e_analise_aumento_campo(message)
        if size_context:
            return size_context

    # Step 1
    entendimento = step1_entender(message, llm)
    entendimento["_msg_words"] = [w.lower() for w in message.split() if len(w) > 3]

    # Step 2
    mapa_padrao = step2_mapear_padrao(entendimento)

    # Step 3
    cruzamento = step3_cruzar_cliente(entendimento, mapa_padrao)

    # Step 3b — Field-specific analysis (table ecosystem for mandatory/new fields)
    campo_context = step3b_analise_campo(message, entendimento)

    # Step 3c — Trigger-specific analysis
    gatilho_context = step3c_analise_gatilho(message)

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

    # Add trigger analysis if available
    if gatilho_context:
        parts.append(gatilho_context)

    return "\n".join(parts)
