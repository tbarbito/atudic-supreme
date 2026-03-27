"""
Serviço de Base de Conhecimento do AtuDIC.

Gerencia artigos de erros conhecidos do Protheus, correlaciona com alertas
detectados pelo log parser, e fornece sugestões de correção automáticas.
"""

import re
import hashlib
from datetime import datetime, timedelta
from app.database import get_db, release_db_connection, TransactionContext


def hash_message(message):
    """Gera hash curto para agrupar mensagens similares."""
    # Normaliza: remove números variáveis, timestamps, IDs de thread
    normalized = re.sub(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[.\d]*\b", "<TS>", message)
    normalized = re.sub(r"\b\d+\b", "<N>", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip().lower()
    return hashlib.md5(normalized.encode()).hexdigest()[:16]


def find_matching_article(category, message):
    """Busca artigo da base de conhecimento que melhor corresponde ao erro."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        # Busca artigos ativos da categoria
        cursor.execute(
            """
            SELECT id, title, error_pattern, solution, causes, description
            FROM knowledge_articles
            WHERE is_active = TRUE AND (category = %s OR category = 'geral')
            ORDER BY usage_count DESC
        """,
            (category,),
        )
        articles = cursor.fetchall()

        msg_lower = message.lower()
        for article in articles:
            pattern = article.get("error_pattern")
            if pattern:
                try:
                    if re.search(pattern, msg_lower, re.IGNORECASE):
                        return dict(article)
                except re.error:
                    # Pattern inválido, tenta match literal
                    if pattern.lower() in msg_lower:
                        return dict(article)
        return None
    finally:
        release_db_connection(conn)


def track_recurrence(environment_id, category, message, alert_id=None):
    """Registra/atualiza recorrência de um alerta. Retorna o registro."""
    msg_hash = hash_message(message)
    now = datetime.now()

    conn = get_db()
    cursor = conn.cursor()
    try:
        # Tenta atualizar se já existe
        cursor.execute(
            """
            UPDATE alert_recurrence
            SET occurrence_count = occurrence_count + 1,
                last_seen_at = %s,
                last_alert_id = COALESCE(%s, last_alert_id)
            WHERE environment_id = %s AND category = %s AND message_hash = %s
            RETURNING id, occurrence_count
        """,
            (now, alert_id, environment_id, category, msg_hash),
        )
        row = cursor.fetchone()

        if row:
            conn.commit()
            return dict(row)

        # Se não existe, busca artigo correspondente
        article = find_matching_article(category, message)
        article_id = article["id"] if article else None

        cursor.execute(
            """
            INSERT INTO alert_recurrence
                (environment_id, category, message_hash, message_sample,
                 occurrence_count, first_seen_at, last_seen_at,
                 last_alert_id, suggestion_article_id)
            VALUES (%s, %s, %s, %s, 1, %s, %s, %s, %s)
            ON CONFLICT (environment_id, category, message_hash)
            DO UPDATE SET
                occurrence_count = alert_recurrence.occurrence_count + 1,
                last_seen_at = EXCLUDED.last_seen_at,
                last_alert_id = COALESCE(EXCLUDED.last_alert_id,
                                         alert_recurrence.last_alert_id)
            RETURNING id, occurrence_count
        """,
            (environment_id, category, msg_hash, message[:500], now, now, alert_id, article_id),
        )
        row = cursor.fetchone()
        conn.commit()
        return dict(row) if row else {"id": None, "occurrence_count": 1}
    except Exception:
        conn.rollback()
        return {"id": None, "occurrence_count": 1}
    finally:
        release_db_connection(conn)


def get_recurring_errors(environment_id=None, min_count=3, days=7, limit=20):
    """Retorna erros recorrentes agrupados por padrão."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        conditions = ["ar.last_seen_at >= %s"]
        params = [datetime.now() - timedelta(days=days)]

        if environment_id:
            conditions.append("ar.environment_id = %s")
            params.append(environment_id)

        conditions.append("ar.occurrence_count >= %s")
        params.append(min_count)

        where = " AND ".join(conditions)
        params.append(limit)

        cursor.execute(
            f"""
            SELECT ar.*, e.name as environment_name,
                   ka.title as article_title, ka.solution as article_solution
            FROM alert_recurrence ar
            LEFT JOIN environments e ON ar.environment_id = e.id
            LEFT JOIN knowledge_articles ka ON ar.suggestion_article_id = ka.id
            WHERE {where}
            ORDER BY ar.occurrence_count DESC, ar.last_seen_at DESC
            LIMIT %s
        """,
            params,
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        release_db_connection(conn)


def get_error_analysis(environment_id=None, days=7):
    """Análise inteligente: agrupa erros por categoria com tendências."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        params = []
        env_filter = ""
        if environment_id:
            env_filter = "AND la.environment_id = %s"
            params.append(environment_id)

        cutoff = datetime.now() - timedelta(days=days)
        params_full = [cutoff] + params

        # Erros por categoria nos últimos N dias
        cursor.execute(
            f"""
            SELECT la.category,
                   COUNT(*) as total,
                   COUNT(*) FILTER (WHERE la.severity = 'critical') as critical_count,
                   COUNT(*) FILTER (WHERE la.severity = 'warning') as warning_count,
                   COUNT(*) FILTER (WHERE la.acknowledged = FALSE) as unresolved,
                   MIN(la.occurred_at) as first_occurrence,
                   MAX(la.occurred_at) as last_occurrence
            FROM log_alerts la
            WHERE la.occurred_at >= %s {env_filter}
            GROUP BY la.category
            ORDER BY total DESC
        """,
            params_full,
        )
        by_category = []
        for row in cursor.fetchall():
            item = dict(row)
            for key in ("first_occurrence", "last_occurrence"):
                if item.get(key):
                    item[key] = item[key].isoformat()
            by_category.append(item)

        # Tendência: comparar últimos N dias com N dias anteriores
        prev_cutoff = cutoff - timedelta(days=days)
        params_prev = [prev_cutoff, cutoff] + params

        cursor.execute(
            f"""
            SELECT la.category, COUNT(*) as total
            FROM log_alerts la
            WHERE la.occurred_at >= %s AND la.occurred_at < %s {env_filter}
            GROUP BY la.category
        """,
            params_prev,
        )
        previous = {row["category"]: row["total"] for row in cursor.fetchall()}

        for item in by_category:
            prev_count = previous.get(item["category"], 0)
            current = item["total"]
            if prev_count == 0:
                item["trend"] = "new"
            elif current > prev_count * 1.2:
                item["trend"] = "increasing"
            elif current < prev_count * 0.8:
                item["trend"] = "decreasing"
            else:
                item["trend"] = "stable"
            item["previous_count"] = prev_count

        # Top erros recorrentes com sugestões
        recurring = get_recurring_errors(environment_id=environment_id, min_count=2, days=days, limit=10)

        return {
            "by_category": by_category,
            "recurring_errors": recurring,
            "period_days": days,
        }
    finally:
        release_db_connection(conn)


def increment_article_usage(article_id):
    """Incrementa contador de uso de um artigo."""
    try:
        with TransactionContext() as (conn, cursor):
            cursor.execute(
                "UPDATE knowledge_articles SET usage_count = usage_count + 1 " "WHERE id = %s", (article_id,)
            )
    except Exception:
        pass


def search_articles(query, category=None, limit=20):
    """Busca artigos por texto — usa FTS (tsvector) quando disponivel, ILIKE como fallback."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        conditions = ["ka.is_active = TRUE"]
        params = []
        use_fts = False

        if query:
            # Tentar FTS primeiro (GIN index, O(log n) em vez de O(n))
            try:
                cursor.execute("SELECT 1 FROM information_schema.columns WHERE table_name = 'knowledge_articles' AND column_name = 'tsv' LIMIT 1")
                use_fts = cursor.fetchone() is not None
            except Exception:
                pass

            if use_fts:
                # plainto_tsquery aceita texto livre (hifens, codigos como ORA-01017)
                # sem precisar escapar operadores FTS
                clean_query = query.strip()
                if clean_query:
                    conditions.append("ka.tsv @@ plainto_tsquery('portuguese', %s)")
                    params.append(clean_query)
                else:
                    use_fts = False

            if not use_fts:
                # Fallback para ILIKE
                conditions.append("""
                    (ka.title ILIKE %s OR ka.description ILIKE %s
                     OR ka.solution ILIKE %s OR ka.tags ILIKE %s
                     OR ka.causes ILIKE %s)
                """)
                like = f"%{query}%"
                params.extend([like, like, like, like, like])

        if category:
            conditions.append("ka.category = %s")
            params.append(category)

        where = " AND ".join(conditions)

        # FTS retorna com ranking, ILIKE com usage_count
        order = "ts_rank(ka.tsv, plainto_tsquery('portuguese', %s)) DESC" if use_fts and query else "ka.usage_count DESC"
        if use_fts and query:
            params.append(query.strip())

        # limit DEVE ser o ultimo parametro (corresponde ao LIMIT %s)
        params.append(limit)

        cursor.execute(
            f"""
            SELECT ka.*
            FROM knowledge_articles ka
            WHERE {where}
            ORDER BY {order}, ka.created_at DESC
            LIMIT %s
        """,
            params,
        )
        articles = []
        for row in cursor.fetchall():
            article = dict(row)
            for key in ("created_at", "updated_at"):
                if article.get(key):
                    article[key] = article[key].isoformat()
            articles.append(article)
        return articles
    finally:
        release_db_connection(conn)


def parse_erros_protheus_md(filepath):
    """
    Parseia o arquivo erros_protheus.md e retorna lista de artigos.
    Formato esperado:
    ### `Titulo do Erro`
    **Descrição:** ...
    **Causas comuns:** ...
    **Solução:** ...
    **Referência TDN:** url
    """
    articles = []
    current_category = ""

    # Map de nomes de seção para categorias do log_parser
    category_map = {
        "ssl/tls": "network",
        "ads": "database",
        "alias": "thread_error",
        "work area": "thread_error",
        "array": "thread_error",
        "rede": "network",
        "conexão": "connection",
        "ctree": "database",
        "dbf": "database",
        "estrutura": "database",
        "topconnect": "database",
        "sql": "database",
        "compilação": "rpo",
        "rpo": "rpo",
        "tipo": "thread_error",
        "variável": "thread_error",
        "memória": "thread_error",
        "recursos": "thread_error",
        "índice": "database",
        "lock": "database",
        "transação": "database",
        "string": "thread_error",
        "diversos": "application",
    }

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        return []

    # Split por seções de categoria (## N. Titulo)
    cat_sections = re.split(r"^## \d+\.\s+", content, flags=re.MULTILINE)

    for section in cat_sections[1:]:  # Skip header
        # Primeira linha é o nome da categoria
        lines = section.strip().split("\n")
        cat_name = lines[0].strip()

        # Mapear para categoria do log_parser
        mapped_cat = "application"
        for key, val in category_map.items():
            if key in cat_name.lower():
                mapped_cat = val
                break
        current_category = mapped_cat

        # Split por artigos (### `Titulo`)
        error_sections = re.split(r"^### ", section, flags=re.MULTILINE)

        for err_section in error_sections[1:]:
            article = _parse_single_article(err_section, current_category)
            if article:
                articles.append(article)

    return articles


def _parse_single_article(text, category):
    """Parseia um único artigo do erros_protheus.md."""
    lines = text.strip().split("\n")
    if not lines:
        return None

    # Título: primeira linha (pode ter backticks)
    title = lines[0].strip().strip("`").strip()
    if not title:
        return None

    # Gerar error_pattern a partir do título
    error_pattern = re.escape(title).replace(r"\ ", ".*?")
    # Simplificar: pegar palavras-chave principais
    keywords = re.findall(r"[A-Z][a-z]+|[A-Z]{2,}|Error|error|\d{4,}", title)
    if keywords:
        error_pattern = ".*?".join(re.escape(k) for k in keywords[:4])

    full_text = "\n".join(lines[1:])

    # Extrair seções
    description = _extract_section(full_text, "Descrição")
    causes = _extract_section(full_text, "Causas comuns")
    solution = _extract_section(full_text, "Solução")
    ref_url = ""
    ref_match = re.search(r"\*\*Referência TDN:\*\*\s*(https?://\S+)", full_text)
    if ref_match:
        ref_url = ref_match.group(1)

    # Code snippets (texto entre ```)
    code = ""
    code_match = re.search(r"```[\w]*\n(.*?)```", full_text, re.DOTALL)
    if code_match:
        code = code_match.group(1).strip()

    return {
        "title": title,
        "category": category,
        "error_pattern": error_pattern,
        "description": description,
        "causes": causes,
        "solution": solution,
        "code_snippet": code,
        "reference_url": ref_url,
        "tags": category,
        "source": "erros_protheus",
    }


def _extract_section(text, section_name):
    """Extrai conteúdo de uma seção markdown (**Nome:**)."""
    pattern = rf"\*\*{section_name}[^*]*\*\*[:\s]*\n?(.*?)(?=\n\*\*|\n---|\Z)"
    match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    if match:
        content = match.group(1).strip()
        # Remove marcadores de lista
        content = re.sub(r"^-\s+", "- ", content, flags=re.MULTILINE)
        return content
    return ""


def seed_knowledge_base(filepath):
    """Importa artigos do erros_protheus.md para o banco."""
    articles = parse_erros_protheus_md(filepath)
    if not articles:
        return 0

    imported = 0
    conn = get_db()
    cursor = conn.cursor()
    try:
        for article in articles:
            # Verifica se já existe (por título)
            cursor.execute(
                "SELECT id FROM knowledge_articles WHERE title = %s AND source = %s",
                (article["title"], "erros_protheus"),
            )
            if cursor.fetchone():
                continue

            cursor.execute(
                """
                INSERT INTO knowledge_articles
                    (title, category, error_pattern, description, causes,
                     solution, code_snippet, reference_url, tags, source,
                     created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
                (
                    article["title"],
                    article["category"],
                    article["error_pattern"],
                    article["description"],
                    article["causes"],
                    article["solution"],
                    article["code_snippet"],
                    article["reference_url"],
                    article["tags"],
                    article["source"],
                    datetime.now(),
                ),
            )
            imported += 1
        conn.commit()
        return imported
    except Exception:
        conn.rollback()
        raise
    finally:
        release_db_connection(conn)
