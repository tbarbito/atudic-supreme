"""
Connection Alias Resolver — resolve nomes/aliases para IDs de conexao.

Quando o LLM gera tool calls com nomes como "HML", "PRD", "homologacao",
este modulo resolve para o conn_id correto antes da execucao.

Funciona como middleware entre o output do LLM e o execute_tool().
"""

import logging
import re

from app.database import get_db, release_db_connection

logger = logging.getLogger(__name__)

# Aliases conhecidos mapeados para patterns de busca no nome da conexao
# Ordem importa: mais especificos primeiro
_ALIAS_PATTERNS = [
    # Producao
    (re.compile(r"^(prd|prod|produ[cç][aã]o|production)$", re.IGNORECASE), ["produc", "prd", "prod"]),
    # Homologacao
    (re.compile(r"^(hml|homolog|homologa[cç][aã]o|staging|stg)$", re.IGNORECASE), ["homolog", "hml", "staging"]),
    # Desenvolvimento
    (re.compile(r"^(dev|desenvolvimento|develop|development)$", re.IGNORECASE), ["desenv", "dev", "develop"]),
    # QA / Teste
    (re.compile(r"^(qa|teste|test|quality)$", re.IGNORECASE), ["qa", "test", "qualit"]),
]

# Campos de tool params que contem IDs de conexao
_CONN_ID_FIELDS = [
    "conn_id_a", "conn_id_b",
    "connection_id", "conn_id",
    "source_conn_id", "target_conn_id",
]

# Cache de conexoes por environment (evita queries repetidas na mesma sessao)
_conn_cache = {}


def _get_connections(environment_id):
    """Busca conexoes do ambiente com cache."""
    if not environment_id:
        return []

    cache_key = int(environment_id)
    if cache_key in _conn_cache:
        return _conn_cache[cache_key]

    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT id, name, driver, host, database_name
            FROM database_connections
            WHERE environment_id = %s
            ORDER BY name
            """,
            (environment_id,),
        )
        connections = [dict(row) for row in cursor.fetchall()]
        _conn_cache[cache_key] = connections
        return connections
    except Exception as e:
        logger.warning("Erro ao buscar conexoes para resolver: %s", e)
        return []
    finally:
        release_db_connection(conn)


def invalidate_cache(environment_id=None):
    """Limpa cache de conexoes (chamar quando conexoes mudam)."""
    if environment_id:
        _conn_cache.pop(int(environment_id), None)
    else:
        _conn_cache.clear()


def _resolve_alias(alias_value, connections):
    """Tenta resolver um alias (string) para um conn_id (int).

    Estrategia:
    1. Se ja for int ou string numerica, retorna como int
    2. Tenta match por alias patterns conhecidos
    3. Tenta match parcial no nome da conexao (case-insensitive)
    4. Tenta match no database_name
    5. Retorna None se nao encontrar
    """
    if alias_value is None:
        return None

    # Ja e um ID numerico
    if isinstance(alias_value, int):
        return alias_value
    if isinstance(alias_value, str) and alias_value.strip().isdigit():
        return int(alias_value.strip())

    alias_str = str(alias_value).strip().lower()
    if not alias_str or not connections:
        return None

    # Match via alias patterns
    for pattern, search_terms in _ALIAS_PATTERNS:
        if pattern.match(alias_str):
            for conn in connections:
                conn_name = (conn.get("name") or "").lower()
                conn_db = (conn.get("database_name") or "").lower()
                searchable = f"{conn_name} {conn_db}"
                for term in search_terms:
                    if term in searchable:
                        logger.info(
                            "Alias '%s' resolvido para conexao '%s' (ID %s) via pattern",
                            alias_value, conn.get("name"), conn["id"],
                        )
                        return conn["id"]

    # Match direto parcial no nome da conexao
    for conn in connections:
        conn_name = (conn.get("name") or "").lower()
        if alias_str in conn_name or conn_name in alias_str:
            logger.info(
                "Alias '%s' resolvido para conexao '%s' (ID %s) via nome",
                alias_value, conn.get("name"), conn["id"],
            )
            return conn["id"]

    # Match no database_name
    for conn in connections:
        conn_db = (conn.get("database_name") or "").lower()
        if alias_str in conn_db or conn_db in alias_str:
            logger.info(
                "Alias '%s' resolvido para conexao '%s' (ID %s) via database_name",
                alias_value, conn.get("name"), conn["id"],
            )
            return conn["id"]

    logger.warning("Alias '%s' nao resolvido — nenhuma conexao correspondente", alias_value)
    return None


def resolve_connection_params(params, environment_id):
    """Resolve aliases em todos os campos de conn_id dos params.

    Retorna (params_resolvidos, resolucoes_feitas) onde resolucoes_feitas
    e uma lista de strings descrevendo o que foi resolvido (para log/working memory).
    """
    if not environment_id:
        return params, []

    connections = _get_connections(environment_id)
    if not connections:
        return params, []

    resolved = dict(params)
    resolutions = []

    for field in _CONN_ID_FIELDS:
        value = resolved.get(field)
        if value is None:
            continue

        # So tenta resolver se nao for inteiro puro
        if isinstance(value, int):
            continue
        if isinstance(value, str) and value.strip().isdigit():
            resolved[field] = int(value.strip())
            continue

        # Resolver alias
        conn_id = _resolve_alias(value, connections)
        if conn_id is not None:
            resolved[field] = conn_id
            conn_name = next((c["name"] for c in connections if c["id"] == conn_id), "?")
            resolutions.append(f"{field}: '{value}' → {conn_name} (ID {conn_id})")

    return resolved, resolutions


def get_connections_summary(environment_id):
    """Retorna resumo formatado das conexoes para injecao no prompt.

    Formato compacto para economia de tokens.
    """
    connections = _get_connections(environment_id)
    if not connections:
        return ""

    lines = ["### Conexoes de Banco Disponiveis"]
    lines.append("Use estes IDs ao chamar tools que exigem conn_id. "
                 "Se o usuario mencionar aliases (HML, PRD, dev, etc.), "
                 "resolva para o ID correto automaticamente.")
    for c in connections:
        driver = c.get("driver", "?")
        host = c.get("host", "?")
        db_name = c.get("database_name", "?")
        lines.append(f"- **ID {c['id']}**: {c.get('name', '?')} ({driver}) — {host}/{db_name}")

    return "\n".join(lines)
