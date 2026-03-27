from flask import Blueprint, request, jsonify, current_app
from psycopg2 import IntegrityError, Error as PsycopgError
from datetime import datetime
import json
import os
import platform
import subprocess
import threading

from app.database import get_db, release_db_connection
from app.utils.security import (
    require_auth,
    require_operator,
    check_protected_item
)
from app.utils.helpers import now_br
from app.services.scheduler import calculate_next_run

services_bp = Blueprint('services', __name__)

# =====================================================================
# ROTAS DE SERVIÇOS (SERVER SERVICES)
# =====================================================================

@services_bp.route("/api/server-services", methods=["GET"])
@require_operator
def get_server_services():
    """Lista todos os serviços de servidor do ambiente ativo."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Filtrar por ambiente se fornecido
    environment_id = request.args.get('environment_id')
    
    if environment_id:
        cursor.execute("""
            SELECT ss.*, e.name as environment_name 
            FROM server_services ss
            LEFT JOIN environments e ON ss.environment_id = e.id
            WHERE ss.environment_id = %s
            ORDER BY ss.name
        """, (environment_id,))
    else:
        cursor.execute("""
            SELECT ss.*, e.name as environment_name 
            FROM server_services ss
            LEFT JOIN environments e ON ss.environment_id = e.id
            ORDER BY ss.name
        """)

    services = [dict(row) for row in cursor.fetchall()]
    release_db_connection(conn)
    return jsonify(services)

@services_bp.route("/api/server-services", methods=["POST"])
@require_operator
def create_server_service():
    """Cria um novo serviço de servidor."""
    data = request.json
    if not data.get("name"):
        return jsonify({"error": "O nome do serviço é obrigatório"}), 400
    if not data.get("server_name"):
        return jsonify({"error": "O nome do servidor é obrigatório"}), 400
    if not data.get("environment_id"):
        return jsonify({"error": "O ambiente é obrigatório"}), 400
        
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO server_services 
               (environment_id, name, display_name, server_name, description, is_active, created_at) 
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (
                data["environment_id"],
                data["name"], 
                data.get("display_name", data["name"]),
                data["server_name"],
                data.get("description", ""), 
                data.get("is_active", True),
                datetime.now()
            )
        )
        conn.commit()
        return jsonify({"success": True, "message": "Serviço criado com sucesso"}), 201
    except IntegrityError:
        return jsonify({"error": "Erro ao criar serviço"}), 409
    finally:
        release_db_connection(conn)

@services_bp.route("/api/server-services/<int:service_id>", methods=["PUT"])
@require_operator
def update_server_service(service_id):
    """Atualiza um serviço de servidor existente."""
    data = request.json
    if not data.get("name"):
        return jsonify({"error": "O nome do serviço é obrigatório"}), 400
    if not data.get("server_name"):
        return jsonify({"error": "O nome do servidor é obrigatório"}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Atualizar o serviço
        cursor.execute(
            """UPDATE server_services 
               SET name = %s, display_name = %s, server_name = %s, 
                   description = %s, is_active = %s, environment_id = %s
               WHERE id = %s""",
            (
                data["name"], 
                data.get("display_name", data["name"]),
                data["server_name"],
                data.get("description", ""), 
                data.get("is_active", True),
                data.get("environment_id"),
                service_id
            )
        )
        conn.commit()
        return jsonify({"success": True, "message": "Serviço atualizado com sucesso"})
    
    except IntegrityError:
        return jsonify({"error": "Erro de integridade ao atualizar serviço"}), 409
    
    finally:
        release_db_connection(conn)

@services_bp.route("/api/server-services/<int:service_id>", methods=["DELETE"])
@require_operator
def delete_server_service(service_id):
    """Exclui um serviço de servidor."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM server_services WHERE id = %s", (service_id,))
    conn.commit()
    release_db_connection(conn)
    return jsonify({"success": True, "message": "Serviço excluído com sucesso"})


# =====================================================================
# ROTAS DE GESTÃO DE SERVIÇOS (SERVICE ACTIONS)
# =====================================================================

@services_bp.route("/api/service-actions", methods=["GET"])
@require_auth
def get_service_actions():
    """Lista todas as ações de serviços"""
    env_id = request.headers.get("X-Environment-Id")
    if not env_id:
        return jsonify({"error": "Ambiente não especificado"}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM service_actions WHERE environment_id = %s ORDER BY name",
        (env_id,)
    )
    actions = [dict(row) for row in cursor.fetchall()]
    release_db_connection(conn)
    return jsonify(actions)

@services_bp.route("/api/service-actions", methods=["POST"])
@require_operator
def create_service_action():
    """Cria nova ação de serviço"""
    env_id = request.headers.get("X-Environment-Id")
    if not env_id:
        return jsonify({"error": "Ambiente não especificado"}), 400
    
    data = request.json
    
    if not data.get("name") or not data.get("action_type") or not data.get("os_type") or not data.get("service_ids"):
        return jsonify({"error": "Campos obrigatórios: name, action_type, os_type, service_ids"}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Calcular next_run_at se tiver agendamento
        next_run_at = None
        if data.get("schedule_type") and data.get("schedule_config"):
            schedule_config = json.loads(data.get("schedule_config")) if isinstance(data.get("schedule_config"), str) else data.get("schedule_config")
            
            if data.get("schedule_type") == "once":
                # Para execução única, pegar datetime do config como STRING (igual pipeline_schedules)
                next_run_at = schedule_config.get("datetime")
            else:
                # Para outros tipos, usar calculate_next_run (importado)
                temp_schedule = {
                    'schedule_type': data.get("schedule_type"),
                    'schedule_config': json.dumps(schedule_config) if isinstance(schedule_config, dict) else schedule_config
                }
                # USANDO FUNÇÃO IMPORTADA
                next_run_dt = calculate_next_run(temp_schedule)
                next_run_at = next_run_dt.isoformat() if next_run_dt else None
        
        cursor.execute(
            """INSERT INTO service_actions 
            (environment_id, name, description, action_type, os_type, force_stop, service_ids, 
             schedule_type, schedule_config, is_active, next_run_at, created_by, created_at, notify_emails, notify_whatsapp) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (
                env_id,
                data["name"],
                data.get("description", ""),
                data["action_type"],
                data["os_type"],
                data.get("force_stop", False),
                data["service_ids"],
                data.get("schedule_type"),
                data.get("schedule_config"),
                data.get("is_active", False),
                next_run_at,
                request.current_user["id"],
                now_br(),
                data.get("notify_emails"),
                data.get("notify_whatsapp")
            )
        )
        action_id = cursor.fetchone()['id']
        conn.commit()
        return jsonify({"success": True, "id": action_id, "message": "Ação criada com sucesso"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        release_db_connection(conn)

@services_bp.route("/api/service-actions/<int:action_id>", methods=["PUT"])
@require_operator
def update_service_action(action_id):
    """Atualiza ação de serviço"""
    env_id = request.headers.get("X-Environment-Id")
    if not env_id:
        return jsonify({"error": "Ambiente não especificado"}), 400
    
    data = request.json
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Buscar dados atuais da ação
        cursor.execute(
            "SELECT * FROM service_actions WHERE id = %s AND environment_id = %s",
            (action_id, env_id)
        )
        current_action = cursor.fetchone()
        
        if not current_action:
            return jsonify({"error": "Ação não encontrada"}), 404
        
        # Fazer merge dos dados atuais com os novos dados
        updated_data = {
            "name": data.get("name", current_action["name"]),
            "description": data.get("description", current_action["description"]),
            "action_type": data.get("action_type", current_action["action_type"]),
            "os_type": data.get("os_type", current_action["os_type"]),
            "force_stop": data.get("force_stop", current_action.get("force_stop", False)),
            "service_ids": data.get("service_ids", current_action["service_ids"]),
            "schedule_type": data.get("schedule_type") if "schedule_type" in data else current_action["schedule_type"],
            "schedule_config": data.get("schedule_config") if "schedule_config" in data else current_action["schedule_config"],
            "is_active": data.get("is_active", current_action["is_active"])
        }
        
        # Calcular next_run_at se tiver agendamento ATIVO
        next_run_at = None
        if updated_data["is_active"] and updated_data["schedule_type"] and updated_data["schedule_config"]:
            schedule_config = json.loads(updated_data["schedule_config"]) if isinstance(updated_data["schedule_config"], str) else updated_data["schedule_config"]
            
            if updated_data["schedule_type"] == "once":
                # Para execução única, pegar datetime do config como STRING
                next_run_at = schedule_config.get("datetime")
            else:
                # Para outros tipos, usar calculate_next_run
                temp_schedule = {
                    'schedule_type': updated_data["schedule_type"],
                    'schedule_config': json.dumps(schedule_config) if isinstance(schedule_config, dict) else schedule_config
                }
                # USANDO FUNÇÃO IMPORTADA
                next_run_dt = calculate_next_run(temp_schedule)
                next_run_at = next_run_dt.isoformat() if next_run_dt else None
        
        cursor.execute(
            """UPDATE service_actions 
            SET name = %s, description = %s, action_type = %s, os_type = %s, force_stop = %s, service_ids = %s,
                schedule_type = %s, schedule_config = %s, is_active = %s, next_run_at = %s, notify_emails = %s, notify_whatsapp = %s
            WHERE id = %s AND environment_id = %s""",
            (
                updated_data["name"],
                updated_data["description"],
                updated_data["action_type"],
                updated_data["os_type"],
                updated_data["force_stop"],
                updated_data["service_ids"],
                updated_data["schedule_type"],
                updated_data["schedule_config"],
                updated_data["is_active"],
                next_run_at,
                data.get("notify_emails") if "notify_emails" in data else current_action.get("notify_emails"),
                data.get("notify_whatsapp") if "notify_whatsapp" in data else current_action.get("notify_whatsapp"),
                action_id,
                env_id
            )
        )
        conn.commit()
        return jsonify({"success": True, "message": "Ação atualizada com sucesso"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        release_db_connection(conn)

@services_bp.route("/api/service-actions/<int:action_id>", methods=["DELETE"])
@require_operator
def delete_service_action(action_id):
    """Exclui ação de serviço"""
    env_id = request.headers.get("X-Environment-Id")
    if not env_id:
        return jsonify({"error": "Ambiente não especificado"}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM service_actions WHERE id = %s AND environment_id = %s", (action_id, env_id))
    conn.commit()
    release_db_connection(conn)
    return jsonify({"success": True, "message": "Ação excluída com sucesso"})

@services_bp.route("/api/service-actions/<int:action_id>/execute", methods=["POST"])
@require_operator
def execute_service_action(action_id):
    """Executa uma ação de serviço (start/stop)"""
    env_id = request.headers.get("X-Environment-Id")
    if not env_id:
        return jsonify({"error": "Ambiente não especificado"}), 400
    
    from app.services.runner import execute_service_action_logic
    
    user_id = request.current_user["id"]
    
    result = execute_service_action_logic(current_app._get_current_object(), action_id, env_id, user_id)
    
    status_code = result.pop("status_code", 200)
    return jsonify(result), status_code


# =====================================================================
# STATUS EM TEMPO REAL DOS SERVIÇOS
# =====================================================================

@services_bp.route("/api/server-services/status", methods=["GET"])
@require_auth
def get_server_services_status():
    """Consulta o status real dos serviços registrados em um ambiente."""
    env_id = request.args.get('environment_id')
    if not env_id:
        return jsonify({"error": "Ambiente não especificado (environment_id)"}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT id, name, display_name, server_name, is_active
            FROM server_services 
            WHERE environment_id = %s AND is_active = TRUE
            ORDER BY name
        """, (env_id,))
        services = [dict(row) for row in cursor.fetchall()]
        release_db_connection(conn)
        
        if not services:
            return jsonify([])
        
        # Carregar variáveis de ambiente do banco para resolver ${VAR}
        conn2 = get_db()
        cursor2 = conn2.cursor()
        cursor2.execute("SELECT name, value FROM server_variables")
        db_vars = cursor2.fetchall()
        env_vars = os.environ.copy()
        for var in db_vars:
            env_vars[var['name']] = var['value']
        release_db_connection(conn2)
        
        results = []
        for svc in services:
            service_name = svc['name']
            server_name = svc.get('server_name', 'localhost')
            
            # Substituir variáveis ${VAR} no server_name
            import re
            variables_found = re.findall(r'\$\{([A-Z_0-9]+)\}', server_name)
            for var_name in variables_found:
                if var_name in env_vars:
                    server_name = server_name.replace(f"${{{var_name}}}", env_vars[var_name])
            
            status_info = _check_service_status(service_name, server_name, env_vars)
            results.append({
                "id": svc['id'],
                "name": service_name,
                "display_name": svc.get('display_name', service_name),
                "status": status_info["status"],
                "details": status_info.get("details", "")
            })
            
        return jsonify(results)
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def _sanitize_service_name(name):
    """Sanitiza nome de serviço para prevenir injeção de comando."""
    import re
    if not re.match(r'^[a-zA-Z0-9._@:/-]+$', name):
        raise ValueError(f"Nome de serviço inválido: {name}")
    return name

def _check_service_status(service_name, server_name, env_vars):
    """
    Verifica o status de um serviço no servidor indicado.
    Retorna: {"status": "running"|"stopped"|"unknown", "details": "..."}
    """
    is_linux_server = platform.system() == 'Linux'

    try:
        service_name = _sanitize_service_name(service_name)

        if is_linux_server:
            # Linux: systemctl is-active <service_name> — sem shell=True
            result = subprocess.run(
                ["systemctl", "is-active", service_name],
                shell=False,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=10,
                env=env_vars
            )
            output = result.stdout.strip().lower()
            if output == 'active':
                return {"status": "running", "details": "active"}
            elif output in ('inactive', 'deactivating'):
                return {"status": "stopped", "details": output}
            elif output == 'failed':
                return {"status": "error", "details": "failed"}
            else:
                return {"status": "unknown", "details": output}
        else:
            # Windows
            is_local = server_name.lower() in ['localhost', '127.0.0.1', '.', ''] or \
                        server_name.lower() == os.environ.get('COMPUTERNAME', '').lower()
            
            service_name = _sanitize_service_name(service_name)
            if is_local:
                ps_script = f"(Get-Service -Name '{service_name}' -ErrorAction SilentlyContinue).Status"
            else:
                ps_script = f"Invoke-Command -ComputerName '{server_name}' -ScriptBlock {{ (Get-Service -Name '{service_name}' -ErrorAction SilentlyContinue).Status }}"
            
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
                shell=False,
                capture_output=True,
                text=True,
                encoding='cp850',
                errors='replace',
                timeout=15,
                env=env_vars
            )
            output = result.stdout.strip()
            
            if output.lower() == 'running':
                return {"status": "running", "details": "Running"}
            elif output.lower() == 'stopped':
                return {"status": "stopped", "details": "Stopped"}
            elif output:
                return {"status": "unknown", "details": output}
            else:
                return {"status": "unknown", "details": result.stderr.strip() or "Service not found"}
    
    except subprocess.TimeoutExpired:
        return {"status": "unknown", "details": "Timeout ao verificar status"}
    except Exception as e:
        return {"status": "unknown", "details": str(e)}


# =====================================================================
# HISTÓRICO DE EXECUÇÕES DE AÇÕES
# =====================================================================

@services_bp.route("/api/service-actions/<int:action_id>/logs", methods=["GET"])
@require_auth
def get_service_action_logs(action_id):
    """Retorna histórico de execuções de uma ação."""
    env_id = request.headers.get("X-Environment-Id")
    if not env_id:
        return jsonify({"error": "Ambiente não especificado"}), 400
    
    limit = request.args.get('limit', 20, type=int)
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT sal.*, u.username as executed_by_name
            FROM service_action_logs sal
            LEFT JOIN users u ON sal.executed_by = u.id
            WHERE sal.action_id = %s AND sal.environment_id = %s
            ORDER BY sal.executed_at DESC
            LIMIT %s
        """, (action_id, env_id, limit))
        
        logs = [dict(row) for row in cursor.fetchall()]
        return jsonify(logs)
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        release_db_connection(conn)
