"""
Rate limiting utility module.

Sistema de rate limiting baseado em memória com cleanup automático.
Compatível com gunicorn+gevent (single process, múltiplas greenlets).
"""
import time
from collections import defaultdict
from threading import Lock
from functools import wraps
from flask import request, jsonify

# Intervalo mínimo entre cleanups (evita overhead em alta frequência)
_CLEANUP_INTERVAL = 300  # 5 minutos


class RateLimiter:
    """
    Rate limiter in-memory com cleanup automático de registros expirados.
    Thread-safe via Lock.
    """

    def __init__(self):
        self.requests = defaultdict(list)
        self.lock = Lock()
        self._last_cleanup = time.time()

    def is_allowed(self, identifier, max_requests, window_seconds):
        """
        Verifica se requisição é permitida dentro da janela de tempo.

        Args:
            identifier: chave única (IP, user_id, endpoint)
            max_requests: máximo de requisições na janela
            window_seconds: tamanho da janela em segundos

        Returns:
            tuple: (is_allowed, retry_after_seconds)
        """
        with self.lock:
            now = time.time()

            # Cleanup periódico de identificadores inativos
            if now - self._last_cleanup > _CLEANUP_INTERVAL:
                self._cleanup(now)

            # Remove requisições fora da janela para este identificador
            self.requests[identifier] = [
                req_time for req_time in self.requests[identifier]
                if now - req_time < window_seconds
            ]

            # Verifica limite
            if len(self.requests[identifier]) >= max_requests:
                oldest_request = min(self.requests[identifier])
                retry_after = window_seconds - (now - oldest_request)
                return False, int(retry_after) + 1

            # Registra nova requisição
            self.requests[identifier].append(now)
            return True, 0

    def clear_user(self, identifier):
        """Remove histórico de um usuário/IP."""
        with self.lock:
            self.requests.pop(identifier, None)

    def _cleanup(self, now):
        """Remove identificadores sem requisições recentes (> 1h)."""
        stale_keys = [
            key for key, timestamps in self.requests.items()
            if not timestamps or (now - max(timestamps)) > 3600
        ]
        for key in stale_keys:
            del self.requests[key]
        self._last_cleanup = now


# Instância global
rate_limiter = RateLimiter()

def rate_limit(max_requests=60, window_seconds=60):
    """
    Decorator para aplicar rate limiting em rotas.
    
    Uso:
        @rate_limit(max_requests=5, window_seconds=60)  # 5 req/min
        def my_route():
            ...
    """
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            # Identifica usuário por IP + endpoint (rate limit por rota)
            identifier = request.remote_addr

            # Se autenticado, usa user_id ao invés de IP
            if hasattr(request, 'current_user') and request.current_user:
                identifier = f"user_{request.current_user['id']}"

            # Inclui endpoint no identificador para limites independentes por rota
            identifier = f"{identifier}:{request.endpoint or request.path}"

            # Verifica rate limit
            allowed, retry_after = rate_limiter.is_allowed(
                identifier, max_requests, window_seconds
            )
            
            if not allowed:
                return jsonify({
                    "error": "Rate limit excedido. Tente novamente em alguns segundos.",
                    "retry_after": retry_after
                }), 429
            
            return f(*args, **kwargs)
        
        return wrapped
    return decorator

def login_rate_limit(max_attempts=5, window_seconds=300):
    """
    Rate limiting específico para tentativas de login.
    Mais restritivo para prevenir brute force.
    
    5 tentativas por 5 minutos
    """
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            # Usa IP como identificador para login
            identifier = f"login_{request.remote_addr}"
            
            allowed, retry_after = rate_limiter.is_allowed(
                identifier, max_attempts, window_seconds
            )
            
            if not allowed:
                return jsonify({
                    "error": f"Muitas tentativas de login. Bloqueado por {retry_after} segundos.",
                    "retry_after": retry_after
                }), 429
            
            return f(*args, **kwargs)
        
        return wrapped
    return decorator
