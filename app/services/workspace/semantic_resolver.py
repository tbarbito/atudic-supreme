# backend/services/semantic_resolver.py
"""Semantic resolver — translate vague user messages into concrete Protheus entities.

Uses 5 data sources from the client environment:
1. Menus (43K entries) — match routine names by keyword
2. Propósitos (8K fonte summaries) — semantic match on AI-generated descriptions
3. Processos detectados — known client workflows
4. Campos por título — field names matching keywords
5. Padrão (padrao.db) — standard routines by name

Returns ranked candidates: [{tabela, campo, rotina, fontes, confiança, descrição}]
"""
import json
import re
from pathlib import Path
from app.services.workspace.config import load_config, get_client_workspace
from app.services.workspace.workspace_db import Database

WORKSPACE = Path("workspace")
CONFIG_PATH = Path("config.json")

# Words to exclude from search
_STOPWORDS = {
    "tem", "uma", "um", "que", "de", "do", "da", "dos", "das", "no", "na",
    "nos", "nas", "ao", "para", "por", "com", "sem", "mas", "acho", "algo",
    "assim", "isso", "esta", "pode", "verificar", "parece", "usuario", "tela",
    "salva", "salvar", "alterado", "alterar", "campo", "rotina", "programa",
    "fonte", "quando", "nao", "valor", "tipo", "tambem", "deveria", "antes",
    "depois", "ainda", "sempre", "nunca", "estou", "problema", "erro",
    "como", "qual", "onde", "porque", "esta", "estamos", "preciso",
}


def _get_db() -> Database:
    config = load_config(CONFIG_PATH)
    client_dir = get_client_workspace(WORKSPACE, config.active_client)
    db_path = client_dir / "db" / "extrairpo.db"
    db = Database(db_path)
    db.initialize()
    return db


# Protheus contextual synonyms — expand search terms to cover vocabulary gaps.
# These are NOT entity mappings (like "pedido de venda" → SC5).
# They are WORD equivalences that help menus/propositos match.
_SYNONYM_EXPANSIONS = {
    "bloqueio": ["liberacao", "liberação", "bloqueio", "bloqueado", "bloq"],
    "liberacao": ["bloqueio", "liberacao", "liberação", "aprovacao"],
    "liberação": ["bloqueio", "liberacao", "liberação", "aprovacao"],
    "aprovacao": ["liberacao", "liberação", "aprovacao", "aprovação"],
    "aprovação": ["liberacao", "liberação", "aprovacao", "aprovação"],
    "rateio": ["rateio", "distribuicao", "distribuição", "centro custo"],
    "distribuicao": ["rateio", "distribuicao", "distribuição"],
    "desconto": ["desconto", "abatimento", "rebate"],
    "estorno": ["estorno", "cancelamento", "devolucao"],
    "cancelamento": ["estorno", "cancelamento", "devolucao"],
    "devolucao": ["devolucao", "devolução", "estorno"],
    "integracao": ["integracao", "integração", "interface", "edi"],
}


def _extrair_termos(mensagem: str) -> list[str]:
    """Extract meaningful search terms from user message."""
    words = re.findall(r'\b(\w{3,})\b', mensagem.lower())
    return [w for w in words if w not in _STOPWORDS]


def _expandir_termos(termos: list[str]) -> list[str]:
    """Expand terms with Protheus contextual synonyms for broader search."""
    expanded = set(termos)
    for t in termos:
        t_norm = _normalize(t)
        for key, synonyms in _SYNONYM_EXPANSIONS.items():
            if t_norm == _normalize(key):
                expanded.update(synonyms)
    return list(expanded)


def _normalize(text: str) -> str:
    """Remove accents for search matching."""
    import unicodedata
    nfkd = unicodedata.normalize('NFKD', text)
    return ''.join(c for c in nfkd if not unicodedata.combining(c)).lower()


def _resolve_tabelas_rotina(db: Database, rotina: str) -> list[str]:
    """Find tables for a routine — tries client DB first, then padrao.db."""
    rotina_upper = rotina.upper()

    # 1. Try client fontes — write_tables first, then tabelas_ref
    fonte = db.execute(
        "SELECT write_tables, tabelas_ref FROM fontes WHERE UPPER(arquivo) LIKE ? LIMIT 1",
        (f"%{rotina_upper}%",)
    ).fetchone()
    if fonte:
        for col_idx in [0, 1]:  # write_tables, then tabelas_ref
            if fonte[col_idx]:
                try:
                    tabs = json.loads(fonte[col_idx])
                    # Filter out system tables (SX*, SM0)
                    tabs = [t for t in tabs if not t.startswith("SX") and t != "SM0"]
                    if tabs:
                        return tabs
                except (json.JSONDecodeError, TypeError):
                    pass

    # 2. Fallback: try padrao.db
    try:
        from app.services.workspace.padrao_database import PadraoDB
        from app.services.workspace.workspace_populator import _get_fontes_padrao_db_path
        padrao_path = _get_fontes_padrao_db_path()
        if padrao_path.exists():
            pdb = PadraoDB(padrao_path)
            pdb.initialize()
            try:
                # Try tabelas_ref in padrao fontes
                pfonte = pdb.execute(
                    "SELECT tabelas_ref, write_tables FROM fontes WHERE UPPER(arquivo) LIKE ? LIMIT 1",
                    (f"%{rotina_upper}%",)
                ).fetchone()
                if pfonte:
                    for col in [pfonte["write_tables"], pfonte["tabelas_ref"]]:
                        if col:
                            try:
                                tabs = json.loads(col)
                                tabs = [t for t in tabs if not t.startswith("SX") and t != "SM0"]
                                if tabs:
                                    return tabs
                            except (json.JSONDecodeError, TypeError):
                                pass

                # 3. Last resort: check funcoes.tabelas_ref in padrao
                func_rows = pdb.execute(
                    "SELECT tabelas_ref FROM funcoes WHERE UPPER(arquivo) LIKE ? AND tabelas_ref != '[]' LIMIT 5",
                    (f"%{rotina_upper}%",)
                ).fetchall()
                all_tabs = set()
                for fr in func_rows:
                    try:
                        tabs = json.loads(fr["tabelas_ref"])
                        for t in tabs:
                            if not t.startswith("SX") and t != "SM0":
                                all_tabs.add(t)
                    except (json.JSONDecodeError, TypeError):
                        pass
                if all_tabs:
                    return sorted(all_tabs)
            finally:
                pdb.close()
    except Exception:
        pass

    return []


# Cache for menus (loaded once per resolver call)
_menu_cache = None
_menu_cache_db_path = None


def _get_menu_cache(db: Database) -> list:
    """Cache all menus in memory for fast search."""
    global _menu_cache, _menu_cache_db_path
    # Simple cache invalidation by db path
    db_path = str(getattr(db, 'db_path', ''))
    if _menu_cache is not None and _menu_cache_db_path == db_path:
        return _menu_cache
    _menu_cache = db.execute("SELECT modulo, rotina, nome, menu FROM menus").fetchall()
    _menu_cache_db_path = db_path
    return _menu_cache


def _buscar_menus(db: Database, termos: list[str]) -> list[dict]:
    """Search menus table for routines matching terms."""
    results = []
    seen_rotinas = set()

    all_rows = _get_menu_cache(db)

    # First try: all terms combined (highest precision)
    for r in all_rows:
        nome_norm = _normalize(r[2] or "")
        if all(_normalize(t) in nome_norm for t in termos):
            rotina = r[1]
            if rotina not in seen_rotinas:
                seen_rotinas.add(rotina)
                tabelas = _resolve_tabelas_rotina(db, rotina)
                results.append({
                    "tipo": "menu",
                    "rotina": rotina,
                    "nome": r[2],
                    "modulo": r[0],
                    "menu_path": r[3] or "",
                    "tabelas": tabelas,
                })
        if len(results) >= 10:
            break

    if results:
        return results

    # Second try: pairs of terms (when 3+ terms, some may not all appear in one menu)
    if len(termos) >= 2:
        for i in range(len(termos)):
            for j in range(i + 1, len(termos)):
                t1_norm = _normalize(termos[i])
                t2_norm = _normalize(termos[j])
                for r in all_rows:
                    nome_norm = _normalize(r[2] or "")
                    if t1_norm in nome_norm and t2_norm in nome_norm:
                        rotina = r[1]
                        if rotina not in seen_rotinas:
                            seen_rotinas.add(rotina)
                            tabelas = _resolve_tabelas_rotina(db, rotina)
                            results.append({
                                "tipo": "menu",
                                "rotina": rotina,
                                "nome": r[2],
                                "modulo": r[0],
                                "menu_path": r[3] or "",
                                "tabelas": tabelas,
                            })
                    if len(results) >= 15:
                        break
                if len(results) >= 15:
                    break
            if len(results) >= 15:
                break

    if results:
        return results

    # Fallback: search per term
    for termo in termos:
        termo_norm = _normalize(termo)
        rows = []
        for r in all_rows:
            if termo_norm in _normalize(r[2] or "") and r[1] not in seen_rotinas:
                rows.append(r)
        rows = rows[:10]

        for r in rows:
            rotina = r[1]
            if rotina not in seen_rotinas:
                seen_rotinas.add(rotina)
                tabelas = _resolve_tabelas_rotina(db, rotina)
                results.append({
                    "tipo": "menu",
                    "rotina": rotina,
                    "nome": r[2],
                    "modulo": r[0],
                    "menu_path": r[3] or "",
                    "tabelas": tabelas,
                })

    return results


def _buscar_propositos(db: Database, termos: list[str]) -> list[dict]:
    """Search fonte propósitos (AI-generated summaries) for matching terms."""
    results = []
    seen = set()

    # Build LIKE clauses for each term
    conditions = " AND ".join(["LOWER(proposito) LIKE ?"] * len(termos))
    params = tuple(f"%{t}%" for t in termos)

    if not termos:
        return []

    # Try all terms together first (highest precision)
    rows = db.execute(
        f"SELECT chave, proposito FROM propositos WHERE {conditions} LIMIT 10",
        params
    ).fetchall()

    # If no results with all terms, try pairs
    if not rows and len(termos) >= 2:
        for i in range(len(termos)):
            for j in range(i + 1, len(termos)):
                pair_rows = db.execute(
                    "SELECT chave, proposito FROM propositos "
                    "WHERE LOWER(proposito) LIKE ? AND LOWER(proposito) LIKE ? LIMIT 5",
                    (f"%{termos[i]}%", f"%{termos[j]}%")
                ).fetchall()
                rows.extend(pair_rows)

    for r in rows:
        arquivo = r[0]
        if arquivo in seen:
            continue
        seen.add(arquivo)

        proposito_text = ""
        try:
            p = json.loads(r[1])
            proposito_text = p.get("humano", "")[:200]
        except (json.JSONDecodeError, TypeError):
            proposito_text = (r[1] or "")[:200]

        # Get fonte metadata — include both write_tables and tabelas_ref
        fonte = db.execute(
            "SELECT modulo, write_tables, tabelas_ref FROM fontes WHERE UPPER(arquivo) = ? LIMIT 1",
            (arquivo.upper(),)
        ).fetchone()

        tabelas = []
        if fonte:
            # Prefer write_tables, fallback to tabelas_ref
            for col_idx in [1, 2]:
                if fonte[col_idx]:
                    try:
                        tabs = json.loads(fonte[col_idx])
                        tabs = [t for t in tabs if not t.startswith("SX") and t != "SM0"]
                        tabelas.extend(tabs)
                    except (json.JSONDecodeError, TypeError):
                        pass
            tabelas = list(dict.fromkeys(tabelas))  # deduplicate preserving order

        results.append({
            "tipo": "proposito",
            "arquivo": arquivo,
            "proposito": proposito_text,
            "modulo": fonte[0] if fonte else "",
            "tabelas": tabelas,
        })

    return results[:10]


def _buscar_campos_por_titulo(db: Database, termos: list[str], tabelas_hint: list[str] = None) -> list[dict]:
    """Search fields by title/description matching terms.

    Args:
        termos: Search terms
        tabelas_hint: If provided, prioritize campos from these tables (from menus/propositos)
    """
    results_priority = []  # Campos in hint tables
    results_other = []     # Campos in other tables
    seen = set()

    for termo in termos:
        if len(termo) < 4:  # Skip very short terms
            continue

        rows = db.execute(
            "SELECT tabela, campo, titulo, tipo, tamanho FROM campos "
            "WHERE (LOWER(titulo) LIKE ? OR LOWER(campo) LIKE ?) "
            "LIMIT 30",
            (f"%{termo}%", f"%{termo}%")
        ).fetchall()

        for r in rows:
            key = f"{r[0]}.{r[1]}"
            if key in seen:
                continue
            seen.add(key)
            item = {
                "tipo": "campo",
                "tabela": r[0],
                "campo": r[1],
                "titulo": r[2] or "",
                "tipo_campo": r[3] or "",
                "tamanho": r[4] or "",
            }
            # Prioritize campos in tables we already found via menus/propositos
            if tabelas_hint and r[0] in tabelas_hint:
                results_priority.append(item)
            else:
                results_other.append(item)

    # Return priority first, then others (limited)
    return results_priority[:10] + results_other[:10]

    return results[:20]


def _buscar_processos(db: Database, termos: list[str]) -> list[dict]:
    """Search detected client processes."""
    results = []

    try:
        count = db.execute("SELECT COUNT(*) FROM processos_detectados").fetchone()[0]
        if count == 0:
            return []
    except Exception:
        return []

    for termo in termos:
        rows = db.execute(
            "SELECT nome, tipo, descricao, tabelas, score FROM processos_detectados "
            "WHERE LOWER(nome) LIKE ? OR LOWER(descricao) LIKE ? "
            "ORDER BY score DESC LIMIT 5",
            (f"%{termo}%", f"%{termo}%")
        ).fetchall()
        for r in rows:
            tabelas = []
            try:
                tabelas = json.loads(r[3]) if r[3] else []
            except (json.JSONDecodeError, TypeError):
                pass
            results.append({
                "tipo": "processo",
                "nome": r[0],
                "tipo_processo": r[1],
                "descricao": (r[2] or "")[:150],
                "tabelas": tabelas,
                "score": r[4] or 0,
            })

    return results[:5]


def _agrupar_candidatos(menus, propositos, processos, campos) -> list[dict]:
    """Group results from all sources into ranked candidates.

    A candidate is a {tabela, rotina, fontes, confiança, descrição} that represents
    one possible interpretation of what the user meant.

    Candidates that appear in multiple sources get boosted confidence.
    """
    # Build a map: tabela → evidence
    tabela_evidence = {}

    for m in menus:
        for tab in m.get("tabelas", []):
            tab = tab.upper()
            if tab not in tabela_evidence:
                tabela_evidence[tab] = {"fontes_evidencia": [], "rotinas": set(), "modulos": set(), "descricoes": []}
            tabela_evidence[tab]["fontes_evidencia"].append("menu")
            tabela_evidence[tab]["rotinas"].add(m["rotina"])
            tabela_evidence[tab]["modulos"].add(m.get("modulo", ""))
            tabela_evidence[tab]["descricoes"].append(f"Menu: {m['nome']} ({m.get('menu_path', '')})")

    for p in propositos:
        for tab in p.get("tabelas", []):
            tab = tab.upper()
            if tab not in tabela_evidence:
                tabela_evidence[tab] = {"fontes_evidencia": [], "rotinas": set(), "modulos": set(), "descricoes": []}
            tabela_evidence[tab]["fontes_evidencia"].append("proposito")
            tabela_evidence[tab]["descricoes"].append(f"Fonte: {p['arquivo']} — {p['proposito'][:100]}")

    for proc in processos:
        for tab in proc.get("tabelas", []):
            tab = tab.upper()
            if tab not in tabela_evidence:
                tabela_evidence[tab] = {"fontes_evidencia": [], "rotinas": set(), "modulos": set(), "descricoes": []}
            tabela_evidence[tab]["fontes_evidencia"].append("processo")
            tabela_evidence[tab]["descricoes"].append(f"Processo: {proc['nome']} — {proc['descricao'][:100]}")

    for c in campos:
        tab = c["tabela"].upper()
        if tab not in tabela_evidence:
            tabela_evidence[tab] = {"fontes_evidencia": [], "rotinas": set(), "modulos": set(), "descricoes": []}
        tabela_evidence[tab]["fontes_evidencia"].append("campo")
        tabela_evidence[tab]["descricoes"].append(f"Campo: {c['campo']} ({c['titulo']})")

    # Score candidates: distinct sources + volume of evidence
    candidatos = []
    for tab, ev in tabela_evidence.items():
        source_types = set(ev["fontes_evidencia"])
        n_sources = len(source_types)
        n_total = len(ev["fontes_evidencia"])
        confianca = min(1.0, 0.3 + (n_sources * 0.2))

        # Volume boost: many menus pointing to same table = strong signal
        if n_total >= 5:
            confianca = min(1.0, confianca + 0.15)
        elif n_total >= 3:
            confianca = min(1.0, confianca + 0.1)

        # Extra boost for strong combinations
        if "menu" in source_types and "proposito" in source_types:
            confianca = min(1.0, confianca + 0.15)
        if "menu" in source_types and "campo" in source_types:
            confianca = min(1.0, confianca + 0.1)
        if "processo" in source_types:
            confianca = min(1.0, confianca + 0.1)

        # Get table name
        campos_do_tab = [c for c in campos if c["tabela"].upper() == tab]

        candidatos.append({
            "tabela": tab,
            "rotinas": sorted(ev["rotinas"]),
            "modulos": sorted(ev["modulos"] - {""}),
            "campos_relevantes": [c["campo"] for c in campos_do_tab[:5]],
            "confianca": round(confianca, 2),
            "evidencias": len(ev["fontes_evidencia"]),
            "descricao": ev["descricoes"][0] if ev["descricoes"] else "",
            "todas_descricoes": ev["descricoes"][:5],
        })

    # Sort by confidence (desc), then by evidence count
    candidatos.sort(key=lambda x: (-x["confianca"], -x["evidencias"]))

    return candidatos[:10]


def resolver_semantico(mensagem: str, entidades_explicitas: dict = None) -> dict:
    """Main entry point: resolve a vague user message into concrete Protheus entities.

    Args:
        mensagem: Raw user message
        entidades_explicitas: Already-detected entities from classifier (optional)

    Returns:
        {
            resolvido: bool,
            termos: [str],
            candidatos: [{tabela, rotinas, campos_relevantes, confianca, descricao}],
            menus: [...],
            propositos: [...],
            processos: [...],
            campos: [...],
        }
    """
    termos = _extrair_termos(mensagem)
    if not termos:
        return {"resolvido": False, "termos": [], "candidatos": []}

    db = _get_db()
    try:
        # Expand terms with synonyms for broader menu/proposito search
        termos_expandidos = _expandir_termos(termos)

        menus = _buscar_menus(db, termos)
        # Also search with expanded terms if original didn't find much
        if len(menus) < 3:
            menus_exp = _buscar_menus(db, termos_expandidos)
            seen_rotinas = {m["rotina"] for m in menus}
            for m in menus_exp:
                if m["rotina"] not in seen_rotinas:
                    menus.append(m)
                    seen_rotinas.add(m["rotina"])

        propositos = _buscar_propositos(db, termos)
        if len(propositos) < 3:
            propositos_exp = _buscar_propositos(db, termos_expandidos)
            seen_arqs = {p["arquivo"] for p in propositos}
            for p in propositos_exp:
                if p["arquivo"] not in seen_arqs:
                    propositos.append(p)
                    seen_arqs.add(p["arquivo"])

        processos = _buscar_processos(db, termos)

        # Collect tables already found by menus/propositos to prioritize campo search
        hint_tables = set()
        for m in menus:
            hint_tables.update(m.get("tabelas", []))
        for p in propositos:
            hint_tables.update(p.get("tabelas", []))
        for proc in processos:
            hint_tables.update(proc.get("tabelas", []))

        campos = _buscar_campos_por_titulo(db, termos, list(hint_tables) if hint_tables else None)

        candidatos = _agrupar_candidatos(menus, propositos, processos, campos)

        return {
            "resolvido": len(candidatos) > 0,
            "termos": termos,
            "candidatos": candidatos,
            "menus": menus,
            "propositos": propositos,
            "processos": processos,
            "campos": campos,
        }
    finally:
        db.close()
