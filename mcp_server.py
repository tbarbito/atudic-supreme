#!/usr/bin/env python3
"""Entry point do MCP Server standalone do AtuDIC.

Conecta agentes IA externos (Claude Code, Cursor, etc.) ao AtuDIC
via Model Context Protocol (MCP) sobre transporte stdio.

Uso direto:
  python mcp_server.py --url http://localhost:5000 --api-key at_xxx

Claude Code:
  claude mcp add atudic -- python /caminho/mcp_server.py --url http://host:5000 --api-key at_xxx

Variaveis de ambiente (alternativa aos argumentos):
  AtuDIC_URL=http://localhost:5000
  AtuDIC_API_KEY=at_xxx
"""

import argparse
import logging
import os
import sys

# Adiciona raiz do projeto ao path para imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.mcp.server import AtuDICMCPServer


def setup_logging(debug=False):
    """Configura logging para stderr (stdout e reservado para MCP).

    Args:
        debug: Se True, loga em nivel DEBUG.
    """
    level = logging.DEBUG if debug else logging.INFO
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter("[%(asctime)s] %(name)s %(levelname)s: %(message)s", "%H:%M:%S")
    )
    logger = logging.getLogger("atudic-mcp")
    logger.setLevel(level)
    logger.addHandler(handler)
    return logger


def main():
    """Ponto de entrada principal do MCP Server."""
    parser = argparse.ArgumentParser(
        description="AtuDIC MCP Server — expoe ferramentas DevOps para agentes IA"
    )
    parser.add_argument(
        "--url",
        default=os.environ.get("AtuDIC_URL", "http://localhost:5000"),
        help="URL base do AtuDIC (default: $AtuDIC_URL ou http://localhost:5000)",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("AtuDIC_API_KEY"),
        help="Chave de API do AtuDIC (default: $AtuDIC_API_KEY)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        default=os.environ.get("AtuDIC_MCP_DEBUG", "").lower() in ("1", "true"),
        help="Ativar modo debug (loga JSON-RPC em stderr)",
    )
    args = parser.parse_args()

    logger = setup_logging(args.debug)

    if not args.api_key:
        logger.error(
            "API key obrigatoria. Use --api-key ou defina AtuDIC_API_KEY."
        )
        sys.exit(1)

    logger.info("Iniciando AtuDIC MCP Server v1.0.0")
    logger.info("URL: %s", args.url)
    logger.info("Debug: %s", args.debug)

    server = AtuDICMCPServer(base_url=args.url, api_key=args.api_key)

    try:
        server.run()
    except KeyboardInterrupt:
        logger.info("Servidor MCP encerrado pelo usuario")
    except Exception as e:
        logger.error("Erro fatal no servidor MCP: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
