"""
Agent Tools — Modulo modularizado de ferramentas do agente.

Submodulos:
- helpers: _internal_api, _serialize_rows, _check_permission
- formatters: format_tool_result_for_llm e helpers de formatação
- registry: AGENT_TOOLS, register_tool, get_available_tools, execute_tool

O arquivo agent_tools.py na raiz de services/ continua como facade
para retrocompatibilidade.
"""
