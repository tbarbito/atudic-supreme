# -*- coding: utf-8 -*-
"""
Rotas Flask — Workspace (Engenharia Reversa Protheus)

Endpoints para gerenciar workspaces, ingestao de CSVs/fontes,
explorar dicionario e consultar vinculos.
"""

import logging
from pathlib import Path
from flask import Blueprint, request, jsonify

from app.services.workspace.workspace_populator import WorkspacePopulator
from app.services.workspace.workspace_db import Database
from app.services.workspace.knowledge import KnowledgeService

logger = logging.getLogger(__name__)

workspace_bp = Blueprint("workspace", __name__)

# Diretorio base para workspaces
WORKSPACE_BASE = Path("workspace/clients")


def _get_workspace_path(slug: str) -> Path:
    """Retorna path do workspace por slug."""
    return WORKSPACE_BASE / slug


def _get_db(slug: str) -> Database:
    """Retorna Database inicializado para o workspace."""
    ws_path = _get_workspace_path(slug)
    db = Database(ws_path / "workspace.db")
    db.initialize()
    return db


# ========================================================================
# WORKSPACE CRUD
# ========================================================================

@workspace_bp.route("/workspaces", methods=["GET"])
def list_workspaces():
    """Lista workspaces existentes."""
    if not WORKSPACE_BASE.exists():
        return jsonify([])

    workspaces = []
    for d in sorted(WORKSPACE_BASE.iterdir()):
        if d.is_dir() and (d / "workspace.db").exists():
            pop = WorkspacePopulator(d)
            pop.initialize()
            stats = pop.get_stats()
            pop.close()
            workspaces.append({
                "slug": d.name,
                "path": str(d),
                "stats": stats,
            })
    return jsonify(workspaces)


@workspace_bp.route("/workspaces/<slug>/stats", methods=["GET"])
def workspace_stats(slug):
    """Retorna estatisticas do workspace."""
    ws_path = _get_workspace_path(slug)
    if not (ws_path / "workspace.db").exists():
        return jsonify({"error": "Workspace nao encontrado"}), 404

    pop = WorkspacePopulator(ws_path)
    pop.initialize()
    stats = pop.get_stats()
    pop.close()
    return jsonify(stats)


# ========================================================================
# INGESTAO
# ========================================================================

@workspace_bp.route("/workspaces/<slug>/ingest/csv", methods=["POST"])
def ingest_csv(slug):
    """Ingere CSVs SX no workspace.

    Body JSON: {"csv_dir": "/path/to/csvs"}
    """
    data = request.get_json()
    csv_dir = Path(data.get("csv_dir", ""))

    if not csv_dir.exists():
        return jsonify({"error": f"Diretorio nao encontrado: {csv_dir}"}), 400

    ws_path = _get_workspace_path(slug)
    pop = WorkspacePopulator(ws_path)
    pop.initialize()

    try:
        stats = pop.populate_from_csv(csv_dir)
        return jsonify({"success": True, "stats": stats})
    except Exception as e:
        logger.exception(f"Erro na ingestao CSV: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        pop.close()


@workspace_bp.route("/workspaces/<slug>/ingest/fontes", methods=["POST"])
def ingest_fontes(slug):
    """Parseia fontes ADVPL/TLPP e popula workspace.

    Body JSON: {"fontes_dir": "/path/to/fontes", "mapa_modulos": "/path/to/mapa.json"}
    """
    data = request.get_json()
    fontes_dir = Path(data.get("fontes_dir", ""))
    mapa_path = data.get("mapa_modulos")

    if not fontes_dir.exists():
        return jsonify({"error": f"Diretorio nao encontrado: {fontes_dir}"}), 400

    ws_path = _get_workspace_path(slug)
    pop = WorkspacePopulator(ws_path)
    pop.initialize()

    try:
        mapa = Path(mapa_path) if mapa_path else None
        stats = pop.parse_fontes(fontes_dir, mapa)
        return jsonify({"success": True, "stats": stats})
    except Exception as e:
        logger.exception(f"Erro no parse de fontes: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        pop.close()


@workspace_bp.route("/workspaces/<slug>/ingest/live", methods=["POST"])
def ingest_live(slug):
    """Popula workspace lendo SX* diretamente do banco Protheus.

    Body JSON: {"connection_id": 1, "company_code": "01", "environment_id": 1}
    """
    data = request.get_json()
    connection_id = data.get("connection_id")
    company_code = data.get("company_code", "01")
    environment_id = data.get("environment_id")

    if not connection_id:
        return jsonify({"error": "connection_id e obrigatorio"}), 400

    ws_path = _get_workspace_path(slug)
    pop = WorkspacePopulator(ws_path)
    pop.initialize()

    try:
        stats = pop.populate_from_db(connection_id, company_code, environment_id)
        return jsonify({"success": True, "stats": stats})
    except Exception as e:
        logger.exception(f"Erro na ingestao live: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        pop.close()


@workspace_bp.route("/workspaces/<slug>/ingest/hybrid", methods=["POST"])
def ingest_hybrid(slug):
    """Modo hibrido: dicionario do DB + fontes do filesystem.

    Body JSON: {"connection_id": 1, "company_code": "01", "fontes_dir": "/path", "environment_id": 1}
    """
    data = request.get_json()
    connection_id = data.get("connection_id")
    company_code = data.get("company_code", "01")
    fontes_dir = Path(data.get("fontes_dir", ""))
    environment_id = data.get("environment_id")
    mapa_path = data.get("mapa_modulos")

    if not connection_id:
        return jsonify({"error": "connection_id e obrigatorio"}), 400
    if not fontes_dir.exists():
        return jsonify({"error": f"Diretorio nao encontrado: {fontes_dir}"}), 400

    ws_path = _get_workspace_path(slug)
    pop = WorkspacePopulator(ws_path)
    pop.initialize()

    try:
        mapa = Path(mapa_path) if mapa_path else None
        stats = pop.populate_hybrid(connection_id, company_code, fontes_dir, mapa, environment_id)
        return jsonify({"success": True, "stats": stats})
    except Exception as e:
        logger.exception(f"Erro na ingestao hibrida: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        pop.close()


@workspace_bp.route("/connections", methods=["GET"])
def list_connections():
    """Lista conexoes de banco disponiveis para modo live."""
    try:
        from app.database.core import get_db_connection, release_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, name, driver, host, port, database_name, environment_id "
            "FROM database_connections WHERE is_active = TRUE ORDER BY name"
        )
        rows = cursor.fetchall()
        release_db_connection(conn)
        return jsonify([dict(r) for r in rows])
    except Exception as e:
        return jsonify([])


# ========================================================================
# EXPLORER — Navegacao no dicionario
# ========================================================================

@workspace_bp.route("/workspaces/<slug>/explorer/tabelas", methods=["GET"])
def explorer_tabelas(slug):
    """Lista todas as tabelas do workspace."""
    db = _get_db(slug)
    rows = db.execute(
        "SELECT codigo, nome, modo, custom FROM tabelas ORDER BY codigo"
    ).fetchall()
    return jsonify([
        {"codigo": r[0], "nome": r[1], "modo": r[2], "custom": bool(r[3])}
        for r in rows
    ])


@workspace_bp.route("/workspaces/<slug>/explorer/tabela/<codigo>", methods=["GET"])
def explorer_tabela_detail(slug, codigo):
    """Retorna informacoes completas de uma tabela (campos, indices, gatilhos, relacoes)."""
    db = _get_db(slug)
    ks = KnowledgeService(db)
    info = ks.get_table_info(codigo.upper())
    if not info:
        return jsonify({"error": "Tabela nao encontrada"}), 404
    return jsonify(info)


@workspace_bp.route("/workspaces/<slug>/explorer/fontes", methods=["GET"])
def explorer_fontes(slug):
    """Lista fontes parseados no workspace."""
    db = _get_db(slug)
    modulo = request.args.get("modulo")

    if modulo:
        rows = db.execute(
            "SELECT arquivo, tipo, modulo, lines_of_code FROM fontes WHERE modulo = ? ORDER BY arquivo",
            (modulo,)
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT arquivo, tipo, modulo, lines_of_code FROM fontes ORDER BY arquivo"
        ).fetchall()

    return jsonify([
        {"arquivo": r[0], "tipo": r[1], "modulo": r[2], "lines_of_code": r[3]}
        for r in rows
    ])


@workspace_bp.route("/workspaces/<slug>/explorer/vinculos", methods=["GET"])
def explorer_vinculos(slug):
    """Lista vinculos do workspace, opcionalmente filtrados por modulo."""
    db = _get_db(slug)
    ks = KnowledgeService(db)
    modulo = request.args.get("modulo", "")

    if modulo:
        vinculos = ks.get_vinculos_for_module(modulo)
    else:
        rows = db.execute(
            "SELECT tipo, COUNT(*) FROM vinculos GROUP BY tipo ORDER BY COUNT(*) DESC"
        ).fetchall()
        vinculos = [{"tipo": r[0], "count": r[1]} for r in rows]

    return jsonify(vinculos)


@workspace_bp.route("/workspaces/<slug>/explorer/summary", methods=["GET"])
def explorer_summary(slug):
    """Retorna resumo de customizacoes do workspace."""
    db = _get_db(slug)
    ks = KnowledgeService(db)
    return jsonify(ks.get_custom_summary())


# ========================================================================
# CONTEXTO PARA AGENTE IA
# ========================================================================

@workspace_bp.route("/workspaces/<slug>/context/module/<modulo>", methods=["GET"])
def context_module(slug, modulo):
    """Gera contexto estruturado (markdown) de um modulo para o agente IA."""
    db = _get_db(slug)
    ks = KnowledgeService(db)
    context = ks.build_context_for_module(modulo)
    return jsonify({"modulo": modulo, "context": context, "chars": len(context)})


@workspace_bp.route("/workspaces/<slug>/context/table/<tabela>", methods=["GET"])
def context_table(slug, tabela):
    """Gera analise profunda de uma tabela para o agente IA."""
    db = _get_db(slug)
    ks = KnowledgeService(db)
    analysis = ks.build_deep_field_analysis(tabela.upper())
    if not analysis:
        return jsonify({"error": "Tabela nao encontrada"}), 404
    return jsonify({"tabela": tabela.upper(), "analysis": analysis, "chars": len(analysis)})


# ========================================================================
# DOCUMENTACAO IA
# ========================================================================

@workspace_bp.route("/workspaces/<slug>/docs/modules", methods=["GET"])
def docs_modules(slug):
    """Lista modulos disponiveis para geracao de docs."""
    db = _get_db(slug)
    from app.services.workspace.doc_pipeline import DocPipeline
    pipeline = DocPipeline(db)
    return jsonify(pipeline.get_available_modules())


@workspace_bp.route("/workspaces/<slug>/docs/generate/<modulo>", methods=["POST"])
def docs_generate(slug, modulo):
    """Gera documentacao para um modulo (sem LLM = apenas contexto)."""
    db = _get_db(slug)
    from app.services.workspace.doc_pipeline import DocPipeline
    pipeline = DocPipeline(db, llm_provider=None)  # TODO: injetar LLM provider

    try:
        result = pipeline.generate_for_module(modulo)
        return jsonify({
            "success": True,
            "modulo": modulo,
            "context_chars": result.get("context_chars"),
            "elapsed_seconds": result.get("elapsed_seconds"),
            "has_llm": False,
        })
    except Exception as e:
        logger.exception(f"Erro ao gerar docs: {e}")
        return jsonify({"error": str(e)}), 500


# ========================================================================
# EXPORT
# ========================================================================

@workspace_bp.route("/workspaces/<slug>/export/campos", methods=["GET"])
def export_campos(slug):
    """Exporta campos customizados em CSV."""
    db = _get_db(slug)
    from app.services.workspace.exporter import WorkspaceExporter
    exporter = WorkspaceExporter(db)
    tabela = request.args.get("tabela")
    csv_data = exporter.export_campos_custom_csv(tabela)
    return csv_data, 200, {"Content-Type": "text/csv; charset=utf-8",
                           "Content-Disposition": "attachment; filename=campos_custom.csv"}


@workspace_bp.route("/workspaces/<slug>/export/indices", methods=["GET"])
def export_indices(slug):
    """Exporta indices customizados em CSV."""
    db = _get_db(slug)
    from app.services.workspace.exporter import WorkspaceExporter
    exporter = WorkspaceExporter(db)
    tabela = request.args.get("tabela")
    csv_data = exporter.export_indices_custom_csv(tabela)
    return csv_data, 200, {"Content-Type": "text/csv; charset=utf-8",
                           "Content-Disposition": "attachment; filename=indices_custom.csv"}


@workspace_bp.route("/workspaces/<slug>/export/gatilhos", methods=["GET"])
def export_gatilhos(slug):
    """Exporta gatilhos customizados em CSV."""
    db = _get_db(slug)
    from app.services.workspace.exporter import WorkspaceExporter
    exporter = WorkspaceExporter(db)
    csv_data = exporter.export_gatilhos_custom_csv()
    return csv_data, 200, {"Content-Type": "text/csv; charset=utf-8",
                           "Content-Disposition": "attachment; filename=gatilhos_custom.csv"}


@workspace_bp.route("/workspaces/<slug>/export/atudic", methods=["GET"])
def export_atudic(slug):
    """Exporta em formato AtuDic JSON."""
    db = _get_db(slug)
    from app.services.workspace.exporter import WorkspaceExporter
    exporter = WorkspaceExporter(db)
    tabela = request.args.get("tabela")
    data = exporter.export_atudic_json(tabela)
    return jsonify(data)


@workspace_bp.route("/workspaces/<slug>/export/diff", methods=["GET"])
def export_diff(slug):
    """Exporta diff padrao x cliente em CSV."""
    db = _get_db(slug)
    from app.services.workspace.exporter import WorkspaceExporter
    exporter = WorkspaceExporter(db)
    tipo_sx = request.args.get("tipo_sx")
    csv_data = exporter.export_diff_csv(tipo_sx)
    return csv_data, 200, {"Content-Type": "text/csv; charset=utf-8",
                           "Content-Disposition": "attachment; filename=diff.csv"}
