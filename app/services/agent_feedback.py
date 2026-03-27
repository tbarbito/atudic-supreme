"""
Feedback loop do GolIAs — avaliação de respostas pelo usuário.

Responsabilidades:
- Registrar feedback (thumbs up/down) por mensagem
- Calcular métricas de satisfação por intent/specialist
- Detectar skills e intents com baixa performance
"""

import json
import logging

logger = logging.getLogger(__name__)


class FeedbackService:
    """Gerencia feedback de respostas do agente."""

    def __init__(self, memory):
        self.memory = memory

    def save_feedback(self, message_id, session_id, environment_id, rating, metadata=None):
        """Salva feedback do usuário.

        Args:
            message_id: ID da mensagem avaliada
            session_id: ID da sessão
            environment_id: ID do ambiente
            rating: 1 (positivo) ou -1 (negativo)
            metadata: dict com intent, specialist, skills_used, tools_used
        """
        conn = self.memory._get_conn()
        cursor = conn.cursor()

        meta = metadata or {}
        skills = json.dumps(meta.get("skills_used", []))
        tools = json.dumps(meta.get("tools_used", []))

        cursor.execute(
            """
            INSERT INTO agent_feedback
                (message_id, session_id, environment_id, rating, intent, specialist, skills_used, tools_used)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                message_id,
                session_id,
                environment_id,
                rating,
                meta.get("intent", ""),
                meta.get("specialist", ""),
                skills,
                tools,
            ),
        )
        conn.commit()

        logger.info(
            "📊 Feedback salvo: msg=%s rating=%d intent=%s",
            message_id, rating, meta.get("intent", "?"),
        )

    def get_satisfaction_stats(self, days=7, environment_id=None):
        """Calcula métricas de satisfação agregadas.

        Returns:
            dict com total, positivos, negativos, taxa por intent, taxa por specialist
        """
        conn = self.memory._get_conn()
        cursor = conn.cursor()

        # Filtro de período
        where = "WHERE created_at >= datetime('now', ?)"
        params = [f"-{days} days"]

        if environment_id:
            where += " AND environment_id = ?"
            params.append(environment_id)

        # Totais
        cursor.execute(f"SELECT COUNT(*) as total, SUM(CASE WHEN rating > 0 THEN 1 ELSE 0 END) as positive, SUM(CASE WHEN rating < 0 THEN 1 ELSE 0 END) as negative FROM agent_feedback {where}", params)
        row = cursor.fetchone()
        total = row["total"] or 0
        positive = row["positive"] or 0
        negative = row["negative"] or 0

        # Por intent
        cursor.execute(
            f"""
            SELECT intent,
                   COUNT(*) as total,
                   SUM(CASE WHEN rating > 0 THEN 1 ELSE 0 END) as positive,
                   SUM(CASE WHEN rating < 0 THEN 1 ELSE 0 END) as negative
            FROM agent_feedback
            {where}
            GROUP BY intent
            ORDER BY total DESC
        """,
            params,
        )
        by_intent = []
        for r in cursor.fetchall():
            t = r["total"] or 1
            by_intent.append({
                "intent": r["intent"],
                "total": t,
                "positive": r["positive"] or 0,
                "negative": r["negative"] or 0,
                "satisfaction": round((r["positive"] or 0) / t * 100, 1),
            })

        # Por specialist
        cursor.execute(
            f"""
            SELECT specialist,
                   COUNT(*) as total,
                   SUM(CASE WHEN rating > 0 THEN 1 ELSE 0 END) as positive,
                   SUM(CASE WHEN rating < 0 THEN 1 ELSE 0 END) as negative
            FROM agent_feedback
            {where} AND specialist != ''
            GROUP BY specialist
            ORDER BY total DESC
        """,
            params,
        )
        by_specialist = []
        for r in cursor.fetchall():
            t = r["total"] or 1
            by_specialist.append({
                "specialist": r["specialist"],
                "total": t,
                "satisfaction": round((r["positive"] or 0) / t * 100, 1),
            })

        satisfaction_rate = round(positive / max(total, 1) * 100, 1)

        return {
            "period_days": days,
            "total": total,
            "positive": positive,
            "negative": negative,
            "satisfaction_rate": satisfaction_rate,
            "by_intent": by_intent,
            "by_specialist": by_specialist,
        }

    def get_low_performing(self, days=7, min_feedback=3, threshold=70):
        """Identifica intents/specialists com satisfação abaixo do threshold.

        Returns:
            list de alertas sobre performance baixa
        """
        stats = self.get_satisfaction_stats(days=days)
        alerts = []

        for item in stats["by_intent"]:
            if item["total"] >= min_feedback and item["satisfaction"] < threshold:
                alerts.append({
                    "type": "intent",
                    "name": item["intent"],
                    "satisfaction": item["satisfaction"],
                    "total": item["total"],
                    "message": f"Intent '{item['intent']}' com {item['satisfaction']}% de satisfação ({item['total']} avaliações)",
                })

        for item in stats["by_specialist"]:
            if item["total"] >= min_feedback and item["satisfaction"] < threshold:
                alerts.append({
                    "type": "specialist",
                    "name": item["specialist"],
                    "satisfaction": item["satisfaction"],
                    "total": item["total"],
                    "message": f"Specialist '{item['specialist']}' com {item['satisfaction']}% de satisfação",
                })

        return alerts
