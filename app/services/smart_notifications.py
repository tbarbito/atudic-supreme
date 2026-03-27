"""
Serviço de Notificações Inteligentes do AtuDIC.

Avalia regras de notificação configuráveis para decidir QUANDO alertar,
evitando spam e notificando apenas quando realmente necessário.
"""

from datetime import datetime, timedelta
from app.database import get_db, release_db_connection


def evaluate_notification_rules(environment_id, severity, category):
    """
    Avalia se um alerta deve gerar notificação com base nas regras configuradas.
    Retorna lista de regras que foram acionadas (com canais e destinatários).
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        now = datetime.now()

        # Busca regras ativas para este ambiente (ou globais, env_id=NULL)
        cursor.execute(
            """
            SELECT * FROM notification_rules
            WHERE is_active = TRUE
              AND (environment_id = %s OR environment_id IS NULL)
              AND severity = %s
              AND (category IS NULL OR category = '' OR category = %s)
            ORDER BY id
        """,
            (environment_id, severity, category),
        )
        rules = [dict(r) for r in cursor.fetchall()]

        triggered = []
        for rule in rules:
            # Verificar cooldown
            last_triggered = rule.get("last_triggered_at")
            cooldown = rule.get("cooldown_minutes", 30)
            if last_triggered and isinstance(last_triggered, datetime):
                if now - last_triggered < timedelta(minutes=cooldown):
                    continue  # Em cooldown, pula

            # Verificar min_occurrences na janela de tempo
            min_occ = rule.get("min_occurrences", 1)
            window = rule.get("time_window_minutes", 5)

            if min_occ > 1:
                window_start = now - timedelta(minutes=window)
                cursor.execute(
                    """
                    SELECT COUNT(*) as cnt FROM log_alerts
                    WHERE environment_id = %s
                      AND severity = %s
                      AND category = %s
                      AND occurred_at >= %s
                """,
                    (environment_id, severity, category, window_start),
                )
                count = cursor.fetchone()["cnt"]
                if count < min_occ:
                    continue  # Não atingiu mínimo

            # Regra acionada — atualizar timestamp e contador
            cursor.execute(
                """
                UPDATE notification_rules
                SET last_triggered_at = %s,
                    trigger_count = trigger_count + 1
                WHERE id = %s
            """,
                (now, rule["id"]),
            )

            triggered.append(
                {
                    "rule_id": rule["id"],
                    "rule_name": rule["name"],
                    "notify_email": rule.get("notify_email", True),
                    "notify_whatsapp": rule.get("notify_whatsapp", False),
                    "notify_webhook": rule.get("notify_webhook", False),
                    "recipients": rule.get("recipients", ""),
                }
            )

        if triggered:
            conn.commit()

        return triggered
    except Exception:
        conn.rollback()
        return []
    finally:
        release_db_connection(conn)


def get_notification_stats(environment_id=None, days=30):
    """Retorna estatísticas de notificações disparadas."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        conditions = ["is_active = TRUE"]
        params = []

        if environment_id:
            conditions.append("(environment_id = %s OR environment_id IS NULL)")
            params.append(environment_id)

        where = " AND ".join(conditions)
        cursor.execute(
            f"""
            SELECT id, name, severity, category, min_occurrences,
                   time_window_minutes, cooldown_minutes,
                   trigger_count, last_triggered_at,
                   notify_email, notify_whatsapp, notify_webhook,
                   environment_id
            FROM notification_rules
            WHERE {where}
            ORDER BY trigger_count DESC
        """,
            params,
        )

        rules = []
        for row in cursor.fetchall():
            rule = dict(row)
            if rule.get("last_triggered_at"):
                rule["last_triggered_at"] = rule["last_triggered_at"].isoformat()
            rules.append(rule)
        return rules
    finally:
        release_db_connection(conn)
