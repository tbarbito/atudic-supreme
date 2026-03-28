# -*- coding: utf-8 -*-
"""
Tools do agente GolIAs Supreme — Workspace (Engenharia Reversa).

6 tools vindas da integracao com ExtraiRPO:
- parse_source_code: Analisa arquivo ADVPL/TLPP
- analyze_impact: Impacto de alterar campo/tabela
- build_dependency_graph: Grafo de vinculos de um modulo
- list_vinculos: Lista relacoes campo->funcao->gatilho->PE
- processos_cliente: Lista processos de negocio detectados
- registrar_processo: Registra ou enriquece processo de negocio
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
        {
            "name": "processos_cliente",
            "description": "Lista processos de negocio detectados no ambiente do cliente. "
                           "Opcionalmente filtra por tabelas envolvidas.",
            "parameters": {
                "workspace_slug": {"type": "string", "description": "Slug do workspace"},
                "tabelas": {"type": "string", "description": "Tabelas para filtrar (separadas por virgula). Opcional."},
            },
            "required": ["workspace_slug"],
            "risk": "low",
            "min_profile": "viewer",
            "handler": _handle_processos_cliente,
        },
        {
            "name": "registrar_processo",
            "description": "Registra ou enriquece um processo de negocio do cliente. "
                           "Se processo similar existe, enriquece com novas informacoes.",
            "parameters": {
                "workspace_slug": {"type": "string", "description": "Slug do workspace"},
                "nome": {"type": "string", "description": "Nome do processo"},
                "tipo": {"type": "string", "description": "Tipo: workflow|integracao|logistica|fiscal|automacao|qualidade|outro"},
                "descricao": {"type": "string", "description": "Descricao do processo"},
                "tabelas": {"type": "string", "description": "Tabelas envolvidas (separadas por virgula). Opcional."},
                "criticidade": {"type": "string", "description": "Criticidade: alta|media|baixa", "default": "media"},
            },
            "required": ["workspace_slug", "nome", "tipo", "descricao"],
            "risk": "low",
            "min_profile": "viewer",
            "handler": _handle_registrar_processo,
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


def _safe_json(val):
    """Parse JSON seguro, retorna lista vazia em caso de erro."""
    if not val:
        return []
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return []


def _handle_processos_cliente(params: dict) -> dict:
    """Lista processos de negocio detectados no workspace."""
    slug = params["workspace_slug"]
    tabelas_str = params.get("tabelas", "")
    tabelas = [t.strip().upper() for t in tabelas_str.split(",") if t.strip()] if tabelas_str else None

    db = _get_db(slug)
    if not db:
        return {"success": False, "error": f"Workspace '{slug}' nao encontrado"}

    try:
        count = db.execute("SELECT COUNT(*) FROM processos_detectados").fetchone()[0]
    except Exception:
        return {"success": True, "data": {"total": 0, "processos": [], "status": "tabela_nao_existe"}}

    if count == 0:
        return {"success": True, "data": {"total": 0, "processos": [], "status": "sem_processos"}}

    rows = db.execute(
        "SELECT id, nome, tipo, descricao, criticidade, tabelas, score, fluxo_mermaid "
        "FROM processos_detectados ORDER BY score DESC"
    ).fetchall()

    processos = []
    for r in rows:
        tabs = _safe_json(r[5])
        if tabelas:
            tabs_upper = {t.upper() for t in tabs}
            if not tabs_upper.intersection(set(tabelas)):
                continue
        processos.append({
            "id": r[0], "nome": r[1], "tipo": r[2], "descricao": r[3],
            "criticidade": r[4], "tabelas": tabs, "score": r[6],
            "fluxo_mermaid": r[7],
        })

    return {"success": True, "data": {"total": len(processos), "processos": processos, "status": "ok"}}


def _handle_registrar_processo(params: dict) -> dict:
    """Registra ou enriquece processo de negocio do cliente."""
    slug = params["workspace_slug"]
    nome = params["nome"]
    tipo = params["tipo"]
    descricao = params["descricao"]
    tabelas_str = params.get("tabelas", "")
    tabelas = [t.strip().upper() for t in tabelas_str.split(",") if t.strip()] if tabelas_str else []
    criticidade = params.get("criticidade", "media")

    db = _get_db(slug)
    if not db:
        return {"success": False, "error": f"Workspace '{slug}' nao encontrado"}

    # Stage 1: Busca por texto para encontrar processo similar
    termos = nome.lower().split()
    candidatos = []
    for termo in termos:
        if len(termo) < 3:
            continue
        try:
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
        except Exception:
            pass

    # Stage 2: Match por substring
    best_match = None
    if candidatos:
        nome_lower = nome.lower().strip()
        for c in candidatos:
            c_nome_lower = c["nome"].lower().strip()
            if c_nome_lower == nome_lower or nome_lower in c_nome_lower or c_nome_lower in nome_lower:
                best_match = c
                break

    if best_match:
        # Enriquecer processo existente
        existing_tabs = set(best_match["tabelas"])
        new_tabs = existing_tabs | set(tabelas)
        new_desc = best_match["descricao"]
        if descricao and descricao not in new_desc:
            new_desc = f"{new_desc}\n{descricao}".strip()

        db.execute(
            "UPDATE processos_detectados SET tabelas=?, descricao=?, updated_at=datetime('now') WHERE id=?",
            (json.dumps(list(new_tabs)), new_desc, best_match["id"]),
        )
        db.commit()

        return {
            "success": True,
            "data": {
                "acao": "enriquecido",
                "processo": {**best_match, "tabelas": list(new_tabs), "descricao": new_desc},
            },
        }
    else:
        # Criar novo processo
        db.execute(
            "INSERT INTO processos_detectados (nome, tipo, descricao, criticidade, tabelas, metodo, score) "
            "VALUES (?, ?, ?, ?, ?, 'manual', 0.5)",
            (nome, tipo, descricao, criticidade, json.dumps(tabelas)),
        )
        db.commit()
        new_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

        return {
            "success": True,
            "data": {
                "acao": "criado",
                "processo": {
                    "id": new_id, "nome": nome, "tipo": tipo, "descricao": descricao,
                    "criticidade": criticidade, "tabelas": tabelas, "score": 0.5,
                },
            },
        }
