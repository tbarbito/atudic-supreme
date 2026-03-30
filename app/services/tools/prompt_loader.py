"""
Carregamento e cache do system prompt do agente GolIAs.

Carrega o prompt core (BIIZHUBOPS_AGENT_CONTEXT_CORE.md) com fallback
para o prompt legado ou fallback hardcoded.
"""
import os
import logging

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT_CACHE = None

_SYSTEM_PROMPT_FALLBACK = (
    "Voce e o GolIAs, Agente Orquestrador e Executor de Tarefas do BiizHubOps, "
    "plataforma DevOps para TOTVS Protheus.\n"
    "Voce NAO e um chatbot. Voce e um terminal inteligente: recebe comandos "
    "em linguagem natural, aciona ferramentas e entrega resultados.\n\n"
    "Regras: USE ferramentas para dados reais (nunca invente). Primeira frase = "
    "resposta ou acao. Cite fontes. Estruture com tabelas markdown.\n"
    "Erros: tente recuperar sozinho (max 3 retries). Se bloqueado, reporte causa + "
    "sugestao ao operador.\n"
    "Seguranca: nunca exponha credenciais. Acoes destrutivas exigem confirmacao.\n\n"
    "Formato de resposta: Status (Sucesso/Parcial/Falha) | Acao realizada | "
    "Resultado | Proximo passo.\n\n"
    "## Usuario e ambiente atual\n{user_context}\n\n"
    "## Dados consultados do sistema\n{context}"
)


def load_system_prompt():
    """Carrega system prompt core do arquivo, com cache.

    Procura BIIZHUBOPS_AGENT_CONTEXT_CORE.md primeiro, fallback para
    BIIZHUBOPS_AGENT_CONTEXT.md, fallback hardcoded.
    """
    global _SYSTEM_PROMPT_CACHE
    if _SYSTEM_PROMPT_CACHE is not None:
        return _SYSTEM_PROMPT_CACHE

    # tools/ → services/ → app/ → projeto_raiz/
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    candidates = [
        os.path.join(base_dir, "prompt", "BIIZHUBOPS_AGENT_CONTEXT_CORE.md"),
        os.path.join(base_dir, "prompt", "BIIZHUBOPS_AGENT_CONTEXT.md"),
        os.path.join(base_dir, "prompt", "BiizHubOps_AGENT_CONTEXT_CORE.md"),
        os.path.join(base_dir, "prompt", "BiizHubOps_AGENT_CONTEXT.md"),
        os.path.join(base_dir, "memory", "BiizHubOps_AGENT_CONTEXT.md"),
    ]

    for path in candidates:
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                if "CORE" not in os.path.basename(path):
                    content += (
                        "\n\n## Usuário e ambiente atual\n{user_context}\n\n"
                        "## Dados consultados do sistema\n{context}"
                    )
                _SYSTEM_PROMPT_CACHE = content
                logger.info("System prompt carregado de %s (%d chars)", path, len(content))
                return content
            except Exception as e:
                logger.warning("Erro ao carregar system prompt: %s", e)

    logger.warning("Arquivo BIIZHUBOPS_AGENT_CONTEXT_CORE.md nao encontrado, usando fallback")
    _SYSTEM_PROMPT_CACHE = _SYSTEM_PROMPT_FALLBACK
    return _SYSTEM_PROMPT_FALLBACK


def reload_system_prompt():
    """Forca recarga do system prompt. Retorna info sobre o reload."""
    global _SYSTEM_PROMPT_CACHE
    _SYSTEM_PROMPT_CACHE = None
    content = load_system_prompt()
    is_fallback = content == _SYSTEM_PROMPT_FALLBACK
    return {
        "message": (
            "Contexto recarregado com sucesso" if not is_fallback
            else "Usando fallback (arquivo nao encontrado)"
        ),
        "chars": len(content),
        "fallback": is_fallback,
    }
