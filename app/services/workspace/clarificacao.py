"""Intelligent clarification — detect ambiguity and ask before investigating.

When a question is generic (e.g., "pedido não libera") and has multiple
distinct possibilities in the client environment, this module groups them
into logical blocks and decides whether to ask or investigate directly.
"""
import json
import re
from collections import defaultdict


# Keywords that indicate types of problems
KEYWORDS_MAP = {
    "bloqueio": ["bloq", "lib", "trav", "liber", "aprov", "pend", "status"],
    "rateio": ["rate", "rateio", "cc ", "centro_custo", "distr"],
    "integracao": ["integr", "taura", "tms", "sfa", "argo", "commerce", "edi"],
    "fiscal": ["sintr", "sped", "reinf", "nfe", "fiscal", "icms", "pis", "cofins"],
    "aprovacao": ["aprov", "workflow", "alcad", "alçad"],
    "estoque": ["estoq", "saldo", "movimen", "requisi"],
}


def avaliar_ambiguidade(db, tabelas: list, keywords: list, campos_encontrados: list = None) -> dict:
    """Evaluate if a question is ambiguous and needs clarification.

    Args:
        db: Database connection
        tabelas: Tables identified from the question (e.g., ['SC5'])
        keywords: Keywords from the question (e.g., ['liberar', 'pedido'])
        campos_encontrados: Fields already identified (if any)

    Returns:
        {
            "ambiguo": True/False,
            "total_blocos": N,
            "blocos": [...],  # logical blocks with campos, fontes, description
            "sugestao_pergunta": "...",  # formatted clarification text
        }
    """
    result = {
        "ambiguo": False,
        "total_blocos": 0,
        "blocos": [],
        "sugestao_pergunta": "",
    }

    if not tabelas:
        return result

    # If the USER explicitly mentioned a specific campo code in their message,
    # it's not ambiguous (they know what field they're talking about)
    # campos_encontrados here are from regex on the user's message text,
    # NOT from the resolver (those get added to campos_msg later)
    if campos_encontrados and any(
        "_" in c and len(c) > 4 for c in campos_encontrados
    ):
        return result

    # Detect which type of problem based on keywords
    problema_tipo = _detect_problem_type(keywords)

    # For each table, find relevant campos and group into blocks
    all_blocks = []
    for tabela in tabelas[:3]:
        campo_keywords = _get_campo_keywords(problema_tipo, keywords)
        blocks = _find_and_group_campos(db, tabela, campo_keywords)
        for b in blocks:
            b["tabela"] = tabela
        all_blocks.extend(blocks)

    # Cross-table search: only when explicitly looking for a concept across modules
    # (e.g., "rateio" which exists in SC1, SC7, SD1)
    # Skip for focused questions where tabelas are already identified
    if problema_tipo in ("rateio",) and len(tabelas) <= 1:
        extra_tabelas = _find_tables_with_keyword(db, keywords)
        # Only add tables from the same "family" (S** standard tables)
        for tab in extra_tabelas[:5]:
            if tab not in tabelas and tab.startswith("S"):
                blocks = _find_and_group_campos(db, tab, _get_campo_keywords(problema_tipo, keywords))
                for b in blocks:
                    b["tabela"] = tab
                all_blocks.extend(blocks)

    # Consolidate: merge all "padrão" blocks into one, keep only custom blocks with fontes
    custom_blocks = [b for b in all_blocks if b.get("fontes")]
    padrao_campos = []
    for b in all_blocks:
        if not b.get("fontes") and b.get("campos"):
            padrao_campos.extend(b["campos"])

    meaningful_blocks = custom_blocks
    if padrao_campos:
        # Single consolidated padrão block
        meaningful_blocks.append({
            "nome": "Configuração padrão Protheus",
            "campos": sorted(set(padrao_campos)),
            "campos_info": {},
            "fontes": [],
            "descricao": f"{len(set(padrao_campos))} campos controlados pela rotina padrão (sem customização identificada)",
            "operacoes_count": 0,
        })

    # Decide ambiguity
    result["blocos"] = meaningful_blocks
    result["total_blocos"] = len(meaningful_blocks)
    result["ambiguo"] = len(meaningful_blocks) >= 4

    # Build clarification suggestion if ambiguous
    if result["ambiguo"]:
        result["sugestao_pergunta"] = _format_clarification(meaningful_blocks, keywords)

    return result


def _detect_problem_type(keywords: list) -> str:
    """Detect the type of problem from keywords."""
    text = " ".join(keywords).lower()
    for tipo, kws in KEYWORDS_MAP.items():
        for kw in kws:
            if kw in text:
                return tipo
    return ""


def _get_campo_keywords(problema_tipo: str, keywords: list) -> list:
    """Get field-level keywords to search for based on problem type.
    Only uses PROBLEM keywords (bloq, lib, status), not CONTEXT keywords (pedido, venda)."""
    base = KEYWORDS_MAP.get(problema_tipo, [])
    # Only add keywords that look like field/problem indicators, not generic context
    CONTEXT_NOISE = {"nao", "não", "com", "sem", "que", "para", "pode", "ser",
                     "pedido", "venda", "compra", "nota", "fiscal", "entrada", "saida",
                     "rotina", "tela", "campo", "valor", "cliente", "fornecedor",
                     "estou", "conseguindo", "fazer", "esta", "está"}
    extra = []
    for kw in keywords:
        kw_lower = kw.lower()
        if len(kw_lower) >= 3 and kw_lower not in CONTEXT_NOISE:
            extra.append(kw_lower)
    return list(set(base + extra))


def _find_and_group_campos(db, tabela: str, campo_keywords: list) -> list:
    """Find campos matching keywords and group by shared write sources."""

    # Build SQL LIKE conditions for campo name, titulo, descricao
    conditions = []
    params = []
    for kw in campo_keywords[:10]:
        kw_upper = kw.upper()
        conditions.append("(upper(campo) LIKE ? OR upper(titulo) LIKE ? OR upper(descricao) LIKE ?)")
        params.extend([f"%{kw_upper}%", f"%{kw_upper}%", f"%{kw_upper}%"])

    if not conditions:
        return []

    sql = f"SELECT campo, titulo, descricao FROM campos WHERE upper(tabela) = ? AND ({' OR '.join(conditions)})"
    campos_match = db.execute(sql, [tabela.upper()] + params).fetchall()

    if not campos_match:
        return []

    # For each campo, find fontes that write it
    campo_fontes = {}
    for campo, titulo, desc in campos_match:
        ops = db.execute(
            "SELECT DISTINCT arquivo FROM operacoes_escrita WHERE upper(tabela) = ? AND campos LIKE ?",
            (tabela.upper(), f"%{campo}%"),
        ).fetchall()
        fontes = sorted(set(r[0] for r in ops))
        campo_fontes[campo] = {"titulo": titulo or "", "descricao": desc or "", "fontes": fontes}

    # Group by shared fontes (union-find)
    fonte_to_campos = defaultdict(set)
    for campo, info in campo_fontes.items():
        for fonte in info["fontes"]:
            fonte_to_campos[fonte].add(campo)

    blocks = []
    used = set()

    # First: group campos that share fontes
    for campo in campo_fontes:
        if campo in used:
            continue
        if not campo_fontes[campo]["fontes"]:
            continue  # handle later

        block_campos = set()
        block_fontes = set()
        queue = [campo]
        while queue:
            c = queue.pop(0)
            if c in block_campos:
                continue
            block_campos.add(c)
            used.add(c)
            for f in campo_fontes.get(c, {}).get("fontes", []):
                block_fontes.add(f)
                for other_c in fonte_to_campos[f]:
                    if other_c not in block_campos:
                        queue.append(other_c)

        # Build block with enriched info
        block = _enrich_block(db, tabela, sorted(block_campos), sorted(block_fontes), campo_fontes)
        blocks.append(block)

    # Campos without fontes → "Padrão Protheus" block
    padrao_campos = [c for c in campo_fontes if c not in used and campo_fontes[c]["fontes"] == []]
    if padrao_campos:
        blocks.append({
            "nome": f"Configuração padrão Protheus",
            "campos": sorted(padrao_campos),
            "campos_info": {c: campo_fontes[c] for c in padrao_campos},
            "fontes": [],
            "descricao": "Campos controlados pela rotina padrão do Protheus (sem customização identificada)",
            "operacoes_count": 0,
        })

    return blocks


def _enrich_block(db, tabela: str, campos: list, fontes: list, campo_fontes: dict) -> dict:
    """Enrich a block with descriptions and operation counts."""
    # Count write operations for this block
    ops_count = 0
    for campo in campos:
        count = db.execute(
            "SELECT COUNT(*) FROM operacoes_escrita WHERE upper(tabela) = ? AND campos LIKE ?",
            (tabela.upper(), f"%{campo}%"),
        ).fetchone()[0]
        ops_count += count

    # Get proposito of main fonte
    descricao_parts = []
    for fonte in fontes[:3]:
        try:
            p_row = db.execute("SELECT proposito FROM propositos WHERE chave = ?", (fonte,)).fetchone()
            if p_row and p_row[0]:
                parsed = json.loads(p_row[0]) if p_row[0].startswith("{") else {}
                humano = parsed.get("humano", "")[:80] if isinstance(parsed, dict) else ""
                if humano:
                    descricao_parts.append(f"{fonte}: {humano}")
        except Exception:
            pass

    # Auto-name the block based on campos and fontes
    nome = _auto_name_block(campos, fontes, campo_fontes)

    return {
        "nome": nome,
        "campos": campos,
        "campos_info": {c: campo_fontes.get(c, {}) for c in campos},
        "fontes": fontes,
        "descricao": " | ".join(descricao_parts) if descricao_parts else f"{ops_count} operações de escrita em {len(fontes)} fontes",
        "operacoes_count": ops_count,
    }


def _auto_name_block(campos: list, fontes: list, campo_fontes: dict) -> str:
    """Generate a descriptive name for a block based on its campos and fontes."""
    # Try to name based on campo titles
    titulos = [campo_fontes.get(c, {}).get("titulo", "") for c in campos]
    titulos = [t for t in titulos if t]

    if len(campos) == 1:
        campo = campos[0]
        titulo = campo_fontes.get(campo, {}).get("titulo", "")
        return f"{titulo or campo}"

    # Check if fontes suggest a pattern
    fonte_names = [f.replace(".prw", "").replace(".PRW", "") for f in fontes[:3]]
    if fonte_names:
        return f"{', '.join(titulos[:2])} ({', '.join(fonte_names[:2])})"

    return f"{', '.join(titulos[:3])}"


def _find_tables_with_keyword(db, keywords: list) -> list:
    """Find tables that have campos matching keywords (for cross-table ambiguity)."""
    tables = set()
    for kw in keywords[:5]:
        kw_upper = kw.upper()
        if len(kw_upper) < 3:
            continue
        rows = db.execute(
            "SELECT DISTINCT tabela FROM campos WHERE upper(campo) LIKE ? OR upper(titulo) LIKE ? LIMIT 10",
            (f"%{kw_upper}%", f"%{kw_upper}%"),
        ).fetchall()
        for r in rows:
            tables.add(r[0])
    return sorted(tables)


def _format_clarification(blocks: list, keywords: list) -> str:
    """Format blocks into a clarification message for the LLM to present."""
    tabelas_envolvidas = sorted(set(b.get("tabela", "") for b in blocks if b.get("tabela")))

    parts = [f"AMBIGUIDADE DETECTADA: A pergunta pode se referir a {len(blocks)} cenários distintos."]
    if tabelas_envolvidas:
        parts.append(f"Tabelas envolvidas: {', '.join(tabelas_envolvidas)}")
    parts.append("")
    parts.append("INSTRUCAO: Apresente as opcoes abaixo ao usuario e pergunte qual se aplica ao caso dele.")
    parts.append("NAO investigue todos — espere o usuario escolher.")
    parts.append("")

    for i, block in enumerate(blocks, 1):
        campos_str = ", ".join(block["campos"][:4])
        if len(block["campos"]) > 4:
            campos_str += f" (+{len(block['campos'])-4})"

        fontes_str = ""
        if block["fontes"]:
            fontes_str = f" — Fontes: {', '.join(block['fontes'][:3])}"

        parts.append(f"{i}. **{block['nome']}** [{campos_str}]{fontes_str}")
        if block.get("descricao"):
            parts.append(f"   {block['descricao'][:120]}")

    return "\n".join(parts)
