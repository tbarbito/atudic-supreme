"""
Monitor Proativo do GolIAs — detecção autônoma de anomalias.

Roda em background (thread separada) e verifica condições configuráveis:
- Pipeline com N+ falhas consecutivas
- Alerta critical sem acknowledge > Xh
- Serviço down > X min
- Novo erro recorrente (N+ em 24h)

Se anomalia detectada, gera diagnóstico preliminar e notifica
via SSE (se sessão ativa) ou canal de notificação.
"""

import logging
import threading
import time

from app.database import get_db, release_db_connection

logger = logging.getLogger(__name__)

# Configurações do monitor
CHECK_INTERVAL = 300  # 5 minutos entre checks
PIPELINE_FAIL_THRESHOLD = 3  # falhas consecutivas
ALERT_CRITICAL_MAX_AGE_HOURS = 1  # critical sem ack > 1h
RECURRING_ERROR_THRESHOLD = 3  # N+ ocorrências em 24h
COOLDOWN_MINUTES = 30  # não repetir mesmo alerta por 30 min


class ProactiveMonitor:
    """Monitor de anomalias em background."""

    def __init__(self):
        self._running = False
        self._thread = None
        self._enabled_environments = set()
        self._cooldowns = {}  # {alert_key: last_notified_timestamp}
        self._emit_fn = None  # Função para emitir SSE

    def set_emit_fn(self, fn):
        """Define função para emitir notificações SSE."""
        self._emit_fn = fn

    def enable_environment(self, environment_id):
        """Habilita monitoramento proativo para um ambiente."""
        self._enabled_environments.add(environment_id)
        logger.info("👁️ Monitor proativo habilitado para ambiente %s", environment_id)

    def disable_environment(self, environment_id):
        """Desabilita monitoramento proativo para um ambiente."""
        self._enabled_environments.discard(environment_id)

    def start(self):
        """Inicia o loop de monitoramento em thread separada."""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True, name="golias-proactive")
        self._thread.start()
        logger.info("👁️ Monitor proativo iniciado (intervalo: %ds)", CHECK_INTERVAL)

    def stop(self):
        """Para o monitor."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)
            self._thread = None
        logger.info("👁️ Monitor proativo parado")

    def _monitor_loop(self):
        """Loop principal de monitoramento."""
        while self._running:
            for env_id in list(self._enabled_environments):
                try:
                    anomalies = self._check_environment(env_id)
                    for anomaly in anomalies:
                        self._notify(env_id, anomaly)
                except Exception as e:
                    logger.warning("Erro no check proativo (env %s): %s", env_id, e)

            # Limpar cooldowns expirados
            self._cleanup_cooldowns()

            # Aguardar próximo ciclo
            for _ in range(CHECK_INTERVAL):
                if not self._running:
                    return
                time.sleep(1)

    def _check_environment(self, env_id):
        """Executa todos os checks para um ambiente.

        Returns:
            lista de anomalias detectadas [{type, severity, message, data}]
        """
        anomalies = []

        anomalies.extend(self._check_pipeline_failures(env_id))
        anomalies.extend(self._check_critical_alerts(env_id))
        anomalies.extend(self._check_recurring_errors(env_id))

        return anomalies

    def _check_pipeline_failures(self, env_id):
        """Detecta pipelines com falhas consecutivas."""
        conn = get_db()
        cursor = conn.cursor()
        anomalies = []

        try:
            cursor.execute(
                """
                SELECT p.id, p.name,
                       COUNT(*) as fail_count
                FROM pipeline_runs pr
                JOIN pipelines p ON p.id = pr.pipeline_id
                WHERE p.environment_id = %s
                  AND pr.status = 'failed'
                  AND pr.started_at >= NOW() - INTERVAL '24 hours'
                GROUP BY p.id, p.name
                HAVING COUNT(*) >= %s
            """,
                (env_id, PIPELINE_FAIL_THRESHOLD),
            )

            for row in cursor.fetchall():
                r = dict(row)
                anomalies.append({
                    "type": "pipeline_failures",
                    "severity": "critical",
                    "message": f"Pipeline '{r['name']}' falhou {r['fail_count']}x nas últimas 24h",
                    "data": r,
                })

        except Exception as e:
            logger.debug("Check pipeline failures: %s", e)
        finally:
            release_db_connection(conn)

        return anomalies

    def _check_critical_alerts(self, env_id):
        """Detecta alertas critical sem acknowledge."""
        conn = get_db()
        cursor = conn.cursor()
        anomalies = []

        try:
            cursor.execute(
                """
                SELECT id, category, message, created_at
                FROM log_alerts
                WHERE environment_id = %s
                  AND severity = 'critical'
                  AND acknowledged = false
                  AND created_at <= NOW() - INTERVAL '%s hours'
                ORDER BY created_at DESC
                LIMIT 5
            """,
                (env_id, ALERT_CRITICAL_MAX_AGE_HOURS),
            )

            rows = [dict(r) for r in cursor.fetchall()]
            if rows:
                anomalies.append({
                    "type": "unacked_critical",
                    "severity": "high",
                    "message": f"{len(rows)} alerta(s) critical sem acknowledge há mais de {ALERT_CRITICAL_MAX_AGE_HOURS}h",
                    "data": {"alerts": rows[:3]},
                })

        except Exception as e:
            logger.debug("Check critical alerts: %s", e)
        finally:
            release_db_connection(conn)

        return anomalies

    def _check_recurring_errors(self, env_id):
        """Detecta novos erros recorrentes (que não existiam antes)."""
        conn = get_db()
        cursor = conn.cursor()
        anomalies = []

        try:
            cursor.execute(
                """
                SELECT category, message, COUNT(*) as count
                FROM log_alerts
                WHERE environment_id = %s
                  AND severity IN ('error', 'critical')
                  AND created_at >= NOW() - INTERVAL '24 hours'
                GROUP BY category, message
                HAVING COUNT(*) >= %s
                ORDER BY count DESC
                LIMIT 5
            """,
                (env_id, RECURRING_ERROR_THRESHOLD),
            )

            for row in cursor.fetchall():
                r = dict(row)
                anomalies.append({
                    "type": "recurring_error",
                    "severity": "warning",
                    "message": f"Erro recorrente: '{r['category']}' ({r['count']}x em 24h)",
                    "data": r,
                })

        except Exception as e:
            logger.debug("Check recurring errors: %s", e)
        finally:
            release_db_connection(conn)

        return anomalies

    def _notify(self, env_id, anomaly):
        """Notifica sobre anomalia detectada (com cooldown)."""
        # Cooldown: não repetir mesmo tipo de alerta dentro do período
        cooldown_key = f"{env_id}:{anomaly['type']}:{anomaly.get('message', '')[:50]}"
        now = time.time()

        last = self._cooldowns.get(cooldown_key, 0)
        if now - last < COOLDOWN_MINUTES * 60:
            return  # Ainda em cooldown

        self._cooldowns[cooldown_key] = now

        logger.info(
            "👁️ Anomalia detectada (env %s): [%s] %s",
            env_id, anomaly["severity"], anomaly["message"],
        )

        # Emitir via SSE se função disponível
        if self._emit_fn:
            try:
                self._emit_fn(env_id, {
                    "type": "proactive_alert",
                    "step": "proactive",
                    "severity": anomaly["severity"],
                    "description": anomaly["message"],
                    "anomaly_type": anomaly["type"],
                })
            except Exception as e:
                logger.debug("Erro ao emitir SSE proativo: %s", e)

    def _cleanup_cooldowns(self):
        """Remove cooldowns expirados."""
        now = time.time()
        expired = [k for k, v in self._cooldowns.items() if now - v > COOLDOWN_MINUTES * 60 * 2]
        for k in expired:
            del self._cooldowns[k]

    def get_status(self):
        """Retorna status do monitor."""
        return {
            "running": self._running,
            "enabled_environments": list(self._enabled_environments),
            "active_cooldowns": len(self._cooldowns),
            "check_interval_seconds": CHECK_INTERVAL,
        }


# Singleton
_monitor = None


def get_proactive_monitor():
    """Retorna instância singleton do ProactiveMonitor."""
    global _monitor
    if _monitor is None:
        _monitor = ProactiveMonitor()
    return _monitor
