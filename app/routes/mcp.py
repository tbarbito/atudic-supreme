"""MCP Gateway — endpoints REST para o Model Context Protocol.

Expoe as ferramentas do BiizHubOps para agentes IA externos.
O servidor MCP standalone (app/mcp/server.py) consome estes endpoints.

Endpoints:
  GET  /api/mcp/health   — Health check do gateway
  GET  /api/mcp/tools    — Lista ferramentas (filtrado por perfil da API key)
  POST /api/mcp/execute  — Executa uma ferramenta
"""

import logging
from flask import Blueprint, jsonify, request
from app.utils.security import require_api_key
from app.database.core import get_db, release_db_connection
from app.services.agent_tools import get_available_tools, execute_tool, AGENT_TOOLS

logger = logging.getLogger(__name__)

mcp_bp = Blueprint("mcp", __name__)


def _get_api_key_profile():
    """Retorna o perfil do usuario associado a API key atual.

    A tabela api_keys tem created_by (FK users), entao fazemos JOIN
    para pegar o perfil do usuario que criou a chave.
    Se nao encontrar, retorna 'viewer' (menor privilegio).

    Returns:
        str: Perfil do usuario (admin, operator, viewer).
    """
    api_key_info = getattr(request, "api_key", None)
    if not api_key_info:
        return "viewer"

    created_by = api_key_info.get("created_by")
    if not created_by:
        return "viewer"

    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT profile FROM users WHERE id = %s AND active = TRUE",
            (created_by,),
        )
        row = cursor.fetchone()
        if row:
            return dict(row).get("profile", "viewer")
        return "viewer"
    except Exception as e:
        logger.warning("Erro ao buscar perfil da API key: %s", e)
        return "viewer"
    finally:
        release_db_connection(conn)


def _get_api_key_user_id():
    """Retorna o user_id do criador da API key.

    Returns:
        int ou None: ID do usuario que criou a API key.
    """
    api_key_info = getattr(request, "api_key", None)
    if api_key_info:
        return api_key_info.get("created_by")
    return None


def _tool_to_mcp_schema(tool):
    """Converte schema interno do BiizHubOps para formato MCP (JSON Schema).

    O registro interno usa:
        [{"name": "x", "type": "int", "description": "..."}]

    O MCP espera JSON Schema:
        {"type": "object", "properties": {...}, "required": [...]}

    Args:
        tool: dict com registro da ferramenta interna.

    Returns:
        dict: JSON Schema compativel com MCP.
    """
    properties = {}
    required = []

    type_map = {
        "int": "integer",
        "str": "string",
        "bool": "boolean",
        "list": "array",
        "float": "number",
    }

    for param in tool.get("parameters", []):
        param_name = param["name"]
        param_type = param.get("type", "string")
        param_desc = param.get("description", "")

        json_type = type_map.get(param_type, "string")

        prop = {"type": json_type, "description": param_desc}
        if json_type == "array":
            prop["items"] = {"type": "string"}

        properties[param_name] = prop

        # Inferir obrigatoriedade pela descricao
        desc_lower = param_desc.lower()
        if "obrigatório" in desc_lower or "obrigatorio" in desc_lower:
            required.append(param_name)

    schema = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required

    return schema


@mcp_bp.route("/api/mcp/health", methods=["GET"])
def mcp_health():
    """Health check do gateway MCP.

    Nao requer autenticacao — usado para verificar se o servidor esta ativo.
    """
    return jsonify({
        "status": "ok",
        "service": "atudic-mcp",
        "version": "1.0.0",
        "protocol": "MCP 2024-11-05",
        "tools_count": len(AGENT_TOOLS),
    })


@mcp_bp.route("/api/mcp/tools", methods=["GET"])
@require_api_key
def mcp_list_tools():
    """Lista ferramentas disponiveis para a API key atual.

    Filtra por perfil de permissao do usuario que criou a API key.
    Retorna no formato compativel com MCP (name, description, inputSchema).
    """
    profile = _get_api_key_profile()
    available = get_available_tools(profile)

    tools = []
    for tool_info in available:
        tool_name = tool_info["name"]
        tool = AGENT_TOOLS.get(tool_name, {})
        tools.append({
            "name": tool_name,
            "description": tool_info.get("description", ""),
            "inputSchema": _tool_to_mcp_schema(tool),
        })

    logger.info("MCP tools/list: profile=%s, tools=%d", profile, len(tools))
    return jsonify({"tools": tools, "total": len(tools)})


@mcp_bp.route("/api/mcp/execute", methods=["POST"])
@require_api_key
def mcp_execute_tool():
    """Executa uma ferramenta do BiizHubOps.

    Body JSON:
        {
            "tool_name": "get_alerts",
            "params": {"environment_id": 1, "severity": "critical"}
        }

    Permissoes sao validadas pelo perfil do usuario da API key.
    """
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"error": "Body JSON obrigatório"}), 400

    tool_name = data.get("tool_name")
    if not tool_name:
        return jsonify({"error": "Campo 'tool_name' obrigatório"}), 400

    params = data.get("params", {})
    profile = _get_api_key_profile()
    user_id = _get_api_key_user_id()
    environment_id = params.get("environment_id")

    logger.info(
        "MCP execute: tool=%s profile=%s user_id=%s env_id=%s",
        tool_name, profile, user_id, environment_id,
    )

    result = execute_tool(
        tool_name=tool_name,
        params=params,
        user_profile=profile,
        environment_id=environment_id,
        user_id=user_id,
    )

    if "error" in result:
        error_msg = result["error"].lower()
        if "permissão" in error_msg or "permissao" in error_msg:
            status_code = 403
        elif "não encontrada" in error_msg or "nao encontrada" in error_msg:
            status_code = 404
        else:
            status_code = 400
        return jsonify(result), status_code

    return jsonify(result)
