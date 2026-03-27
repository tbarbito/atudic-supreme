"""
Error handlers globais para a aplicação Flask.
"""
import traceback
from flask import jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException


def register_error_handlers(app):
    """Registra todos os error handlers globais na app Flask."""

    @app.errorhandler(400)
    def bad_request(error):
        app.logger.warning(f"Bad Request: {error}")
        return jsonify({
            "error": "Requisição inválida",
            "message": str(error.description) if hasattr(error, 'description') else "Dados inválidos"
        }), 400

    @app.errorhandler(401)
    def unauthorized(error):
        app.logger.warning(f"Unauthorized access attempt from {request.remote_addr}")
        return jsonify({
            "error": "Não autorizado",
            "message": "Autenticação necessária"
        }), 401

    @app.errorhandler(403)
    def forbidden(error):
        user_info = "anonymous"
        if hasattr(request, 'current_user'):
            user_info = request.current_user.get('username', 'unknown')
        app.logger.warning(f"Forbidden access by {user_info} to {request.path}")
        return jsonify({
            "error": "Acesso negado",
            "message": "Você não tem permissão para acessar este recurso"
        }), 403

    @app.errorhandler(404)
    def not_found(error):
        # Se for uma rota de API, retorna o JSON de erro original
        if request.path.startswith('/api/'):
            return jsonify({
                "error": "Recurso não encontrado",
                "message": "O recurso solicitado não existe"
            }), 404
            
        # Para qualquer outra rota não mapeada vinda do frontend (SPA),
        # delegamos para o index do React renderizar a UI/routing
        return send_from_directory(app.root_path, "index.html")

    @app.errorhandler(429)
    def rate_limit_exceeded(error):
        app.logger.warning(f"Rate limit exceeded from {request.remote_addr}")
        return jsonify({
            "error": "Muitas requisições",
            "message": "Você excedeu o limite de requisições. Tente novamente mais tarde."
        }), 429

    @app.errorhandler(500)
    def internal_error(error):
        app.logger.error(f"Internal Server Error: {error}")
        app.logger.error(traceback.format_exc())
        if app.debug:
            return jsonify({
                "error": "Erro interno do servidor",
                "message": str(error),
                "traceback": traceback.format_exc()
            }), 500
        else:
            return jsonify({
                "error": "Erro interno do servidor",
                "message": "Ocorreu um erro inesperado. Tente novamente mais tarde."
            }), 500

    @app.errorhandler(Exception)
    def handle_exception(error):
        if isinstance(error, HTTPException):
            return error
        app.logger.error(f"Unhandled Exception: {error}")
        app.logger.error(traceback.format_exc())
        if app.debug:
            return jsonify({
                "error": "Erro não tratado",
                "type": type(error).__name__,
                "message": str(error),
                "traceback": traceback.format_exc()
            }), 500
        else:
            return jsonify({
                "error": "Erro interno do servidor",
                "message": "Ocorreu um erro inesperado. Contate o administrador."
            }), 500
