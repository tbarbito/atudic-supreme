from flask import Blueprint, request, jsonify, current_app
from psycopg2 import IntegrityError, Error as PsycopgError
import traceback
from datetime import datetime

from app.database import get_db, release_db_connection
from app.utils.security import (
    require_admin,
    hash_password,
    verify_password,
    get_user_permissions,
    get_effective_permission_keys,
)
from app.utils.permissions import (
    is_valid_permission_key,
    catalog_for_api,
    VALID_EFFECTS,
    DEFAULT_ROLE_PERMISSIONS,
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


# =====================================================================
# ROTAS DE PERMISSION OVERRIDES (RBAC HIBRIDO)
# =====================================================================

@users_bp.route("/api/permissions/catalog", methods=["GET"])
@require_admin
def get_permissions_catalog():
    """Retorna o catalogo completo de permission_keys com metadados."""
    return jsonify({
        "catalog": catalog_for_api(),
        "roles": {
            role: sorted(keys)
            for role, keys in DEFAULT_ROLE_PERMISSIONS.items()
        },
    })


@users_bp.route("/api/users/<int:user_id>/permissions", methods=["GET"])
@require_admin
def get_user_effective_permissions(user_id):
    """
    Retorna permissoes efetivas de um usuario + overrides ativos.
    Inclui de onde vem cada permissao (perfil, grant, deny).
    """
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT id, username, profile, active FROM users WHERE id = %s",
            (user_id,),
        )
        user = cursor.fetchone()
        if not user:
            return jsonify({"error": "Usuário não encontrado"}), 404

        user = dict(user)

        # Overrides ativos
        cursor.execute(
            """
            SELECT o.id, o.permission_key, o.effect, o.reason, o.expires_at, o.created_at,
                   g.username AS granted_by_username
            FROM user_permission_overrides o
            LEFT JOIN users g ON g.id = o.granted_by
            WHERE o.user_id = %s
              AND (o.expires_at IS NULL OR o.expires_at > NOW())
            ORDER BY o.permission_key
            """,
            (user_id,),
        )
        overrides = [dict(row) for row in cursor.fetchall()]

        # Permissoes efetivas (formato aninhado + keys)
        permissions = get_user_permissions(
            user["profile"], user["username"], user_id=user["id"]
        )
        effective_keys = sorted(
            get_effective_permission_keys(user["id"], user["profile"], user["username"])
        )

        return jsonify({
            "user_id": user_id,
            "username": user["username"],
            "profile": user["profile"],
            "is_root": user["username"] == "admin",
            "permissions": permissions,
            "permission_keys": effective_keys,
            "overrides": overrides,
        })
    finally:
        release_db_connection(conn)


@users_bp.route("/api/users/<int:user_id>/permissions/overrides", methods=["POST"])
@require_admin
def create_permission_override(user_id):
    """
    Cria um override de permissao (GRANT ou DENY) para um usuario.

    Body JSON:
        permission_key (str): key no formato 'resource:action'
        effect (str): 'GRANT' ou 'DENY'
        reason (str): motivo do override (obrigatorio)
        expires_at (str, opcional): ISO 8601 datetime para expirar automaticamente
    """
    data = request.json or {}
    permission_key = data.get("permission_key", "").strip()
    effect = data.get("effect", "").strip().upper()
    reason = data.get("reason", "").strip()
    expires_at = data.get("expires_at")

    # Validacoes
    if not permission_key:
        return jsonify({"error": "Campo permission_key é obrigatório"}), 400
    if not is_valid_permission_key(permission_key):
        return jsonify({"error": f"Permission key inválida: {permission_key}"}), 400
    if effect not in VALID_EFFECTS:
        return jsonify({"error": f"Effect deve ser GRANT ou DENY"}), 400
    if not reason:
        return jsonify({"error": "Campo reason é obrigatório (auditoria)"}), 400

    conn = get_db()
    cursor = conn.cursor()
    try:
        # Bloquear override sobre root admin
        cursor.execute("SELECT username FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        if not user:
            return jsonify({"error": "Usuário não encontrado"}), 404
        if user["username"] == "admin":
            return jsonify({"error": "Root admin não aceita overrides"}), 403

        # Parse expires_at se fornecido
        parsed_expires = None
        if expires_at:
            try:
                parsed_expires = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                return jsonify({"error": "expires_at deve ser ISO 8601 válido"}), 400

        # Upsert: se ja existe override para essa key, atualiza
        cursor.execute(
            """
            INSERT INTO user_permission_overrides
                (user_id, permission_key, effect, granted_by, reason, expires_at, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (user_id, permission_key)
            DO UPDATE SET
                effect = EXCLUDED.effect,
                granted_by = EXCLUDED.granted_by,
                reason = EXCLUDED.reason,
                expires_at = EXCLUDED.expires_at,
                created_at = NOW()
            RETURNING id
            """,
            (user_id, permission_key, effect, request.current_user["id"], reason, parsed_expires),
        )
        override_id = cursor.fetchone()["id"]
        conn.commit()

        # Auditoria
        log_audit(
            action=f"permission_override_{effect.lower()}",
            user_id=request.current_user["id"],
            user_name=request.current_user["username"],
            details=(
                f"Override {effect} '{permission_key}' for user {user['username']} "
                f"(ID:{user_id}). Reason: {reason}"
                + (f" Expires: {expires_at}" if expires_at else "")
            ),
            status="success",
        )

        return jsonify({
            "success": True,
            "id": override_id,
            "message": f"Override {effect} criado para {permission_key}",
        }), 201

    except IntegrityError as e:
        conn.rollback()
        return jsonify({"error": f"Erro de integridade: {str(e)}"}), 400
    except Exception as e:
        conn.rollback()
        current_app.logger.error(f"Erro ao criar override: {e}")
        current_app.logger.error(traceback.format_exc())
        return jsonify({"error": "Erro ao criar override"}), 500
    finally:
        release_db_connection(conn)


@users_bp.route("/api/users/<int:user_id>/permissions/overrides/<int:override_id>", methods=["PUT"])
@require_admin
def update_permission_override(user_id, override_id):
    """
    Atualiza um override existente (effect, reason, expires_at).
    Nao permite alterar permission_key — delete + create para isso.
    """
    data = request.json or {}
    effect = data.get("effect", "").strip().upper()
    reason = data.get("reason", "").strip()
    expires_at = data.get("expires_at")

    if effect and effect not in VALID_EFFECTS:
        return jsonify({"error": "Effect deve ser GRANT ou DENY"}), 400
    if not reason:
        return jsonify({"error": "Campo reason é obrigatório (auditoria)"}), 400

    conn = get_db()
    cursor = conn.cursor()
    try:
        # Verificar se override pertence ao user informado
        cursor.execute(
            "SELECT id, permission_key FROM user_permission_overrides WHERE id = %s AND user_id = %s",
            (override_id, user_id),
        )
        existing = cursor.fetchone()
        if not existing:
            return jsonify({"error": "Override não encontrado"}), 404

        existing = dict(existing)

        # Montar update dinamico
        update_parts = ["reason = %s", "granted_by = %s"]
        values = [reason, request.current_user["id"]]

        if effect:
            update_parts.append("effect = %s")
            values.append(effect)

        if "expires_at" in data:
            if expires_at:
                try:
                    parsed = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                    update_parts.append("expires_at = %s")
                    values.append(parsed)
                except (ValueError, AttributeError):
                    return jsonify({"error": "expires_at deve ser ISO 8601 válido"}), 400
            else:
                update_parts.append("expires_at = NULL")

        values.append(override_id)
        cursor.execute(
            f"UPDATE user_permission_overrides SET {', '.join(update_parts)} WHERE id = %s",
            tuple(values),
        )
        conn.commit()

        log_audit(
            action="permission_override_update",
            user_id=request.current_user["id"],
            user_name=request.current_user["username"],
            details=(
                f"Updated override #{override_id} ({existing['permission_key']}) "
                f"for user_id {user_id}. Reason: {reason}"
            ),
            status="success",
        )

        return jsonify({"success": True, "message": "Override atualizado"})
    except Exception as e:
        conn.rollback()
        current_app.logger.error(f"Erro ao atualizar override: {e}")
        return jsonify({"error": "Erro ao atualizar override"}), 500
    finally:
        release_db_connection(conn)


@users_bp.route("/api/users/<int:user_id>/permissions/overrides/<int:override_id>", methods=["DELETE"])
@require_admin
def delete_permission_override(user_id, override_id):
    """Remove um override, fazendo o usuario cair de volta no perfil base."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT id, permission_key, effect FROM user_permission_overrides WHERE id = %s AND user_id = %s",
            (override_id, user_id),
        )
        existing = cursor.fetchone()
        if not existing:
            return jsonify({"error": "Override não encontrado"}), 404

        existing = dict(existing)
        cursor.execute("DELETE FROM user_permission_overrides WHERE id = %s", (override_id,))
        conn.commit()

        log_audit(
            action="permission_override_delete",
            user_id=request.current_user["id"],
            user_name=request.current_user["username"],
            details=(
                f"Deleted override #{override_id} ({existing['effect']} {existing['permission_key']}) "
                f"for user_id {user_id}"
            ),
            status="success",
        )

        return jsonify({"success": True, "message": "Override removido"})
    except Exception as e:
        conn.rollback()
        current_app.logger.error(f"Erro ao remover override: {e}")
        return jsonify({"error": "Erro ao remover override"}), 500
    finally:
        release_db_connection(conn)


@users_bp.route("/api/users/<int:user_id>/permissions/history", methods=["GET"])
@require_admin
def get_permission_override_history(user_id):
    """
    Retorna historico de overrides (incluindo expirados e removidos via audit log).
    Fonte: log de auditoria com action LIKE 'permission_override_%'.
    """
    # Como o audit log vai para file (nao banco), retornamos overrides atuais
    # incluindo expirados para historico. Overrides deletados ficam no audit.log.
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT o.id, o.permission_key, o.effect, o.reason, o.expires_at, o.created_at,
                   g.username AS granted_by_username,
                   CASE WHEN o.expires_at IS NOT NULL AND o.expires_at <= NOW() THEN TRUE ELSE FALSE END AS expired
            FROM user_permission_overrides o
            LEFT JOIN users g ON g.id = o.granted_by
            WHERE o.user_id = %s
            ORDER BY o.created_at DESC
            """,
            (user_id,),
        )
        history = [dict(row) for row in cursor.fetchall()]
        return jsonify({"user_id": user_id, "history": history})
    finally:
        release_db_connection(conn)
