# =============================================================================
# 🔒 AtuDIC DEVOPS - MELHORIAS DE SEGURANÇA
# =============================================================================
# Este arquivo contém todas as melhorias de segurança para o sistema
# =============================================================================

from functools import wraps
from flask import request, jsonify
from datetime import datetime, timedelta
import hashlib
import re
from collections import defaultdict
from threading import Lock
import secrets

# =============================================================================
# RATE LIMITING
# =============================================================================

class RateLimiter:
    """
    Limita número de requisições por IP para prevenir ataques de força bruta
    """
    def __init__(self):
        self.requests = defaultdict(list)
        self.lock = Lock()
        
    def is_rate_limited(self, identifier, max_requests=100, window_seconds=60):
        """
        Verifica se o identificador (IP/usuário) excedeu o limite de requisições
        """
        with self.lock:
            now = datetime.now()
            window_start = now - timedelta(seconds=window_seconds)
            
            # Remover requisições antigas
            self.requests[identifier] = [
                req_time for req_time in self.requests[identifier]
                if req_time > window_start
            ]
            
            # Verificar se excedeu o limite
            if len(self.requests[identifier]) >= max_requests:
                return True
            
            # Adicionar nova requisição
            self.requests[identifier].append(now)
            return False

# Instância global do rate limiter
rate_limiter = RateLimiter()

def rate_limit(max_requests=100, window_seconds=60):
    """
    Decorator para aplicar rate limiting em rotas
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Usar IP como identificador
            identifier = request.remote_addr
            
            if rate_limiter.is_rate_limited(identifier, max_requests, window_seconds):
                return jsonify({
                    "error": "Muitas requisições. Tente novamente em alguns segundos.",
                    "retry_after": window_seconds
                }), 429
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# =============================================================================
# SECURITY HEADERS
# =============================================================================

def add_security_headers(response):
    """
    Adiciona headers de segurança às respostas HTTP
    """
    # Previne clickjacking
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    
    # Previne MIME-sniffing
    response.headers['X-Content-Type-Options'] = 'nosniff'
    
    # XSS Protection
    response.headers['X-XSS-Protection'] = '1; mode=block'
    
    # Content Security Policy
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
        "font-src 'self' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com data:; "
        "img-src 'self' data: https:; "
        "connect-src 'self' https://api.github.com;"
    )
    
    # Strict Transport Security (HTTPS)
    # Descomente quando tiver HTTPS configurado
    # response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    
    # Referrer Policy
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    
    # Permissions Policy
    response.headers['Permissions-Policy'] = (
        "geolocation=(), "
        "microphone=(), "
        "camera=(), "
        "payment=(), "
        "usb=()"
    )
    
    return response

# =============================================================================
# PASSWORD POLICY
# =============================================================================

class PasswordPolicy:
    """
    Valida senhas de acordo com política de segurança
    """
    @staticmethod
    def validate(password):
        """
        Valida senha conforme política:
        - Mínimo 8 caracteres
        - Pelo menos 1 letra maiúscula
        - Pelo menos 1 letra minúscula
        - Pelo menos 1 número
        - Pelo menos 1 caractere especial
        """
        errors = []
        
        if len(password) < 8:
            errors.append("Senha deve ter no mínimo 8 caracteres")
        
        if not re.search(r"[A-Z]", password):
            errors.append("Senha deve conter pelo menos 1 letra maiúscula")
        
        if not re.search(r"[a-z]", password):
            errors.append("Senha deve conter pelo menos 1 letra minúscula")
        
        if not re.search(r"\d", password):
            errors.append("Senha deve conter pelo menos 1 número")
        
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
            errors.append("Senha deve conter pelo menos 1 caractere especial")
        
        # Verificar senhas comuns
        common_passwords = [
            "password", "123456", "12345678", "qwerty", "abc123",
            "password123", "admin", "letmein", "welcome", "monkey"
        ]
        if password.lower() in common_passwords:
            errors.append("Senha muito comum. Escolha uma senha mais segura")
        
        return len(errors) == 0, errors
    
    @staticmethod
    def check_strength(password):
        """
        Retorna força da senha (0-100)
        """
        strength = 0
        
        # Comprimento
        if len(password) >= 8:
            strength += 20
        if len(password) >= 12:
            strength += 10
        if len(password) >= 16:
            strength += 10
        
        # Complexidade
        if re.search(r"[a-z]", password):
            strength += 15
        if re.search(r"[A-Z]", password):
            strength += 15
        if re.search(r"\d", password):
            strength += 15
        if re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
            strength += 15
        
        return min(strength, 100)

# =============================================================================
# CSRF PROTECTION
# =============================================================================

class CSRFProtection:
    """
    Proteção contra Cross-Site Request Forgery
    """
    @staticmethod
    def generate_token():
        """
        Gera token CSRF único
        """
        return secrets.token_urlsafe(32)
    
    @staticmethod
    def validate_token(session_token, request_token):
        """
        Valida token CSRF
        """
        if not session_token or not request_token:
            return False
        return secrets.compare_digest(session_token, request_token)

# =============================================================================
# INPUT VALIDATION
# =============================================================================

class InputValidator:
    """
    Validação e sanitização de inputs
    """
    @staticmethod
    def sanitize_string(text, max_length=500):
        """
        Sanitiza string removendo caracteres perigosos
        """
        if not text:
            return ""
        
        # Limitar comprimento
        text = str(text)[:max_length]
        
        # Remover caracteres perigosos
        dangerous_chars = ['<', '>', '"', "'", '&', ';', '|', '`', '$']
        for char in dangerous_chars:
            text = text.replace(char, '')
        
        return text.strip()
    
    @staticmethod
    def validate_email(email):
        """
        Valida formato de email
        """
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None
    
    @staticmethod
    def validate_username(username):
        """
        Valida username (apenas alfanumérico e underscore)
        """
        pattern = r'^[a-zA-Z0-9_]{3,30}$'
        return re.match(pattern, username) is not None
    
    @staticmethod
    def validate_sql_safe(text):
        """
        Verifica se texto não contém comandos SQL perigosos
        """
        dangerous_patterns = [
            r'DROP\s+TABLE',
            r'DELETE\s+FROM',
            r'TRUNCATE\s+TABLE',
            r'ALTER\s+TABLE',
            r'CREATE\s+TABLE',
            r'EXEC\(',
            r'EXECUTE\(',
            r'UNION\s+SELECT',
            r'INSERT\s+INTO',
            r'UPDATE\s+.*\s+SET',
            r'--',
            r'/\*',
            r'\*/',
            r'xp_cmdshell'
        ]
        
        text_upper = text.upper()
        for pattern in dangerous_patterns:
            if re.search(pattern, text_upper, re.IGNORECASE):
                return False
        return True

# =============================================================================
# SESSION SECURITY
# =============================================================================

class SessionSecurity:
    """
    Melhorias de segurança para sessões
    """
    @staticmethod
    def generate_session_id():
        """
        Gera ID de sessão seguro
        """
        return secrets.token_urlsafe(64)
    
    @staticmethod
    def hash_session_id(session_id, secret_key):
        """
        Hash do session ID para armazenamento
        """
        return hashlib.sha256(
            f"{session_id}{secret_key}".encode()
        ).hexdigest()
    
    @staticmethod
    def is_session_expired(last_activity, timeout_minutes=30):
        """
        Verifica se sessão expirou
        """
        if not last_activity:
            return True
        
        now = datetime.now()
        if isinstance(last_activity, str):
            last_activity = datetime.fromisoformat(last_activity)
        
        return (now - last_activity).seconds > (timeout_minutes * 60)

# =============================================================================
# AUDIT LOGGING
# =============================================================================

class AuditLogger:
    """
    Sistema de auditoria para ações sensíveis
    """
    SENSITIVE_ACTIONS = [
        'login',
        'logout',
        'password_change',
        'user_create',
        'user_delete',
        'permission_change',
        'config_change',
        'pipeline_execute',
        'command_execute'
    ]
    
    @staticmethod
    def should_audit(action):
        """
        Verifica se ação deve ser auditada
        """
        return action in AuditLogger.SENSITIVE_ACTIONS
    
    @staticmethod
    def create_audit_entry(action, user_id, user_name, details, ip_address):
        """
        Cria entrada de auditoria
        """
        return {
            'timestamp': datetime.now().isoformat(),
            'action': action,
            'user_id': user_id,
            'user_name': user_name,
            'ip_address': ip_address,
            'details': details,
            'hash': hashlib.sha256(
                f"{action}{user_id}{datetime.now().isoformat()}".encode()
            ).hexdigest()
        }

# =============================================================================
# IP WHITELIST/BLACKLIST
# =============================================================================

class IPFilter:
    """
    Filtro de IPs permitidos/bloqueados
    """
    def __init__(self):
        self.whitelist = set()
        self.blacklist = set()
    
    def add_to_whitelist(self, ip):
        """Adiciona IP à whitelist"""
        self.whitelist.add(ip)
    
    def add_to_blacklist(self, ip):
        """Adiciona IP à blacklist"""
        self.blacklist.add(ip)
    
    def is_allowed(self, ip):
        """Verifica se IP é permitido"""
        # Se está na blacklist, bloqueia
        if ip in self.blacklist:
            return False
        
        # Se whitelist está vazia, permite todos (exceto blacklist)
        if not self.whitelist:
            return True
        
        # Se whitelist tem IPs, apenas permite os que estão nela
        return ip in self.whitelist

# Instância global do filtro de IP
ip_filter = IPFilter()

# =============================================================================
# INSTRUÇÕES DE USO
# =============================================================================

"""
COMO APLICAR AS MELHORIAS DE SEGURANÇA NO app.py:

1. IMPORTAR O MÓDULO:
   from security_enhancements import (
       rate_limit, add_security_headers, PasswordPolicy,
       InputValidator, SessionSecurity, AuditLogger, ip_filter
   )

2. ADICIONAR SECURITY HEADERS:
   @app.after_request
   def security_headers(response):
       return add_security_headers(response)

3. APLICAR RATE LIMITING:
   # Login (5 tentativas por minuto)
   @app.route("/api/login", methods=["POST"])
   @rate_limit(max_requests=5, window_seconds=60)
   def login():
       ...
   
   # Rotas normais (100 requisições por minuto)
   @app.route("/api/users", methods=["GET"])
   @rate_limit(max_requests=100, window_seconds=60)
   def get_users():
       ...

4. VALIDAR SENHAS:
   password = request.json.get("password")
   is_valid, errors = PasswordPolicy.validate(password)
   if not is_valid:
       return jsonify({"error": errors}), 400

5. SANITIZAR INPUTS:
   username = InputValidator.sanitize_string(request.json.get("username"))
   
   if not InputValidator.validate_username(username):
       return jsonify({"error": "Username inválido"}), 400

6. VERIFICAR IP:
   if not ip_filter.is_allowed(request.remote_addr):
       return jsonify({"error": "IP bloqueado"}), 403

7. AUDITORIA:
   if AuditLogger.should_audit('login'):
       audit_entry = AuditLogger.create_audit_entry(
           action='login',
           user_id=user['id'],
           user_name=user['username'],
           details='Login bem-sucedido',
           ip_address=request.remote_addr
       )
       # Salvar no banco de dados
"""
