"""
BiizHubOps - Ponto de entrada da aplicação.
"""

# =====================================================================
# 1. CONFIGURAÇÃO DE ENCODING (deve ser primeiro!)
# =====================================================================
from app.config import configure_encoding, load_env_file, get_base_directory

configure_encoding()

# =====================================================================
# 2. CARREGAR VARIÁVEIS DE AMBIENTE (antes de qualquer import de DB)
# =====================================================================
print("[INFO] Carregando variaveis de ambiente...")
load_env_file()

# =====================================================================
# 3. IMPORTS
# =====================================================================
import os
import sys
import signal
import atexit
import psycopg2.pool
from flask import Flask
from flask_cors import CORS

# Database e Seeds
from app.database import get_db, release_db_connection, DB_CONFIG, init_db, run_migrations

# Security
from app.utils.crypto import TokenEncryption, init_crypto
import app.utils.crypto as crypto
from app.utils.security import (
    verify_password,
    hash_password,
    generate_session_token,
    require_auth,
    require_auth_no_update,
    require_admin,
    require_operator,
    get_user_permissions,
    check_protected_item,
)

# Licenciamento (desabilitado nesta versão)
# from license_system import init_license_system

# Serviços
from app.services.scheduler import PipelineScheduler
from app.services.log_parser import LogMonitor
from app.services.events import event_manager

# =====================================================================
# 4. CRIAR APLICAÇÃO FLASK
# =====================================================================
import sys

# Definir a resolução de diretórios compatível com local/PyInstaller
if getattr(sys, "frozen", False):
    # Executável PyInstaller empacota os arquivos roots aqui
    root_dir = sys._MEIPASS
    template_dir = os.path.join(sys._MEIPASS, "app", "static")
else:
    # Desenvolvimento nativo aponta para o workspace
    root_dir = os.path.dirname(os.path.abspath(__file__))
    template_dir = os.path.join(root_dir, "static")

app = Flask(__name__, static_folder=template_dir, root_path=root_dir)

# CORS — restrito a origens confiáveis (configurável via env)
_cors_origins = os.getenv("CORS_ALLOWED_ORIGINS", "").strip()
if _cors_origins:
    # Lista separada por vírgula: "http://localhost:6001,https://atudic.empresa.com"
    CORS(app, origins=[o.strip() for o in _cors_origins.split(",") if o.strip()])
else:
    # Fallback para desenvolvimento local — aceita localhost nas portas da app
    CORS(app, origins=[
        "http://localhost:6001", "http://127.0.0.1:6001",   # dev (python run.py)
        "http://localhost:5000", "http://127.0.0.1:5000",   # docker (gunicorn)
    ])

# =====================================================================
# 5. REGISTRAR BLUEPRINTS
# =====================================================================
from app.routes.auth import auth_bp
from app.routes.main import main_bp
from app.routes.pipelines import pipelines_bp
from app.routes.users import users_bp
from app.routes.repositories import repositories_bp
from app.routes.source_control import source_control_bp
from app.routes.settings import settings_bp
from app.routes.services import services_bp
from app.routes.commands import commands_bp
from app.routes.admin import admin_bp
from app.routes.license import license_bp
from app.routes.rpo import rpo_bp
from app.routes.api import api_bp
from app.routes.observability import observability_bp
from app.routes.knowledge import knowledge_bp
from app.routes.database import database_bp
from app.routes.processes import processes_bp
from app.routes.documentation import documentation_bp
from app.routes.devworkspace import devworkspace_bp
from app.routes.dictionary import dictionary_bp
from app.routes.agent import agent_bp
from app.routes.mcp import mcp_bp
from app.routes.auditor import auditor_bp
from app.routes.tdn import tdn_bp
from app.routes.workspace import workspace_bp

app.register_blueprint(auth_bp)
app.register_blueprint(main_bp)
app.register_blueprint(pipelines_bp)
app.register_blueprint(users_bp)
app.register_blueprint(repositories_bp)
app.register_blueprint(source_control_bp)
app.register_blueprint(settings_bp)
app.register_blueprint(services_bp)
app.register_blueprint(commands_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(license_bp)
app.register_blueprint(rpo_bp)
app.register_blueprint(api_bp)
app.register_blueprint(observability_bp)
app.register_blueprint(knowledge_bp)
app.register_blueprint(database_bp)
app.register_blueprint(processes_bp)
app.register_blueprint(documentation_bp)
app.register_blueprint(devworkspace_bp)
app.register_blueprint(dictionary_bp)
app.register_blueprint(agent_bp)
app.register_blueprint(mcp_bp)
app.register_blueprint(auditor_bp)
app.register_blueprint(tdn_bp)
app.register_blueprint(workspace_bp, url_prefix="/api/workspace")

# =====================================================================
# 6. REGISTRAR ERROR HANDLERS E MIDDLEWARE
# =====================================================================
from app.utils.error_handlers import register_error_handlers
from app.middleware import register_middleware

register_error_handlers(app)
register_middleware(app)

# =====================================================================
# 7. VARIÁVEIS GLOBAIS
# =====================================================================
token_encryption = None
audit_logger = None
pipeline_scheduler = None
log_monitor = None


# =====================================================================
# 8. INICIALIZAÇÃO DO SISTEMA
# =====================================================================
def _validate_environment():
    """Valida variáveis de ambiente críticas no startup."""
    warnings = []
    if not os.getenv("DB_PASSWORD"):
        warnings.append("DB_PASSWORD nao definida — usando fallback de desenvolvimento")
    if not os.getenv("DB_HOST"):
        warnings.append("DB_HOST nao definido — usando localhost")
    if os.getenv("FLASK_ENV") == "production" and not os.getenv("CORS_ALLOWED_ORIGINS"):
        warnings.append("CORS_ALLOWED_ORIGINS nao definido em producao — acesso restrito a localhost")
    return warnings


def initialize_system():
    """Inicializa todos os componentes do sistema."""
    global token_encryption, audit_logger, pipeline_scheduler, log_monitor

    print("=" * 60)
    print("🚀 BIIZHUBOPS - DASHBOARD e API BACKEND")
    print("=" * 60)

    # 0. Validar ambiente
    env_warnings = _validate_environment()
    if env_warnings:
        print("\n⚠️  Avisos de configuração:")
        for w in env_warnings:
            print(f"   - {w}")

    # 1. Banco de dados
    print("\n📊 Inicializando banco de dados...")
    init_db()
    print("✓ Banco de dados inicializado com sucesso!")

    # 1b. Migrations incrementais
    print("\n📦 Verificando migrations...")
    try:
        # Conexão NOVA (fora do pool) para garantir visibilidade de todos os dados
        # commitados pelo init_db() — conexões do pool podem ter snapshot anterior
        import psycopg2.extras as _pge
        conn = psycopg2.connect(
            connection_factory=_pge.RealDictConnection,
            **DB_CONFIG
        )
        cursor = conn.cursor()
        applied = run_migrations(conn, cursor)
        conn.close()
        if applied:
            print(f"✓ {applied} migration(s) aplicada(s) com sucesso!")
        else:
            print("✓ Banco de dados atualizado (nenhuma migration pendente)")
    except Exception as e:
        print(f"❌ Erro ao executar migrations: {e}")
        raise

    # 2. Criptografia
    print("\n🔐 Inicializando sistema de criptografia...")
    try:
        token_encryption = init_crypto()
        if token_encryption and token_encryption.is_initialized():
            print("✓ Sistema de criptografia inicializado!")
            if not token_encryption.has_backup():
                print("⚠️  AVISO: Chave de criptografia SEM BACKUP!")
                print(f"   Execute: cp {token_encryption.key_file} {token_encryption.key_file}.backup")
        else:
            print("❌ ERRO: Sistema de criptografia não foi inicializado!")
    except Exception as e:
        print(f"❌ ERRO ao inicializar criptografia: {e}")

    # 3. Logging
    print("\n📝 Inicializando sistema de logging...")
    try:
        from app.utils.logging_config import setup_logging

        audit_logger = setup_logging(app)
        print("✓ Sistema de logging inicializado!")
        print("   Logs em: logs/app.log, logs/errors.log, logs/audit.log")
    except Exception as e:
        print(f"⚠️  Logging: {e}")

    # 4. Pipeline Scheduler
    print("\n⏰ Inicializando Pipeline Scheduler...")
    try:
        pipeline_scheduler = PipelineScheduler(app)
        pipeline_scheduler.start()
        print("✅ Pipeline Scheduler inicializado e rodando!")
    except Exception as e:
        print(f"⚠️ Scheduler: {e}")

    # 5. Log Monitor (Monitoramento)
    print("\n📡 Inicializando Log Monitor...")
    try:
        log_monitor = LogMonitor(app)
        log_monitor.start()
        print("✅ Log Monitor inicializado e rodando!")
    except Exception as e:
        print(f"⚠️ Log Monitor: {e}")

    # 6. Licenciamento
    print("\n🎯 BiizHubOps — licenciamento desabilitado nesta versão.")

    # 7. Verificações finais
    print("\n⚙️  Verificando configurações...")
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) as count FROM users")
        print(f"   Usuários cadastrados: {cursor.fetchone()['count']}")

        cursor.execute("SELECT COUNT(*) as count FROM environments")
        print(f"   Ambientes configurados: {cursor.fetchone()['count']}")

        cursor.execute("SELECT username FROM github_settings WHERE id = 1")
        gh = cursor.fetchone()
        print(f"   GitHub: {gh['username'] if gh and gh['username'] else 'Não configurado'}")
    except Exception as e:
        print(f"   ⚠️  Verificação incompleta: {e}")
        conn.rollback()
    finally:
        release_db_connection(conn)

    print("\n✓ Sistema pronto!")
    print(f"\n🖥️  Dashboard: http://localhost:6001")
    print(f"🌐 API: http://localhost:6001/api")
    print("\n" + "=" * 60 + "\n")


def shutdown_system(signum=None, frame=None):
    """Encerra componentes do sistema de forma controlada."""
    sig_name = signal.Signals(signum).name if signum else "atexit"
    print(f"\n🛑 Recebido {sig_name} — encerrando sistema...")

    # Parar scheduler
    if pipeline_scheduler:
        try:
            pipeline_scheduler.stop()
            print("   ✓ Pipeline Scheduler parado")
        except Exception as e:
            print(f"   ⚠️ Scheduler: {e}")

    # Parar log monitor
    if log_monitor:
        try:
            log_monitor.stop()
            print("   ✓ Log Monitor parado")
        except Exception as e:
            print(f"   ⚠️ Log Monitor: {e}")

    # Fechar pool de conexões do banco
    from app.database.core import _db_pool
    if _db_pool:
        try:
            _db_pool.closeall()
            print("   ✓ Pool de conexões fechado")
        except Exception as e:
            print(f"   ⚠️ Pool DB: {e}")

    print("👋 Sistema encerrado.\n")
    if signum:
        sys.exit(0)


# Registrar handlers de shutdown
signal.signal(signal.SIGTERM, shutdown_system)
signal.signal(signal.SIGINT, shutdown_system)
atexit.register(shutdown_system)


# Iniciar o sistema garantindo que não duplique workers pelo reloader do werkzeug
if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not app.debug:
    initialize_system()

# =====================================================================
# 9. ENTRY POINT
# =====================================================================
if __name__ == "__main__":
    _host = os.getenv("APP_HOST", "0.0.0.0")
    _port = int(os.getenv("APP_PORT", "6001"))

    if getattr(sys, "frozen", False):
        # Executável PyInstaller → servidor de produção (sem warning)
        from waitress import serve
        print(f"🌐 Waitress servindo em http://{_host}:{_port}")
        serve(app, host=_host, port=_port, threads=8)
    else:
        # Desenvolvimento → servidor Flask embutido
        app.run(debug=False, host=_host, port=_port)
