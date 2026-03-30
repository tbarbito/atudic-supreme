"""
Configurações centralizadas do GolIAs — agente inteligente do BiizHubOps.

Elimina magic numbers dos serviços do agente. Defaults hardcoded aqui,
override via tabela agent_settings (PostgreSQL) no futuro.
"""


class AgentConfig:
    """Configurações do agente. Valores centralizados, fáceis de ajustar."""

    # === LLM Parameters ===
    TEMPERATURE_DEFAULT = 0.7
    TEMPERATURE_REACT = 0.5
    TEMPERATURE_SUMMARY = 0.3
    TEMPERATURE_CONFIRMED_ACTION = 0.5
    MAX_TOKENS_DEFAULT = 2048
    MAX_TOKENS_REACT = 2048
    MAX_TOKENS_SUMMARY = 300
    MAX_TOKENS_CONFIRMED_ACTION = 1024

    # === Token Budget (ReAct) ===
    TOKEN_BUDGET_DEFAULT = 50_000
    MAX_REACT_ITERATIONS = 10
    TOKEN_ESTIMATE_DIVISOR = 3  # chars / 3 ≈ tokens (Claude ~3.5 chars/token)

    # === Cost Estimation (USD por 1M tokens) ===
    LLM_INPUT_COST_PER_MILLION = 3
    LLM_OUTPUT_COST_PER_MILLION = 15

    # === Chat History ===
    HISTORY_LIMIT_TWOSTEOP = 20  # mensagens carregadas para two-step
    HISTORY_LIMIT_REACT = 6  # mensagens carregadas para ReAct
    HISTORY_KEEP_RECENT = 4  # mensagens recentes mantidas intactas
    HISTORY_SUMMARIZE_THRESHOLD = 8  # a partir de quantas msgs sumarizar
    HISTORY_RESUMMARIZE_DELTA = 4  # msgs novas para re-sumarizar

    # === Truncation ===
    ASSISTANT_MSG_TRUNCATE = 500  # chars de resposta no history
    USER_MSG_TRUNCATE = 300  # chars de mensagem do usuario no history
    TOOL_RESULT_TRUNCATE = 3000  # chars de resultado de tool
    KB_ARTICLE_TRUNCATE = 500  # chars de artigo da KB
    STDOUT_TRUNCATE = 5000  # chars de stdout de comando
    STDERR_TRUNCATE = 2000  # chars de stderr de comando

    # === Search/Query Limits ===
    DEFAULT_ALERTS_LIMIT = 10
    MAX_ALERTS_LIMIT = 50
    DEFAULT_ALERT_SUMMARY_DAYS = 7
    MAX_ALERT_SUMMARY_DAYS = 30
    MIN_RECURRING_ERROR_COUNT = 3
    DEFAULT_KB_SEARCH_LIMIT = 5
    MAX_KB_SEARCH_LIMIT = 20
    DEFAULT_DB_QUERY_ROWS = 100
    MAX_DB_QUERY_ROWS = 500
    DEFAULT_MEMORY_SEARCH_LIMIT = 5
    DEFAULT_PIPELINES_LIMIT = 5
    DEFAULT_SX2_LOOKUP_LIMIT = 5

    # === Skills ===
    MAX_SKILLS_PER_REQUEST = 5
    MAX_SKILL_TOKENS = 4000
    SKILL_INTENT_MATCH_WEIGHT = 10
    SKILL_KEYWORD_MATCH_WEIGHT = 2
    SKILL_SPECIALIST_BOOST = 15
    DEFAULT_SKILL_PRIORITY = 50

    # === Memory (FTS5/chunks) ===
    CHUNK_MAX_SIZE = 3500
    CHUNK_OVERLAP = 500  # ~14% overlap para manter coerencia semantica

    # === Sandbox / System Tools ===
    MAX_FILE_READ_SIZE = 1_048_576  # 1MB
    MAX_FILE_WRITE_SIZE = 102_400  # 100KB
    COMMAND_TIMEOUT = 30  # segundos
    MAX_DIRECTORY_ENTRIES = 100
    MAX_DIRECTORY_SEARCH_DEPTH = 5
    MAX_FILES_TO_SEARCH = 100
    MAX_SEARCH_RESULTS = 50

    # === Intent Detection ===
    SIMPLE_INTENT_CONFIDENCE_THRESHOLD = 0.8
    LLM_INTENT_FALLBACK_THRESHOLD = 0.68  # abaixo disso, pedir ao LLM classificar

    # === Session ===
    SESSION_CLEANUP_DAYS = 30


# Singleton global
agent_config = AgentConfig()
