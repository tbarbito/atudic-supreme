# -*- coding: utf-8 -*-
"""
Tools do agente GolIAs Supreme — Workspace (Engenharia Reversa).

4 novas tools vindas da integracao com ExtraiRPO:
- parse_source_code: Analisa arquivo ADVPL/TLPP
- analyze_impact: Impacto de alterar campo/tabela
- build_dependency_graph: Grafo de vinculos de um modulo
- list_vinculos: Lista relacoes campo->funcao->gatilho->PE
"""

import json
import logging
from pathlib import Path

from app.services.workspace.workspace_db import Database
from app.services.workspace.knowledge import KnowledgeService
from app.services.workspace import parser_source

logger = logging.getLogger(__name__)


def get_workspace_tools():
    """Retorna lista de tools do workspace para registro no agente."""
    return [
        {
            "name": "parse_source_code",
            "description": "Analisa um arquivo ADVPL/TLPP e extrai funcoes, tabelas referenciadas, "
                           "pontos de entrada, call graph, operacoes de escrita e campos referenciados.",
            "parameters": {
                "file_path": {"type": "string", "description": "Caminho completo do arquivo .prw/.tlpp"},
                "include_chunks": {"type": "boolean", "description": "Incluir chunks para indexacao", "default": False},
            },
            "required": ["file_path"],
            "risk": "low",
            "min_profile": "viewer",
            "handler": _handle_parse_source_code,
        },
        {
            "name": "analyze_impact",
            "description": "Analisa o impacto de alterar um campo ou tabela Protheus. "
                           "Retorna fontes afetadas, gatilhos, vinculos e operacoes de escrita.",
            "parameters": {
                "workspace_slug": {"type": "string", "description": "Slug do workspace"},
                "tabela": {"type": "string", "description": "Codigo da tabela (ex: SA1, SC5)"},
                "campo": {"type": "string", "description": "Nome do campo (ex: A1_NOME). Opcional."},
            },
            "required": ["workspace_slug", "tabela"],
            "risk": "low",
            "min_profile": "viewer",
            "handler": _handle_analyze_impact,
        },
        {
            "name": "build_dependency_graph",
            "description": "Retorna o grafo de dependencias de um modulo Protheus (vinculos entre "
                           "funcoes, tabelas, gatilhos, PEs, jobs e schedules).",
            "parameters": {
                "workspace_slug": {"type": "string", "description": "Slug do workspace"},
                "modulo": {"type": "string", "description": "Nome do modulo (ex: compras, faturamento, estoque)"},
            },
            "required": ["workspace_slug", "modulo"],
            "risk": "low",
            "min_profile": "viewer",
            "handler": _handle_build_dependency_graph,
        },
        {
            "name": "list_vinculos",
            "description": "Lista vinculos (relacionamentos) de um workspace, opcionalmente filtrados "
                           "por tipo (funcao_definida_em, fonte_le_tabela, pe_afeta_rotina, etc).",
            "parameters": {
                "workspace_slug": {"type": "string", "description": "Slug do workspace"},
                "tipo": {"type": "string", "description": "Tipo de vinculo para filtrar. Opcional."},
                "origem": {"type": "string", "description": "Filtrar por origem. Opcional."},
                "destino": {"type": "string", "description": "Filtrar por destino. Opcional."},
                "limit": {"type": "integer", "description": "Limite de resultados", "default": 50},
            },
            "required": ["workspace_slug"],
            "risk": "low",
            "min_profile": "viewer",
            "handler": _handle_list_vinculos,
        },
    ]


# ========================================================================
# HANDLERS
# ========================================================================

WORKSPACE_BASE = Path("workspace/clients")


def _get_db(slug: str) -> Database:
    """Retorna Database inicializado para o workspace."""
    db_path = WORKSPACE_BASE / slug / "workspace.db"
    if not db_path.exists():
        return None
    db = Database(db_path)
    db.initialize()
    return db


def _handle_parse_source_code(params: dict) -> dict:
    """Analisa um arquivo ADVPL/TLPP."""
    file_path = Path(params["file_path"])
    if not file_path.exists():
        return {"success": False, "error": f"Arquivo nao encontrado: {file_path}"}

    include_chunks = params.get("include_chunks", False)

    try:
        result = parser_source.parse_source(file_path, include_chunks=include_chunks)
        # Resumo para o agente (sem chunks completos para economia de tokens)
        summary = {
            "arquivo": result["arquivo"],
            "source_type": result.get("source_type", ""),
            "funcoes": result["funcoes"],
            "user_funcs": result["user_funcs"],
            "pontos_entrada": result["pontos_entrada"],
            "tabelas_ref": result["tabelas_ref"],
            "write_tables": result["write_tables"],
            "calls_u": result["calls_u"],
            "lines_of_code": result["lines_of_code"],
            "operacoes_escrita_count": len(result.get("operacoes_escrita", [])),
            "chunks_count": len(result.get("chunks", [])) if include_chunks else 0,
        }
        return {"success": True, "data": summary}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _handle_analyze_impact(params: dict) -> dict:
    """Analisa impacto de alteracao em campo/tabela."""
    slug = params["workspace_slug"]
    tabela = params["tabela"].upper()
    campo = params.get("campo", "").upper()

    db = _get_db(slug)
    if not db:
        return {"success": False, "error": f"Workspace '{slug}' nao encontrado"}

    ks = KnowledgeService(db)
    result = {"tabela": tabela, "campo": campo, "impactos": []}

    # 1. Fontes que referenciam a tabela
    fontes_leitura = db.execute(
        "SELECT arquivo, modulo FROM fontes WHERE tabelas_ref LIKE ?",
        (f'%"{tabela}"%',)
    ).fetchall()
    result["fontes_leitura"] = [{"arquivo": f[0], "modulo": f[1]} for f in fontes_leitura]

    # 2. Fontes que escrevem na tabela
    fontes_escrita = db.execute(
        "SELECT arquivo, modulo FROM fontes WHERE write_tables LIKE ?",
        (f'%"{tabela}"%',)
    ).fetchall()
    result["fontes_escrita"] = [{"arquivo": f[0], "modulo": f[1]} for f in fontes_escrita]

    # 3. Operacoes de escrita na tabela
    ops = db.execute(
        "SELECT arquivo, funcao, tipo, campos, condicao, linha FROM operacoes_escrita WHERE tabela = ?",
        (tabela,)
    ).fetchall()
    result["operacoes_escrita"] = [
        {"arquivo": o[0], "funcao": o[1], "tipo": o[2],
         "campos": json.loads(o[3]) if o[3] else [], "condicao": o[4], "linha": o[5]}
        for o in ops
    ]

    # 4. Gatilhos envolvendo a tabela ou campo
    if campo:
        gatilhos = db.execute(
            "SELECT campo_origem, campo_destino, regra, condicao FROM gatilhos "
            "WHERE campo_origem = ? OR campo_destino = ?",
            (campo, campo)
        ).fetchall()
    else:
        prefix = tabela[1:] + "_"
        gatilhos = db.execute(
            "SELECT campo_origem, campo_destino, regra, condicao FROM gatilhos "
            "WHERE campo_origem LIKE ? OR campo_destino LIKE ?",
            (prefix + "%", prefix + "%")
        ).fetchall()
    result["gatilhos"] = [
        {"campo_origem": g[0], "campo_destino": g[1], "regra": g[2], "condicao": g[3]}
        for g in gatilhos
    ]

    # 5. Vinculos relacionados
    vinculos = db.execute(
        "SELECT tipo, origem, destino, contexto, peso FROM vinculos "
        "WHERE origem LIKE ? OR destino LIKE ? ORDER BY peso DESC LIMIT 30",
        (f"%{campo or tabela}%", f"%{campo or tabela}%")
    ).fetchall()
    result["vinculos"] = [
        {"tipo": v[0], "origem": v[1], "destino": v[2], "contexto": v[3], "peso": v[4]}
        for v in vinculos
    ]

    # Resumo
    result["resumo"] = {
        "fontes_leitura": len(fontes_leitura),
        "fontes_escrita": len(fontes_escrita),
        "operacoes_escrita": len(ops),
        "gatilhos": len(gatilhos),
        "vinculos": len(vinculos),
        "risco": "ALTO" if len(fontes_escrita) > 5 or len(gatilhos) > 3 else
                 "MEDIO" if len(fontes_escrita) > 2 or len(gatilhos) > 0 else "BAIXO",
    }

    return {"success": True, "data": result}


def _handle_build_dependency_graph(params: dict) -> dict:
    """Retorna grafo de dependencias de um modulo."""
    slug = params["workspace_slug"]
    modulo = params["modulo"]

    db = _get_db(slug)
    if not db:
        return {"success": False, "error": f"Workspace '{slug}' nao encontrado"}

    ks = KnowledgeService(db)
    vinculos = ks.get_vinculos_for_module(modulo)

    # Agrupar por tipo
    by_type = {}
    for v in vinculos:
        tipo = v["tipo"]
        by_type.setdefault(tipo, []).append(v)

    # Nodes e edges para visualizacao
    nodes = set()
    edges = []
    for v in vinculos:
        nodes.add(f"{v['origem_tipo']}:{v['origem']}")
        nodes.add(f"{v['destino_tipo']}:{v['destino']}")
        edges.append({
            "source": f"{v['origem_tipo']}:{v['origem']}",
            "target": f"{v['destino_tipo']}:{v['destino']}",
            "type": v["tipo"],
            "weight": v["peso"],
        })

    return {
        "success": True,
        "data": {
            "modulo": modulo,
            "total_vinculos": len(vinculos),
            "por_tipo": {k: len(v) for k, v in by_type.items()},
            "nodes_count": len(nodes),
            "edges_count": len(edges),
            "vinculos": vinculos[:100],  # Limitar para economia de tokens
        }
    }


def _handle_list_vinculos(params: dict) -> dict:
    """Lista vinculos com filtros."""
    slug = params["workspace_slug"]
    tipo = params.get("tipo")
    origem = params.get("origem")
    destino = params.get("destino")
    limit = params.get("limit", 50)

    db = _get_db(slug)
    if not db:
        return {"success": False, "error": f"Workspace '{slug}' nao encontrado"}

    # Build query
    conditions = []
    query_params = []

    if tipo:
        conditions.append("tipo = ?")
        query_params.append(tipo)
    if origem:
        conditions.append("(origem LIKE ? OR origem = ?)")
        query_params.extend([f"%{origem}%", origem])
    if destino:
        conditions.append("(destino LIKE ? OR destino = ?)")
        query_params.extend([f"%{destino}%", destino])

    where = " AND ".join(conditions) if conditions else "1=1"
    query_params.append(limit)

    rows = db.execute(
        f"SELECT tipo, origem_tipo, origem, destino_tipo, destino, modulo, contexto, peso "
        f"FROM vinculos WHERE {where} ORDER BY peso DESC LIMIT ?",
        tuple(query_params)
    ).fetchall()

    vinculos = [
        {"tipo": r[0], "origem_tipo": r[1], "origem": r[2], "destino_tipo": r[3],
         "destino": r[4], "modulo": r[5], "contexto": r[6], "peso": r[7]}
        for r in rows
    ]

    # Stats
    total = db.execute("SELECT COUNT(*) FROM vinculos").fetchone()[0]
    types = db.execute("SELECT tipo, COUNT(*) FROM vinculos GROUP BY tipo").fetchall()

    return {
        "success": True,
        "data": {
            "vinculos": vinculos,
            "filtered_count": len(vinculos),
            "total_count": total,
            "tipos_disponiveis": {r[0]: r[1] for r in types},
        }
    }
