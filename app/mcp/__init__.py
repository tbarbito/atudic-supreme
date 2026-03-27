# MCP Server — Model Context Protocol para AtuDIC
# Expoe ferramentas do AtuDIC para agentes IA externos (Claude Code, Cursor, etc.)
#
# Arquitetura:
#   Claude Code / Agente Externo
#       ↓ (JSON-RPC via stdio)
#   mcp_server.py (standalone)
#       ↓ (HTTP REST)
#   Flask Gateway (/api/mcp/*)
#       ↓ (execute_tool)
#   agent_tools.py (21 ferramentas)
