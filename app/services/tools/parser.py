"""
Parser de tool calls em respostas de LLM.

Extrai chamadas de ferramentas (JSON) de respostas em texto livre do LLM.
Tolerante com diferentes formatos: code blocks, JSON inline, JSON misturado em texto.

Também detecta quando o LLM respondeu com um "plano" em vez de executar
(comportamento comum do Gemini Flash).
"""
import re
import json
import logging

logger = logging.getLogger(__name__)

# Regex pre-compilados (evita recompilação por mensagem)
_RE_TOOL_JSON_BLOCK = re.compile(r'```json\s*(\{[^`]*?"tool"[^`]*?\})\s*```', re.DOTALL)
_RE_TOOL_CODE_BLOCK = re.compile(r'```\s*(\{[^`]*?"tool"[^`]*?\})\s*```', re.DOTALL)
_RE_PLAN_NUMBERED = re.compile(r"^\s*1\.\s+", re.MULTILINE)
_RE_PLAN_PREFIX = re.compile(r"(?i)(PLANO|PLAN)\s*:")
_RE_PLAN_VOU = re.compile(r"(?i)vou\s+(consultar|buscar|executar|verificar)")
_RE_PLAN_PASSO = re.compile(r"(?i)(passo|etapa)\s+\d")
_RE_PLAN_PRECISO = re.compile(r"(?i)para\s+isso.*preciso")


def parse_tool_call(response_text):
    """Detecta se a resposta do LLM contém um tool call JSON.

    Tolerante com diferentes formatos de LLM:
    - Code block: ```json {"tool": "..."} ```
    - JSON inline: {"tool": "...", "params": {...}}
    - Texto + JSON misturado: "Vou consultar... {"tool": "..."}"

    Returns:
        dict com {"tool": "nome", "params": {...}} ou None
    """
    # Buscar bloco ```json ... ``` com campo "tool" (regex pre-compilado)
    for pattern in (_RE_TOOL_JSON_BLOCK, _RE_TOOL_CODE_BLOCK):
        match = pattern.search(response_text)
        if match:
            try:
                data = json.loads(match.group(1))
                if "tool" in data:
                    return {
                        "tool": data["tool"],
                        "params": data.get("params", data.get("parameters", {})),
                    }
            except (json.JSONDecodeError, KeyError):
                continue

    # Fallback: buscar JSON com "tool" em qualquer lugar do texto
    tool_idx = response_text.find('"tool"')
    if tool_idx == -1:
        tool_idx = response_text.find("'tool'")

    # Se encontrou "tool", tentar brace balancing
    brace_start = -1
    if tool_idx >= 0:
        brace_start = response_text.rfind("{", 0, tool_idx)

    # Balancear chaves para encontrar o fim do JSON
    depth = 0
    for i in range(max(0, brace_start), len(response_text)) if brace_start >= 0 else []:
        if response_text[i] == "{":
            depth += 1
        elif response_text[i] == "}":
            depth -= 1
            if depth == 0:
                json_str = response_text[brace_start: i + 1]
                try:
                    data = json.loads(json_str)
                    if "tool" in data:
                        return {
                            "tool": data["tool"],
                            "params": data.get("params", data.get("parameters", {})),
                        }
                except (json.JSONDecodeError, KeyError):
                    pass
                break

    # Fallback: detectar formato XML que alguns LLMs geram
    # Ex: <get_server_variables><environment_id>2</environment_id></get_server_variables>
    # Tags HTML comuns a ignorar
    _html_tags = {"div", "span", "p", "br", "a", "table", "tr", "td", "th", "ul", "li", "ol", "h1", "h2", "h3", "h4", "strong", "em", "code", "pre", "i", "b"}
    xml_match = re.search(r'<([a-z_]\w+)>\s*(.*?)\s*</\1>', response_text, re.DOTALL)
    if xml_match:
        tool_name = xml_match.group(1)
        xml_body = xml_match.group(2)
        if tool_name not in _html_tags:
            params = {}
            for param_match in re.finditer(r'<([a-z_]\w+)>(.*?)</\1>', xml_body):
                key = param_match.group(1)
                val = param_match.group(2).strip()
                try:
                    val = int(val)
                except (ValueError, TypeError):
                    pass
                params[key] = val
            logger.info("Parser: detectou tool call em formato XML: %s", tool_name)
            return {"tool": tool_name, "params": params}

    return None


def looks_like_plan_not_action(text):
    """Detecta se o LLM respondeu com um plano/lista em vez de executar.

    Gemini Flash frequentemente lista passos (1. Consultar... 2. Retornar...)
    em vez de emitir o JSON da tool call.

    Returns:
        True se o texto parece ser um plano em vez de uma ação
    """
    if not text or len(text) < 20:
        return False

    indicators = [
        _RE_PLAN_NUMBERED.search(text),
        _RE_PLAN_PREFIX.search(text),
        _RE_PLAN_VOU.search(text),
        _RE_PLAN_PASSO.search(text),
        _RE_PLAN_PRECISO.search(text),
    ]

    return sum(1 for i in indicators if i) >= 2
