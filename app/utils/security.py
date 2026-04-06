"""
Security utility module.
Handling password hashing, token generation and authentication decorators.
"""
import os
import secrets
import hashlib
import bcrypt
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify, g
from app.database import get_db, release_db_connection
from app.utils.permissions import (
    get_base_permissions,
    resolve_effective_keys,
    keys_to_nested_dict,
    is_valid_permission_key,
    VALID_PERMISSION_KEYS,
)


def _rbac_overrides_enabled():
    """Feature flag para desabilitar overrides em caso de regressao.

    Env var RBAC_OVERRIDES_ENABLED (default 'true'). Se 'false', o sistema
    ignora a tabela user_permission_overrides e usa apenas o perfil base.
    """
    return os.getenv("RBAC_OVERRIDES_ENABLED", "true").lower() not in ("false", "0", "no")

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


def _load_user_overrides(user_id):
    """
    Carrega overrides ativos de um usuario (exclui expirados).

    Returns:
        list[dict]: [{permission_key, effect}, ...]
    """
    if not _rbac_overrides_enabled() or not user_id:
        return []

    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT permission_key, effect
            FROM user_permission_overrides
            WHERE user_id = %s
              AND (expires_at IS NULL OR expires_at > NOW())
            """,
            (user_id,),
        )
        return [dict(row) for row in cursor.fetchall()]
    except Exception:
        # Tabela pode nao existir se migration 022 nao rodou ainda — degrade gracefully
        return []
    finally:
        release_db_connection(conn)


def _compute_effective_keys(user_id, profile, username):
    """
    Calcula o set de permission_keys efetivas, aplicando overrides.
    Root admin (username='admin') recebe todas as keys do catalogo.
    """
    if username == "admin":
        return set(VALID_PERMISSION_KEYS)

    overrides = _load_user_overrides(user_id)
    return resolve_effective_keys(profile, overrides)


def get_effective_permission_keys(user_id, profile, username):
    """
    API publica para obter permission_keys efetivas de um usuario.

    Returns:
        set[str]: keys no formato 'resource:action'
    """
    return _compute_effective_keys(user_id, profile, username)


def has_permission(permission_key, user=None):
    """
    Verifica se um usuario possui uma permission_key.

    Ordem de resolucao:
    1. Root admin (username='admin')              -> ALLOW
    2. Usuario inativo                            -> DENY
    3. DENY explicito no override                 -> DENY
    4. GRANT explicito no override                -> ALLOW
    5. Permissao presente no perfil               -> ALLOW
    6. Default                                    -> DENY

    Args:
        permission_key (str): key no formato 'resource:action'
        user (dict, opcional): dict do usuario. Se None, usa request.current_user

    Returns:
        bool
    """
    if not is_valid_permission_key(permission_key):
        return False

    if user is None:
        user = getattr(request, "current_user", None)
    if not user:
        return False

    if not user.get("active", True):
        return False

    username = user.get("username")
    if username == "admin":
        return True

    # Cache por request para evitar N queries quando decorator + checks internos
    # chamam has_permission() varias vezes na mesma requisicao.
    try:
        cache = g.setdefault("_rbac_keys_cache", {})
    except RuntimeError:
        # Fora do contexto de request (ex: background tasks)
        cache = {}

    user_id = user.get("id")
    cache_key = user_id
    if cache_key in cache:
        effective = cache[cache_key]
    else:
        effective = _compute_effective_keys(user_id, user.get("profile"), username)
        cache[cache_key] = effective

    return permission_key in effective


def require_permission(permission_key):
    """
    Decorator para rotas que exigem uma permission_key granular.

    Uso:
        @require_permission('pipelines:execute')
        def run_pipeline(...): ...

    Aplica @require_auth automaticamente antes de validar a permissao.
    """
    def decorator(f):
        @wraps(f)
        @require_auth
        def decorated_function(*args, **kwargs):
            if not has_permission(permission_key, request.current_user):
                return jsonify({
                    "error": "Acesso negado.",
                    "required_permission": permission_key,
                }), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def get_user_permissions(profile, username=None, user_id=None):
    """
    Retorna as permissoes em formato aninhado {resource: {action: bool}}.
    Usado pelo frontend (canPerformAction) e endpoint /api/me/permissions.

    Aplica a resolucao efetiva: perfil base + overrides (GRANT/DENY).

    EXCEPCAO: User 'admin' (root) tem permissao total.

    Args:
        profile (str): perfil base do usuario
        username (str, opcional): usado para detectar root
        user_id (int, opcional): necessario para aplicar overrides. Se None,
                                 retorna apenas as permissoes do perfil base.

    Returns:
        dict: estrutura aninhada {resource: {action: bool}, ...}
              + flags 'is_root' e 'can_edit_protected'
    """
    is_root = username == "admin"

    if is_root:
        keys = set(VALID_PERMISSION_KEYS)
    else:
        # Se user_id nao foi fornecido, opera sem overrides (compat com chamadas antigas)
        if user_id is None:
            keys = set(get_base_permissions(profile))
        else:
            overrides = _load_user_overrides(user_id)
            keys = resolve_effective_keys(profile, overrides)

    return keys_to_nested_dict(
        keys,
        is_root=is_root,
        can_edit_protected=is_root,  # preserva comportamento legado: so root edita protegidos
    )
