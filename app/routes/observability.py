"""
AtuDIC - Rotas de Monitoramento

Endpoints para configuração e consulta do monitoramento de logs do Protheus.
"""

from flask import Blueprint, request, jsonify
from datetime import datetime
import json
import os

from app.database import get_db, release_db_connection
from app.utils.security import require_auth, require_operator, require_admin
from app.services.log_parser import scan_log, parse_log_lines

observability_bp = Blueprint("observability", __name__)

# =====================================================================
# LOG MONITOR CONFIGS (CRUD)
# =====================================================================


@observability_bp.route("/api/log-monitors", methods=["GET"])
@require_operator
def list_log_monitors():
    """Lista todas as configurações de monitoramento de log."""
    conn = get_db()
    cursor = conn.cursor()

    try:
        environment_id = request.args.get("environment_id")

        if environment_id:
            cursor.execute(
                """
                SELECT lmc.*, e.name as environment_name
                FROM log_monitor_configs lmc
                LEFT JOIN environments e ON lmc.environment_id = e.id
                WHERE lmc.environment_id = %s
                ORDER BY lmc.id
            """,
                (environment_id,),
            )
        else:
            cursor.execute("""
                SELECT lmc.*, e.name as environment_name
                FROM log_monitor_configs lmc
                LEFT JOIN environments e ON lmc.environment_id = e.id
                ORDER BY lmc.id
            """)

        configs = [dict(row) for row in cursor.fetchall()]

        for c in configs:
            for key in ("created_at", "updated_at", "last_read_at"):
                if c.get(key):
                    c[key] = c[key].isoformat()

        return jsonify(configs), 200
    finally:
        release_db_connection(conn)


@observability_bp.route("/api/log-monitors/browse-logs", methods=["GET"])
@require_operator
def browse_log_files():
    """Lista arquivos .log disponiveis no LOG_DIR do ambiente ativo.

    Busca a variavel LOG_DIR_{SUFFIX} (PRD/HOM/DEV/TST) e lista
    os arquivos com extensao .log (case-insensitive) no diretorio.
    """
    environment_id = request.args.get("environment_id", type=int)
    if not environment_id:
        return jsonify({"error": "environment_id e obrigatorio"}), 400

    conn = get_db()
    cursor = conn.cursor()
    try:
        # Resolver sufixo do ambiente
        cursor.execute("SELECT name FROM environments WHERE id = %s", (environment_id,))
        env = cursor.fetchone()
        if not env:
            return jsonify({"error": "Ambiente nao encontrado"}), 404

        env_name = env["name"].lower().strip()
        suffix_map = {
            "produção": "PRD",
            "producao": "PRD",
            "prd": "PRD",
            "homologação": "HOM",
            "homologacao": "HOM",
            "hom": "HOM",
            "desenvolvimento": "DEV",
            "dev": "DEV",
            "testes": "TST",
            "teste": "TST",
            "tst": "TST",
        }
        suffix = suffix_map.get(env_name, env_name[:3].upper())

        # Buscar LOG_DIR_{SUFFIX}
        cursor.execute("SELECT value FROM server_variables WHERE name = %s", (f"LOG_DIR_{suffix}",))
        row = cursor.fetchone()
        if not row or not row["value"]:
            return (
                jsonify(
                    {
                        "error": f"Variavel LOG_DIR_{suffix} nao configurada. Configure em Admin > Variaveis de Servidor.",
                        "log_dir_var": f"LOG_DIR_{suffix}",
                        "files": [],
                    }
                ),
                200,
            )

        log_dir = row["value"].strip()

        # Listar arquivos .log (case-insensitive)
        files = []
        if os.path.isdir(log_dir):
            for entry in sorted(os.listdir(log_dir)):
                if entry.lower().endswith(".log") and os.path.isfile(os.path.join(log_dir, entry)):
                    try:
                        size = os.path.getsize(os.path.join(log_dir, entry))
                    except OSError:
                        size = 0
                    files.append(
                        {
                            "name": entry,
                            "size": size,
                        }
                    )

        return (
            jsonify(
                {
                    "log_dir": log_dir,
                    "log_dir_var": f"LOG_DIR_{suffix}",
                    "files": files,
                }
            ),
            200,
        )

    finally:
        release_db_connection(conn)


@observability_bp.route("/api/log-monitors", methods=["POST"])
@require_operator
def create_log_monitor():
    """Cria uma nova configuração de monitoramento de log."""
    data = request.get_json()

    required = ["environment_id", "name", "log_path"]
    for field in required:
        if not data.get(field):
            return jsonify({"error": f"Campo obrigatório: {field}"}), 400

    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO log_monitor_configs
                (environment_id, name, log_type, log_path, os_type,
                 is_active, check_interval_seconds, notify_emails, created_by, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """,
            (
                data["environment_id"],
                data["name"],
                data.get("log_type", "console"),
                data["log_path"],
                data.get("os_type", "windows"),
                data.get("is_active", True),
                data.get("check_interval_seconds", 60),
                data.get("notify_emails") or None,
                request.current_user["id"],
                datetime.now(),
            ),
        )
        new_id = cursor.fetchone()["id"]
        conn.commit()

        return jsonify({"id": new_id, "message": "Monitor criado com sucesso"}), 201
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        release_db_connection(conn)


@observability_bp.route("/api/log-monitors/<int:config_id>", methods=["PUT"])
@require_operator
def update_log_monitor(config_id):
    """Atualiza uma configuração de monitoramento de log."""
    data = request.get_json()

    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT id FROM log_monitor_configs WHERE id = %s", (config_id,))
        if not cursor.fetchone():
            return jsonify({"error": "Monitor não encontrado"}), 404

        fields = []
        values = []
        updatable = ["name", "log_type", "log_path", "os_type", "is_active", "check_interval_seconds", "notify_emails"]

        for field in updatable:
            if field in data:
                fields.append(f"{field} = %s")
                values.append(data[field])

        if not fields:
            return jsonify({"error": "Nenhum campo para atualizar"}), 400

        fields.append("updated_at = %s")
        values.append(datetime.now())
        values.append(config_id)

        cursor.execute(f"UPDATE log_monitor_configs SET {', '.join(fields)} WHERE id = %s", values)
        conn.commit()

        return jsonify({"message": "Monitor atualizado com sucesso"}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        release_db_connection(conn)


@observability_bp.route("/api/log-monitors/<int:config_id>", methods=["DELETE"])
@require_admin
def delete_log_monitor(config_id):
    """Remove uma configuração de monitoramento (e seus alertas)."""
    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT id FROM log_monitor_configs WHERE id = %s", (config_id,))
        if not cursor.fetchone():
            return jsonify({"error": "Monitor não encontrado"}), 404

        cursor.execute("DELETE FROM log_monitor_configs WHERE id = %s", (config_id,))
        conn.commit()

        return jsonify({"message": "Monitor removido com sucesso"}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        release_db_connection(conn)


# =====================================================================
# SCAN MANUAL
# =====================================================================


@observability_bp.route("/api/log-monitors/<int:config_id>/scan", methods=["POST"])
@require_operator
def trigger_scan(config_id):
    """Dispara um scan manual do log configurado."""
    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT id FROM log_monitor_configs WHERE id = %s", (config_id,))
        if not cursor.fetchone():
            return jsonify({"error": "Monitor não encontrado"}), 404
    finally:
        release_db_connection(conn)

    result = scan_log(config_id)
    status_code = 200 if result.get("success") else 500

    return jsonify(result), status_code


@observability_bp.route("/api/log-monitors/<int:config_id>/reset", methods=["POST"])
@require_operator
def reset_position(config_id):
    """Reseta a posição de leitura do log (relê desde o início)."""
    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT id FROM log_monitor_configs WHERE id = %s", (config_id,))
        if not cursor.fetchone():
            return jsonify({"error": "Monitor não encontrado"}), 404

        cursor.execute(
            "UPDATE log_monitor_configs SET last_read_position = 0, last_read_at = NULL WHERE id = %s", (config_id,)
        )
        conn.commit()

        return jsonify({"message": "Posição resetada. Próximo scan lerá desde o início."}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        release_db_connection(conn)


# =====================================================================
# LOG ALERTS (CONSULTA)
# =====================================================================


@observability_bp.route("/api/log-alerts", methods=["GET"])
@require_auth
def list_alerts():
    """
    Lista alertas de log com filtros.

    Query params:
        environment_id: filtrar por ambiente
        severity: critical, warning, info
        category: database, thread_error, rpo, service, etc.
        acknowledged: true/false
        config_id: filtrar por monitor específico
        limit: max resultados (default 100)
        offset: paginação
        from_date: data inicial (ISO format)
        to_date: data final (ISO format)
    """
    conn = get_db()
    cursor = conn.cursor()

    try:
        conditions = []
        params = []

        environment_id = request.args.get("environment_id")
        if environment_id:
            conditions.append("la.environment_id = %s")
            params.append(environment_id)

        severity = request.args.get("severity")
        if severity:
            conditions.append("la.severity = %s")
            params.append(severity)

        category = request.args.get("category")
        if category:
            conditions.append("la.category = %s")
            params.append(category)

        acknowledged = request.args.get("acknowledged")
        if acknowledged is not None:
            conditions.append("la.acknowledged = %s")
            params.append(acknowledged.lower() == "true")

        config_id = request.args.get("config_id")
        if config_id:
            conditions.append("la.config_id = %s")
            params.append(config_id)

        from_date = request.args.get("from_date")
        if from_date:
            conditions.append("la.occurred_at >= %s")
            params.append(from_date)

        to_date = request.args.get("to_date")
        if to_date:
            conditions.append("la.occurred_at <= %s")
            params.append(to_date)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        limit = min(int(request.args.get("limit", 100)), 500)
        offset = int(request.args.get("offset", 0))

        # Total count
        cursor.execute(f"SELECT COUNT(*) as total FROM log_alerts la {where}", params)
        total = cursor.fetchone()["total"]

        # Resultados paginados
        cursor.execute(
            f"""
            SELECT la.*, e.name as environment_name, lmc.name as monitor_name
            FROM log_alerts la
            LEFT JOIN environments e ON la.environment_id = e.id
            LEFT JOIN log_monitor_configs lmc ON la.config_id = lmc.id
            {where}
            ORDER BY la.occurred_at DESC NULLS LAST, la.id DESC
            LIMIT %s OFFSET %s
        """,
            params + [limit, offset],
        )

        alerts = []
        for row in cursor.fetchall():
            alert = dict(row)
            for key in ("occurred_at", "created_at", "acknowledged_at"):
                if alert.get(key):
                    alert[key] = alert[key].isoformat()
            if alert.get("details") and isinstance(alert["details"], str):
                try:
                    alert["details"] = json.loads(alert["details"])
                except (json.JSONDecodeError, TypeError):
                    pass
            alerts.append(alert)

        return (
            jsonify(
                {
                    "alerts": alerts,
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                }
            ),
            200,
        )
    finally:
        release_db_connection(conn)


@observability_bp.route("/api/log-alerts/<int:alert_id>/acknowledge", methods=["POST"])
@require_operator
def acknowledge_alert(alert_id):
    """Marca um alerta como reconhecido (acknowledged)."""
    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT id, acknowledged FROM log_alerts WHERE id = %s", (alert_id,))
        alert = cursor.fetchone()
        if not alert:
            return jsonify({"error": "Alerta não encontrado"}), 404

        cursor.execute(
            """
            UPDATE log_alerts
            SET acknowledged = TRUE, acknowledged_by = %s, acknowledged_at = %s
            WHERE id = %s
        """,
            (request.current_user["id"], datetime.now(), alert_id),
        )
        conn.commit()

        return jsonify({"message": "Alerta reconhecido"}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        release_db_connection(conn)


@observability_bp.route("/api/log-alerts/acknowledge-bulk", methods=["POST"])
@require_operator
def acknowledge_alerts_bulk():
    """Marca múltiplos alertas como reconhecidos."""
    data = request.get_json()
    alert_ids = data.get("alert_ids", [])

    if not alert_ids:
        return jsonify({"error": "Informe alert_ids"}), 400

    conn = get_db()
    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            UPDATE log_alerts
            SET acknowledged = TRUE, acknowledged_by = %s, acknowledged_at = %s
            WHERE id = ANY(%s) AND acknowledged = FALSE
        """,
            (request.current_user["id"], datetime.now(), alert_ids),
        )
        count = cursor.rowcount
        conn.commit()

        return jsonify({"message": f"{count} alerta(s) reconhecido(s)"}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        release_db_connection(conn)


# =====================================================================
# DASHBOARD / RESUMO
# =====================================================================


@observability_bp.route("/api/log-alerts/summary", methods=["GET"])
@require_auth
def alerts_summary():
    """
    Retorna resumo dos alertas para dashboard.

    Query params:
        environment_id: filtrar por ambiente (opcional)
    """
    conn = get_db()
    cursor = conn.cursor()

    try:
        environment_id = request.args.get("environment_id")
        env_filter = ""
        params = []

        if environment_id:
            env_filter = "WHERE environment_id = %s"
            params = [environment_id]

        # Contagem por severidade
        cursor.execute(
            f"""
            SELECT severity, COUNT(*) as count
            FROM log_alerts {env_filter}
            GROUP BY severity
        """,
            params,
        )
        by_severity = {row["severity"]: row["count"] for row in cursor.fetchall()}

        # Contagem por categoria (apenas não reconhecidos)
        ack_filter = f"{'AND' if env_filter else 'WHERE'} acknowledged = FALSE"
        cursor.execute(
            f"""
            SELECT category, COUNT(*) as count
            FROM log_alerts {env_filter} {ack_filter}
            GROUP BY category
            ORDER BY count DESC
        """,
            params,
        )
        by_category = {row["category"]: row["count"] for row in cursor.fetchall()}

        # Não reconhecidos por severidade
        cursor.execute(
            f"""
            SELECT severity, COUNT(*) as count
            FROM log_alerts {env_filter} {ack_filter}
            GROUP BY severity
        """,
            params,
        )
        unacknowledged = {row["severity"]: row["count"] for row in cursor.fetchall()}

        # Últimos 5 alertas críticos não reconhecidos
        cursor.execute(
            f"""
            SELECT la.id, la.severity, la.category, la.message, la.occurred_at,
                   la.source_file, e.name as environment_name
            FROM log_alerts la
            LEFT JOIN environments e ON la.environment_id = e.id
            {env_filter.replace('environment_id', 'la.environment_id')}
            {'AND' if env_filter else 'WHERE'} la.acknowledged = FALSE AND la.severity = 'critical'
            ORDER BY la.occurred_at DESC NULLS LAST
            LIMIT 5
        """,
            params,
        )

        recent_critical = []
        for row in cursor.fetchall():
            alert = dict(row)
            if alert.get("occurred_at"):
                alert["occurred_at"] = alert["occurred_at"].isoformat()
            recent_critical.append(alert)

        # Status dos monitors
        cursor.execute("""
            SELECT lmc.id, lmc.name, lmc.is_active, lmc.last_read_at,
                   lmc.last_read_position, e.name as environment_name
            FROM log_monitor_configs lmc
            LEFT JOIN environments e ON lmc.environment_id = e.id
            ORDER BY lmc.id
        """)
        monitors = []
        for row in cursor.fetchall():
            m = dict(row)
            if m.get("last_read_at"):
                m["last_read_at"] = m["last_read_at"].isoformat()
            monitors.append(m)

        return (
            jsonify(
                {
                    "by_severity": by_severity,
                    "by_category": by_category,
                    "unacknowledged": unacknowledged,
                    "recent_critical": recent_critical,
                    "monitors": monitors,
                }
            ),
            200,
        )
    finally:
        release_db_connection(conn)


# =====================================================================
# TIMELINE DE ALERTAS (area chart por hora)
# =====================================================================


@observability_bp.route("/api/log-alerts/timeline", methods=["GET"])
@require_auth
def get_log_alerts_timeline():
    """
    Retorna alertas agrupados por hora para exibição em area chart.

    Query params:
        hours: janela de tempo em horas (default 24, max 72)

    Headers:
        X-Environment-Id: ID do ambiente obrigatório

    Returns:
        {"period_hours": N, "timeline": [{"hour": "ISO", "critical": N, "warning": N, "info": N}]}
    """
    env_id = request.headers.get("X-Environment-Id")
    if not env_id:
        return jsonify({"error": "Ambiente nao especificado"}), 400

    hours = request.args.get("hours", 24, type=int)
    hours = min(hours, 72)

    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT DATE_TRUNC('hour', occurred_at) AS hour,
                   COUNT(*) FILTER (WHERE severity = 'critical') AS critical,
                   COUNT(*) FILTER (WHERE severity = 'warning') AS warning,
                   COUNT(*) FILTER (WHERE severity = 'info') AS info
            FROM log_alerts
            WHERE environment_id = %s
              AND occurred_at >= NOW() - make_interval(hours => %s)
            GROUP BY DATE_TRUNC('hour', occurred_at)
            ORDER BY hour ASC
        """,
            (env_id, hours),
        )

        timeline = []
        for row in cursor.fetchall():
            entry = dict(row)
            if entry.get("hour"):
                entry["hour"] = entry["hour"].isoformat()
            timeline.append(entry)

        return (
            jsonify(
                {
                    "period_hours": hours,
                    "timeline": timeline,
                }
            ),
            200,
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            release_db_connection(conn)


# =====================================================================
# PARSE AVULSO (para testar padrões sem salvar)
# =====================================================================


@observability_bp.route("/api/log-alerts/parse-test", methods=["POST"])
@require_operator
def parse_test():
    """
    Recebe um bloco de texto de log e retorna os alertas parseados (sem salvar).
    Útil para testar e validar padrões.
    """
    data = request.get_json()
    log_text = data.get("log_text", "")

    if not log_text:
        return jsonify({"error": "Informe log_text"}), 400

    lines = log_text.splitlines()
    alerts, metrics = parse_log_lines(lines, source_file="test-input")

    # Serializa timestamps
    for a in alerts:
        if a.get("occurred_at"):
            a["occurred_at"] = a["occurred_at"].isoformat()
    for m in metrics:
        if m.get("occurred_at"):
            m["occurred_at"] = m["occurred_at"].isoformat()

    return (
        jsonify(
            {
                "alerts": alerts,
                "metrics": metrics,
                "total_lines": len(lines),
                "alerts_count": len(alerts),
                "metrics_count": len(metrics),
            }
        ),
        200,
    )
