from flask import Blueprint, request, jsonify, send_from_directory, current_app
from datetime import datetime, timedelta
import os
import platform

from app.database import get_db, release_db_connection
from app.utils.helpers import get_base_dir_for_repo, CLONE_DIR
from app.utils.security import require_auth, verify_password, hash_password, get_user_permissions
from app.utils.serializers import convert_datetime_to_str

main_bp = Blueprint("main", __name__)

# =====================================================================
# INFORMAÇÕES DO SISTEMA
# =====================================================================


@main_bp.route("/api/system/info", methods=["GET"])
def system_info():
    """Retorna informações do SO do servidor para filtro automático no frontend"""
    os_name = platform.system()  # 'Windows' ou 'Linux'
    os_display = _get_os_display_name()
    return jsonify(
        {
            "os": os_name.lower(),
            "command_type": "powershell" if os_name == "Windows" else "bash",
            "os_display": os_display,
        }
    )


def _get_os_display_name():
    """Retorna nome amigável do SO (ex: 'Windows 11 Pro', 'Ubuntu 22.04 LTS')"""
    os_name = platform.system()

    if os_name == "Windows":
        try:
            ver = platform.win32_ver()  # ('10', '10.0.22631', 'SP0', 'Multiprocessor Free')
            release = platform.release()  # '10' ou '11'
            # Tenta obter edição via registro do Windows
            try:
                import winreg

                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion")
                product_name = winreg.QueryValueEx(key, "ProductName")[0]
                winreg.CloseKey(key)
                return product_name  # Ex: "Windows 11 Pro", "Windows Server 2019 Standard"
            except Exception:
                pass
            # Fallback: monta o nome com platform info
            build = ver[1] if ver[1] else ""
            return f"Windows {release} (Build {build})" if build else f"Windows {release}"
        except Exception:
            return "Windows"

    elif os_name == "Linux":
        try:
            # Lê /etc/os-release para obter nome da distribuição
            with open("/etc/os-release", "r") as f:
                os_release = {}
                for line in f:
                    line = line.strip()
                    if "=" in line:
                        key, value = line.split("=", 1)
                        os_release[key] = value.strip('"')
            pretty_name = os_release.get("PRETTY_NAME", "")
            if pretty_name:
                return pretty_name  # Ex: "Ubuntu 22.04.3 LTS", "Debian GNU/Linux 12"
            name = os_release.get("NAME", "Linux")
            version = os_release.get("VERSION", "")
            return f"{name} {version}".strip()
        except Exception:
            return "Linux"

    return platform.platform()


# =====================================================================
# ROTA DE SAÚDE
# =====================================================================


@main_bp.route("/api/health", methods=["GET"])
def health_check():
    """
    Liveness probe — verifica se a app está respondendo.
    Leve e rápido, sem queries pesadas.
    """
    return jsonify({"status": "healthy"}), 200


@main_bp.route("/api/health/ready", methods=["GET"])
def readiness_check():
    """
    Readiness probe — verifica se a app está pronta para receber tráfego.
    Testa conexão com o banco e retorna estatísticas básicas.
    """
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()

        # Query leve com timeout implícito do pool (statement_timeout)
        cursor.execute("SELECT 1 AS ok")
        cursor.fetchone()

        # Estatísticas básicas
        cursor.execute("SELECT COUNT(*) as count FROM users WHERE username != 'admin'")
        users_count = cursor.fetchone()["count"]

        cursor.execute("SELECT COUNT(*) as count FROM pipelines")
        pipelines_count = cursor.fetchone()["count"]

        release_db_connection(conn)
        conn = None

        return jsonify(
            {
                "status": "ready",
                "database": "connected",
                "stats": {
                    "users": users_count,
                    "pipelines": pipelines_count,
                },
            }
        )
    except Exception as e:
        if conn:
            release_db_connection(conn)
        return jsonify({"status": "not_ready", "error": str(e)}), 503


# =====================================================================
# DASHBOARD API ENDPOINT
# =====================================================================


@main_bp.route("/api/dashboard/stats", methods=["GET"])
@require_auth
def get_dashboard_stats():
    """Retorna estatísticas para o Dashboard, filtradas por SO quando command_type é informado."""
    env_id = request.headers.get("X-Environment-Id")
    if not env_id:
        return jsonify({"error": "Ambiente não especificado"}), 400

    # Filtro por SO: bash→linux, powershell→windows
    command_type = request.args.get("command_type")  # 'bash' ou 'powershell'
    os_type = None
    if command_type:
        os_type = "linux" if command_type == "bash" else "windows"

    # Sub-select reutilizável: pipelines cujos TODOS comandos são do command_type
    # (pipeline aparece se não existe nenhum comando incompatível)
    pipeline_os_filter = ""
    if command_type:
        pipeline_os_filter = """
            AND pr.pipeline_id IN (
                SELECT p2.id FROM pipelines p2
                WHERE p2.environment_id = %s
                AND NOT EXISTS (
                    SELECT 1 FROM pipeline_commands pc
                    JOIN commands c ON pc.command_id = c.id
                    WHERE pc.pipeline_id = p2.id AND c.type != %s
                )
            )
        """

    conn = get_db()
    cursor = conn.cursor()

    try:
        # Métricas de Pipelines
        if command_type:
            cursor.execute(
                f"""
                SELECT
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE pr.status = 'success') as success,
                    COUNT(*) FILTER (WHERE pr.status = 'failed') as failed,
                    COUNT(*) FILTER (WHERE pr.status = 'running') as running
                FROM pipeline_runs pr
                WHERE pr.environment_id = %s
                {pipeline_os_filter}
            """,
                (env_id, env_id, command_type),
            )
        else:
            cursor.execute(
                """
                SELECT
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE pr.status = 'success') as success,
                    COUNT(*) FILTER (WHERE pr.status = 'failed') as failed,
                    COUNT(*) FILTER (WHERE pr.status = 'running') as running
                FROM pipeline_runs pr
                WHERE pr.environment_id = %s
            """,
                (env_id,),
            )
        pipeline_stats = dict(cursor.fetchone())

        # Últimas 5 execuções
        if command_type:
            cursor.execute(
                f"""
                SELECT
                    pr.id, pr.run_number, pr.status, pr.started_at, pr.finished_at,
                    pr.trigger_type, p.name as pipeline_name
                FROM pipeline_runs pr
                JOIN pipelines p ON pr.pipeline_id = p.id
                WHERE pr.environment_id = %s
                {pipeline_os_filter}
                ORDER BY pr.started_at DESC
                LIMIT 5
            """,
                (env_id, env_id, command_type),
            )
        else:
            cursor.execute(
                """
                SELECT
                    pr.id, pr.run_number, pr.status, pr.started_at, pr.finished_at,
                    pr.trigger_type, p.name as pipeline_name
                FROM pipeline_runs pr
                JOIN pipelines p ON pr.pipeline_id = p.id
                WHERE pr.environment_id = %s
                ORDER BY pr.started_at DESC
                LIMIT 5
            """,
                (env_id,),
            )
        recent_runs = [dict(row) for row in cursor.fetchall()]

        # Métricas de Releases (Deploys)
        if command_type:
            cursor.execute(
                """
                SELECT
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE r.status = 'success') as success,
                    COUNT(*) FILTER (WHERE r.status = 'failed') as failed
                FROM releases r
                JOIN pipelines p ON r.pipeline_id = p.id
                WHERE p.environment_id = %s
                AND p.id IN (
                    SELECT p2.id FROM pipelines p2
                    WHERE p2.environment_id = %s
                    AND NOT EXISTS (
                        SELECT 1 FROM pipeline_commands pc
                        JOIN commands c ON pc.command_id = c.id
                        WHERE pc.pipeline_id = p2.id AND c.type != %s
                    )
                )
            """,
                (env_id, env_id, command_type),
            )
        else:
            cursor.execute(
                """
                SELECT
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE r.status = 'success') as success,
                    COUNT(*) FILTER (WHERE r.status = 'failed') as failed
                FROM releases r
                JOIN pipelines p ON r.pipeline_id = p.id
                WHERE p.environment_id = %s
            """,
                (env_id,),
            )
        release_stats = dict(cursor.fetchone())

        # Schedules Ativos
        if command_type:
            cursor.execute(
                """
                SELECT
                    s.id, s.name, s.next_run_at, s.is_active,
                    p.name as pipeline_name, s.schedule_type
                FROM pipeline_schedules s
                JOIN pipelines p ON s.pipeline_id = p.id
                WHERE s.environment_id = %s AND s.is_active = true
                AND p.id IN (
                    SELECT p2.id FROM pipelines p2
                    WHERE p2.environment_id = %s
                    AND NOT EXISTS (
                        SELECT 1 FROM pipeline_commands pc
                        JOIN commands c ON pc.command_id = c.id
                        WHERE pc.pipeline_id = p2.id AND c.type != %s
                    )
                )
                ORDER BY s.next_run_at ASC
                LIMIT 5
            """,
                (env_id, env_id, command_type),
            )
        else:
            cursor.execute(
                """
                SELECT
                    s.id, s.name, s.next_run_at, s.is_active,
                    p.name as pipeline_name, s.schedule_type
                FROM pipeline_schedules s
                JOIN pipelines p ON s.pipeline_id = p.id
                WHERE s.environment_id = %s AND s.is_active = true
                ORDER BY s.next_run_at ASC
                LIMIT 5
            """,
                (env_id,),
            )
        active_schedules = [dict(row) for row in cursor.fetchall()]

        # Status de Serviços (Service Actions)
        if os_type:
            cursor.execute(
                """
                SELECT
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE is_active = true) as active
                FROM service_actions
                WHERE environment_id = %s AND os_type = %s
            """,
                (env_id, os_type),
            )
        else:
            cursor.execute(
                """
                SELECT
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE is_active = true) as active
                FROM service_actions
                WHERE environment_id = %s
            """,
                (env_id,),
            )
        service_stats = dict(cursor.fetchone())

        # Últimas execuções de Service Actions
        if os_type:
            cursor.execute(
                """
                SELECT
                    id, name, action_type, os_type, last_run_at, is_active
                FROM service_actions
                WHERE environment_id = %s AND os_type = %s AND last_run_at IS NOT NULL
                ORDER BY last_run_at DESC
                LIMIT 5
            """,
                (env_id, os_type),
            )
        else:
            cursor.execute(
                """
                SELECT
                    id, name, action_type, os_type, last_run_at, is_active
                FROM service_actions
                WHERE environment_id = %s AND last_run_at IS NOT NULL
                ORDER BY last_run_at DESC
                LIMIT 5
            """,
                (env_id,),
            )
        recent_service_actions = [dict(row) for row in cursor.fetchall()]

        # Próximos agendamentos de Service Actions
        if os_type:
            cursor.execute(
                """
                SELECT
                    id, name, action_type, os_type, schedule_type, next_run_at, is_active
                FROM service_actions
                WHERE environment_id = %s AND os_type = %s AND is_active = true AND next_run_at IS NOT NULL
                ORDER BY next_run_at ASC
                LIMIT 5
            """,
                (env_id, os_type),
            )
        else:
            cursor.execute(
                """
                SELECT
                    id, name, action_type, os_type, schedule_type, next_run_at, is_active
                FROM service_actions
                WHERE environment_id = %s AND is_active = true AND next_run_at IS NOT NULL
                ORDER BY next_run_at ASC
                LIMIT 5
            """,
                (env_id,),
            )
        scheduled_service_actions = [dict(row) for row in cursor.fetchall()]

        # Contadores gerais
        if command_type:
            cursor.execute(
                """
                SELECT COUNT(*) as count FROM pipelines p
                WHERE p.environment_id = %s
                AND NOT EXISTS (
                    SELECT 1 FROM pipeline_commands pc
                    JOIN commands c ON pc.command_id = c.id
                    WHERE pc.pipeline_id = p.id AND c.type != %s
                )
            """,
                (env_id, command_type),
            )
        else:
            cursor.execute("SELECT COUNT(*) as count FROM pipelines WHERE environment_id = %s", (env_id,))
        total_pipelines = cursor.fetchone()["count"]

        if command_type:
            cursor.execute(
                "SELECT COUNT(*) as count FROM commands WHERE environment_id = %s AND type = %s", (env_id, command_type)
            )
        else:
            cursor.execute("SELECT COUNT(*) as count FROM commands WHERE environment_id = %s", (env_id,))
        total_commands = cursor.fetchone()["count"]

        cursor.execute("SELECT COUNT(*) as count FROM repositories WHERE environment_id = %s", (env_id,))
        total_repos = cursor.fetchone()["count"]

        # Repositórios com branches clonadas (para card do dashboard)
        cursor.execute(
            "SELECT id, name, default_branch FROM repositories WHERE environment_id = %s ORDER BY name", (env_id,)
        )
        repos_rows = cursor.fetchall()
        repos_with_branches = []
        for repo_row in repos_rows:
            repo_info = {
                "id": repo_row["id"],
                "name": repo_row["name"],
                "default_branch": repo_row["default_branch"],
                "branches": [],
            }
            BASE_DIR = get_base_dir_for_repo(cursor, repo_row["id"])
            for base in [BASE_DIR, CLONE_DIR]:
                repo_dir = os.path.join(base, repo_row["name"])
                if not os.path.isdir(repo_dir):
                    continue
                try:
                    subdirs = [
                        d
                        for d in sorted(os.listdir(repo_dir))
                        if os.path.isdir(os.path.join(repo_dir, d)) and not d.startswith(".")
                    ]
                except OSError:
                    continue
                if subdirs:
                    repo_info["branches"] = subdirs
                    break
            repos_with_branches.append(repo_info)

        return jsonify(
            {
                "pipeline_runs": convert_datetime_to_str(pipeline_stats),
                "recent_runs": convert_datetime_to_str(recent_runs),
                "releases": release_stats,
                "active_schedules": convert_datetime_to_str(active_schedules),
                "service_actions": service_stats,
                "recent_service_actions": convert_datetime_to_str(recent_service_actions),
                "scheduled_service_actions": convert_datetime_to_str(scheduled_service_actions),
                "totals": {"pipelines": total_pipelines, "commands": total_commands, "repositories": total_repos},
                "repositories": repos_with_branches,
            }
        )

    except Exception as e:
        current_app.logger.error(f"Erro ao buscar stats do dashboard: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            release_db_connection(conn)


# =====================================================================
# MÉTRICAS AVANÇADAS DO DASHBOARD
# =====================================================================


@main_bp.route("/api/dashboard/metrics", methods=["GET"])
@require_auth
def get_dashboard_metrics():
    """Retorna métricas avançadas: tendência diária, taxa de sucesso, duração média."""
    env_id = request.headers.get("X-Environment-Id")
    if not env_id:
        return jsonify({"error": "Ambiente não especificado"}), 400

    days = request.args.get("days", 30, type=int)
    days = min(days, 90)
    since = datetime.now() - timedelta(days=days)

    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()

        # Tendência diária de runs (success/failed por dia, timezone BRT)
        cursor.execute(
            """
            SELECT DATE(pr.started_at AT TIME ZONE 'America/Sao_Paulo') as day,
                   COUNT(*) as total,
                   COUNT(*) FILTER (WHERE pr.status = 'success') as success,
                   COUNT(*) FILTER (WHERE pr.status = 'failed') as failed
            FROM pipeline_runs pr
            JOIN pipelines p ON pr.pipeline_id = p.id
            WHERE p.environment_id = %s AND pr.started_at >= %s
              AND pr.status IN ('success', 'failed')
            GROUP BY DATE(pr.started_at AT TIME ZONE 'America/Sao_Paulo')
            ORDER BY day
        """,
            (env_id, since),
        )
        daily_runs = [dict(r) for r in cursor.fetchall()]

        # Tendência diária de releases (timezone BRT)
        cursor.execute(
            """
            SELECT DATE(r.started_at AT TIME ZONE 'America/Sao_Paulo') as day,
                   COUNT(*) as total,
                   COUNT(*) FILTER (WHERE r.status = 'success') as success,
                   COUNT(*) FILTER (WHERE r.status = 'failed') as failed
            FROM releases r
            JOIN pipelines p ON r.pipeline_id = p.id
            WHERE p.environment_id = %s AND r.started_at >= %s
              AND r.status IN ('success', 'failed')
            GROUP BY DATE(r.started_at AT TIME ZONE 'America/Sao_Paulo')
            ORDER BY day
        """,
            (env_id, since),
        )
        daily_releases = [dict(r) for r in cursor.fetchall()]

        # Duração média de runs (em segundos) por pipeline
        cursor.execute(
            """
            SELECT p.name as pipeline_name,
                   COUNT(*) as total_runs,
                   ROUND(AVG(EXTRACT(EPOCH FROM (pr.finished_at - pr.started_at))))::int as avg_duration_sec,
                   ROUND(AVG(CASE WHEN pr.status = 'success' THEN 1.0 ELSE 0.0 END) * 100, 1) as success_rate
            FROM pipeline_runs pr
            JOIN pipelines p ON pr.pipeline_id = p.id
            WHERE p.environment_id = %s AND pr.started_at >= %s
              AND pr.status IN ('success', 'failed')
              AND pr.finished_at IS NOT NULL
            GROUP BY p.name
            ORDER BY total_runs DESC
            LIMIT 20
        """,
            (env_id, since),
        )
        pipeline_stats = [dict(r) for r in cursor.fetchall()]

        # Top 5 pipelines que mais falharam
        cursor.execute(
            """
            SELECT p.name as pipeline_name,
                   COUNT(*) as fail_count
            FROM pipeline_runs pr
            JOIN pipelines p ON pr.pipeline_id = p.id
            WHERE p.environment_id = %s AND pr.started_at >= %s
              AND pr.status = 'failed'
            GROUP BY p.name
            ORDER BY fail_count DESC
            LIMIT 5
        """,
            (env_id, since),
        )
        top_failures = [dict(r) for r in cursor.fetchall()]

        # Serializar datas
        for row in daily_runs + daily_releases:
            if row.get("day"):
                row["day"] = row["day"].isoformat()

        return jsonify(
            {
                "period_days": days,
                "daily_runs": daily_runs,
                "daily_releases": daily_releases,
                "pipeline_stats": pipeline_stats,
                "top_failures": top_failures,
            }
        )

    except Exception as e:
        current_app.logger.error(f"Erro ao buscar métricas: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            release_db_connection(conn)


# =====================================================================
# ROTA DE VERIFICAÇÃO DE SESSÃO / USUÁRIO
# =====================================================================


@main_bp.route("/api/me", methods=["GET"])
@require_auth
def get_current_user():
    """Retorna os dados do usuário autenticado pelo token"""
    user = request.current_user

    # Buscar ambientes vinculados ao usuário
    environment_ids = []
    if user["username"] != "admin":
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT environment_id FROM user_environments WHERE user_id = %s", (user["id"],))
        environment_ids = [row["environment_id"] for row in cursor.fetchall()]
        release_db_connection(conn)

    return jsonify(
        {
            "id": user["id"],
            "username": user["username"],
            "name": user["name"],
            "email": user["email"],
            "profile": user["profile"],
            "lastLogin": user["last_login"],
            "environment_ids": environment_ids,
        }
    )


@main_bp.route("/api/me/password", methods=["POST"])
@require_auth
def change_own_password():
    """Permite ao usuário autenticado alterar sua própria senha."""
    data = request.json
    current_password = data.get("current_password")
    new_password = data.get("new_password")

    user = request.current_user

    if not verify_password(user["password"], user["password_salt"], current_password):
        return jsonify({"error": "Senha atual incorreta"}), 403

    new_hashed_password, new_salt = hash_password(new_password)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET password = %s, password_salt = %s WHERE id = %s",
        (new_hashed_password, new_salt, user["id"]),
    )
    conn.commit()
    release_db_connection(conn)

    return jsonify({"success": True, "message": "Senha alterada com sucesso!"})


@main_bp.route("/api/me/permissions", methods=["GET"])
@require_auth
def get_current_user_permissions():
    """Retorna as permissões do usuário autenticado"""
    user = request.current_user
    permissions = get_user_permissions(user["profile"], user["username"])
    return jsonify(
        {
            "profile": user["profile"],
            "username": user["username"],
            "is_root": user["username"] == "admin",
            "permissions": permissions,
        }
    )


# =====================================================================
# FEED UNIFICADO DE ATIVIDADES DO DASHBOARD
# =====================================================================


@main_bp.route("/api/dashboard/feed", methods=["GET"])
@require_auth
def get_dashboard_feed():
    """
    Retorna feed unificado de atividades recentes de múltiplas fontes.

    Combina via UNION ALL: pipeline_runs, log_alerts (não reconhecidos) e
    service_actions com last_run_at. Cada item inclui type, icon, title,
    status, timestamp, drilldown (âncora de navegação) e color (classe CSS).

    Query params:
        limit: número de itens (default 10, max 20)

    Headers:
        X-Environment-Id: ID do ambiente obrigatório

    Returns:
        {"items": [...]}
    """
    env_id = request.headers.get("X-Environment-Id")
    if not env_id:
        return jsonify({"error": "Ambiente nao especificado"}), 400

    limit = request.args.get("limit", 10, type=int)
    limit = min(limit, 20)

    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT * FROM (
                -- Pipeline runs
                SELECT
                    'pipeline_run'          AS type,
                    'fa-play-circle'        AS icon,
                    p.name                  AS title,
                    pr.status               AS status,
                    pr.started_at           AS timestamp,
                    '#pipelines'            AS drilldown
                FROM pipeline_runs pr
                JOIN pipelines p ON pr.pipeline_id = p.id
                WHERE p.environment_id = %s
                  AND pr.started_at IS NOT NULL

                UNION ALL

                -- Alertas nao reconhecidos
                SELECT
                    'alert'                                         AS type,
                    'fa-exclamation-triangle'                       AS icon,
                    LEFT(la.message, 80)                            AS title,
                    la.severity                                     AS status,
                    la.occurred_at                                  AS timestamp,
                    '#observability'                                AS drilldown
                FROM log_alerts la
                WHERE la.environment_id = %s
                  AND la.acknowledged = FALSE
                  AND la.occurred_at IS NOT NULL

                UNION ALL

                -- Service actions com execucao registrada
                SELECT
                    'service_action'    AS type,
                    'fa-server'         AS icon,
                    sa.name             AS title,
                    sa.action_type      AS status,
                    sa.last_run_at      AS timestamp,
                    '#schedules'        AS drilldown
                FROM service_actions sa
                WHERE sa.environment_id = %s
                  AND sa.last_run_at IS NOT NULL
            ) AS feed
            ORDER BY timestamp DESC
            LIMIT %s
        """,
            (env_id, env_id, env_id, limit),
        )

        color_map = {
            "success": "success",
            "failed": "danger",
            "critical": "danger",
            "warning": "warning",
            "info": "info",
        }

        items = []
        for row in cursor.fetchall():
            item = dict(row)
            if item.get("timestamp"):
                item["timestamp"] = item["timestamp"].isoformat()
            item["color"] = color_map.get(item.get("status", ""), "secondary")
            items.append(item)

        return jsonify({"items": items}), 200

    except Exception as e:
        current_app.logger.error(f"Erro ao buscar feed do dashboard: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            release_db_connection(conn)


# =====================================================================
# RESUMO AGREGADO DE MÓDULOS DO DASHBOARD
# =====================================================================


@main_bp.route("/api/dashboard/modules-summary", methods=["GET"])
@require_auth
def get_dashboard_modules_summary():
    """
    Retorna contagens agregadas de todos os módulos para o dashboard.

    Cada módulo é consultado independentemente com try/except — tabelas
    opcionais retornam 0 se não existirem no banco ainda.

    Headers:
        X-Environment-Id: ID do ambiente obrigatório

    Returns:
        {
            "database": {"total": N},
            "processes": {"total": N},
            "knowledge": {"total": N},
            "documentation": {"total": N},
            "schedules": {"total": N, "active": N}
        }
    """
    env_id = request.headers.get("X-Environment-Id")
    if not env_id:
        return jsonify({"error": "Ambiente nao especificado"}), 400

    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()

        summary = {
            "database": {"total": 0},
            "processes": {"total": 0},
            "knowledge": {"total": 0},
            "documentation": {"total": 0},
            "schedules": {"total": 0, "active": 0},
        }

        # database_connections — filtrado por ambiente
        try:
            cursor.execute(
                "SELECT COUNT(*) AS total FROM database_connections WHERE environment_id = %s",
                (env_id,),
            )
            summary["database"]["total"] = cursor.fetchone()["total"]
        except Exception:
            conn.rollback()

        # business_processes — global (sem environment_id)
        try:
            cursor.execute("SELECT COUNT(*) AS total FROM business_processes")
            summary["processes"]["total"] = cursor.fetchone()["total"]
        except Exception:
            conn.rollback()

        # knowledge_articles — global (sem environment_id)
        try:
            cursor.execute("SELECT COUNT(*) AS total FROM knowledge_articles")
            summary["knowledge"]["total"] = cursor.fetchone()["total"]
        except Exception:
            conn.rollback()

        # generated_docs — global (sem environment_id)
        try:
            cursor.execute("SELECT COUNT(*) AS total FROM generated_docs")
            summary["documentation"]["total"] = cursor.fetchone()["total"]
        except Exception:
            conn.rollback()

        # pipeline_schedules — tabela principal com active count
        try:
            cursor.execute(
                """
                SELECT
                    COUNT(*)                             AS total,
                    COUNT(*) FILTER (WHERE is_active)   AS active
                FROM pipeline_schedules
                WHERE environment_id = %s
            """,
                (env_id,),
            )
            row = cursor.fetchone()
            summary["schedules"]["total"] = row["total"]
            summary["schedules"]["active"] = row["active"]
        except Exception:
            conn.rollback()

        return jsonify(summary), 200

    except Exception as e:
        current_app.logger.error(f"Erro ao buscar resumo de modulos: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            release_db_connection(conn)


# =====================================================================
# ROTAS PARA SERVIR O FRONTEND (INDEX.HTML E ARQUIVOS ESTÁTICOS)
# =====================================================================


@main_bp.route("/")
def serve_index():
    """Serve o arquivo principal index.html"""
    # Utiliza root_path pois o index.html está na raiz, não na pasta static
    return send_from_directory(current_app.root_path, "index.html")


@main_bp.route("/<path:filename>")
def serve_static(filename):
    """Serve outros arquivos estáticos (js, css, etc.)"""
    return send_from_directory(current_app.root_path, filename)
