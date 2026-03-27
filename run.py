#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AtuDIC Supreme — Entry Point
Plataforma unificada de inteligencia Protheus.
"""

import os
import sys

# Garante que o diretorio do projeto esta no path
project_dir = os.path.dirname(os.path.abspath(__file__))
if project_dir not in sys.path:
    sys.path.insert(0, project_dir)

# Carregar .env se existir
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def main():
    """Inicializa e executa a aplicacao."""
    print("\n=== AtuDIC Supreme ===\n")

    # 1. Banco de dados
    print("[DB] Inicializando banco de dados...")
    try:
        from app.database import init_db, run_migrations, DB_CONFIG
        import psycopg2
        import psycopg2.extras

        init_db()
        print("[DB] Banco de dados inicializado!")

        # 2. Migrations
        print("[DB] Verificando migrations...")
        conn = psycopg2.connect(
            connection_factory=psycopg2.extras.RealDictConnection,
            **DB_CONFIG
        )
        cursor = conn.cursor()
        applied = run_migrations(conn, cursor)
        conn.close()
        if applied:
            print(f"[DB] {applied} migration(s) aplicada(s)!")
        else:
            print("[DB] Migrations em dia.")

    except Exception as e:
        print(f"[WARN] PostgreSQL nao disponivel: {e}")
        print("[WARN] Workspace (SQLite) funciona normalmente sem PostgreSQL.")
        print("[WARN] Funcionalidades de plataforma (auth, historico) ficam desabilitadas.\n")

    # 3. Criar app Flask
    from app import create_app
    app = create_app()

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"

    print(f"\n[OK] AtuDIC Supreme rodando em http://{host}:{port}\n")

    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()
