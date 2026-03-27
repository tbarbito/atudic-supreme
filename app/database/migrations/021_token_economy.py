"""
Migration 021: Economia de tokens — pre-computacao de resumos

Adiciona colunas de summary para reduzir tokens de contexto enviados ao LLM:
- knowledge_articles.solution_summary — resumo compacto da solucao (max 200 chars)
- alert_trends view — tendencias agregadas de alertas por categoria
"""


def upgrade(cursor):
    # 1. Summary compacto para artigos da KB
    cursor.execute("""
        ALTER TABLE knowledge_articles
        ADD COLUMN IF NOT EXISTS solution_summary TEXT
    """)

    # Preencher solution_summary inicial a partir do solution existente (truncado)
    cursor.execute("""
        UPDATE knowledge_articles
        SET solution_summary = LEFT(
            REGEXP_REPLACE(
                COALESCE(solution, description, ''),
                E'\\s+', ' ', 'g'
            ),
            200
        )
        WHERE solution_summary IS NULL
    """)

    # 2. View materializada de tendencias de alertas
    # Agrega alertas por categoria com contagem por janela temporal
    cursor.execute("DROP MATERIALIZED VIEW IF EXISTS alert_trends")
    cursor.execute("""
        CREATE MATERIALIZED VIEW alert_trends AS
        SELECT
            la.environment_id,
            la.category,
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE la.occurred_at >= NOW() - INTERVAL '1 hour') AS last_hour,
            COUNT(*) FILTER (WHERE la.occurred_at >= NOW() - INTERVAL '24 hours') AS last_24h,
            COUNT(*) FILTER (WHERE la.severity = 'critical') AS critical_count,
            COUNT(*) FILTER (WHERE la.severity = 'error') AS error_count,
            MAX(la.occurred_at) AS last_seen,
            CASE
                WHEN COUNT(*) FILTER (WHERE la.occurred_at >= NOW() - INTERVAL '1 hour') >
                     COUNT(*) FILTER (WHERE la.occurred_at >= NOW() - INTERVAL '24 hours'
                                      AND la.occurred_at < NOW() - INTERVAL '1 hour') / GREATEST(23, 1)
                THEN 'crescente'
                WHEN COUNT(*) FILTER (WHERE la.occurred_at >= NOW() - INTERVAL '1 hour') = 0
                THEN 'inativo'
                ELSE 'estavel'
            END AS trend
        FROM log_alerts la
        WHERE la.occurred_at >= NOW() - INTERVAL '7 days'
        GROUP BY la.environment_id, la.category
    """)

    # Index para refresh rapido
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_alert_trends_env_cat
        ON alert_trends (environment_id, category)
    """)

    # 3. Indice para busca FTS na knowledge_articles (substituir ILIKE)
    cursor.execute("""
        ALTER TABLE knowledge_articles
        ADD COLUMN IF NOT EXISTS tsv tsvector
    """)

    # Popular tsvector com conteudo existente
    cursor.execute("""
        UPDATE knowledge_articles
        SET tsv = setweight(to_tsvector('portuguese', COALESCE(title, '')), 'A') ||
                  setweight(to_tsvector('portuguese', COALESCE(description, '')), 'B') ||
                  setweight(to_tsvector('portuguese', COALESCE(solution, '')), 'B') ||
                  setweight(to_tsvector('portuguese', COALESCE(tags, '')), 'C')
        WHERE tsv IS NULL
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_knowledge_articles_tsv
        ON knowledge_articles USING gin(tsv)
    """)


def downgrade(cursor):
    cursor.execute("DROP INDEX IF EXISTS idx_knowledge_articles_tsv")
    cursor.execute("ALTER TABLE knowledge_articles DROP COLUMN IF EXISTS tsv")
    cursor.execute("DROP MATERIALIZED VIEW IF EXISTS alert_trends")
    cursor.execute("ALTER TABLE knowledge_articles DROP COLUMN IF EXISTS solution_summary")
