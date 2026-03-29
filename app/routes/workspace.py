# -*- coding: utf-8 -*-
"""
Rotas Flask — Workspace (Engenharia Reversa Protheus)

Endpoints para gerenciar workspaces, ingestao de CSVs/fontes,
explorar dicionario e consultar vinculos.
"""

import json
import logging
import re
from pathlib import Path
from flask import Blueprint, request, jsonify, Response, stream_with_context

from app.services.workspace.workspace_populator import WorkspacePopulator
from app.services.workspace.workspace_db import Database
from app.services.workspace.knowledge import KnowledgeService

logger = logging.getLogger(__name__)

workspace_bp = Blueprint("workspace", __name__)


def _get_llm_provider():
    """Retorna LLMProvider via AgentChatEngine singleton."""
    from app.services.agent_chat import get_chat_engine
    engine = get_chat_engine()
    if not engine._llm_provider:
        raise RuntimeError("Nenhum LLM provider configurado")
    return engine._llm_provider


def _llm_chat_text(provider, messages):
    """Chama LLMProvider.chat() e retorna texto da resposta."""
    result = provider.chat(messages)
    if isinstance(result, str):
        return result
    return result.get("content", result.get("response", ""))

# Mapa de normalizacao SIGA* → nome curto do modulo
_SIGA_TO_MODULE = {
    "sigacom": "compras", "sigafat": "faturamento", "sigafin": "financeiro",
    "sigaest": "estoque", "sigafis": "fiscal", "sigactb": "contabilidade",
    "sigagpe": "rh", "sigapcp": "pcp", "sigamnt": "manutencao",
    "sigatms": "logistica", "sigaqie": "qualidade", "sigacrm": "crm",
    "sigajuri": "juridico", "sigaorg": "organizacional", "sigaoms": "oms",
    "sigagpr": "gestao_projetos", "sigaloja": "loja", "sigataf": "taf",
    "sigamdi": "mdi", "sigapls": "plano_saude",
}


def _normalize_menu_module(mod_name: str) -> str:
    """Normaliza nome de modulo do menu (SIGACOM → compras)."""
    clean = mod_name.strip().lower()
    return _SIGA_TO_MODULE.get(clean, clean)


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


@workspace_bp.route("/workspaces/<slug>", methods=["DELETE"])
def delete_workspace(slug):
    """Exclui workspace e todos os dados."""
    import shutil
    ws_path = _get_workspace_path(slug)
    if not ws_path.exists():
        return jsonify({"error": "Workspace nao encontrado"}), 404
    try:
        shutil.rmtree(ws_path)
        # Limpar cache de DBs inicializados para permitir re-criacao
        from app.services.workspace.workspace_db import _initialized_dbs
        keys_to_remove = [k for k in _initialized_dbs if slug in k]
        for k in keys_to_remove:
            _initialized_dbs.discard(k)
        logger.info("Workspace %s excluido: %s", slug, ws_path)
        return jsonify({"success": True, "slug": slug})
    except Exception as e:
        return jsonify({"error": str(e)[:200]}), 500


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


def _ingest_padrao_if_provided(data: dict, db) -> dict | None:
    """Se padrao_csv_dir foi fornecido, ingere CSVs padrao e calcula diff."""
    padrao_csv_dir = data.get("padrao_csv_dir", "")
    if not padrao_csv_dir:
        return None

    padrao_path = Path(padrao_csv_dir)
    if not padrao_path.exists():
        logger.warning("Diretorio padrao nao encontrado: %s", padrao_path)
        return None

    try:
        from app.services.workspace.workspace_populator import ingest_padrao_sxs, calculate_diff
        padrao_summary = ingest_padrao_sxs(db, padrao_path)
        diff_summary = calculate_diff(db)
        return {"padrao": padrao_summary, "diff": diff_summary}
    except Exception as e:
        logger.warning("Erro ao processar CSV padrao: %s", e)
        return {"padrao": {"error": str(e)}, "diff": {}}


# ========================================================================
# INGESTAO
# ========================================================================

@workspace_bp.route("/workspaces/<slug>/ingest/csv", methods=["POST"])
def ingest_csv(slug):
    """Ingere CSVs SX no workspace.

    Body JSON: {"csv_dir": "/path/to/csvs", "padrao_csv_dir": "/path/to/csvs_padrao"}
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
        # Ingerir CSV padrao e calcular diff se fornecido
        padrao_stats = _ingest_padrao_if_provided(data, pop.db)
        if padrao_stats:
            stats["padrao"] = padrao_stats["padrao"]
            stats["diff"] = padrao_stats["diff"]
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

    Body JSON: {"connection_id": 1, "company_code": "01", "environment_id": 1, "padrao_csv_dir": "..."}
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
        padrao_stats = _ingest_padrao_if_provided(data, pop.db)
        if padrao_stats:
            stats["padrao"] = padrao_stats["padrao"]
            stats["diff"] = padrao_stats["diff"]
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
        padrao_stats = _ingest_padrao_if_provided(data, pop.db)
        if padrao_stats:
            stats["padrao"] = padrao_stats["padrao"]
            stats["diff"] = padrao_stats["diff"]
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
    """Retorna informacoes completas de uma tabela (campos, indices, gatilhos, fontes vinculados).
    Enriquece campos com status diff (padrao/adicionado/alterado)."""
    db = _get_db(slug)
    ks = KnowledgeService(db)
    info = ks.get_table_info(codigo.upper())
    if not info:
        return jsonify({"error": "Tabela nao encontrada"}), 404

    # Enriquecer campos com status diff
    try:
        diff_rows = db.execute(
            "SELECT chave, acao, campo_diff, valor_padrao, valor_cliente "
            "FROM diff WHERE tipo_sx IN ('campo', 'SX3') AND tabela = ?",
            (codigo.upper(),)
        ).fetchall()
        diff_added = set()
        diff_altered = {}
        for r in diff_rows:
            if r[1] == "adicionado":
                diff_added.add(r[0])
            elif r[1] == "alterado":
                diff_altered.setdefault(r[0], []).append({
                    "campo_diff": r[2], "valor_padrao": r[3], "valor_cliente": r[4]
                })

        for campo in info.get("campos", []):
            nome = campo["campo"]
            if nome in diff_added:
                campo["status"] = "adicionado"
            elif nome in diff_altered:
                campo["status"] = "alterado"
                campo["alteracoes"] = diff_altered[nome]
            else:
                campo["status"] = "padrao"
    except Exception:
        pass

    # Fontes vinculados a esta tabela
    try:
        tab = codigo.upper()
        fontes_rows = db.execute(
            "SELECT arquivo, modulo, tabelas_ref, write_tables, lines_of_code "
            "FROM fontes WHERE tabelas_ref LIKE ? OR write_tables LIKE ?",
            (f'%"{tab}"%', f'%"{tab}"%')
        ).fetchall()
        fontes_vinculados = []
        for f in fontes_rows:
            writes = json.loads(f[3]) if f[3] else []
            modo = "Leitura/Escrita" if tab in [w.upper() for w in writes] else "Leitura"
            fontes_vinculados.append({
                "arquivo": f[0], "modulo": f[1] or "", "loc": f[4] or 0, "modo": modo
            })
        info["fontes_vinculados"] = fontes_vinculados
    except Exception:
        info["fontes_vinculados"] = []

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


@workspace_bp.route("/workspaces/<slug>/explorer/stats", methods=["GET"])
def explorer_stats(slug):
    """Retorna estatisticas resumidas para a barra de stats do Explorer."""
    db = _get_db(slug)

    def _c(q, p=()):
        try:
            return db.execute(q, p).fetchone()[0]
        except Exception:
            return 0

    return jsonify({
        "tabelas": {"total": _c("SELECT COUNT(*) FROM tabelas"), "custom": _c("SELECT COUNT(*) FROM tabelas WHERE custom=1")},
        "campos": {"total": _c("SELECT COUNT(*) FROM campos"), "custom": _c("SELECT COUNT(*) FROM campos WHERE custom=1")},
        "fontes": {"total": _c("SELECT COUNT(*) FROM fontes")},
        "menus": {"total": _c("SELECT COUNT(*) FROM menus")},
        "diff": {
            "adicionados": _c("SELECT COUNT(DISTINCT chave) FROM diff WHERE tipo_sx IN ('campo','SX3') AND acao='adicionado'"),
            "alterados": _c("SELECT COUNT(DISTINCT chave) FROM diff WHERE tipo_sx IN ('campo','SX3') AND acao='alterado'"),
            "removidos": _c("SELECT COUNT(DISTINCT chave) FROM diff WHERE tipo_sx IN ('campo','SX3') AND acao='removido'")
        },
        "jobs": {"total": _c("SELECT COUNT(*) FROM jobs")},
        "schedules": {"total": _c("SELECT COUNT(*) FROM schedules"), "ativos": _c("SELECT COUNT(*) FROM schedules WHERE status='Ativo'")}
    })


@workspace_bp.route("/workspaces/<slug>/explorer/tree", methods=["GET"])
def explorer_tree(slug):
    """Retorna arvore hierarquica de modulos com contagens por categoria."""
    db = _get_db(slug)

    # Build module -> tables map from mapa_modulos
    modulos = {}

    # From mapa_modulos (standard mapping)
    try:
        mapa_rows = db.execute("SELECT modulo, tabelas, rotinas FROM mapa_modulos").fetchall()
        for mr in mapa_rows:
            mod = mr[0]
            tabs = json.loads(mr[1]) if mr[1] else []
            modulos[mod] = {"tabelas": set(t.upper() for t in tabs), "fontes": 0, "pes": 0, "menus_cliente": 0, "menus_padrao": 0}
    except Exception:
        pass

    # Count fontes per module AND enriquecer tabelas com fontes.tabelas_ref
    try:
        rows = db.execute(
            "SELECT modulo, COUNT(*) FROM fontes WHERE modulo IS NOT NULL AND modulo != '' GROUP BY modulo"
        ).fetchall()
        for r in rows:
            mod = r[0].lower()
            if mod not in modulos:
                modulos[mod] = {"tabelas": set(), "fontes": 0, "pes": 0, "menus_cliente": 0, "menus_padrao": 0}
            modulos[mod]["fontes"] = r[1]
    except Exception:
        pass

    # Enriquecer tabelas por modulo usando fontes.tabelas_ref (real)
    try:
        rows = db.execute(
            "SELECT modulo, tabelas_ref, write_tables FROM fontes WHERE modulo IS NOT NULL AND modulo != ''"
        ).fetchall()
        for r in rows:
            mod = r[0].lower()
            if mod not in modulos:
                continue
            for field in [r[1], r[2]]:
                try:
                    refs = json.loads(field) if field else []
                    for t in refs:
                        if isinstance(t, str) and t.strip():
                            modulos[mod]["tabelas"].add(t.strip().upper())
                except (json.JSONDecodeError, TypeError):
                    pass
    except Exception:
        pass

    # Count PEs per module (from fontes.pontos_entrada JSON)
    try:
        rows = db.execute("SELECT modulo, pontos_entrada FROM fontes WHERE pontos_entrada IS NOT NULL AND pontos_entrada != '[]'").fetchall()
        for r in rows:
            mod = (r[0] or "outros").lower()
            pes = json.loads(r[1]) if r[1] else []
            if mod not in modulos:
                modulos[mod] = {"tabelas": set(), "fontes": 0, "pes": 0, "menus_cliente": 0, "menus_padrao": 0}
            modulos[mod]["pes"] += len(pes)
    except Exception:
        pass

    # Count menus per module (normaliza SIGA* → nome curto)
    try:
        rows = db.execute("SELECT modulo, COUNT(*) FROM menus WHERE modulo IS NOT NULL GROUP BY modulo").fetchall()
        for r in rows:
            mod = _normalize_menu_module(r[0])
            if mod in modulos:
                modulos[mod]["menus_cliente"] += r[1]
            else:
                # Criar modulo se nao existir
                modulos.setdefault(mod, {"tabelas": set(), "fontes": 0, "pes": 0, "menus_cliente": 0, "menus_padrao": 0})
                modulos[mod]["menus_cliente"] += r[1]
    except Exception:
        pass

    # Assign tables to modules (check which tables belong to which module)
    all_tabelas = set()
    try:
        rows = db.execute("SELECT codigo FROM tabelas").fetchall()
        all_tabelas = {r[0].upper() for r in rows}
    except Exception:
        pass

    assigned_tabelas = set()
    for mod_data in modulos.values():
        assigned_tabelas |= mod_data["tabelas"]

    # Tables not assigned to any module go to "outros"
    unassigned = all_tabelas - assigned_tabelas
    if unassigned:
        modulos.setdefault("outros", {"tabelas": set(), "fontes": 0, "pes": 0, "menus_cliente": 0, "menus_padrao": 0})
        modulos["outros"]["tabelas"] |= unassigned

    # Build tree
    tree = []
    for mod_name in sorted(modulos.keys()):
        mod = modulos[mod_name]
        tab_count = len(mod["tabelas"] & all_tabelas)  # Only count tables that actually exist
        children = []
        if tab_count > 0:
            children.append({"key": mod_name + "_tabelas", "label": "Tabelas", "type": "category", "data": {"cat": "tabelas", "count": tab_count, "modulo": mod_name}})
        if mod["pes"] > 0:
            children.append({"key": mod_name + "_pes", "label": "Pontos de Entrada", "type": "category", "data": {"cat": "pes", "count": mod["pes"], "modulo": mod_name}})
        if mod["menus_cliente"] > 0:
            children.append({"key": mod_name + "_menus", "label": "Menus Cliente", "type": "category", "data": {"cat": "menus_cliente", "count": mod["menus_cliente"], "modulo": mod_name}})
        if mod["fontes"] > 0:
            children.append({"key": mod_name + "_fontes", "label": "Fontes Custom", "type": "category", "data": {"cat": "fontes", "count": mod["fontes"], "modulo": mod_name}})

        tree.append({
            "key": mod_name,
            "label": mod_name.capitalize(),
            "type": "modulo",
            "data": {"fontes": mod["fontes"], "tabelas": tab_count, "menus": mod["menus_cliente"], "pes": mod["pes"]},
            "children": children
        })

    # Add Jobs and Schedules at root level
    try:
        jobs_count = db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        if jobs_count > 0:
            tree.append({"key": "_jobs", "label": "Jobs (" + str(jobs_count) + ")", "type": "leaf_category", "data": {"cat": "jobs", "count": jobs_count}})
    except Exception:
        pass
    try:
        sched_count = db.execute("SELECT COUNT(*) FROM schedules").fetchone()[0]
        if sched_count > 0:
            tree.append({"key": "_schedules", "label": "Schedules (" + str(sched_count) + ")", "type": "leaf_category", "data": {"cat": "schedules", "count": sched_count}})
    except Exception:
        pass

    return jsonify(tree)


@workspace_bp.route("/workspaces/<slug>/explorer/category/<modulo>/<cat>", methods=["GET"])
def explorer_category_items(slug, modulo, cat):
    """Retorna itens de uma categoria dentro de um modulo."""
    db = _get_db(slug)

    if cat == "tabelas":
        # Combinar mapa_modulos (seed) + fontes.tabelas_ref (real) para pegar TODAS as tabelas
        tab_set = set()

        # Fonte 1: mapa_modulos (tabelas seed)
        try:
            row = db.execute("SELECT tabelas FROM mapa_modulos WHERE modulo = ?", (modulo,)).fetchone()
            if row:
                for t in json.loads(row[0]):
                    tab_set.add(t.upper())
        except Exception:
            pass

        # Fonte 2: fontes.tabelas_ref (tabelas reais referenciadas por fontes do modulo)
        try:
            rows = db.execute(
                "SELECT tabelas_ref, write_tables FROM fontes WHERE lower(modulo) = ?",
                (modulo.lower(),)
            ).fetchall()
            for r in rows:
                for field in [r[0], r[1]]:
                    try:
                        refs = json.loads(field) if field else []
                        for t in refs:
                            if isinstance(t, str) and t.strip():
                                tab_set.add(t.strip().upper())
                    except (json.JSONDecodeError, TypeError):
                        pass
        except Exception:
            pass

        # Buscar info de cada tabela e contar campos custom + alterados
        diff_alt_map = {}
        try:
            diff_rows = db.execute(
                "SELECT tabela, COUNT(DISTINCT chave) FROM diff "
                "WHERE tipo_sx IN ('campo','SX3') AND acao='alterado' GROUP BY tabela"
            ).fetchall()
            diff_alt_map = {r[0]: r[1] for r in diff_rows}
        except Exception:
            pass

        items = []
        for tc in sorted(tab_set):
            row = db.execute("SELECT codigo, nome, custom FROM tabelas WHERE upper(codigo) = ?", (tc,)).fetchone()
            if row:
                add_count = 0
                try:
                    add_count = db.execute("SELECT COUNT(*) FROM campos WHERE tabela = ? AND custom = 1", (row[0],)).fetchone()[0]
                except Exception:
                    pass
                alt_count = diff_alt_map.get(row[0], 0)
                items.append({
                    "codigo": row[0], "nome": row[1], "custom": bool(row[2]),
                    "campos_add": add_count, "campos_alt": alt_count
                })
        return jsonify(items)

    elif cat == "pes":
        # PEs from fontes in this module
        items = []
        try:
            rows = db.execute(
                "SELECT arquivo, pontos_entrada FROM fontes WHERE lower(modulo) = ? AND pontos_entrada IS NOT NULL AND pontos_entrada != '[]'",
                (modulo.lower(),)
            ).fetchall()
            for r in rows:
                pes = json.loads(r[1]) if r[1] else []
                for pe in pes:
                    if isinstance(pe, str) and pe.strip():
                        items.append({"pe": pe.strip(), "fonte": r[0]})
        except Exception:
            pass
        items.sort(key=lambda x: x["pe"])
        return jsonify(items)

    elif cat == "menus_cliente":
        items = []
        try:
            # Buscar menus: por nome curto OU pelo nome SIGA* original
            siga_names = [k for k, v in _SIGA_TO_MODULE.items() if v == modulo.lower()]
            placeholders = ",".join(["?"] * (len(siga_names) + 1))
            params = [modulo.lower()] + siga_names
            rows = db.execute(
                f"SELECT rotina, nome, menu FROM menus WHERE lower(TRIM(modulo)) IN ({placeholders}) ORDER BY rotina",
                params
            ).fetchall()
            # Try to find matching fonte
            for r in rows:
                fonte = ""
                try:
                    f = db.execute("SELECT arquivo FROM fontes WHERE upper(arquivo) LIKE ?", (r[0].upper() + '%',)).fetchone()
                    if f:
                        fonte = f[0]
                except Exception:
                    pass
                items.append({"rotina": r[0], "nome": r[1], "menu": r[2] or "", "fonte": fonte})
        except Exception:
            pass
        return jsonify(items)

    elif cat == "fontes":
        items = []
        try:
            rows = db.execute(
                "SELECT arquivo, funcoes, lines_of_code FROM fontes WHERE lower(modulo) = ? ORDER BY arquivo",
                (modulo.lower(),)
            ).fetchall()
            for r in rows:
                funcs = json.loads(r[1]) if r[1] else []
                items.append({"arquivo": r[0], "funcoes": len(funcs), "loc": r[2] or 0})
        except Exception:
            pass
        return jsonify(items)

    elif cat == "jobs":
        items = []
        try:
            rows = db.execute("SELECT arquivo_ini, sessao, rotina, refresh_rate, parametros FROM jobs ORDER BY rotina").fetchall()
            for r in rows:
                items.append({"arquivo": r[0], "sessao": r[1], "rotina": r[2], "refresh_rate": r[3], "parametros": r[4] or ""})
        except Exception:
            pass
        return jsonify(items)

    elif cat == "schedules":
        items = []
        try:
            rows = db.execute(
                "SELECT codigo, rotina, empresa_filial, status, tipo_recorrencia, execucoes_dia, hora_inicio FROM schedules ORDER BY rotina"
            ).fetchall()
            for r in rows:
                items.append({"codigo": r[0], "rotina": r[1], "empresa_filial": r[2], "status": r[3], "tipo_recorrencia": r[4], "execucoes_dia": r[5], "hora_inicio": r[6] or ""})
        except Exception:
            pass
        return jsonify(items)

    return jsonify([])


@workspace_bp.route("/workspaces/<slug>/explorer/fonte/<arquivo>", methods=["GET"])
def explorer_fonte_detail(slug, arquivo):
    """Retorna detalhe de um fonte (funcoes, tabelas, PEs, operacoes de escrita)."""
    db = _get_db(slug)

    row = db.execute(
        "SELECT arquivo, caminho, tipo, modulo, funcoes, user_funcs, pontos_entrada, "
        "tabelas_ref, write_tables, includes, calls_u, calls_execblock, fields_ref, "
        "lines_of_code, hash "
        "FROM fontes WHERE arquivo = ?", (arquivo,)
    ).fetchone()

    if not row:
        return jsonify({"error": "Fonte nao encontrado"}), 404

    def _j(val):
        try:
            return json.loads(val) if val else []
        except Exception:
            return []

    result = {
        "arquivo": row[0],
        "caminho": row[1] or "",
        "tipo": row[2] or "",
        "modulo": row[3] or "",
        "funcoes": _j(row[4]),
        "user_funcs": _j(row[5]),
        "pontos_entrada": _j(row[6]),
        "tabelas_ref": _j(row[7]),
        "write_tables": _j(row[8]),
        "includes": _j(row[9]),
        "calls_u": _j(row[10]),
        "calls_execblock": _j(row[11]),
        "fields_ref": _j(row[12]),
        "lines_of_code": row[13] or 0,
    }

    # Operacoes de escrita deste fonte
    try:
        ops = db.execute(
            "SELECT funcao, tipo, tabela, campos, condicao, linha "
            "FROM operacoes_escrita WHERE arquivo = ? ORDER BY linha",
            (arquivo,)
        ).fetchall()
        result["operacoes_escrita"] = [
            {"funcao": o[0], "tipo": o[1], "tabela": o[2],
             "campos": json.loads(o[3]) if o[3] else [], "condicao": o[4] or "", "linha": o[5]}
            for o in ops
        ]
    except Exception:
        result["operacoes_escrita"] = []

    # Vinculos deste fonte
    try:
        vinc = db.execute(
            "SELECT tipo, origem, destino, contexto FROM vinculos "
            "WHERE origem = ? OR destino = ? LIMIT 50",
            (arquivo, arquivo)
        ).fetchall()
        result["vinculos"] = [
            {"tipo": v[0], "origem": v[1], "destino": v[2], "contexto": v[3] or ""}
            for v in vinc
        ]
    except Exception:
        result["vinculos"] = []

    # Funcao docs (resumos gerados)
    try:
        docs = db.execute(
            "SELECT funcao, tipo, assinatura, resumo, tabelas_ref, chama, chamada_por, retorno "
            "FROM funcao_docs WHERE arquivo = ?",
            (arquivo,)
        ).fetchall()
        result["funcao_docs"] = [
            {"funcao": d[0], "tipo": d[1], "assinatura": d[2] or "", "resumo": d[3] or "",
             "tabelas_ref": d[4] or "", "chama": d[5] or "", "chamada_por": d[6] or "", "retorno": d[7] or ""}
            for d in docs
        ]
    except Exception:
        result["funcao_docs"] = []

    return jsonify(result)


@workspace_bp.route("/workspaces/<slug>/explorer/diff/<tabela>", methods=["GET"])
def explorer_diff_detail(slug, tabela):
    """Retorna diff detalhado padrao vs cliente para uma tabela."""
    db = _get_db(slug)
    tab = tabela.upper()

    # Check if padrao data exists
    padrao_count = 0
    try:
        padrao_count = db.execute("SELECT COUNT(*) FROM padrao_campos WHERE tabela = ?", (tab,)).fetchone()[0]
    except Exception:
        pass

    if padrao_count == 0:
        return jsonify({"available": False, "tabela": tab, "message": "Dados padrao nao ingeridos para esta tabela"})

    # Adicionados: no cliente mas nao no padrao
    adicionados = []
    try:
        rows = db.execute(
            "SELECT c.campo, c.tipo, c.tamanho, c.titulo, c.validacao "
            "FROM campos c LEFT JOIN padrao_campos p ON c.tabela = p.tabela AND c.campo = p.campo "
            "WHERE c.tabela = ? AND p.campo IS NULL ORDER BY c.campo", (tab,)
        ).fetchall()
        adicionados = [{"campo": r[0], "tipo": r[1], "tamanho": r[2], "titulo": r[3] or "", "validacao": r[4] or ""} for r in rows]
    except Exception:
        pass

    # Removidos: no padrao mas nao no cliente
    removidos = []
    try:
        rows = db.execute(
            "SELECT p.campo, p.tipo, p.tamanho, p.titulo, p.validacao "
            "FROM padrao_campos p LEFT JOIN campos c ON p.tabela = c.tabela AND p.campo = c.campo "
            "WHERE p.tabela = ? AND c.campo IS NULL ORDER BY p.campo", (tab,)
        ).fetchall()
        removidos = [{"campo": r[0], "tipo": r[1], "tamanho": r[2], "titulo": r[3] or "", "validacao": r[4] or ""} for r in rows]
    except Exception:
        pass

    # Alterados: existe nos dois mas difere
    alterados = []
    try:
        rows = db.execute(
            "SELECT c.campo, p.tipo, c.tipo, p.tamanho, c.tamanho, p.titulo, c.titulo, p.validacao, c.validacao "
            "FROM campos c INNER JOIN padrao_campos p ON c.tabela = p.tabela AND c.campo = p.campo "
            "WHERE c.tabela = ? AND (c.tipo != p.tipo OR c.tamanho != p.tamanho OR c.validacao != p.validacao) "
            "ORDER BY c.campo", (tab,)
        ).fetchall()
        for r in rows:
            diffs = {}
            if r[1] != r[2]:
                diffs["tipo"] = {"padrao": r[1], "cliente": r[2]}
            if r[3] != r[4]:
                diffs["tamanho"] = {"padrao": str(r[3]), "cliente": str(r[4])}
            if r[7] != r[8]:
                diffs["validacao"] = {"padrao": r[7] or "", "cliente": r[8] or ""}
            if r[5] != r[6]:
                diffs["titulo"] = {"padrao": r[5] or "", "cliente": r[6] or ""}
            if diffs:
                alterados.append({"campo": r[0], "diferencas": diffs})
    except Exception:
        pass

    return jsonify({
        "available": True,
        "tabela": tab,
        "adicionados": adicionados,
        "alterados": alterados,
        "removidos": removidos,
        "resumo": {
            "adicionados": len(adicionados),
            "alterados": len(alterados),
            "removidos": len(removidos)
        }
    })


@workspace_bp.route("/workspaces/<slug>/explorer/search", methods=["GET"])
def explorer_search(slug):
    """Busca global no workspace: tabelas, fontes, menus, campos."""
    db = _get_db(slug)
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify({"results": [], "total": 0})

    q_upper = q.upper()
    q_like = f"%{q_upper}%"
    results = []

    # Search tabelas
    try:
        rows = db.execute(
            "SELECT codigo, nome FROM tabelas WHERE upper(codigo) LIKE ? OR upper(nome) LIKE ? LIMIT 15",
            (q_like, q_like)
        ).fetchall()
        for r in rows:
            results.append({"type": "tabela", "key": r[0], "label": r[0] + " — " + (r[1] or ""), "action": "wsSelectTable", "params": {"codigo": r[0]}})
    except Exception:
        pass

    # Search fontes
    try:
        rows = db.execute(
            "SELECT arquivo, modulo FROM fontes WHERE upper(arquivo) LIKE ? LIMIT 15",
            (q_like,)
        ).fetchall()
        for r in rows:
            results.append({"type": "fonte", "key": r[0], "label": r[0] + " (" + (r[1] or "") + ")", "action": "wsOpenFonte", "params": {"arquivo": r[0]}})
    except Exception:
        pass

    # Search menus
    try:
        rows = db.execute(
            "SELECT rotina, nome FROM menus WHERE upper(rotina) LIKE ? OR upper(nome) LIKE ? LIMIT 10",
            (q_like, q_like)
        ).fetchall()
        for r in rows:
            results.append({"type": "menu", "key": r[0], "label": r[0] + " — " + (r[1] or "")})
    except Exception:
        pass

    # Search campos
    try:
        rows = db.execute(
            "SELECT tabela, campo, titulo FROM campos WHERE upper(campo) LIKE ? LIMIT 10",
            (q_like,)
        ).fetchall()
        for r in rows:
            results.append({"type": "campo", "key": r[0] + "." + r[1], "label": r[1] + " (" + r[0] + ") — " + (r[2] or ""), "action": "wsSelectTable", "params": {"codigo": r[0]}})
    except Exception:
        pass

    return jsonify({"results": results[:30], "total": len(results)})


# ---------------------------------------------------------------------------
#  Explorer — IA Overview, Funcao Resumir/Codigo, Anotacoes
# ---------------------------------------------------------------------------


@workspace_bp.route("/workspaces/<slug>/explorer/fonte/<arquivo>/overview", methods=["POST"])
def explorer_fonte_overview(slug, arquivo):
    """Gera overview IA do fonte (resumo do programa)."""
    db = _get_db(slug)
    force = request.args.get("force", "false").lower() == "true"

    row = db.execute(
        "SELECT arquivo, modulo, funcoes, pontos_entrada, tabelas_ref, write_tables, lines_of_code "
        "FROM fontes WHERE arquivo = ?", (arquivo,)
    ).fetchone()
    if not row:
        return jsonify({"error": "Fonte nao encontrado"}), 404

    def _j(v):
        try:
            return json.loads(v) if v else []
        except Exception:
            return []

    # Check cache in funcao_docs
    if not force:
        try:
            cached = db.execute(
                "SELECT resumo FROM funcao_docs WHERE arquivo = ? AND funcao = '__overview__'",
                (arquivo,)
            ).fetchone()
            if cached and cached[0]:
                return jsonify({"arquivo": arquivo, "overview": cached[0], "cached": True})
        except Exception:
            pass

    try:
        llm = _get_llm_provider()
    except Exception as e:
        return jsonify({"error": f"LLM nao disponivel: {str(e)[:200]}"}), 500

    funcoes = _j(row[2])
    pes = _j(row[3])
    tabs_ref = _j(row[4])
    tabs_write = _j(row[5])

    # Buscar operacoes de escrita
    ops = []
    try:
        ops_rows = db.execute(
            "SELECT funcao, tipo, tabela, condicao FROM operacoes_escrita WHERE arquivo = ? LIMIT 30",
            (arquivo,)
        ).fetchall()
        ops = [f"{r[0]}: {r[1]} em {r[2]}" + (f" (cond: {r[3]})" if r[3] else "") for r in ops_rows]
    except Exception:
        pass

    prompt = f"""Analise o fonte Protheus ADVPL/TLPP "{arquivo}" e gere um overview tecnico.

Modulo: {row[1] or 'desconhecido'}
Funcoes: {', '.join(funcoes[:20])}
Pontos de Entrada: {', '.join(pes) if pes else 'Nenhum'}
Tabelas leitura: {', '.join(tabs_ref[:15])}
Tabelas escrita: {', '.join(tabs_write[:10])}
Linhas de codigo: {row[6]}
Operacoes de escrita: {chr(10).join(ops[:15]) if ops else 'Nenhuma detectada'}

Gere um overview TECNICO em markdown com:
## Ecossistema
## Cadeia de Chamadas
## Write Points
## Pontos de Atencao
## Resumo

Baseie-se APENAS nos dados fornecidos. Seja conciso."""

    text = _llm_chat_text(llm, [{"role": "user", "content": prompt}])

    # Cache
    try:
        db.execute(
            "INSERT OR REPLACE INTO funcao_docs (arquivo, funcao, tipo, resumo, fonte) VALUES (?, '__overview__', 'overview', ?, 'auto')",
            (arquivo, text)
        )
        db.commit()
    except Exception:
        pass

    return jsonify({"arquivo": arquivo, "overview": text, "cached": False})


@workspace_bp.route("/workspaces/<slug>/explorer/funcao/<arquivo>/<funcao>/resumir", methods=["POST"])
def explorer_funcao_resumir(slug, arquivo, funcao):
    """Gera resumo IA de uma funcao especifica."""
    db = _get_db(slug)

    # Check cache
    try:
        cached = db.execute(
            "SELECT resumo FROM funcao_docs WHERE arquivo = ? AND funcao = ?",
            (arquivo, funcao)
        ).fetchone()
        if cached and cached[0]:
            return jsonify({"arquivo": arquivo, "funcao": funcao, "resumo": cached[0], "cached": True})
    except Exception:
        pass

    # Get function context from chunks
    chunk_content = ""
    try:
        row = db.execute(
            "SELECT content FROM fonte_chunks WHERE arquivo = ? AND funcao = ?",
            (arquivo, funcao)
        ).fetchone()
        if row:
            chunk_content = row[0][:3000]  # Limit to 3000 chars
    except Exception:
        pass

    if not chunk_content:
        return jsonify({"error": "Codigo da funcao nao encontrado nos chunks"}), 404

    try:
        llm = _get_llm_provider()
    except Exception as e:
        return jsonify({"error": f"LLM nao disponivel: {str(e)[:200]}"}), 500

    prompt = f"""Analise a funcao ADVPL/TLPP "{funcao}" do arquivo "{arquivo}" e gere um resumo tecnico.

CODIGO:
{chunk_content}

Retorne um resumo conciso (2-3 frases) explicando:
- O que a funcao faz
- Quais tabelas manipula
- Se tem condicoes especiais ou tratamento de erro
Seja direto e tecnico."""

    text = _llm_chat_text(llm, [{"role": "user", "content": prompt}])

    # Cache
    try:
        db.execute(
            "INSERT OR REPLACE INTO funcao_docs (arquivo, funcao, tipo, resumo, fonte) VALUES (?, ?, 'function', ?, 'auto')",
            (arquivo, funcao, text)
        )
        db.commit()
    except Exception:
        pass

    return jsonify({"arquivo": arquivo, "funcao": funcao, "resumo": text, "cached": False})


@workspace_bp.route("/workspaces/<slug>/explorer/funcao/<arquivo>/<funcao>/codigo", methods=["GET"])
def explorer_funcao_codigo(slug, arquivo, funcao):
    """Retorna codigo fonte de uma funcao (do chunk)."""
    db = _get_db(slug)

    try:
        row = db.execute(
            "SELECT content FROM fonte_chunks WHERE arquivo = ? AND funcao = ?",
            (arquivo, funcao)
        ).fetchone()
        if not row:
            return jsonify({"error": "Chunk nao encontrado"}), 404
        return jsonify({"arquivo": arquivo, "funcao": funcao, "codigo": row[0]})
    except Exception as e:
        return jsonify({"error": str(e)[:200]}), 500


@workspace_bp.route("/workspaces/<slug>/explorer/anotacoes/<tipo>/<chave>", methods=["GET"])
def explorer_listar_anotacoes(slug, tipo, chave):
    """Lista anotacoes de uma tabela/fonte/campo."""
    db = _get_db(slug)
    try:
        rows = db.execute(
            "SELECT id, texto, autor, tags, data FROM anotacoes WHERE tipo = ? AND chave = ? ORDER BY data DESC",
            (tipo, chave)
        ).fetchall()
        return jsonify([
            {"id": r[0], "texto": r[1], "autor": r[2], "tags": json.loads(r[3]) if r[3] else [], "data": r[4]}
            for r in rows
        ])
    except Exception:
        return jsonify([])


@workspace_bp.route("/workspaces/<slug>/explorer/anotacoes", methods=["POST"])
def explorer_criar_anotacao(slug):
    """Cria anotacao em tabela/fonte/campo."""
    db = _get_db(slug)
    data = request.get_json()
    tipo = data.get("tipo", "")
    chave = data.get("chave", "")
    texto = data.get("texto", "")
    if not tipo or not chave or not texto:
        return jsonify({"error": "tipo, chave e texto obrigatorios"}), 400

    try:
        db.execute(
            "INSERT INTO anotacoes (tipo, chave, texto, autor, tags) VALUES (?, ?, ?, 'consultor', '[]')",
            (tipo, chave, texto)
        )
        db.commit()
        new_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        return jsonify({"id": new_id, "success": True})
    except Exception as e:
        return jsonify({"error": str(e)[:200]}), 500


@workspace_bp.route("/workspaces/<slug>/explorer/anotacoes/<int:anotacao_id>", methods=["DELETE"])
def explorer_deletar_anotacao(slug, anotacao_id):
    """Deleta anotacao."""
    db = _get_db(slug)
    try:
        db.execute("DELETE FROM anotacoes WHERE id = ?", (anotacao_id,))
        db.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)[:200]}), 500


@workspace_bp.route("/workspaces/<slug>/dashboard", methods=["GET"])
def workspace_dashboard(slug):
    """Retorna dados ricos para dashboard do workspace (similar ao ExtraiRPO)."""
    try:
        db = _get_db(slug)
    except Exception as e:
        logger.error("Erro ao abrir workspace %s: %s", slug, e)
        return jsonify({"error": "Workspace nao encontrado"}), 404

    def _count(query, params=()):
        try:
            row = db.execute(query, params).fetchone()
            return row[0] if row else 0
        except Exception:
            return 0

    # --- RESUMO ---
    tabelas_total = _count("SELECT COUNT(*) FROM tabelas")
    tabelas_custom = _count("SELECT COUNT(*) FROM tabelas WHERE custom = 1")
    campos_total = _count("SELECT COUNT(*) FROM campos")
    campos_custom = _count("SELECT COUNT(*) FROM campos WHERE custom = 1")
    campos_adicionados = _count("SELECT COUNT(DISTINCT chave) FROM diff WHERE tipo_sx = 'SX3' AND acao = 'adicionado'")
    campos_alterados = _count("SELECT COUNT(DISTINCT chave) FROM diff WHERE tipo_sx = 'SX3' AND acao = 'alterado'")
    diff_removidos = _count("SELECT COUNT(DISTINCT chave) FROM diff WHERE tipo_sx = 'SX3' AND acao = 'removido'")
    indices_total = _count("SELECT COUNT(*) FROM indices")
    indices_custom = _count("SELECT COUNT(*) FROM indices WHERE custom = 1")
    gatilhos_total = _count("SELECT COUNT(*) FROM gatilhos")
    gatilhos_custom = _count("SELECT COUNT(*) FROM gatilhos WHERE custom = 1")
    fontes_total = _count("SELECT COUNT(*) FROM fontes")
    vinculos_total = _count("SELECT COUNT(*) FROM vinculos")
    menus_total = _count("SELECT COUNT(*) FROM menus")
    jobs_total = _count("SELECT COUNT(*) FROM jobs")
    schedules_total = _count("SELECT COUNT(*) FROM schedules")
    schedules_ativos = _count("SELECT COUNT(*) FROM schedules WHERE status = 'Ativo'")

    resumo = {
        "tabelas_total": tabelas_total,
        "tabelas_custom": tabelas_custom,
        "campos_total": campos_total,
        "campos_custom": campos_custom,
        "campos_adicionados": campos_adicionados,
        "campos_alterados": campos_alterados,
        "indices_total": indices_total,
        "indices_custom": indices_custom,
        "gatilhos_total": gatilhos_total,
        "gatilhos_custom": gatilhos_custom,
        "fontes_total": fontes_total,
        "vinculos": vinculos_total,
        "menus_total": menus_total,
        "jobs_total": jobs_total,
        "schedules_total": schedules_total,
        "schedules_ativos": schedules_ativos,
        "diff_removidos": diff_removidos,
    }

    # --- DISTRIBUICAO DE RISCO ---
    campos_so_padrao = max(0, campos_total - campos_custom - campos_adicionados - campos_alterados)
    distribuicao_risco = {
        "campos_so_padrao": campos_so_padrao,
        "campos_adicionados": campos_adicionados,
        "campos_alterados": campos_alterados,
        "campos_removidos": diff_removidos,
    }

    # --- TOP TABELAS (mais customizadas) ---
    top_tabelas = []
    try:
        rows = db.execute("""
            SELECT c.tabela,
                   COALESCE(t.nome, '') AS nome,
                   SUM(CASE WHEN c.custom = 1 THEN 1 ELSE 0 END) AS campos_add
            FROM campos c
            LEFT JOIN tabelas t ON t.codigo = c.tabela
            GROUP BY c.tabela
            HAVING campos_add > 0
            ORDER BY campos_add DESC
        """).fetchall()

        # Complementar com dados de diff (alterados por tabela)
        diff_alt_map = {}
        try:
            diff_rows = db.execute("""
                SELECT tabela, COUNT(DISTINCT chave) AS cnt
                FROM diff
                WHERE tipo_sx = 'SX3' AND acao = 'alterado'
                GROUP BY tabela
            """).fetchall()
            diff_alt_map = {r[0]: r[1] for r in diff_rows}
        except Exception:
            pass

        for r in rows:
            tabela, nome, campos_add = r[0], r[1], r[2]
            campos_alt = diff_alt_map.get(tabela, 0)
            score = campos_add * 2 + campos_alt
            top_tabelas.append({
                "tabela": tabela,
                "nome": nome,
                "campos_add": campos_add,
                "campos_alt": campos_alt,
                "score": score,
            })

        top_tabelas.sort(key=lambda x: x["score"], reverse=True)
        top_tabelas = top_tabelas[:10]
    except Exception as e:
        logger.warning("Erro ao calcular top_tabelas: %s", e)

    # --- TOP INTERACAO (tabelas mais referenciadas em fontes) ---
    top_interacao = []
    try:
        fontes_rows = db.execute(
            "SELECT arquivo, tabelas_ref, write_tables FROM fontes"
        ).fetchall()

        leitura_map = {}
        escrita_map = {}
        for row in fontes_rows:
            # tabelas_ref - leitura
            try:
                refs = json.loads(row[1]) if row[1] else []
                for tab in refs:
                    if isinstance(tab, str) and tab.strip():
                        leitura_map[tab.strip().upper()] = leitura_map.get(tab.strip().upper(), 0) + 1
            except (json.JSONDecodeError, TypeError):
                pass
            # write_tables - escrita
            try:
                writes = json.loads(row[2]) if row[2] else []
                for tab in writes:
                    if isinstance(tab, str) and tab.strip():
                        escrita_map[tab.strip().upper()] = escrita_map.get(tab.strip().upper(), 0) + 1
            except (json.JSONDecodeError, TypeError):
                pass

        all_tabs = set(leitura_map.keys()) | set(escrita_map.keys())
        interacao_list = []
        for tab in all_tabs:
            leit = leitura_map.get(tab, 0)
            escr = escrita_map.get(tab, 0)
            interacao_list.append({
                "tabela": tab,
                "leitura": leit,
                "escrita": escr,
                "total": leit + escr,
            })
        interacao_list.sort(key=lambda x: x["total"], reverse=True)
        top_interacao = interacao_list[:10]
    except Exception as e:
        logger.warning("Erro ao calcular top_interacao: %s", e)

    # --- MODULOS ---
    modulos = []
    try:
        mod_rows = db.execute("""
            SELECT modulo, COUNT(*) AS fontes_count
            FROM fontes
            WHERE modulo IS NOT NULL AND modulo != ''
            GROUP BY modulo
            ORDER BY fontes_count DESC
        """).fetchall()

        # Buscar contagem de tabelas do mapa_modulos
        mapa_tab_map = {}
        try:
            mapa_rows = db.execute("SELECT modulo, tabelas FROM mapa_modulos").fetchall()
            for mr in mapa_rows:
                try:
                    tabs = json.loads(mr[1]) if mr[1] else []
                    mapa_tab_map[mr[0].lower()] = len(tabs)
                except (json.JSONDecodeError, TypeError):
                    mapa_tab_map[mr[0].lower()] = 0
        except Exception:
            pass

        for mr in mod_rows:
            mod_name = mr[0]
            modulos.append({
                "modulo": mod_name,
                "fontes": mr[1],
                "tabelas": mapa_tab_map.get(mod_name.lower(), 0),
            })
    except Exception as e:
        logger.warning("Erro ao calcular modulos: %s", e)

    # --- TOP FONTES (maiores por LOC) ---
    top_fontes = []
    try:
        rows = db.execute(
            "SELECT arquivo, funcoes, lines_of_code, modulo FROM fontes "
            "WHERE lines_of_code > 0 ORDER BY lines_of_code DESC LIMIT 10"
        ).fetchall()
        for r in rows:
            funcs = json.loads(r[1]) if r[1] else []
            top_fontes.append({"arquivo": r[0], "funcoes": len(funcs), "loc": r[2], "modulo": r[3] or ""})
    except Exception:
        pass

    return jsonify({
        "resumo": resumo,
        "distribuicao_risco": distribuicao_risco,
        "top_tabelas": top_tabelas,
        "top_interacao": top_interacao,
        "top_fontes": top_fontes,
        "modulos": modulos,
    })


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


# ========================================================================
# PROCESSOS DO CLIENTE — Detecçao, analise, chat e registro
# ========================================================================

@workspace_bp.route("/workspaces/<slug>/build-vinculos", methods=["POST"])
def rebuild_vinculos(slug):
    """Reconstroi grafo de vinculos do workspace (11 tipos de relacionamento)."""
    ws_path = _get_workspace_path(slug)
    db_path = ws_path / "workspace.db"
    if not db_path.exists():
        return jsonify({"error": "Workspace nao encontrado"}), 404

    try:
        from app.services.workspace.build_vinculos import build_vinculos
        build_vinculos(db_path)
        # Contar vinculos criados
        db = _get_db(slug)
        count = db.execute("SELECT COUNT(*) FROM vinculos").fetchone()[0]
        tipos = db.execute("SELECT tipo, COUNT(*) FROM vinculos GROUP BY tipo ORDER BY COUNT(*) DESC").fetchall()
        return jsonify({
            "success": True,
            "total": count,
            "por_tipo": {r[0]: r[1] for r in tipos}
        })
    except Exception as e:
        logger.exception(f"Erro ao construir vinculos: {e}")
        return jsonify({"error": str(e)[:300]}), 500


@workspace_bp.route("/workspaces/<slug>/processos/descobrir", methods=["POST"])
def descobrir_processos_endpoint(slug):
    """Roda pipeline de descoberta automatica de processos (5 passos SQL + LLM)."""
    data = request.get_json() or {}
    force = data.get("force", False)

    db = _get_db(slug)

    try:
        llm = _get_llm_provider()
    except Exception as e:
        return jsonify({"error": f"LLM nao disponivel: {str(e)[:200]}"}), 500

    try:
        from app.services.workspace.descoberta_processos import descobrir_processos
        processos = descobrir_processos(db, llm, force=force)
        return jsonify({"total": len(processos), "processos": processos})
    except Exception as e:
        logger.exception(f"Erro na descoberta de processos: {e}")
        return jsonify({"error": str(e)[:300]}), 500


@workspace_bp.route("/workspaces/<slug>/processos", methods=["GET"])
def listar_processos(slug):
    """Lista processos de negocio detectados no workspace."""
    db = _get_db(slug)
    try:
        rows = db.execute(
            "SELECT id, nome, tipo, descricao, criticidade, tabelas, score, "
            "fluxo_mermaid, validado, created_at, updated_at "
            "FROM processos_detectados ORDER BY score DESC"
        ).fetchall()
    except Exception:
        return jsonify([])

    tabela_filter = request.args.get("tabela", "").upper()
    tipo_filter = request.args.get("tipo", "")

    processos = []
    for r in rows:
        tabs = json.loads(r[5]) if r[5] else []
        if tabela_filter and tabela_filter not in [t.upper() for t in tabs]:
            continue
        if tipo_filter and r[2] != tipo_filter:
            continue
        processos.append({
            "id": r[0], "nome": r[1], "tipo": r[2], "descricao": r[3],
            "criticidade": r[4], "tabelas": tabs, "score": r[6],
            "fluxo_mermaid": r[7], "validado": bool(r[8]),
            "created_at": r[9], "updated_at": r[10],
        })
    return jsonify(processos)


@workspace_bp.route("/workspaces/<slug>/processos/<int:processo_id>/fluxo", methods=["POST"])
def gerar_fluxo_processo(slug, processo_id):
    """Gera (ou retorna cache) diagrama Mermaid de um processo via LLM."""
    db = _get_db(slug)
    force = request.args.get("force", "false").lower() == "true"

    row = db.execute(
        "SELECT id, nome, tipo, descricao, criticidade, tabelas, score, fluxo_mermaid "
        "FROM processos_detectados WHERE id = ?",
        (processo_id,),
    ).fetchone()

    if not row:
        return jsonify({"error": "Processo nao encontrado"}), 404

    # Cache hit
    if row[7] and not force:
        return jsonify({"fluxo_mermaid": row[7]})

    # Gather write operations for real flow data
    ks = KnowledgeService(db)
    flow_context_parts = []
    tabelas_list = json.loads(row[5]) if row[5] else []
    for tab in tabelas_list[:5]:
        ops = db.execute(
            "SELECT DISTINCT arquivo, funcao, tipo FROM operacoes_escrita WHERE upper(tabela) = ?",
            (tab.upper(),)
        ).fetchall()
        if ops:
            flow_context_parts.append(f"Tabela {tab}: " + ", ".join(
                [f"{o[0]}:{o[1]}({o[2]})" for o in ops[:10]]
            ))
    flow_context = "\n".join(flow_context_parts)

    # Gerar via LLM
    try:
        llm = _get_llm_provider()
    except Exception as e:
        return jsonify({"error": f"LLM nao disponivel: {str(e)[:200]}"}), 500

    prompt = (
        f'Gere um diagrama Mermaid `flowchart TD` para o processo "{row[1]}" do tipo "{row[2]}".\n'
        f"Descricao: {row[3]}\n"
        f"Tabelas envolvidas: {row[5]}\n"
        f"Criticidade: {row[4]}\n"
        + (f"Operacoes de escrita reais:\n{flow_context}\n" if flow_context else "")
        + "Represente as etapas principais do processo de forma clara. "
        + "Retorne APENAS o codigo Mermaid, sem explicacoes."
    )

    try:
        text = _llm_chat_text(llm, [{"role": "user", "content": prompt}])

        match = re.search(r"```(?:mermaid)?\s*([\s\S]*?)```", text)
        if match:
            mermaid_str = match.group(1).strip()
        elif text.strip().startswith(("flowchart", "graph")):
            mermaid_str = text.strip()
        else:
            return jsonify({"error": "Resposta do LLM nao e um diagrama Mermaid valido"}), 500

        db.execute(
            "UPDATE processos_detectados SET fluxo_mermaid = ? WHERE id = ?",
            (mermaid_str, processo_id),
        )
        db.commit()
        return jsonify({"fluxo_mermaid": mermaid_str})
    except Exception as e:
        logger.exception(f"Erro ao gerar fluxo: {e}")
        return jsonify({"error": str(e)[:300]}), 500


@workspace_bp.route("/workspaces/<slug>/processos/<int:processo_id>/analise", methods=["GET"])
def get_analise_processo(slug, processo_id):
    """Gera (ou retorna cache) analise tecnica de um processo via investigacao + LLM."""
    db = _get_db(slug)
    force = request.args.get("force", "false").lower() == "true"

    row = db.execute(
        "SELECT id, nome, tipo, descricao, criticidade, tabelas, score, "
        "analise_markdown, analise_json, analise_updated_at "
        "FROM processos_detectados WHERE id = ?",
        (processo_id,),
    ).fetchone()

    if not row:
        return jsonify({"error": "Processo nao encontrado"}), 404

    # Cache hit
    if row[7] and not force and row[9] != 'generating':
        return jsonify({
            "analise_markdown": row[7],
            "analise_json": json.loads(row[8]) if row[8] else {},
            "analise_updated_at": row[9],
        })

    # Concurrency guard
    if row[9] == 'generating' and not force:
        return jsonify({"error": "Analise em geracao por outra requisicao"}), 409

    # Mark as generating
    db.execute(
        "UPDATE processos_detectados SET analise_updated_at = 'generating' WHERE id = ?",
        (processo_id,),
    )
    db.commit()

    try:
        tabelas = json.loads(row[5]) if row[5] else []
        nome = row[1]
        tipo = row[2]
        descricao = row[3]

        # Fase 1: Investigar usando knowledge service
        ks = KnowledgeService(db)
        tool_results_parts = []

        for tab in tabelas[:8]:
            try:
                info = ks.get_table_info(tab)
                if info:
                    tool_results_parts.append(f"### Tabela {tab}\n{json.dumps(info, ensure_ascii=False, indent=2)}")
            except Exception:
                pass

            # Operacoes de escrita por tabela
            try:
                ops_rows = db.execute(
                    "SELECT arquivo, funcao, tipo, campos, condicao, linha "
                    "FROM operacoes_escrita WHERE upper(tabela) = ?", (tab.upper(),)
                ).fetchall()
                if ops_rows:
                    ops_details = [{"arquivo": r[0], "funcao": r[1], "tipo": r[2], "campos": r[3], "condicao": r[4], "linha": r[5]} for r in ops_rows]
                    tool_results_parts.append(
                        f"### Operacoes {tab}\nTotal: {len(ops_rows)} operacoes\n{json.dumps(ops_details, ensure_ascii=False)}"
                    )
            except Exception:
                pass

            # Fontes que escrevem na tabela
            try:
                fontes_rows = db.execute(
                    "SELECT arquivo, modulo, lines_of_code FROM fontes WHERE write_tables LIKE ?",
                    (f'%"{tab}"%',)
                ).fetchall()
                if fontes_rows:
                    fontes_list = [{"arquivo": r[0], "modulo": r[1], "loc": r[2]} for r in fontes_rows]
                    tool_results_parts.append(f"### Fontes escrita {tab}\n{json.dumps(fontes_list, ensure_ascii=False)}")
            except Exception:
                pass

        # Parametros relacionados (SX6)
        try:
            for tab in tabelas[:4]:
                param_rows = db.execute(
                    "SELECT variavel, tipo, descricao, conteudo FROM parametros "
                    "WHERE upper(descricao) LIKE ? OR upper(variavel) LIKE ? LIMIT 10",
                    (f'%{tab}%', f'%{tab}%')
                ).fetchall()
                if param_rows:
                    params_list = [{"variavel": r[0], "tipo": r[1], "descricao": r[2], "conteudo": r[3]} for r in param_rows]
                    tool_results_parts.append(f"### Parametros {tab}\n{json.dumps(params_list, ensure_ascii=False)}")
        except Exception:
            pass

        tool_results_text = "\n\n".join(tool_results_parts) or "Nenhum dado de investigacao encontrado."

        # Fase 2: LLM gera markdown + JSON
        try:
            llm = _get_llm_provider()
        except Exception as e:
            db.execute(
                "UPDATE processos_detectados SET analise_updated_at = NULL WHERE id = ?",
                (processo_id,),
            )
            db.commit()
            return jsonify({"error": f"LLM nao disponivel: {str(e)[:200]}"}), 500

        prompt = f"""Analise o processo "{nome}" (tipo: {tipo}, criticidade: {row[4]}).
Descricao: {descricao}
Tabelas envolvidas: {', '.join(tabelas)}

DADOS DE INVESTIGACAO:
{tool_results_text}

Gere DUAS saidas:

1. ANALISE EM MARKDOWN — relatorio tecnico completo com secoes:
## Write Points
## Triggers e Gatilhos
## Entry Points (PEs)
## Parametros Relacionados
## Fontes Envolvidas
## Condicoes Criticas
## Resumo do Processo

2. JSON ESTRUTURADO — no formato abaixo (dentro de um bloco ```json):
```json
{{
  "tabelas": [
    {{
      "codigo": "XXX",
      "write_points": [
        {{ "fonte": "ARQUIVO.PRW", "funcao": "Funcao", "campos": ["CAMPO1"], "condicao": "cond" }}
      ],
      "triggers": [
        {{ "campo": "CAMPO", "gatilho": "U_FUNC", "tipo": "change" }}
      ],
      "operacoes": [
        {{ "tipo": "reclock", "funcao": "Funcao", "modo": "inclusao" }}
      ]
    }}
  ],
  "entry_points": [
    {{ "pe": "NOME_PE", "fonte": "ARQUIVO.PRW", "descricao": "desc" }}
  ],
  "parametros": [
    {{ "nome": "MV_XXXX", "conteudo": "valor", "descricao": "desc" }}
  ],
  "fontes_envolvidas": ["ARQUIVO1.PRW", "ARQUIVO2.PRW"],
  "condicoes_criticas": [
    {{ "condicao": "expr", "impacto": "desc", "fonte": "ARQUIVO.PRW" }}
  ]
}}
```

Retorne PRIMEIRO o markdown completo, depois o bloco JSON.
Baseie-se APENAS nos dados de investigacao fornecidos. Nao invente dados."""

        text = _llm_chat_text(llm, [{"role": "user", "content": prompt}])

        # Fase 3: Parse response
        json_match = re.search(r"```json\s*([\s\S]*?)```", text)
        analise_json_str = "{}"
        if json_match:
            try:
                analise_json_obj = json.loads(json_match.group(1).strip())
                analise_json_str = json.dumps(analise_json_obj, ensure_ascii=False)
            except json.JSONDecodeError:
                analise_json_str = "{}"

        analise_md = text[:json_match.start()].strip() if json_match else text.strip()

        # Fase 4: Salvar
        from datetime import datetime
        now = datetime.utcnow().isoformat()
        db.execute(
            "UPDATE processos_detectados SET analise_markdown=?, analise_json=?, analise_updated_at=? WHERE id=?",
            (analise_md, analise_json_str, now, processo_id),
        )
        db.commit()

        return jsonify({
            "analise_markdown": analise_md,
            "analise_json": json.loads(analise_json_str),
            "analise_updated_at": now,
        })

    except Exception as e:
        db.execute(
            "UPDATE processos_detectados SET analise_updated_at = NULL WHERE id = ? AND analise_updated_at = 'generating'",
            (processo_id,),
        )
        db.commit()
        logger.exception(f"Erro ao gerar analise: {e}")
        return jsonify({"error": str(e)[:300]}), 500


@workspace_bp.route("/workspaces/<slug>/processos/<int:processo_id>/chat", methods=["POST"])
def chat_processo(slug, processo_id):
    """SSE streaming chat escopado a um processo — usa modo duvida com contexto do processo."""
    db = _get_db(slug)

    row = db.execute(
        "SELECT id, nome, tipo, descricao, tabelas, analise_json "
        "FROM processos_detectados WHERE id = ?",
        (processo_id,),
    ).fetchone()
    if not row:
        return jsonify({"error": "Processo nao encontrado"}), 404

    data = request.get_json()
    message = data.get("message", "")
    if not message:
        return jsonify({"error": "Mensagem vazia"}), 400

    proc_nome = row[1]
    proc_tabelas = json.loads(row[4]) if row[4] else []
    analise_json = row[5] or "{}"

    # Salvar mensagem do usuario
    db.execute(
        "INSERT INTO processo_mensagens (processo_id, role, content) VALUES (?, 'user', ?)",
        (processo_id, message),
    )
    db.commit()

    # Carregar historico (ultimas 30)
    hist_rows = db.execute(
        "SELECT role, content FROM processo_mensagens WHERE processo_id = ? ORDER BY id DESC LIMIT 30",
        (processo_id,),
    ).fetchall()
    hist_rows = list(reversed(hist_rows))

    def generate():
        yield f"data: {json.dumps({'event': 'status', 'step': 'Investigando contexto do processo...'}, ensure_ascii=False)}\n\n"

        # Fase 1: Contexto do processo
        ks = KnowledgeService(db)
        tool_results_parts = []
        for tab in proc_tabelas[:5]:
            try:
                info = ks.get_table_info(tab)
                if info:
                    tool_results_parts.append(f"Info {tab}: {json.dumps(info, ensure_ascii=False)}")
            except Exception:
                pass

        # Operacoes de escrita
        for tab in proc_tabelas[:5]:
            try:
                ops_rows = db.execute(
                    "SELECT arquivo, funcao, tipo, campos, condicao FROM operacoes_escrita WHERE upper(tabela) = ? LIMIT 20",
                    (tab.upper(),)
                ).fetchall()
                if ops_rows:
                    ops_list = [{"arquivo": r[0], "funcao": r[1], "tipo": r[2], "campos": r[3], "condicao": r[4]} for r in ops_rows]
                    tool_results_parts.append(f"Operacoes escrita {tab}: {json.dumps(ops_list, ensure_ascii=False)}")
            except Exception:
                pass

        tool_results_text = "\n".join(tool_results_parts)

        context = f"""PROCESSO: {proc_nome}
Tabelas: {', '.join(proc_tabelas)}
Analise tecnica existente (JSON): {analise_json}
"""

        system_prompt = (
            "Voce e um consultor tecnico senior de ambientes TOTVS Protheus.\n"
            "Use APENAS os dados do CONTEXTO abaixo. Nao invente dados.\n"
            "Responda com informacoes CONCRETAS.\n\n"
            f"CONTEXTO DO AMBIENTE:\n{context}\n\n"
            f"DADOS DE INVESTIGACAO:\n{tool_results_text}\n"
        )

        messages = [{"role": "system", "content": system_prompt}]
        for h_role, h_content in hist_rows:
            messages.append({"role": h_role, "content": h_content})

        # Fase 2: Stream LLM
        yield f"data: {json.dumps({'event': 'status', 'step': 'Gerando resposta...'}, ensure_ascii=False)}\n\n"

        full_text = ""
        try:
            llm = _get_llm_provider()

            if hasattr(llm, 'chat_stream'):
                for chunk_data in llm.chat_stream(messages):
                    chunk_text = chunk_data.get("chunk", "") if isinstance(chunk_data, dict) else str(chunk_data)
                    if chunk_text:
                        full_text += chunk_text
                        yield f"data: {json.dumps({'event': 'content', 'text': chunk_text}, ensure_ascii=False)}\n\n"
            else:
                full_text = _llm_chat_text(llm, messages)
                yield f"data: {json.dumps({'event': 'content', 'text': full_text}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'event': 'error', 'error': str(e)[:300]}, ensure_ascii=False)}\n\n"
            return

        # Fase 3: Salvar resposta do assistente
        try:
            db2 = _get_db(slug)
            db2.execute(
                "INSERT INTO processo_mensagens (processo_id, role, content) VALUES (?, 'assistant', ?)",
                (processo_id, full_text),
            )
            db2.commit()

            # Fase 4: Enriquecimento heuristico (max 3 complementos)
            existing_analysis = json.loads(analise_json) if analise_json and analise_json != "{}" else None
            if existing_analysis and any(kw in full_text.lower() for kw in ["reclock", "gatilho", "trigger", "ponto de entrada", "pe_", "u_"]):
                existing_md = db2.execute(
                    "SELECT analise_markdown FROM processos_detectados WHERE id = ?",
                    (processo_id,),
                ).fetchone()
                enrichment_count = (existing_md[0] or "").count("## Complemento via Chat") if existing_md else 0
                if enrichment_count < 3:
                    db2.execute(
                        """UPDATE processos_detectados
                        SET analise_markdown = COALESCE(analise_markdown, '') || char(10) || char(10) || '## Complemento via Chat' || char(10) || ?,
                            analise_updated_at = datetime('now')
                        WHERE id = ?""",
                        (full_text[:2000], processo_id),
                    )
                    db2.commit()
            db2.close()
        except Exception as e:
            logger.warning("Erro ao salvar resposta do chat de processo: %s", e)

        yield f"data: {json.dumps({'event': 'done', 'status': 'ok'}, ensure_ascii=False)}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        }
    )


@workspace_bp.route("/workspaces/<slug>/processos/<int:processo_id>/mensagens", methods=["GET"])
def listar_mensagens_processo(slug, processo_id):
    """Lista mensagens de chat de um processo."""
    db = _get_db(slug)
    limit = request.args.get("limit", 30, type=int)
    offset = request.args.get("offset", 0, type=int)

    try:
        total = db.execute(
            "SELECT COUNT(*) FROM processo_mensagens WHERE processo_id = ?",
            (processo_id,),
        ).fetchone()[0]
        rows = db.execute(
            "SELECT id, role, content, created_at FROM processo_mensagens "
            "WHERE processo_id = ? ORDER BY id DESC LIMIT ? OFFSET ?",
            (processo_id, limit, offset),
        ).fetchall()
        mensagens = [
            {"id": r[0], "role": r[1], "content": r[2], "created_at": r[3]}
            for r in reversed(rows)
        ]
        return jsonify({"total": total, "mensagens": mensagens})
    except Exception:
        return jsonify({"total": 0, "mensagens": []})


@workspace_bp.route("/workspaces/<slug>/processos/registrar", methods=["POST"])
def registrar_processo(slug):
    """Registra ou enriquece um processo a partir de descricao livre (usa LLM para classificar)."""
    data = request.get_json()
    descricao = data.get("descricao", "")
    if not descricao:
        return jsonify({"error": "Descricao vazia"}), 400

    # Fase 1: Extrair info via LLM
    try:
        llm = _get_llm_provider()
    except Exception as e:
        return jsonify({"error": f"LLM nao disponivel: {str(e)[:200]}"}), 500

    extract_prompt = f"""Extraia as informacoes de processo de negocio do texto abaixo.
Retorne APENAS um JSON:
{{"nome": "Nome do Processo", "tipo": "workflow|integracao|logistica|fiscal|automacao|qualidade|outro", "descricao": "descricao limpa", "tabelas": ["TAB1", "TAB2"], "criticidade": "alta|media|baixa"}}

Texto: {descricao}"""

    try:
        text = _llm_chat_text(llm, [{"role": "user", "content": extract_prompt}])
        json_match = re.search(r'\{[\s\S]*\}', text)
        if not json_match:
            return jsonify({"error": "LLM nao retornou JSON valido"}), 500
        extracted = json.loads(json_match.group())
    except Exception as e:
        return jsonify({"error": f"Erro ao classificar processo: {str(e)[:200]}"}), 500

    # Fase 2: Registrar via handler do agent_tools
    from app.services.workspace.agent_tools import _handle_registrar_processo
    result = _handle_registrar_processo({
        "workspace_slug": slug,
        "nome": extracted.get("nome", descricao[:80]),
        "tipo": extracted.get("tipo", "outro"),
        "descricao": extracted.get("descricao", descricao),
        "tabelas": ",".join(extracted.get("tabelas", [])),
        "criticidade": extracted.get("criticidade", "media"),
    })

    if result.get("success"):
        return jsonify(result["data"])
    return jsonify({"error": result.get("error", "Erro desconhecido")}), 500
