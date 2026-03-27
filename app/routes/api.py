import string
import secrets
import threading
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app

from app.database import get_db, release_db_connection
from app.utils.security import require_admin, require_api_key
from app.services.runner import execute_pipeline_thread

api_bp = Blueprint('api', __name__)

# =====================================================================
# GERENCIAMENTO DE CHAVES DE API (Interno, para o Painel)
# =====================================================================
@api_bp.route("/api/api_management/keys", methods=["GET"])
@require_admin
def get_api_keys():
    """Lista todas as API keys. Chaves são mascaradas (últimos 6 chars)."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, key, is_active, created_by, created_at, last_used_at FROM api_keys ORDER BY created_at DESC")
    keys = [dict(row) for row in cursor.fetchall()]
    
    # Mascara as chaves para segurança no front, exceto as últimas 6
    for k in keys:
        if len(k['key']) > 8:
            k['masked_key'] = "..." + k['key'][-6:]
        else:
            k['masked_key'] = k['key']
            
    release_db_connection(conn)
    return jsonify(keys)

@api_bp.route("/api/api_management/keys", methods=["POST"])
@require_admin
def create_api_key():
    """Gera nova API key (prefixo at_ + 48 chars aleatórios)."""
    data = request.json
    name = data.get("name")
    if not name:
        return jsonify({"error": "O nome da chave é obrigatório"}), 400
        
    alphabet = string.ascii_letters + string.digits
    api_key_value = "at_" + "".join(secrets.choice(alphabet) for i in range(48))
    
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO api_keys (name, key, is_active, created_by, created_at) VALUES (%s, %s, %s, %s, %s)",
            (name, api_key_value, True, request.current_user['id'], datetime.now())
        )
        conn.commit()
    except Exception as e:
        release_db_connection(conn)
        return jsonify({"error": str(e)}), 500
        
    release_db_connection(conn)
    return jsonify({"success": True, "key": api_key_value, "message": "Chave de API gerada com sucesso"})

@api_bp.route("/api/api_management/keys/<int:key_id>", methods=["DELETE"])
@require_admin
def delete_api_key(key_id):
    """Exclui uma API key permanentemente."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM api_keys WHERE id = %s", (key_id,))
    conn.commit()
    release_db_connection(conn)
    return jsonify({"success": True, "message": "Chave de API excluída com sucesso"})

# =====================================================================
# ROTAS DA API EXTERNA (Para integrações via Webhooks / Clients)
# =====================================================================

@api_bp.route("/api/v1/pipelines/<int:pipeline_id>/trigger", methods=["POST"])
@require_api_key
def trigger_pipeline(pipeline_id):
    """
    Aciona um pipeline externamente via API Key.
    """
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM pipelines WHERE id = %s", (pipeline_id,))
        pipeline = cursor.fetchone()

        if not pipeline:
            return jsonify({"error": "Pipeline não encontrado"}), 404

        api_key_name = request.api_key.get("name", "API Externa") if hasattr(request, 'api_key') else "API Externa"

        # Inicia a execução em background
        thread = threading.Thread(
            target=execute_pipeline_thread,
            args=(current_app._get_current_object(), pipeline_id, f"API Key ({api_key_name})", "api", None, None),
            daemon=True
        )
        thread.start()

        return jsonify({
            "success": True,
            "message": f"Pipeline {pipeline['name']} iniciado com sucesso via API.",
            "pipeline_id": pipeline_id
        }), 202

    except Exception as e:
        current_app.logger.error(f"Erro ao acionar pipeline via API: {str(e)}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            release_db_connection(conn)

@api_bp.route("/api/v1/pipelines/<int:pipeline_id>/status", methods=["GET"])
@require_api_key
def get_pipeline_status(pipeline_id):
    """
    Recupera o status atual do pipeline.
    """
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("SELECT name, status, last_run, duration FROM pipelines WHERE id = %s", (pipeline_id,))
        pipeline = cursor.fetchone()

        if not pipeline:
            return jsonify({"error": "Pipeline não encontrado"}), 404

        # Pega a última execução
        cursor.execute(
            "SELECT id, status, started_at, finished_at FROM pipeline_runs WHERE pipeline_id = %s ORDER BY started_at DESC LIMIT 1",
            (pipeline_id,)
        )
        last_run = cursor.fetchone()

        return jsonify({
            "pipeline_id": pipeline_id,
            "name": pipeline["name"],
            "pipeline_status": pipeline["status"],
            "last_run_details": dict(last_run) if last_run else None
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            release_db_connection(conn)

@api_bp.route("/api/v1/services/actions/<int:action_id>/trigger", methods=["POST"])
@require_api_key
def trigger_service_action(action_id):
    """
    Aciona uma Service Action externamente via API Key.
    """
    from app.services.runner import execute_service_action_logic

    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("SELECT id, name, environment_id FROM service_actions WHERE id = %s", (action_id,))
        action = cursor.fetchone()

        if not action:
            return jsonify({"error": "Service Action não encontrada"}), 404

        action_dict = dict(action)
        api_key_name = request.api_key.get("name", "API Externa") if hasattr(request, 'api_key') else "API Externa"

        # Executa em background usando a lógica do runner
        thread = threading.Thread(
            target=execute_service_action_logic,
            args=(current_app._get_current_object(), action_id, action_dict['environment_id'], None),
            daemon=True
        )
        thread.start()

        return jsonify({
            "success": True,
            "message": f"Service Action '{action_dict['name']}' iniciada via API.",
            "action_id": action_id
        }), 202

    except Exception as e:
        current_app.logger.error(f"Erro ao acionar Service Action via API: {str(e)}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            release_db_connection(conn)
