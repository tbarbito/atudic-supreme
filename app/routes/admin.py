from flask import Blueprint, request, jsonify, current_app
import json
import os

from app.database import get_db, release_db_connection
from app.utils.security import require_admin, require_auth
from app.utils.rate_limiter import rate_limiter
from app.utils.crypto import token_encryption

admin_bp = Blueprint('admin', __name__)

@admin_bp.route("/api/admin/logs/<log_type>", methods=["GET"])
@require_admin
def get_system_logs(log_type):
    """
    Retorna logs do sistema (apenas admin).
    
    Tipos: general, errors, audit
    """
    allowed_types = ['general', 'errors', 'audit']
    if log_type not in allowed_types:
        return jsonify({"error": "Tipo de log inválido"}), 400
    
    log_file_map = {
        'general': 'app.log',
        'errors': 'errors.log',
        'audit': 'audit.log'
    }
    
    # Logs estão na raiz do projeto, dois níveis acima de app/routes
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    
    log_file = os.path.join(
        base_dir, 
        'logs', 
        log_file_map[log_type]
    )
    
    if not os.path.exists(log_file):
        # Tenta fallback para diretório atual se estiver rodando de outro lugar
        fallback_log = os.path.join('logs', log_file_map[log_type])
        if os.path.exists(fallback_log):
            log_file = fallback_log
        else:
            return jsonify({"error": "Arquivo de log não encontrado"}), 404
    
    # Lê últimas N linhas
    lines = request.args.get('lines', 100, type=int)
    lines = min(lines, 1000)  # Máximo 1000 linhas
    
    try:
        with open(log_file, 'r') as f:
            all_lines = f.readlines()
            last_lines = all_lines[-lines:]
        
        return jsonify({
            "log_type": log_type,
            "lines": last_lines,
            "total_lines": len(last_lines)
        })
    
    except Exception as e:
        return jsonify({"error": f"Erro ao ler log: {str(e)}"}), 500

@admin_bp.route("/api/admin/rate-limits", methods=["GET"])
@require_admin
def get_rate_limits():
    """Retorna estatísticas de rate limiting (apenas admin)"""
    with rate_limiter.lock:
        stats = {
            "active_identifiers": len(rate_limiter.requests),
            "total_tracked_requests": sum(len(reqs) for reqs in rate_limiter.requests.values()),
            "top_requesters": []
        }
        
        # Top 10 usuários com mais requisições
        sorted_requests = sorted(
            rate_limiter.requests.items(),
            key=lambda x: len(x[1]),
            reverse=True
        )[:10]
        
        for identifier, requests in sorted_requests:
            stats["top_requesters"].append({
                "identifier": identifier,
                "request_count": len(requests)
            })
        
        return jsonify(stats)

@admin_bp.route("/api/admin/rate-limits/clear", methods=["POST"])
@require_admin
def clear_rate_limits():
    """Limpa todos os rate limits (apenas admin)"""
    data = request.json
    identifier = data.get("identifier")
    
    if identifier:
        rate_limiter.clear_user(identifier)
        return jsonify({"success": True, "message": f"Rate limit limpo para {identifier}"})
    else:
        # Limpa tudo
        with rate_limiter.lock:
            rate_limiter.requests.clear()
        return jsonify({"success": True, "message": "Todos os rate limits foram limpos"})


@admin_bp.route("/api/admin/encryption-key/info", methods=["GET"])
@require_admin
def get_encryption_key_info():
    """Retorna informações sobre a chave de criptografia (sem expor a chave)."""
    if not token_encryption:
        return jsonify({"error": "Sistema de criptografia não inicializado"}), 500
    return jsonify(token_encryption.get_key_info())


@admin_bp.route("/api/admin/encryption-key/backup", methods=["POST"])
@require_admin
def create_encryption_key_backup():
    """Cria backup da chave de criptografia no servidor."""
    if not token_encryption:
        return jsonify({"error": "Sistema de criptografia não inicializado"}), 500
    try:
        backup_path = token_encryption.create_backup()
        return jsonify({"success": True, "backup_path": backup_path})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =====================================================================
# WEBHOOKS CRUD
# =====================================================================

@admin_bp.route("/api/admin/webhooks", methods=["GET"])
@require_admin
def list_webhooks():
    """Lista todos os webhooks configurados."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM webhooks ORDER BY created_at DESC")
    webhooks = cursor.fetchall()
    release_db_connection(conn)
    return jsonify([dict(w) for w in webhooks])


@admin_bp.route("/api/admin/webhooks", methods=["POST"])
@require_admin
def create_webhook():
    """Cria um novo webhook."""
    data = request.json
    if not data or not data.get("name") or not data.get("url") or not data.get("events"):
        return jsonify({"error": "name, url e events são obrigatórios"}), 400

    headers_json = json.dumps(data.get("headers", {}))
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO webhooks (name, url, events, headers, is_active, created_by)
           VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
        (
            data["name"],
            data["url"],
            data["events"],
            headers_json,
            data.get("is_active", True),
            request.current_user["username"],
        ),
    )
    new_id = cursor.fetchone()["id"]
    conn.commit()
    release_db_connection(conn)
    return jsonify({"success": True, "id": new_id}), 201


@admin_bp.route("/api/admin/webhooks/<int:webhook_id>", methods=["PUT"])
@require_admin
def update_webhook(webhook_id):
    """Atualiza um webhook existente."""
    data = request.json
    if not data:
        return jsonify({"error": "Dados não fornecidos"}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM webhooks WHERE id = %s", (webhook_id,))
    if not cursor.fetchone():
        release_db_connection(conn)
        return jsonify({"error": "Webhook não encontrado"}), 404

    fields = []
    values = []
    for field in ("name", "url", "events", "is_active"):
        if field in data:
            fields.append(f"{field} = %s")
            values.append(data[field])
    if "headers" in data:
        fields.append("headers = %s")
        values.append(json.dumps(data["headers"]))

    if not fields:
        release_db_connection(conn)
        return jsonify({"error": "Nenhum campo para atualizar"}), 400

    values.append(webhook_id)
    cursor.execute(
        f"UPDATE webhooks SET {', '.join(fields)} WHERE id = %s", values
    )
    conn.commit()
    release_db_connection(conn)
    return jsonify({"success": True})


@admin_bp.route("/api/admin/webhooks/<int:webhook_id>", methods=["DELETE"])
@require_admin
def delete_webhook(webhook_id):
    """Remove um webhook."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM webhooks WHERE id = %s", (webhook_id,))
    if cursor.rowcount == 0:
        release_db_connection(conn)
        return jsonify({"error": "Webhook não encontrado"}), 404
    conn.commit()
    release_db_connection(conn)
    return jsonify({"success": True})


@admin_bp.route("/api/admin/webhooks/<int:webhook_id>/test", methods=["POST"])
@require_admin
def test_webhook(webhook_id):
    """Envia um evento de teste para o webhook."""
    from app.services.webhook_dispatcher import _send_webhook

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM webhooks WHERE id = %s", (webhook_id,))
    webhook = cursor.fetchone()
    release_db_connection(conn)

    if not webhook:
        return jsonify({"error": "Webhook não encontrado"}), 404

    _send_webhook(dict(webhook), "WEBHOOK_TEST", {"message": "Teste de webhook AtuDIC"})
    return jsonify({"success": True, "message": f"Evento de teste enviado para {webhook['url']}"})
