#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AtuDIC Supreme — Entry Point
Plataforma unificada de inteligencia Protheus.
"""

import os
import sys
import logging

def main():
    """Inicializa e executa a aplicacao."""
    # Garante que o diretorio do projeto esta no path
    project_dir = os.path.dirname(os.path.abspath(__file__))
    if project_dir not in sys.path:
        sys.path.insert(0, project_dir)

    from app import create_app

    app = create_app()

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"

    logging.info(f"AtuDIC Supreme iniciando em http://{host}:{port}")

    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()
