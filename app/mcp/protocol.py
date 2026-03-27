"""Protocolo MCP (Model Context Protocol) — JSON-RPC sobre stdio.

Implementacao zero-dependencia do protocolo MCP para transporte stdio.
Segue a especificacao MCP 2025-03-26 (JSON-RPC 2.0).

Metodos suportados:
  - initialize       — handshake com capabilities
  - notifications/initialized — notificacao pos-handshake
  - ping             — heartbeat
  - tools/list       — lista ferramentas disponiveis
  - tools/call       — executa uma ferramenta
"""

import json
import sys
import logging

logger = logging.getLogger("atudic-mcp")

# Versao do protocolo MCP suportada
MCP_PROTOCOL_VERSION = "2024-11-05"

# Informacoes do servidor
SERVER_INFO = {
    "name": "atudic-mcp",
    "version": "1.0.0",
}

# Capabilities declaradas pelo servidor
SERVER_CAPABILITIES = {
    "tools": {},
}


def read_message():
    """Le uma mensagem JSON-RPC do stdin (uma linha por mensagem).

    Returns:
        dict: Mensagem JSON-RPC parseada, ou None se EOF.
    """
    try:
        line = sys.stdin.readline()
        if not line:
            return None
        line = line.strip()
        if not line:
            return None
        return json.loads(line)
    except json.JSONDecodeError as e:
        logger.error("JSON invalido no stdin: %s", e)
        return None
    except Exception as e:
        logger.error("Erro lendo stdin: %s", e)
        return None


def write_message(msg):
    """Escreve uma mensagem JSON-RPC no stdout.

    Args:
        msg: dict com a mensagem JSON-RPC.
    """
    try:
        line = json.dumps(msg, ensure_ascii=False, separators=(",", ":"))
        sys.stdout.write(line + "\n")
        sys.stdout.flush()
    except Exception as e:
        logger.error("Erro escrevendo stdout: %s", e)


def make_response(request_id, result):
    """Cria uma resposta JSON-RPC de sucesso.

    Args:
        request_id: ID da requisicao original.
        result: Payload de resultado.

    Returns:
        dict: Resposta JSON-RPC formatada.
    """
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": result,
    }


def make_error(request_id, code, message, data=None):
    """Cria uma resposta JSON-RPC de erro.

    Args:
        request_id: ID da requisicao original (pode ser None).
        code: Codigo de erro JSON-RPC.
        message: Mensagem de erro.
        data: Dados adicionais (opcional).

    Returns:
        dict: Resposta de erro JSON-RPC formatada.
    """
    error = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": error,
    }


# Codigos de erro JSON-RPC padrao
ERR_PARSE = -32700
ERR_INVALID_REQUEST = -32600
ERR_METHOD_NOT_FOUND = -32601
ERR_INVALID_PARAMS = -32602
ERR_INTERNAL = -32603


def handle_initialize(request_id, _params):
    """Processa handshake MCP (initialize).

    Returns:
        dict: Resposta com protocolVersion, capabilities e serverInfo.
    """
    return make_response(request_id, {
        "protocolVersion": MCP_PROTOCOL_VERSION,
        "capabilities": SERVER_CAPABILITIES,
        "serverInfo": SERVER_INFO,
    })


def handle_ping(request_id, _params):
    """Processa heartbeat (ping).

    Returns:
        dict: Resposta vazia (pong).
    """
    return make_response(request_id, {})
