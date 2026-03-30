# -*- coding: utf-8 -*-
"""
AgentConfig — Configuracao centralizada do agente GolIAs Supreme.

Unifica configs do BiizHubOps (GolIAs) + ExtraiRPO (Analista).
"""


class AgentConfig:
    """Singleton de configuracao do agente."""

    # === LLM ===
    TEMPERATURE_DEFAULT = 0.7
    TEMPERATURE_DETERMINISTIC = 0.2  # Para analises factuais (dicionarista, impacto)
    MAX_TOKENS_DEFAULT = 2048
    TOKEN_BUDGET_DEFAULT = 50_000

    # === Chat History ===
    HISTORY_LIMIT_REACT = 6  # Mensagens no contexto do ReAct loop
    HISTORY_SUMMARIZE_THRESHOLD = 8  # Resumir historico apos N mensagens

    # === Memory ===
    CHUNK_MAX_SIZE = 3500  # Caracteres por chunk
    CHUNK_OVERLAP = 500  # Overlap entre chunks
    QUERY_EMBED_CACHE_MAX = 200  # Cache LRU de embeddings

    # === Skills ===
    MAX_SKILLS_PER_REQUEST = 5
    MAX_SKILL_TOKENS = 4000

    # === Timeouts (segundos) ===
    COMMAND_TIMEOUT = 30
    LLM_TIMEOUT_DEFAULT = 60
    LLM_TIMEOUTS = {
        "ollama": 15,
        "groq": 20,
        "openai": 60,
        "anthropic": 90,
        "google": 90,
    }

    # === Workspace ===
    WORKSPACE_BATCH_COMMIT = 5  # Commit a cada N arquivos na ingestao
    WORKSPACE_MAX_RAM_MB = 512  # Limite de RAM para ingestao
    WORKSPACE_MAX_FILE_SIZE = 5_000_000  # 5MB — pular arquivos maiores
    WORKSPACE_CHUNK_SIZE = 4000  # Chars por chunk de fonte
    WORKSPACE_CHUNK_OVERLAP = 400  # Overlap entre chunks de fonte

    # === Specialists ===
    # Total: 15 (9 BiizHubOps + 6 ExtraiRPO)
    SPECIALIST_COUNT = 15
    MAX_PARALLEL_AGENTS = 3  # Maximo de sub-agentes simultaneos
    MAX_CHAIN_STEPS = 4  # Maximo de etapas em chain orchestration

    # === Tools ===
    # Total: 63+ (59 BiizHubOps + 4 workspace)
    TOOL_COUNT = 63

    # === RBAC ===
    PROFILE_LEVELS = {
        "viewer": 1,
        "operator": 2,
        "admin": 3,
    }

    # === Retry ===
    MAX_RETRIES = 3
    RETRY_BACKOFF_BASE = 2  # Exponential backoff: 2^n segundos
    RETRIABLE_ERRORS = ["timeout", "rate_limit", "server_error"]
