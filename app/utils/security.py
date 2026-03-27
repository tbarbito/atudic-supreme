"""
Security utility module.
Handling password hashing, token generation and authentication decorators.
"""
import secrets
import hashlib
import bcrypt
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify
from app.database import get_db, release_db_connection

def hash_password(password):
    """Gera hash bcrypt para a senha. Retorna (hash, salt_placeholder) para manter compatibilidade."""
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt(rounds=12))
    return hashed.decode('utf-8'), 'bcrypt'

def verify_password(stored_password, stored_salt, provided_password):
    """Verifica senha — suporta bcrypt (novo) e SHA-256 legado para migração gradual."""
    if not stored_salt:
        return False
    if stored_salt == 'bcrypt':
        try:
            return bcrypt.checkpw(
                provided_password.encode('utf-8'),
                stored_password.encode('utf-8')
            )
        except Exception:
            return False
    # Fallback SHA-256 legado (senhas antigas ainda não migradas)
    hashed_password = hashlib.sha256(
        (provided_password + stored_salt).encode()
    ).hexdigest()
    return hashed_password == stored_password

def generate_session_token():
    """Gera token de sessão único"""
    return secrets.token_hex(32)

def require_auth(f):
    """Decorator para rotas que requerem autenticação (atualiza last_activity)"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.headers.get("Authorization")
        if not token:
            token = request.args.get("auth_token")

        if not token:
            return jsonify({"error": "Token não fornecido"}), 401

        conn = get_db()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                "SELECT * FROM users WHERE session_token = %s AND active = TRUE", (token,)
            )
            user = cursor.fetchone()

            if not user:
                return jsonify({"error": "Token inválido ou expirado"}), 401

            user_dict = dict(user)
            timeout_minutes = user_dict.get('session_timeout_minutes', 0)
            
            if timeout_minutes and timeout_minutes > 0 and user_dict.get('last_activity'):
                last_activity_time = user_dict['last_activity']
                # Se for string, converter para datetime
                if isinstance(last_activity_time, str):
                    last_activity_time = datetime.fromisoformat(last_activity_time.replace('Z', '+00:00'))
                # Remover timezone para comparação
                if hasattr(last_activity_time, 'tzinfo') and last_activity_time.tzinfo is not None:
                    last_activity_time = last_activity_time.replace(tzinfo=None)
                if datetime.now() > last_activity_time + timedelta(minutes=timeout_minutes):
                    cursor.execute("UPDATE users SET session_token = NULL WHERE id = %s", (user_dict['id'],))
                    conn.commit()
                    return jsonify({"error": "Sessão expirada por inatividade"}), 401
            
            # ATUALIZA A ÚLTIMA ATIVIDADE COM A CONEXÃO AINDA ABERTA
            cursor.execute("UPDATE users SET last_activity = %s WHERE id = %s", (datetime.now(), user_dict['id']))
            conn.commit()
            
            request.current_user = user_dict
        
        finally:
            release_db_connection(conn)

        return f(*args, **kwargs)

    return decorated_function

def require_auth_no_update(f):
    """
    Decorator para rotas que requerem autenticação MAS NÃO atualizam last_activity.
    Usado para keep-alive - apenas verifica se a sessão ainda é válida.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.headers.get("Authorization")
        if not token:
            token = request.args.get("auth_token")

        if not token:
            return jsonify({"error": "Token não fornecido"}), 401

        conn = get_db()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                "SELECT * FROM users WHERE session_token = %s AND active = TRUE", (token,)
            )
            user = cursor.fetchone()

            if not user:
                return jsonify({"error": "Token inválido ou expirado"}), 401

            user_dict = dict(user)
            timeout_minutes = user_dict.get('session_timeout_minutes', 0)
            
            # Verificar timeout SEM atualizar last_activity
            if timeout_minutes and timeout_minutes > 0 and user_dict.get('last_activity'):
                last_activity_time = user_dict['last_activity']
                if isinstance(last_activity_time, str):
                    last_activity_time = datetime.fromisoformat(last_activity_time.replace('Z', '+00:00'))
                if hasattr(last_activity_time, 'tzinfo') and last_activity_time.tzinfo is not None:
                    last_activity_time = last_activity_time.replace(tzinfo=None)
                if datetime.now() > last_activity_time + timedelta(minutes=timeout_minutes):
                    cursor.execute("UPDATE users SET session_token = NULL WHERE id = %s", (user_dict['id'],))
                    conn.commit()
                    return jsonify({"error": "Sessão expirada por inatividade"}), 401
            
            request.current_user = user_dict
        
        finally:
            release_db_connection(conn)

        return f(*args, **kwargs)

    return decorated_function

def require_admin(f):
    """Decorator para rotas que requerem perfil admin"""
    @wraps(f)
    @require_auth
    def decorated_function(*args, **kwargs):
        if request.current_user["profile"] != "admin":
            return jsonify({"error": "Acesso negado. Perfil admin necessário."}), 403
        return f(*args, **kwargs)

    return decorated_function

def require_operator(f):
    """Decorator para rotas que requerem perfil operator ou admin"""
    @wraps(f)
    @require_auth
    def decorated_function(*args, **kwargs):
        if request.current_user["profile"] not in ["admin", "operator"]:
            return jsonify({"error": "Acesso negado. Perfil operator ou admin necessário."}), 403
        return f(*args, **kwargs)
    return decorated_function

def require_api_key(f):
    """Decorator para rotas da API Externa (valida JWT/Token ou Header x-api-key)"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Suporta x-api-key ou Authorization: Bearer <key>
        token = request.headers.get("x-api-key")
        if not token:
            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1]

        if not token:
            return jsonify({"error": "Chave de API não fornecida nos headers x-api-key ou Authorization"}), 401

        conn = get_db()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                "SELECT * FROM api_keys WHERE key = %s AND is_active = TRUE", (token,)
            )
            api_key_record = cursor.fetchone()

            if not api_key_record:
                # Fallback: Caso o cliente esteja usando session token de admin?
                # Não, endpoints da API Externa são exclusivos de apikeys, mas podemos permitir auth normal.
                return jsonify({"error": "Chave de API inválida ou inativa"}), 401
                
            # Atualiza último uso
            cursor.execute("UPDATE api_keys SET last_used_at = %s WHERE id = %s", (datetime.now(), dict(api_key_record)['id']))
            conn.commit()
            
            # Populando user genérico para compatibilidade (a API key age como usuário do sistema que a criou)
            # ou simplesmente passa.
            request.api_key = dict(api_key_record)
        
        finally:
            release_db_connection(conn)

        return f(*args, **kwargs)

    return decorated_function


def check_protected_item(table_name, item_id):
    """
    Verifica se um item é protegido (is_protected = TRUE).
    Retorna True se protegido, False caso contrário.
    
    EXCEÇÃO: User 'admin' (root) ignora proteção.
    """
    # User admin é imune a proteções
    if hasattr(request, 'current_user') and request.current_user.get('username') == 'admin':
        return False
    
    allowed_tables = ['commands', 'pipelines', 'server_variables']
    if table_name not in allowed_tables:
        return False
    
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            f"SELECT is_protected FROM {table_name} WHERE id = %s",
            (item_id,)
        )
        result = cursor.fetchone()
        if result and result.get('is_protected'):
            return True
        return False
    finally:
        release_db_connection(conn)


def get_user_permissions(profile, username=None):
    """
    Retorna as permissões baseadas no perfil do usuário.
    Usado pelo frontend para controle de UI.
    
    EXCEÇÃO: User 'admin' (root) tem permissão total.
    """
    # User admin é o root supremo - permissão total
    if username == 'admin':
        return {
            'is_root': True,
            'users': {'view': True, 'create': True, 'edit': True, 'delete': True},
            'environments': {'view': True, 'create': True, 'edit': True, 'delete': True},
            'repositories': {'view': True, 'create': True, 'edit': True, 'delete': True, 'sync': True},
            'commands': {'view': True, 'create': True, 'edit': True, 'delete': True},
            'pipelines': {'view': True, 'create': True, 'edit': True, 'delete': True, 'execute': True, 'release': True},
            'schedules': {'view': True, 'create': True, 'edit': True, 'delete': True},
            'service_actions': {'view': True, 'create': True, 'edit': True, 'delete': True, 'execute': True},
            'variables': {'view': True, 'create': True, 'edit': True, 'delete': True},
            'services': {'view': True, 'create': True, 'edit': True, 'delete': True},
            'github_settings': {'view': True, 'edit': True},
            'can_edit_protected': True
        }
    
    permissions = {
        'admin': {
            'users': {'view': True, 'create': True, 'edit': True, 'delete': True},
            'environments': {'view': True, 'create': False, 'edit': False, 'delete': False},
            'repositories': {'view': True, 'create': True, 'edit': True, 'delete': True, 'sync': True},
            'commands': {'view': True, 'create': True, 'edit': True, 'delete': True},
            'pipelines': {'view': True, 'create': True, 'edit': True, 'delete': True, 'execute': True, 'release': True},
            'schedules': {'view': True, 'create': True, 'edit': True, 'delete': True},
            'service_actions': {'view': True, 'create': True, 'edit': True, 'delete': True, 'execute': True},
            'variables': {'view': True, 'create': True, 'edit': True, 'delete': True},
            'services': {'view': True, 'create': True, 'edit': True, 'delete': True},
            'github_settings': {'view': True, 'edit': True},
            'can_edit_protected': False
        },
        'operator': {
            'users': {'view': False, 'create': False, 'edit': False, 'delete': False},
            'environments': {'view': False, 'create': False, 'edit': False, 'delete': False},
            'repositories': {'view': True, 'create': True, 'edit': True, 'delete': False, 'sync': False},
            'commands': {'view': True, 'create': False, 'edit': False, 'delete': False},
            'pipelines': {'view': True, 'create': True, 'edit': True, 'delete': True, 'execute': True, 'release': True},
            'schedules': {'view': True, 'create': True, 'edit': True, 'delete': True},
            'service_actions': {'view': True, 'create': True, 'edit': True, 'delete': True, 'execute': True},
            'variables': {'view': True, 'create': True, 'edit': True, 'delete': True},
            'services': {'view': True, 'create': True, 'edit': True, 'delete': True},
            'github_settings': {'view': False, 'edit': False},
            'can_edit_protected': False
        },
        'viewer': {
            'users': {'view': False, 'create': False, 'edit': False, 'delete': False},
            'environments': {'view': False, 'create': False, 'edit': False, 'delete': False},
            'repositories': {'view': True, 'create': False, 'edit': False, 'delete': False, 'sync': False},
            'commands': {'view': False, 'create': False, 'edit': False, 'delete': False},
            'pipelines': {'view': True, 'create': False, 'edit': False, 'delete': False, 'execute': False, 'release': False},
            'schedules': {'view': True, 'create': False, 'edit': False, 'delete': False},
            'service_actions': {'view': False, 'create': False, 'edit': False, 'delete': False, 'execute': False},
            'variables': {'view': False, 'create': False, 'edit': False, 'delete': False},
            'services': {'view': False, 'create': False, 'edit': False, 'delete': False},
            'github_settings': {'view': False, 'edit': False},
            'can_edit_protected': False
        }
    }
    return permissions.get(profile, permissions['viewer'])
