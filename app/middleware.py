"""
Middleware global para a aplicação Flask.

Inclui rate limiting, headers de segurança e request ID.
"""
import uuid
from flask import request, jsonify, g
from app.utils.rate_limiter import rate_limiter


def register_middleware(app):
    """Registra middleware global na app Flask."""

    @app.before_request
    def global_rate_limit():
        """
        Rate limiting global para TODAS as rotas da API.
        Previne abuso generalizado.
        """
        if not request.path.startswith('/api/'):
            return None

        identifier = f"global_{request.remote_addr}"
        allowed, retry_after = rate_limiter.is_allowed(identifier, 1000, 3600)

        if not allowed:
            return jsonify({
                "error": "Rate limit global excedido. Contate o administrador.",
                "retry_after": retry_after
            }), 429

        return None

    @app.before_request
    def inject_request_id():
        """Gera um ID único por requisição para rastreamento em logs."""
        g.request_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:8])

    @app.after_request
    def set_security_headers(response):
        """Headers de segurança em todas as respostas."""
        # Previne clickjacking
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        # Previne MIME-type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"
        # Controle de referrer
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Previne XSS em browsers antigos
        response.headers["X-XSS-Protection"] = "1; mode=block"
        # Permissões de features do browser
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        # Request ID no response para correlação
        response.headers["X-Request-ID"] = getattr(g, "request_id", "")
        # CSP — alinhado com o meta tag do index.html
        # Permite CDNs usados pelo frontend (Bootstrap, Font Awesome, Google Fonts)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://fonts.googleapis.com; "
            "font-src 'self' https://cdnjs.cloudflare.com https://fonts.gstatic.com; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'self'"
        )
        return response
