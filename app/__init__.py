# -*- coding: utf-8 -*-
"""
AtuDIC Supreme — Application Factory
"""

from flask import Flask, render_template


def create_app(config_override=None):
    """Cria e configura a aplicacao Flask."""
    app = Flask(
        __name__,
        static_folder="../static",
        template_folder="../templates",
    )

    # Configuracao padrao
    app.config.from_mapping(
        SECRET_KEY=__import__("os").environ.get("SECRET_KEY", "dev-key-change-me"),
        JSON_SORT_KEYS=False,
    )

    if config_override:
        app.config.from_mapping(config_override)

    # Registrar blueprints
    _register_blueprints(app)

    # Health check
    @app.route("/api/health")
    def health():
        return {"status": "ok", "service": "atudic-supreme"}

    # Paginas
    @app.route("/")
    @app.route("/workspace")
    def workspace_page():
        return render_template("workspace.html")

    return app


def _register_blueprints(app):
    """Registra blueprints da aplicacao."""
    from app.routes.workspace import workspace_bp
    app.register_blueprint(workspace_bp, url_prefix="/api/workspace")
