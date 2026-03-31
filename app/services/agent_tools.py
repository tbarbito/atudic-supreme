"""
Agent Tools — Ferramentas que o agente pode executar no sistema.

REGRA: O agente é apenas um ORQUESTRADOR. Ele NUNCA implementa lógica
própria — sempre chama os serviços e funções que já existem no BiizHubOps.

Modularizado em:
- app/services/tools/helpers.py — _internal_api, _serialize_rows, _check_permission
- app/services/tools/formatters.py — format_tool_result_for_llm e _format_*
Este arquivo mantém registry, handlers e init_tools() para retrocompatibilidade.
"""

import json
import os
import re
import logging
from datetime import datetime, timedelta

from app.database import get_db, release_db_connection

# Importar helpers e formatters dos submodulos
from app.services.tools.helpers import (
    _internal_api, _serialize_rows, _check_permission, PROFILE_LEVELS,
)
from app.services.tools.formatters import format_tool_result_for_llm
from app.services.tools.connection_resolver import resolve_connection_params

logger = logging.getLogger(__name__)


AGENT_TOOLS = {}


def register_tool(name, description, parameters, min_profile, handler,
                   requires_confirmation=False, risk_level=None):
    """Registra uma ferramenta no registry.

    Args:
        risk_level: "low" (leitura/consulta), "medium" (CRUD em homolog),
                    "high" (deploy, execução em produção, alteração de dados críticos).
                    Se None, infere a partir de requires_confirmation.
    """
    if risk_level is None:
        risk_level = "high" if requires_confirmation else "low"

    AGENT_TOOLS[name] = {
        "name": name,
        "description": description,
        "parameters": parameters,
        "min_profile": min_profile,
        "handler": handler,
        "requires_confirmation": requires_confirmation,
        "risk_level": risk_level,
    }


def get_available_tools(user_profile="viewer"):
    """Retorna ferramentas disponíveis para o perfil do usuário."""
    tools = []
    for tool in AGENT_TOOLS.values():
        if _check_permission(user_profile, tool["min_profile"]):
            tools.append(
                {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["parameters"],
                    "risk_level": tool.get("risk_level", "low"),
                }
            )
    return tools


# Mapa de fallback: se tool X falha, tentar tool Y
FALLBACK_MAP = {
    "get_alerts": ["search_knowledge"],
    "get_alert_summary": ["get_alerts"],
    "get_recurring_errors": ["search_knowledge"],
    "get_pipeline_status": ["get_pipelines"],
    "query_database": ["search_knowledge"],
    "get_services": [],
    "get_repositories": [],
    "run_pipeline": [],
    "create_release": ["get_pipeline_status"],
    "execute_service_action": [],
    "git_pull": [],
}


def execute_tool(tool_name, params, user_profile="viewer", environment_id=None, user_id=None, session_id=None):
    """Executa uma ferramenta e retorna o resultado.

    Inclui inferencia global de params: se um param esta faltando mas foi
    usado em uma tool call anterior da sessao, reutiliza automaticamente.
    """
    tool = AGENT_TOOLS.get(tool_name)
    if not tool:
        return {"error": f"Ferramenta '{tool_name}' não encontrada."}

    if not _check_permission(user_profile, tool["min_profile"]):
        return {
            "error": f"Sem permissão. Perfil '{user_profile}' não pode executar '{tool_name}' (requer '{tool['min_profile']}')."
        }

    if environment_id and "environment_id" not in params:
        params["environment_id"] = environment_id
    if user_id and "user_id" not in params:
        params["user_id"] = user_id

    # Inferir params faltantes do historico da sessao (global, todas as tools)
    if session_id:
        try:
            from app.services.agent_working_memory import get_working_memory
            wm = get_working_memory()
            params, inferred = wm.infer_missing_params(session_id, tool_name, params)
            if inferred:
                logger.info("Params inferidos da sessao: %s", "; ".join(inferred))
        except Exception as e:
            logger.debug("Inferencia de params falhou: %s", e)

    # Resolver aliases de conexao (HML, PRD, etc.) para IDs reais
    params, conn_resolutions = resolve_connection_params(params, environment_id)
    if conn_resolutions:
        logger.info("Conexoes resolvidas: %s", "; ".join(conn_resolutions))

    # Registrar tool call no historico da sessao (para inferencia futura)
    if session_id:
        try:
            from app.services.agent_working_memory import get_working_memory
            wm = get_working_memory()
            wm.record_tool_call(session_id, tool_name, params)
        except Exception:
            pass

    try:
        result = tool["handler"](params)

        # Se foi preview, salvar token + sql_statements no historico para auto-execute
        if session_id and tool_name in ("preview_equalization", "preview_ingestion"):
            try:
                preview_data = result if isinstance(result, dict) else {}
                if "preview" in preview_data and isinstance(preview_data["preview"], dict):
                    preview_data = preview_data["preview"]

                token = preview_data.get("confirmation_token")
                sql_stmts = preview_data.get("phase1_ddl", []) + preview_data.get("phase2_dml", [])

                if token:
                    from app.services.agent_working_memory import get_working_memory
                    wm = get_working_memory()
                    wm.record_tool_call(session_id, tool_name, {
                        **params,
                        "confirmation_token": token,
                        "_sql_statements": sql_stmts,
                    })
                    logger.info("Preview salvo: token=%s... stmts=%d", token[:10], len(sql_stmts))
            except Exception:
                pass

        return {"success": True, "data": result}
    except Exception as e:
        logger.error("Erro ao executar tool %s: %s", tool_name, e)
        original_error = str(e)

        # Tentar fallback se disponível
        fallbacks = FALLBACK_MAP.get(tool_name, [])
        for fb_name in fallbacks:
            fb_tool = AGENT_TOOLS.get(fb_name)
            if not fb_tool or not _check_permission(user_profile, fb_tool["min_profile"]):
                continue

            fb_params = _adapt_fallback_params(tool_name, fb_name, params)
            try:
                fb_result = fb_tool["handler"](fb_params)
                logger.info("🔄 Fallback: %s falhou → %s executado", tool_name, fb_name)
                return {
                    "success": True,
                    "data": fb_result,
                    "fallback": True,
                    "fallback_tool": fb_name,
                    "original_tool": tool_name,
                    "warning": f"⚠️ {tool_name} indisponível, dados via {fb_name}",
                }
            except Exception as fb_e:
                logger.debug("Fallback %s também falhou: %s", fb_name, fb_e)

        return {"error": f"Erro ao executar '{tool_name}': {original_error}"}


def _adapt_fallback_params(original_tool, fallback_tool, params):
    """Adapta parâmetros da tool original para o formato do fallback."""
    fb_params = dict(params)

    if fallback_tool == "search_knowledge":
        query_parts = []
        for key in ("category", "severity", "query"):
            if params.get(key):
                query_parts.append(str(params[key]))
        if params.get("pipeline_id"):
            query_parts.append(f"pipeline {params['pipeline_id']}")
        fb_params["query"] = " ".join(query_parts) if query_parts else "erro recente"
        fb_params["limit"] = params.get("limit", 5)
    elif fallback_tool == "get_pipelines":
        fb_params.pop("pipeline_id", None)
    elif fallback_tool == "get_alerts":
        fb_params["limit"] = params.get("limit", 10)

    return fb_params


# Formatação e serialização movidas para tools/formatters.py e tools/helpers.py
# _serialize_rows, _format_*, format_tool_result_for_llm importados no topo




# =====================================================================
# FERRAMENTAS DE LEITURA (9F-1)
# Queries simples de listagem — sem lógica de negócio duplicada
# =====================================================================


def _tool_get_environments(params):
    """Lista ambientes."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, name, description, created_at FROM environments ORDER BY id")
        rows = _serialize_rows([dict(r) for r in cursor.fetchall()])
        return {"environments": rows, "total": len(rows)}
    finally:
        release_db_connection(conn)


def _tool_get_pipelines(params):
    """Lista pipelines configurados."""
    env_id = params.get("environment_id")
    conn = get_db()
    cursor = conn.cursor()
    try:
        query = "SELECT id, name, description, environment_id, status, is_protected FROM pipelines"
        args = []
        if env_id:
            query += " WHERE environment_id = %s"
            args.append(env_id)
        query += " ORDER BY name"
        cursor.execute(query, tuple(args))
        return {"pipelines": [dict(r) for r in cursor.fetchall()], "total": cursor.rowcount}
    finally:
        release_db_connection(conn)


def _tool_get_pipeline_status(params):
    """Lista execuções recentes de pipelines."""
    env_id = params.get("environment_id")
    limit = min(int(params.get("limit", 10)), 50)
    conn = get_db()
    cursor = conn.cursor()
    try:
        query = """
            SELECT pr.id, pr.pipeline_id, p.name as pipeline_name,
                   pr.status, pr.started_at, pr.finished_at,
                   pr.started_by, pr.trigger_type
            FROM pipeline_runs pr
            JOIN pipelines p ON p.id = pr.pipeline_id
        """
        args = []
        if env_id:
            query += " WHERE p.environment_id = %s"
            args.append(env_id)
        query += " ORDER BY pr.started_at DESC LIMIT %s"
        args.append(limit)
        cursor.execute(query, tuple(args))
        rows = _serialize_rows([dict(r) for r in cursor.fetchall()])

        # human_summary: ~80 tokens vs ~400
        summary_lines = [f"{len(rows)} execução(ões) de pipeline."]
        for r in rows[:5]:
            name = r.get("pipeline_name", "?")
            status = r.get("status", "?")
            started = str(r.get("started_at", ""))[:16]
            summary_lines.append(f"- {name}: {status} ({started})")

        return {"pipeline_runs": rows, "total": len(rows), "human_summary": "\n".join(summary_lines)}
    finally:
        release_db_connection(conn)


def _tool_get_alerts(params):
    """Lista alertas recentes."""
    env_id = params.get("environment_id")
    limit = min(int(params.get("limit", 10)), 50)
    severity = params.get("severity")
    category = params.get("category")
    conn = get_db()
    cursor = conn.cursor()
    try:
        query = "SELECT id, category, severity, message, source_file, thread_id, created_at, acknowledged FROM log_alerts WHERE 1=1"
        args = []
        if env_id:
            query += " AND environment_id = %s"
            args.append(env_id)
        if severity:
            query += " AND severity = %s"
            args.append(severity)
        if category:
            query += " AND category = %s"
            args.append(category)
        query += " ORDER BY created_at DESC LIMIT %s"
        args.append(limit)
        cursor.execute(query, tuple(args))
        rows = _serialize_rows([dict(r) for r in cursor.fetchall()])

        # human_summary: formato compacto para o LLM (~100 tokens vs ~500)
        summary_lines = [f"{len(rows)} alerta(s) encontrado(s)."]
        for r in rows[:5]:
            summary_lines.append(
                f"- [{r.get('severity', '?')}] {r.get('category', '?')}: {str(r.get('message', ''))[:100]}"
            )
        if len(rows) > 5:
            summary_lines.append(f"... e mais {len(rows) - 5} alertas.")

        return {"alerts": rows, "total": len(rows), "human_summary": "\n".join(summary_lines)}
    finally:
        release_db_connection(conn)


def _tool_get_alert_summary(params):
    """Resumo de alertas por categoria e severidade."""
    env_id = params.get("environment_id")
    days = min(int(params.get("days", 7)), 30)
    conn = get_db()
    cursor = conn.cursor()
    try:
        since = datetime.now() - timedelta(days=days)
        query = "SELECT category, severity, COUNT(*) as count FROM log_alerts WHERE created_at >= %s"
        args = [since]
        if env_id:
            query += " AND environment_id = %s"
            args.append(env_id)
        query += " GROUP BY category, severity ORDER BY count DESC"
        cursor.execute(query, tuple(args))
        rows = [dict(r) for r in cursor.fetchall()]
        total = sum(r["count"] for r in rows)

        # human_summary: ~80 tokens vs ~300
        summary_lines = [f"Resumo de alertas ({days} dias): {total} total."]
        for r in rows[:8]:
            summary_lines.append(f"- {r['category']} [{r['severity']}]: {r['count']}x")

        return {
            "summary": rows,
            "total_alerts": total,
            "period_days": days,
            "human_summary": "\n".join(summary_lines),
        }
    finally:
        release_db_connection(conn)


def _tool_get_recurring_errors(params):
    """Lista erros recorrentes — REUTILIZA knowledge_base.get_recurring_errors()."""
    from app.services.knowledge_base import get_recurring_errors

    env_id = params.get("environment_id")
    days = min(int(params.get("days", 7)), 30)
    min_count = max(int(params.get("min_count", 3)), 2)
    results = get_recurring_errors(environment_id=env_id, min_count=min_count, days=days, limit=20)
    return {"recurring_errors": results or [], "total": len(results or []), "period_days": days}


def _tool_get_repositories(params):
    """Lista repositórios."""
    env_id = params.get("environment_id")
    conn = get_db()
    cursor = conn.cursor()
    try:
        query = (
            "SELECT id, name, html_url, clone_url, default_branch, private, environment_id FROM repositories WHERE 1=1"
        )
        args = []
        if env_id:
            query += " AND environment_id = %s"
            args.append(env_id)
        query += " ORDER BY name"
        cursor.execute(query, tuple(args))
        return {"repositories": [dict(r) for r in cursor.fetchall()], "total": cursor.rowcount}
    finally:
        release_db_connection(conn)


def _tool_get_services(params):
    """Lista serviços monitorados e ações disponíveis (start/stop/restart)."""
    env_id = params.get("environment_id")
    conn = get_db()
    cursor = conn.cursor()
    try:
        query = "SELECT id, name, display_name, server_name, environment_id, is_active FROM server_services"
        args = []
        if env_id:
            query += " WHERE environment_id = %s"
            args.append(env_id)
        query += " ORDER BY name"
        cursor.execute(query, tuple(args))
        services = [dict(r) for r in cursor.fetchall()]

        # Incluir ações disponíveis (service_actions) para o agente saber os action_ids
        actions = []
        act_query = """
            SELECT id as action_id, name, description, action_type, os_type,
                   service_ids, force_stop
            FROM service_actions
        """
        act_args = []
        if env_id:
            act_query += " WHERE environment_id = %s"
            act_args.append(env_id)
        act_query += " ORDER BY name"
        cursor.execute(act_query, tuple(act_args))
        actions = [dict(r) for r in cursor.fetchall()]

        return {
            "services": services,
            "actions": actions,
            "total_services": len(services),
            "total_actions": len(actions),
            "hint": "Para executar uma ação, use execute_service_action com o action_id da ação desejada",
        }
    finally:
        release_db_connection(conn)


def _tool_get_schedules(params):
    """Lista agendamentos."""
    env_id = params.get("environment_id")
    conn = get_db()
    cursor = conn.cursor()
    try:
        query = """
            SELECT s.id, s.name, s.pipeline_id, p.name as pipeline_name,
                   s.schedule_type, s.schedule_config, s.is_active,
                   s.last_run_at, s.next_run_at
            FROM pipeline_schedules s
            JOIN pipelines p ON p.id = s.pipeline_id
        """
        args = []
        if env_id:
            query += " WHERE s.environment_id = %s"
            args.append(env_id)
        query += " ORDER BY s.name"
        cursor.execute(query, tuple(args))
        rows = _serialize_rows([dict(r) for r in cursor.fetchall()])
        return {"schedules": rows, "total": len(rows)}
    finally:
        release_db_connection(conn)


def _tool_get_server_variables(params):
    """Lista variáveis de servidor (senhas mascaradas).

    Se environment_id esta no contexto, filtra variaveis pelo sufixo
    do ambiente ativo (_HOM, _PRD, _DEV, _TST) + variaveis globais.
    """
    env_id = params.get("environment_id")
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT id, name, value, description, is_password, is_protected FROM server_variables ORDER BY name"
        )
        rows = [dict(r) for r in cursor.fetchall()]
        for row in rows:
            if row.get("is_password"):
                row["value"] = "********"

        # Filtrar pelo ambiente ativo se informado
        env_suffix = None
        if env_id:
            cursor.execute("SELECT name FROM environments WHERE id = %s", (env_id,))
            env_row = cursor.fetchone()
            if env_row:
                env_name = env_row["name"].lower()
                suffix_map = {
                    "homolog": "_HOM", "hom": "_HOM",
                    "producao": "_PRD", "prod": "_PRD", "prd": "_PRD",
                    "desenvolvimento": "_DEV", "dev": "_DEV",
                    "teste": "_TST", "tst": "_TST", "test": "_TST",
                }
                for key, suffix in suffix_map.items():
                    if key in env_name:
                        env_suffix = suffix
                        break

        if env_suffix:
            # Variaveis do ambiente + globais (sem sufixo de outro ambiente)
            all_suffixes = {"_HOM", "_PRD", "_DEV", "_TST"}
            other_suffixes = all_suffixes - {env_suffix}
            filtered = []
            for row in rows:
                name = row["name"]
                is_other = any(name.endswith(s) for s in other_suffixes)
                if not is_other:
                    filtered.append(row)
            rows = filtered

        # human_summary compacto
        summary_lines = [f"{len(rows)} variavel(is) do ambiente{(' (' + env_suffix + ')') if env_suffix else ''}."]
        for r in rows[:20]:
            val = r["value"] if not r.get("is_password") else "********"
            summary_lines.append(f"- {r['name']} = {val}")
        if len(rows) > 20:
            summary_lines.append(f"... e mais {len(rows) - 20} variaveis.")

        return {"variables": rows, "total": len(rows), "human_summary": "\n".join(summary_lines)}
    finally:
        release_db_connection(conn)


def _tool_get_db_connections(params):
    """Lista conexoes de banco — mostra TODAS com indicacao de ambiente.

    O agente precisa ver conexoes de outros ambientes para comparacoes
    (ex: PRD cadastrada no HOM para consulta cruzada).
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT dc.id, dc.name, dc.driver, dc.host, dc.port,
                   dc.database_name, dc.username, dc.environment_id,
                   dc.is_readonly, COALESCE(e.name, '') as environment_name
            FROM database_connections dc
            LEFT JOIN environments e ON e.id = dc.environment_id
            ORDER BY dc.name
        """)
        rows = [dict(r) for r in cursor.fetchall()]

        # human_summary com ambiente indicado
        summary_lines = [f"{len(rows)} conexao(oes) de banco configuradas."]
        for r in rows:
            env_label = f" [{r.get('environment_name', '')}]" if r.get('environment_name') else ""
            readonly = " (somente leitura)" if r.get("is_readonly") else ""
            summary_lines.append(
                f"- {r['name']}{env_label}: {r['driver']} {r['host']}:{r['port']}/{r['database_name']}{readonly}"
            )
        return {"connections": rows, "total": len(rows), "human_summary": "\n".join(summary_lines)}
    finally:
        release_db_connection(conn)


def _tool_search_knowledge(params):
    """Busca na KB — REUTILIZA knowledge_base.search_articles()."""
    from app.services.knowledge_base import search_articles

    query = params.get("query", "")
    if not query:
        return {"error": "Parâmetro 'query' é obrigatório."}
    category = params.get("category")
    limit = min(int(params.get("limit", 5)), 20)
    results = search_articles(query, category=category, limit=limit)
    # Truncar para não estourar contexto LLM
    for r in results or []:
        for field in ("description", "solution", "causes"):
            if r.get(field) and len(r[field]) > 500:
                r[field] = r[field][:500] + "..."
    return {"articles": results or [], "total": len(results or [])}


def _tool_search_tdn(params):
    """Busca na base TDN (TOTVS Developer Network) — 182K+ chunks de documentacao oficial.

    Busca em duas camadas:
    1. PostgreSQL tsvector (full-text search portugues com ranking)
    2. Fallback ILIKE se tsvector nao encontrar

    Fontes disponiveis: advpl, tlpp, tss, framework, protheus12, totvstec
    """
    query = params.get("query", "")
    if not query:
        return {"error": "Parametro 'query' e obrigatorio."}

    source = params.get("source")  # Filtrar por fonte (ex: "protheus12", "advpl")
    limit = min(int(params.get("limit", 5)), 10)

    results = []

    # Busca 1: PostgreSQL tsvector (chunks pesados — framework, protheus12, totvstec)
    try:
        from app.services.tdn_ingestor import TDNIngestor
        ingestor = TDNIngestor()
        pg_results = ingestor.search(query, source=source, limit=limit)
        if pg_results:
            results.extend(pg_results)
    except Exception as e:
        logger.debug("Busca TDN PG falhou: %s", e)

    # Busca 2: SQLite FTS5 BM25 (chunks leves — advpl local, tlpp local, tss local)
    if len(results) < limit:
        try:
            from app.services.agent_memory import AgentMemoryService
            memory = AgentMemoryService()
            bm25_results = memory.search_bm25(query, chunk_type="semantic", limit=limit - len(results))
            for r in bm25_results or []:
                results.append(r)
        except Exception as e:
            logger.debug("Busca TDN BM25 falhou: %s", e)

    # Formatar para o LLM
    formatted = []
    for r in results[:limit]:
        if isinstance(r, dict):
            entry = {
                "title": r.get("page_title") or r.get("section_title") or "",
                "section": r.get("section_title") or "",
                "content": (r.get("content") or "")[:800],
                "source": r.get("source") or "",
                "url": r.get("page_url") or "",
            }
        else:
            # Row do cursor PostgreSQL
            entry = {
                "title": r.get("page_title", "") if hasattr(r, "get") else str(r),
                "section": r.get("section_title", "") if hasattr(r, "get") else "",
                "content": (r.get("content", "") if hasattr(r, "get") else "")[:800],
                "source": r.get("source", "") if hasattr(r, "get") else "",
                "url": r.get("page_url", "") if hasattr(r, "get") else "",
            }
        formatted.append(entry)

    return {
        "results": formatted,
        "total": len(formatted),
        "query": query,
        "source_filter": source,
    }


def _tool_get_users(params):
    """Lista usuários."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT id, username, name, email, profile, active, last_login, session_timeout_minutes FROM users ORDER BY username"
        )
        rows = _serialize_rows([dict(r) for r in cursor.fetchall()])
        return {"users": rows, "total": len(rows)}
    finally:
        release_db_connection(conn)


# =====================================================================
# FERRAMENTAS DE AÇÃO (9F-2)
# REGRA: Apenas orquestrar — chamar serviços/routes existentes
# =====================================================================


def _tool_run_pipeline(params):
    """Dispara pipeline — chama POST /api/pipelines/<id>/run (mesma API do frontend)."""
    pipeline_id = params.get("pipeline_id")
    if not pipeline_id:
        return {"error": "Parâmetro 'pipeline_id' é obrigatório."}

    env_id = params.get("environment_id")
    headers = {}
    if env_id:
        headers["X-Environment-Id"] = str(env_id)

    return _internal_api("POST", f"/api/pipelines/{pipeline_id}/run", headers=headers)


def _tool_create_release(params):
    """Cria release (deploy) a partir de um run bem-sucedido — chama POST /api/runs/<id>/release."""
    run_id = params.get("run_id")
    if not run_id:
        return {"error": "Parâmetro 'run_id' é obrigatório."}

    env_id = params.get("environment_id")
    headers = {}
    if env_id:
        headers["X-Environment-Id"] = str(env_id)

    return _internal_api("POST", f"/api/runs/{run_id}/release", headers=headers)


def _tool_execute_service_action(params):
    """Executa service action — chama POST /api/service-actions/<id>/execute."""
    action_id = params.get("action_id")
    env_id = params.get("environment_id")
    if not action_id:
        return {"error": "Parâmetro 'action_id' é obrigatório."}
    if not env_id:
        return {"error": "Parâmetro 'environment_id' é obrigatório."}

    return _internal_api("POST", f"/api/service-actions/{action_id}/execute", headers={"X-Environment-Id": str(env_id)})


def _tool_acknowledge_alert(params):
    """Marca alerta como visto — chama POST /api/log-alerts/<id>/acknowledge."""
    alert_id = params.get("alert_id")
    if not alert_id:
        return {"error": "Parâmetro 'alert_id' é obrigatório."}

    return _internal_api("POST", f"/api/log-alerts/{alert_id}/acknowledge")


def _tool_acknowledge_alerts_bulk(params):
    """Reconhece alertas em lote — chama POST /api/log-alerts/acknowledge-bulk."""
    alert_ids = params.get("alert_ids", [])
    if not alert_ids:
        return {"error": "Parâmetro 'alert_ids' (lista) é obrigatório."}

    return _internal_api("POST", "/api/log-alerts/acknowledge-bulk", json_body={"alert_ids": alert_ids})


def _tool_toggle_schedule(params):
    """Toggle agendamento — chama PATCH /api/schedules/<id>/toggle."""
    schedule_id = params.get("schedule_id")
    env_id = params.get("environment_id")
    if not schedule_id:
        return {"error": "Parâmetro 'schedule_id' é obrigatório."}

    headers = {}
    if env_id:
        headers["X-Environment-Id"] = str(env_id)

    return _internal_api("PATCH", f"/api/schedules/{schedule_id}/toggle", headers=headers)


def _tool_git_pull(params):
    """Git pull — chama POST /api/repositories/<id>/pull (mesma API do frontend)."""
    repo_id = params.get("repo_id")
    branch = params.get("branch")
    if not repo_id:
        return {"error": "Parâmetro 'repo_id' é obrigatório."}

    body = {}
    if branch:
        body["branch_name"] = branch
    else:
        # Buscar default_branch do repo
        conn = get_db()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT default_branch FROM repositories WHERE id = %s", (repo_id,))
            row = cursor.fetchone()
            body["branch_name"] = row["default_branch"] if row else "main"
        finally:
            release_db_connection(conn)

    return _internal_api("POST", f"/api/repositories/{repo_id}/pull", json_body=body)


# =====================================================================
# FERRAMENTAS ADMIN (9F-3)
# REGRA: Reutilizar serviços existentes
# =====================================================================


def _tool_query_database(params):
    """Executa SELECT — chama POST /api/db-connections/<id>/query.

    Suporta dois modos:
    1. Template (recomendado): {"template": "parametro", "param_name": "MV_ESTNEG"}
       O codigo monta o SQL com sufixo correto automaticamente.
    2. Query raw: {"query": "SELECT ..."}
       Inclui auto-correcao de sufixo Protheus.
    """
    conn_id = params.get("connection_id")
    template_name = params.get("template")
    query_text = params.get("query", "").strip()
    max_rows = min(int(params.get("max_rows", 100)), 500)

    if not conn_id:
        return {"error": "Parâmetro 'connection_id' é obrigatório."}

    # Modo template: resolver query via template Protheus
    if template_name:
        from app.services.tools.query_templates import resolve_template
        from app.services.tools.context_precompute import _precompute_cache

        # Buscar contexto pre-computado do ambiente
        env_id = params.get("environment_id")
        precomputed = _precompute_cache.get(int(env_id), {}) if env_id else {}

        # Se nao tem precomputed, tentar montar um minimo com discovery
        if not precomputed.get("companies"):
            companies = _discover_protheus_companies(conn_id)
            if companies:
                precomputed["companies"] = {
                    conn_id: [{"code": c["code"], "name": c["name"], "suffix": f"{c['code']}0"} for c in companies]
                }

        sql, error = resolve_template(template_name, params, conn_id, precomputed)
        if error:
            return {"error": error}
        query_text = sql

    if not query_text:
        return {"error": "Parâmetro 'query' ou 'template' é obrigatório."}

    _re = re  # usar o re ja importado no topo do modulo

    # Tabelas que NAO seguem regra de sufixo
    _SUFFIX_EXCEPTIONS = {
        "SYS_COMPANY", "TOP_FIELD", "INFORMATION_SCHEMA", "SYSOBJECTS",
        "SYSINDEXES", "SYSCOLUMNS", "SYSTYPES",
    }

    # Detectar TODAS as tabelas Protheus na query (com ou sem sufixo)
    # Padroes: SX6 (sem sufixo), SX6010 (com sufixo), SA1990 (com sufixo)
    # Formato: 2-3 letras + 1 digito + opcionalmente 2-3 digitos de sufixo
    _protheus_tables = _re.findall(
        r'\b(?:FROM|JOIN)\s+(?:dbo\.|DBO\.)?([A-Z]{2,3}\d\d{0,3})\b',
        query_text.upper(),
    )
    _protheus_tables = [t for t in _protheus_tables if t.upper() not in _SUFFIX_EXCEPTIONS]

    # Auto-descobrir empresas para validar/corrigir sufixo
    if _protheus_tables:
        companies = _discover_protheus_companies(conn_id)

        if companies is not None and len(companies) > 0:
            # Montar sufixos validos
            valid_suffixes = {f"{c['code'].strip()}0" for c in companies}

            # Verificar se as tabelas tem sufixo valido
            needs_correction = False
            for table in _protheus_tables:
                # Extrair prefixo base (2-3 letras + 1 digito) e sufixo
                match = _re.match(r'^([A-Z]{2,3}\d)(\d*)$', table)
                if match:
                    base, current_suffix = match.group(1), match.group(2)
                    if not current_suffix or current_suffix not in valid_suffixes:
                        needs_correction = True
                        break

            if needs_correction:
                if len(companies) == 1:
                    # Auto-corrigir com o unico sufixo valido
                    code = companies[0]["code"].strip()
                    suffix = f"{code}0"
                    corrected_query = query_text
                    for table in _protheus_tables:
                        match = _re.match(r'^([A-Z]{2,3}\d)', table)
                        if match:
                            base = match.group(1)
                            # Substituir qualquer variacao (SX6, SX6010, SX60) pelo correto
                            corrected_query = _re.sub(
                                r'\b((?:dbo\.|DBO\.)?)'+ _re.escape(table) + r'\b',
                                r'\1' + base + suffix,
                                corrected_query,
                                flags=_re.IGNORECASE,
                            )
                    logger.info(
                        "🔧 Auto-correcao de sufixo Protheus: empresa %s → %s | query: %s",
                        code, suffix, corrected_query[:100],
                    )
                    query_text = corrected_query
                else:
                    # Multiplas empresas — perguntar ao usuario
                    company_list = ", ".join(
                        f"{c['code'].strip()} ({c.get('name', '').strip()})" for c in companies
                    )
                    return {
                        "error": (
                            f"Encontrei {len(companies)} empresas neste banco: {company_list}. "
                            f"Qual empresa deseja consultar? "
                            f"Informe o codigo da empresa para que eu monte a query corretamente."
                        ),
                        "companies": [{"code": c["code"].strip(), "name": c.get("name", "").strip()} for c in companies],
                    }

    # Executar a query
    result = _internal_api(
        "POST", f"/api/db-connections/{conn_id}/query", json_body={"query": query_text, "max_rows": max_rows}
    )

    # Se deu erro de "Invalid object name" — tentar auto-corrigir e re-executar
    if isinstance(result, dict) and result.get("error") and "Invalid object name" in str(result.get("error", "")):
        companies = _discover_protheus_companies(conn_id)
        if companies and len(companies) == 1:
            code = companies[0]["code"].strip()
            suffix = f"{code}0"
            # Tentar corrigir a query e re-executar
            corrected = _re.sub(
                r'\b((?:dbo\.|DBO\.)?)([A-Z]{2,3}\d)\d{0,3}\b',
                lambda m: m.group(1) + m.group(2) + suffix,
                query_text,
                flags=_re.IGNORECASE,
            )
            if corrected != query_text:
                logger.info("🔧 Re-tentativa com sufixo corrigido: %s", corrected[:100])
                retry_result = _internal_api(
                    "POST", f"/api/db-connections/{conn_id}/query",
                    json_body={"query": corrected, "max_rows": max_rows},
                )
                if isinstance(retry_result, dict) and not retry_result.get("error"):
                    retry_result["auto_corrected"] = True
                    retry_result["original_query"] = query_text
                    retry_result["corrected_query"] = corrected
                    result = retry_result
                    logger.info("✅ Query corrigida executou com sucesso")
        if isinstance(result, dict) and result.get("error"):
            # Ainda com erro — adicionar hint
            if companies:
                company_list = ", ".join(f"{c['code'].strip()}" for c in companies)
                result["hint"] = (
                    f"Tabela nao encontrada. Empresas disponiveis: {company_list}. "
                    f"O sufixo correto e TABELA + M0_CODIGO + 0 (ex: empresa 99 → SX6990)."
                )

    # Proteger contra resultado None
    if result is None:
        return {"error": "Sem resposta da API de query. Verifique se a conexao esta ativa."}

    # Truncar para contexto LLM
    if isinstance(result, dict) and result.get("rows") and len(result["rows"]) > 20:
        result["rows"] = result["rows"][:20]
        result["truncated_by_agent"] = True
        result["note"] = f"Mostrando 20 de {result.get('row_count', '?')} linhas."

    return result


def _discover_protheus_companies(conn_id):
    """Descobre empresas Protheus via SYS_COMPANY.

    Returns:
        list[dict]: [{"code": "99", "name": "Matriz"}] ou None se erro.
    """
    try:
        result = _internal_api(
            "POST",
            f"/api/db-connections/{conn_id}/query",
            json_body={
                "query": "SELECT M0_CODIGO, M0_NOME FROM SYS_COMPANY WHERE D_E_L_E_T_ = ' ' ORDER BY M0_CODIGO",
                "max_rows": 50,
            },
        )
        if result is None:
            return None
        if isinstance(result, dict) and result.get("rows"):
            companies = []
            for row in result["rows"]:
                code = row.get("M0_CODIGO", row.get("m0_codigo", ""))
                name = row.get("M0_NOME", row.get("m0_nome", ""))
                if code and str(code).strip():
                    companies.append({"code": str(code).strip(), "name": str(name).strip()})
            return companies
        return []
    except Exception as e:
        logger.warning("Erro ao consultar SYS_COMPANY na conexao %s: %s", conn_id, e)
        return None


def _tool_preview_equalization(params):
    """Preview de equalizacao com parsing robusto de items.

    O LLM pode enviar items como string JSON em vez de lista — este handler
    faz o parsing e logging para facilitar debug.
    """
    items = params.get("items", [])

    # Se items veio como string, tentar parsear como JSON
    if isinstance(items, str):
        try:
            items = json.loads(items)
            params["items"] = items
        except (json.JSONDecodeError, TypeError):
            return {"error": f"Parametro 'items' invalido. Esperava lista, recebeu string: {items[:200]}"}

    if not items or not isinstance(items, list):
        return {"error": "Parametro 'items' deve ser uma lista nao vazia de itens a equalizar."}

    # Normalizar campos para uppercase (o equalizador espera UPPER)
    for item in items:
        if "table_alias" in item:
            item["table_alias"] = str(item["table_alias"]).upper()
        if "field_name" in item:
            item["field_name"] = str(item["field_name"]).upper()
        if "meta_table" in item:
            item["meta_table"] = str(item["meta_table"]).upper()
        if "indice" in item:
            item["indice"] = str(item["indice"]).upper()

    logger.info(
        "🔧 Preview equalizacao: source=%s target=%s company=%s items=%d | %s",
        params.get("source_conn_id"), params.get("target_conn_id"),
        params.get("company_code"), len(items),
        json.dumps(items[:3], ensure_ascii=False, default=str)[:300],
    )

    return _internal_api("POST", "/api/dictionary/equalize/preview", params)


def _tool_execute_equalization(params):
    """Execucao de equalizacao com auto-redirect para preview.

    Se chamado sem confirmation_token, executa preview automaticamente
    em vez de dar erro — retorna o preview com instrucao de confirmar.
    """
    items = params.get("items", [])
    if isinstance(items, str):
        try:
            items = json.loads(items)
            params["items"] = items
        except (json.JSONDecodeError, TypeError):
            return {"error": f"Parametro 'items' invalido."}

    if not params.get("confirmation_token"):
        # Auto-redirect: fazer preview automaticamente
        logger.info("execute_equalization sem token — redirecionando para preview automatico")
        preview_result = _tool_preview_equalization(params)
        if isinstance(preview_result, dict) and preview_result.get("error"):
            return preview_result
        # Retornar preview com instrucao clara
        return {
            "auto_preview": True,
            "preview": preview_result,
            "message": (
                "Preview gerado automaticamente. Mostre os SQLs ao usuario e "
                "pergunte se deseja aplicar. Se confirmar, chame execute_equalization "
                "com o confirmation_token retornado no preview."
            ),
        }

    logger.info(
        "🔧 Execute equalizacao: source=%s target=%s company=%s token=%s items=%d",
        params.get("source_conn_id"), params.get("target_conn_id"),
        params.get("company_code"), params.get("confirmation_token", "")[:10],
        len(items) if isinstance(items, list) else 0,
    )

    return _internal_api("POST", "/api/dictionary/equalize/execute", params)


# =========================================================
# INGESTOR DE DICIONARIO — Handlers
# =========================================================


def _tool_upload_ingest_file(params):
    """Upload e parse de arquivo de ingestao de dicionario."""
    content = params.get("content", "")
    filename = params.get("filename", "ingest_file.json")

    if not content:
        return {"error": "Parametro 'content' e obrigatorio. Envie o conteudo do arquivo JSON ou MD."}

    logger.info(
        "📥 Upload ingest file: filename=%s content_len=%d",
        filename, len(content),
    )

    return _internal_api("POST", "/api/dictionary/ingest/upload", {
        "content": content,
        "filename": filename,
    })


def _tool_preview_ingestion(params):
    """Preview de ingestao com parsing robusto de items."""
    items = params.get("items", [])

    if isinstance(items, str):
        try:
            items = json.loads(items)
            params["items"] = items
        except (json.JSONDecodeError, TypeError):
            return {"error": f"Parametro 'items' invalido. Esperava lista, recebeu string: {str(items)[:200]}"}

    if not items or not isinstance(items, list):
        return {"error": "Parametro 'items' deve ser uma lista nao vazia. Faca upload_ingest_file primeiro."}

    # Normalizar campos para uppercase
    for item in items:
        if "table_alias" in item:
            item["table_alias"] = str(item["table_alias"]).upper()
        if "field_name" in item:
            item["field_name"] = str(item["field_name"]).upper()
        if "meta_table" in item:
            item["meta_table"] = str(item["meta_table"]).upper()
        if "indice" in item:
            item["indice"] = str(item["indice"]).upper()

    logger.info(
        "🔍 Preview ingestao: target=%s company=%s items=%d",
        params.get("target_conn_id"), params.get("company_code"), len(items),
    )

    return _internal_api("POST", "/api/dictionary/ingest/preview", params)


def _tool_execute_ingestion(params):
    """Execucao de ingestao com validacao de token."""
    if not params.get("confirmation_token"):
        return {"error": "confirmation_token e obrigatorio. Faca preview_ingestion primeiro."}

    sql_statements = params.get("sql_statements", [])
    if isinstance(sql_statements, str):
        try:
            sql_statements = json.loads(sql_statements)
            params["sql_statements"] = sql_statements
        except (json.JSONDecodeError, TypeError):
            return {"error": "Parametro 'sql_statements' invalido."}

    logger.info(
        "🔧 Execute ingestao: target=%s company=%s token=%s stmts=%d",
        params.get("target_conn_id"), params.get("company_code"),
        params.get("confirmation_token", "")[:10],
        len(sql_statements) if isinstance(sql_statements, list) else 0,
    )

    return _internal_api("POST", "/api/dictionary/ingest/execute", params)


def _tool_compare_dictionary(params):
    """Compara dicionário — chama POST /api/dictionary/compare.

    Pré-formata o resultado para o LLM com resumo compacto,
    evitando que o LLM alucine ao interpretar JSONs grandes.
    """
    conn_id_a = params.get("conn_id_a")
    conn_id_b = params.get("conn_id_b")
    company_code = params.get("company_code", "01")

    if not conn_id_a or not conn_id_b:
        return {"error": "Parâmetros 'conn_id_a' e 'conn_id_b' são obrigatórios."}

    env_id = params.get("environment_id")
    result = _internal_api(
        "POST",
        "/api/dictionary/compare",
        json_body={
            "conn_id_a": conn_id_a,
            "conn_id_b": conn_id_b,
            "company_code": company_code,
            "tables": params.get("tables"),
            "include_deleted": params.get("include_deleted", False),
            "environment_id": env_id,
        },
    )

    if result.get("error"):
        return result

    # Pré-formatar para o LLM — resumo compacto dos resultados
    summary = result.get("summary", {})
    results = result.get("results", {})

    lines = []
    lines.append(f"Comparação empresa {company_code}: {summary.get('tables_compared', 0)} tabelas, "
                 f"{summary.get('tables_with_diffs', 0)} com diferenças, "
                 f"{summary.get('total_diffs', 0)} divergências ({summary.get('duration_ms', 0)}ms)")

    for tname, info in sorted(results.items()):
        only_a = info.get("only_a", [])
        only_b = info.get("only_b", [])
        different = info.get("different", [])
        if not only_a and not only_b and not different:
            continue

        lines.append(f"\n{tname} ({info.get('prefix', '')}):")
        lines.append(f"  Base A: {info.get('total_a', 0)} registros | Base B: {info.get('total_b', 0)} registros")

        if only_a:
            lines.append(f"  Apenas na Base A ({len(only_a)}):")
            for item in only_a[:20]:  # Limitar a 20 itens
                lines.append(f"    - {item.get('key', '')}")
            if len(only_a) > 20:
                lines.append(f"    ... e mais {len(only_a) - 20}")

        if only_b:
            lines.append(f"  Apenas na Base B ({len(only_b)}):")
            for item in only_b[:20]:
                lines.append(f"    - {item.get('key', '')}")
            if len(only_b) > 20:
                lines.append(f"    ... e mais {len(only_b) - 20}")

        if different:
            lines.append(f"  Diferentes ({len(different)}):")
            for item in different[:10]:
                fields = [f["field"] for f in item.get("fields", [])]
                lines.append(f"    - {item.get('key', '')}: {', '.join(fields[:5])}")
            if len(different) > 10:
                lines.append(f"    ... e mais {len(different) - 10}")

    return {"formatted_result": "\n".join(lines), "history_id": result.get("history_id")}


# =====================================================================
# SYSTEM TOOLS — ACESSO AO SISTEMA (9J-F3)
# =====================================================================


def _tool_read_file(params):
    """Le conteudo de arquivo (sandbox valida path)."""
    path = params.get("path", "")
    if not path:
        return {"error": "Parametro 'path' e obrigatorio."}

    try:
        abs_path = os.path.abspath(path)
        size = os.path.getsize(abs_path) if os.path.exists(abs_path) else 0

        if size > 1_048_576:
            return {"error": f"Arquivo muito grande ({size} bytes, max 1MB)"}

        # Tentar ler como texto, fallback para binario
        try:
            with open(abs_path, "r", encoding="utf-8") as f:
                content = f.read()
        except UnicodeDecodeError:
            try:
                with open(abs_path, "r", encoding="cp1252") as f:
                    content = f.read()
            except Exception:
                return {"error": "Arquivo binario — nao pode ser lido como texto"}

        # Truncar se muito grande para contexto LLM
        truncated = False
        if len(content) > 10000:
            content = content[:10000]
            truncated = True

        return {
            "path": abs_path,
            "size": size,
            "content": content,
            "truncated": truncated,
            "lines": content.count("\n") + 1,
        }
    except FileNotFoundError:
        return {"error": f"Arquivo nao encontrado: {path}"}
    except PermissionError:
        return {"error": f"Sem permissao para ler: {path}"}
    except Exception as e:
        return {"error": f"Erro ao ler arquivo: {e}"}


def _tool_write_file(params):
    """Escreve conteudo em arquivo (sandbox valida path)."""
    path = params.get("path", "")
    content = params.get("content", "")

    if not path:
        return {"error": "Parametro 'path' e obrigatorio."}
    if not content:
        return {"error": "Parametro 'content' e obrigatorio."}
    if len(content) > 102_400:
        return {"error": f"Conteudo muito grande ({len(content)} bytes, max 100KB)"}

    try:
        abs_path = os.path.abspath(path)
        # Criar diretorio pai se nao existir
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)

        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(content)

        return {
            "path": abs_path,
            "bytes_written": len(content),
            "message": "Arquivo salvo com sucesso",
        }
    except Exception as e:
        return {"error": f"Erro ao escrever arquivo: {e}"}


def _tool_list_directory(params):
    """Lista conteudo de um diretorio."""
    path = params.get("path", ".")
    pattern = params.get("pattern", "*")

    try:
        import glob as glob_mod

        abs_path = os.path.abspath(path)
        if not os.path.isdir(abs_path):
            return {"error": f"Nao e um diretorio: {path}"}

        entries = []
        for entry in sorted(os.listdir(abs_path))[:100]:  # Max 100 entries
            full = os.path.join(abs_path, entry)
            if pattern != "*" and not __import__("fnmatch").fnmatch(entry, pattern):
                continue
            entry_info = {
                "name": entry,
                "type": "dir" if os.path.isdir(full) else "file",
            }
            if os.path.isfile(full):
                entry_info["size"] = os.path.getsize(full)
            entries.append(entry_info)

        return {
            "path": abs_path,
            "entries": entries,
            "total": len(entries),
        }
    except Exception as e:
        return {"error": f"Erro ao listar diretorio: {e}"}


def _tool_search_files(params):
    """Busca texto/regex em arquivos de um diretorio."""
    path = params.get("path", ".")
    query = params.get("query", "")
    pattern = params.get("file_pattern", "*.py")

    if not query:
        return {"error": "Parametro 'query' e obrigatorio."}

    try:
        abs_path = os.path.abspath(path)
        results = []
        files_searched = 0

        import fnmatch as fnm

        for root, dirs, files in os.walk(abs_path):
            # Limitar profundidade
            depth = root.replace(abs_path, "").count(os.sep)
            if depth > 5:
                continue
            for fname in files:
                if not fnm.fnmatch(fname, pattern):
                    continue
                fpath = os.path.join(root, fname)
                files_searched += 1
                if files_searched > 100:
                    break
                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        for i, line in enumerate(f, 1):
                            if re.search(query, line, re.IGNORECASE):
                                results.append(
                                    {
                                        "file": os.path.relpath(fpath, abs_path),
                                        "line": i,
                                        "content": line.strip()[:200],
                                    }
                                )
                                if len(results) >= 50:
                                    break
                except Exception:
                    continue
                if len(results) >= 50:
                    break
            if len(results) >= 50:
                break

        return {
            "path": abs_path,
            "query": query,
            "matches": results,
            "total_matches": len(results),
            "files_searched": files_searched,
            "truncated": len(results) >= 50,
        }
    except Exception as e:
        return {"error": f"Erro na busca: {e}"}


def _tool_get_file_info(params):
    """Retorna metadados de um arquivo (tamanho, datas, tipo)."""
    path = params.get("path", "")
    if not path:
        return {"error": "Parametro 'path' e obrigatorio."}

    try:
        abs_path = os.path.abspath(path)
        if not os.path.exists(abs_path):
            return {"error": f"Arquivo nao encontrado: {path}"}

        stat = os.stat(abs_path)
        return {
            "path": abs_path,
            "exists": True,
            "type": "directory" if os.path.isdir(abs_path) else "file",
            "size": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
            "readable": os.access(abs_path, os.R_OK),
            "writable": os.access(abs_path, os.W_OK),
        }
    except Exception as e:
        return {"error": f"Erro ao obter info: {e}"}


def _tool_run_command(params):
    """Executa comando shell (sandbox valida comando)."""
    import subprocess
    import shlex

    command = params.get("command", "")
    timeout = min(int(params.get("timeout", 30)), 60)

    if not command:
        return {"error": "Parametro 'command' e obrigatorio."}

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=params.get("cwd"),
        )

        stdout = result.stdout
        stderr = result.stderr

        # Truncar saida longa
        if len(stdout) > 5000:
            stdout = stdout[:5000] + "\n... (truncado)"
        if len(stderr) > 2000:
            stderr = stderr[:2000] + "\n... (truncado)"

        return {
            "command": command,
            "exit_code": result.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "success": result.returncode == 0,
        }
    except subprocess.TimeoutExpired:
        return {"error": f"Comando excedeu timeout de {timeout}s", "command": command}
    except Exception as e:
        return {"error": f"Erro ao executar comando: {e}"}


def _tool_get_system_overview(params):
    """Snapshot geral do sistema — ambientes, pipelines, alertas, repos, servicos, conexoes."""
    env_id = params.get("environment_id")
    conn = get_db()
    cursor = conn.cursor()
    overview = {}

    try:
        # Ambientes
        cursor.execute("SELECT id, name, description FROM environments ORDER BY id")
        overview["environments"] = _serialize_rows([dict(row) for row in cursor.fetchall()])

        if not env_id:
            return overview

        # Pipelines recentes
        cursor.execute(
            """
            SELECT p.name, pr.status, pr.started_at, pr.finished_at
            FROM pipeline_runs pr
            JOIN pipelines p ON p.id = pr.pipeline_id
            WHERE p.environment_id = %s
            ORDER BY pr.started_at DESC LIMIT 5
            """,
            (env_id,),
        )
        overview["recent_pipelines"] = _serialize_rows([dict(row) for row in cursor.fetchall()])

        # Alertas recentes
        cursor.execute(
            """
            SELECT category, severity, message, created_at
            FROM log_alerts
            WHERE environment_id = %s
            ORDER BY created_at DESC LIMIT 5
            """,
            (env_id,),
        )
        overview["recent_alerts"] = _serialize_rows([dict(row) for row in cursor.fetchall()])

        # Repositorios
        cursor.execute(
            "SELECT name, html_url, default_branch FROM repositories WHERE environment_id = %s ORDER BY name",
            (env_id,),
        )
        overview["repositories"] = [dict(row) for row in cursor.fetchall()]

        # Servicos
        cursor.execute(
            "SELECT name, server_name FROM server_services WHERE environment_id = %s ORDER BY name",
            (env_id,),
        )
        overview["services"] = [dict(row) for row in cursor.fetchall()]

        # Conexoes de banco
        cursor.execute(
            "SELECT id, name, driver, host, database_name FROM database_connections WHERE environment_id = %s ORDER BY name",
            (env_id,),
        )
        overview["db_connections"] = [dict(row) for row in cursor.fetchall()]

    except Exception as e:
        logger.warning("Erro ao gerar system overview: %s", e)
        overview["error"] = str(e)
    finally:
        release_db_connection(conn)

    return overview


# =====================================================================
# REGISTRO DAS FERRAMENTAS
# =====================================================================


def init_tools():
    """Registra todas as ferramentas disponíveis."""

    # --- Leitura (viewer+) ---
    register_tool(
        "get_environments", "Lista ambientes do BiizHubOps (PRD, HML, DEV, TST).", [], "viewer", _tool_get_environments
    )
    register_tool(
        "get_pipelines",
        "Lista pipelines configurados no ambiente.",
        [{"name": "environment_id", "type": "int", "description": "ID do ambiente (opcional)"}],
        "viewer",
        _tool_get_pipelines,
    )
    register_tool(
        "get_pipeline_status",
        "Execucoes recentes de pipelines (historico de runs).",
        [
            {"name": "environment_id", "type": "int", "description": "ID do ambiente (opcional)"},
            {"name": "limit", "type": "int", "description": "Quantidade (padrao 10, max 50)"},
        ],
        "viewer",
        _tool_get_pipeline_status,
    )

    register_tool(
        "get_alerts",
        "Alertas de erro do monitoramento de logs Protheus.",
        [
            {"name": "environment_id", "type": "int", "description": "ID do ambiente (opcional)"},
            {"name": "severity", "type": "str", "description": "Filtro: critical, error, warning, info"},
            {"name": "category", "type": "str", "description": "Filtro: database, thread_error, network, etc."},
            {"name": "limit", "type": "int", "description": "Quantidade (padrão 10, máx 50)"},
        ],
        "viewer",
        _tool_get_alerts,
    )
    register_tool(
        "get_alert_summary",
        "Resumo estatístico de alertas por categoria/severidade.",
        [
            {"name": "environment_id", "type": "int", "description": "ID do ambiente (opcional)"},
            {"name": "days", "type": "int", "description": "Período em dias (padrão 7, máx 30)"},
        ],
        "viewer",
        _tool_get_alert_summary,
    )
    register_tool(
        "get_recurring_errors",
        "Erros recorrentes — diagnóstico de problemas crônicos.",
        [
            {"name": "environment_id", "type": "int", "description": "ID do ambiente (opcional)"},
            {"name": "days", "type": "int", "description": "Período (padrão 7, máx 30)"},
            {"name": "min_count", "type": "int", "description": "Mínimo de ocorrências (padrão 3)"},
        ],
        "viewer",
        _tool_get_recurring_errors,
    )
    register_tool(
        "get_repositories",
        "Lista repositorios configurados no ambiente.",
        [{"name": "environment_id", "type": "int", "description": "ID do ambiente (opcional)"}],
        "viewer",
        _tool_get_repositories,
    )
    register_tool(
        "get_services",
        "Serviços monitorados (AppServer, DbAccess, etc.).",
        [{"name": "environment_id", "type": "int", "description": "ID do ambiente (opcional)"}],
        "viewer",
        _tool_get_services,
    )
    register_tool(
        "get_schedules",
        "Lista agendamentos de pipelines.",
        [{"name": "environment_id", "type": "int", "description": "ID do ambiente (opcional)"}],
        "viewer",
        _tool_get_schedules,
    )
    register_tool(
        "get_server_variables",
        "Variáveis de servidor (senhas mascaradas).",
        [{"name": "environment_id", "type": "int", "description": "ID do ambiente (opcional)"}],
        "operator",
        _tool_get_server_variables,
    )
    register_tool(
        "get_db_connections",
        "Conexões de banco de dados configuradas.",
        [{"name": "environment_id", "type": "int", "description": "ID do ambiente (opcional)"}],
        "operator",
        _tool_get_db_connections,
    )
    register_tool(
        "search_knowledge",
        "Busca na Base de Conhecimento de erros Protheus.",
        [
            {"name": "query", "type": "str", "description": "Texto de busca (obrigatório)"},
            {"name": "category", "type": "str", "description": "Filtro: database, thread_error, network, etc."},
            {"name": "limit", "type": "int", "description": "Quantidade (padrão 5, máx 20)"},
        ],
        "viewer",
        _tool_search_knowledge,
    )
    register_tool(
        "search_tdn",
        "Busca na documentacao oficial TDN (TOTVS Developer Network) — 182K+ chunks. "
        "Use para funcoes AdvPL/TLPP, configuracoes Protheus, procedures, APIs REST, webservices, TSS, framework. "
        "Prefira esta tool em vez de search_knowledge quando a pergunta for sobre como fazer algo no Protheus.",
        [
            {"name": "query", "type": "str", "description": "Texto de busca (obrigatorio). Ex: 'como configurar broker webservice', 'MsExecAuto MATA410'"},
            {"name": "source", "type": "str", "description": "Filtro por fonte: advpl, tlpp, tss, framework, protheus12, totvstec (opcional)"},
            {"name": "limit", "type": "int", "description": "Quantidade (padrao 5, max 10)"},
        ],
        "viewer",
        _tool_search_tdn,
    )
    register_tool("get_users", "Usuários do sistema com perfil e status.", [], "admin", _tool_get_users)

    # --- Ação (operator+) ---
    register_tool(
        "run_pipeline",
        "Dispara execucao de um pipeline.",
        [
            {"name": "pipeline_id", "type": "int", "description": "ID do pipeline (obrigatorio)"},
            {"name": "environment_id", "type": "int", "description": "ID do ambiente (opcional)"},
        ],
        "operator",
        _tool_run_pipeline,
    )
    register_tool(
        "create_release",
        "Cria release (deploy) a partir de um run bem-sucedido. O run precisa ter status 'success' e o pipeline precisa ter deploy_command_id configurado.",
        [
            {"name": "run_id", "type": "int", "description": "ID do run/build bem-sucedido (obrigatorio)"},
            {"name": "environment_id", "type": "int", "description": "ID do ambiente (opcional, usa o do run)"},
        ],
        "operator",
        _tool_create_release,
        requires_confirmation=True,
        risk_level="high",
    )
    register_tool(
        "execute_service_action",
        "Executa acao em servicos (start/stop/restart).",
        [
            {"name": "action_id", "type": "int", "description": "ID da acao (obrigatorio)"},
            {"name": "environment_id", "type": "int", "description": "ID do ambiente (obrigatorio)"},
        ],
        "operator",
        _tool_execute_service_action,
    )
    register_tool(
        "acknowledge_alert",
        "Marca alerta como reconhecido/visto.",
        [{"name": "alert_id", "type": "int", "description": "ID do alerta (obrigatório)"}],
        "operator",
        _tool_acknowledge_alert,
        risk_level="medium",
    )
    register_tool(
        "acknowledge_alerts_bulk",
        "Reconhece múltiplos alertas de uma vez.",
        [{"name": "alert_ids", "type": "list", "description": "Lista de IDs dos alertas (obrigatório)"}],
        "operator",
        _tool_acknowledge_alerts_bulk,
        risk_level="medium",
    )
    register_tool(
        "toggle_schedule",
        "Ativa/desativa um agendamento de pipeline.",
        [
            {"name": "schedule_id", "type": "int", "description": "ID do agendamento (obrigatorio)"},
            {"name": "environment_id", "type": "int", "description": "ID do ambiente (opcional)"},
        ],
        "operator",
        _tool_toggle_schedule,
    )
    register_tool(
        "git_pull",
        "Executa git pull em um repositorio.",
        [
            {"name": "repo_id", "type": "int", "description": "ID do repositorio (obrigatorio)"},
            {"name": "branch", "type": "str", "description": "Branch (opcional, usa default_branch)"},
        ],
        "operator",
        _tool_git_pull,
    )

    # --- System Tools (9J-F3) — requerem sandbox habilitado ---
    register_tool(
        "read_file",
        "Le conteudo de um arquivo no servidor (max 1MB, sandbox).",
        [{"name": "path", "type": "str", "description": "Caminho do arquivo (obrigatorio)"}],
        "viewer",
        _tool_read_file,
    )
    register_tool(
        "list_directory",
        "Lista conteudo de um diretorio (max 100 entradas).",
        [
            {"name": "path", "type": "str", "description": "Caminho do diretorio (obrigatorio)"},
            {"name": "pattern", "type": "str", "description": "Filtro glob (padrao: *)"},
        ],
        "viewer",
        _tool_list_directory,
    )
    register_tool(
        "search_files",
        "Busca texto/regex em arquivos de um diretorio.",
        [
            {"name": "path", "type": "str", "description": "Diretorio base (obrigatorio)"},
            {"name": "query", "type": "str", "description": "Texto ou regex para buscar (obrigatorio)"},
            {"name": "file_pattern", "type": "str", "description": "Filtro de arquivo (padrao: *.py)"},
        ],
        "viewer",
        _tool_search_files,
    )
    register_tool(
        "get_file_info",
        "Metadados de arquivo (tamanho, datas, permissoes).",
        [{"name": "path", "type": "str", "description": "Caminho do arquivo (obrigatorio)"}],
        "viewer",
        _tool_get_file_info,
    )
    register_tool(
        "write_file",
        "Cria ou sobrescreve arquivo (max 100KB, sandbox, requer confirmacao).",
        [
            {"name": "path", "type": "str", "description": "Caminho do arquivo (obrigatorio)"},
            {"name": "content", "type": "str", "description": "Conteudo a escrever (obrigatorio)"},
        ],
        "operator",
        _tool_write_file,
    )
    register_tool(
        "run_command",
        "Executa comando shell no servidor (allowlist, timeout 30s, requer confirmacao).",
        [
            {"name": "command", "type": "str", "description": "Comando shell (obrigatorio)"},
            {"name": "timeout", "type": "int", "description": "Timeout em segundos (padrao 30, max 60)"},
            {"name": "cwd", "type": "str", "description": "Diretorio de trabalho (opcional)"},
        ],
        "operator",
        _tool_run_command,
    )

    # --- Visao geral — 9K-T3 (lazy context) ---
    register_tool(
        "get_system_overview",
        "Snapshot geral do sistema: ambientes, pipelines recentes, alertas, repos, servicos e conexoes de banco. "
        "Use quando precisar de uma visao geral do estado atual.",
        [{"name": "environment_id", "type": "int", "description": "ID do ambiente (usa o ativo se omitido)"}],
        "viewer",
        _tool_get_system_overview,
    )

    # --- Admin — 9F-3 ---
    register_tool(
        "query_database",
        "Executa SELECT em banco Protheus. PREFIRA usar template em vez de SQL bruto — "
        "o sistema monta o SQL com sufixo correto automaticamente. "
        "Templates: parametro, parametros_modulo, campos_tabela, indices_tabela, tabelas, "
        "tabela_info, gatilhos_campo, tabelas_genericas, empresas, dados_tabela, count_tabela.",
        [
            {"name": "connection_id", "type": "int|str", "description": "ID ou alias da conexão (ex: 1, 'HML', 'PRD')"},
            {"name": "template", "type": "str", "description": "Nome do template (ex: 'parametro'). PREFIRA template em vez de query raw."},
            {"name": "param_name", "type": "str", "description": "Para template=parametro: nome do MV_ (ex: 'MV_ESTNEG')"},
            {"name": "table_alias", "type": "str", "description": "Para templates de tabela: alias (ex: 'SA1', 'SC5')"},
            {"name": "prefix", "type": "str", "description": "Para template=parametros_modulo: prefixo (ex: 'MV_COM')"},
            {"name": "field_name", "type": "str", "description": "Para template=gatilhos_campo: nome do campo (ex: 'A1_COD')"},
            {"name": "query", "type": "str", "description": "SQL SELECT bruto (usar apenas se nenhum template atende)"},
            {"name": "max_rows", "type": "int", "description": "Máximo de linhas (padrão 100, máx 500)"},
        ],
        "admin",
        _tool_query_database,
        risk_level="medium",
    )
    register_tool(
        "compare_dictionary",
        "Compara dicionário Protheus entre dois bancos. "
        "Use os IDs das conexões listadas no contexto. "
        "Se o usuário disser HML/PRD/dev, use o nome ou alias como conn_id — o sistema resolve automaticamente.",
        [
            {"name": "conn_id_a", "type": "int|str", "description": "ID ou nome/alias da primeira conexão (ex: 1, 'HML', 'Homologacao')"},
            {"name": "conn_id_b", "type": "int|str", "description": "ID ou nome/alias da segunda conexão (ex: 2, 'PRD', 'Producao')"},
            {"name": "company_code", "type": "str", "description": "Código da empresa (padrão '01')"},
            {"name": "tables", "type": "list", "description": "Tabelas a comparar (opcional, ex: ['SX3'] para só SX3)"},
        ],
        "admin",
        _tool_compare_dictionary,
        risk_level="medium",
    )

    # =================================================================
    # CRUD TOOLS — "Pergunte ao Analista!"
    # Todas delegam para _internal_api() — zero lógica nova
    # =================================================================

    # --- Observability CRUD ---
    register_tool("list_log_monitors", "Lista monitores de log configurados.",
        [{"name": "environment_id", "type": "int", "description": "ID do ambiente (opcional)"}],
        "operator", lambda p: _internal_api("GET", f"/api/log-monitors?environment_id={p.get('environment_id', '')}"))
    register_tool("create_log_monitor", "Cria novo monitor de log.",
        [{"name": "name", "type": "str", "description": "Nome do monitor (obrigatório)"},
         {"name": "log_file_path", "type": "str", "description": "Caminho do arquivo de log (obrigatório)"},
         {"name": "environment_id", "type": "int", "description": "ID do ambiente (obrigatório)"},
         {"name": "scan_interval", "type": "int", "description": "Intervalo de scan em segundos (padrão 60)"}],
        "operator", lambda p: _internal_api("POST", "/api/log-monitors", p), requires_confirmation=True)
    register_tool("update_log_monitor", "Atualiza configuração de monitor de log.",
        [{"name": "config_id", "type": "int", "description": "ID do monitor (obrigatório)"},
         {"name": "name", "type": "str", "description": "Novo nome (opcional)"},
         {"name": "scan_interval", "type": "int", "description": "Novo intervalo (opcional)"}],
        "operator", lambda p: _internal_api("PUT", f"/api/log-monitors/{p.get('config_id')}", {k: v for k, v in p.items() if k != 'config_id'}), requires_confirmation=True)
    register_tool("delete_log_monitor", "Remove monitor de log e seus alertas.",
        [{"name": "config_id", "type": "int", "description": "ID do monitor (obrigatório)"}],
        "admin", lambda p: _internal_api("DELETE", f"/api/log-monitors/{p['config_id']}"), requires_confirmation=True)
    register_tool("scan_log_monitor", "Dispara scan manual de um monitor de log.",
        [{"name": "config_id", "type": "int", "description": "ID do monitor (obrigatório)"}],
        "operator", lambda p: _internal_api("POST", f"/api/log-monitors/{p['config_id']}/scan"),
        risk_level="medium")
    register_tool("browse_log_files", "Lista arquivos .log disponíveis no servidor.",
        [], "operator", lambda p: _internal_api("GET", "/api/log-monitors/browse-logs"))
    register_tool("get_alerts_timeline", "Timeline de alertas por hora (gráfico).",
        [{"name": "environment_id", "type": "int", "description": "ID do ambiente (opcional)"},
         {"name": "hours", "type": "int", "description": "Janela em horas (padrão 24)"}],
        "viewer", lambda p: _internal_api("GET", f"/api/log-alerts/timeline?environment_id={p.get('environment_id', '')}&hours={p.get('hours', 24)}"))

    # --- Database CRUD ---
    register_tool("create_db_connection", "Cria nova conexão de banco de dados externo.",
        [{"name": "name", "type": "str", "description": "Nome da conexão (obrigatório)"},
         {"name": "driver", "type": "str", "description": "Driver: mssql, oracle, postgresql, mysql (obrigatório)"},
         {"name": "host", "type": "str", "description": "Endereço do servidor (obrigatório)"},
         {"name": "port", "type": "int", "description": "Porta (obrigatório)"},
         {"name": "database_name", "type": "str", "description": "Nome do banco (obrigatório)"},
         {"name": "username", "type": "str", "description": "Usuário (obrigatório)"},
         {"name": "password", "type": "str", "description": "Senha (obrigatório)"},
         {"name": "environment_id", "type": "int", "description": "ID do ambiente (obrigatório)"}],
        "admin", lambda p: _internal_api("POST", "/api/db-connections", p), requires_confirmation=True)
    register_tool("update_db_connection", "Atualiza conexão de banco de dados.",
        [{"name": "conn_id", "type": "int", "description": "ID da conexão (obrigatório)"},
         {"name": "name", "type": "str", "description": "Novo nome (opcional)"},
         {"name": "host", "type": "str", "description": "Novo host (opcional)"},
         {"name": "port", "type": "int", "description": "Nova porta (opcional)"}],
        "admin", lambda p: _internal_api("PUT", f"/api/db-connections/{p.get('conn_id')}", {k: v for k, v in p.items() if k != 'conn_id'}), requires_confirmation=True)
    register_tool("delete_db_connection", "Remove conexão de banco de dados.",
        [{"name": "conn_id", "type": "int", "description": "ID da conexão (obrigatório)"}],
        "admin", lambda p: _internal_api("DELETE", f"/api/db-connections/{p['conn_id']}"), requires_confirmation=True)
    register_tool("test_db_connection", "Testa conexão com banco de dados e mede latência.",
        [{"name": "conn_id", "type": "int", "description": "ID da conexão (obrigatório)"}],
        "admin", lambda p: _internal_api("POST", f"/api/db-connections/{p['conn_id']}/test"),
        risk_level="medium")
    register_tool("discover_db_schema", "Descobre schema do banco (tabelas e colunas) e armazena em cache.",
        [{"name": "conn_id", "type": "int", "description": "ID da conexão (obrigatório)"}],
        "admin", lambda p: _internal_api("POST", f"/api/db-connections/{p['conn_id']}/discover"),
        risk_level="medium")

    # --- Dictionary CRUD ---
    register_tool("validate_dictionary", "Valida integridade do dicionário Protheus (SX2/SX3/SIX vs físico).",
        [{"name": "connection_id", "type": "int", "description": "ID da conexão (obrigatório)"},
         {"name": "company_code", "type": "str", "description": "Código da empresa (obrigatório)"}],
        "admin", lambda p: _internal_api("POST", "/api/dictionary/validate", p))
    register_tool("get_dictionary_history", "Lista histórico de comparações e validações de dicionário.",
        [{"name": "environment_id", "type": "int", "description": "ID do ambiente (opcional)"}],
        "admin", lambda p: _internal_api("GET", f"/api/dictionary/history?environment_id={p.get('environment_id', '')}"))
    register_tool("preview_equalization", "Gera preview SQL de equalização sem executar.",
        [{"name": "source_conn_id", "type": "int", "description": "ID conexão origem (obrigatório)"},
         {"name": "target_conn_id", "type": "int", "description": "ID conexão destino (obrigatório)"},
         {"name": "company_code", "type": "str", "description": "Código da empresa (obrigatório)"},
         {"name": "items", "type": "list", "description": "Itens a equalizar (obrigatório)"}],
        "admin", _tool_preview_equalization)
    register_tool("execute_equalization",
        "Executa equalizacao. Se chamado sem confirmation_token, faz preview automatico. "
        "A confirmacao real e via token do preview — NAO precisa de confirmacao dupla.",
        [{"name": "source_conn_id", "type": "int|str", "description": "ID ou alias da conexao origem (ex: 'HML')"},
         {"name": "target_conn_id", "type": "int|str", "description": "ID ou alias da conexao destino (ex: 'PRD')"},
         {"name": "company_code", "type": "str", "description": "Codigo da empresa (usa o do contexto se omitido)"},
         {"name": "items", "type": "list", "description": "Itens a equalizar (obrigatorio)"},
         {"name": "confirmation_token", "type": "str", "description": "Token do preview (se omitido, faz preview automatico)"}],
        "admin", _tool_execute_equalization, risk_level="high")

    # --- Ingestor de Dicionário ---
    register_tool("upload_ingest_file", "Faz upload e parse de arquivo de ingestão de dicionário (JSON ou MD).",
        [{"name": "content", "type": "str", "description": "Conteúdo do arquivo JSON ou Markdown (obrigatório)"},
         {"name": "filename", "type": "str", "description": "Nome do arquivo (ex: export_sa1.json) — usado para detectar formato"}],
        "admin", _tool_upload_ingest_file)
    register_tool("preview_ingestion", "Gera preview SQL de ingestão de dicionário a partir de arquivo externo.",
        [{"name": "target_conn_id", "type": "int", "description": "ID conexão destino (obrigatório)"},
         {"name": "company_code", "type": "str", "description": "Código da empresa (obrigatório)"},
         {"name": "items", "type": "list", "description": "Itens parseados do upload (obrigatório)"},
         {"name": "metadata", "type": "dict", "description": "Metadata do arquivo (opcional)"}],
        "admin", _tool_preview_ingestion)
    register_tool("execute_ingestion", "Executa ingestão de dicionário (transação atômica).",
        [{"name": "target_conn_id", "type": "int", "description": "ID conexão destino (obrigatório)"},
         {"name": "company_code", "type": "str", "description": "Código da empresa (obrigatório)"},
         {"name": "sql_statements", "type": "list", "description": "SQLs do preview (obrigatório)"},
         {"name": "confirmation_token", "type": "str", "description": "Token de confirmação do preview (obrigatório)"},
         {"name": "file_metadata", "type": "dict", "description": "Metadata do arquivo (opcional)"}],
        "admin", _tool_execute_ingestion, requires_confirmation=True)

    # --- Settings CRUD ---
    # create/update/delete_environment: REMOVIDOS — operação exclusiva do root admin via UI
    # A rota exige username='admin' (não apenas profile admin) — agente não deve oferecer
    register_tool("create_server_variable", "Cria variável de servidor.",
        [{"name": "name", "type": "str", "description": "Nome da variável (obrigatório)"},
         {"name": "value", "type": "str", "description": "Valor (obrigatório)"},
         {"name": "environment_id", "type": "int", "description": "ID do ambiente (obrigatório)"},
         {"name": "is_password", "type": "bool", "description": "É senha? (padrão false)"}],
        "operator", lambda p: _internal_api("POST", "/api/server-variables", p), requires_confirmation=True)
    register_tool("update_server_variable", "Atualiza variável de servidor.",
        [{"name": "var_id", "type": "int", "description": "ID da variável (obrigatório)"},
         {"name": "value", "type": "str", "description": "Novo valor (obrigatório)"}],
        "operator", lambda p: _internal_api("PUT", f"/api/server-variables/{p.get('var_id')}", {k: v for k, v in p.items() if k != 'var_id'}), requires_confirmation=True)
    register_tool("delete_server_variable", "Remove variável de servidor.",
        [{"name": "var_id", "type": "int", "description": "ID da variável (obrigatório)"}],
        "operator", lambda p: _internal_api("DELETE", f"/api/server-variables/{p['var_id']}"), requires_confirmation=True)
    register_tool("get_variable_history", "Histórico de alterações de uma variável de servidor.",
        [{"name": "var_id", "type": "int", "description": "ID da variável (obrigatório)"}],
        "operator", lambda p: _internal_api("GET", f"/api/server-variables/{p['var_id']}/history"))

    # --- Admin CRUD ---
    register_tool("list_webhooks", "Lista webhooks configurados.",
        [], "admin", lambda p: _internal_api("GET", "/api/admin/webhooks"))
    register_tool("create_webhook", "Cria novo webhook para eventos do sistema.",
        [{"name": "url", "type": "str", "description": "URL do webhook (obrigatório)"},
         {"name": "events", "type": "list", "description": "Eventos a escutar (obrigatório)"},
         {"name": "environment_id", "type": "int", "description": "ID do ambiente (obrigatório)"}],
        "admin", lambda p: _internal_api("POST", "/api/admin/webhooks", p), requires_confirmation=True)
    register_tool("update_webhook", "Atualiza webhook existente.",
        [{"name": "webhook_id", "type": "int", "description": "ID do webhook (obrigatório)"},
         {"name": "url", "type": "str", "description": "Nova URL (opcional)"},
         {"name": "events", "type": "list", "description": "Novos eventos (opcional)"}],
        "admin", lambda p: _internal_api("PUT", f"/api/admin/webhooks/{p.get('webhook_id')}", {k: v for k, v in p.items() if k != 'webhook_id'}), requires_confirmation=True)
    register_tool("delete_webhook", "Remove webhook.",
        [{"name": "webhook_id", "type": "int", "description": "ID do webhook (obrigatório)"}],
        "admin", lambda p: _internal_api("DELETE", f"/api/admin/webhooks/{p['webhook_id']}"), requires_confirmation=True)
    register_tool("test_webhook", "Envia evento de teste para webhook.",
        [{"name": "webhook_id", "type": "int", "description": "ID do webhook (obrigatório)"}],
        "admin", lambda p: _internal_api("POST", f"/api/admin/webhooks/{p['webhook_id']}/test"),
        risk_level="medium")

    # --- Auditor CRUD ---
    register_tool("get_auditor_history", "Lista histórico de auditorias de INI.",
        [{"name": "environment_id", "type": "int", "description": "ID do ambiente (opcional)"}],
        "viewer", lambda p: _internal_api("GET", f"/api/auditor/history?environment_id={p.get('environment_id', '')}"))
    register_tool("get_audit_detail", "Detalhes completos de uma auditoria específica.",
        [{"name": "audit_id", "type": "int", "description": "ID da auditoria (obrigatório)"}],
        "viewer", lambda p: _internal_api("GET", f"/api/auditor/audit/{p['audit_id']}"))
    register_tool("delete_audit", "Remove registro de auditoria.",
        [{"name": "audit_id", "type": "int", "description": "ID da auditoria (obrigatório)"}],
        "admin", lambda p: _internal_api("DELETE", f"/api/auditor/audit/{p['audit_id']}"), requires_confirmation=True)

    # --- Marcar tools existentes que precisam de confirmação ---
    for tool_name in ["acknowledge_alerts_bulk", "write_file", "run_command"]:
        if tool_name in AGENT_TOOLS:
            AGENT_TOOLS[tool_name]["requires_confirmation"] = True

    # --- Workspace tools (ExtraiRPO — engenharia reversa Protheus) ---
    try:
        from app.services.workspace.agent_tools import get_workspace_tools
        for tool in get_workspace_tools():
            register_tool(
                name=tool["name"],
                description=tool["description"],
                parameters=[
                    {"name": k, "type": v.get("type", "string"), "description": v.get("description", "")}
                    for k, v in tool["parameters"].items()
                ],
                min_profile=tool.get("min_profile", "viewer"),
                handler=tool["handler"],
                risk_level=tool.get("risk", "low"),
            )
        logger.info("🔧 %d workspace tools registradas", len(get_workspace_tools()))
    except Exception as e:
        logger.warning("⚠️ Workspace tools nao carregadas: %s", e)

    logger.info("🔧 %d ferramentas do agente registradas", len(AGENT_TOOLS))


# Inicializar ao importar
init_tools()
