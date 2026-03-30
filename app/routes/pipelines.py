from flask import Blueprint, request, jsonify, current_app
from datetime import datetime, timedelta
import json
import threading
import time
from psycopg2 import IntegrityError

from app.database import get_db, release_db_connection
from app.utils.security import (
    require_auth,
    require_operator,
    check_protected_item
)
from app.services.runner import execute_pipeline_thread, execute_pipeline_run, execute_release, get_live_stream, cleanup_live_stream, acquire_env_lock, release_env_lock, get_env_running_info
from app.services.scheduler import calculate_next_run
from app.services.events import event_manager

pipelines_bp = Blueprint('pipelines', __name__)

# =====================================================================
# ROTAS DE PIPELINES
# =====================================================================

@pipelines_bp.route("/api/pipelines", methods=["GET"])
@require_auth
def get_pipelines():
    # Pega o ID do ambiente do cabeçalho da requisição
    env_id = request.headers.get("X-Environment-Id")
    if not env_id:
        return jsonify({"error": "Cabeçalho X-Environment-Id é obrigatório"}), 400
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM pipelines WHERE environment_id = %s ORDER BY created_at DESC",
            (env_id,)
        )
        pipelines_data = cursor.fetchall()
        pipelines = []
        for p in pipelines_data:
            pipeline_dict = dict(p)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT c.* FROM commands c JOIN pipeline_commands pc ON c.id = pc.command_id WHERE pc.pipeline_id = %s ORDER BY pc.sequence_order",
                (p["id"],),
            )
            commands = cursor.fetchall()
            pipeline_dict["commands"] = [dict(c) for c in commands]
            pipelines.append(pipeline_dict)
        return jsonify(pipelines)
    finally:
        release_db_connection(conn)


@pipelines_bp.route("/api/pipelines", methods=["POST"])
@require_operator
def create_pipeline():
    env_id = request.headers.get("X-Environment-Id")
    if not env_id:
        return jsonify({"error": "Cabeçalho X-Environment-Id é obrigatório"}), 400
    data = request.json
    required_fields = ["name"]
    if not all(field in data for field in required_fields):
        return jsonify({"error": "O nome da pipeline é obrigatório"}), 400
    if not data.get("commands") or len(data["commands"]) == 0:
        return jsonify({"error": "Selecione pelo menos um comando"}), 400

    conn = get_db()
    cursor = conn.cursor()
    
    # Validar deploy_command_id se fornecido
    deploy_command_id = data.get("deploy_command_id")
    if deploy_command_id:
        deploy_cmd = cursor.execute(
            "SELECT id FROM commands WHERE id = %s AND command_category = 'deploy'",
            (deploy_command_id,)
        )
        deploy_cmd = cursor.fetchone()
        if not deploy_cmd:
            release_db_connection(conn)
            return jsonify({"error": "Comando de deploy inválido"}), 400
    
    cursor.execute(
        """INSERT INTO pipelines (environment_id, name, description, deploy_command_id, status, last_run, created_at) 
           VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
        (
            env_id,
            data["name"],
            data.get("description", ""),
            deploy_command_id,
            "queued",
            "Nunca executada",
            datetime.now(),
        ),
    )
    pipeline_id = cursor.fetchone()['id']
    for index, command in enumerate(data["commands"]):
        cursor.execute(
            "INSERT INTO pipeline_commands (pipeline_id, command_id, sequence_order) VALUES (%s, %s, %s)",
            (pipeline_id, command["id"], index),
        )
    conn.commit()
    release_db_connection(conn)
    return (
        jsonify(
            {
                "success": True,
                "id": pipeline_id,
                "message": "Pipeline criada com sucesso",
            }
        ),
        201,
    )


@pipelines_bp.route("/api/pipelines/<int:pipeline_id>", methods=["PUT"])
@require_operator
def update_pipeline(pipeline_id):
    data = request.json
    env_id = request.headers.get('X-Environment-Id')
    
    if not env_id:
        return jsonify({"error": "Ambiente não especificado"}), 400
    
    # Verificar se item é protegido
    if check_protected_item('pipelines', pipeline_id):
        return jsonify({"error": "Esta pipeline é protegida e não pode ser alterada"}), 403
    
    conn = get_db()
    cursor = conn.cursor()

    try:
        # Verificar se já existe outra pipeline com esse nome no mesmo ambiente
        cursor.execute(
            "SELECT id FROM pipelines WHERE name = %s AND environment_id = %s AND id != %s",
            (data["name"], int(env_id), pipeline_id)
        )
        existing = cursor.fetchone()
        
        if existing:
            release_db_connection(conn)
            return jsonify({"error": "Uma pipeline com este nome já existe neste ambiente"}), 409
        
        deploy_command_id = data.get("deploy_command_id")
        if deploy_command_id == '':
            deploy_command_id = None

        cursor.execute(
            "UPDATE pipelines SET name = %s, description = %s, deploy_command_id = %s WHERE id = %s AND environment_id = %s",
            (data["name"], data.get("description", ""), deploy_command_id, pipeline_id, int(env_id))
        )

        if "commands" in data:
            cursor.execute("DELETE FROM pipeline_commands WHERE pipeline_id = %s", (pipeline_id,))
            for index, command in enumerate(data["commands"]):
                cursor.execute(
                    "INSERT INTO pipeline_commands (pipeline_id, command_id, sequence_order) VALUES (%s, %s, %s)",
                    (pipeline_id, command["id"], index)
                )

        conn.commit()
        return jsonify({"success": True, "message": "Pipeline atualizada com sucesso"})

    except IntegrityError:
        return jsonify({"error": "Erro de integridade ao atualizar pipeline"}), 409
    except Exception as e:
        current_app.logger.error(f"Erro em update_pipeline: {e}")
        return jsonify({"error": "Erro interno ao atualizar a pipeline"}), 500
    finally:
        release_db_connection(conn)


@pipelines_bp.route("/api/pipelines/<int:pipeline_id>", methods=["DELETE"])
@require_operator
def delete_pipeline(pipeline_id):
    """Exclui pipeline"""
    if check_protected_item('pipelines', pipeline_id):
        return jsonify({"error": "Esta pipeline é protegida e não pode ser excluída"}), 403
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM pipelines WHERE id = %s", (pipeline_id,))
    conn.commit()
    release_db_connection(conn)

    return jsonify({"success": True, "message": "Pipeline excluída com sucesso"})


@pipelines_bp.route("/api/pipelines/<int:pipeline_id>/run", methods=["POST"])
@require_operator
def run_pipeline(pipeline_id):
    """
    Executa um pipeline (Build/CI) e retorna o run_id.
    Similar ao 'Run Pipeline' do Azure DevOps.
    """
    try:
        start_time = datetime.now()
        user_name = request.current_user["username"]
        environment_id = request.headers.get("X-Environment-Id")
        trigger_type = 'manual'

        conn = get_db()
        cursor = conn.cursor()
        
        # Verificar se pipeline existe
        cursor.execute("SELECT * FROM pipelines WHERE id = %s", (pipeline_id,))
        pipeline = cursor.fetchone()
        
        if not pipeline:
            release_db_connection(conn)
            return jsonify({"error": "Pipeline não encontrado"}), 404
        
        pipeline = dict(pipeline)
        
        # Se environment_id não veio no header, usar o do pipeline
        if not environment_id:
            environment_id = pipeline.get('environment_id')
        
        # Buscar comandos do pipeline
        cursor.execute("""
            SELECT c.* FROM commands c
            JOIN pipeline_commands pc ON c.id = pc.command_id
            WHERE pc.pipeline_id = %s
            ORDER BY pc.sequence_order
        """, (pipeline_id,))
        commands_raw = cursor.fetchall()
        commands = [dict(row) for row in commands_raw]
        
        if not commands:
            release_db_connection(conn)
            return jsonify({"error": "Pipeline sem comandos configurados"}), 400

        # Verificar lock de ambiente — acesso exclusivo ao RPO
        if environment_id:
            running = get_env_running_info(environment_id)
            if running:
                release_db_connection(conn)
                return jsonify({
                    "error": "Ambiente ocupado",
                    "message": (
                        f"Já existe uma execução em andamento neste ambiente: "
                        f"{running['type']} do pipeline '{running['pipeline']}' "
                        f"(iniciado em {running['started_at'].strftime('%H:%M:%S')}). "
                        f"Aguarde a conclusão antes de iniciar uma nova execução."
                    )
                }), 409

        # Obter próximo run_number
        cursor.execute(
            "SELECT MAX(run_number) as last FROM pipeline_runs WHERE pipeline_id = %s",
            (pipeline_id,)
        )
        last_run = cursor.fetchone()
        run_number = (dict(last_run)["last"] or 0) + 1
        
        # Buscar user_id
        cursor.execute("SELECT id FROM users WHERE username = %s", (user_name,))
        user_id_result = cursor.fetchone()
        user_id = user_id_result['id'] if user_id_result else None
        
        # Criar novo run
        cursor.execute("""
                INSERT INTO pipeline_runs 
                (pipeline_id, run_number, status, started_at, started_by, environment_id, trigger_type)
                VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
        """, (pipeline_id, run_number, 'running', start_time.isoformat(), 
                  user_id, environment_id, trigger_type))
        
        run_id = cursor.fetchone()['id']
        conn.commit()
        release_db_connection(conn)
        
        # Adquirir lock do ambiente antes de iniciar a thread
        if environment_id:
            if not acquire_env_lock(environment_id, "build", run_id, pipeline.get('name', '')):
                release_db_connection(conn)
                running = get_env_running_info(environment_id)
                msg = "Ambiente ocupado — outra execução iniciou entre a verificação e o lock."
                if running:
                    msg = (
                        f"Ambiente ocupado: {running['type']} do pipeline '{running['pipeline']}' "
                        f"(iniciado em {running['started_at'].strftime('%H:%M:%S')}). "
                        f"Aguarde a conclusão."
                    )
                return jsonify({"error": "Ambiente ocupado", "message": msg}), 409
            current_app.logger.info(f"🔒 Lock adquirido para ambiente {environment_id} (build run_id={run_id})")

        # Iniciar execução em thread separada usando execute_pipeline_run
        thread = threading.Thread(
            target=execute_pipeline_run,
            args=(current_app._get_current_object(), run_id, pipeline_id, commands),
            kwargs={"environment_id": environment_id},
            daemon=True
        )
        thread.start()

        return jsonify({
            "success": True,
            "run_id": run_id,
            "run_number": run_number,
            "message": f"Pipeline #{run_number} iniciado"
        }), 200
        
    except Exception as e:
        current_app.logger.error(f"Erro ao executar pipeline: {e}")
        return jsonify({"error": str(e)}), 500


@pipelines_bp.route("/api/pipelines/<int:pipeline_id>/runs", methods=["GET"])
@require_auth
def get_pipeline_runs(pipeline_id):
    """Retorna histórico de execuções (runs) de um pipeline."""
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 20))
        offset = (page - 1) * limit
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Buscar runs com info de usuário e pipeline
        cursor.execute("""
            SELECT 
                pr.id, pr.run_number, pr.status, pr.started_at, pr.finished_at,
                pr.environment_id, pr.trigger_type, pr.error_message,
                CASE 
                    WHEN pr.trigger_type = 'scheduled' THEN 'Schedule'
                    ELSE COALESCE(u.username, 'Desconhecido')
                END as started_by_name,
                p.deploy_command_id
            FROM pipeline_runs pr
            LEFT JOIN users u ON pr.started_by = u.id
            LEFT JOIN pipelines p ON pr.pipeline_id = p.id
            WHERE pr.pipeline_id = %s
            ORDER BY pr.started_at DESC
            LIMIT %s OFFSET %s
        """, (pipeline_id, limit, offset))
        runs = cursor.fetchall()
        
        # Contar total
        cursor.execute(
            "SELECT COUNT(*) as count FROM pipeline_runs WHERE pipeline_id = %s",
            (pipeline_id,)
        )
        total_row = cursor.fetchone()
        total = total_row["count"] if total_row else 0
        
        release_db_connection(conn)
        
        return jsonify({
            "runs": [dict(row) for row in runs],
            "total": total,
            "page": page,
            "limit": limit
        }), 200
        
    except Exception as e:
        current_app.logger.error(f"Erro ao buscar runs: {e}")
        return jsonify({"error": str(e)}), 500


@pipelines_bp.route("/api/pipelines/<int:pipeline_id>/stream-logs")
@require_auth
def stream_logs(pipeline_id):
    def generate():
        max_wait_iterations = 10
        wait_iteration = 0
        start_time_of_this_run = None

        while wait_iteration < max_wait_iterations:
            conn_check = get_db()
            try:
                cursor_check = conn_check.cursor()
                cursor_check.execute(
                    "SELECT MAX(started_at) as last_start FROM execution_logs WHERE pipeline_id = %s",
                    (pipeline_id,),
                )
                last_run = cursor_check.fetchone()
            finally:
                release_db_connection(conn_check)

            if last_run and dict(last_run)["last_start"]:
                start_time_of_this_run = dict(last_run)["last_start"]
                break

            wait_iteration += 1
            time.sleep(1)

        if not start_time_of_this_run:
            yield "data: ERRO: Não foi possível encontrar o início da execução após 10 segundos.\n\n"
            return

        sent_output = {}
        is_finished = False

        while not is_finished:
            conn = get_db()
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM execution_logs WHERE pipeline_id = %s AND started_at >= %s ORDER BY id",
                    (pipeline_id, start_time_of_this_run),
                )
                logs = cursor.fetchall()

                for log in logs:
                    log_id = log["id"]
                    full_log_text = (log["output"] or "") + (log["error"] or "")
                    last_sent = sent_output.get(log_id, "")
                    if len(full_log_text) > len(last_sent):
                        new_text = full_log_text[len(last_sent) :]
                        for line in new_text.splitlines():
                            yield f"data: {line}\n\n"
                        sent_output[log_id] = full_log_text

                cursor = conn.cursor()
                cursor.execute(
                    "SELECT status FROM pipelines WHERE id = %s", (pipeline_id,)
                )
                pipeline = cursor.fetchone()
                if pipeline and pipeline["status"] in ("success", "failed"):
                    yield f"data: [FIM DA EXECUÇÃO - STATUS: {pipeline['status'].upper()}]\n\n"
                    is_finished = True
            finally:
                release_db_connection(conn)
            time.sleep(1)

    return current_app.response_class(generate(), mimetype="text/event-stream")


@pipelines_bp.route("/api/events")
@require_auth
def stream_events():
    from app.utils.serializers import convert_datetime_to_str
    def generate():
        q = event_manager.subscribe()
        try:
            while True:
                message = q.get()
                safe_message = convert_datetime_to_str(message)
                yield f"data: {json.dumps(safe_message)}\n\n"
        except GeneratorExit:
            event_manager.unsubscribe(q)

    return current_app.response_class(generate(), mimetype="text/event-stream")


# =====================================================================
# ROTAS DE PIPELINE SCHEDULES
# =====================================================================

@pipelines_bp.route("/api/schedules", methods=["GET"])
@require_auth
def get_schedules():
    """Lista todos os schedules do ambiente"""
    env_id = request.headers.get("X-Environment-Id")
    if not env_id:
        return jsonify({"error": "Cabeçalho X-Environment-Id é obrigatório"}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.*, p.name as pipeline_name, u.username as created_by_name
        FROM pipeline_schedules s
        JOIN pipelines p ON s.pipeline_id = p.id
        JOIN users u ON s.created_by = u.id
        WHERE s.environment_id = %s
        ORDER BY s.created_at DESC
    """, (env_id,))
    schedules = cursor.fetchall()
    
    release_db_connection(conn)
    return jsonify([dict(s) for s in schedules])


@pipelines_bp.route("/api/schedules", methods=["POST"])
@require_operator
def create_schedule():
    """Cria novo agendamento"""
    env_id = request.headers.get("X-Environment-Id")
    if not env_id:
        return jsonify({"error": "Cabeçalho X-Environment-Id é obrigatório"}), 400
    
    data = request.json
    required = ["pipeline_id", "name", "schedule_type", "schedule_config"]
    
    if not all(field in data for field in required):
        return jsonify({"error": "Campos obrigatórios faltando"}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        pipeline = cursor.execute(
            "SELECT id FROM pipelines WHERE id = %s AND environment_id = %s",
            (data["pipeline_id"], env_id)
        )
        pipeline = cursor.fetchone()
        
        if not pipeline:
            return jsonify({"error": "Pipeline não encontrada neste ambiente"}), 404
        
        schedule_config = json.loads(data["schedule_config"]) if isinstance(data["schedule_config"], str) else data["schedule_config"]
        
        next_run = None
        if data["schedule_type"] == "once":
            next_run = schedule_config.get("datetime")
        else:
            temp_schedule = {
                'schedule_type': data["schedule_type"],
                'schedule_config': json.dumps(schedule_config)
            }
            # Usa função standalone
            next_run_dt = calculate_next_run(temp_schedule)
            next_run = next_run_dt.isoformat() if next_run_dt else None
        
        cursor.execute("""
            INSERT INTO pipeline_schedules 
            (pipeline_id, environment_id, name, description, schedule_type, 
             schedule_config, is_active, created_by, created_at, next_run_at, notify_emails, notify_whatsapp)
            VALUES (%s, %s, %s, %s, %s, %s, False, %s, %s, %s, %s, %s) RETURNING id
        """, (
            data["pipeline_id"],
            env_id,
            data["name"],
            data.get("description", ""),
            data["schedule_type"],
            json.dumps(schedule_config),
            request.current_user["id"],
            datetime.now(),
            next_run,
            data.get("notify_emails"),
            data.get("notify_whatsapp")
        ))
        
        schedule_id = cursor.fetchone()['id']
        conn.commit()
        
        return jsonify({
            "success": True,
            "id": schedule_id,
            "message": "Agendamento criado com sucesso (INATIVO)"
        }), 201
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        release_db_connection(conn)


@pipelines_bp.route("/api/schedules/<int:schedule_id>", methods=["PUT"])
@require_operator
def update_schedule(schedule_id):
    """Atualiza agendamento"""
    env_id = request.headers.get("X-Environment-Id")
    if not env_id:
        return jsonify({"error": "Ambiente não especificado"}), 400
    
    data = request.json
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        schedule = cursor.execute(
            "SELECT id FROM pipeline_schedules WHERE id = %s AND environment_id = %s",
            (schedule_id, env_id)
        )
        schedule = cursor.fetchone()
        
        if not schedule:
            return jsonify({"error": "Agendamento não encontrado"}), 404
        
        schedule_config = json.loads(data["schedule_config"]) if isinstance(data["schedule_config"], str) else data["schedule_config"]
        
        next_run = None
        if data["schedule_type"] == "once":
            next_run = schedule_config.get("datetime")
        else:
            temp_schedule = {
                'schedule_type': data["schedule_type"],
                'schedule_config': json.dumps(schedule_config)
            }
            next_run_dt = calculate_next_run(temp_schedule)
            next_run = next_run_dt.isoformat() if next_run_dt else None
        
        cursor.execute("""
            UPDATE pipeline_schedules
            SET name = %s, description = %s, schedule_type = %s, 
                schedule_config = %s, next_run_at = %s, updated_at = %s,
                notify_emails = %s, notify_whatsapp = %s
            WHERE id = %s AND environment_id = %s
        """, (
            data["name"],
            data.get("description", ""),
            data["schedule_type"],
            json.dumps(schedule_config),
            next_run,
            datetime.now(),
            data.get("notify_emails"),
            data.get("notify_whatsapp"),
            schedule_id,
            env_id
        ))
        
        conn.commit()
        return jsonify({"success": True, "message": "Agendamento atualizado"})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        release_db_connection(conn)


@pipelines_bp.route("/api/schedules/<int:schedule_id>/toggle", methods=["PATCH"])
@require_operator
def toggle_schedule(schedule_id):
    """Ativa/Desativa agendamento"""
    env_id = request.headers.get("X-Environment-Id")
    if not env_id:
        return jsonify({"error": "Ambiente não especificado"}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        schedule = cursor.execute(
            "SELECT is_active FROM pipeline_schedules WHERE id = %s AND environment_id = %s",
            (schedule_id, env_id)
        )
        schedule = cursor.fetchone()
        
        if not schedule:
            return jsonify({"error": "Agendamento não encontrado"}), 404
        
        new_status = not schedule["is_active"]

        cursor.execute("""
            UPDATE pipeline_schedules
            SET is_active = %s, updated_at = %s
            WHERE id = %s AND environment_id = %s
        """, (new_status, datetime.now(), schedule_id, env_id))

        conn.commit()

        status_text = "ativado" if new_status else "desativado"
        return jsonify({
            "success": True,
            "is_active": new_status,
            "message": f"Agendamento {status_text}"
        })
        
    finally:
        release_db_connection(conn)


@pipelines_bp.route("/api/schedules/<int:schedule_id>", methods=["DELETE"])
@require_operator
def delete_schedule(schedule_id):
    """Deleta agendamento"""
    env_id = request.headers.get("X-Environment-Id")
    if not env_id:
        return jsonify({"error": "Ambiente não especificado"}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            "DELETE FROM pipeline_schedules WHERE id = %s AND environment_id = %s",
            (schedule_id, env_id)
        )
        if cursor.rowcount == 0:
             return jsonify({"error": "Agendamento não encontrado"}), 404
             
        conn.commit()
        return jsonify({"success": True, "message": "Agendamento excluído"})
        
    finally:
        release_db_connection(conn)

@pipelines_bp.route("/api/events", methods=["GET"])
@require_auth
def get_events():
    """Endpoint para polling de eventos/notificações."""
    try:
        env_id = request.headers.get('X-Environment-Id')
        
        if not env_id:
            return jsonify({"events": []})
        
        conn = get_db()
        cursor = conn.cursor()
        
        five_minutes_ago = (datetime.now() - timedelta(minutes=5)).isoformat()
        
        cursor.execute(
            """
            SELECT 
                l.id,
                l.status,
                l.started_at,
                l.output,
                p.name as pipeline_name,
                l.pipeline_id,
                l.command_id
            FROM execution_logs l
            JOIN pipelines p ON l.pipeline_id = p.id
            WHERE p.environment_id = %s
            AND l.started_at >= %s
            ORDER BY l.started_at DESC
            LIMIT 50
            """,
            (env_id, five_minutes_ago)
        )
        
        recent_logs = cursor.fetchall()
        events = []
        
        for log in recent_logs:
            log_dict = dict(log)
            
            event_type = "info"
            if log_dict['status'] == 'success':
                event_type = "success"
            elif log_dict['status'] == 'error':
                event_type = "error"
            elif log_dict['status'] == 'running':
                event_type = "progress"
            
            events.append({
                "id": log_dict['id'],
                "type": event_type,
                "title": f"Pipeline: {log_dict['pipeline_name'] or 'Desconhecida'}",
                "message": f"Status: {log_dict['status']}",
                "timestamp": log_dict['started_at'],
                "pipeline_id": log_dict['pipeline_id'],
                "command_id": log_dict['command_id']
            })
        
        release_db_connection(conn)
        
        return jsonify({
            "events": events,
            "count": len(events),
            "timestamp": datetime.now()
        })
    
    except Exception as e:
        current_app.logger.error(f"Erro ao buscar eventos: {e}")
        return jsonify({"events": [], "error": str(e)}), 500


# =====================================================================
# ENDPOINTS DE RUNS (Build History)
# =====================================================================

@pipelines_bp.route("/api/runs/<int:run_id>/logs", methods=["GET"])
@require_auth
def get_run_logs(run_id):
    """Retorna logs em tempo real de uma execução de pipeline."""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Verificar se run existe
        cursor.execute("SELECT * FROM pipeline_runs WHERE id = %s", (run_id,))
        run = cursor.fetchone()
        
        if not run:
            release_db_connection(conn)
            return jsonify({"error": "Run não encontrado"}), 404
        
        # Buscar logs dos comandos
        cursor.execute("""
            SELECT 
                prl.*,
                c.name as command_name,
                c.description as command_description
            FROM pipeline_run_logs prl
            LEFT JOIN commands c ON prl.command_id = c.id
            WHERE prl.run_id = %s
            ORDER BY prl.command_order
        """, (run_id,))
        logs = cursor.fetchall()
        
        release_db_connection(conn)
        
        return jsonify({
            "run": dict(run),
            "logs": [dict(row) for row in logs]
        }), 200
        
    except Exception as e:
        current_app.logger.error(f"Erro ao buscar logs do run: {e}")
        return jsonify({"error": str(e)}), 500


@pipelines_bp.route("/api/runs/<int:run_id>/releases", methods=["GET"])
@require_auth
def get_run_releases(run_id):
    """Retorna releases associados a um RUN específico."""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                r.*,
                u.username as deployed_by_name,
                e.name as environment_name,
                pr.run_number as build_number
            FROM releases r
            LEFT JOIN users u ON r.deployed_by = u.id
            LEFT JOIN environments e ON r.environment_id = e.id
            LEFT JOIN pipeline_runs pr ON r.run_id = pr.id
            WHERE r.run_id = %s
            ORDER BY r.started_at DESC
        """, (run_id,))
        releases = cursor.fetchall()
        
        release_db_connection(conn)
        
        return jsonify({
            "releases": [dict(row) for row in releases]
        }), 200
        
    except Exception as e:
        current_app.logger.error(f"Erro ao buscar releases do run: {e}")
        return jsonify({"error": str(e)}), 500


@pipelines_bp.route("/api/runs/<int:run_id>/release", methods=["POST"])
@require_operator
def create_release_from_run(run_id):
    """
    Cria um release (deploy) associado a um RUN específico.
    Só permite criar release se o RUN estiver com status 'success'.
    """
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # 1. Verificar se o RUN existe e foi bem-sucedido
        cursor.execute("""
            SELECT pr.*, p.name as pipeline_name, p.deploy_command_id
            FROM pipeline_runs pr
            JOIN pipelines p ON pr.pipeline_id = p.id
            WHERE pr.id = %s
        """, (run_id,))
        run = cursor.fetchone()
        
        if not run:
            release_db_connection(conn)
            return jsonify({"error": "Run não encontrado"}), 404
        
        run_dict = dict(run)
        
        # 2. Validar se o RUN foi bem-sucedido
        if run_dict['status'] != 'success':
            release_db_connection(conn)
            return jsonify({
                "error": "Release não permitido",
                "message": f"O build precisa ter status 'success'. Status atual: '{run_dict['status']}'"
            }), 400
        
        # 3. Verificar se pipeline tem comando de deploy configurado
        if not run_dict.get('deploy_command_id'):
            release_db_connection(conn)
            return jsonify({
                "error": "Deploy não configurado",
                "message": "Este pipeline não tem um comando de deploy associado"
            }), 400
        
        # 4. Buscar comando de deploy
        cursor.execute(
            "SELECT * FROM commands WHERE id = %s AND command_category = 'deploy'",
            (run_dict['deploy_command_id'],)
        )
        command = cursor.fetchone()
        
        if not command:
            release_db_connection(conn)
            return jsonify({"error": "Comando de deploy não encontrado"}), 404

        # 4.1 Verificar lock de ambiente — acesso exclusivo ao RPO
        environment_id = request.headers.get('X-Environment-Id') or run_dict.get('environment_id')
        if environment_id:
            running = get_env_running_info(environment_id)
            if running:
                release_db_connection(conn)
                return jsonify({
                    "error": "Ambiente ocupado",
                    "message": (
                        f"Já existe uma execução em andamento neste ambiente: "
                        f"{running['type']} do pipeline '{running['pipeline']}' "
                        f"(iniciado em {running['started_at'].strftime('%H:%M:%S')}). "
                        f"Aguarde a conclusão antes de iniciar o release."
                    )
                }), 409

        # 5. Obter próximo release_number
        cursor.execute(
            "SELECT MAX(release_number) as last FROM releases WHERE pipeline_id = %s",
            (run_dict['pipeline_id'],)
        )
        last_release = cursor.fetchone()
        release_number = (dict(last_release)["last"] or 0) + 1
        
        # 6. Criar registro do release
        cursor.execute("""
            INSERT INTO releases (
                pipeline_id, run_id, release_number, environment_id, deployed_by, 
                deploy_command_id, status, started_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
        """, (
            run_dict['pipeline_id'],
            run_id,
            release_number,
            environment_id,
            request.current_user['id'],
            run_dict['deploy_command_id'],
            'running',
            datetime.now()
        ))
        
        release_id = cursor.fetchone()['id']
        conn.commit()
        release_db_connection(conn)
        
        # 7. Adquirir lock e executar deploy em thread separada
        if environment_id:
            if not acquire_env_lock(environment_id, "release", release_id, run_dict.get('pipeline_name', '')):
                release_db_connection(conn)
                running = get_env_running_info(environment_id)
                msg = "Ambiente ocupado — outra execução iniciou entre a verificação e o lock."
                if running:
                    msg = (
                        f"Ambiente ocupado: {running['type']} do pipeline '{running['pipeline']}' "
                        f"(iniciado em {running['started_at'].strftime('%H:%M:%S')}). "
                        f"Aguarde a conclusão."
                    )
                return jsonify({"error": "Ambiente ocupado", "message": msg}), 409
            current_app.logger.info(f"🔒 Lock adquirido para ambiente {environment_id} (release_id={release_id})")

        thread = threading.Thread(
            target=execute_release,
            args=(current_app._get_current_object(), release_id, run_id, dict(command)),
            kwargs={"environment_id": environment_id},
            daemon=True
        )
        thread.start()

        current_app.logger.info(f"✅ Release {release_id} iniciado para run {run_id}")
        
        return jsonify({
            "success": True,
            "release_id": release_id,
            "message": f"Release iniciado para o build #{run_dict['run_number']}"
        }), 201
        
    except Exception as e:
        current_app.logger.error(f"❌ Erro ao criar release: {e}")
        return jsonify({"error": str(e)}), 500


@pipelines_bp.route("/api/environments/<int:env_id>/lock-status", methods=["GET"])
@require_auth
def get_environment_lock_status(env_id):
    """Verifica se o ambiente esta com execucao ativa (lock do RPO)."""
    running = get_env_running_info(env_id)
    if running:
        return jsonify({
            "locked": True,
            "type": running["type"],
            "id": running["id"],
            "pipeline": running["pipeline"],
            "started_at": running["started_at"].isoformat(),
        })
    return jsonify({"locked": False})


@pipelines_bp.route("/api/releases/<int:release_id>/logs", methods=["GET"])
@require_auth
def get_release_logs(release_id):
    """Retorna logs em tempo real de um release."""
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Verificar se release existe
        cursor.execute("SELECT * FROM releases WHERE id = %s", (release_id,))
        release = cursor.fetchone()
        
        if not release:
            return jsonify({"error": "Release não encontrado"}), 404
        
        # Buscar logs do release
        cursor.execute("""
            SELECT * FROM release_logs 
            WHERE release_id = %s
            ORDER BY created_at ASC
        """, (release_id,))
        logs = cursor.fetchall()
        
        return jsonify({
            "release": dict(release),
            "logs": [dict(row) for row in logs] if logs else []
        }), 200
        
    except Exception as e:
        current_app.logger.error(f"Erro ao buscar logs do release {release_id}: {e}")
        return jsonify({"error": str(e)}), 500
        
    finally:
        if conn:
            release_db_connection(conn)


@pipelines_bp.route("/api/releases/<int:release_id>/logs/stream", methods=["GET"])
@require_auth
def stream_release_logs(release_id):
    """
    Stream de logs em tempo real de um release.
    """
    from flask import Response
    from app.utils.serializers import convert_datetime_to_str
    
    def generate():
        conn = get_db()
        try:
            cursor = conn.cursor()

            last_log_id = 0
            max_iterations = 600  # 10 minutos com intervalo de 1s
            iterations = 0

            while iterations < max_iterations:
                # Buscar release status
                cursor.execute(
                    "SELECT status FROM releases WHERE id = %s",
                    (release_id,)
                )
                release = cursor.fetchone()

                if not release:
                    yield f"data: {json.dumps({'error': 'Release não encontrado'})}\n\n"
                    break

                # Buscar novos logs
                cursor.execute("""
                    SELECT * FROM release_logs
                    WHERE release_id = %s AND id > %s
                    ORDER BY created_at
                """, (release_id, last_log_id))
                logs = cursor.fetchall()

                # Enviar novos logs
                for log in logs:
                    log_dict = dict(log)
                    yield f"data: {json.dumps(convert_datetime_to_str(log_dict), ensure_ascii=False)}\n\n"
                    last_log_id = log_dict['id']

                # Verificar se release terminou
                release_status = release["status"]
                if release_status in ["success", "failed"]:
                    time.sleep(1)
                    final_msg = {"id": -1, "release_id": release_id, "output": f"\n[Deploy concluído com status: {release_status.upper()}]"}
                    yield f"data: {json.dumps(final_msg, ensure_ascii=False)}\n\n"
                    break

                iterations += 1
                time.sleep(1)
        finally:
            release_db_connection(conn)

    return current_app.response_class(generate(), mimetype="text/event-stream")


@pipelines_bp.route("/api/runs/<int:run_id>/output/stream")
@require_auth
def stream_run_output(run_id):
    """
    Stream de logs em tempo real de uma execução de build.
    Lê diretamente da memória para máxima performance.
    """
    from flask import Response, stream_with_context
    
    def generate():
        last_index = 0
        max_iterations = 1200  # 10 minutos com intervalo de 0.1s
        iterations = 0
        
        while iterations < max_iterations:
            stream = get_live_stream(run_id)
            logs = list(stream['logs'])
            
            # Enviar novos logs
            if len(logs) > last_index:
                for log in logs[last_index:]:
                    yield f"data: {json.dumps(log, ensure_ascii=False)}\n\n"
                last_index = len(logs)
            
            # Verificar se terminou
            if stream['status'] in ['success', 'failed']:
                # Enviar logs finais
                logs = list(stream['logs'])
                if len(logs) > last_index:
                    for log in logs[last_index:]:
                        yield f"data: {json.dumps(log, ensure_ascii=False)}\n\n"
                
                yield f"data: {json.dumps({'status': 'completed', 'final_status': stream['status']})}\n\n"
                
                # Cleanup imediato
                cleanup_live_stream(run_id)
                break
            
            iterations += 1
            time.sleep(0.1)  # Polling rápido: 100ms
    
    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )


@pipelines_bp.route("/api/runs/<int:run_id>/logs/stream")
@require_auth
def stream_run_logs(run_id):
    """
    Stream de logs em tempo real de uma execução de pipeline.
    Lê do banco de dados (pipeline_run_logs).
    """
    from flask import Response, stream_with_context
    from app.utils.serializers import convert_datetime_to_str
    
    def generate():
        conn = get_db()
        try:
            cursor = conn.cursor()

            last_log_id = 0
            max_iterations = 300  # 5 minutos com intervalo de 1s
            iterations = 0

            while iterations < max_iterations:
                # Buscar run status
                cursor.execute("SELECT status FROM pipeline_runs WHERE id = %s", (run_id,))
                run = cursor.fetchone()

                if not run:
                    yield f"data: {json.dumps({'error': 'Run não encontrado'})}\n\n"
                    break

                # Buscar novos logs
                cursor.execute("""
                    SELECT
                        prl.*,
                        c.name as command_name
                    FROM pipeline_run_logs prl
                    LEFT JOIN commands c ON prl.command_id = c.id
                    WHERE prl.run_id = %s AND prl.id > %s
                    ORDER BY prl.command_order
                """, (run_id, last_log_id))
                logs = cursor.fetchall()

                # Enviar novos logs
                for log in logs:
                    log_dict = dict(log)
                    yield f"data: {json.dumps(convert_datetime_to_str(log_dict), ensure_ascii=False)}\n\n"
                    last_log_id = log_dict['id']

                # Verificar se run terminou
                run_status = dict(run)["status"]
                if run_status in ["success", "failed"]:
                    yield f"data: {json.dumps({'status': 'completed', 'final_status': run_status})}\n\n"
                    break

                iterations += 1
                time.sleep(1)
        finally:
            release_db_connection(conn)
    
    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )
