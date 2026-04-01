"""Generic graph traversal over the vinculos table.

Given any node (fonte, funcao, tabela, campo, pe, job, schedule, parametro),
navigates the relationship graph up to N hops and returns a structured context
with all connected entities.

Usage:
    from app.services.workspace.graph_traversal import traverse_graph
    ctx = traverse_graph(db, "A100DEL.prw", "fonte", max_depth=2)
    ctx = traverse_graph(db, "MGFTAE08", "funcao", max_depth=2)
    ctx = traverse_graph(db, "SF1", "tabela", max_depth=1)
"""
import json
from collections import defaultdict


def traverse_graph(db, node: str, node_type: str, max_depth: int = 2) -> dict:
    """Traverse vinculos graph starting from any node.

    Args:
        db: Database connection (sqlite3)
        node: Node identifier (e.g., "A100DEL.prw", "MGFTAE08", "SF1")
        node_type: Node type (fonte, funcao, tabela, campo, pe, job, schedule, parametro, rotina)
        max_depth: How many hops to follow (1=direct, 2=direct+one level, etc.)

    Returns:
        dict with:
          - nodes: {(type, name): {details}} — all visited nodes
          - edges: [(from_type, from_name, to_type, to_name, edge_type, context, weight)]
          - by_type: grouped view — tables, fontes, funcoes, parametros, campos, etc.
          - summary: pre-built text sections for LLM consumption
    """
    visited_nodes = {}   # (type, name) -> {first_seen_depth, ...}
    edges = []           # all edges found
    frontier = [(node_type, node, 0)]  # BFS queue: (type, name, depth)
    seen = set()         # avoid re-visiting

    # Normalize: some nodes can be searched as both "fonte" and "funcao"
    # e.g., A100DEL.prw (fonte) contains function A100DEL (funcao)
    seed_variants = _node_variants(node, node_type)

    while frontier:
        ntype, nname, depth = frontier.pop(0)

        key = (ntype, nname)
        if key in seen:
            continue
        seen.add(key)

        if key not in visited_nodes:
            visited_nodes[key] = {"depth": depth}

        if depth >= max_depth:
            continue

        # Get all variants for this node to search in vinculos
        variants = _node_variants(nname, ntype)

        # Outgoing edges (this node is the origin)
        for row in _query_edges_out(db, variants):
            tipo, otipo, orig, dtipo, dest, mod, ctx, peso = row
            edge = (otipo, orig, dtipo, dest, tipo, ctx, peso)
            edges.append(edge)
            dest_key = (dtipo, dest)
            if dest_key not in visited_nodes:
                visited_nodes[dest_key] = {"depth": depth + 1}
            if dest_key not in seen:
                frontier.append((dtipo, dest, depth + 1))

        # Incoming edges (this node is the destination)
        for row in _query_edges_in(db, variants):
            tipo, otipo, orig, dtipo, dest, mod, ctx, peso = row
            edge = (otipo, orig, dtipo, dest, tipo, ctx, peso)
            edges.append(edge)
            orig_key = (otipo, orig)
            if orig_key not in visited_nodes:
                visited_nodes[orig_key] = {"depth": depth + 1}
            if orig_key not in seen:
                frontier.append((otipo, orig, depth + 1))

    # Deduplicate edges
    unique_edges = list({(e[0], e[1], e[2], e[3], e[4]): e for e in edges}.values())

    # Group by type
    by_type = _group_by_type(visited_nodes, unique_edges)

    # Build summary sections for LLM
    summary = _build_summary(node, node_type, visited_nodes, unique_edges, by_type, db)

    return {
        "root": {"type": node_type, "name": node},
        "nodes": visited_nodes,
        "edges": unique_edges,
        "by_type": by_type,
        "summary": summary,
    }


def _node_variants(name: str, ntype: str) -> list[str]:
    """Generate search variants for a node name."""
    variants = [name]
    if ntype == "fonte":
        # A fonte "A100DEL.prw" also has function "A100DEL"
        base = name.replace(".prw", "").replace(".PRW", "").replace(".tlpp", "").replace(".TLPP", "")
        variants.append(base)
        variants.append(name.upper())
        variants.append(name.lower())
    elif ntype == "funcao":
        # A function "MGFTAE08" might be in fonte "MGFTAE08.prw" or "MGFTAE08.PRW"
        variants.append(name + ".prw")
        variants.append(name + ".PRW")
    return list(set(variants))


def _query_edges_out(db, variants: list[str]):
    """Query outgoing edges for all name variants."""
    if not variants:
        return []
    placeholders = ",".join(["?"] * len(variants))
    return db.execute(
        f"SELECT tipo, origem_tipo, origem, destino_tipo, destino, modulo, contexto, peso "
        f"FROM vinculos WHERE origem IN ({placeholders})",
        variants,
    ).fetchall()


def _query_edges_in(db, variants: list[str]):
    """Query incoming edges for all name variants."""
    if not variants:
        return []
    placeholders = ",".join(["?"] * len(variants))
    return db.execute(
        f"SELECT tipo, origem_tipo, origem, destino_tipo, destino, modulo, contexto, peso "
        f"FROM vinculos WHERE destino IN ({placeholders})",
        variants,
    ).fetchall()


def _group_by_type(visited_nodes: dict, edges: list) -> dict:
    """Group nodes and edges by entity type."""
    groups = defaultdict(set)
    for (ntype, nname), info in visited_nodes.items():
        groups[ntype].add(nname)

    # Also extract from edges
    edge_groups = defaultdict(list)
    for e in edges:
        edge_groups[e[4]].append(e)  # group by edge type

    return {
        "fontes": sorted(groups.get("fonte", set())),
        "funcoes": sorted(groups.get("funcao", set())),
        "tabelas": sorted(groups.get("tabela", set())),
        "campos": sorted(groups.get("campo", set())),
        "parametros": sorted(groups.get("parametro", set())),
        "rotinas": sorted(groups.get("rotina", set())),
        "pes": sorted(groups.get("pe", set())),
        "jobs": sorted(groups.get("job", set())),
        "schedules": sorted(groups.get("schedule", set())),
        "modulos": sorted(groups.get("modulo", set())),
        "gatilhos": sorted(groups.get("gatilho", set())),
        "edges_by_type": {k: len(v) for k, v in edge_groups.items()},
    }


def _build_summary(root_name, root_type, nodes, edges, by_type, db) -> dict:
    """Build pre-formatted text sections ready for LLM consumption."""
    sections = {}

    # PE info
    pe_edges = [e for e in edges if e[4] == "pe_afeta_rotina"]
    if pe_edges:
        parts = []
        for e in pe_edges:
            parts.append(f"PE {e[1]} intercepta rotina padrao {e[3]} ({e[5][:80]})")
        sections["pontos_entrada"] = "\n".join(parts)

    # Call chain: who calls root, who root calls
    calls_out = [e for e in edges if e[4] in ("funcao_chama_funcao", "fonte_chama_funcao") and _matches(e[1], root_name)]
    calls_in = [e for e in edges if e[4] in ("funcao_chama_funcao", "fonte_chama_funcao") and _matches(e[3], root_name)]
    if calls_out:
        parts = [f"-> {e[3]} (via {e[4]})" for e in calls_out]
        sections["chama"] = "\n".join(parts)
    if calls_in:
        parts = [f"<- [{e[0]}] {e[1]} (via {e[4]})" for e in calls_in]
        sections["chamado_por"] = "\n".join(parts)

    # Tables
    tab_read = set()
    tab_write = set()
    for e in edges:
        if e[4] == "fonte_le_tabela":
            tab_read.add(e[3])
        elif e[4] == "fonte_escreve_tabela":
            tab_write.add(e[3])
        elif e[4] == "funcao_referencia_tabela":
            tab_read.add(e[3])
        elif e[4] == "operacao_escrita_tabela":
            tab_write.add(e[3])
    if tab_read or tab_write:
        parts = []
        if tab_read:
            parts.append(f"Leitura: {', '.join(sorted(tab_read))}")
        if tab_write:
            parts.append(f"Escrita: {', '.join(sorted(tab_write))}")
        sections["tabelas"] = "\n".join(parts)

    # Parameters
    if by_type["parametros"]:
        # Enrich with actual values from DB
        param_details = []
        for param in by_type["parametros"]:
            try:
                row = db.execute(
                    "SELECT variavel, descricao, conteudo, tipo FROM parametros WHERE variavel = ?",
                    (param,)
                ).fetchone()
                if row:
                    param_details.append(f"{row[0]}: {row[2] or '(vazio)'} — {row[1] or ''}")
                else:
                    param_details.append(param)
            except Exception:
                param_details.append(param)
        sections["parametros"] = "\n".join(param_details)

    # Fields
    if by_type["campos"]:
        sections["campos"] = ", ".join(by_type["campos"][:30])
        if len(by_type["campos"]) > 30:
            sections["campos"] += f" (+{len(by_type['campos']) - 30} mais)"

    # Jobs/Schedules
    job_edges = [e for e in edges if e[4] in ("job_executa_funcao", "schedule_executa_funcao")]
    if job_edges:
        parts = [f"{e[4].replace('_', ' ')}: {e[1]} -> {e[3]} ({e[5][:40]})" for e in job_edges]
        sections["jobs_schedules"] = "\n".join(parts)

    # Triggers
    trigger_edges = [e for e in edges if e[4] == "gatilho_executa_funcao"]
    if trigger_edges:
        parts = [f"Gatilho {e[1]} executa {e[3]}" for e in trigger_edges]
        sections["gatilhos"] = "\n".join(parts)

    # Field validations
    valid_edges = [e for e in edges if e[4] == "campo_valida_funcao"]
    if valid_edges:
        parts = [f"Campo {e[1]} valida com {e[3]} ({e[5]})" for e in valid_edges]
        sections["validacoes_campo"] = "\n".join(parts)

    # Write operations detail
    write_ops = [e for e in edges if e[4] == "operacao_escrita_tabela"]
    if write_ops:
        parts = [f"{e[1]} -> {e[3]} ({e[5][:60]})" for e in write_ops]
        sections["operacoes_escrita"] = "\n".join(parts)

    # Related fontes
    if by_type["fontes"]:
        sections["fontes_relacionados"] = ", ".join(by_type["fontes"][:20])

    return sections


def _matches(name: str, root: str) -> bool:
    """Check if a name matches the root node (case-insensitive, with/without extension)."""
    root_base = root.replace(".prw", "").replace(".PRW", "")
    name_base = name.replace(".prw", "").replace(".PRW", "")
    return name_base.upper() == root_base.upper()


def format_context_for_llm(traversal_result: dict) -> str:
    """Format the traversal result into a single text block for LLM consumption."""
    root = traversal_result["root"]
    summary = traversal_result["summary"]
    by_type = traversal_result["by_type"]

    parts = [f"CONTEXTO DO GRAFO para [{root['type']}] {root['name']}:"]
    parts.append(f"Nos visitados: {len(traversal_result['nodes'])} | Arestas: {len(traversal_result['edges'])}")
    parts.append(f"Tipos de aresta: {by_type['edges_by_type']}")
    parts.append("")

    section_titles = {
        "pontos_entrada": "PONTOS DE ENTRADA",
        "chama": "FUNCOES QUE ESTE NO CHAMA",
        "chamado_por": "QUEM CHAMA ESTE NO",
        "tabelas": "TABELAS ENVOLVIDAS",
        "parametros": "PARAMETROS (com valores do ambiente)",
        "campos": "CAMPOS REFERENCIADOS",
        "jobs_schedules": "JOBS E SCHEDULES",
        "gatilhos": "GATILHOS",
        "validacoes_campo": "VALIDACOES DE CAMPO",
        "operacoes_escrita": "OPERACOES DE ESCRITA",
        "fontes_relacionados": "FONTES RELACIONADOS",
    }

    for key, title in section_titles.items():
        if key in summary:
            parts.append(f"### {title}")
            parts.append(summary[key])
            parts.append("")

    return "\n".join(parts)
