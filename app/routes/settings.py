from flask import Blueprint, request, jsonify
from psycopg2 import IntegrityError
from datetime import datetime

from app.database import get_db, release_db_connection
from app.utils.security import (
    require_auth,
    require_admin,
    require_operator,
    check_protected_item
)

settings_bp = Blueprint('settings', __name__)

# =====================================================================
# ROTAS DE AMBIENTES
# =====================================================================

@settings_bp.route("/api/environments", methods=["GET"])
@require_auth
def get_environments():
    """Lista todos os ambientes."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM environments ORDER BY name")

    environments = [dict(row) for row in cursor.fetchall()]
    release_db_connection(conn)
    return jsonify(environments)

@settings_bp.route("/api/environments", methods=["POST"])
@require_admin
def create_environment():
    """Cria um novo ambiente. Apenas user admin (root) pode criar."""
    # Apenas user admin (root) pode criar ambientes
    if request.current_user["username"] != "admin":
        return jsonify({"error": "Apenas o administrador root pode criar ambientes"}), 403
    
    data = request.json
    if not data.get("name"):
        return jsonify({"error": "O nome do ambiente é obrigatório"}), 400
    
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO environments (name, description, created_at) VALUES (%s, %s, %s)",
            (data["name"], data.get("description", ""), datetime.now())
        )
        conn.commit()
        return jsonify({"success": True, "message": "Ambiente criado com sucesso"}), 201
    except IntegrityError:
        return jsonify({"error": "Um ambiente com este nome já existe"}), 409
    finally:
        release_db_connection(conn)

@settings_bp.route("/api/environments/<int:env_id>", methods=["PUT"])
@require_admin
def update_environment(env_id):
    """Atualiza um ambiente. Apenas user admin (root) pode editar."""
    # Apenas user admin (root) pode editar ambientes
    if request.current_user["username"] != "admin":
        return jsonify({"error": "Apenas o administrador root pode editar ambientes"}), 403
    
    data = request.json
    if not data.get("name"):
        return jsonify({"error": "O nome do ambiente é obrigatório"}), 400

    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Verificar se já existe outro ambiente com esse nome (exceto o atual)
        cursor.execute(
            "SELECT id FROM environments WHERE name = %s AND id != %s",
            (data["name"], env_id)
        )
        existing = cursor.fetchone()
        
        if existing:
            release_db_connection(conn)
            return jsonify({"error": "Um ambiente com este nome já existe"}), 409
        
        # Atualizar o ambiente
        cursor.execute(
            "UPDATE environments SET name = %s, description = %s WHERE id = %s",
            (data["name"], data.get("description", ""), env_id)
        )
        conn.commit()
        return jsonify({"success": True, "message": "Ambiente atualizado com sucesso"})
    
    except IntegrityError:
        return jsonify({"error": "Erro de integridade ao atualizar ambiente"}), 409
    
    finally:
        release_db_connection(conn)

@settings_bp.route("/api/environments/<int:env_id>", methods=["DELETE"])
@require_admin
def delete_environment(env_id):
    """Exclui um ambiente. Apenas user admin (root) pode excluir."""
    # Apenas user admin (root) pode excluir ambientes
    if request.current_user["username"] != "admin":
        return jsonify({"error": "Apenas o administrador root pode excluir ambientes"}), 403
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM environments WHERE id = %s", (env_id,))
    conn.commit()
    release_db_connection(conn)
    return jsonify({"success": True, "message": "Ambiente excluído com sucesso"})

# =====================================================================
# ROTAS DE CONFIGURAÇÕES DO SISTEMA (SERVER VARIABLES)
# =====================================================================


@settings_bp.route("/api/server-variables", methods=["GET"])
@require_operator
def get_server_variables():
    """Lista todas as variáveis de servidor. Senhas são mascaradas."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM server_variables ORDER BY name")

    variables = [dict(row) for row in cursor.fetchall()]
    
    # Mascarar valores de variáveis do tipo senha
    for var in variables:
        if var.get('is_password'):
            var['value'] = '••••••••'
    
    release_db_connection(conn)
    return jsonify(variables)

@settings_bp.route("/api/server-variables", methods=["POST"])
@require_operator
def create_server_variable():
    """Cria uma nova variável de servidor. Registra auditoria."""
    data = request.json
    if not data.get("name") or not data.get("value"):
        return jsonify({"error": "Nome e Valor são obrigatórios"}), 400
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO server_variables (name, value, description, is_password, created_at) VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (data["name"], data["value"], data.get("description", ""), data.get("is_password", False), datetime.now())
        )
        new_var = cursor.fetchone()
        # Registrar auditoria
        cursor.execute(
            "INSERT INTO server_variables_audit (variable_id, variable_name, change_type, old_value, new_value, changed_by) VALUES (%s, %s, %s, %s, %s, %s)",
            (new_var["id"], data["name"], "create", None, "(senha)" if data.get("is_password") else data["value"], request.current_user["username"])
        )
        conn.commit()
        return jsonify({"success": True, "message": "Variável criada com sucesso"}), 201
    except IntegrityError:
        return jsonify({"error": "Uma variável com este nome já existe"}), 409
    finally:
        release_db_connection(conn)

@settings_bp.route("/api/server-variables/<int:var_id>", methods=["PUT"])
@require_operator
def update_server_variable(var_id):
    """Atualiza variável de servidor. Registra auditoria com valor anterior."""
    data = request.json
    if not data.get("name") or not data.get("value"):
        return jsonify({"error": "Nome e Valor são obrigatórios"}), 400
    
    # Verificar se item é protegido (perfil admin pode editar protegidas)
    if request.current_user.get('profile') != 'admin' and check_protected_item('server_variables', var_id):
        return jsonify({"error": "Esta variável é protegida e não pode ser alterada"}), 403
    
    conn = get_db()
    cursor = conn.cursor()

    try:
        # Verificar se já existe outra variável com esse nome (exceto a atual)
        cursor.execute(
            "SELECT id FROM server_variables WHERE name = %s AND id != %s",
            (data["name"], var_id)
        )
        existing = cursor.fetchone()

        if existing:
            release_db_connection(conn)
            return jsonify({"error": "Uma variável com este nome já existe"}), 409

        # Buscar valor atual para auditoria
        cursor.execute("SELECT name, value, is_password FROM server_variables WHERE id = %s", (var_id,))
        current = cursor.fetchone()

        # Atualizar a variável (se valor for __KEEP_CURRENT__, mantém o atual)
        if data["value"] == "__KEEP_CURRENT__":
            cursor.execute(
                "UPDATE server_variables SET name = %s, description = %s, is_password = %s WHERE id = %s",
                (data["name"], data.get("description", ""), data.get("is_password", False), var_id)
            )
        else:
            cursor.execute(
                "UPDATE server_variables SET name = %s, value = %s, description = %s, is_password = %s WHERE id = %s",
                (data["name"], data["value"], data.get("description", ""), data.get("is_password", False), var_id)
            )

        # Registrar auditoria
        is_pwd = current["is_password"] if current else False
        old_val = "(senha)" if is_pwd else (current["value"] if current else None)
        new_val = "(senha)" if data.get("is_password") else ("(sem alteração)" if data["value"] == "__KEEP_CURRENT__" else data["value"])
        cursor.execute(
            "INSERT INTO server_variables_audit (variable_id, variable_name, change_type, old_value, new_value, changed_by) VALUES (%s, %s, %s, %s, %s, %s)",
            (var_id, data["name"], "update", old_val, new_val, request.current_user["username"])
        )

        conn.commit()
        return jsonify({"success": True, "message": "Variável atualizada com sucesso"})

    except IntegrityError:
        return jsonify({"error": "Erro de integridade ao atualizar variável"}), 409

    finally:
        release_db_connection(conn)

@settings_bp.route("/api/server-variables/<int:var_id>", methods=["DELETE"])
@require_operator
def delete_server_variable(var_id):
    """Exclui variável de servidor. Registra auditoria antes da exclusão."""
    # Verificar se item é protegido
    if check_protected_item('server_variables', var_id):
        return jsonify({"error": "Esta variável é protegida e não pode ser excluída"}), 403

    conn = get_db()
    cursor = conn.cursor()
    # Buscar dados para auditoria antes de deletar
    cursor.execute("SELECT name, value, is_password FROM server_variables WHERE id = %s", (var_id,))
    current = cursor.fetchone()
    # Registrar auditoria ANTES do delete (FK SET NULL mantém o registro)
    if current:
        old_val = "(senha)" if current["is_password"] else current["value"]
        cursor.execute(
            "INSERT INTO server_variables_audit (variable_id, variable_name, change_type, old_value, new_value, changed_by) VALUES (%s, %s, %s, %s, %s, %s)",
            (var_id, current["name"], "delete", old_val, None, request.current_user["username"])
        )
    cursor.execute("DELETE FROM server_variables WHERE id = %s", (var_id,))
    conn.commit()
    release_db_connection(conn)
    return jsonify({"success": True, "message": "Variável excluída com sucesso"})


@settings_bp.route("/api/server-variables/<int:var_id>/history", methods=["GET"])
@require_operator
def get_variable_history(var_id):
    """Retorna o histórico de alterações de uma variável."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM server_variables_audit WHERE variable_id = %s ORDER BY changed_at DESC LIMIT 50",
        (var_id,)
    )
    history = cursor.fetchall()
    release_db_connection(conn)
    return jsonify([dict(row) for row in history])


# =====================================================================
# ROTAS DE CONFIGURAÇÕES DE NOTIFICAÇÃO (GLOBAL)
# =====================================================================

@settings_bp.route("/api/notification-settings", methods=["GET"])
@require_admin
def get_notification_settings():
    """Retorna configurações globais de notificação."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM notification_settings WHERE id = 1")
    row = cursor.fetchone()
    release_db_connection(conn)
    
    if not row:
        return jsonify({})
    
    settings = dict(row)
    # Mascarar senha SMTP
    if settings.get("smtp_password"):
        settings["smtp_password"] = "••••••••"
        
    return jsonify(settings)

@settings_bp.route("/api/notification-settings", methods=["PUT"])
@require_admin
def update_notification_settings():
    """Atualiza configurações globais de notificação (email, WhatsApp)."""
    data = request.json
    conn = get_db()
    cursor = conn.cursor()
    
    # Se a senha for enviada com os marcadores, não atualiza a senha
    password_query_part = ""
    params = [
        data.get("smtp_server", ""),
        data.get("smtp_port") or None,
        data.get("smtp_user", ""),
        data.get("smtp_from_email", ""),
        data.get("whatsapp_api_url", ""),
        data.get("whatsapp_api_method", "POST"),
        data.get("whatsapp_api_headers", ""),
        data.get("whatsapp_api_body", "")
    ]
    
    if data.get("smtp_password") and data.get("smtp_password") != "••••••••":
        password_query_part = ", smtp_password = %s"
        params.append(data.get("smtp_password"))
        
    query = f"""
        UPDATE notification_settings 
        SET smtp_server = %s, smtp_port = %s, smtp_user = %s, smtp_from_email = %s,
            whatsapp_api_url = %s, whatsapp_api_method = %s, whatsapp_api_headers = %s, whatsapp_api_body = %s
            {password_query_part}
        WHERE id = 1
    """
    
    try:
        cursor.execute(query, tuple(params))
        conn.commit()
    except Exception as e:
        release_db_connection(conn)
        return jsonify({"error": str(e)}), 500
        
    release_db_connection(conn)
    return jsonify({"success": True, "message": "Configurações de notificação salvas com sucesso"})
