"""
Authentication routes blueprint.
Handles login, logout, session management and first access checks.
"""
from flask import Blueprint, request, jsonify, current_app
from datetime import datetime, timedelta
import secrets

from app.database import get_db, release_db_connection
from app.utils.security import (
    verify_password, 
    hash_password, 
    generate_session_token, 
    require_auth,
    require_auth_no_update
)
from app.utils.rate_limiter import login_rate_limit, rate_limiter
from app.utils.audit import log_audit
from app.utils.crypto import TokenEncryption
from app.services.notifier import send_email_async

# Importação condicional/tardia para licença para evitar circular import se necessário
# Mas license_system parece ser um módulo independente na raiz/PYTHONPATH
# No app.py era: from license_system import ...
# Se license_system estiver na raiz, deve funcionar desde que PYTHONPATH inclua raiz.
# Assumindo que sim.

auth_bp = Blueprint('auth', __name__)

@auth_bp.route("/api/login", methods=["POST"])
@login_rate_limit(max_attempts=5, window_seconds=300)
def login():
    """Login com auditoria completa"""
    data = request.json
    username = data.get("username")
    password = data.get("password")
    force_login = data.get("force", False)

    if not username or not password:
        return jsonify({"error": "Usuário e senha são obrigatórios"}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = %s AND active = TRUE", (username,))
    user = cursor.fetchone()

    # Validação de credenciais
    if not user or not verify_password(user["password"], user["password_salt"], password):
        release_db_connection(conn)
        current_app.logger.warning(f"Failed login attempt for user: {username} from {request.remote_addr}")
        log_audit(
            action='login_failed',
            user_id=0,
            user_name=username,
            details=f"Failed login attempt from {request.remote_addr}",
            status='failure'
        )
        return jsonify({"error": "Usuário ou senha inválidos"}), 401

    # ============================================================
    # Licença desabilitada no BiizHubOps (modo demo)
    # ============================================================

    # Verifica sessão única - MAS considera timeout expirado
    if user["session_token"] and not force_login:
        session_expired = False
        
        try:
            timeout_minutes = user["session_timeout_minutes"] if user["session_timeout_minutes"] else 0
        except (KeyError, TypeError):
            timeout_minutes = 0
        
        try:
            last_activity = user["last_activity"]
        except (KeyError, TypeError):
            last_activity = None
        
        # Se tem timeout configurado, verificar se a sessão anterior expirou
        if timeout_minutes and timeout_minutes > 0 and last_activity:
            try:
                # Se last_activity é string, converter para datetime
                if isinstance(last_activity, str):
                    last_activity = datetime.fromisoformat(last_activity.replace('Z', '+00:00'))
                
                # Remover timezone para comparação (se tiver)
                if hasattr(last_activity, 'tzinfo') and last_activity.tzinfo is not None:
                    last_activity = last_activity.replace(tzinfo=None)
                
                # Verificar se expirou
                if datetime.now() > last_activity + timedelta(minutes=timeout_minutes):
                    session_expired = True
                    current_app.logger.info(f"Session timeout detected for user {username}, allowing new login")
                    # Limpar token expirado
                    cursor.execute("UPDATE users SET session_token = NULL WHERE id = %s", (user["id"],))
                    conn.commit()
            except Exception as e:
                current_app.logger.warning(f"Error checking session timeout: {e}")
        
        # Só bloquear se sessão NÃO expirou
        if not session_expired:
            release_db_connection(conn)
            current_app.logger.info(f"User {username} tried to login with active session")
            return jsonify({
                "error": f"O usuário '{username}' já possui uma sessão ativa."
            }), 409

    # Gerar novo token de sessão
    token = generate_session_token()
    now = datetime.now()

    cursor.execute(
        """
        UPDATE users 
        SET session_token = %s, last_login = %s, last_activity = %s
        WHERE id = %s
        """,
        (token, now, now, user["id"])
    )

    conn.commit()

    # Buscar ambientes vinculados ao usuário
    environment_ids = []
    if user["username"] != "admin":
        cursor.execute(
            "SELECT environment_id FROM user_environments WHERE user_id = %s",
            (user["id"],)
        )
        environment_ids = [row["environment_id"] for row in cursor.fetchall()]

    release_db_connection(conn)

    # Limpa rate limit após login bem-sucedido
    rate_limiter.clear_user(f"login_{request.remote_addr}")

    # AUDITORIA: Login bem-sucedido
    current_app.logger.info(f"Successful login: {username} from {request.remote_addr}")
    log_audit(
        action='login_success',
        user_id=user["id"],
        user_name=username,
        details=f"Login from {request.remote_addr}",
        status='success'
    )

    return jsonify({
        "success": True,
        "token": token,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "name": user["name"],
            "email": user["email"],
            "profile": user["profile"],
            "lastLogin": now,
            "environment_ids": environment_ids,
        },
    })


@auth_bp.route("/api/logout", methods=["POST"])
@require_auth
def logout():
    """Endpoint de logout"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE users SET session_token = NULL WHERE id = %s
    """,
        (request.current_user["id"],),
    )
    conn.commit()
    release_db_connection(conn)

    return jsonify({"success": True, "message": "Logout realizado com sucesso"})

@auth_bp.route("/api/session/keep-alive", methods=["POST"])
@require_auth_no_update
def session_keep_alive():
    """
    Mantém a sessão ativa ou verifica se expirou.
    Diferente de outras rotas, esta NÃO atualiza o last_activity automaticamente pelo decorator,
    mas se o frontend enviar, podemos atualizar se quisermos?
    
    Original app.py: Não faz nada além de retornar 'ok' se passar pelo decorator.
    O decorator require_auth_no_update não atualiza last_activity.
    Isso serve para polling passivo sem resetar o timeout de inatividade?
    Sim, parece ser o objetivo. Apenas checa se token ainda é válido.
    """
    return jsonify({"status": "active", "message": "Session is valid"})

# =====================================================================
# PRIMEIRO ACESSO
# =====================================================================

@auth_bp.route("/api/first-access/check", methods=["GET"])
def check_first_access():
    """
    Verifica se é o primeiro acesso (não existe admin além do root).
    Rota pública - não requer autenticação.
    """
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Conta admins que NÃO são o root (username != 'admin')
        cursor.execute("""
            SELECT COUNT(*) as count FROM users 
            WHERE profile = 'admin' AND username != 'admin' AND active = TRUE
        """)
        result = cursor.fetchone()
        release_db_connection(conn)
        
        admin_count = result['count'] if result else 0
        is_first_access = admin_count == 0
        
        return jsonify({
            "first_access": is_first_access,
            "message": "Nenhum administrador configurado" if is_first_access else "Sistema já configurado"
        })
        
    except Exception as e:
        current_app.logger.error(f"Erro ao verificar primeiro acesso: {e}")
        return jsonify({"first_access": False, "error": str(e)}), 500


@auth_bp.route("/api/first-access/create", methods=["POST"])
def create_first_admin():
    """
    Cria o primeiro usuário administrador do cliente.
    Só funciona se não existir nenhum admin além do root.
    Rota pública - não requer autenticação.
    """
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Verificar se realmente é primeiro acesso
        cursor.execute("""
            SELECT COUNT(*) as count FROM users 
            WHERE profile = 'admin' AND username != 'admin' AND active = TRUE
        """)
        result = cursor.fetchone()
        
        if result and result['count'] > 0:
            release_db_connection(conn)
            return jsonify({
                "error": "Já existe um administrador configurado no sistema"
            }), 400
        
        # Validar dados recebidos
        data = request.json
        required_fields = ["username", "name", "email", "password"]
        
        for field in required_fields:
            if not data.get(field):
                release_db_connection(conn)
                return jsonify({"error": f"Campo {field} é obrigatório"}), 400
        
        # Validar que não está tentando criar o user 'admin'
        if data["username"].lower() == "admin":
            release_db_connection(conn)
            return jsonify({"error": "Este nome de usuário não está disponível"}), 400
        
        # Validar senha mínima
        if len(data["password"]) < 6:
            release_db_connection(conn)
            return jsonify({"error": "A senha deve ter no mínimo 6 caracteres"}), 400
        
        # Verificar se username já existe
        cursor.execute("SELECT id FROM users WHERE username = %s", (data["username"],))
        if cursor.fetchone():
            release_db_connection(conn)
            return jsonify({"error": "Este nome de usuário já está em uso"}), 400
        
        # Verificar se email já existe
        cursor.execute("SELECT id FROM users WHERE email = %s", (data["email"],))
        if cursor.fetchone():
            release_db_connection(conn)
            return jsonify({"error": "Este email já está em uso"}), 400
            
        # Criar usuário
        hashed, salt = hash_password(data["password"])
        
        cursor.execute("""
            INSERT INTO users (username, password, password_salt, name, email, profile, active, created_at)
            VALUES (%s, %s, %s, %s, %s, 'admin', TRUE, %s)
            RETURNING id
        """, (data["username"], hashed, salt, data["name"], data["email"], datetime.now()))
        
        user_id = cursor.fetchone()['id']

        # Vincular o primeiro admin a todos os ambientes
        cursor.execute("""
            INSERT INTO user_environments (user_id, environment_id)
            SELECT %s, id FROM environments
            ON CONFLICT DO NOTHING
        """, (user_id,))

        conn.commit()
        release_db_connection(conn)

        log_audit(
            action='create_first_admin',
            user_id=user_id,
            user_name=data["username"],
            details=f"First admin created via first-access setup",
            status='success'
        )
        
        return jsonify({
            "success": True,
            "message": "Administrador criado com sucesso! Você já pode fazer login."
        })
        
    except Exception as e:
        current_app.logger.error(f"Erro ao criar primeiro admin: {e}")
        return jsonify({"error": str(e)}), 500


# =====================================================================
# RECUPERAÇÃO DE SENHA
# =====================================================================

@auth_bp.route("/api/forgot-password", methods=["POST"])
@login_rate_limit(max_attempts=3, window_seconds=300)
def forgot_password():
    """
    Solicita recuperação de senha via e-mail.
    Rota pública - não requer autenticação.
    Sempre retorna sucesso para não revelar se o e-mail existe.
    """
    data = request.json
    email = (data.get("email") or "").strip().lower()

    if not email:
        return jsonify({"error": "E-mail é obrigatório"}), 400

    # Resposta padrão (sempre a mesma, independente do resultado)
    success_response = jsonify({
        "success": True,
        "message": "Se o e-mail estiver cadastrado, você receberá as instruções de recuperação."
    })

    try:
        conn = get_db()
        cursor = conn.cursor()

        # Buscar TODOS os usuários ativos com este email (excluir user root 'admin')
        cursor.execute(
            "SELECT id, username, name, email FROM users WHERE LOWER(email) = %s AND active = TRUE AND username != 'admin'",
            (email,)
        )
        users = cursor.fetchall()

        if not users:
            release_db_connection(conn)
            current_app.logger.info(f"Password reset requested for unknown/admin email: {email}")
            return success_response

        # Gerar token exclusivo para cada usuário e salvar no banco
        reset_expires = datetime.now() + timedelta(minutes=30)
        user_tokens = []

        for user in users:
            reset_token = secrets.token_urlsafe(32)
            cursor.execute(
                "UPDATE users SET reset_token = %s, reset_token_expires = %s WHERE id = %s",
                (reset_token, reset_expires, user["id"])
            )
            user_tokens.append({
                "id": user["id"],
                "username": user["username"],
                "name": user["name"],
                "token": reset_token
            })

        conn.commit()
        release_db_connection(conn)

        # Montar blocos HTML com código de cada usuário
        users_html = ""
        for ut in user_tokens:
            users_html += f"""
            <div style="background: #f0f4f8; border-radius: 8px; padding: 15px; margin: 10px 0;">
                <p style="margin: 0 0 8px 0; font-size: 14px;">👤 Usuário: <strong>{ut['username']}</strong> ({ut['name']})</p>
                <div style="background: #fff; border-radius: 6px; padding: 10px; text-align: center;">
                    <span style="font-size: 18px; font-weight: bold; letter-spacing: 2px; color: #1a73e8;">{ut['token']}</span>
                </div>
            </div>
            """

        from app.services.notifier import email_base_template

        # Blocos de usuário em tema claro
        users_html_light = ""
        for ut in user_tokens:
            users_html_light += f"""
            <div style="background: #f0f4f8; border-radius: 8px; padding: 14px; margin: 10px 0; border: 1px solid #e0e0e0;">
                <p style="margin: 0 0 8px 0; font-size: 14px; color: #555;">Usuário: <strong style="color: #333;">{ut['username']}</strong> ({ut['name']})</p>
                <div style="background: #fff; border-radius: 6px; padding: 10px; text-align: center; border: 1px solid #e0e0e0;">
                    <span style="font-size: 20px; font-weight: bold; letter-spacing: 3px; color: #1565c0;">{ut['token']}</span>
                </div>
            </div>
            """

        body_content = f"""
            <h3 style="color: #1565c0; margin: 0 0 16px 0; border-bottom: 2px solid #1565c0; padding-bottom: 10px;">Recuperação de Senha</h3>
            <p>Recebemos uma solicitação de recuperação de senha no <strong>BiizHubOps</strong>.</p>
            <p>{'Encontramos as seguintes contas vinculadas ao seu e-mail. Use o código correspondente:' if len(user_tokens) > 1 else 'Use o código abaixo para redefinir sua senha:'}</p>
            {users_html_light}
            <p style="color: #666; font-size: 13px;">{'Os códigos expiram' if len(user_tokens) > 1 else 'Este código expira'} em <strong>30 minutos</strong>.</p>
            <p style="color: #999; font-size: 12px;">Se você não solicitou esta recuperação, ignore este e-mail.</p>
        """

        body_html = email_base_template('Segurança', '#1565c0', body_content)

        send_email_async(
            [users[0]["email"]],
            "BiizHubOps — Recuperação de Senha",
            body_html
        )

        usernames = ", ".join([ut["username"] for ut in user_tokens])
        current_app.logger.info(f"Password reset tokens generated for users: {usernames}")
        for ut in user_tokens:
            log_audit(
                action='password_reset_requested',
                user_id=ut["id"],
                user_name=ut["username"],
                details=f"Password reset requested from {request.remote_addr}",
                status='success'
            )

        return success_response

    except Exception as e:
        current_app.logger.error(f"Erro ao processar recuperação de senha: {e}")
        return success_response


@auth_bp.route("/api/reset-password", methods=["POST"])
@login_rate_limit(max_attempts=5, window_seconds=300)
def reset_password():
    """
    Redefine a senha usando o token de recuperação.
    Rota pública - não requer autenticação.
    """
    data = request.json
    token = (data.get("token") or "").strip()
    new_password = data.get("new_password") or ""

    if not token or not new_password:
        return jsonify({"error": "Token e nova senha são obrigatórios"}), 400

    if len(new_password) < 6:
        return jsonify({"error": "A senha deve ter no mínimo 6 caracteres"}), 400

    try:
        conn = get_db()
        cursor = conn.cursor()

        # Buscar usuário pelo token válido (não expirado)
        cursor.execute(
            "SELECT id, username FROM users WHERE reset_token = %s AND reset_token_expires > %s AND active = TRUE",
            (token, datetime.now())
        )
        user = cursor.fetchone()

        if not user:
            release_db_connection(conn)
            current_app.logger.warning(f"Invalid/expired reset token attempt from {request.remote_addr}")
            return jsonify({"error": "Token inválido ou expirado. Solicite uma nova recuperação."}), 400

        # Gerar novo hash de senha
        hashed, salt = hash_password(new_password)

        # Atualizar senha e limpar token + sessão ativa
        cursor.execute(
            """
            UPDATE users
            SET password = %s, password_salt = %s,
                reset_token = NULL, reset_token_expires = NULL,
                session_token = NULL
            WHERE id = %s
            """,
            (hashed, salt, user["id"])
        )
        conn.commit()
        release_db_connection(conn)

        current_app.logger.info(f"Password reset completed for user: {user['username']}")
        log_audit(
            action='password_reset_completed',
            user_id=user["id"],
            user_name=user["username"],
            details=f"Password reset completed from {request.remote_addr}",
            status='success'
        )

        return jsonify({
            "success": True,
            "message": "Senha redefinida com sucesso! Faça login com sua nova senha."
        })

    except Exception as e:
        current_app.logger.error(f"Erro ao redefinir senha: {e}")
        return jsonify({"error": "Erro ao redefinir senha. Tente novamente."}), 500
