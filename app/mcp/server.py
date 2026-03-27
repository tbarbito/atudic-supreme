"""MCP Server standalone — conecta protocolo MCP ao AtuDIC via REST API.

Arquitetura:
  - Le JSON-RPC do stdin (protocolo MCP)
  - Mapeia tools/list e tools/call para o gateway Flask (/api/mcp/*)
  - Escreve respostas JSON-RPC no stdout

Uso:
  python mcp_server.py --url http://localhost:5000 --api-key at_xxx

Claude Code:
  claude mcp add atudic -- python /path/to/mcp_server.py --url http://host:5000 --api-key at_xxx
"""

import json
import logging
import sys

import requests

from app.mcp.protocol import (
    ERR_INTERNAL,
    ERR_INVALID_PARAMS,
    ERR_METHOD_NOT_FOUND,
    handle_initialize,
    handle_ping,
    make_error,
    make_response,
    read_message,
    write_message,
)

logger = logging.getLogger("atudic-mcp")


class AtuDICMCPServer:
    """Servidor MCP que conecta agentes externos ao AtuDIC."""

    def __init__(self, base_url, api_key):
        """Inicializa o servidor MCP.

        Args:
            base_url: URL base do AtuDIC (ex: http://localhost:5000).
            api_key: Chave de API para autenticacao (at_xxx).
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            "x-api-key": self.api_key,
            "Content-Type": "application/json",
        })
        self._tools_cache = None

    def _api_get(self, path):
        """Faz GET no gateway MCP do AtuDIC.

        Args:
            path: Caminho relativo (ex: /api/mcp/tools).

        Returns:
            dict: Resposta JSON ou dict com erro.
        """
        try:
            resp = self.session.get(f"{self.base_url}{path}", timeout=30)
            return resp.json()
        except requests.ConnectionError:
            return {"error": f"Nao foi possivel conectar ao AtuDIC em {self.base_url}"}
        except requests.Timeout:
            return {"error": "Timeout ao conectar ao AtuDIC"}
        except Exception as e:
            return {"error": f"Erro na requisicao: {str(e)}"}

    def _api_post(self, path, data):
        """Faz POST no gateway MCP do AtuDIC.

        Args:
            path: Caminho relativo (ex: /api/mcp/execute).
            data: Payload JSON.

        Returns:
            dict: Resposta JSON ou dict com erro.
        """
        try:
            resp = self.session.post(
                f"{self.base_url}{path}",
                json=data,
                timeout=60,
            )
            return resp.json()
        except requests.ConnectionError:
            return {"error": f"Nao foi possivel conectar ao AtuDIC em {self.base_url}"}
        except requests.Timeout:
            return {"error": "Timeout ao executar ferramenta no AtuDIC"}
        except Exception as e:
            return {"error": f"Erro na requisicao: {str(e)}"}

    def fetch_tools(self):
        """Busca lista de ferramentas do gateway MCP.

        Returns:
            list: Lista de ferramentas no formato MCP.
        """
        if self._tools_cache is not None:
            return self._tools_cache

        result = self._api_get("/api/mcp/tools")
        if "error" in result:
            logger.error("Erro ao buscar ferramentas: %s", result["error"])
            return []

        self._tools_cache = result.get("tools", [])
        return self._tools_cache

    def execute_tool(self, tool_name, arguments):
        """Executa uma ferramenta via gateway MCP.

        Args:
            tool_name: Nome da ferramenta.
            arguments: Dicionario de parametros.

        Returns:
            dict: Resultado da execucao.
        """
        result = self._api_post("/api/mcp/execute", {
            "tool_name": tool_name,
            "params": arguments or {},
        })
        return result

    def handle_tools_list(self, request_id, _params):
        """Processa tools/list — retorna ferramentas disponiveis.

        Args:
            request_id: ID da requisicao JSON-RPC.

        Returns:
            dict: Resposta JSON-RPC com lista de ferramentas.
        """
        tools = self.fetch_tools()
        return make_response(request_id, {"tools": tools})

    def handle_tools_call(self, request_id, params):
        """Processa tools/call — executa uma ferramenta.

        Args:
            request_id: ID da requisicao JSON-RPC.
            params: Parametros MCP (name, arguments).

        Returns:
            dict: Resposta JSON-RPC com resultado.
        """
        if not params:
            return make_error(request_id, ERR_INVALID_PARAMS, "Parametros obrigatorios")

        tool_name = params.get("name")
        if not tool_name:
            return make_error(request_id, ERR_INVALID_PARAMS, "Campo 'name' obrigatorio")

        arguments = params.get("arguments", {})
        result = self.execute_tool(tool_name, arguments)

        # Formatar resultado como MCP content
        if "error" in result:
            return make_response(request_id, {
                "content": [{
                    "type": "text",
                    "text": json.dumps({"error": result["error"]}, ensure_ascii=False),
                }],
                "isError": True,
            })

        # Resultado de sucesso
        data = result.get("data", result)
        return make_response(request_id, {
            "content": [{
                "type": "text",
                "text": json.dumps(data, ensure_ascii=False, indent=2),
            }],
        })

    def handle_message(self, msg):
        """Processa uma mensagem JSON-RPC e retorna resposta.

        Args:
            msg: Mensagem JSON-RPC parseada.

        Returns:
            dict ou None: Resposta JSON-RPC, ou None para notificacoes.
        """
        method = msg.get("method")
        request_id = msg.get("id")
        params = msg.get("params", {})

        # Notificacoes (sem id) nao precisam de resposta
        if request_id is None:
            if method == "notifications/initialized":
                logger.info("Cliente MCP inicializado com sucesso")
            return None

        handlers = {
            "initialize": handle_initialize,
            "ping": handle_ping,
            "tools/list": self.handle_tools_list,
            "tools/call": self.handle_tools_call,
        }

        handler = handlers.get(method)
        if handler:
            try:
                return handler(request_id, params)
            except Exception as e:
                logger.error("Erro processando %s: %s", method, e)
                return make_error(request_id, ERR_INTERNAL, str(e))

        return make_error(request_id, ERR_METHOD_NOT_FOUND, f"Metodo '{method}' nao suportado")

    def run(self):
        """Loop principal do servidor MCP (stdio).

        Le mensagens do stdin, processa, e escreve respostas no stdout.
        Roda ate EOF no stdin.
        """
        logger.info("AtuDIC MCP Server iniciado — conectando a %s", self.base_url)

        while True:
            msg = read_message()
            if msg is None:
                logger.info("EOF no stdin — encerrando servidor MCP")
                break

            logger.debug("← %s", json.dumps(msg, ensure_ascii=False))

            response = self.handle_message(msg)
            if response is not None:
                logger.debug("→ %s", json.dumps(response, ensure_ascii=False))
                write_message(response)
