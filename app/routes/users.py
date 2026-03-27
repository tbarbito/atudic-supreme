from flask import Blueprint, request, jsonify, current_app
from psycopg2 import IntegrityError, Error as PsycopgError
import traceback
from datetime import datetime

from app.database import get_db, release_db_connection
from app.utils.security import (
    require_admin,
    hash_password,
    verify_password,
    get_user_permissions
)
from app.utils.audit import log_audit

users_bp = Blueprint('users', __name__)

# =====================================================================
# ROTAS DE USUÁRIOS
# =====================================================================

@users_bp.route("/api/users", methods=["GET"])
@require_admin
def get_users():
    """Lista todos os usuários com seus ambientes vinculados"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, username, name, email, profile, active, created_at, last_login, session_timeout_minutes FROM users WHERE username != 'admin'"
    )
    users = [dict(row) for row in cursor.fetchall()]

    # Busca ambientes vinculados a cada usuário
    for user in users:
        cursor.execute(
            "SELECT environment_id FROM user_environments WHERE user_id = %s",
            (user['id'],)
        )
        user['environment_ids'] = [row['environment_id'] for row in cursor.fetchall()]

    release_db_connection(conn)
    return jsonify(users)


@users_bp.route("/api/users", methods=["POST"])
@require_admin
def create_user():
    """Cria novo usuário com logging e auditoria"""
    data = request.json
    
    try:
        # Validação
        required_fields = ["username", "name", "email", "password", "profile"]
        for field in required_fields:
            if not data.get(field):
                current_app.logger.warning(f"Create user failed: missing field {field}")
                return jsonify({"error": f"Campo {field} é obrigatório"}), 400

        hashed_password, salt = hash_password(data["password"])

        conn = get_db()
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO users (username, name, email, password, password_salt, profile, active, session_timeout_minutes, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                data["username"],
                data["name"],
                data["email"],
                hashed_password,
                salt,
                data["profile"],
                data.get("active", True),
                data.get("session_timeout_minutes", 0),
                datetime.now(),
            ),
        )

        user_id = cursor.fetchone()['id']

        # Vincular ambientes ao usuário
        environment_ids = data.get('environment_ids', [])
        if environment_ids:
            for env_id in environment_ids:
                cursor.execute(
                    "INSERT INTO user_environments (user_id, environment_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    (user_id, env_id)
                )

        conn.commit()
        release_db_connection(conn)

        # AUDITORIA: Registra criação de usuário
        log_audit(
            action='create_user',
            user_id=request.current_user['id'],
            user_name=request.current_user['username'],
            details=f"Created user: {data['username']} (ID: {user_id})",
            status='success'
        )
        
        current_app.logger.info(f"User created: {data['username']} (ID: {user_id})")

        return jsonify({
            "success": True,
            "id": user_id,
            "message": "Usuário criado com sucesso",
        }), 201

    except IntegrityError as e:
        current_app.logger.warning(f"Create user failed: {e}")
        
        log_audit(
            action='create_user',
            user_id=request.current_user['id'],
            user_name=request.current_user['username'],
            details=f"Failed to create user: {data.get('username', 'unknown')} - {str(e)}",
            status='failure'
        )
        
        return jsonify({"error": "Nome de usuário já existe"}), 400
    
    except Exception as e:
        current_app.logger.error(f"Unexpected error creating user: {e}")
        current_app.logger.error(traceback.format_exc())
        
        log_audit(
            action='create_user',
            user_id=request.current_user['id'],
            user_name=request.current_user['username'],
            details=f"Error creating user: {str(e)}",
            status='failure'
        )
        
        return jsonify({"error": "Erro ao criar usuário"}), 500         


@users_bp.route("/api/users/<int:user_id>", methods=["PUT"])
@require_admin
def update_user(user_id):
    """Atualiza usuário existente com prepared statements"""
    data = request.json

    conn = get_db()
    cursor = conn.cursor()

    # Verificação de permissão
    cursor.execute(
        "SELECT username FROM users WHERE id = %s", (user_id,)
    )
    user_to_edit = cursor.fetchone()
    
    if (user_to_edit and user_to_edit["username"] == "admin" 
        and request.current_user["username"] != "admin"):
        release_db_connection(conn)
        return jsonify({
            "error": "Apenas o próprio usuário 'admin' pode alterar seus dados."
        }), 403

    # Construir query com prepared statements seguros
    allowed_fields = {
        'name': str,
        'email': str,
        'profile': str,
        'active': bool,
        'session_timeout_minutes': int
    }
    
    update_parts = []
    values = []
    
    for field, field_type in allowed_fields.items():
        if field in data:
            # Valida tipo de dado
            try:
                value = field_type(data[field])
                update_parts.append(f"{field} = %s")
                values.append(value)
            except (ValueError, TypeError):
                release_db_connection(conn)
                return jsonify({"error": f"Tipo inválido para campo {field}"}), 400
    
    # Tratamento especial para senha
    if "password" in data and data["password"]:
        hashed_password, salt = hash_password(data["password"])
        update_parts.append("password = %s")
        update_parts.append("password_salt = %s")
        values.append(hashed_password)
        values.append(salt)
    
    if not update_parts:
        release_db_connection(conn)
        return jsonify({"error": "Nenhum campo para atualizar"}), 400

    values.append(user_id)
    
    # Query segura com placeholders
    query = f"UPDATE users SET {', '.join(update_parts)} WHERE id = %s"
    
    try:
        cursor.execute(query, tuple(values))

        # Atualizar ambientes vinculados (se enviado)
        if 'environment_ids' in data:
            environment_ids = data['environment_ids']
            cursor.execute("DELETE FROM user_environments WHERE user_id = %s", (user_id,))
            for env_id in environment_ids:
                cursor.execute(
                    "INSERT INTO user_environments (user_id, environment_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    (user_id, env_id)
                )

        conn.commit()
        return jsonify({"success": True, "message": "Usuário atualizado com sucesso"})
    except PsycopgError as e:
        return jsonify({"error": f"Erro no banco de dados: {str(e)}"}), 500
    finally:
        release_db_connection(conn)


@users_bp.route("/api/users/<int:user_id>", methods=["DELETE"])
@require_admin
def delete_user(user_id):
    """Deleta usuário com auditoria"""
    
    try:
        if user_id == request.current_user["id"]:
            return jsonify({"error": "Você não pode excluir seu próprio usuário"}), 400

        conn = get_db()
        cursor = conn.cursor()

        # Busca informações do usuário antes de deletar
        cursor.execute("SELECT username FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()

        if not user:
            release_db_connection(conn)
            return jsonify({"error": "Usuário não encontrado"}), 404

        if user["username"] == "admin":
            release_db_connection(conn)
            return jsonify({"error": "Não é possível excluir o administrador principal"}), 400

        deleted_username = user["username"]
        cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()
        release_db_connection(conn)
        
        # AUDITORIA: Registra exclusão
        log_audit(
            action='delete_user',
            user_id=request.current_user['id'],
            user_name=request.current_user['username'],
            details=f"Deleted user: {deleted_username} (ID: {user_id})",
            status='success'
        )
        
        current_app.logger.info(f"User deleted: {deleted_username} (ID: {user_id})")

        return jsonify({"success": True, "message": "Usuário excluído com sucesso"})
    
    except Exception as e:
        current_app.logger.error(f"Error deleting user {user_id}: {e}")
        current_app.logger.error(traceback.format_exc())
        
        log_audit(
            action='delete_user',
            user_id=request.current_user['id'],
            user_name=request.current_user['username'],
            details=f"Failed to delete user ID {user_id}: {str(e)}",
            status='failure'
        )
        
        return jsonify({"error": "Erro ao excluir usuário"}), 500

@users_bp.route("/api/users/<int:user_id>/password", methods=["PUT"])
@require_admin
def admin_change_user_password(user_id):
    """
    [ADMIN] Altera a senha de um usuário específico.
    Requer a senha do admin que está executando a ação para autorização.
    """
    data = request.json
    admin_password = data.get("admin_password")
    new_password = data.get("new_password")

    if not admin_password or not new_password:
        return jsonify({"error": "Todos os campos de senha são obrigatórios"}), 400

    # 1. Verificar a senha do admin que está fazendo a ação
    current_admin = request.current_user
    if not verify_password(current_admin["password"], current_admin["password_salt"], admin_password):
        return jsonify({"error": "Senha do administrador incorreta. Ação não autorizada."}), 403

    # 2. Se a senha do admin estiver correta, hashear a nova senha do usuário alvo
    new_hashed_password, new_salt = hash_password(new_password)
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET password = %s, password_salt = %s WHERE id = %s",
        (new_hashed_password, new_salt, user_id),
    )
    conn.commit()
    release_db_connection(conn)

    return jsonify({"success": True, "message": "Senha do usuário alterada com sucesso!"})
