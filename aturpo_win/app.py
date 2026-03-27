import sys
import io
import os
import platform

os.environ['PYTHONUNBUFFERED'] = '1'

# Configurar encoding ANTES de qualquer outro import
if hasattr(sys, 'frozen'):
    # Executando como executavel PyInstaller
    print("[INFO] Detectado ambiente PyInstaller, aplicando fixes de encoding...")
    
    # Fix 1: Redirecionar stdout/stderr para UTF-8
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
        print("[OK] stdout/stderr configurados para UTF-8")
    except Exception as e:
        print(f"[AVISO] Erro ao configurar stdout/stderr: {e}")
    
    # Fix 2: Variaveis de ambiente para PostgreSQL/psycopg2
    os.environ['PGCLIENTENCODING'] = 'UTF8'
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    print("[OK] Variaveis de ambiente configuradas: PGCLIENTENCODING=UTF8")
    
    # Fix 3: Locale
    import locale
    try:
        locale.setlocale(locale.LC_ALL, 'C.UTF-8')
        print("[OK] Locale configurado: C.UTF-8")
    except:
        try:
            locale.setlocale(locale.LC_ALL, '')
            print("[OK] Locale configurado: default")
        except Exception as e:
            print(f"[AVISO] Nao foi possivel configurar locale: {e}")

# =====================================================================
# IMPORTS BASICOS - SEM psycopg2 ainda!
# =====================================================================
from flask import Flask, request, jsonify, send_from_directory, session, stream_with_context
from cryptography.fernet import Fernet
import base64
import threading
import time
import shlex
import re
import subprocess
import shutil
import queue
import json
from flask_cors import CORS

# =====================================================================
# Funcao para carregar variaveis de ambiente manualmente (sem python-dotenv)
# DEVE SER CHAMADO ANTES DE IMPORTAR psycopg2
# =====================================================================
def load_env_file(env_file='.env'):
    """Carrega variaveis do arquivo de configuracao manualmente"""
    
    # Lista de locais para procurar config
    possible_paths = []
    
    # Se rodando como executavel PyInstaller
    if hasattr(sys, 'frozen'):
        # Diretorio do executavel
        exe_dir = os.path.dirname(sys.executable)
        possible_paths = [
            os.path.join(exe_dir, 'config.env'),
            os.path.join(exe_dir, '.env'),
            'config.env',
            '.env'
        ]
    else:
        # Rodando como script Python
        possible_paths = [env_file, 'config.env', '.env']
    
    # Tentar cada caminho
    for path in possible_paths:
        if os.path.exists(path):
            env_file = path
            break
    else:
        print(f"[AVISO] Arquivo de configuracao nao encontrado")
        print(f"[DEBUG] Caminhos tentados: {possible_paths}")
        return
    
    # Carregar arquivo encontrado
    if os.path.exists(env_file):
        try:
            with open(env_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        os.environ[key.strip()] = value.strip()
            print(f"[OK] Variaveis carregadas de: {env_file}")
        except Exception as e:
            print(f"[ERRO] Erro ao carregar {env_file}: {e}")
    else:
        print(f"[AVISO] Arquivo {env_file} nao encontrado")

# Carregar variaveis de ambiente ANTES de importar psycopg2
print("[INFO] Carregando variaveis de ambiente...")
load_env_file()

def get_base_directory():
    """
    Retorna o diretório base correto dependendo do modo de execução.
    - Executável PyInstaller: diretório do .exe
    - Script Python: diretório do script
    """
    if hasattr(sys, 'frozen'):
        # Rodando como executável empacotado
        return os.path.dirname(sys.executable)
    else:
        # Rodando como script Python
        return os.path.dirname(os.path.abspath(__file__))

# =====================================================================
# IMPORTS QUE DEPENDEM DE VARIAVEIS DE AMBIENTE
# =====================================================================
print("[INFO] Importando psycopg2...")
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import IntegrityError, Error as PsycopgError
try:
    from psycopg2 import errors as psycopg2_errors
except ImportError:
    # Fallback para executaveis PyInstaller
    psycopg2_errors = None
print("[OK] psycopg2 importado")

print("[INFO] Importando license_system...")
from license_system import (
    init_license_system,
    init_license_cache_db,
    get_hardware_id,
    get_license_key,
    save_license_key,
    get_license_status,
    validate_license_hybrid,
    clear_license_cache,
    LICENSE_FILE
)
print("[OK] license_system importado")

from datetime import datetime, timedelta
from functools import wraps
from collections import defaultdict
from threading import Lock

# =====================================================================
# QUEUE EM MEMÓRIA PARA STREAMING DE LOGS EM TEMPO REAL
# =====================================================================
from collections import deque

# Estrutura: {run_id: {'logs': deque([...]), 'status': 'running'|'success'|'failed'}}
live_log_streams = {}
live_log_streams_lock = Lock()

def get_live_stream(run_id):
    """Obtém ou cria stream de logs para um run_id"""
    with live_log_streams_lock:
        if run_id not in live_log_streams:
            live_log_streams[run_id] = {
                'logs': deque(maxlen=5000),  # Máximo 5000 linhas em memória
                'status': 'running'
            }
        return live_log_streams[run_id]

def save_logs_background(flask_app, log_buffer, log_id, output, status):
    """Salva logs no banco em thread background (não bloqueia execução)"""
    def _save():
        with flask_app.app_context():
            try:
                conn = get_db()
                cursor = conn.cursor()
                
                # Inserir logs de output
                if log_buffer:
                    cursor.executemany("""
                        INSERT INTO pipeline_run_output_logs (run_id, output, log_type, created_at)
                        VALUES (%s, %s, %s, %s)
                    """, log_buffer)
                
                # Atualizar log do comando
                cursor.execute("""
                    UPDATE pipeline_run_logs 
                    SET output = %s, status = %s, finished_at = %s
                    WHERE id = %s
                """, (output, status, datetime.now(), log_id))
                
                conn.commit()
                conn.close()
                flask_app.logger.info(f"✅ Logs salvos em background para log_id={log_id}")
            except Exception as e:
                flask_app.logger.error(f"❌ Erro ao salvar logs em background: {e}")
    
    thread = threading.Thread(target=_save, daemon=True)
    thread.start()

def push_live_log(run_id, message, level="output"):
    """Adiciona log ao stream em memória"""
    stream = get_live_stream(run_id)
    stream['logs'].append({'output': message, 'log_type': level})

def set_live_stream_status(run_id, status):
    """Define status final do stream"""
    stream = get_live_stream(run_id)
    stream['status'] = status

def cleanup_live_stream(run_id):
    """Remove stream da memória após conclusão"""
    with live_log_streams_lock:
        if run_id in live_log_streams:
            del live_log_streams[run_id]

import hashlib
import secrets
import logging
from logging.handlers import RotatingFileHandler
import traceback
from werkzeug.exceptions import HTTPException
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo  # Python 3.9+
from license_system import get_license_status_realtime
import pytz


# =====================================================================
# CONFIGURAÇÃO DE TIMEZONE
# =====================================================================

try:
    TIMEZONE = ZoneInfo('America/Sao_Paulo')
except:
    # Fallback para pytz se zoneinfo não disponível
    import pytz
    TIMEZONE = pytz.timezone('America/Sao_Paulo')

def now_br():
    """Retorna datetime atual no timezone do Brasil (São Paulo)"""
    return datetime.now(TIMEZONE)

app = Flask(__name__)
CORS(app)

# =====================================================================
# HELPER PARA SERIALIZAÇÃO JSON
# =====================================================================

def convert_datetime_to_str(obj):
    """
    Converte objetos datetime para string ISO format recursivamente.
    Usado para serializar resultados do PostgreSQL para JSON.
    """
    if isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {key: convert_datetime_to_str(value) for key, value in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [convert_datetime_to_str(item) for item in obj]
    return obj

# =====================================================================
# CONFIGURAÇÃO DE LOGGING
# =====================================================================

def setup_logging(app):
    """
    Configura sistema de logging robusto com rotação de arquivos.
    """
    
    # Cria diretório de logs se não existir (compatível com executável)
    log_dir = os.path.join(get_base_directory(), 'logs')
    os.makedirs(log_dir, exist_ok=True)

    # Mostra onde os logs estão sendo gravados
    print(f"📝 Logs do sistema: {log_dir}")
    print(f"   - app.log: Logs gerais")
    print(f"   - errors.log: Apenas erros")
    print(f"   - audit.log: Auditoria")
    
    # Remove handlers padrão do Flask
    app.logger.handlers.clear()
    
    # Formato detalhado de log
    formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
    )
    
    # Handler para arquivo geral (INFO e acima)
    general_handler = RotatingFileHandler(
        os.path.join(log_dir, 'app.log'),
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=10,
        encoding='utf-8'  # Suporte a emojis e caracteres especiais
    )
    general_handler.setLevel(logging.INFO)
    general_handler.setFormatter(formatter)

    # Handler para erros (ERROR e acima)
    error_handler = RotatingFileHandler(
        os.path.join(log_dir, 'errors.log'),
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=10,
        encoding='utf-8'  # Suporte a emojis e caracteres especiais
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)

    # Handler para console (desenvolvimento)
    import sys
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG if app.debug else logging.INFO)
    console_handler.setFormatter(formatter)
    # Força UTF-8 no console do Windows
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    
    # Adiciona handlers ao logger do app
    app.logger.addHandler(general_handler)
    app.logger.addHandler(error_handler)
    app.logger.addHandler(console_handler)
    app.logger.setLevel(logging.DEBUG if app.debug else logging.INFO)
    
    # Log de auditoria separado
    audit_handler = RotatingFileHandler(
        os.path.join(log_dir, 'audit.log'),
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=20,
        encoding='utf-8'  # Suporte a emojis e caracteres especiais
    )
    audit_handler.setLevel(logging.INFO)
    audit_handler.setFormatter(formatter)
    
    # Logger de auditoria separado
    audit_logger = logging.getLogger('audit')
    audit_logger.addHandler(audit_handler)
    audit_logger.setLevel(logging.INFO)
    
    app.logger.info("Sistema de logging configurado com sucesso")
    
    return audit_logger

# Inicializa logging (chamar no início do app)
# audit_logger = setup_logging(app)

# =====================================================================
# FUNÇÕES DE AUDITORIA
# =====================================================================

def log_audit(action, user_id, user_name, details, status='success'):
    """
    Registra ação de auditoria.
    
    Args:
        action: Tipo de ação (login, create_user, delete_repo, etc)
        user_id: ID do usuário
        user_name: Nome do usuário
        details: Detalhes da ação
        status: success ou failure
    """
    audit_logger = logging.getLogger('audit')
    audit_logger.info(
        f"ACTION={action} | USER_ID={user_id} | USER={user_name} | "
        f"STATUS={status} | IP={request.remote_addr} | DETAILS={details}"
    )

# =====================================================================
# TRATADORES DE ERROS GLOBAIS
# =====================================================================

@app.errorhandler(400)
def bad_request(error):
    """Trata erros 400 - Bad Request"""
    app.logger.warning(f"Bad Request: {error}")
    return jsonify({
        "error": "Requisição inválida",
        "message": str(error.description) if hasattr(error, 'description') else "Dados inválidos"
    }), 400


@app.errorhandler(401)
def unauthorized(error):
    """Trata erros 401 - Unauthorized"""
    app.logger.warning(f"Unauthorized access attempt from {request.remote_addr}")
    return jsonify({
        "error": "Não autorizado",
        "message": "Autenticação necessária"
    }), 401


@app.errorhandler(403)
def forbidden(error):
    """Trata erros 403 - Forbidden"""
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
    """Trata erros 404 - Not Found"""
    return jsonify({
        "error": "Recurso não encontrado",
        "message": "O recurso solicitado não existe"
    }), 404


@app.errorhandler(429)
def rate_limit_exceeded(error):
    """Trata erros 429 - Rate Limit"""
    app.logger.warning(f"Rate limit exceeded from {request.remote_addr}")
    return jsonify({
        "error": "Muitas requisições",
        "message": "Você excedeu o limite de requisições. Tente novamente mais tarde."
    }), 429


@app.errorhandler(500)
def internal_error(error):
    """Trata erros 500 - Internal Server Error"""
    # Log completo do erro
    app.logger.error(f"Internal Server Error: {error}")
    app.logger.error(traceback.format_exc())
    
    # Em produção, não expõe detalhes do erro
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
    """Tratador genérico para exceções não tratadas"""
    
    # Passa HTTPException para os handlers específicos
    if isinstance(error, HTTPException):
        return error
    
    # Log do erro completo
    app.logger.error(f"Unhandled Exception: {error}")
    app.logger.error(traceback.format_exc())
    
    # Em produção, retorna mensagem genérica
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
    
# =====================================================================
# SISTEMA DE RATE LIMITING
# =====================================================================

class RateLimiter:
    """
    Sistema de rate limiting simples baseado em memória.
    Para produção, considere usar Redis.
    """
    
    def __init__(self):
        self.requests = defaultdict(list)
        self.lock = Lock()
    
    def is_allowed(self, identifier, max_requests, window_seconds):
        """
        Verifica se requisição é permitida.
        
        Args:
            identifier: IP ou user_id
            max_requests: Número máximo de requisições
            window_seconds: Janela de tempo em segundos
            
        Returns:
            tuple: (is_allowed, retry_after_seconds)
        """
        with self.lock:
            now = time.time()
            
            # Remove requisições antigas fora da janela
            self.requests[identifier] = [
                req_time for req_time in self.requests[identifier]
                if now - req_time < window_seconds
            ]
            
            # Verifica se excedeu o limite
            if len(self.requests[identifier]) >= max_requests:
                # Calcula quanto tempo falta para liberar
                oldest_request = min(self.requests[identifier])
                retry_after = window_seconds - (now - oldest_request)
                return False, int(retry_after) + 1
            
            # Registra nova requisição
            self.requests[identifier].append(now)
            return True, 0
    
    def clear_user(self, identifier):
        """Remove histórico de um usuário/IP"""
        with self.lock:
            if identifier in self.requests:
                del self.requests[identifier]

# Instância global
rate_limiter = RateLimiter()

# =====================================================================
# DECORATORS DE RATE LIMITING
# =====================================================================

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
            # Identifica usuário por IP
            identifier = request.remote_addr
            
            # Se autenticado, usa user_id ao invés de IP
            if hasattr(request, 'current_user'):
                identifier = f"user_{request.current_user['id']}"
            
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

# =====================================================================
# SISTEMA DE CRIPTOGRAFIA PARA TOKENS SENSÍVEIS
# =====================================================================

class TokenEncryption:
    """
    Gerenciador de criptografia para tokens sensíveis.
    Versão robusta com tratamento de erros melhorado.
    """
    
    def __init__(self, key_filename='.encryption_key'):
        """Inicializa o sistema de criptografia"""
        self.key_file = os.path.join(get_base_directory(), key_filename)
        self.key = None
        self.cipher = None
        
        try:
            self.key = self._get_or_create_key()
            self.cipher = Fernet(self.key)
            print(f"   ✓ Criptografia inicializada: {self.key_file}")
        except Exception as e:
            print(f"   ❌ ERRO ao inicializar criptografia: {e}")
            raise
    
    def _get_or_create_key(self):
        """
        Obtém chave de criptografia existente ou cria uma nova.
        """
        try:
            if os.path.exists(self.key_file):
                # Carrega chave existente
                print(f"   📂 Carregando chave existente...")
                with open(self.key_file, 'rb') as f:
                    key = f.read()
                
                # Valida que a chave é válida
                try:
                    Fernet(key)  # Testa se é uma chave válida
                    print(f"   ✓ Chave válida carregada")
                    return key
                except Exception as e:
                    print(f"   ⚠️  Chave inválida encontrada, gerando nova: {e}")
                    # Remove chave inválida
                    os.remove(self.key_file)
            
            # Gera nova chave
            print(f"   🔑 Gerando nova chave de criptografia...")
            key = Fernet.generate_key()
            
            # Cria diretório se não existir
            base_dir = os.path.dirname(self.key_file)
            if base_dir:  # Só cria se houver diretório pai
                os.makedirs(base_dir, exist_ok=True)
            
            # Salva chave com permissões restritas
            with open(self.key_file, 'wb') as f:
                f.write(key)
            
            # Define permissões apenas para owner (Unix/Linux)
            try:
                os.chmod(self.key_file, 0o600)
                print(f"   ✓ Permissões definidas: 0600")
            except Exception as e:
                print(f"   ⚠️  Não foi possível definir permissões: {e}")
            
            print(f"   ✓ Nova chave criada: {self.key_file}")
            print(f"")
            print(f"   ⚠️  IMPORTANTE: Faça backup desta chave!")
            print(f"   📋 Backup recomendado:")
            print(f"      cp {self.key_file} {self.key_file}.backup")
            print(f"")
            
            return key
            
        except PermissionError as e:
            raise Exception(f"Sem permissão para criar arquivo de chave: {e}")
        except OSError as e:
            raise Exception(f"Erro ao acessar sistema de arquivos: {e}")
    
    def encrypt_token(self, token):
        """Criptografa um token."""
        if not token:
            return None
        
        if not self.cipher:
            raise Exception("Sistema de criptografia não inicializado!")
        
        try:
            token_bytes = token.encode('utf-8')
            encrypted_bytes = self.cipher.encrypt(token_bytes)
            return base64.b64encode(encrypted_bytes).decode('utf-8')
        except Exception as e:
            raise Exception(f"Erro ao criptografar token: {e}")
    
    def decrypt_token(self, encrypted_token):
        """Descriptografa um token."""
        if not encrypted_token:
            return None
        
        if not self.cipher:
            raise Exception("Sistema de criptografia não inicializado!")
        
        try:
            encrypted_bytes = base64.b64decode(encrypted_token.encode('utf-8'))
            decrypted_bytes = self.cipher.decrypt(encrypted_bytes)
            return decrypted_bytes.decode('utf-8')
        except Exception as e:
            print(f"❌ Erro ao descriptografar token: {type(e).__name__}")
            raise Exception(f"Erro ao descriptografar token: token pode estar corrompido")
    
    def is_initialized(self):
        """Verifica se o sistema está inicializado"""
        return self.cipher is not None


# Inicializa como None - será criado no startup
token_encryption = None

# =====================================================================
# FUNÇÕES DE SANITIZAÇÃO E VALIDAÇÃO
# =====================================================================

def sanitize_path_component(component):
    """
    Sanitiza componentes de caminho para prevenir path traversal.
    Remove caracteres perigosos e valida o formato.
    """
    if not component:
        return None
    
    # Remove espaços em branco
    component = component.strip()
    
    # Rejeita componentes perigosos
    dangerous_patterns = ['..', './', '\\', '~', '$', '`', ';', '|', '&', '<', '>', '*', '?', '[', ']', '{', '}', '(', ')']
    for pattern in dangerous_patterns:
        if pattern in component:
            raise ValueError(f"Caractere perigoso detectado no caminho: {pattern}")
    
    # Valida que contém apenas caracteres seguros
    if not re.match(r'^[a-zA-Z0-9_\-\.]+$', component):
        raise ValueError(f"Nome de caminho inválido: {component}")
    
    return component

def sanitize_branch_name(branch_name):
    """
    Sanitiza nome de branch Git para prevenir injection.
    """
    if not branch_name:
        return None
    
    branch_name = branch_name.strip()
    
    # Git branch names não podem conter certos caracteres
    dangerous_chars = ['..', '~', '^', ':', '?', '*', '[', '\\', ' ', '\t', '\n']
    for char in dangerous_chars:
        if char in branch_name:
            raise ValueError(f"Caractere inválido em nome de branch: {char}")
    
    # Valida formato básico
    if not re.match(r'^[a-zA-Z0-9/_\-\.]+$', branch_name):
        raise ValueError(f"Formato de branch inválido: {branch_name}")
    
    # Não pode começar ou terminar com /
    if branch_name.startswith('/') or branch_name.endswith('/'):
        raise ValueError("Branch não pode começar ou terminar com /")
    
    return branch_name

def sanitize_commit_message(message):
    """
    Sanitiza mensagem de commit para prevenir injection.
    """
    if not message:
        raise ValueError("Mensagem de commit não pode estar vazia")
    
    message = message.strip()
    
    # Remove caracteres de controle e caracteres perigosos
    message = re.sub(r'[\x00-\x1F\x7F]', '', message)
    
    # Limita tamanho
    if len(message) > 500:
        message = message[:500]
    
    # Escapa aspas e caracteres especiais para uso em shell
    # Usando shlex.quote para escapar adequadamente
    return message

def validate_git_url(url):
    """
    Valida URL do Git para garantir que é HTTPS e de origem confiável.
    """
    if not url:
        raise ValueError("URL não pode estar vazia")
    
    # Deve ser HTTPS
    if not url.startswith('https://'):
        raise ValueError("Apenas URLs HTTPS são permitidas")
    
    # Valida formato básico de URL Git
    git_url_pattern = r'^https://[a-zA-Z0-9\-\.]+/[a-zA-Z0-9\-_\.]+/[a-zA-Z0-9\-_\.]+\.git$'
    if not re.match(git_url_pattern, url):
        raise ValueError("Formato de URL Git inválido")
    
    return url

def execute_git_command_safely(command_args, cwd=None, timeout=300):
    """
    Executa comandos Git de forma segura usando lista de argumentos.
    
    Args:
        command_args: Lista de argumentos (não string!)
        cwd: Diretório de trabalho
        timeout: Timeout em segundos
    
    Returns:
        subprocess.CompletedProcess
    """
    # Garante que o primeiro argumento é 'git'
    if not command_args or command_args[0] != 'git':
        raise ValueError("Comando deve começar com 'git'")
    
    # Valida que todos os argumentos são strings
    if not all(isinstance(arg, str) for arg in command_args):
        raise ValueError("Todos os argumentos devem ser strings")
    
    # Executa com shell=False para segurança
    try:
        result = subprocess.run(
            command_args,
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False  # CRÍTICO: shell=False previne injection
        )
        return result
    except subprocess.TimeoutExpired:
        raise Exception(f"Comando Git excedeu o timeout de {timeout}s")
    except subprocess.CalledProcessError as e:
        raise Exception(f"Erro ao executar comando Git: {e.stderr}")

# *****************************

class EventManager:
    def __init__(self):
        self.clients = []
        self.lock = threading.Lock()

    def subscribe(self):
        q = queue.Queue()
        with self.lock:
            self.clients.append(q)
        return q

    def unsubscribe(self, q):
        with self.lock:
            self.clients.remove(q)

    def broadcast(self, message):
        with self.lock:
            for q in self.clients:
                q.put(message)                

event_manager = EventManager()

# =====================================================================
# SCHEDULER WORKER - AGENDAMENTO DE PIPELINES
# =====================================================================

class PipelineScheduler:
    """Worker que monitora e executa pipelines agendadas"""
    
    def __init__(self, flask_app):
        self.flask_app = flask_app
        self.running = False
        self.thread = None
        
    def start(self):
        """Inicia o worker em background"""
        if self.running:
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self.thread.start()
        print("✅ Scheduler worker iniciado!")
        
    def stop(self):
        """Para o worker"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        print("🛑 Scheduler worker parado!")
    
    def _scheduler_loop(self):
        """Loop principal do scheduler"""
        with self.flask_app.app_context():
            while self.running:
                try:
                    self._check_and_execute_schedules()
                    self._check_and_execute_service_actions()
                except Exception as e:
                    print(f"❌ Erro no scheduler loop: {e}")
                    traceback.print_exc()
                
                # Aguarda 30 segundos antes da próxima verificação
                time.sleep(30)
    
    def _check_and_execute_schedules(self):
        """Verifica schedules ativos e executa se necessário"""
        conn = get_db()
        cursor = conn.cursor()
        
        now = datetime.now()
        
        # Busca schedules ativos que devem ser executados
        cursor.execute("""
            SELECT s.*, p.name as pipeline_name, u.username
            FROM pipeline_schedules s
            JOIN pipelines p ON s.pipeline_id = p.id
            JOIN users u ON s.created_by = u.id
            WHERE s.is_active = TRUE
            AND (s.next_run_at IS NULL OR s.next_run_at <= %s)
        """, (now,))
        schedules = cursor.fetchall()
        
        for schedule in schedules:
            try:
                schedule_dict = dict(schedule)
                self._execute_scheduled_pipeline(cursor, schedule_dict, now)
            except Exception as e:
                print(f"❌ Erro ao executar schedule {schedule['id']}: {e}")
                traceback.print_exc()
        
        conn.commit()
        conn.close()
    
    def _execute_scheduled_pipeline(self, cursor, schedule, now):
        """Executa uma pipeline agendada"""
        schedule_id = schedule['id']
        pipeline_id = schedule['pipeline_id']
        created_by = schedule['created_by']
        username = schedule['username']

        # 🆕 Usar hora local do Brasil
        now_local = now_br()

        print(f"⏰ Executando schedule #{schedule_id}: {schedule['name']} (Pipeline: {schedule['pipeline_name']})")

        # Buscar comandos BUILD da pipeline
        cursor.execute("""
            SELECT c.* FROM commands c
            JOIN pipeline_commands pc ON c.id = pc.command_id
            WHERE pc.pipeline_id = %s
            ORDER BY pc.sequence_order
        """, (pipeline_id,))
        build_commands = [dict(row) for row in cursor.fetchall()]

        if not build_commands:
            print(f"❌ Schedule #{schedule_id}: Pipeline sem comandos configurados")
            return

        # 🆕 Buscar comando DEPLOY da pipeline (se existir)
        cursor.execute(
            "SELECT deploy_command_id FROM pipelines WHERE id = %s",
            (pipeline_id,)
        )
        pipeline_info = cursor.fetchone()
        deploy_command_id = pipeline_info['deploy_command_id'] if pipeline_info else None

        deploy_command = None
        if deploy_command_id:
            cursor.execute(
                "SELECT * FROM commands WHERE id = %s AND command_category = 'deploy'",
                (deploy_command_id,)
            )
            deploy_command = cursor.fetchone()
            if deploy_command:
                deploy_command = dict(deploy_command)

        # 🆕 Combinar comandos: BUILD + DEPLOY (se existir)
        all_commands = build_commands.copy()
        if deploy_command:
            all_commands.append(deploy_command)
            print(f"📦 Schedule incluirá {len(build_commands)} comandos BUILD + 1 comando DEPLOY")
        else:
            print(f"📦 Schedule incluirá {len(build_commands)} comandos BUILD (sem deploy)")

        # Buscar environment_id da pipeline
        cursor.execute(
            "SELECT environment_id FROM pipelines WHERE id = %s",
            (pipeline_id,)
        )
        env_row = cursor.fetchone()
        environment_id = env_row['environment_id'] if env_row else None

        # 🆕 Usar NULL para started_by quando for schedule
        cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
        user_row = cursor.fetchone()
        user_id = None  # 🆕 Forçar NULL para schedules

        # Obter próximo run_number
        cursor.execute(
            "SELECT MAX(run_number) as last FROM pipeline_runs WHERE pipeline_id = %s",
            (pipeline_id,)
        )
        last_run = cursor.fetchone()
        run_number = (dict(last_run)["last"] or 0) + 1

        # Criar novo pipeline_run com hora do Brasil
        cursor.execute("""
            INSERT INTO pipeline_runs 
            (pipeline_id, run_number, status, started_at, started_by, environment_id, trigger_type)
            VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
        """, (pipeline_id, run_number, 'running', now_local, 
              user_id, environment_id, 'scheduled'))

        run_id = cursor.fetchone()['id']
        cursor.connection.commit()

        # Inicia execução da pipeline em background com TODOS os comandos
        thread = threading.Thread(
            target=execute_pipeline_run,
            args=(self.flask_app, run_id, pipeline_id, all_commands),
            daemon=True
        )
        thread.start()

        print(f"✅ Schedule #{schedule_id}: Pipeline run #{run_number} iniciado (run_id: {run_id})")

        # Atualiza last_run_at com hora do Brasil
        cursor.execute("""
            UPDATE pipeline_schedules 
            SET last_run_at = %s
            WHERE id = %s
        """, (now_local, schedule_id))

        # Calcula próxima execução
        next_run = self._calculate_next_run(schedule)

        if next_run:
            cursor.execute("""
                UPDATE pipeline_schedules 
                SET next_run_at = %s
                WHERE id = %s
            """, (next_run, schedule_id))
        else:
            # Se não há próxima execução (ex: execução única), desativa
            cursor.execute("""
                UPDATE pipeline_schedules 
                SET is_active = FALSE, next_run_at = NULL
                WHERE id = %s
            """, (schedule_id,))
    
    def _check_and_execute_service_actions(self):
        """Verifica service actions agendadas e executa se necessário"""
        conn = get_db()
        cursor = conn.cursor()

        now = now_br()  # ✅ CORRETO: GMT-3 Brasil
        
        # Busca service actions ativas com agendamento
        cursor.execute("""
            SELECT sa.*, u.username
            FROM service_actions sa
            JOIN users u ON sa.created_by = u.id
            WHERE sa.is_active = TRUE
            AND sa.schedule_type IS NOT NULL
            AND (sa.next_run_at IS NULL OR sa.next_run_at <= %s)
        """, (now,))
        actions = cursor.fetchall()
        
        for action in actions:
            try:
                action_dict = dict(action)
                self._execute_scheduled_service_action(cursor, action_dict, now)
            except Exception as e:
                print(f"❌ Erro ao executar service action {action['id']}: {e}")
                traceback.print_exc()
        
        conn.commit()
        conn.close()
    
    def _execute_scheduled_service_action(self, cursor, action, now):
        """Executa uma ação de serviço agendada"""
        action_id = action['id']
        action_name = action['name']
        
        now_local = now_br()
        
        print(f"⚙️ Executando service action #{action_id}: {action_name}")
        
        # Buscar nome do ambiente para mapear sufixo
        cursor.execute(
            "SELECT name FROM environments WHERE id = %s",
            (action['environment_id'],)
        )
        env = cursor.fetchone()
        
        # Mapeia ambiente para sufixo
        suffix_map = {
            'Produção': 'PRD',
            'Homologação': 'HOM',
            'Desenvolvimento': 'DEV',
            'Testes': 'TST'
        }
        suffix = suffix_map.get(env['name'], 'PRD') if env else 'PRD'
        
        # Parse service IDs (manter a ordem original do sequenciador!)
        service_ids = action['service_ids'].split(',')
        
        # Get service names and server_name
        cursor.execute(
            f"SELECT id, name, server_name FROM server_services WHERE id IN ({','.join(['%s'] * len(service_ids))})",
            service_ids
        )
        services_unordered = cursor.fetchall()
        
        # IMPORTANTE: Ordenar serviços na ordem original dos IDs (sequenciador)
        services_dict = {str(s['id']): s for s in services_unordered}
        services = [services_dict[sid] for sid in service_ids if sid in services_dict]
        
        # Carregar variáveis de ambiente do banco
        cursor.execute("SELECT name, value FROM server_variables")
        db_vars = cursor.fetchall()
        env_vars = os.environ.copy()
        for var in db_vars:
            env_vars[var['name']] = var['value']
        
        success_count = 0
        for service in services:
            service_name = service['name']
            server_name = service.get('server_name', 'localhost')
            
            # Substituir variáveis ${VAR} no server_name
            import re
            variables_found = re.findall(r'\$\{([A-Z_0-9]+)\}', server_name)
            for var_name in variables_found:
                if var_name in env_vars:
                    server_name = server_name.replace(f"${{{var_name}}}", env_vars[var_name])
            
            # Build command based on OS and action type
            if action['os_type'] == 'linux':
                if action['action_type'] == 'start':
                    command = f"systemctl start {service_name}"
                elif action['action_type'] == 'stop':
                    command = f"systemctl stop {service_name}"
                elif action['action_type'] == 'restart':
                    command = f"systemctl restart {service_name}"
                
                # Execute Linux command
                import subprocess
                try:
                    result = subprocess.run(
                        command,
                        shell=True,
                        capture_output=True,
                        text=True,
                        timeout=60,
                        env=env_vars
                    )
                    if result.returncode == 0:
                        success_count += 1
                        print(f"  ✅ {service_name}: {action['action_type']} executado com sucesso")
                    else:
                        print(f"  ❌ {service_name}: Erro - {result.stderr}")
                except Exception as e:
                    print(f"  ❌ {service_name}: Exceção - {str(e)}")
                    
            else:  # windows
                force_flag = "-Force" if action.get('force_stop', False) else ""
                
                # Build PowerShell script based on action type
                if action['action_type'] == 'start':
                    ps_script = f"Start-Service -Name '{service_name}'"
                elif action['action_type'] == 'stop':
                    ps_script = f"Stop-Service -Name '{service_name}' {force_flag}"
                elif action['action_type'] == 'restart':
                    ps_script = f"Restart-Service -Name '{service_name}' {force_flag}"
                
                # Detectar SO do servidor AtuDIC
                import subprocess
                is_linux_server = platform.system() == 'Linux'
                
                try:
                    if is_linux_server:
                        # AtuDIC rodando em Linux → usar SSH para Windows
                        ssh_host = env_vars.get(f'SSH_HOST_WINDOWS_{suffix}', server_name)
                        ssh_user = env_vars.get(f'SSH_USER_WINDOWS_{suffix}', 'administrador')
                        ssh_port = env_vars.get(f'SSH_PORT_WINDOWS_{suffix}', '22')
                        
                        ssh_command = f"ssh -i ~/.ssh/id_rsa_aturpo -p {ssh_port} -o StrictHostKeyChecking=no -o ConnectTimeout=10 {ssh_user}@{ssh_host} \"powershell -Command {ps_script}\""
                        
                        print(f"  🔧 Executando via SSH ({ssh_user}@{ssh_host}): {ps_script}")
                        
                        result = subprocess.run(
                            ssh_command,
                            shell=True,
                            capture_output=True,
                            text=True,
                            timeout=60,
                            env=env_vars,
                            encoding='utf-8',
                            errors='replace'
                        )
                        if result.returncode == 0:
                            success_count += 1
                            print(f"  ✅ {service_name}: {action['action_type']} executado com sucesso via SSH")
                            if result.stdout:
                                print(f"     📤 Output: {result.stdout.strip()}")
                        else:
                            print(f"  ❌ {service_name}: Erro SSH - {result.stderr}")
                    else:
                        # AtuDIC rodando em Windows → PowerShell direto
                        is_local = server_name.lower() in ['localhost', '127.0.0.1', '.', ''] or server_name.lower() == os.environ.get('COMPUTERNAME', '').lower()
                        
                        if not is_local:
                            # Servidor REMOTO - usa Invoke-Command (requer WinRM)
                            if action['action_type'] == 'start':
                                ps_script = f"Invoke-Command -ComputerName '{server_name}' -ScriptBlock {{ Start-Service -Name '{service_name}' }}"
                            elif action['action_type'] == 'stop':
                                ps_script = f"Invoke-Command -ComputerName '{server_name}' -ScriptBlock {{ Stop-Service -Name '{service_name}' {force_flag} }}"
                            elif action['action_type'] == 'restart':
                                ps_script = f"Invoke-Command -ComputerName '{server_name}' -ScriptBlock {{ Restart-Service -Name '{service_name}' {force_flag} }}"
                            print(f"  🔧 Executando REMOTO ({server_name}): {ps_script}")
                        else:
                            print(f"  🔧 Executando LOCAL: {ps_script}")
                        
                        exec_command = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script]
                        
                        result = subprocess.run(
                            exec_command,
                            shell=False,
                            capture_output=True,
                            text=True,
                            encoding='utf-8',
                            errors='replace',
                            timeout=60,
                            env=env_vars
                        )
                        if result.returncode == 0:
                            success_count += 1
                            print(f"  ✅ {service_name}: {action['action_type']} executado com sucesso")
                            if result.stdout:
                                print(f"     📤 Output: {result.stdout.strip()}")
                        else:
                            print(f"  ❌ {service_name}: Erro - {result.stderr}")
                except Exception as e:
                    print(f"  ❌ {service_name}: Exceção - {str(e)}")
        
        # Atualizar last_run_at
        cursor.execute(
            "UPDATE service_actions SET last_run_at = %s WHERE id = %s",
            (now_local, action_id)
        )
        
        # Calcular next_run_at
        temp_schedule = {
            'schedule_type': action['schedule_type'],
            'schedule_config': action['schedule_config']
        }
        next_run = self._calculate_next_run(temp_schedule)
        
        # Se for execução única, desativar
        if action['schedule_type'] == 'once':
            cursor.execute(
                "UPDATE service_actions SET next_run_at = %s, is_active = FALSE WHERE id = %s",
                (next_run, action_id)
            )
            print(f"  ℹ️ Service action desativada (execução única)")
        else:
            cursor.execute(
                "UPDATE service_actions SET next_run_at = %s WHERE id = %s",
                (next_run, action_id)
            )
        
        print(f"  ⏰ Próxima execução: {next_run if next_run else 'N/A'}")

    def _calculate_next_run(self, schedule):
        """Calcula próxima execução baseado no tipo de schedule"""
        import json

        schedule_type = schedule['schedule_type']
        config = json.loads(schedule['schedule_config'])
        now = now_br()  # ✅ CORRETO: GMT-3 Brasil
        
        if schedule_type == 'once':
            # Execução única, sem próxima
            return None
        
        elif schedule_type == 'daily':
            # Diária: mesmo horário todo dia
            hour = config.get('hour', False)
            minute = config.get('minute', False)
            
            next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if next_run <= now:
                next_run += timedelta(days=1)
            
            return next_run
        
        elif schedule_type == 'weekly':
            # Semanal: dias específicos da semana
            weekdays = config.get('weekdays', [])  # 0=segunda, 6=domingo
            hour = config.get('hour', False)
            minute = config.get('minute', False)
            
            next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            
            # Procura próximo dia válido
            for i in range(8):  # Máximo 7 dias + 1
                candidate = next_run + timedelta(days=i)
                if candidate.weekday() in weekdays and candidate > now:
                    return candidate
            
            return None
        
        elif schedule_type == 'monthly':
            # Mensal: dia específico do mês
            day = config.get('day', True)
            hour = config.get('hour', False)
            minute = config.get('minute', False)
            
            # Tenta no mês atual
            try:
                next_run = now.replace(day=day, hour=hour, minute=minute, second=0, microsecond=0)
                if next_run > now:
                    return next_run
            except ValueError:
                pass  # Dia inválido no mês
            
            # Próximo mês
            if now.month == 12:
                next_month = now.replace(year=now.year + 1, month=1)
            else:
                next_month = now.replace(month=now.month + 1)
            
            try:
                return next_month.replace(day=day, hour=hour, minute=minute, second=0, microsecond=0)
            except ValueError:
                return None
        
        elif schedule_type == 'cron':
            # Cron expression (implementação simplificada)
            # Para produção, usar biblioteca como 'croniter'
            print(f"⚠️ Cron schedule não implementado ainda para schedule {schedule['id']}")
            return None
        
        return None

# Instância global do scheduler
pipeline_scheduler = None

app = Flask(__name__)
CORS(app)

# Configurações do PostgreSQL
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', '5432')),
    'database': os.getenv('DB_NAME', 'aturpo_devops'),
    'user': os.getenv('DB_USER', 'aturpo_user'),
    'password': os.getenv('DB_PASSWORD', 'aturpo_2024'),
    'client_encoding': 'UTF8'
}
CLONE_DIR = "cloned_repos"  # Nome da pasta onde os repositórios ficarão

# Flag para debug de conexões com banco de dados
DEBUG_DB = os.getenv('DEBUG_DB', 'false').lower() == 'true'

# =====================================================================
# FUNÇÕES DE BANCO DE DADOS
# =====================================================================


def get_db():
    """Conecta ao banco de dados PostgreSQL"""
    try:
        # Debug: mostrar configuracao (sem senha) - apenas se DEBUG_DB=true
        if DEBUG_DB:
            debug_config = {k: v for k, v in DB_CONFIG.items() if k != 'password'}
            print(f"[DEBUG] Tentando conectar ao PostgreSQL: {debug_config}")
        
        conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
        
        if DEBUG_DB:
            print("[OK] Conexao PostgreSQL estabelecida com sucesso")
        return conn
    except UnicodeDecodeError as e:
        debug_config = {k: v for k, v in DB_CONFIG.items() if k != 'password'}
        print(f"[ERRO] Erro de encoding ao conectar ao PostgreSQL:")
        print(f"  - Byte problematico: 0x{e.object[e.start]:02x} na posicao {e.start}")
        print(f"  - Encoding esperado: {e.encoding}")
        print(f"  - Verifique se o PostgreSQL esta configurado com UTF8")
        print(f"  - Config: {debug_config}")
        raise
    except psycopg2.OperationalError as e:
        debug_config = {k: v for k, v in DB_CONFIG.items() if k != 'password'}
        error_msg = str(e).lower()
        print(f"[ERRO] Erro ao conectar ao PostgreSQL: {e}")
        print(f"  - Config: {debug_config}")
        
        # Mensagens especificas por tipo de erro
        if 'does not exist' in error_msg or 'database' in error_msg:
            print(f"[DICA] O banco '{DB_CONFIG['database']}' nao existe!")
            print("[DICA] Execute a funcao init_db() para criar o banco e as tabelas")
        elif 'authentication failed' in error_msg or 'password' in error_msg:
            print("[DICA] Verifique o usuario e senha do PostgreSQL no config.env")
        elif 'connection refused' in error_msg or 'could not connect' in error_msg:
            print("[DICA] PostgreSQL nao esta rodando ou nao esta acessivel")
            print(f"[DICA] Verifique se o servidor esta em {DB_CONFIG['host']}:{DB_CONFIG['port']}")
        
        raise
        
    except PsycopgError as e:
        debug_config = {k: v for k, v in DB_CONFIG.items() if k != 'password'}
        print(f"[ERRO] Erro ao conectar ao PostgreSQL: {e}")
        print(f"  - Config: {debug_config}")
        raise
    except Exception as e:
        debug_config = {k: v for k, v in DB_CONFIG.items() if k != 'password'}
        print(f"[ERRO] Erro inesperado: {type(e).__name__}: {e}")
        print(f"  - Config: {debug_config}")
        raise

def create_database_if_not_exists():
    """
    Verifica se o banco de dados existe e cria se necessario.
    
    Esta funcao conecta ao banco 'postgres' (que sempre existe) para
    verificar se o banco da aplicacao existe. Se nao existir, cria.
    
    IMPORTANTE: O usuario PostgreSQL precisa ter permissao CREATEDB!
    
    Returns:
        bool: True se banco existe ou foi criado, False se falha
    """
    
    db_name = DB_CONFIG['database']
    
    print(f"[INFO] Verificando se o banco '{db_name}' existe...")
    
    # Configuracao para conectar ao banco 'postgres' (sempre existe)
    admin_config = DB_CONFIG.copy()
    admin_config['database'] = 'postgres'
    admin_config['client_encoding'] = 'UTF8'  # Forcar UTF-8'
    
    try:
        # Conectar ao banco postgres
        conn = psycopg2.connect(**admin_config)
        conn.autocommit = True  # Necessario para CREATE DATABASE
        
        # Forcar encoding UTF-8 na conexao (importante para Windows)
        try:
            conn.set_client_encoding('UTF8')
        except Exception as e:
            print(f"[AVISO] Nao foi possivel configurar encoding UTF8: {e}")
        
        cursor = conn.cursor()
        
        # Verificar se banco existe
        cursor.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            (db_name,)
        )
        exists = cursor.fetchone()
        
        if exists:
            print(f"[OK] Banco '{db_name}' ja existe")
            cursor.close()
            conn.close()
            return True
        
        # Banco nao existe, vamos criar
        print(f"[INFO] Banco '{db_name}' nao existe, criando...")
        
        # SQL para criar banco com encoding UTF8
        create_sql = f"""
            CREATE DATABASE {db_name}
            WITH OWNER = {DB_CONFIG['user']}
            ENCODING = 'UTF8'
            LC_COLLATE = 'C'
            LC_CTYPE = 'C'
            TEMPLATE = template0
        """
        
        cursor.execute(create_sql)
        print(f"[OK] Banco '{db_name}' criado com sucesso!")
        
        cursor.close()
        conn.close()
        
        return True
        
    except UnicodeDecodeError as e:
        print(f"[ERRO] Erro de encoding ao comunicar com PostgreSQL:")
        print(f"  - Byte problematico: 0x{e.object[e.start]:02x} na posicao {e.start}")
        print(f"[DICA] PostgreSQL no Windows pode estar com encoding incorreto")
        print(f"[DICA] Execute como admin PostgreSQL:")
        print(f"       ALTER DATABASE postgres SET client_encoding = 'UTF8';")
        return False
        
    except PsycopgError as e:
        error_msg = str(e).lower()
        
        # Verificar se é erro de permissão
        if 'permission denied' in error_msg or 'insufficient privilege' in error_msg or 'createdb' in error_msg:
            print(f"[ERRO] Usuario '{DB_CONFIG['user']}' nao tem permissao para criar bancos!")
            print(f"[DICA] Execute como admin PostgreSQL:")
            print(f"       ALTER USER {DB_CONFIG['user']} CREATEDB;")
            return False
        
        # Outros erros psycopg2
        print(f"[ERRO] Erro ao criar banco: {e}")
        return False
        
    except psycopg2.OperationalError as e:
        print(f"[ERRO] Nao foi possivel conectar ao PostgreSQL: {e}")
        print("[DICA] Verifique se o PostgreSQL esta rodando e acessivel")
        return False
        
    except Exception as e:
        print(f"[ERRO] Erro ao verificar/criar banco: {type(e).__name__}: {e}")
        return False

# =====================================================================
# FUNÇÕES AUXILIARES PARA BASE_DIR POR AMBIENTE
# =====================================================================

def get_base_dir_for_repo(cursor, repo_id):
    """
    Retorna o BASE_DIR correto baseado no ambiente do repositório.
    
    Args:
        cursor: Cursor do banco de dados
        repo_id: ID do repositório
        
    Returns:
        str: Caminho do BASE_DIR correspondente ao ambiente
    """
    
    # Busca environment_id do repositório
    repo = cursor.execute(
        "SELECT environment_id FROM repositories WHERE id = %s", (repo_id,)
    )
    repo = cursor.fetchone()
    
    if not repo:
        return CLONE_DIR  # Fallback para compatibilidade
    
    # Busca nome do ambiente
    env = cursor.execute(
        "SELECT name FROM environments WHERE id = %s", (repo['environment_id'],)
    )
    env = cursor.fetchone()
    
    if not env:
        return CLONE_DIR  # Fallback
    
    # Mapeia ambiente para sufixo
    suffix_map = {
        'Produção': 'PRD',
        'Homologação': 'HOM',
        'Desenvolvimento': 'DEV',
        'Testes': 'TST'
    }
    suffix = suffix_map.get(env['name'], 'PRD')
    
    # Busca variável BASE_DIR_{SUFFIX}
    base_dir_var = cursor.execute(
        "SELECT value FROM server_variables WHERE name = %s", (f"BASE_DIR_{suffix}",)
    )
    base_dir_var = cursor.fetchone()
    
    return base_dir_var["value"] if base_dir_var else CLONE_DIR


def get_base_dir_for_pipeline(cursor, pipeline_id):
    """
    Retorna o BASE_DIR correto baseado no ambiente da pipeline.
    
    Args:
        cursor: Cursor do banco de dados
        pipeline_id: ID da pipeline
        
    Returns:
        str: Caminho do BASE_DIR correspondente ao ambiente
    """
    
    # Busca environment_id da pipeline
    pipeline = cursor.execute(
        "SELECT environment_id FROM pipelines WHERE id = %s", (pipeline_id,)
    )
    pipeline = cursor.fetchone()
    
    if not pipeline:
        return CLONE_DIR  # Fallback
    
    # Busca nome do ambiente
    env = cursor.execute(
        "SELECT name FROM environments WHERE id = %s", (pipeline['environment_id'],)
    )
    env = cursor.fetchone()
    
    if not env:
        return CLONE_DIR  # Fallback
    
    # Mapeia ambiente para sufixo
    suffix_map = {
        'Produção': 'PRD',
        'Homologação': 'HOM',
        'Desenvolvimento': 'DEV',
        'Testes': 'TST'
    }
    suffix = suffix_map.get(env['name'], 'PRD')
    
    # Busca variável BASE_DIR_{SUFFIX}
    base_dir_var = cursor.execute(
        "SELECT value FROM server_variables WHERE name = %s", (f"BASE_DIR_{suffix}",)
    )
    base_dir_var = cursor.fetchone()
    
    return base_dir_var["value"] if base_dir_var else CLONE_DIR

def init_db():
    """Inicializa o banco de dados com as tabelas necessárias"""
    
    # Verificar/criar banco de dados antes de tentar conectar
    if not create_database_if_not_exists():
        print("❌ [ERRO] Nao foi possivel criar o banco de dados!")
        print("💡 [DICA] Crie o banco manualmente ou verifique permissoes do usuario")
        raise Exception("Banco de dados nao existe e nao pode ser criado")
    
    conn = get_db()
    cursor = conn.cursor()

    # (NOVO) Tabela de Ambientes
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS environments (
            id SERIAL PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            created_at TIMESTAMP NOT NULL
        )
        """
    )

    # Adiciona ambientes padrão se não existirem
    cursor.execute("SELECT COUNT(*) FROM environments")
    if cursor.fetchone()['count'] == 0:
        now = datetime.now()
        default_environments = [
            ('Produção', 'Ambiente de produção principal', now),
            ('Homologação', 'Ambiente de homologação para validações', now),
            ('Desenvolvimento', 'Ambiente para desenvolvimento de novas features', now),
            ('Testes', 'Ambiente para testes e QA', now)
        ]
        cursor.executemany(
            "INSERT INTO environments (name, description, created_at) VALUES (%s, %s, %s)",
            default_environments
        )
        print("✅ Ambientes padrão criados: Produção, Homologação, Desenvolvimento, Testes")

    # Tabela de Variáveis do Servidor
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS server_variables (
            id SERIAL PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            value TEXT NOT NULL,
            description TEXT,
            is_protected BOOLEAN DEFAULT FALSE,
            is_password BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP NOT NULL
        )
        """
    )
    # Adiciona a variável BASE_DIR como padrão para substituir a tabela antiga
    cursor.execute("SELECT COUNT(*) FROM server_variables")
    if cursor.fetchone()['count'] == 0:
        now = datetime.now()
        cursor.execute(
            "INSERT INTO server_variables (name, value, description, created_at) VALUES (%s, %s, %s, %s)",
            ('BASE_DIR', 'cloned_repos', 'Pasta raiz no servidor onde os repositórios são clonados.', now)
        )

    # =====================================================================
    # INSERIR VARIÁVEIS PADRÃO DO PROTHEUS (60 variáveis com sufixos)
    # =====================================================================
    cursor.execute("SELECT COUNT(*) FROM server_variables WHERE name LIKE '%_PRD' OR name LIKE '%_HOM' OR name LIKE '%_DEV' OR name LIKE '%_TST'")
    
    if cursor.fetchone()['count'] == 0:
        now = datetime.now()
        
        # Lista de variáveis base
        base_variables = [
            ('BASE_DIR', 'Diretório base para clone de repositórios Git'),
            ('BUILD_DIR', 'Diretório de build/compilação'),
            ('FONTES_DIR', 'Diretório dos fontes .prw, .tlpp, .prx'),
            ('INCLUDE_DIR', 'Diretório de includes do Protheus'),
            ('LOG_DIR', 'Diretório de logs'),
            ('BASE_DIR_PATCHES', 'Diretório base para patches'),
            ('PASTA_APO', 'Pasta onde ficam os RPOs dos servidores'),
            ('PASTA_CMP', 'Pasta de compilação onde está o RPO compilado'),
            ('PASTA_BIN', 'Pasta dos binários do Protheus (appserver.ini)'),
            ('PROTHEUS_SERVER', 'Servidor Protheus (ex: localhost ou IP)'),
            ('PROTHEUS_PORT', 'Porta do servidor Protheus (ex: 1234)'),
            ('PROTHEUS_SECURE', 'Conexão segura: 0 para não, 1 para sim'),
            ('PROTHEUS_BUILD', 'Build do Protheus (ex: 7.00.240223P)'),
            ('PROTHEUS_ENV', 'Ambiente do Protheus (ex: protheus_cmp)'),
            ('PROTHEUS_USER', 'Usuário do Protheus para compilação'),
            ('PROTHEUS_PASSWORD', 'Senha do usuário Protheus'),
            ('SSH_HOST_WINDOWS', 'Host/IP do servidor Windows para conexão SSH'),
            ('SSH_USER_WINDOWS', 'Usuário SSH para conectar no servidor Windows'),
            ('SSH_PORT_WINDOWS', 'Porta SSH do servidor Windows (padrão: 22)'),
        ]
        
        # Sufixos dos ambientes
        environments_suffixes = [
            ('PRD', 'Produção', '/producao', '\\\\servidor-prd'),
            ('HOM', 'Homologação', '/homologacao', '\\\\servidor-hom'),
            ('DEV', 'Desenvolvimento', '/desenvolvimento', '\\\\servidor-dev'),
            ('TST', 'Testes', '/testes', '\\\\servidor-tst'),
        ]
        
        # Mapeamento de valores exemplo por tipo de variável
        def get_placeholder_value(var_name, suffix, linux_path, windows_path):
            """Gera valor placeholder baseado no tipo de variável e ambiente"""
            
            if var_name == 'BASE_DIR':
                return f"{linux_path}/git-repos"
            
            elif var_name in ['BUILD_DIR', 'FONTES_DIR', 'INCLUDE_DIR', 'LOG_DIR', 'BASE_DIR_PATCHES', 'PASTA_CMP']:
                return f"{linux_path}/{var_name.lower().replace('_dir', '').replace('_', '-')}"
            
            elif var_name == 'PASTA_APO':
                return f"{windows_path}\\apo"
            
            elif var_name == 'PASTA_BIN':
                return f"{windows_path}\\bin"
            
            elif var_name == 'PROTHEUS_SERVER':
                return f"servidor-{suffix.lower()}" if suffix != 'PRD' else 'localhost'
            
            elif var_name == 'PROTHEUS_PORT':
                port_map = {'PRD': '1234', 'HOM': '1235', 'DEV': '1236', 'TST': '1237'}
                return port_map[suffix]
            
            elif var_name == 'PROTHEUS_SECURE':
                return '0'
            
            elif var_name == 'PROTHEUS_BUILD':
                return '7.00.240223P'
            
            elif var_name == 'PROTHEUS_ENV':
                env_map = {'PRD': 'protheus_prd', 'HOM': 'protheus_hom', 'DEV': 'protheus_dev', 'TST': 'protheus_tst'}
                return env_map[suffix]
            
            elif var_name == 'PROTHEUS_USER':
                return 'admin'
            
            elif var_name == 'PROTHEUS_PASSWORD':
                return 'senha123'
            
            elif var_name == 'SSH_HOST_WINDOWS':
                host_map = {'PRD': '192.168.0.1', 'HOM': '192.168.0.2', 'DEV': '192.168.0.3', 'TST': '192.168.0.4'}
                return host_map[suffix]
            
            elif var_name == 'SSH_USER_WINDOWS':
                return 'administrador'
            
            elif var_name == 'SSH_PORT_WINDOWS':
                return '22'
            
            return f"/caminho/para/{var_name.lower()}"
        
        # Gera as 64 variáveis (16 × 4 ambientes)
        all_variables = []
        for suffix, env_name, linux_path, windows_path in environments_suffixes:
            for var_name, var_description in base_variables:
                full_var_name = f"{var_name}_{suffix}"
                placeholder_value = get_placeholder_value(var_name, suffix, linux_path, windows_path)
                full_description = f"[{env_name}] {var_description}"
                
                # PROTHEUS_PASSWORD deve ter is_password=TRUE
                is_password_field = (var_name == 'PROTHEUS_PASSWORD')
                all_variables.append((full_var_name, placeholder_value, full_description, True, is_password_field, now))
        
        # Insere todas as variáveis
        cursor.executemany(
            "INSERT INTO server_variables (name, value, description, is_protected, is_password, created_at) VALUES (%s, %s, %s, %s, %s, %s)",
            all_variables
        )
        print(f"✅ {len(all_variables)} variáveis padrão do Protheus inseridas com sucesso!")
        
    # (NOVA) Tabela de Serviços do Servidor
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS server_services (
            id SERIAL PRIMARY KEY,
            environment_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            display_name TEXT,
            server_name TEXT NOT NULL,
            description TEXT,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP NOT NULL,
            FOREIGN KEY (environment_id) REFERENCES environments(id) ON DELETE CASCADE
        )
        """
    )

    # Tabela de Usuários
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(255) UNIQUE NOT NULL,
            name VARCHAR(255) NOT NULL,
            email VARCHAR(255) NOT NULL,
            password VARCHAR(255) NOT NULL,
            password_salt VARCHAR(255),
            profile VARCHAR(50) NOT NULL,
            active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP NOT NULL,
            last_login TIMESTAMP,
            session_token VARCHAR(255),
            last_activity TIMESTAMP,
            session_timeout_minutes INTEGER DEFAULT 0 
        )
    """
    )

    # (ATUALIZADO) Tabela de Repositórios
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS repositories (
            id SERIAL PRIMARY KEY,
            environment_id INTEGER NOT NULL,
            github_id INTEGER, name VARCHAR(255) NOT NULL, full_name VARCHAR(255), description TEXT,
            private BOOLEAN, html_url TEXT, clone_url TEXT, language VARCHAR(100),
            default_branch VARCHAR(100), size INTEGER, updated_at TIMESTAMP, created_at TIMESTAMP,
            FOREIGN KEY (environment_id) REFERENCES environments (id) ON DELETE CASCADE
        )
        """
    )

    # (ATUALIZADO) Tabela de Comandos
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS commands (
            id SERIAL PRIMARY KEY,
            environment_id INTEGER NOT NULL,
            name VARCHAR(255) NOT NULL,
            command_category VARCHAR(50) NOT NULL DEFAULT 'build',
            type VARCHAR(50) NOT NULL,
            description TEXT,
            script TEXT NOT NULL,
            is_protected BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP,
            last_executed TIMESTAMP,
            FOREIGN KEY (environment_id) REFERENCES environments (id) ON DELETE CASCADE,
            CHECK (command_category IN ('build', 'deploy'))
        )
        """
    )

    # (ATUALIZADO) Tabela de Deploys
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS deploys (
            id SERIAL PRIMARY KEY,
            environment_id INTEGER NOT NULL,
            name VARCHAR(255) NOT NULL, description TEXT, command_id INTEGER NOT NULL,
            created_at TIMESTAMP,
            FOREIGN KEY (environment_id) REFERENCES environments (id) ON DELETE CASCADE,
            FOREIGN KEY (command_id) REFERENCES commands (id) ON DELETE CASCADE
        )
        """
    )
    
    # =====================================================================
    # INSERIR COMANDOS PADRÃO (24 comandos = 6 scripts × 4 ambientes)
    # =====================================================================
    
    # Busca IDs dos ambientes
    cursor.execute("SELECT id, name FROM environments ORDER BY name")
    environments_map = {row['name']: row['id'] for row in cursor.fetchall()}
    
    # Mapeamento de sufixos
    suffix_map = {
        'Produção': 'PRD',
        'Homologação': 'HOM',
        'Desenvolvimento': 'DEV',
        'Testes': 'TST'
    }
    
    # Verifica se já existem comandos padrão
    cursor.execute("SELECT COUNT(*) FROM commands WHERE name LIKE '%Apply Patches%' OR name LIKE '%Compilar Fontes%' OR name LIKE '%Troca Quente%'")
    
    if cursor.fetchone()['count'] == 0:
        now = datetime.now()
        
        # ===== SCRIPT 1: apply_patch.ps1 (BUILD) =====
        apply_patch_ps1_template = '''# ==============================================================================
# Script de aplicação de patches Protheus para ambiente Windows (PowerShell)
# ==============================================================================

# --- CONFIGURAÇÕES DE DIRETÓRIOS ---
$BASE_DIR_PATCHES = "${BASE_DIR_PATCHES_{{SUFFIX}}}"
$BUILD_DIR = "${BUILD_DIR_{{SUFFIX}}}"

# --- CONFIGURAÇÕES DO SERVIDOR PROTHEUS ---
$PROTHEUS_SERVER = "${PROTHEUS_SERVER_{{SUFFIX}}}"
$PROTHEUS_PORT = "${PROTHEUS_PORT_{{SUFFIX}}}"
$PROTHEUS_SECURE = "${PROTHEUS_SECURE_{{SUFFIX}}}"
$PROTHEUS_BUILD = "${PROTHEUS_BUILD_{{SUFFIX}}}"
$PROTHEUS_ENV = "${PROTHEUS_ENV_{{SUFFIX}}}"
$PROTHEUS_USER = "${PROTHEUS_USER_{{SUFFIX}}}"
$PROTHEUS_PASSWORD = "${PROTHEUS_PASSWORD_{{SUFFIX}}}"

# --- DEFINIÇÃO DAS PASTAS ---
$PENDENTES_DIR = "$BASE_DIR_PATCHES\\pendentes"
$ZIPS_PROCESSADOS_DIR = "$BASE_DIR_PATCHES\\zips_processados"
$APLICADOS_DIR = "$BASE_DIR_PATCHES\\aplicados"
$OUTPUT_INI_FILE = "$BUILD_DIR\\apply_patches.ini"
$LOG_FILE = "$BUILD_DIR\\apply_patch.log"
$ADVPLS_EXECUTABLE = "$BUILD_DIR\\advpls.exe"

# --- INÍCIO DO SCRIPT ---
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "📦 Extraindo arquivos ZIP da pasta pendentes..." -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan

$zip_files = Get-ChildItem -Path $PENDENTES_DIR -Filter "*.zip" -File

if ($zip_files.Count -gt 0) {
    Write-Host "✅ Encontrados $($zip_files.Count) arquivos ZIP para extração" -ForegroundColor Green
    if (-not (Test-Path $ZIPS_PROCESSADOS_DIR)) {
        New-Item -ItemType Directory -Path $ZIPS_PROCESSADOS_DIR -Force | Out-Null
    }
    foreach ($zip_file in $zip_files) {
        Write-Host "📄 Extraindo: $($zip_file.Name)" -ForegroundColor Yellow
        Expand-Archive -Path $zip_file.FullName -DestinationPath $PENDENTES_DIR -Force
        Move-Item -Path $zip_file.FullName -Destination $ZIPS_PROCESSADOS_DIR -Force
    }
    Write-Host "🎉 Extração de arquivos ZIP concluída" -ForegroundColor Green
} else {
    Write-Host "⚠️ Nenhum arquivo ZIP encontrado para extração" -ForegroundColor Yellow
}

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "📄 Gerando script com lista de patches..." -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan

if (-not (Test-Path $PENDENTES_DIR)) {
    Write-Host "❌ Pasta de patches não encontrada: $PENDENTES_DIR" -ForegroundColor Red
    Write-Host "🔨 Criando a pasta..." -ForegroundColor Yellow
    New-Item -ItemType Directory -Path $PENDENTES_DIR -Force | Out-Null
    Write-Host "📁 Pasta criada. Por favor, coloque os arquivos de patch na pasta e execute novamente." -ForegroundColor Green
    exit 1
}

$patch_files = Get-ChildItem -Path $PENDENTES_DIR -Filter "*.PTM" -File | Sort-Object Name

if ($patch_files.Count -eq 0) {
    Write-Host "⚠️ Nenhum arquivo de patch PTM encontrado na pasta: $PENDENTES_DIR" -ForegroundColor Yellow
    exit 0
}

Write-Host "📋 Encontrados $($patch_files.Count) arquivos de patch" -ForegroundColor Green

$iniContent = @"
logToFile=$LOG_FILE
showConsoleOutput=true

;Sessão de Autenticação
[authentication]
action=authentication
server=$PROTHEUS_SERVER
port=$PROTHEUS_PORT
secure=$PROTHEUS_SECURE
build=$PROTHEUS_BUILD
environment=$PROTHEUS_ENV
user=$PROTHEUS_USER
psw=$PROTHEUS_PASSWORD

;Sessões para aplicar os patches no rpo, geradas automaticamente
"@

$session_number = 1
foreach ($patch_file in $patch_files) {
    $iniContent += @"

[patchApply_$session_number]
action=patchApply
patchFile=$($patch_file.FullName)
localPatch=True
applyOldProgram=False
"@
    $session_number++
}

$iniContent += @"

;Sessão que faz defrag do rpo
[defragRPO]
action=defragRPO
"@

$iniContent | Out-File -FilePath $OUTPUT_INI_FILE -Encoding Default -Force

Write-Host "✅ Arquivo INI gerado com sucesso: $OUTPUT_INI_FILE" -ForegroundColor Green
Write-Host "📊 Total de sessões de patch: $($patch_files.Count)" -ForegroundColor Green

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "🔧 Aplicando patches..." -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan

if (-not (Test-Path $ADVPLS_EXECUTABLE)) {
    Write-Host "❌ Executável não encontrado em: $ADVPLS_EXECUTABLE" -ForegroundColor Red
    Write-Host "Verifique a variável BUILD_DIR no sistema." -ForegroundColor Yellow
    exit 1
}

& $ADVPLS_EXECUTABLE cli $OUTPUT_INI_FILE

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "=========================================" -ForegroundColor Red
    Write-Host "❌ ERRO ao aplicar patches! O advpls retornou código de erro." -ForegroundColor Red
    Write-Host "Verifique os logs acima para mais detalhes." -ForegroundColor Yellow
    Write-Host "=========================================" -ForegroundColor Red
    exit 1
}

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "🧹 Limpando arquivos de patches..." -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan

if (-not (Test-Path $APLICADOS_DIR)) {
    New-Item -ItemType Directory -Path $APLICADOS_DIR -Force | Out-Null
}

Get-ChildItem -Path $PENDENTES_DIR -Filter "*.ptm" -File | Move-Item -Destination $APLICADOS_DIR -Force
Write-Host "Arquivos .ptm movidos para $APLICADOS_DIR" -ForegroundColor Green

Get-ChildItem -Path $PENDENTES_DIR -Recurse | Remove-Item -Force -Recurse
Write-Host "Arquivos restantes em $PENDENTES_DIR foram removidos." -ForegroundColor Green

Write-Host "✅ Processo concluído." -ForegroundColor Green'''

        # ===== SCRIPT 2: apply_patch.sh (BUILD) =====
        apply_patch_sh_template = '''#!/bin/bash

# ==============================================================================
# Script de aplicação de patches Protheus para ambiente Linux (Bash)
# ==============================================================================

# --- CONFIGURAÇÕES DE DIRETÓRIOS ---
BASE_DIR_PATCHES="${BASE_DIR_PATCHES_{{SUFFIX}}}"
BUILD_DIR="${BUILD_DIR_{{SUFFIX}}}"

# --- CONFIGURAÇÕES DO SERVIDOR PROTHEUS ---
PROTHEUS_SERVER="${PROTHEUS_SERVER_{{SUFFIX}}}"
PROTHEUS_PORT="${PROTHEUS_PORT_{{SUFFIX}}}"
PROTHEUS_SECURE="${PROTHEUS_SECURE_{{SUFFIX}}}"
PROTHEUS_BUILD="${PROTHEUS_BUILD_{{SUFFIX}}}"
PROTHEUS_ENV="${PROTHEUS_ENV_{{SUFFIX}}}"
PROTHEUS_USER="${PROTHEUS_USER_{{SUFFIX}}}"
PROTHEUS_PASSWORD="${PROTHEUS_PASSWORD_{{SUFFIX}}}"

# --- DEFINIÇÃO DAS PASTAS ---
PENDENTES_DIR="$BASE_DIR_PATCHES/pendentes"
ZIPS_PROCESSADOS_DIR="$BASE_DIR_PATCHES/zips_processados"
APLICADOS_DIR="$BASE_DIR_PATCHES/aplicados"
OUTPUT_INI_FILE="$BUILD_DIR/apply_patches.ini"
LOG_FILE="$BUILD_DIR/apply_patch.log"
ADVPLS_EXECUTABLE="$BUILD_DIR/advpls"

# --- INÍCIO DO SCRIPT ---
echo "========================================="
echo "📦 Extraindo arquivos ZIP da pasta pendentes..."
echo "========================================="

zip_files=$(find "$PENDENTES_DIR" -maxdepth 1 -type f -iname "*.zip")

if [ -n "$zip_files" ]; then
    file_count=$(echo "$zip_files" | wc -l)
    echo "✅ Encontrados $file_count arquivos ZIP para extração"
    mkdir -p "$ZIPS_PROCESSADOS_DIR"
    echo "$zip_files" | while read -r zip_file; do
        filename=$(basename "$zip_file")
        echo "📄 Extraindo: $filename"
        unzip -o "$zip_file" -d "$PENDENTES_DIR"
        mv "$zip_file" "$ZIPS_PROCESSADOS_DIR/"
    done
    echo "🎉 Extração de arquivos ZIP concluída"
else
    echo "⚠️ Nenhum arquivo ZIP encontrado para extração"
fi

echo "========================================="
echo "📄 Gerando script com lista de patches..."
echo "========================================="

if [ ! -d "$PENDENTES_DIR" ]; then
    echo "❌ Pasta de patches não encontrada: $PENDENTES_DIR"
    echo "🔨 Criando a pasta..."
    mkdir -p "$PENDENTES_DIR"
    echo "📁 Pasta criada. Por favor, coloque os arquivos de patch na pasta e execute novamente."
    exit 1
fi

patch_files=$(find "$PENDENTES_DIR" -maxdepth 1 -type f -iname "*.PTM" | sort)

if [ -z "$patch_files" ]; then
    echo "⚠️ Nenhum arquivo de patch PTM encontrado na pasta: $PENDENTES_DIR"
    exit 0
fi

patch_count=$(echo "$patch_files" | wc -l)
echo "📋 Encontrados $patch_count arquivos de patch"

cat > "$OUTPUT_INI_FILE" << EOF
logToFile=$LOG_FILE
showConsoleOutput=true

;Sessão de Autenticação
[authentication]
action=authentication
server=$PROTHEUS_SERVER
port=$PROTHEUS_PORT
secure=$PROTHEUS_SECURE
build=$PROTHEUS_BUILD
environment=$PROTHEUS_ENV
user=$PROTHEUS_USER
psw=$PROTHEUS_PASSWORD

;Sessões para aplicar os patches no rpo, geradas automaticamente
EOF

session_number=1
echo "$patch_files" | while read -r patch_file; do
    cat >> "$OUTPUT_INI_FILE" << EOF

[patchApply_$session_number]
action=patchApply
patchFile=$patch_file
localPatch=True
applyOldProgram=False
EOF
    ((session_number++))
done

cat >> "$OUTPUT_INI_FILE" << EOF

;Sessão que faz defrag do rpo
[defragRPO]
action=defragRPO
EOF

echo "✅ Arquivo INI gerado com sucesso: $OUTPUT_INI_FILE"
echo "📊 Total de sessões de patch: $patch_count"

echo "========================================="
echo "🔧 Aplicando patches..."
echo "========================================="

if [ ! -f "$ADVPLS_EXECUTABLE" ]; then
    echo "❌ Executável não encontrado em: $ADVPLS_EXECUTABLE"
    echo "Verifique a variável BUILD_DIR no sistema."
    exit 1
fi

"$ADVPLS_EXECUTABLE" cli "$OUTPUT_INI_FILE"

if [ $? -ne 0 ]; then
    echo ""
    echo "========================================="
    echo "❌ ERRO ao aplicar patches! O advpls retornou código de erro."
    echo "Verifique os logs acima para mais detalhes."
    echo "========================================="
    exit 1
fi

echo "========================================="
echo "🧹 Limpando arquivos de patches..."
echo "========================================="

mkdir -p "$APLICADOS_DIR"

find "$PENDENTES_DIR" -maxdepth 1 -type f -iname "*.ptm" -exec mv -t "$APLICADOS_DIR/" {} +
echo "Arquivos .ptm movidos para $APLICADOS_DIR"

rm -R -f "$PENDENTES_DIR"/*
echo "Arquivos restantes em $PENDENTES_DIR foram removidos."

echo "✅ Processo concluído."'''

        # ===== SCRIPT 3: compila.ps1 (BUILD) =====
        compila_ps1_template = '''# ==============================================================================
# Script de compilação de fontes Protheus para ambiente Windows (PowerShell)
# ==============================================================================

# --- CONFIGURAÇÕES DE DIRETÓRIOS ---
$BUILD_DIR = "${BUILD_DIR_{{SUFFIX}}}"
$FONTES_DIR = "${FONTES_DIR_{{SUFFIX}}}"
$INCLUDE_DIR = "${INCLUDE_DIR_{{SUFFIX}}}"
$LOG_DIR = "${LOG_DIR_{{SUFFIX}}}"

# --- CONFIGURAÇÕES DO SERVIDOR PROTHEUS ---
$PROTHEUS_SERVER = "${PROTHEUS_SERVER_{{SUFFIX}}}"
$PROTHEUS_PORT = "${PROTHEUS_PORT_{{SUFFIX}}}"
$PROTHEUS_SECURE = "${PROTHEUS_SECURE_{{SUFFIX}}}"
$PROTHEUS_BUILD = "${PROTHEUS_BUILD_{{SUFFIX}}}"
$PROTHEUS_ENV = "${PROTHEUS_ENV_{{SUFFIX}}}"
$PROTHEUS_USER = "${PROTHEUS_USER_{{SUFFIX}}}"
$PROTHEUS_PASSWORD = "${PROTHEUS_PASSWORD_{{SUFFIX}}}"

# --- DEFINIÇÃO DE ARQUIVOS ---
$LST_FILE = "$BUILD_DIR\\compila.txt"
$INI_FILE = "$BUILD_DIR\\compila.ini"
$LOG_FILE = "$LOG_DIR\\compila.log"
$ADVPLS_EXE = "$BUILD_DIR\\advpls.exe"

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host " 🔄 GERANDO LISTA DE FONTES" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan

if (Test-Path $LST_FILE) {
    Remove-Item $LST_FILE -Force
}

# Verifica variações de extensão automaticamente
Get-ChildItem -Path "$FONTES_DIR\\*.prw", "$FONTES_DIR\\*.tlpp", "$FONTES_DIR\\*.prx" | 
    Select-Object -ExpandProperty Name | 
    Out-File -FilePath $LST_FILE -Encoding Default

Write-Host "✅ Lista de fontes gerada: $LST_FILE" -ForegroundColor Green

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host " 📄 GERANDO ARQUIVO DE CONFIGURAÇÃO" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan

$iniContent = @"
logToFile=$LOG_FILE
showConsoleOutput=true

[user]
INCLUDE_DIR=$INCLUDE_DIR
LOG_DIR=$LOG_DIR
BUILD_DIR=$BUILD_DIR

[authentication]
action=authentication
server=$PROTHEUS_SERVER
port=$PROTHEUS_PORT
secure=$PROTHEUS_SECURE
build=$PROTHEUS_BUILD
environment=$PROTHEUS_ENV
user=$PROTHEUS_USER
psw=$PROTHEUS_PASSWORD

;Compila somente fontes diferentes do rpo
[compile]
action=compile
recompile=F
programlist=$LST_FILE
includes=$INCLUDE_DIR

;faz defrag do rpo
[defragRPO]
action=defragRPO
"@

$iniContent | Out-File -FilePath $INI_FILE -Encoding Default -Force

Write-Host "✅ Arquivo INI gerado com sucesso: $INI_FILE" -ForegroundColor Green

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host " 🔧 COMPILANDO FONTES" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan

if (-not (Test-Path $ADVPLS_EXE)) {
    Write-Host "❌ Executável não encontrado: $ADVPLS_EXE" -ForegroundColor Red
    Write-Host "Verifique a variável BUILD_DIR no sistema." -ForegroundColor Yellow
    exit 1
}

Push-Location -Path "$FONTES_DIR"
& $ADVPLS_EXE cli $INI_FILE
Pop-Location

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "=========================================" -ForegroundColor Red
    Write-Host "❌ ERRO na compilação! O advpls retornou código de erro." -ForegroundColor Red
    Write-Host "Verifique os logs acima para mais detalhes." -ForegroundColor Yellow
    Write-Host "=========================================" -ForegroundColor Red
    exit 1
}

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "✅ Processo de compilação concluído! 🎉" -ForegroundColor Green
Write-Host "=========================================" -ForegroundColor Cyan'''

        # ===== SCRIPT 4: compila.sh (BUILD) =====
        compila_sh_template = '''#!/bin/bash

# ==============================================================================
# Script de compilação de fontes Protheus para ambiente Linux (Bash)
# ==============================================================================

# --- CONFIGURAÇÕES DE DIRETÓRIOS ---
BUILD_DIR="${BUILD_DIR_{{SUFFIX}}}"
FONTES_DIR="${FONTES_DIR_{{SUFFIX}}}"
INCLUDE_DIR="${INCLUDE_DIR_{{SUFFIX}}}"
LOG_DIR="${LOG_DIR_{{SUFFIX}}}"

# --- CONFIGURAÇÕES DO SERVIDOR PROTHEUS ---
PROTHEUS_SERVER="${PROTHEUS_SERVER_{{SUFFIX}}}"
PROTHEUS_PORT="${PROTHEUS_PORT_{{SUFFIX}}}"
PROTHEUS_SECURE="${PROTHEUS_SECURE_{{SUFFIX}}}"
PROTHEUS_BUILD="${PROTHEUS_BUILD_{{SUFFIX}}}"
PROTHEUS_ENV="${PROTHEUS_ENV_{{SUFFIX}}}"
PROTHEUS_USER="${PROTHEUS_USER_{{SUFFIX}}}"
PROTHEUS_PASSWORD="${PROTHEUS_PASSWORD_{{SUFFIX}}}"

# --- DEFINIÇÃO DE ARQUIVOS ---
LST_FILE="$BUILD_DIR/compila.txt"
INI_FILE="$BUILD_DIR/compila.ini"
LOG_FILE="$LOG_DIR/compila.log"
ADVPLS_EXE="$BUILD_DIR/advpls"

echo "========================================="
echo " 🔄 GERANDO LISTA DE FONTES"
echo "========================================="

rm -f "$LST_FILE"

cd "$FONTES_DIR" || exit 1
find . -maxdepth 1 -type f \\( -iname "*.prw" -o -iname "*.tlpp" -o -iname "*.prx" \\) -printf "%f\\n" > "$LST_FILE"

echo "✅ Lista de fontes gerada: $LST_FILE"

echo "========================================="
echo " 📄 GERANDO ARQUIVO DE CONFIGURAÇÃO"
echo "========================================="

cat > "$INI_FILE" << EOF
logToFile=$LOG_FILE
showConsoleOutput=true

[user]
INCLUDE_DIR=$INCLUDE_DIR
LOG_DIR=$LOG_DIR
BUILD_DIR=$BUILD_DIR

[authentication]
action=authentication
server=$PROTHEUS_SERVER
port=$PROTHEUS_PORT
secure=$PROTHEUS_SECURE
build=$PROTHEUS_BUILD
environment=$PROTHEUS_ENV
user=$PROTHEUS_USER
psw=$PROTHEUS_PASSWORD

;Compila somente fontes diferentes do rpo
[compile]
action=compile
recompile=F
programlist=$LST_FILE
includes=$INCLUDE_DIR

;faz defrag do rpo
[defragRPO]
action=defragRPO
EOF

echo "✅ Arquivo INI gerado com sucesso: $INI_FILE"

echo "========================================="
echo " 🔧 COMPILANDO FONTES"
echo "========================================="

if [ ! -f "$ADVPLS_EXE" ]; then
    echo "❌ Executável não encontrado: $ADVPLS_EXE"
    echo "Verifique a variável BUILD_DIR no sistema."
    exit 1
fi

"$ADVPLS_EXE" cli "$INI_FILE"

if [ $? -ne 0 ]; then
    echo ""
    echo "========================================="
    echo "❌ ERRO na compilação! O advpls retornou código de erro."
    echo "Verifique os logs acima para mais detalhes."
    echo "========================================="
    exit 1
fi

echo "========================================="
echo "✅ Processo de compilação concluído! 🎉"
echo "========================================="'''

        # ===== SCRIPT 5: tq.ps1 (DEPLOY) =====
        tq_ps1_template = '''# ==============================================================================
# Script de Troca Quente (TQ) do RPO Protheus para ambiente Windows (PowerShell)
# ==============================================================================

Write-Host "--------------------------------------------------------------------------" -ForegroundColor Yellow
Write-Host "ATENCAO: Toda vez que esse script for executado, a pasta destino do RPO" -ForegroundColor Yellow
Write-Host "sempre sera criada pois ele busca a data e hora atual do sistema para" -ForegroundColor Yellow
Write-Host "nomear a pasta e busca a pasta atual do RPO para substituicao nos appserver.ini" -ForegroundColor Yellow
Write-Host "Execute com precisao e cuidado!" -ForegroundColor Yellow
Write-Host "--------------------------------------------------------------------------" -ForegroundColor Yellow

# --- CONFIGURAÇÕES DE DIRETÓRIOS ---
$PASTA_APO = "${PASTA_APO_{{SUFFIX}}}"
$PASTA_CMP = "${PASTA_CMP_{{SUFFIX}}}"
$PASTA_BIN = "${PASTA_BIN_{{SUFFIX}}}"

# Verifica se a pasta alvo existe
if (-not (Test-Path $PASTA_APO)) {
    Write-Host "Erro: O diretório PASTA_APO não foi encontrado em: $PASTA_APO" -ForegroundColor Red
    exit 1
}

# Procura o diretório mais recente que começa com '202'
Write-Host "Procurando o diretorio mais recente em: $PASTA_APO" -ForegroundColor Cyan

$anoAtual = (Get-Date).Year.ToString().Substring(0, 3) # Pega "202" ou "203" etc
$diretorios = Get-ChildItem -Path $PASTA_APO -Directory -Filter "${anoAtual}*" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

if (-not $diretorios) {
    Write-Host "Erro: Nenhum diretório começando com '202' foi encontrado em $PASTA_APO" -ForegroundColor Red
    exit 1
}

$ORIGEM = $diretorios.Name

# Obtém a data e hora atual no formato desejado
$DESTINO = Get-Date -Format "yyyyMMdd_HHmm"

# Mostra em tela as pastas que serão atualizadas
Write-Host "-------------------------------------------" -ForegroundColor Cyan
Write-Host "Pasta de ORIGEM: $ORIGEM" -ForegroundColor Green
Write-Host "-------------------------------------------" -ForegroundColor Cyan
Write-Host "-------------------------------------------" -ForegroundColor Cyan
Write-Host "Pasta de DESTINO: $DESTINO" -ForegroundColor Green
Write-Host "-------------------------------------------" -ForegroundColor Cyan

Write-Host "REALIZANDO COPIA DO RPO COMPILACAO PARA SERVIDORES PROTHEUS..." -ForegroundColor Yellow

# Cria o diretório de destino
$PASTA_DESTINO = Join-Path $PASTA_APO $DESTINO
New-Item -ItemType Directory -Path $PASTA_DESTINO -Force | Out-Null

# Copia os arquivos RPO para o novo diretório de destino
Copy-Item -Path "$PASTA_CMP\\tttm120.rpo" -Destination $PASTA_DESTINO -Force
Copy-Item -Path "$PASTA_CMP\\custom.rpo" -Destination $PASTA_DESTINO -Force

Write-Host "Arquivos RPO copiados com sucesso!" -ForegroundColor Green

Write-Host "REALIZANDO TQ..." -ForegroundColor Yellow
Write-Host "Buscando arquivos appserver*.ini em $PASTA_BIN e subdiretórios..." -ForegroundColor Cyan

# Localiza os arquivos .ini RECURSIVAMENTE e substitui a string
$arquivosEncontrados = Get-ChildItem -Path $PASTA_BIN -Filter "appserver*.ini" -File -Recurse

if ($arquivosEncontrados) {
    Write-Host "Arquivos encontrados: $($arquivosEncontrados.Count)" -ForegroundColor Cyan
    
    $arquivosEncontrados | ForEach-Object {
        Write-Host "`nProcessando: $($_.FullName)" -ForegroundColor Yellow
        
        $conteudo = Get-Content $_.FullName -Raw
        
        # Verifica se encontrou a string de origem
        if ($conteudo -match [regex]::Escape($ORIGEM)) {
            Write-Host "  Substituindo '$ORIGEM' por '$DESTINO'" -ForegroundColor Yellow
            $conteudo = $conteudo -replace [regex]::Escape($ORIGEM), $DESTINO
            $conteudo | Set-Content $_.FullName -Force
            Write-Host "  Atualizado com sucesso!" -ForegroundColor Green
        } else {
            Write-Host "  String '$ORIGEM' nao encontrada (arquivo pode ja estar atualizado)" -ForegroundColor Gray
        }
    }
} else {
    Write-Host "NENHUM arquivo appserver*.ini encontrado!" -ForegroundColor Red
    Write-Host "Verifique o caminho: $PASTA_BIN" -ForegroundColor Yellow
}

Write-Host "`nPROCESSO CONCLUIDO!" -ForegroundColor Green'''

        # ===== SCRIPT 6: tq.sh (DEPLOY) =====
        tq_sh_template = '''#!/bin/bash

# ==============================================================================
# Script de Troca Quente (TQ) do RPO Protheus para ambiente Linux (Bash)
# ==============================================================================

echo "--------------------------------------------------------------------------"
echo "ATENCAO: Toda vez que esse script for executado, a pasta destino do RPO"
echo "sempre sera criada pois ele busca a data e hora atual do sistema para"
echo "nomear a pasta e busca a pasta atual do RPO para substituicao nos appserver.ini"
echo "Execute com precisao e cuidado!"
echo "--------------------------------------------------------------------------"

# --- CONFIGURAÇÕES DE DIRETÓRIOS ---
PASTA_APO="${PASTA_APO_{{SUFFIX}}}"
PASTA_CMP="${PASTA_CMP_{{SUFFIX}}}"
PASTA_BIN="${PASTA_BIN_{{SUFFIX}}}"

if [ ! -d "$PASTA_APO" ]; then
    echo "Erro: O diretório PASTA_APO não foi encontrado em: $PASTA_APO"
    exit 1
fi

echo "Procurando o diretorio mais recente em: $PASTA_APO"
ANO_ATUAL=$(date +'%Y' | cut -c1-3)  # Pega "202" ou "203" etc
DIRETORIO_MAIS_RECENTE=$(ls -td "$PASTA_APO"/${ANO_ATUAL}*/ 2>/dev/null | head -n 1)

if [ -z "$DIRETORIO_MAIS_RECENTE" ]; then
    echo "Erro: Nenhum diretório começando com '202' foi encontrado em $PASTA_APO"
    exit 1
fi

ORIGEM=$(basename "$DIRETORIO_MAIS_RECENTE")
DESTINO=$(date +'%Y%m%d_%H%M')

echo "-------------------------------------------"
echo "Pasta de ORIGEM: ${ORIGEM}"
echo "-------------------------------------------"
echo "-------------------------------------------"
echo "Pasta de DESTINO: ${DESTINO}"
echo "-------------------------------------------"

echo "REALIZANDO COPIA DO RPO COMPILACAO PARA SERVIDORES PROTHEUS..."

mkdir -p "${PASTA_APO}/${DESTINO}"

cp -p "${PASTA_CMP}/tttm120.rpo" "${PASTA_CMP}/custom.rpo" "${PASTA_APO}/${DESTINO}/"

echo "✅ Arquivos RPO copiados com sucesso!"

echo "REALIZANDO TQ..."

find "$PASTA_BIN" -type f -iname "appserver*.ini" -exec sed -i "s#${ORIGEM}#${DESTINO}#g" {} +

echo "PROCESSO CONCLUIDO!"'''

        # Lista de scripts com metadados
        scripts_metadata = [
            ('Apply Patches (PowerShell)', 'powershell', 'build', 'Aplica patches PTM no RPO usando advpls (Windows)', apply_patch_ps1_template),
            ('Apply Patches (Bash)', 'bash', 'build', 'Aplica patches PTM no RPO usando advpls (Linux)', apply_patch_sh_template),
            ('Compilar Fontes (PowerShell)', 'powershell', 'build', 'Compila fontes .prw, .tlpp, .prx no RPO (Windows)', compila_ps1_template),
            ('Compilar Fontes (Bash)', 'bash', 'build', 'Compila fontes .prw, .tlpp, .prx no RPO (Linux)', compila_sh_template),
            ('Troca Quente - TQ (PowerShell)', 'powershell', 'deploy', 'Realiza troca quente do RPO nos servidores (Windows)', tq_ps1_template),
            ('Troca Quente - TQ (Bash)', 'bash', 'deploy', 'Realiza troca quente do RPO nos servidores (Linux)', tq_sh_template),
        ]
        
        # Gera os 24 comandos (6 scripts × 4 ambientes)
        all_commands = []
        for env_name, env_id in environments_map.items():
            suffix = suffix_map[env_name]
            
            for script_name, script_type, script_category, script_description, script_template in scripts_metadata:
                # Substitui {{SUFFIX}} no template
                final_script = script_template.replace('{{SUFFIX}}', suffix)
                
                # Nome completo do comando
                full_command_name = f"{script_name} - {env_name}"
                
                all_commands.append((
                    env_id,
                    full_command_name,
                    script_category,
                    script_type,
                    f"{script_description} [Ambiente: {env_name}]",
                    final_script,
                    True,
                    now
                ))
        
        # Insere todos os comandos
        cursor.executemany(
            """
            INSERT INTO commands (environment_id, name, command_category, type, description, script, is_protected, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            all_commands
        )
        print(f"✅ {len(all_commands)} comandos padrão inseridos com sucesso!")
        print(f"   • {len([c for c in all_commands if c[2] == 'build'])} comandos BUILD")
        print(f"   • {len([c for c in all_commands if c[2] == 'deploy'])} comandos DEPLOY")

    # (ATUALIZADO) Tabela de Pipelines
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS pipelines (
            id SERIAL PRIMARY KEY,
            environment_id INTEGER NOT NULL,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            deploy_command_id INTEGER,
            status VARCHAR(50),
            last_run VARCHAR(100),
            duration VARCHAR(100),
            is_protected BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP,
            FOREIGN KEY (environment_id) REFERENCES environments (id) ON DELETE CASCADE,
            FOREIGN KEY (deploy_command_id) REFERENCES commands (id) ON DELETE SET NULL
        )
        """
    )

    # Tabela de relacionamento Pipeline-Comandos (ordem sequencial)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS pipeline_commands (
            id SERIAL PRIMARY KEY,
            pipeline_id INTEGER NOT NULL,
            command_id INTEGER NOT NULL,
            sequence_order INTEGER NOT NULL,
            FOREIGN KEY (pipeline_id) REFERENCES pipelines (id) ON DELETE CASCADE,
            FOREIGN KEY (command_id) REFERENCES commands (id) ON DELETE CASCADE
        )
    """
    )

    # Tabela de Configurações GitHub
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS github_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            token TEXT,
            username VARCHAR(255),
            saved_at TIMESTAMP
        )
    """
    )
    
    # tabela de Pipeline Runs (Build History)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pipeline_runs (
            id SERIAL PRIMARY KEY,
            pipeline_id INTEGER NOT NULL,
            run_number INTEGER NOT NULL,
            status VARCHAR(50) DEFAULT 'running',
            started_at TIMESTAMP NOT NULL,
            finished_at TIMESTAMP,
            started_by INTEGER,
            environment_id INTEGER,
            trigger_type VARCHAR(50) DEFAULT 'manual',
            error_message TEXT,
            FOREIGN KEY (pipeline_id) REFERENCES pipelines(id) ON DELETE CASCADE,
            FOREIGN KEY (started_by) REFERENCES users(id),
            FOREIGN KEY (environment_id) REFERENCES environments(id)
        )
    """)
        
    # tabela de Pipeline Run Logs
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pipeline_run_logs (
            id SERIAL PRIMARY KEY,
            run_id INTEGER NOT NULL,
            command_id INTEGER,
            command_order INTEGER,
            output TEXT,
            status VARCHAR(50) DEFAULT 'running',
            started_at TIMESTAMP NOT NULL,
            finished_at TIMESTAMP,
            FOREIGN KEY (run_id) REFERENCES pipeline_runs(id) ON DELETE CASCADE,
            FOREIGN KEY (command_id) REFERENCES commands(id)
        )
    """)
        
    # tabela de Releases (CD History)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS releases (
            id SERIAL PRIMARY KEY,
            pipeline_id INTEGER NOT NULL,
            run_id INTEGER,
            release_number INTEGER NOT NULL,
            status VARCHAR(50) DEFAULT 'running',
            started_at TIMESTAMP NOT NULL,
            finished_at TIMESTAMP,
            deployed_by INTEGER,
            environment_id INTEGER,
            deploy_script TEXT,
            error_message TEXT,
            FOREIGN KEY (pipeline_id) REFERENCES pipelines(id) ON DELETE CASCADE,
            FOREIGN KEY (run_id) REFERENCES pipeline_runs(id),
            FOREIGN KEY (deployed_by) REFERENCES users(id),
            FOREIGN KEY (environment_id) REFERENCES environments(id)
        )
    """)
    # Adiciona coluna deploy_command_id se não existir
    cursor.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='releases' AND column_name='deploy_command_id'
    """)
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE releases ADD COLUMN deploy_command_id INTEGER")

    # Tabela de Agendamentos de Pipelines
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pipeline_schedules (
            id SERIAL PRIMARY KEY,
            pipeline_id INTEGER NOT NULL,
            environment_id INTEGER NOT NULL,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            schedule_type VARCHAR(50) NOT NULL,
            schedule_config TEXT NOT NULL,
            is_active BOOLEAN DEFAULT FALSE,
            created_by INTEGER NOT NULL,
            created_at TIMESTAMP NOT NULL,
            updated_at TIMESTAMP,
            last_run_at TIMESTAMP,
            next_run_at TIMESTAMP,
            FOREIGN KEY (pipeline_id) REFERENCES pipelines(id) ON DELETE CASCADE,
            FOREIGN KEY (environment_id) REFERENCES environments(id),
            FOREIGN KEY (created_by) REFERENCES users(id)
        )
    """)

    # Tabela de Ações de Serviços (Start/Stop/Restart)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS service_actions (
            id SERIAL PRIMARY KEY,
            environment_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            action_type TEXT NOT NULL CHECK (action_type IN ('start', 'stop', 'restart')),
            os_type TEXT NOT NULL CHECK (os_type IN ('windows', 'linux')),
            force_stop BOOLEAN DEFAULT FALSE,
            service_ids TEXT NOT NULL,
            schedule_type TEXT CHECK (schedule_type IN ('once', 'daily', 'weekly', 'monthly')),
            schedule_config TEXT,
            is_active BOOLEAN DEFAULT FALSE,
            next_run_at TIMESTAMP,
            last_run_at TIMESTAMP,
            created_by INTEGER NOT NULL,
            created_at TIMESTAMP NOT NULL,
            FOREIGN KEY (environment_id) REFERENCES environments(id) ON DELETE CASCADE,
            FOREIGN KEY (created_by) REFERENCES users(id)
        )
        """
    )

    # tabela de Release Logs
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS release_logs (
            id SERIAL PRIMARY KEY,
            release_id INTEGER NOT NULL,
            output TEXT,
            log_type VARCHAR(50) DEFAULT 'info',
            created_at TIMESTAMP NOT NULL,
            FOREIGN KEY (release_id) REFERENCES releases(id) ON DELETE CASCADE
        )
    """)
    
    # tabela de Pipeline Run Output Logs (streaming igual ao release)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pipeline_run_output_logs (
            id SERIAL PRIMARY KEY,
            run_id INTEGER NOT NULL,
            output TEXT,
            log_type VARCHAR(50) DEFAULT 'info',
            created_at TIMESTAMP NOT NULL,
            FOREIGN KEY (run_id) REFERENCES pipeline_runs(id) ON DELETE CASCADE
        )
    """)

    # índices para performance
    indices = [
        ("idx_pipeline_runs_pipeline", "pipeline_runs", "pipeline_id"),
        ("idx_pipeline_runs_status", "pipeline_runs", "status"),
        ("idx_pipeline_runs_started", "pipeline_runs", "started_at"),
        ("idx_releases_pipeline", "releases", "pipeline_id"),
        ("idx_releases_run", "releases", "run_id"),
        ("idx_releases_status", "releases", "status"),
        ("idx_releases_started", "releases", "started_at"),
    ]
    
    for idx_name, table, column in indices:
        try:
            cursor.execute(f"""
                CREATE INDEX IF NOT EXISTS {idx_name} 
                ON {table}({column})
            """)
            print(f"  ✓ Índice {idx_name} criado")
        except Exception as e:
            print(f"  ⚠️  Índice {idx_name} já existe ou erro: {e}")

    # Tabela de Logs de Execução
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS execution_logs (
            id SERIAL PRIMARY KEY,
            pipeline_id INTEGER,
            command_id INTEGER,
            status VARCHAR(50),
            output TEXT,
            error TEXT,
            started_at TEXT,
            finished_at TIMESTAMP,
            FOREIGN KEY (pipeline_id) REFERENCES pipelines (id) ON DELETE CASCADE,
            FOREIGN KEY (command_id) REFERENCES commands (id) ON DELETE CASCADE
        )
    """
    )
    # (ATUALIZADO) Tabela de Logs de Execução
    # Adiciona coluna environment_id se não existir
    cursor.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='execution_logs' AND column_name='environment_id'
    """)
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE execution_logs ADD COLUMN environment_id INTEGER")
    # Adiciona coluna executed_by se não existir
    cursor.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='execution_logs' AND column_name='executed_by'
    """)
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE execution_logs ADD COLUMN executed_by VARCHAR(255)")

    # =====================================================================
    # MIGRAÇÕES - Adicionar novos campos às tabelas existentes
    # =====================================================================
    
    # Migração: server_services - adicionar environment_id
    cursor.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='server_services' AND column_name='environment_id'
    """)
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE server_services ADD COLUMN environment_id INTEGER")
        print("  ✅ Coluna environment_id adicionada à tabela server_services")
    
    # Migração: server_services - adicionar server_name
    cursor.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='server_services' AND column_name='server_name'
    """)
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE server_services ADD COLUMN server_name TEXT DEFAULT 'localhost'")
        print("  ✅ Coluna server_name adicionada à tabela server_services")
    
    # Migração: server_services - adicionar display_name
    cursor.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='server_services' AND column_name='display_name'
    """)
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE server_services ADD COLUMN display_name TEXT")
        print("  ✅ Coluna display_name adicionada à tabela server_services")
    
    # Migração: server_services - adicionar is_active
    cursor.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='server_services' AND column_name='is_active'
    """)
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE server_services ADD COLUMN is_active BOOLEAN DEFAULT TRUE")
        print("  ✅ Coluna is_active adicionada à tabela server_services")
    
    # Migração: service_actions - adicionar force_stop
    cursor.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='service_actions' AND column_name='force_stop'
    """)
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE service_actions ADD COLUMN force_stop BOOLEAN DEFAULT FALSE")
        print("  ✅ Coluna force_stop adicionada à tabela service_actions")

    # Migração: server_variables - adicionar is_protected
    cursor.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='server_variables' AND column_name='is_protected'
    """)
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE server_variables ADD COLUMN is_protected BOOLEAN DEFAULT FALSE")
        # Marcar variáveis padrão como protegidas
        cursor.execute("""
            UPDATE server_variables SET is_protected = TRUE 
            WHERE name LIKE '%_PRD' OR name LIKE '%_HOM' OR name LIKE '%_DEV' OR name LIKE '%_TST'
        """)
        print("  ✅ Coluna is_protected adicionada à tabela server_variables")

    # Migração: server_variables - adicionar is_password
    cursor.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='server_variables' AND column_name='is_password'
    """)
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE server_variables ADD COLUMN is_password BOOLEAN DEFAULT FALSE")
        # Marcar variáveis PROTHEUS_PASSWORD como senha
        cursor.execute("""
            UPDATE server_variables SET is_password = TRUE 
            WHERE name LIKE 'PROTHEUS_PASSWORD_%'
        """)
        print("  ✅ Coluna is_password adicionada à tabela server_variables")

    # Migração: commands - adicionar is_protected
    cursor.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='commands' AND column_name='is_protected'
    """)
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE commands ADD COLUMN is_protected BOOLEAN DEFAULT FALSE")
        # Marcar comandos padrão como protegidos
        cursor.execute("""
            UPDATE commands SET is_protected = TRUE 
            WHERE name LIKE 'Apply Patches%' OR name LIKE 'Compilar Fontes%' OR name LIKE 'Troca Quente%'
        """)
        print("  ✅ Coluna is_protected adicionada à tabela commands")

    # Migração: pipelines - adicionar is_protected
    cursor.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='pipelines' AND column_name='is_protected'
    """)
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE pipelines ADD COLUMN is_protected BOOLEAN DEFAULT FALSE")
        # Marcar pipelines padrão como protegidas
        cursor.execute("""
            UPDATE pipelines SET is_protected = TRUE 
            WHERE name LIKE '🔨%' OR name LIKE '🚀%'
        """)
        print("  ✅ Coluna is_protected adicionada à tabela pipelines")

    # Criar usuário admin padrão se não existir
    cursor.execute("SELECT COUNT(*) FROM users WHERE username = 'admin'")
    if cursor.fetchone()['count'] == 0:
        hashed_password, salt = hash_password("4dm1n@4TURP0")
        cursor.execute(
            """
            INSERT INTO users (username, name, email, password, password_salt, profile, active, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
            (
                "admin",
                "Administrador",
                "admin@company.com",
                hashed_password,
                salt,
                "admin",
                True,
                datetime.now(),
            ),
        )

    # =====================================================================
    # INSERIR PIPELINES PADRÃO (48 pipelines = 6 tipos × 4 ambientes × 2 scripts)
    # =====================================================================
    
    cursor.execute("SELECT COUNT(*) FROM pipelines WHERE name LIKE '🔨%' OR name LIKE '🚀%'")
    
    if cursor.fetchone()['count'] == 0:
        now = datetime.now()
        
        print("\n🔧 Criando pipelines padrão...")
        
        # Definição das pipelines (6 tipos)
        pipeline_templates = [
            {
                'name': '🚀 Compilar fontes com deploy',
                'description': 'Compila fontes .prw, .tlpp, .prx e realiza troca quente (TQ) no ambiente',
                'build_commands': ['Compilar Fontes'],  # Apenas BUILD
                'deploy_command': 'Troca Quente - TQ'    # TQ vai no DEPLOY
            },
            {
                'name': '🚀 Aplicar patch com deploy',
                'description': 'Aplica patches PTM no RPO e realiza troca quente (TQ) no ambiente',
                'build_commands': ['Apply Patches'],     # Apenas BUILD
                'deploy_command': 'Troca Quente - TQ'    # TQ vai no DEPLOY
            },
            {
                'name': '🚀 Aplicar patch e compilar fonte com deploy',
                'description': 'Compila fontes, aplica patches PTM e realiza troca quente (TQ) no ambiente',
                'build_commands': ['Compilar Fontes', 'Apply Patches'],  # Apenas BUILD
                'deploy_command': 'Troca Quente - TQ'                     # TQ vai no DEPLOY
            },
            {
                'name': '🔨 Compilar fontes sem deploy',
                'description': 'Compila fontes .prw, .tlpp, .prx no RPO (sem deploy)',
                'build_commands': ['Compilar Fontes'],   # Apenas BUILD
                'deploy_command': None                   # SEM deploy
            },
            {
                'name': '🔨 Aplicar patch sem deploy',
                'description': 'Aplica patches PTM no RPO (sem deploy)',
                'build_commands': ['Apply Patches'],     # Apenas BUILD
                'deploy_command': None                   # SEM deploy
            },
            {
                'name': '🔨 Aplicar patch e compilar fonte sem deploy',
                'description': 'Compila fontes e aplica patches PTM no RPO (sem deploy)',
                'build_commands': ['Compilar Fontes', 'Apply Patches'],  # Apenas BUILD
                'deploy_command': None                                    # SEM deploy
            }
        ]
        
        # Tipos de script
        script_types = [
            ('PowerShell', 'powershell'),
            ('Bash', 'bash')
        ]
        
        pipelines_created = 0
        
        # Para cada ambiente
        for env_name, env_id in environments_map.items():
            # Para cada tipo de script
            for script_display_name, script_type in script_types:
                
                # Busca os IDs dos comandos para este ambiente e tipo de script
                commands_cache = {}
                
                for cmd_base_name in ['Apply Patches', 'Compilar Fontes', 'Troca Quente - TQ']:
                    full_cmd_name = f"{cmd_base_name} ({script_display_name}) - {env_name}"
                    
                    cursor.execute(
                        "SELECT id FROM commands WHERE name = %s AND environment_id = %s AND type = %s",
                        (full_cmd_name, env_id, script_type)
                    )
                    
                    cmd_result = cursor.fetchone()
                    if cmd_result:
                        commands_cache[cmd_base_name] = cmd_result['id']
                
                # Se não encontrou os comandos necessários, pula
                if len(commands_cache) < 3:
                    print(f"  ⚠️  Comandos não encontrados para {env_name} - {script_display_name}")
                    continue
                
                # Cria cada pipeline para este ambiente e tipo de script
                for pipeline_template in pipeline_templates:
                    
                    # Monta o nome completo da pipeline
                    pipeline_full_name = f"{pipeline_template['name']} ({script_display_name}) - {env_name}"
                    
                    # Determina o deploy_command_id (apenas se tiver deploy_command definido)
                    deploy_command_id = None
                    if pipeline_template['deploy_command'] and pipeline_template['deploy_command'] in commands_cache:
                        deploy_command_id = commands_cache[pipeline_template['deploy_command']]
                    
                    # Insere a pipeline
                    cursor.execute(
                        """
                        INSERT INTO pipelines (
                            environment_id, name, description, deploy_command_id, 
                            status, last_run, is_protected, created_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                        """,
                        (
                            env_id,
                            pipeline_full_name,
                            pipeline_template['description'],
                            deploy_command_id,
                            'queued',
                            'Nunca executada',
                            True,
                            now
                        )
                    )
                    
                    pipeline_id = cursor.fetchone()['id']
                    
                    # Associa APENAS os comandos de BUILD à pipeline na ordem correta
                    # O comando de DEPLOY (TQ) vai APENAS no campo deploy_command_id
                    for sequence_order, cmd_base_name in enumerate(pipeline_template['build_commands']):
                        if cmd_base_name in commands_cache:
                            cursor.execute(
                                """
                                INSERT INTO pipeline_commands (pipeline_id, command_id, sequence_order)
                                VALUES (%s, %s, %s)
                                """,
                                (pipeline_id, commands_cache[cmd_base_name], sequence_order)
                            )
                    
                    pipelines_created += 1
        
        print(f"✅ {pipelines_created} pipelines padrão criadas com sucesso!")
        print(f"   • 3 pipelines COM deploy por ambiente/script")
        print(f"   • 3 pipelines SEM deploy por ambiente/script")

    try:
        conn.commit()
        print("✓ Banco de dados inicializado com sucesso!")
    except Exception as e:
        conn.rollback()
        print(f"⚠️  Erro ao inicializar banco (ignorando em reload): {e}")
    finally:
        conn.close()


# =====================================================================
# AUTENTICAÇÃO E MIDDLEWARE
# =====================================================================


def hash_password(password):
    """Gera um salt e um hash para a senha"""
    salt = secrets.token_hex(16)
    hashed_password = hashlib.sha256((password + salt).encode()).hexdigest()
    return hashed_password, salt


def verify_password(stored_password, stored_salt, provided_password):
    """Verifica se a senha fornecida corresponde ao hash e salt armazenados"""
    if not stored_salt:
        return False  # Lida com senhas antigas sem salt
    hashed_password = hashlib.sha256(
        (provided_password + stored_salt).encode()
    ).hexdigest()
    return hashed_password == stored_password


def generate_session_token():
    """Gera token de sessão único"""
    return secrets.token_hex(32)


def require_auth(f):
    """Decorator para rotas que requerem autenticação"""

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
            timeout_minutes = user_dict.get('session_timeout_minutes', False)
            
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
            # GARANTE QUE A CONEXÃO SEJA FECHADA, NÃO IMPORTA O QUE ACONTEÇA
            conn.close()

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
            
            # NÃO atualiza last_activity aqui!
            request.current_user = user_dict
        
        finally:
            conn.close()

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
        conn.close()


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
            'repositories': {'view': True, 'create': True, 'edit': True, 'delete': True},
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
            'repositories': {'view': True, 'create': True, 'edit': True, 'delete': True},
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
            'repositories': {'view': True, 'create': True, 'edit': True, 'delete': True},
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
            'repositories': {'view': True, 'create': False, 'edit': False, 'delete': False},
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


# =====================================================================
# ENDPOINT DE PERMISSÕES DO USUÁRIO
# =====================================================================

@app.route("/api/me/permissions", methods=["GET"])
@require_auth
def get_current_user_permissions():
    """Retorna as permissões do usuário autenticado"""
    user = request.current_user
    permissions = get_user_permissions(user["profile"], user["username"])
    return jsonify({
        "profile": user["profile"],
        "username": user["username"],
        "is_root": user["username"] == "admin",
        "permissions": permissions
    })


# =====================================================================
# ENDPOINT DE LOGS PARA ADMIN
# =====================================================================

@app.route("/api/admin/logs/<log_type>", methods=["GET"])
@require_admin
def get_system_logs(log_type):
    """
    Retorna logs do sistema (apenas admin).
    
    Tipos: general, errors, audit
    """
    allowed_types = ['general', 'errors', 'audit']
    if log_type not in allowed_types:
        return jsonify({"error": "Tipo de log inválido"}), 400
    
    log_file_map = {
        'general': 'app.log',
        'errors': 'errors.log',
        'audit': 'audit.log'
    }
    
    log_file = os.path.join(
        os.path.dirname(__file__), 
        'logs', 
        log_file_map[log_type]
    )
    
    if not os.path.exists(log_file):
        return jsonify({"error": "Arquivo de log não encontrado"}), 404
    
    # Lê últimas N linhas
    lines = request.args.get('lines', 100, type=int)
    lines = min(lines, 1000)  # Máximo 1000 linhas
    
    try:
        with open(log_file, 'r') as f:
            all_lines = f.readlines()
            last_lines = all_lines[-lines:]
        
        return jsonify({
            "log_type": log_type,
            "lines": last_lines,
            "total_lines": len(last_lines)
        })
    
    except Exception as e:
        app.logger.error(f"Error reading log file: {e}")
        return jsonify({"error": "Erro ao ler arquivo de log"}), 500
    
# =====================================================================
# ROTAS DE AUTENTICAÇÃO
# =====================================================================


@app.route("/api/login", methods=["POST"])
@login_rate_limit(max_attempts=5, window_seconds=300)
def login():
    """Login com auditoria completa"""
    data = request.json
    username = data.get("username")
    password = data.get("password")
    force_login = data.get("force", False)

    if not username or not password:
        return jsonify({"error": "Usuário e senha são obrigatórios"}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = %s AND active = TRUE", (username,))
    user = cursor.fetchone()

    if not user or not verify_password(user["password"], user["password_salt"], password):
        conn.close()
        
        # AUDITORIA: Tentativa de login falhou
        app.logger.warning(f"Failed login attempt for user: {username} from {request.remote_addr}")
        log_audit(
            action='login_failed',
            user_id=0,
            user_name=username,
            details=f"Failed login attempt from {request.remote_addr}",
            status='failure'
        )
        
        return jsonify({"error": "Usuário ou senha inválidos"}), 401

    # ============================================================
    # 🔐 VALIDAÇÃO DE LICENÇA EM TEMPO REAL NO LOGIN
    # ============================================================
    from license_system import validate_license_online, get_hardware_id, get_trial_status, TRIAL_ENABLED
    
    license_key = get_license_key()
    
    if not license_key:
        # Sem licença - verificar se está em modo trial
        if TRIAL_ENABLED:
            trial = get_trial_status()
            if trial and trial.get('active'):
                # ✅ Trial ativo - permitir login
                app.logger.info(f"Login allowed (TRIAL mode): {username} - {trial.get('days_remaining')} days remaining")
            else:
                # ❌ Trial expirado
                conn.close()
                app.logger.error(f"Login blocked - trial expired: {username}")
                log_audit(
                    action='login_blocked_trial_expired',
                    user_id=user["id"],
                    user_name=username,
                    details=f"Login blocked - trial period expired",
                    status='failure'
                )
                return jsonify({
                    "error": "Período de trial expirado",
                    "message": "Ative uma licença para continuar usando o sistema"
                }), 403
        else:
            # ❌ Sem licença e trial desabilitado
            conn.close()
            app.logger.error(f"Login blocked - no license: {username}")
            log_audit(
                action='login_blocked_no_license',
                user_id=user["id"],
                user_name=username,
                details=f"Login blocked - system not licensed",
                status='failure'
            )
            return jsonify({
                "error": "Sistema não licenciado",
                "message": "Entre em contato com o administrador para ativar a licença"
            }), 403
    else:
        # Tem licença - validar em TEMPO REAL (sem cache)
        hardware_id = get_hardware_id()
        success, license_data, error = validate_license_online(license_key, hardware_id)
        
        if not success:
            conn.close()
            app.logger.error(f"Login blocked - invalid license: {username} - {error}")
            log_audit(
                action='login_blocked_invalid_license',
                user_id=user["id"],
                user_name=username,
                details=f"Login blocked - {error}",
                status='failure'
            )
            return jsonify({
                "error": "Licença inválida ou bloqueada",
                "message": error or "Entre em contato com o administrador"
            }), 403
        
        # ✅ Licença válida
        app.logger.info(f"License validated for login: {username} - {license_data.get('customer_name')}")
    # ============================================================

    # Verifica sessão única - MAS considera timeout expirado
    if user["session_token"] and not force_login:
        session_expired = False
        
        # Acessar campos diretamente (Row object não suporta .get() corretamente)
        try:
            timeout_minutes = user["session_timeout_minutes"] if user["session_timeout_minutes"] else 0
        except (KeyError, TypeError):
            timeout_minutes = 0
        
        try:
            last_activity = user["last_activity"]
        except (KeyError, TypeError):
            last_activity = None
        
        # Se tem timeout configurado, verificar se a sessão anterior expirou
        if timeout_minutes and timeout_minutes > 0 and last_activity:
            try:
                # Se last_activity é string, converter para datetime
                if isinstance(last_activity, str):
                    last_activity = datetime.fromisoformat(last_activity.replace('Z', '+00:00'))
                
                # Remover timezone para comparação (se tiver)
                if hasattr(last_activity, 'tzinfo') and last_activity.tzinfo is not None:
                    last_activity = last_activity.replace(tzinfo=None)
                
                # Verificar se expirou
                if datetime.now() > last_activity + timedelta(minutes=timeout_minutes):
                    session_expired = True
                    app.logger.info(f"Session timeout detected for user {username}, allowing new login")
                    # Limpar token expirado
                    cursor.execute("UPDATE users SET session_token = NULL WHERE id = %s", (user["id"],))
                    conn.commit()
            except Exception as e:
                app.logger.warning(f"Error checking session timeout: {e}")
        
        # Só bloquear se sessão NÃO expirou
        if not session_expired:
            conn.close()
            app.logger.info(f"User {username} tried to login with active session")
            return jsonify({
                "error": f"O usuário '{username}' já possui uma sessão ativa."
            }), 409

    # Gerar novo token de sessão
    token = generate_session_token()
    now = datetime.now()

    cursor.execute(
        """
        UPDATE users 
        SET session_token = %s, last_login = %s, last_activity = %s
        WHERE id = %s
        """,
        (token, now, now, user["id"])
    )

    conn.commit()
    conn.close()
    
    # Limpa rate limit após login bem-sucedido
    rate_limiter.clear_user(f"login_{request.remote_addr}")
    
    # AUDITORIA: Login bem-sucedido
    app.logger.info(f"Successful login: {username} from {request.remote_addr}")
    log_audit(
        action='login_success',
        user_id=user["id"],
        user_name=username,
        details=f"Login from {request.remote_addr}",
        status='success'
    )

    return jsonify({
        "success": True,
        "token": token,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "name": user["name"],
            "email": user["email"],
            "profile": user["profile"],
            "lastLogin": now,
        },
    })


@app.route("/api/logout", methods=["POST"])
@require_auth
def logout():
    """Endpoint de logout"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE users SET session_token = NULL WHERE id = %s
    """,
        (request.current_user["id"],),
    )
    conn.commit()
    conn.close()

    return jsonify({"success": True, "message": "Logout realizado com sucesso"})


# =====================================================================
# ROTA DE VERIFICAÇÃO DE SESSÃO
# =====================================================================


@app.route("/api/me", methods=["GET"])
@require_auth
def get_current_user():
    """Retorna os dados do usuário autenticado pelo token"""
    user = request.current_user
    return jsonify(
        {
            "id": user["id"],
            "username": user["username"],
            "name": user["name"],
            "email": user["email"],
            "profile": user["profile"],
            "lastLogin": user["last_login"],
        }
    )


# =====================================================================
# ROTA DE ALTERAÇÃO DE SENHA
# =====================================================================


@app.route("/api/me/password", methods=["POST"])
@require_auth
def change_own_password():
    data = request.json
    current_password = data.get("current_password")
    new_password = data.get("new_password")

    user = request.current_user

    if not verify_password(user["password"], user["password_salt"], current_password):
        return jsonify({"error": "Senha atual incorreta"}), 403

    new_hashed_password, new_salt = hash_password(new_password)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET password = %s, password_salt = %s WHERE id = %s",
        (new_hashed_password, new_salt, user["id"]),
    )
    conn.commit()
    conn.close()

    return jsonify({"success": True, "message": "Senha alterada com sucesso!"})

# =====================================================================
# PRIMEIRO ACESSO - Criação do Admin do Cliente
# =====================================================================

@app.route("/api/first-access/check", methods=["GET"])
def check_first_access():
    """
    Verifica se é o primeiro acesso (não existe admin além do root).
    Rota pública - não requer autenticação.
    """
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Conta admins que NÃO são o root (username != 'admin')
        cursor.execute("""
            SELECT COUNT(*) as count FROM users 
            WHERE profile = 'admin' AND username != 'admin' AND active = TRUE
        """)
        result = cursor.fetchone()
        conn.close()
        
        admin_count = result['count'] if result else 0
        is_first_access = admin_count == 0
        
        return jsonify({
            "first_access": is_first_access,
            "message": "Nenhum administrador configurado" if is_first_access else "Sistema já configurado"
        })
        
    except Exception as e:
        app.logger.error(f"Erro ao verificar primeiro acesso: {e}")
        return jsonify({"first_access": False, "error": str(e)}), 500


@app.route("/api/first-access/create", methods=["POST"])
def create_first_admin():
    """
    Cria o primeiro usuário administrador do cliente.
    Só funciona se não existir nenhum admin além do root.
    Rota pública - não requer autenticação.
    """
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Verificar se realmente é primeiro acesso
        cursor.execute("""
            SELECT COUNT(*) as count FROM users 
            WHERE profile = 'admin' AND username != 'admin' AND active = TRUE
        """)
        result = cursor.fetchone()
        
        if result and result['count'] > 0:
            conn.close()
            return jsonify({
                "error": "Já existe um administrador configurado no sistema"
            }), 400
        
        # Validar dados recebidos
        data = request.json
        required_fields = ["username", "name", "email", "password"]
        
        for field in required_fields:
            if not data.get(field):
                conn.close()
                return jsonify({"error": f"Campo {field} é obrigatório"}), 400
        
        # Validar que não está tentando criar o user 'admin'
        if data["username"].lower() == "admin":
            conn.close()
            return jsonify({"error": "Este nome de usuário não está disponível"}), 400
        
        # Validar senha mínima
        if len(data["password"]) < 6:
            conn.close()
            return jsonify({"error": "A senha deve ter no mínimo 6 caracteres"}), 400
        
        # Verificar se username já existe
        cursor.execute("SELECT id FROM users WHERE username = %s", (data["username"],))
        if cursor.fetchone():
            conn.close()
            return jsonify({"error": "Este nome de usuário já está em uso"}), 400
        
        # Verificar se email já existe
        cursor.execute("SELECT id FROM users WHERE email = %s", (data["email"],))
        if cursor.fetchone():
            conn.close()
            return jsonify({"error": "Este e-mail já está em uso"}), 400
        
        # Criar o usuário admin
        hashed_password, salt = hash_password(data["password"])
        
        cursor.execute(
            """
            INSERT INTO users (username, name, email, password, password_salt, profile, active, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                data["username"],
                data["name"],
                data["email"],
                hashed_password,
                salt,
                "admin",  # Sempre cria como admin
                True,
                datetime.now(),
            ),
        )
        
        user_id = cursor.fetchone()['id']
        conn.commit()
        conn.close()
        
        # AUDITORIA: Registra criação do primeiro admin
        log_audit(
            action='first_access_admin_created',
            user_id=user_id,
            user_name=data["username"],
            details=f"Primeiro administrador criado: {data['username']} (ID: {user_id})",
            status='success'
        )
        
        app.logger.info(f"✅ Primeiro admin criado: {data['username']} (ID: {user_id})")
        
        return jsonify({
            "success": True,
            "message": "Administrador criado com sucesso! Você já pode fazer login.",
            "username": data["username"]
        }), 201
        
    except IntegrityError as e:
        app.logger.error(f"Erro de integridade ao criar primeiro admin: {e}")
        return jsonify({"error": "Usuário ou e-mail já existe"}), 400
        
    except Exception as e:
        app.logger.error(f"Erro ao criar primeiro admin: {e}")
        app.logger.error(traceback.format_exc())
        return jsonify({"error": "Erro ao criar administrador"}), 500
    
# =====================================================================
# ROTAS DE USUÁRIOS
# =====================================================================


@app.route("/api/users", methods=["GET"])
@require_admin
def get_users():
    """Lista todos os usuários"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, username, name, email, profile, active, created_at, last_login, session_timeout_minutes FROM users WHERE username != 'admin'"
    )
    users = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(users)


@app.route("/api/users", methods=["POST"])
@require_admin
def create_user():
    """Cria novo usuário com logging e auditoria"""
    data = request.json
    
    try:
        # Validação
        required_fields = ["username", "name", "email", "password", "profile"]
        for field in required_fields:
            if not data.get(field):
                app.logger.warning(f"Create user failed: missing field {field}")
                return jsonify({"error": f"Campo {field} é obrigatório"}), 400

        hashed_password, salt = hash_password(data["password"])

        conn = get_db()
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO users (username, name, email, password, password_salt, profile, active, session_timeout_minutes, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                data["username"],
                data["name"],
                data["email"],
                hashed_password,
                salt,
                data["profile"],
                data.get("active", True),
                data.get("session_timeout_minutes", 0),
                datetime.now(),
            ),
        )

        user_id = cursor.fetchone()['id']
        conn.commit()
        conn.close()
        
        # AUDITORIA: Registra criação de usuário
        log_audit(
            action='create_user',
            user_id=request.current_user['id'],
            user_name=request.current_user['username'],
            details=f"Created user: {data['username']} (ID: {user_id})",
            status='success'
        )
        
        app.logger.info(f"User created: {data['username']} (ID: {user_id})")

        return jsonify({
            "success": True,
            "id": user_id,
            "message": "Usuário criado com sucesso",
        }), 201

    except IntegrityError as e:
        app.logger.warning(f"Create user failed: {e}")
        
        log_audit(
            action='create_user',
            user_id=request.current_user['id'],
            user_name=request.current_user['username'],
            details=f"Failed to create user: {data.get('username', 'unknown')} - {str(e)}",
            status='failure'
        )
        
        return jsonify({"error": "Nome de usuário já existe"}), 400
    
    except Exception as e:
        app.logger.error(f"Unexpected error creating user: {e}")
        app.logger.error(traceback.format_exc())
        
        log_audit(
            action='create_user',
            user_id=request.current_user['id'],
            user_name=request.current_user['username'],
            details=f"Error creating user: {str(e)}",
            status='failure'
        )
        
        return jsonify({"error": "Erro ao criar usuário"}), 500         


@app.route("/api/users/<int:user_id>", methods=["PUT"])
@require_admin
def update_user(user_id):
    """Atualiza usuário existente com prepared statements"""
    data = request.json

    conn = get_db()
    cursor = conn.cursor()

    # Verificação de permissão
    user_to_edit = cursor.execute(
        "SELECT username FROM users WHERE id = %s", (user_id,)
    )
    user_to_edit = cursor.fetchone()
    
    if (user_to_edit and user_to_edit["username"] == "admin" 
        and request.current_user["username"] != "admin"):
        conn.close()
        return jsonify({
            "error": "Apenas o próprio usuário 'admin' pode alterar seus dados."
        }), 403

    # NOVO: Construir query com prepared statements seguros
    allowed_fields = {
        'name': str,
        'email': str,
        'profile': str,
        'active': bool,
        'session_timeout_minutes': int
    }
    
    update_parts = []
    values = []
    
    for field, field_type in allowed_fields.items():
        if field in data:
            # Valida tipo de dado
            try:
                value = field_type(data[field])
                update_parts.append(f"{field} = %s")
                values.append(value)
            except (ValueError, TypeError):
                conn.close()
                return jsonify({"error": f"Tipo inválido para campo {field}"}), 400
    
    # Tratamento especial para senha
    if "password" in data and data["password"]:
        hashed_password, salt = hash_password(data["password"])
        update_parts.append("password = %s")
        update_parts.append("password_salt = %s")
        values.append(hashed_password)
        values.append(salt)
    
    if not update_parts:
        conn.close()
        return jsonify({"error": "Nenhum campo para atualizar"}), 400

    values.append(user_id)
    
    # Query segura com placeholders
    query = f"UPDATE users SET {', '.join(update_parts)} WHERE id = %s"
    
    try:
        cursor.execute(query, tuple(values))
        conn.commit()
        return jsonify({"success": True, "message": "Usuário atualizado com sucesso"})
    except PsycopgError as e:
        return jsonify({"error": f"Erro no banco de dados: {str(e)}"}), 500
    finally:
        conn.close()


@app.route("/api/users/<int:user_id>", methods=["DELETE"])
@require_admin
def delete_user(user_id):
    """Deleta usuário com auditoria"""
    
    try:
        if user_id == request.current_user["id"]:
            return jsonify({"error": "Você não pode excluir seu próprio usuário"}), 400

        conn = get_db()
        cursor = conn.cursor()

        # Busca informações do usuário antes de deletar
        cursor.execute("SELECT username FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()

        if not user:
            conn.close()
            return jsonify({"error": "Usuário não encontrado"}), 404

        if user["username"] == "admin":
            conn.close()
            return jsonify({"error": "Não é possível excluir o administrador principal"}), 400

        deleted_username = user["username"]
        cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()
        conn.close()
        
        # AUDITORIA: Registra exclusão
        log_audit(
            action='delete_user',
            user_id=request.current_user['id'],
            user_name=request.current_user['username'],
            details=f"Deleted user: {deleted_username} (ID: {user_id})",
            status='success'
        )
        
        app.logger.info(f"User deleted: {deleted_username} (ID: {user_id})")

        return jsonify({"success": True, "message": "Usuário excluído com sucesso"})
    
    except Exception as e:
        app.logger.error(f"Error deleting user {user_id}: {e}")
        app.logger.error(traceback.format_exc())
        
        log_audit(
            action='delete_user',
            user_id=request.current_user['id'],
            user_name=request.current_user['username'],
            details=f"Failed to delete user ID {user_id}: {str(e)}",
            status='failure'
        )
        
        return jsonify({"error": "Erro ao excluir usuário"}), 500

@app.route("/api/users/<int:user_id>/password", methods=["PUT"])
@require_admin
def admin_change_user_password(user_id):
    """
    [ADMIN] Altera a senha de um usuário específico.
    Requer a senha do admin que está executando a ação para autorização.
    """
    data = request.json
    admin_password = data.get("admin_password")
    new_password = data.get("new_password")

    if not admin_password or not new_password:
        return jsonify({"error": "Todos os campos de senha são obrigatórios"}), 400

    # 1. Verificar a senha do admin que está fazendo a ação
    current_admin = request.current_user
    if not verify_password(current_admin["password"], current_admin["password_salt"], admin_password):
        return jsonify({"error": "Senha do administrador incorreta. Ação não autorizada."}), 403

    # 2. Se a senha do admin estiver correta, hashear a nova senha do usuário alvo
    new_hashed_password, new_salt = hash_password(new_password)
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET password = %s, password_salt = %s WHERE id = %s",
        (new_hashed_password, new_salt, user_id),
    )
    conn.commit()
    conn.close()

    return jsonify({"success": True, "message": "Senha do usuário alterada com sucesso!"})

# =====================================================================
# ROTAS DE AMBIENTES
# =====================================================================

@app.route("/api/environments", methods=["GET"])
@require_auth
def get_environments():
    """Lista todos os ambientes."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM environments ORDER BY name")

    environments = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(environments)

@app.route("/api/environments", methods=["POST"])
@require_admin
def create_environment():
    """Cria um novo ambiente. Apenas user admin (root) pode criar."""
    # Apenas user admin (root) pode criar ambientes
    if request.current_user["username"] != "admin":
        return jsonify({"error": "Apenas o administrador root pode criar ambientes"}), 403
    
    data = request.json
    if not data.get("name"):
        return jsonify({"error": "O nome do ambiente é obrigatório"}), 400
    
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO environments (name, description, created_at) VALUES (%s, %s, %s)",
            (data["name"], data.get("description", ""), datetime.now())
        )
        conn.commit()
        return jsonify({"success": True, "message": "Ambiente criado com sucesso"}), 201
    except IntegrityError:
        return jsonify({"error": "Um ambiente com este nome já existe"}), 409
    finally:
        conn.close()

@app.route("/api/environments/<int:env_id>", methods=["PUT"])
@require_admin
def update_environment(env_id):
    """Atualiza um ambiente. Apenas user admin (root) pode editar."""
    # Apenas user admin (root) pode editar ambientes
    if request.current_user["username"] != "admin":
        return jsonify({"error": "Apenas o administrador root pode editar ambientes"}), 403
    
    data = request.json
    if not data.get("name"):
        return jsonify({"error": "O nome do ambiente é obrigatório"}), 400

    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Verificar se já existe outro ambiente com esse nome (exceto o atual)
        cursor.execute(
            "SELECT id FROM environments WHERE name = %s AND id != %s",
            (data["name"], env_id)
        )
        existing = cursor.fetchone()
        
        if existing:
            conn.close()
            return jsonify({"error": "Um ambiente com este nome já existe"}), 409
        
        # Atualizar o ambiente
        cursor.execute(
            "UPDATE environments SET name = %s, description = %s WHERE id = %s",
            (data["name"], data.get("description", ""), env_id)
        )
        conn.commit()
        return jsonify({"success": True, "message": "Ambiente atualizado com sucesso"})
    
    except IntegrityError:
        return jsonify({"error": "Erro de integridade ao atualizar ambiente"}), 409
    
    finally:
        conn.close()

@app.route("/api/environments/<int:env_id>", methods=["DELETE"])
@require_admin
def delete_environment(env_id):
    """Exclui um ambiente. Apenas user admin (root) pode excluir."""
    # Apenas user admin (root) pode excluir ambientes
    if request.current_user["username"] != "admin":
        return jsonify({"error": "Apenas o administrador root pode excluir ambientes"}), 403
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM environments WHERE id = %s", (env_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "Ambiente excluído com sucesso"})

# =====================================================================
# ROTAS DE CONFIGURAÇÕES DO SISTEMA
# =====================================================================


@app.route("/api/server-variables", methods=["GET"])
@require_operator
def get_server_variables():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM server_variables ORDER BY name")

    variables = [dict(row) for row in cursor.fetchall()]
    
    # Mascarar valores de variáveis do tipo senha
    for var in variables:
        if var.get('is_password'):
            var['value'] = '••••••••'
    
    conn.close()
    return jsonify(variables)

@app.route("/api/server-variables", methods=["POST"])
@require_operator
def create_server_variable():
    data = request.json
    if not data.get("name") or not data.get("value"):
        return jsonify({"error": "Nome e Valor são obrigatórios"}), 400
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO server_variables (name, value, description, is_password, created_at) VALUES (%s, %s, %s, %s, %s)",
            (data["name"], data["value"], data.get("description", ""), data.get("is_password", False), datetime.now())
        )
        conn.commit()
        return jsonify({"success": True, "message": "Variável criada com sucesso"}), 201
    except IntegrityError:
        return jsonify({"error": "Uma variável com este nome já existe"}), 409
    finally:
        conn.close()

@app.route("/api/server-variables/<int:var_id>", methods=["PUT"])
@require_operator
def update_server_variable(var_id):
    data = request.json
    if not data.get("name") or not data.get("value"):
        return jsonify({"error": "Nome e Valor são obrigatórios"}), 400
    
    # Verificar se item é protegido (perfil admin pode editar protegidas)
    if request.current_user.get('profile') != 'admin' and check_protected_item('server_variables', var_id):
        return jsonify({"error": "Esta variável é protegida e não pode ser alterada"}), 403
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Verificar se já existe outra variável com esse nome (exceto a atual)
        cursor.execute(
            "SELECT id FROM server_variables WHERE name = %s AND id != %s",
            (data["name"], var_id)
        )
        existing = cursor.fetchone()
        
        if existing:
            conn.close()
            return jsonify({"error": "Uma variável com este nome já existe"}), 409
        
        # Atualizar a variável (se valor for __KEEP_CURRENT__, mantém o atual)
        if data["value"] == "__KEEP_CURRENT__":
            cursor.execute(
                "UPDATE server_variables SET name = %s, description = %s, is_password = %s WHERE id = %s",
                (data["name"], data.get("description", ""), data.get("is_password", False), var_id)
            )
        else:
            cursor.execute(
                "UPDATE server_variables SET name = %s, value = %s, description = %s, is_password = %s WHERE id = %s",
                (data["name"], data["value"], data.get("description", ""), data.get("is_password", False), var_id)
            )
        conn.commit()
        return jsonify({"success": True, "message": "Variável atualizada com sucesso"})
    
    except IntegrityError:
        return jsonify({"error": "Erro de integridade ao atualizar variável"}), 409
    
    finally:
        conn.close()

@app.route("/api/server-variables/<int:var_id>", methods=["DELETE"])
@require_operator
def delete_server_variable(var_id):
    # Verificar se item é protegido
    if check_protected_item('server_variables', var_id):
        return jsonify({"error": "Esta variável é protegida e não pode ser excluída"}), 403
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM server_variables WHERE id = %s", (var_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "Variável excluída com sucesso"})

@app.route("/api/server-services", methods=["GET"])
@require_operator
def get_server_services():
    conn = get_db()
    cursor = conn.cursor()
    
    # Filtrar por ambiente se fornecido
    environment_id = request.args.get('environment_id')
    
    if environment_id:
        cursor.execute("""
            SELECT ss.*, e.name as environment_name 
            FROM server_services ss
            LEFT JOIN environments e ON ss.environment_id = e.id
            WHERE ss.environment_id = %s
            ORDER BY ss.name
        """, (environment_id,))
    else:
        cursor.execute("""
            SELECT ss.*, e.name as environment_name 
            FROM server_services ss
            LEFT JOIN environments e ON ss.environment_id = e.id
            ORDER BY ss.name
        """)

    services = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(services)

@app.route("/api/server-services", methods=["POST"])
@require_operator
def create_server_service():
    data = request.json
    if not data.get("name"):
        return jsonify({"error": "O nome do serviço é obrigatório"}), 400
    if not data.get("server_name"):
        return jsonify({"error": "O nome do servidor é obrigatório"}), 400
    if not data.get("environment_id"):
        return jsonify({"error": "O ambiente é obrigatório"}), 400
        
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO server_services 
               (environment_id, name, display_name, server_name, description, is_active, created_at) 
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (
                data["environment_id"],
                data["name"], 
                data.get("display_name", data["name"]),
                data["server_name"],
                data.get("description", ""), 
                data.get("is_active", True),
                datetime.now()
            )
        )
        conn.commit()
        return jsonify({"success": True, "message": "Serviço criado com sucesso"}), 201
    except IntegrityError:
        return jsonify({"error": "Erro ao criar serviço"}), 409
    finally:
        conn.close()

@app.route("/api/server-services/<int:service_id>", methods=["PUT"])
@require_operator
def update_server_service(service_id):
    data = request.json
    if not data.get("name"):
        return jsonify({"error": "O nome do serviço é obrigatório"}), 400
    if not data.get("server_name"):
        return jsonify({"error": "O nome do servidor é obrigatório"}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Atualizar o serviço
        cursor.execute(
            """UPDATE server_services 
               SET name = %s, display_name = %s, server_name = %s, 
                   description = %s, is_active = %s, environment_id = %s
               WHERE id = %s""",
            (
                data["name"], 
                data.get("display_name", data["name"]),
                data["server_name"],
                data.get("description", ""), 
                data.get("is_active", True),
                data.get("environment_id"),
                service_id
            )
        )
        conn.commit()
        return jsonify({"success": True, "message": "Serviço atualizado com sucesso"})
    
    except IntegrityError:
        return jsonify({"error": "Erro de integridade ao atualizar serviço"}), 409
    
    finally:
        conn.close()

@app.route("/api/server-services/<int:service_id>", methods=["DELETE"])
@require_operator
def delete_server_service(service_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM server_services WHERE id = %s", (service_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "Serviço excluído com sucesso"})

# =====================================================================
# ROTAS DE COMANDOS
# =====================================================================


@app.route("/api/commands", methods=["GET"])
@require_auth
def get_commands():
    """Lista comandos com filtros seguros"""
    
    # Pega parâmetros de query string
    category = request.args.get('category')  # Tipo de script (bash, powershell, etc)
    command_category = request.args.get('command_category')  # 🆕 Build ou Deploy
    search = request.args.get('search')
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Header base do SQL com ambiente
    env_id = request.headers.get('X-Environment-Id')
    if not env_id:
        conn.close()
        return jsonify({"error": "Ambiente não especificado"}), 400
    
    # Query base segura
    base_query = "SELECT * FROM commands WHERE environment_id = %s"
    params = [int(env_id)]
    
    # Adiciona filtros de forma segura
    if category:
        # Valida categoria contra lista permitida
        allowed_categories = ['build', 'deploy', 'test', 'maintenance']
        if category in allowed_categories:
            base_query += " AND category = %s"
            params.append(category)
    
    # 🆕 Filtro por command_category (build/deploy)
    if command_category:
        allowed_command_categories = ['build', 'deploy']
        if command_category in allowed_command_categories:
            base_query += " AND command_category = %s"
            params.append(command_category)
    
    if search:
        # Sanitiza termo de busca
        search_term = f"%{search}%"
        base_query += " AND (name LIKE %s OR description LIKE %s)"
        params.append(search_term)
        params.append(search_term)
    
    base_query += " ORDER BY name"
    
    try:
        cursor.execute(base_query, tuple(params))
        commands = [dict(row) for row in cursor.fetchall()]
        return jsonify(commands)
    except PsycopgError as e:
        return jsonify({"error": f"Erro no banco de dados: {str(e)}"}), 500
    finally:
        conn.close()

@app.route("/api/commands", methods=["POST"])
@require_admin
def create_command():
    """Cria novo comando com validação completa"""
    data = request.json
    
    # Validação de campos obrigatórios - 🆕 command_category adicionado
    required_fields = ["name", "type", "script", "command_category"]
    for field in required_fields:
        if not data.get(field):
            return jsonify({"error": f"Campo {field} é obrigatório"}), 400
    
    env_id = request.headers.get('X-Environment-Id')
    if not env_id:
        return jsonify({"error": "Ambiente não especificado"}), 400
    
    # Valida tipo de script
    script_type = data.get("type", "bash")
    allowed_types = ['bash', 'powershell', 'python', 'nodejs', 'docker']
    if script_type not in allowed_types:
        return jsonify({"error": f"Tipo inválido. Use: {', '.join(allowed_types)}"}), 400
    
    # 🆕 Valida command_category
    command_category = data.get("command_category")
    allowed_categories = ['build', 'deploy']
    if command_category not in allowed_categories:
        return jsonify({"error": f"Categoria inválida. Use: {', '.join(allowed_categories)}"}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Query segura com placeholders - 🆕 command_category incluído
        cursor.execute(
            """
            INSERT INTO commands (environment_id, name, command_category, type, description, script, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                int(env_id),
                data["name"],
                command_category,
                script_type,
                data.get("description", ""),
                data["script"],
                datetime.now()
            )
        )
        
        command_id = cursor.fetchone()['id']
        conn.commit()
        
        return jsonify({
            "success": True,
            "id": command_id,
            "message": "Comando criado com sucesso"
        }), 201
        
    except IntegrityError:
        return jsonify({"error": "Comando com este nome já existe neste ambiente"}), 409
    except PsycopgError as e:
        return jsonify({"error": f"Erro no banco de dados: {str(e)}"}), 500
    finally:
        conn.close()

@app.route("/api/commands/<int:command_id>", methods=["PUT"])
@require_admin
def update_command(command_id):
    """Atualiza comando existente"""
    data = request.json
    env_id = request.headers.get('X-Environment-Id')
    
    if not env_id:
        return jsonify({"error": "Ambiente não especificado"}), 400

    # Verificar se item é protegido
    if check_protected_item('commands', command_id):
        return jsonify({"error": "Este comando é protegido e não pode ser alterado"}), 403

    # 🆕 Validar command_category
    if 'command_category' in data:
        allowed_categories = ['build', 'deploy']
        if data['command_category'] not in allowed_categories:
            return jsonify({"error": f"Categoria inválida. Use: {', '.join(allowed_categories)}"}), 400

    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Verificar se já existe outro comando com esse nome no mesmo ambiente (exceto o atual)
        cursor.execute(
            "SELECT id FROM commands WHERE name = %s AND environment_id = %s AND id != %s",
            (data["name"], int(env_id), command_id)
        )
        existing = cursor.fetchone()
        
        if existing:
            conn.close()
            return jsonify({"error": "Um comando com este nome já existe neste ambiente"}), 409

        # Atualizar o comando - 🆕 command_category incluído
        cursor.execute(
            """
            UPDATE commands 
            SET name = %s, command_category = %s, type = %s, description = %s, script = %s
            WHERE id = %s AND environment_id = %s
            """,
            (
                data["name"],
                data.get("command_category", "build"),
                data["type"],
                data.get("description", ""),
                data["script"],
                command_id,
                int(env_id),
            ),
        )

        conn.commit()
        return jsonify({"success": True, "message": "Comando atualizado com sucesso"})
    
    except IntegrityError:
        return jsonify({"error": "Erro de integridade ao atualizar comando"}), 409
    
    finally:
        conn.close()


@app.route("/api/commands/<int:command_id>", methods=["DELETE"])
@require_admin
def delete_command(command_id):
    """Deleta comando com validação de ambiente"""
    
    env_id = request.headers.get('X-Environment-Id')
    if not env_id:
        return jsonify({"error": "Ambiente não especificado"}), 400
    
    # Verificar se item é protegido
    if check_protected_item('commands', command_id):
        return jsonify({"error": "Este comando é protegido e não pode ser excluído"}), 403
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Verifica se comando existe e pertence ao ambiente
        cursor.execute(
            "SELECT id FROM commands WHERE id = %s AND environment_id = %s",
            (command_id, int(env_id))
        )
        
        if not cursor.fetchone():
            conn.close()
            return jsonify({"error": "Comando não encontrado neste ambiente"}), 404
        
        # Deleta com prepared statement
        cursor.execute(
            "DELETE FROM commands WHERE id = %s AND environment_id = %s",
            (command_id, int(env_id))
        )
        
        conn.commit()
        return jsonify({"success": True, "message": "Comando excluído com sucesso"})
        
    except PsycopgError as e:
        return jsonify({"error": f"Erro no banco de dados: {str(e)}"}), 500
    finally:
        conn.close()


# =====================================================================
# ROTAS DE PIPELINES
# =====================================================================


@app.route("/api/pipelines", methods=["GET"])
@require_auth
def get_pipelines():
    # Pega o ID do ambiente do cabeçalho da requisição (será enviado pelo frontend)
    env_id = request.headers.get("X-Environment-Id")
    if not env_id:
        return jsonify({"error": "Cabeçalho X-Environment-Id é obrigatório"}), 400
    conn = get_db()
    cursor = conn.cursor()
    pipelines_data = cursor.execute(
        "SELECT * FROM pipelines WHERE environment_id = %s ORDER BY created_at DESC",
        (env_id,)
    )
    pipelines_data = cursor.fetchall()
    pipelines = []
    for p in pipelines_data:
        pipeline_dict = dict(p)
        cursor = conn.cursor()
        commands = cursor.execute(
            "SELECT c.* FROM commands c JOIN pipeline_commands pc ON c.id = pc.command_id WHERE pc.pipeline_id = %s ORDER BY pc.sequence_order",
            (p["id"],),
        )
        commands = cursor.fetchall()
        pipeline_dict["commands"] = [dict(c) for c in commands]
        pipelines.append(pipeline_dict)
    conn.close()
    return jsonify(pipelines)


@app.route("/api/pipelines", methods=["POST"])
@require_operator
def create_pipeline():
    env_id = request.headers.get("X-Environment-Id")
    if not env_id:
        return jsonify({"error": "Cabeçalho X-Environment-Id é obrigatório"}), 400
    data = request.json
    required_fields = ["name"]
    if not all(field in data for field in required_fields):
        return jsonify({"error": "O nome da pipeline é obrigatório"}), 400
    if not data.get("commands") or len(data["commands"]) == 0:
        return jsonify({"error": "Selecione pelo menos um comando"}), 400

    conn = get_db()
    cursor = conn.cursor()
    
    # 🆕 Validar deploy_command_id se fornecido
    deploy_command_id = data.get("deploy_command_id")
    if deploy_command_id:
        deploy_cmd = cursor.execute(
            "SELECT id FROM commands WHERE id = %s AND command_category = 'deploy'",
            (deploy_command_id,)
        )
        deploy_cmd = cursor.fetchone()
        if not deploy_cmd:
            conn.close()
            return jsonify({"error": "Comando de deploy inválido"}), 400
    
    cursor.execute(
        """INSERT INTO pipelines (environment_id, name, description, deploy_command_id, status, last_run, created_at) 
           VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
        (
            env_id,
            data["name"],
            data.get("description", ""),
            deploy_command_id,  # 🆕 Mudou de deploy_id para deploy_command_id
            "queued",
            "Nunca executada",
            datetime.now(),
        ),
    )
    pipeline_id = cursor.fetchone()['id']
    for index, command in enumerate(data["commands"]):
        cursor.execute(
            "INSERT INTO pipeline_commands (pipeline_id, command_id, sequence_order) VALUES (%s, %s, %s)",
            (pipeline_id, command["id"], index),
        )
    conn.commit()
    conn.close()
    return (
        jsonify(
            {
                "success": True,
                "id": pipeline_id,
                "message": "Pipeline criada com sucesso",
            }
        ),
        201,
    )


@app.route("/api/pipelines/<int:pipeline_id>", methods=["PUT"])
@require_operator
def update_pipeline(pipeline_id):
    data = request.json
    env_id = request.headers.get('X-Environment-Id')
    
    if not env_id:
        return jsonify({"error": "Ambiente não especificado"}), 400
    
    # Verificar se item é protegido
    if check_protected_item('pipelines', pipeline_id):
        return jsonify({"error": "Esta pipeline é protegida e não pode ser alterada"}), 403
    
    conn = get_db()
    cursor = conn.cursor()

    try:
        # Verificar se já existe outra pipeline com esse nome no mesmo ambiente (exceto a atual)
        cursor.execute(
            "SELECT id FROM pipelines WHERE name = %s AND environment_id = %s AND id != %s",
            (data["name"], int(env_id), pipeline_id)
        )
        existing = cursor.fetchone()
        
        if existing:
            conn.close()
            return jsonify({"error": "Uma pipeline com este nome já existe neste ambiente"}), 409
        
        deploy_command_id = data.get("deploy_command_id")
        if deploy_command_id == '':
            deploy_command_id = None

        cursor.execute(
            "UPDATE pipelines SET name = %s, description = %s, deploy_command_id = %s WHERE id = %s AND environment_id = %s",
            (data["name"], data.get("description", ""), deploy_command_id, pipeline_id, int(env_id))
        )

        if "commands" in data:
            cursor.execute("DELETE FROM pipeline_commands WHERE pipeline_id = %s", (pipeline_id,))
            for index, command in enumerate(data["commands"]):
                cursor.execute(
                    "INSERT INTO pipeline_commands (pipeline_id, command_id, sequence_order) VALUES (%s, %s, %s)",
                    (pipeline_id, command["id"], index)
                )

        conn.commit()
        return jsonify({"success": True, "message": "Pipeline atualizada com sucesso"})

    except IntegrityError:
        return jsonify({"error": "Erro de integridade ao atualizar pipeline"}), 409
    
    except Exception as e:
        app.logger.error(f"Erro em update_pipeline: {e}")
        return jsonify({"error": "Erro interno ao atualizar a pipeline"}), 500
    
    finally:
        conn.close()


@app.route("/api/pipelines/<int:pipeline_id>", methods=["DELETE"])
@require_operator
def delete_pipeline(pipeline_id):
    """Exclui pipeline"""
    # Verificar se item é protegido
    if check_protected_item('pipelines', pipeline_id):
        return jsonify({"error": "Esta pipeline é protegida e não pode ser excluída"}), 403
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM pipelines WHERE id = %s", (pipeline_id,))
    conn.commit()
    conn.close()

    return jsonify({"success": True, "message": "Pipeline excluída com sucesso"})


def execute_pipeline_thread(flask_app, pipeline_id, user_name, trigger_type='manual', schedule_id=None):
    """Função que roda em background para executar os comandos da pipeline."""
    with flask_app.app_context():
        start_time = datetime.now()
        # Registra trigger type no pipeline_run
        trigger_info = f"{trigger_type}"
        if schedule_id:
            trigger_info += f" (schedule #{schedule_id})"

        conn = get_db()
        cursor = conn.cursor()

        try:
            # Busca BASE_DIR específico do ambiente da pipeline
            BASE_DIR = get_base_dir_for_pipeline(cursor, pipeline_id)

            # Pega os comandos da pipeline
            cursor.execute(
                "SELECT c.* FROM commands c JOIN pipeline_commands pc ON c.id = pc.command_id WHERE pc.pipeline_id = %s ORDER BY pc.sequence_order",
                (pipeline_id,),
            )
            commands_to_run = [dict(row) for row in cursor.fetchall()]

            cursor.execute(
                "UPDATE pipelines SET status = 'running' WHERE id = %s", (pipeline_id,)
            )
            conn.commit()

            pipeline_success = True

            # Pega o diretório do primeiro repositório como base de execução
            cursor.execute(
                "SELECT name, default_branch FROM repositories ORDER BY id LIMIT 1"
            )
            repo = cursor.fetchone()

            working_dir = None
            if repo:
                branch_name = repo["default_branch"]
                # Usa o BASE_DIR do banco de dados em vez do CLONE_DIR fixo
                working_dir = os.path.join(BASE_DIR, repo["name"], branch_name)

                if not os.path.exists(working_dir):
                    log_entry = f"ERRO: O diretório de trabalho esperado não foi encontrado no servidor: {working_dir}. Clone o branch '{branch_name}' primeiro."
                    cursor.execute(
                        "INSERT INTO execution_logs (pipeline_id, status, error, started_at, executed_by) VALUES (%s, %s, %s, %s, %s)",
                        (
                            pipeline_id,
                            "failed",
                            log_entry,
                            datetime.now(),
                            user_name,
                        ),
                    )
                    conn.commit()
                    pipeline_success = False
                    working_dir = None
            else:
                log_entry = "ERRO: Nenhum repositório clonado para definir o diretório de trabalho."
                cursor.execute(
                    "INSERT INTO execution_logs (pipeline_id, status, error, started_at, executed_by) VALUES (%s, %s, %s, %s, %s)",
                    (
                        pipeline_id,
                        "failed",
                        log_entry,
                        datetime.now(),
                        user_name,
                    ),
                )
                conn.commit()
                pipeline_success = False

            # ========================================================
            # DEBUG: Estado antes de executar comandos
            # ========================================================
            #flask_app.logger.info(f"🔍 DEBUG INICIAL - Pipeline ID: {pipeline_id}")
            #flask_app.logger.info(f"🔍 DEBUG INICIAL - Working Dir: {working_dir}")
            #flask_app.logger.info(f"🔍 DEBUG INICIAL - Pipeline Success: {pipeline_success}")
            #flask_app.logger.info(f"🔍 DEBUG INICIAL - Comandos a executar: {len(commands_to_run)}")

            if working_dir and pipeline_success:
                for command in commands_to_run:
                    cursor.execute(
                        "INSERT INTO execution_logs (pipeline_id, command_id, status, started_at, executed_by) VALUES (%s, %s, %s, %s, %s) RETURNING id",
                        (
                            pipeline_id,
                            command["id"],
                            "running",
                            datetime.now(),
                            user_name,
                        ),
                    )
                    log_id = cursor.fetchone()['id']
                    conn.commit()

                    # Substitui a variável ${BASE_DIR} no script antes de executar
                    script_to_run = command["script"].replace("${BASE_DIR}", BASE_DIR)

                    # ========================================================
                    # DEBUG: Informações do comando
                    # ========================================================
                    #flask_app.logger.info(f"🔍 DEBUG - Executando comando")
                    #flask_app.logger.info(f"🔍 DEBUG - Nome: {command.get('name', 'Sem nome')}")
                    #flask_app.logger.info(f"🔍 DEBUG - Tipo: {command.get('type', 'TIPO NÃO DEFINIDO')}")
                    #flask_app.logger.info(f"🔍 DEBUG - Working Dir: {working_dir}")
                    #flask_app.logger.info(f"🔍 DEBUG - Platform: {platform.system()}")

                    # ========================================================
                    # ENCAPSULAMENTO AUTOMÁTICO PARA POWERSHELL COM UNC
                    # ========================================================
                    if command["type"] == "powershell" and working_dir:
                        # Encapsula script PowerShell com navegação automática para UNC
                        script_to_run = f"""
                    # Navega para o diretório de trabalho (suporta UNC)
                    Push-Location '{working_dir}'

                    try {{
                        # ===== SCRIPT ORIGINAL INICIA =====
                        {script_to_run}
                        # ===== SCRIPT ORIGINAL TERMINA =====
                    }} catch {{
                        Write-Error "Erro na execução: $_"
                        throw
                    }} finally {{
                        # Sempre volta ao diretório original
                        Pop-Location
                    }}
                    """

                    # ========================================================
                    # EXECUÇÃO BASEADA NO INTERPRETADOR (não no SO)
                    # ========================================================
                    shell_command = []
                    use_cwd = False  # Controle se usa cwd ou não
                    encoding = 'utf-8'  # Encoding padrão

                    if command["type"] == "bash":
                        # Bash: sempre usa /bin/bash
                        shell_command = ["/bin/bash", "-c", script_to_run]
                        use_cwd = True  # Bash lida bem com cwd

                    elif command["type"] == "powershell":
                        # PowerShell: detecta disponibilidade
                        # Nota: script já está encapsulado com Push-Location se necessário
                        if platform.system() == "Windows":
                            shell_command = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script_to_run]
                            encoding = 'cp850'  # Windows Console usa cp850
                        else:
                            shell_command = ["pwsh", "-NoProfile", "-Command", script_to_run]
                        use_cwd = False  # PowerShell não usa cwd, Push-Location faz o trabalho

                    elif command["type"] == "batch" or command["type"] == "cmd":
                        # Batch/CMD: sempre cmd.exe no Windows
                        if platform.system() == "Windows":
                            shell_command = ["cmd.exe", "/c", script_to_run]
                            encoding = 'cp850'
                            use_cwd = False  # CMD com UNC: script deve usar pushd
                        else:
                            error_msg = f"ERRO: Scripts batch/cmd só são suportados no Windows."
                            cursor.execute(
                                "UPDATE execution_logs SET status = 'failed', error = %s WHERE id = %s",
                                (error_msg, log_id),
                            )
                            conn.commit()
                            pipeline_success = False
                            break

                    else:
                        error_msg = f"ERRO: Tipo de script '{command['type']}' não é suportado."
                        cursor.execute(
                            "UPDATE execution_logs SET status = 'failed', error = %s WHERE id = %s",
                            (error_msg, log_id),
                        )
                        conn.commit()
                        pipeline_success = False
                        break
                    
                    try:
                        # Executa comando com ou sem cwd dependendo do interpretador
                        process = subprocess.Popen(
                            shell_command,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            text=True,
                            cwd=working_dir if use_cwd else None,
                            bufsize=1,
                            universal_newlines=True,
                            encoding=encoding,
                            errors='replace'
                        )
                        output = ""
                        for line in process.stdout:
                            output += line
                            cursor.execute(
                                "UPDATE execution_logs SET output = %s WHERE id = %s",
                                (output, log_id),
                            )
                            conn.commit()

                        process.wait()

                        if process.returncode != 0:
                            raise subprocess.CalledProcessError(
                                process.returncode, shell_command, output=output
                            )

                        cursor.execute(
                            "UPDATE execution_logs SET status = 'success', finished_at = %s WHERE id = %s",
                            (datetime.now(), log_id),
                        )
                        conn.commit()

                    except subprocess.CalledProcessError as e:
                        error_output = (
                            f"{output}\n\nERRO (Código de Saída: {e.returncode})"
                        )
                        cursor.execute(
                            "UPDATE execution_logs SET status = 'failed', error = %s, finished_at = %s WHERE id = %s",
                            (error_output, datetime.now(), log_id),
                        )
                        conn.commit()
                        pipeline_success = False
                        break

            end_time = datetime.now()
            duration = str(end_time - start_time).split(".")[0]
            final_status = "success" if pipeline_success else "failed"

            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM pipelines WHERE id = %s", (pipeline_id,))

            pipeline = cursor.fetchone()
            if pipeline:
                event_manager.broadcast({
                    "type": "PIPELINE_FINISH",
                    "user": user_name,
                    "pipeline_name": pipeline["name"],
                    "status": final_status,
                    "duration": duration,
                    "timestamp": datetime.now()
                })

            cursor.execute(
                "UPDATE pipelines SET status = %s, duration = %s WHERE id = %s",
                (final_status, duration, pipeline_id),
            )
            conn.commit()

        finally:
            conn.close()
           
@app.route("/api/pipelines/<int:pipeline_id>/stream-logs")
@require_auth
def stream_logs(pipeline_id):
    def generate():
        # 🔧 CORREÇÃO: Aguardar logs por até 10 segundos
        max_wait_iterations = 10
        wait_iteration = 0
        start_time_of_this_run = None
        
        while wait_iteration < max_wait_iterations:
            conn_check = get_db()
            cursor_check = conn_check.cursor()
            cursor_check.execute(
                "SELECT MAX(started_at) as last_start FROM execution_logs WHERE pipeline_id = %s",
                (pipeline_id,),
            )
            last_run = cursor_check.fetchone()
            conn_check.close()
            
            if last_run and dict(last_run)["last_start"]:
                start_time_of_this_run = dict(last_run)["last_start"]
                break
            
            # Aguardar 1 segundo antes de tentar novamente
            wait_iteration += 1
            time.sleep(1)
        
        # Se após 10 segundos ainda não houver logs, retornar erro
        if not start_time_of_this_run:
            yield "data: ERRO: Não foi possível encontrar o início da execução após 10 segundos.\n\n"
            return
        sent_output = {}
        is_finished = False

        while not is_finished:
            conn = get_db()
            # Busca logs apenas desta execução específica
            cursor = conn.cursor()
            logs = cursor.execute(
                "SELECT * FROM execution_logs WHERE pipeline_id = %s AND started_at >= %s ORDER BY id",
                (pipeline_id, start_time_of_this_run),
            )
            logs = cursor.fetchall()

            # O restante da lógica de streaming continua igual...
            for log in logs:
                log_id = log["id"]
                full_log_text = (log["output"] or "") + (log["error"] or "")
                last_sent = sent_output.get(log_id, "")
                if len(full_log_text) > len(last_sent):
                    new_text = full_log_text[len(last_sent) :]
                    for line in new_text.splitlines():
                        yield f"data: {line}\n\n"
                    sent_output[log_id] = full_log_text

            cursor = conn.cursor()
            pipeline = cursor.execute(
                "SELECT status FROM pipelines WHERE id = %s", (pipeline_id,)
            )
            pipeline = cursor.fetchone()
            if pipeline and pipeline["status"] in ("success", "failed"):
                yield f"data: [FIM DA EXECUÇÃO - STATUS: {pipeline['status'].upper()}]\n\n"
                is_finished = True

            conn.close()
            time.sleep(1)

    return app.response_class(generate(), mimetype="text/event-stream")

@app.route("/api/events")
@require_auth # Garante que apenas usuários logados possam se conectar
def stream_events():
    def generate():
        q = event_manager.subscribe()
        try:
            while True:
                message = q.get()
                # Usamos json.dumps para enviar dados estruturados
                yield f"data: {json.dumps(message)}\n\n"
        except GeneratorExit:
            # Ocorre quando o cliente desconecta
            event_manager.unsubscribe(q)

    return app.response_class(generate(), mimetype="text/event-stream")

# =====================================================================
# ROTAS DE PIPELINE SCHEDULES
# =====================================================================

@app.route("/api/schedules", methods=["GET"])
@require_auth
def get_schedules():
    """Lista todos os schedules do ambiente"""
    env_id = request.headers.get("X-Environment-Id")
    if not env_id:
        return jsonify({"error": "Cabeçalho X-Environment-Id é obrigatório"}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.*, p.name as pipeline_name, u.username as created_by_name
        FROM pipeline_schedules s
        JOIN pipelines p ON s.pipeline_id = p.id
        JOIN users u ON s.created_by = u.id
        WHERE s.environment_id = %s
        ORDER BY s.created_at DESC
    """, (env_id,))
    schedules = cursor.fetchall()
    
    conn.close()
    return jsonify([dict(s) for s in schedules])


@app.route("/api/schedules", methods=["POST"])
@require_operator
def create_schedule():
    """Cria novo agendamento"""
    env_id = request.headers.get("X-Environment-Id")
    if not env_id:
        return jsonify({"error": "Cabeçalho X-Environment-Id é obrigatório"}), 400
    
    data = request.json
    required = ["pipeline_id", "name", "schedule_type", "schedule_config"]
    
    if not all(field in data for field in required):
        return jsonify({"error": "Campos obrigatórios faltando"}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Valida se pipeline existe no ambiente
        pipeline = cursor.execute(
            "SELECT id FROM pipelines WHERE id = %s AND environment_id = %s",
            (data["pipeline_id"], env_id)
        )
        pipeline = cursor.fetchone()
        
        if not pipeline:
            return jsonify({"error": "Pipeline não encontrada neste ambiente"}), 404
        
        # Calcula next_run_at inicial
        import json
        schedule_config = json.loads(data["schedule_config"]) if isinstance(data["schedule_config"], str) else data["schedule_config"]
        
        next_run = None
        if data["schedule_type"] == "once":
            next_run = schedule_config.get("datetime")
        else:
            # Para outros tipos, calcula baseado no helper
            temp_schedule = {
                'schedule_type': data["schedule_type"],
                'schedule_config': json.dumps(schedule_config)
            }
            next_run_dt = pipeline_scheduler._calculate_next_run(temp_schedule)
            next_run = next_run_dt.isoformat() if next_run_dt else None
        
        cursor.execute("""
            INSERT INTO pipeline_schedules 
            (pipeline_id, environment_id, name, description, schedule_type, 
             schedule_config, is_active, created_by, created_at, next_run_at)
            VALUES (%s, %s, %s, %s, %s, %s, False, %s, %s, %s) RETURNING id
        """, (
            data["pipeline_id"],
            env_id,
            data["name"],
            data.get("description", ""),
            data["schedule_type"],
            json.dumps(schedule_config),
            request.current_user["id"],
            datetime.now(),
            next_run
        ))
        
        schedule_id = cursor.fetchone()['id']
        conn.commit()
        
        return jsonify({
            "success": True,
            "id": schedule_id,
            "message": "Agendamento criado com sucesso (INATIVO)"
        }), 201
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


@app.route("/api/schedules/<int:schedule_id>", methods=["PUT"])
@require_operator
def update_schedule(schedule_id):
    """Atualiza agendamento"""
    env_id = request.headers.get("X-Environment-Id")
    if not env_id:
        return jsonify({"error": "Ambiente não especificado"}), 400
    
    data = request.json
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Verifica se existe
        schedule = cursor.execute(
            "SELECT id FROM pipeline_schedules WHERE id = %s AND environment_id = %s",
            (schedule_id, env_id)
        )
        schedule = cursor.fetchone()
        
        if not schedule:
            return jsonify({"error": "Agendamento não encontrado"}), 404
        
        # Recalcula next_run se schedule_config mudou
        import json
        schedule_config = json.loads(data["schedule_config"]) if isinstance(data["schedule_config"], str) else data["schedule_config"]
        
        temp_schedule = {
            'schedule_type': data["schedule_type"],
            'schedule_config': json.dumps(schedule_config)
        }
        next_run_dt = pipeline_scheduler._calculate_next_run(temp_schedule)
        next_run = next_run_dt.isoformat() if next_run_dt else None
        
        cursor.execute("""
            UPDATE pipeline_schedules
            SET name = %s, description = %s, schedule_type = %s, 
                schedule_config = %s, next_run_at = %s, updated_at = %s
            WHERE id = %s AND environment_id = %s
        """, (
            data["name"],
            data.get("description", ""),
            data["schedule_type"],
            json.dumps(schedule_config),
            next_run,
            datetime.now(),
            schedule_id,
            env_id
        ))
        
        conn.commit()
        return jsonify({"success": True, "message": "Agendamento atualizado"})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


@app.route("/api/schedules/<int:schedule_id>/toggle", methods=["PATCH"])
@require_operator
def toggle_schedule(schedule_id):
    """Ativa/Desativa agendamento"""
    env_id = request.headers.get("X-Environment-Id")
    if not env_id:
        return jsonify({"error": "Ambiente não especificado"}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        schedule = cursor.execute(
            "SELECT is_active FROM pipeline_schedules WHERE id = %s AND environment_id = %s",
            (schedule_id, env_id)
        )
        schedule = cursor.fetchone()
        
        if not schedule:
            return jsonify({"error": "Agendamento não encontrado"}), 404
        
        new_status = not schedule["is_active"]  # Inverte o boolean

        cursor.execute("""
            UPDATE pipeline_schedules
            SET is_active = %s, updated_at = %s
            WHERE id = %s AND environment_id = %s
        """, (new_status, datetime.now(), schedule_id, env_id))

        conn.commit()

        status_text = "ativado" if new_status else "desativado"
        return jsonify({
            "success": True,
            "is_active": new_status,
            "message": f"Agendamento {status_text}"
        })
        
    finally:
        conn.close()


@app.route("/api/schedules/<int:schedule_id>", methods=["DELETE"])
@require_operator
def delete_schedule(schedule_id):
    """Deleta agendamento"""
    env_id = request.headers.get("X-Environment-Id")
    if not env_id:
        return jsonify({"error": "Ambiente não especificado"}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        schedule = cursor.execute(
            "SELECT name FROM pipeline_schedules WHERE id = %s AND environment_id = %s",
            (schedule_id, env_id)
        )
        schedule = cursor.fetchone()
        
        if not schedule:
            return jsonify({"error": "Agendamento não encontrado"}), 404
        
        cursor.execute(
            "DELETE FROM pipeline_schedules WHERE id = %s AND environment_id = %s",
            (schedule_id, env_id)
        )
        
        conn.commit()
        return jsonify({
            "success": True,
            "message": f"Agendamento '{schedule['name']}' excluído"
        })
        
    finally:
        conn.close()

# =====================================================================
# MIDDLEWARE GLOBAL DE RATE LIMITING
# =====================================================================

@app.before_request
def global_rate_limit():
    """
    Rate limiting global para TODAS as rotas da API.
    Previne abuso generalizado.
    """
    # Só aplica em rotas da API
    if not request.path.startswith('/api/'):
        return None
    
    # Rate limit global: 1000 requisições por hora por IP
    identifier = f"global_{request.remote_addr}"
    allowed, retry_after = rate_limiter.is_allowed(identifier, 1000, 3600)
    
    if not allowed:
        return jsonify({
            "error": "Rate limit global excedido. Contate o administrador.",
            "retry_after": retry_after
        }), 429
    
    return None

# =====================================================================
# ENDPOINT PARA MONITORAMENTO (ADMIN)
# =====================================================================

@app.route("/api/admin/rate-limits", methods=["GET"])
@require_admin
def get_rate_limits():
    """Retorna estatísticas de rate limiting (apenas admin)"""
    with rate_limiter.lock:
        stats = {
            "active_identifiers": len(rate_limiter.requests),
            "total_tracked_requests": sum(len(reqs) for reqs in rate_limiter.requests.values()),
            "top_requesters": []
        }
        
        # Top 10 usuários com mais requisições
        sorted_requests = sorted(
            rate_limiter.requests.items(),
            key=lambda x: len(x[1]),
            reverse=True
        )[:10]
        
        for identifier, requests in sorted_requests:
            stats["top_requesters"].append({
                "identifier": identifier,
                "request_count": len(requests)
            })
        
        return jsonify(stats)


@app.route("/api/admin/rate-limits/clear", methods=["POST"])
@require_admin
def clear_rate_limits():
    """Limpa todos os rate limits (apenas admin)"""
    data = request.json
    identifier = data.get("identifier")
    
    if identifier:
        rate_limiter.clear_user(identifier)
        return jsonify({"success": True, "message": f"Rate limit limpo para {identifier}"})
    else:
        # Limpa tudo
        with rate_limiter.lock:
            rate_limiter.requests.clear()
        return jsonify({"success": True, "message": "Todos os rate limits foram limpos"})
    
# =====================================================================
# ROTAS DE REPOSITÓRIOS
# =====================================================================


@app.route("/api/repositories", methods=["GET"])
@require_auth
@rate_limit(max_requests=120, window_seconds=60)  # 120 req/min
def get_repositories():
    """Lista repositórios com rate limiting"""
    env_id = request.headers.get('X-Environment-Id')
    if not env_id:
        return jsonify({"error": "Ambiente não especificado"}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM repositories WHERE environment_id = %s ORDER BY name",
        (int(env_id),)
    )
    repositories = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(repositories)


@app.route("/api/repositories", methods=["POST"])
@require_operator
def save_repositories():
    env_id = request.headers.get("X-Environment-Id")
    if not env_id:
        return jsonify({"error": "Cabeçalho X-Environment-Id é obrigatório"}), 400
   
    data = request.json
    if not isinstance(data, list):
        return jsonify({"error": "Esperado array de repositórios"}), 400

    conn = get_db()
    cursor = conn.cursor()
    
    saved_count = 0
    for repo in data:
        # Verificar se já existe neste ambiente
        cursor.execute(
            "SELECT id FROM repositories WHERE github_id = %s AND environment_id = %s", 
            (repo.get("id"), env_id)
        )
        existing = cursor.fetchone()

        if existing:
            # Atualizar (a lógica de update não precisa mudar, pois já filtra pelo ID único do repo)
            cursor.execute(                
                """
                UPDATE repositories 
                SET name = %s, full_name = %s, description = %s, private = %s, 
                    html_url = %s, clone_url = %s, language = %s, default_branch = %s,
                    size = %s, updated_at = %s
                WHERE id = %s
                """,
                (
                    repo["name"], repo.get("full_name"), repo.get("description"),
                    repo.get("private"), repo.get("html_url"), repo.get("clone_url"),
                    repo.get("language"), repo.get("default_branch"), repo.get("size"),
                    repo.get("updated_at"), existing["id"]
                ),
            )
        else:
            # --- INÍCIO DA CORREÇÃO ---
            # Inserir NOVO registro, agora incluindo o environment_id
            cursor.execute(                
                """
                INSERT INTO repositories (environment_id, github_id, name, full_name, description, private,
                                        html_url, clone_url, language, default_branch, size, updated_at, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    env_id,  # <-- ESTAVA FALTANDO
                    repo["id"],
                    repo["name"],
                    repo.get("full_name"),
                    repo.get("description"),
                    repo.get("private"),
                    repo.get("html_url"),
                    repo.get("clone_url"),
                    repo.get("language"),
                    repo.get("default_branch"),
                    repo.get("size"),
                    repo.get("updated_at"),
                    repo.get("created_at")
                ),
            )
            # --- FIM DA CORREÇÃO ---
            saved_count += 1

    conn.commit()
    conn.close()

    return jsonify(
        {
            "success": True,
            "saved": saved_count,
            "message": f"{saved_count} novos repositórios salvos neste ambiente.",
        }
    )


@app.route("/api/repositories/<int:repo_id>/clone", methods=["POST"])
@require_operator
@rate_limit(max_requests=10, window_seconds=300)  # 10 clones a cada 5 min
def clone_repository(repo_id):
    """Clone com token descriptografado"""
    data = request.json
    branch_name = data.get("branch_name")

    conn = get_db()
    cursor = conn.cursor()
    
    BASE_DIR = get_base_dir_for_repo(cursor, repo_id)
    
    repo = cursor.execute(
        "SELECT * FROM repositories WHERE id = %s", (repo_id,)
    )
    repo = cursor.fetchone()
    
    settings = cursor.execute(
        "SELECT token FROM github_settings WHERE id = 1"
    )
    settings = cursor.fetchone()
    
    conn.close()

    if not repo:
        return jsonify({"error": "Repositório não encontrado"}), 404
    if not settings or not settings["token"]:
        return jsonify({"error": "Token do GitHub não configurado"}), 400

    # NOVO: Descriptografa token
    encrypted_token = settings["token"]
    
    # Tenta descriptografar se o sistema de criptografia estiver disponível
    if token_encryption is not None and token_encryption.is_initialized():
        try:
            github_token = token_encryption.decrypt_token(encrypted_token)
            print(f"✓ Token descriptografado com sucesso para repo_id={repo_id}")
        except Exception as e:
            # Fallback: pode ser um token plain text antigo
            print(f"⚠️  Falha ao descriptografar token (tentando plain text): {e}")
            github_token = encrypted_token
    else:
        # Sistema de criptografia não disponível, usa token plain text
        print(f"⚠️  Criptografia não inicializada, usando token plain text")
        github_token = encrypted_token
    
    if not github_token:
        return jsonify({"error": "Token do GitHub não configurado"}), 400

    try:
        # Sanitização de entrada
        repo_name = sanitize_path_component(repo["name"])
        branch_name = sanitize_branch_name(branch_name or repo["default_branch"])
        clone_url = validate_git_url(repo["clone_url"])
        
    except ValueError as e:
        return jsonify({"error": f"Validação falhou: {str(e)}"}), 400

    target_path = os.path.join(BASE_DIR, repo_name, branch_name)
    
    # Valida path
    real_base = os.path.realpath(BASE_DIR)
    real_target = os.path.realpath(target_path)
    if not real_target.startswith(real_base):
        return jsonify({"error": "Path traversal detectado"}), 400

    # Adiciona token descriptografado de forma segura
    auth_clone_url = clone_url.replace("https://", f"https://{github_token}@")

    # Remove diretório existente se houver
    if os.path.exists(target_path):
        try:
            shutil.rmtree(target_path)
        except OSError as e:
            return jsonify({"error": f"Não foi possível remover diretório: {e.strerror}"}), 500

    try:
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        
        # Execução segura do comando Git
        execute_git_command_safely([
            'git', 'clone',
            '-b', branch_name,
            '--single-branch',
            auth_clone_url,
            target_path
        ], timeout=300)
        
        return jsonify({
            "success": True,
            "message": f"Repositório '{repo_name}' (branch: {branch_name}) clonado com sucesso."
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    pass


@app.route("/api/repositories/<int:repo_id>/pull", methods=["POST"])
@require_operator
def pull_repository(repo_id):
    """Pull seguro de repositório"""
    data = request.json
    branch_name = data.get("branch_name")
    
    if not branch_name:
        return jsonify({"error": "Nome do branch é obrigatório"}), 400

    conn = get_db()
    cursor = conn.cursor()
    BASE_DIR = get_base_dir_for_repo(cursor, repo_id)
    
    cursor = conn.cursor()
    repo = cursor.execute(
        "SELECT name FROM repositories WHERE id = %s", (repo_id,)
    )
    repo = cursor.fetchone()
    conn.close()

    if not repo:
        return jsonify({"error": "Repositório não encontrado"}), 404

    try:
        # NOVO: Sanitização
        repo_name = sanitize_path_component(repo["name"])
        branch_name = sanitize_branch_name(branch_name)
    except ValueError as e:
        return jsonify({"error": f"Validação falhou: {str(e)}"}), 400

    repo_path = os.path.join(BASE_DIR, repo_name, branch_name)
    
    # Valida path
    real_base = os.path.realpath(BASE_DIR)
    real_target = os.path.realpath(repo_path)
    if not real_target.startswith(real_base):
        return jsonify({"error": "Path traversal detectado"}), 400

    if not os.path.exists(repo_path):
        return jsonify({
            "error": f"O branch '{branch_name}' não foi clonado no servidor ainda."
        }), 404

    try:
        # NOVO: Comandos Git seguros
        execute_git_command_safely(['git', 'fetch', 'origin'], cwd=repo_path)
        result = execute_git_command_safely([
            'git', 'reset', '--hard', f'origin/{branch_name}'
        ], cwd=repo_path)
        
        return jsonify({
            "success": True,
            "message": "Sincronização forçada concluída!",
            "details": result.stdout.strip()
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/repositories/<int:repo_id>/push", methods=["POST"])
@require_operator
def push_repository(repo_id):
    """Push seguro de alterações"""
    data = request.json
    commit_message = data.get("commit_message")
    branch_name = data.get("branch_name")

    if not commit_message or not branch_name:
        return jsonify({"error": "Mensagem e branch são obrigatórios"}), 400

    conn = get_db()
    cursor = conn.cursor()
    BASE_DIR = get_base_dir_for_repo(cursor, repo_id)
    
    cursor = conn.cursor()
    repo = cursor.execute(
        "SELECT * FROM repositories WHERE id = %s", (repo_id,)
    )
    repo = cursor.fetchone()
    conn.close()

    if not repo:
        return jsonify({"error": "Repositório não encontrado"}), 404

    try:
        # NOVO: Sanitização de todas as entradas
        repo_name = sanitize_path_component(repo["name"])
        branch_name = sanitize_branch_name(branch_name)
        safe_message = sanitize_commit_message(commit_message)
    except ValueError as e:
        return jsonify({"error": f"Validação falhou: {str(e)}"}), 400

    repo_path = os.path.join(BASE_DIR, repo_name, branch_name)
    
    # Valida path
    real_base = os.path.realpath(BASE_DIR)
    real_target = os.path.realpath(repo_path)
    if not real_target.startswith(real_base):
        return jsonify({"error": "Path traversal detectado"}), 400

    if not os.path.exists(repo_path):
        return jsonify({
            "error": f"O branch '{branch_name}' não foi clonado no servidor ainda."
        }), 404

    try:
        # Buscar configurações do GitHub para identidade do commit
        conn_git = get_db()
        cursor_git = conn_git.cursor()
        cursor_git.execute("SELECT username FROM github_settings WHERE id = 1")
        github_settings = cursor_git.fetchone()
        conn_git.close()
        
        if github_settings and github_settings.get("username"):
            git_user = github_settings["username"]
            git_email = f"{git_user}@users.noreply.github.com"
        else:
            # Fallback para usuário logado
            git_user = request.current_user.get("name", "AtuRPO DevOps")
            git_email = request.current_user.get("email", "devops@aturpo.local")
        
        execute_git_command_safely(['git', 'config', 'user.name', git_user], cwd=repo_path)
        execute_git_command_safely(['git', 'config', 'user.email', git_email], cwd=repo_path)
        
        # NOVO: Sequência segura de comandos Git
        execute_git_command_safely(['git', 'add', '.'], cwd=repo_path)
        execute_git_command_safely(['git', 'commit', '-m', safe_message], cwd=repo_path)
        result = execute_git_command_safely(['git', 'push', 'origin', branch_name], cwd=repo_path)
        
        return jsonify({
            "success": True,
            "message": f"Alterações enviadas para '{branch_name}' com sucesso!",
            "details": result.stdout.strip()
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/repositories/<int:repo_id>", methods=["DELETE"])
@require_operator
def delete_repository(repo_id):
    """Remove repositório da lista"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM repositories WHERE id = %s", (repo_id,))
    conn.commit()
    conn.close()

    return jsonify({"success": True, "message": "Repositório removido"})


@app.route("/api/repositories/<int:repo_id>/tag", methods=["POST"])
@require_operator
def tag_repository(repo_id):
    data = request.json
    tag_name = data.get("tag_name")
    message = data.get("message")

    if not tag_name or not message:
        return jsonify({"error": "Nome da tag e mensagem são obrigatórios"}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM repositories WHERE id = %s", (repo_id,))
    repo = cursor.fetchone()
    conn.close()

    if not repo:
        return jsonify({"error": "Repositório não encontrado"}), 404

    repo_name = repo["name"]
    repo_path = os.path.join(CLONE_DIR, repo_name)

    if not os.path.exists(repo_path):
        return (
            jsonify(
                {
                    "error": f"Repositório '{repo_name}' não foi clonado no servidor ainda."
                }
            ),
            404,
        )

    try:
        # (NOVO E CRUCIAL) Configurar a identidade para o commit da tag
        # Usaremos o nome do usuário logado que realizou a ação
        user_name = request.current_user["name"]
        user_email = request.current_user["email"]
        subprocess.run(
            ["git", "config", "user.name", f'"{user_name}"'], cwd=repo_path, check=True
        )
        subprocess.run(
            ["git", "config", "user.email", f'"{user_email}"'],
            cwd=repo_path,
            check=True,
        )

        # Passo 1: Criar a tag anotada
        subprocess.run(
            ["git", "tag", "-a", tag_name, "-m", message],
            cwd=repo_path,
            check=True,
            capture_output=True,
            text=True,
        )

        # Passo 2: Empurrar a nova tag para o 'origin' (GitHub)
        result = subprocess.run(
            ["git", "push", "origin", tag_name],
            cwd=repo_path,
            check=True,
            capture_output=True,
            text=True,
        )

        return jsonify(
            {
                "success": True,
                "message": f"Tag '{tag_name}' criada e enviada para o GitHub com sucesso!",
                "details": result.stderr.strip(),  # git push usa stderr para mensagens de status
            }
        )
    except subprocess.CalledProcessError as e:
        # Se a tag já existir, o git tag falhará. Vamos tratar isso.
        error_details = e.stderr.strip()
        if "already exists" in error_details:
            return (
                jsonify({"error": f"A tag '{tag_name}' já existe neste repositório."}),
                409,
            )

        return (
            jsonify(
                {"error": "Falha ao criar ou enviar a tag", "details": error_details}
            ),
            500,
        )


@app.route("/api/repositories/<int:repo_id>/branches", methods=["GET"])
@require_auth
def list_branches(repo_id):
    """Lista todos os branches remotos de um repositório clonado."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM repositories WHERE id = %s", (repo_id,))
    repo = cursor.fetchone()
    conn.close()

    if not repo:
        return jsonify({"error": "Repositório não encontrado"}), 404

    repo_path = os.path.join(CLONE_DIR, repo["name"])
    if not os.path.exists(repo_path):
        return jsonify({"error": "Repositório não clonado no servidor."}), 404

    try:
        # Usamos 'git branch -r' para listar branches remotos (origin/main, etc.)
        result = subprocess.run(
            ["git", "branch", "-r"],
            cwd=repo_path,
            check=True,
            capture_output=True,
            text=True,
        )

        branches_raw = result.stdout.strip().split("\n")
        branches = []
        for branch in branches_raw:
            # Limpa o nome do branch (ex: "  origin/main" -> "main")
            # E ignora a linha "origin/HEAD -> ..."
            if "->" not in branch:
                clean_branch = branch.strip().replace("origin/", "")
                branches.append(clean_branch)

        return jsonify(branches)
    except subprocess.CalledProcessError as e:
        return jsonify({"error": "Falha ao listar branches", "details": e.stderr}), 500


@app.route("/api/repositories/<int:repo_id>/branch", methods=["POST"])
@require_operator
def create_branch(repo_id):
    """Criação segura de branch"""
    data = request.json
    new_branch_name = data.get("new_branch_name")
    base_branch_name = data.get("base_branch_name")

    if not new_branch_name or not base_branch_name:
        return jsonify({"error": "Nomes de branch são obrigatórios"}), 400

    conn = get_db()
    cursor = conn.cursor()
    BASE_DIR = get_base_dir_for_repo(cursor, repo_id)
    
    cursor = conn.cursor()
    repo = cursor.execute(
        "SELECT name FROM repositories WHERE id = %s", (repo_id,)
    )
    repo = cursor.fetchone()
    conn.close()

    if not repo:
        return jsonify({"error": "Repositório não encontrado"}), 404

    try:
        # NOVO: Sanitização
        repo_name = sanitize_path_component(repo["name"])
        new_branch = sanitize_branch_name(new_branch_name)
        base_branch = sanitize_branch_name(base_branch_name)
    except ValueError as e:
        return jsonify({"error": f"Validação falhou: {str(e)}"}), 400

    repo_path = os.path.join(BASE_DIR, repo_name, base_branch)
    
    # Valida path
    real_base = os.path.realpath(BASE_DIR)
    real_target = os.path.realpath(repo_path)
    if not real_target.startswith(real_base):
        return jsonify({"error": "Path traversal detectado"}), 400

    if not os.path.exists(repo_path):
        return jsonify({
            "error": f"Branch base '{base_branch}' não existe localmente."
        }), 404

    try:
        # NOVO: Comandos Git seguros
        execute_git_command_safely(['git', 'checkout', base_branch], cwd=repo_path)
        execute_git_command_safely(['git', 'checkout', '-b', new_branch], cwd=repo_path)
        result = execute_git_command_safely(['git', 'push', '-u', 'origin', new_branch], cwd=repo_path)
        
        return jsonify({
            "success": True,
            "message": f"Branch '{new_branch}' criada com sucesso!",
            "details": result.stdout.strip()
        })
        
    except Exception as e:
        error_msg = str(e)
        if "already exists" in error_msg:
            return jsonify({"error": f"A branch '{new_branch}' já existe"}), 409
        return jsonify({"error": error_msg}), 500


# =====================================================================
# ROTAS DE CONFIGURAÇÕES GITHUB
# =====================================================================


@app.route("/api/github-settings", methods=["GET"])
@require_auth
def get_github_settings():
    """Busca configurações GitHub (retorna token descriptografado)"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT token, username, saved_at FROM github_settings WHERE id = 1")
    settings = cursor.fetchone()
    conn.close()

    if settings:
        settings_dict = dict(settings)
        
        # NOVO: Descriptografa token antes de retornar
        encrypted_token = settings_dict.get('token')
        if encrypted_token:
            decrypted_token = token_encryption.decrypt_token(encrypted_token)
            settings_dict['token'] = decrypted_token
        
        return jsonify(settings_dict)
    
    return jsonify({"token": "", "username": "", "saved_at": None})


@app.route("/api/github-settings", methods=["POST"])
@require_admin
def save_github_settings():
    """Salva configurações GitHub (criptografa token antes de salvar)"""
    data = request.json

    if not data.get("token") or not data.get("username"):
        return jsonify({"error": "Token e username são obrigatórios"}), 400
    
    # Valida formato do token
    token = data["token"]
    if not (token.startswith('ghp_') or token.startswith('github_pat_')):
        return jsonify({"error": "Formato de token GitHub inválido"}), 400

    # NOVO: Criptografa token antes de salvar
    encrypted_token = token_encryption.encrypt_token(token)
    
    conn = get_db()
    cursor = conn.cursor()

    # Verificar se já existe
    cursor.execute("SELECT id FROM github_settings WHERE id = 1")
    existing = cursor.fetchone()

    try:
        if existing:
            cursor.execute(
                """
                UPDATE github_settings 
                SET token = %s, username = %s, saved_at = %s
                WHERE id = 1
                """,
                (encrypted_token, data["username"], datetime.now())
            )
        else:
            cursor.execute(
                """
                INSERT INTO github_settings (id, token, username, saved_at)
                VALUES (%s, %s, %s, %s)
                """,
                (1, encrypted_token, data["username"], datetime.now())
            )

        conn.commit()
        return jsonify({
            "success": True, 
            "message": "Configurações GitHub salvas com sucesso (token criptografado)"
        })
        
    except PsycopgError as e:
        return jsonify({"error": f"Erro ao salvar: {str(e)}"}), 500
    finally:
        conn.close()


# =====================================================================
# ROTAS DE LOGS
# =====================================================================


@app.route("/api/logs", methods=["GET"])
@require_auth
def get_logs():
    pipeline_id = request.args.get("pipeline_id", type=int)
    page = request.args.get("page", 1, type=int)
    limit = 30
    offset = (page - 1) * limit

    conn = get_db()

    if pipeline_id:
        # Lógica para "VER LOGS" da última execução
        last_run_query = "SELECT MAX(started_at) as last_start FROM execution_logs WHERE pipeline_id = %s"
        cursor = conn.cursor()
        cursor.execute(last_run_query, (pipeline_id,))

        last_run = cursor.fetchone()

        if not last_run or not dict(last_run)["last_start"]:
            conn.close()
            return jsonify({"logs": [], "total": 0, "page": 1, "limit": limit})

        query = "SELECT * FROM execution_logs WHERE pipeline_id = %s AND started_at >= %s ORDER BY id"
        params = (pipeline_id, dict(last_run)["last_start"])
        total_query = "SELECT COUNT(*) FROM execution_logs WHERE pipeline_id = %s AND started_at >= %s"
        total_params = (pipeline_id, dict(last_run)["last_start"])
    else:
        # Lógica CORRIGIDA para "HISTÓRICO GERAL"
        query = """
            SELECT 
                p.name as pipeline_name, 
                c.name as command_name,
                l.executed_by, 
                l.started_at, 
                l.status
            FROM execution_logs l
            LEFT JOIN pipelines p ON l.pipeline_id = p.id
            LEFT JOIN commands c ON l.command_id = c.id
            ORDER BY l.started_at DESC
            LIMIT %s OFFSET %s
        """
        params = (limit, offset)
        total_query = "SELECT COUNT(*) FROM execution_logs"
        total_params = ()

    cursor = conn.cursor()
    cursor.execute(total_query, total_params)

    total_logs = cursor.fetchone()['id']
    cursor = conn.cursor()
    cursor.execute(query, params)

    logs_data = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return jsonify(
        {"logs": logs_data, "total": total_logs, "page": page, "limit": limit}
    )


# =====================================================================
# ROTA DE SAÚDE
# =====================================================================


@app.route("/api/health", methods=["GET"])
def health_check():
    """Verifica saúde da API"""
    conn = get_db()
    cursor = conn.cursor()

    # Contar registros
    cursor.execute("SELECT COUNT(*) as count FROM users")
    users_count = cursor.fetchone()["count"]

    cursor.execute("SELECT COUNT(*) as count FROM commands")
    commands_count = cursor.fetchone()["count"]

    cursor.execute("SELECT COUNT(*) as count FROM pipelines")
    pipelines_count = cursor.fetchone()["count"]

    cursor.execute("SELECT COUNT(*) as count FROM repositories")
    repos_count = cursor.fetchone()["count"]

    conn.close()

    return jsonify(
        {
            "status": "healthy",
            "database": "connected",
            "stats": {
                "users": users_count,
                "commands": commands_count,
                "pipelines": pipelines_count,
                "repositories": repos_count,
            },
        }
    )


# =====================================================================
# DASHBOARD API ENDPOINT
# =====================================================================

@app.route("/api/dashboard/stats", methods=["GET"])
@require_auth
def get_dashboard_stats():
    """Retorna estatísticas para o Dashboard"""
    env_id = request.headers.get("X-Environment-Id")
    if not env_id:
        return jsonify({"error": "Ambiente não especificado"}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Métricas de Pipelines
        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE pr.status = 'success') as success,
                COUNT(*) FILTER (WHERE pr.status = 'failed') as failed,
                COUNT(*) FILTER (WHERE pr.status = 'running') as running
            FROM pipeline_runs pr
            WHERE pr.environment_id = %s
        """, (env_id,))
        pipeline_stats = dict(cursor.fetchone())
        
        # Últimas 5 execuções
        cursor.execute("""
            SELECT 
                pr.id, pr.run_number, pr.status, pr.started_at, pr.finished_at,
                pr.trigger_type, p.name as pipeline_name
            FROM pipeline_runs pr
            JOIN pipelines p ON pr.pipeline_id = p.id
            WHERE pr.environment_id = %s
            ORDER BY pr.started_at DESC
            LIMIT 5
        """, (env_id,))
        recent_runs = [dict(row) for row in cursor.fetchall()]
        
        # Métricas de Releases (Deploys)
        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE r.status = 'success') as success,
                COUNT(*) FILTER (WHERE r.status = 'failed') as failed
            FROM releases r
            JOIN pipelines p ON r.pipeline_id = p.id
            WHERE p.environment_id = %s
        """, (env_id,))
        release_stats = dict(cursor.fetchone())
        
        # Schedules Ativos
        cursor.execute("""
            SELECT 
                s.id, s.name, s.next_run_at, s.is_active,
                p.name as pipeline_name, s.schedule_type
            FROM pipeline_schedules s
            JOIN pipelines p ON s.pipeline_id = p.id
            WHERE s.environment_id = %s AND s.is_active = true
            ORDER BY s.next_run_at ASC
            LIMIT 5
        """, (env_id,))
        active_schedules = [dict(row) for row in cursor.fetchall()]
        
        # Status de Serviços (Service Actions)
        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE is_active = true) as active
            FROM service_actions
            WHERE environment_id = %s
        """, (env_id,))
        service_stats = dict(cursor.fetchone())
        
        # Últimas execuções de Service Actions (com last_run_at preenchido)
        cursor.execute("""
            SELECT 
                id, name, action_type, os_type, last_run_at, is_active
            FROM service_actions
            WHERE environment_id = %s AND last_run_at IS NOT NULL
            ORDER BY last_run_at DESC
            LIMIT 5
        """, (env_id,))
        recent_service_actions = [dict(row) for row in cursor.fetchall()]
        
        # Próximos agendamentos de Service Actions
        cursor.execute("""
            SELECT 
                id, name, action_type, os_type, schedule_type, next_run_at, is_active
            FROM service_actions
            WHERE environment_id = %s AND is_active = true AND next_run_at IS NOT NULL
            ORDER BY next_run_at ASC
            LIMIT 5
        """, (env_id,))
        scheduled_service_actions = [dict(row) for row in cursor.fetchall()]
        
        # Contadores gerais
        cursor.execute("SELECT COUNT(*) as count FROM pipelines WHERE environment_id = %s", (env_id,))
        total_pipelines = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM commands WHERE environment_id = %s", (env_id,))
        total_commands = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM repositories")
        total_repos = cursor.fetchone()['count']
        
        conn.close()
        
        return jsonify({
            "pipeline_runs": convert_datetime_to_str(pipeline_stats),
            "recent_runs": convert_datetime_to_str(recent_runs),
            "releases": release_stats,
            "active_schedules": convert_datetime_to_str(active_schedules),
            "service_actions": service_stats,
            "recent_service_actions": convert_datetime_to_str(recent_service_actions),
            "scheduled_service_actions": convert_datetime_to_str(scheduled_service_actions),
            "totals": {
                "pipelines": total_pipelines,
                "commands": total_commands,
                "repositories": total_repos
            }
        })
        
    except Exception as e:
        app.logger.error(f"Erro ao buscar stats do dashboard: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            conn.close()

# =====================================================================
# ROTA DE KEEP-ALIVE DA SESSÃO
# =====================================================================

@app.route("/api/session/keep-alive", methods=["POST"])
@require_auth_no_update
def keep_alive():
    """
    Endpoint 'vazio' que serve apenas para ser chamado periodicamente
    pelo frontend para manter a sessão do usuário ativa.
    O decorator @require_auth já faz todo o trabalho de atualizar o 'last_activity'.
    """
    return jsonify({"success": True, "message": "Session kept alive"}), 200

# =====================================================================
# ROTAS PARA SERVIR O FRONTEND (INDEX.HTML E ARQUIVOS ESTÁTICOS)
# =====================================================================


@app.route("/")
def serve_index():
    """Serve o arquivo principal index.html"""
    # O '..' sobe um nível de diretório, assumindo que app.py está em uma pasta 'backend'
    # return send_from_directory("..", "index.html")
    return send_from_directory(".", "index.html")


@app.route("/<path:filename>")
def serve_static(filename):
    """Serve outros arquivos estáticos (js, css, etc.)"""
    # O '..' sobe um nível de diretório
    # return send_from_directory("..", filename)
    return send_from_directory(".", filename)

# =====================================================================
# ROTAS DE GESTÃO DE SERVIÇOS (SERVICE ACTIONS)
# =====================================================================

@app.route("/api/service-actions", methods=["GET"])
@require_auth
def get_service_actions():
    """Lista todas as ações de serviços"""
    env_id = request.headers.get("X-Environment-Id")
    if not env_id:
        return jsonify({"error": "Ambiente não especificado"}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM service_actions WHERE environment_id = %s ORDER BY name",
        (env_id,)
    )
    actions = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(actions)

@app.route("/api/service-actions", methods=["POST"])
@require_operator
def create_service_action():
    """Cria nova ação de serviço"""
    env_id = request.headers.get("X-Environment-Id")
    if not env_id:
        return jsonify({"error": "Ambiente não especificado"}), 400
    
    data = request.json
    
    if not data.get("name") or not data.get("action_type") or not data.get("os_type") or not data.get("service_ids"):
        return jsonify({"error": "Campos obrigatórios: name, action_type, os_type, service_ids"}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Calcular next_run_at se tiver agendamento
        next_run_at = None
        if data.get("schedule_type") and data.get("schedule_config"):
            schedule_config = json.loads(data.get("schedule_config")) if isinstance(data.get("schedule_config"), str) else data.get("schedule_config")
            
            if data.get("schedule_type") == "once":
                # Para execução única, pegar datetime do config como STRING (igual pipeline_schedules)
                next_run_at = schedule_config.get("datetime")
            else:
                # Para outros tipos, usar _calculate_next_run
                temp_schedule = {
                    'schedule_type': data.get("schedule_type"),
                    'schedule_config': json.dumps(schedule_config) if isinstance(schedule_config, dict) else schedule_config
                }
                next_run_dt = pipeline_scheduler._calculate_next_run(temp_schedule)
                next_run_at = next_run_dt.isoformat() if next_run_dt else None
        
        cursor.execute(
            """INSERT INTO service_actions 
            (environment_id, name, description, action_type, os_type, force_stop, service_ids, 
             schedule_type, schedule_config, is_active, next_run_at, created_by, created_at) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (
                env_id,
                data["name"],
                data.get("description", ""),
                data["action_type"],
                data["os_type"],
                data.get("force_stop", False),
                data["service_ids"],
                data.get("schedule_type"),
                data.get("schedule_config"),
                data.get("is_active", False),
                next_run_at,
                request.current_user["id"],
                now_br()
            )
        )
        action_id = cursor.fetchone()['id']
        conn.commit()
        return jsonify({"success": True, "id": action_id, "message": "Ação criada com sucesso"}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route("/api/service-actions/<int:action_id>", methods=["PUT"])
@require_operator
def update_service_action(action_id):
    """Atualiza ação de serviço"""
    env_id = request.headers.get("X-Environment-Id")
    if not env_id:
        return jsonify({"error": "Ambiente não especificado"}), 400
    
    data = request.json
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Buscar dados atuais da ação
        cursor.execute(
            "SELECT * FROM service_actions WHERE id = %s AND environment_id = %s",
            (action_id, env_id)
        )
        current_action = cursor.fetchone()
        
        if not current_action:
            return jsonify({"error": "Ação não encontrada"}), 404
        
        # Fazer merge dos dados atuais com os novos dados
        updated_data = {
            "name": data.get("name", current_action["name"]),
            "description": data.get("description", current_action["description"]),
            "action_type": data.get("action_type", current_action["action_type"]),
            "os_type": data.get("os_type", current_action["os_type"]),
            "force_stop": data.get("force_stop", current_action.get("force_stop", False)),
            "service_ids": data.get("service_ids", current_action["service_ids"]),
            "schedule_type": data.get("schedule_type") if "schedule_type" in data else current_action["schedule_type"],
            "schedule_config": data.get("schedule_config") if "schedule_config" in data else current_action["schedule_config"],
            "is_active": data.get("is_active", current_action["is_active"])
        }
        
        # Calcular next_run_at se tiver agendamento ATIVO (igual pipeline_schedules)
        next_run_at = None
        if updated_data["is_active"] and updated_data["schedule_type"] and updated_data["schedule_config"]:
            schedule_config = json.loads(updated_data["schedule_config"]) if isinstance(updated_data["schedule_config"], str) else updated_data["schedule_config"]
            
            if updated_data["schedule_type"] == "once":
                # Para execução única, pegar datetime do config como STRING (igual pipeline_schedules)
                next_run_at = schedule_config.get("datetime")
            else:
                # Para outros tipos, usar _calculate_next_run
                temp_schedule = {
                    'schedule_type': updated_data["schedule_type"],
                    'schedule_config': json.dumps(schedule_config) if isinstance(schedule_config, dict) else schedule_config
                }
                next_run_dt = pipeline_scheduler._calculate_next_run(temp_schedule)
                next_run_at = next_run_dt.isoformat() if next_run_dt else None
        
        cursor.execute(
            """UPDATE service_actions 
            SET name = %s, description = %s, action_type = %s, os_type = %s, force_stop = %s, service_ids = %s,
                schedule_type = %s, schedule_config = %s, is_active = %s, next_run_at = %s 
            WHERE id = %s AND environment_id = %s""",
            (
                updated_data["name"],
                updated_data["description"],
                updated_data["action_type"],
                updated_data["os_type"],
                updated_data["force_stop"],
                updated_data["service_ids"],
                updated_data["schedule_type"],
                updated_data["schedule_config"],
                updated_data["is_active"],
                next_run_at,
                action_id,
                env_id
            )
        )
        conn.commit()
        return jsonify({"success": True, "message": "Ação atualizada com sucesso"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route("/api/service-actions/<int:action_id>", methods=["DELETE"])
@require_operator
def delete_service_action(action_id):
    """Exclui ação de serviço"""
    env_id = request.headers.get("X-Environment-Id")
    if not env_id:
        return jsonify({"error": "Ambiente não especificado"}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM service_actions WHERE id = %s AND environment_id = %s", (action_id, env_id))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "Ação excluída com sucesso"})

@app.route("/api/service-actions/<int:action_id>/execute", methods=["POST"])
@require_operator
def execute_service_action(action_id):
    """Executa uma ação de serviço (start/stop)"""
    env_id = request.headers.get("X-Environment-Id")
    if not env_id:
        return jsonify({"error": "Ambiente não especificado"}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            "SELECT * FROM service_actions WHERE id = %s AND environment_id = %s",
            (action_id, env_id)
        )
        action = cursor.fetchone()
        
        if not action:
            return jsonify({"error": "Ação não encontrada"}), 404
        
        # Buscar nome do ambiente para mapear sufixo
        cursor.execute(
            "SELECT name FROM environments WHERE id = %s",
            (action['environment_id'],)
        )
        env = cursor.fetchone()
        
        # Mapeia ambiente para sufixo
        suffix_map = {
            'Produção': 'PRD',
            'Homologação': 'HOM',
            'Desenvolvimento': 'DEV',
            'Testes': 'TST'
        }
        suffix = suffix_map.get(env['name'], 'PRD') if env else 'PRD'
        
        # Parse service IDs (manter a ordem original do sequenciador!)
        service_ids = action['service_ids'].split(',')
        
        # Get service names and server_name
        cursor.execute(
            f"SELECT id, name, server_name FROM server_services WHERE id IN ({','.join(['%s'] * len(service_ids))})",
            service_ids
        )
        services_unordered = cursor.fetchall()
        
        # IMPORTANTE: Ordenar serviços na ordem original dos IDs (sequenciador)
        services_dict = {str(s['id']): s for s in services_unordered}
        services = [services_dict[sid] for sid in service_ids if sid in services_dict]
        
        # Carregar variáveis de ambiente do banco
        cursor.execute("SELECT name, value FROM server_variables")
        db_vars = cursor.fetchall()
        env_vars = os.environ.copy()
        for var in db_vars:
            env_vars[var['name']] = var['value']
        
        results = []
        for service in services:
            service_name = service['name']
            server_name = service.get('server_name', 'localhost')
            
            # Substituir variáveis ${VAR} no server_name
            import re
            variables_found = re.findall(r'\$\{([A-Z_0-9]+)\}', server_name)
            for var_name in variables_found:
                if var_name in env_vars:
                    server_name = server_name.replace(f"${{{var_name}}}", env_vars[var_name])
            
            # Build command based on OS and action type
            if action['os_type'] == 'linux':
                if action['action_type'] == 'start':
                    command = f"systemctl start {service_name}"
                elif action['action_type'] == 'stop':
                    command = f"systemctl stop {service_name}"
                elif action['action_type'] == 'restart':
                    command = f"systemctl restart {service_name}"
                
                # Execute Linux command
                import subprocess
                try:
                    result = subprocess.run(
                        command,
                        shell=True,
                        capture_output=True,
                        text=True,
                        timeout=60,
                        env=env_vars
                    )
                    results.append({
                        "service": service_name,
                        "success": result.returncode == 0,
                        "output": result.stdout + result.stderr
                    })
                except Exception as e:
                    results.append({
                        "service": service_name,
                        "success": False,
                        "output": str(e)
                    })
                    
            else:  # windows
                force_flag = "-Force" if action.get('force_stop', False) else ""
                
                # Build PowerShell script based on action type
                if action['action_type'] == 'start':
                    ps_script = f"Start-Service -Name '{service_name}'"
                elif action['action_type'] == 'stop':
                    ps_script = f"Stop-Service -Name '{service_name}' {force_flag}"
                elif action['action_type'] == 'restart':
                    ps_script = f"Restart-Service -Name '{service_name}' {force_flag}"
                
                # Detectar SO do servidor AtuDIC
                import subprocess
                is_linux_server = platform.system() == 'Linux'
                
                try:
                    if is_linux_server:
                        # AtuDIC rodando em Linux → usar SSH para Windows
                        ssh_host = env_vars.get(f'SSH_HOST_WINDOWS_{suffix}', server_name)
                        ssh_user = env_vars.get(f'SSH_USER_WINDOWS_{suffix}', 'administrador')
                        ssh_port = env_vars.get(f'SSH_PORT_WINDOWS_{suffix}', '22')
                        
                        ssh_command = f"ssh -i ~/.ssh/id_rsa_aturpo -p {ssh_port} -o StrictHostKeyChecking=no -o ConnectTimeout=10 {ssh_user}@{ssh_host} \"powershell -Command {ps_script}\""
                        
                        # DEBUG LOG
                        app.logger.info(f"🔧 SSH Service Action: {service_name}")
                        app.logger.info(f"🔧 SSH Command: {ssh_command}")
                        app.logger.info(f"🔧 SSH Vars: host={ssh_host}, user={ssh_user}, port={ssh_port}, suffix={suffix}")
                        
                        result = subprocess.run(
                            ssh_command,
                            shell=True,
                            capture_output=True,
                            text=True,
                            timeout=60,
                            env=env_vars,
                            encoding='utf-8',
                            errors='replace'
                        )
                        
                        # DEBUG LOG resultado
                        app.logger.info(f"🔧 SSH Result: returncode={result.returncode}")
                        app.logger.info(f"🔧 SSH stdout: {result.stdout[:200] if result.stdout else 'empty'}")
                        app.logger.info(f"🔧 SSH stderr: {result.stderr[:200] if result.stderr else 'empty'}")
                        
                        # PowerShell via SSH pode retornar 0 mesmo com stderr vazio
                        # Considerar sucesso se returncode=0 OU se não há mensagem de erro crítica
                        ssh_success = result.returncode == 0 or (result.returncode == 1 and not result.stderr)
                        
                        results.append({
                            "service": service_name,
                            "server": ssh_host,
                            "method": "SSH",
                            "success": ssh_success,
                            "output": result.stdout + result.stderr if (result.stdout or result.stderr) else "Comando executado com sucesso"
                        })
                    else:
                        # AtuDIC rodando em Windows → PowerShell direto
                        is_local = server_name.lower() in ['localhost', '127.0.0.1', '.', ''] or server_name.lower() == os.environ.get('COMPUTERNAME', '').lower()
                        
                        if not is_local:
                            # Servidor REMOTO - usa Invoke-Command (requer WinRM)
                            if action['action_type'] == 'start':
                                ps_script = f"Invoke-Command -ComputerName '{server_name}' -ScriptBlock {{ Start-Service -Name '{service_name}' }}"
                            elif action['action_type'] == 'stop':
                                ps_script = f"Invoke-Command -ComputerName '{server_name}' -ScriptBlock {{ Stop-Service -Name '{service_name}' {force_flag} }}"
                            elif action['action_type'] == 'restart':
                                ps_script = f"Invoke-Command -ComputerName '{server_name}' -ScriptBlock {{ Restart-Service -Name '{service_name}' {force_flag} }}"
                        
                        exec_command = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script]
                        
                        result = subprocess.run(
                            exec_command,
                            shell=False,
                            capture_output=True,
                            text=True,
                            encoding='utf-8',
                            errors='replace',
                            timeout=60,
                            env=env_vars
                        )
                        results.append({
                            "service": service_name,
                            "server": server_name,
                            "method": "PowerShell",
                            "is_local": is_local,
                            "success": result.returncode == 0,
                            "output": result.stdout + result.stderr
                        })
                except Exception as e:
                    results.append({
                        "service": service_name,
                        "server": server_name,
                        "success": False,
                        "output": str(e)
                    })
        
        return jsonify({
            "success": True,
            "results": results,
            "message": f"Ação '{action['name']}' executada"
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

# =====================================================================
# INICIALIZAÇÃO
# =====================================================================

def initialize_system():
    """Inicializa todos os componentes do sistema"""
    print("=" * 60)
    print("🚀 ATUDIC - DASHBOARD e API BACKEND")
    print("=" * 60)
    
    # 1. Inicializar banco de dados
    print("\n📊 Inicializando banco de dados...")
    init_db()
    print("✓ Banco de dados inicializado com sucesso!")
    
    # 2. Inicializar sistema de criptografia
    print("\n🔐 Inicializando sistema de criptografia...")
    global token_encryption
    try:
        token_encryption = TokenEncryption()
        
        key_file = os.path.join(get_base_directory(), '.encryption_key')
        if os.path.exists(key_file):
            print("✓ Sistema de criptografia inicializado!")
        else:
            print("❌ ERRO: Arquivo .encryption_key não foi criado!")
    except Exception as e:
        print(f"❌ ERRO ao inicializar criptografia: {e}")
        print("   O sistema continuará, mas tokens não serão criptografados!")
    
    # 3. Inicializar sistema de logging
    print("\n📝 Inicializando sistema de logging...")
    try:
        global audit_logger
        audit_logger = setup_logging(app)
        print("✓ Sistema de logging inicializado!")
        print("   Logs em: logs/app.log, logs/errors.log, logs/audit.log")
    except Exception as e:
        print(f"⚠️  Logging: {e}")
    
    # 4. Inicializar Pipeline Scheduler
    print("\n⏰ Inicializando Pipeline Scheduler...")
    try:
        global pipeline_scheduler
        pipeline_scheduler = PipelineScheduler(app)
        pipeline_scheduler.start()
        print("✅ Pipeline Scheduler inicializado e rodando!")
    except Exception as e:
        print(f"⚠️ Scheduler: {e}")
    
    # 5. Verificação de licença (informativo apenas)
    license_result = init_license_system()
    if not license_result['valid']:
        print("\n" + "⚠️" * 30)
        print("⚠️  AVISO: Sistema sem licença válida")
        print("⚠️  O acesso será bloqueado no login")
        print("⚠️  Para ativar: python activate_license.py")
        print("⚠️" * 30 + "\n")
    else:
        # Verificar se é modo trial ou licença
        if license_result.get('mode') == 'trial':
            trial = license_result.get('trial', {})
            print(f"🎁 Modo TRIAL: {trial.get('days_remaining', 0)} dias restantes")
        else:
            license_data = license_result.get('license', {})
            print(f"✅ Licença detectada: {license_data.get('customer_name', 'N/A')}")

    # 6. Verificar configurações
    print("\n⚙️  Verificando configurações...")
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) as count FROM users")
    user_count = cursor.fetchone()['count']
    print(f"   Usuários cadastrados: {user_count}")
    
    cursor.execute("SELECT COUNT(*) as count FROM environments")
    env_count = cursor.fetchone()['count']
    print(f"   Ambientes configurados: {env_count}")
    
    cursor.execute("SELECT username FROM github_settings WHERE id = 1")
    github_settings = cursor.fetchone()
    if github_settings and github_settings['username']:
        print(f"   GitHub configurado: {github_settings['username']}")
    else:
        print("   GitHub: Não configurado")
    
    conn.close()
    
    print("\n✓ Sistema pronto!")
    print(f"\n🖥️  Dashboard rodando em: http://localhost:5000")
    print(f"🌐 API rodando em: http://localhost:5000/api")
    print("\n" + "=" * 60 + "\n")

@app.route("/api/events", methods=["GET"])
@require_auth
def get_events():
    """Endpoint para polling de eventos/notificações."""
    try:
        env_id = request.headers.get('X-Environment-Id')
        
        if not env_id:
            return jsonify({"events": []})
        
        conn = get_db()
        cursor = conn.cursor()
        
        five_minutes_ago = (datetime.now() - timedelta(minutes=5)).isoformat()
        
        cursor.execute(
            """
            SELECT 
                l.id,
                l.pipeline_id,
                l.command_id,
                l.status,
                l.started_at,
                l.finished_at,
                p.name as pipeline_name
            FROM execution_logs l
            LEFT JOIN pipelines p ON l.pipeline_id = p.id
            WHERE l.environment_id = %s
              AND l.started_at >= %s
            ORDER BY l.started_at DESC
            LIMIT 10
            """,
            (int(env_id), five_minutes_ago)
        )
        recent_logs = cursor.fetchall()
        
        events = []
        for log in recent_logs:
            log_dict = dict(log)
            
            event_type = "info"
            if log_dict['status'] == 'success':
                event_type = "success"
            elif log_dict['status'] == 'error':
                event_type = "error"
            elif log_dict['status'] == 'running':
                event_type = "progress"
            
            events.append({
                "id": log_dict['id'],
                "type": event_type,
                "title": f"Pipeline: {log_dict['pipeline_name'] or 'Desconhecida'}",
                "message": f"Status: {log_dict['status']}",
                "timestamp": log_dict['started_at'],
                "pipeline_id": log_dict['pipeline_id'],
                "command_id": log_dict['command_id']
            })
        
        conn.close()
        
        return jsonify({
            "events": events,
            "count": len(events),
            "timestamp": datetime.now()
        })
    
    except Exception as e:
        app.logger.error(f"Erro ao buscar eventos: {e}")
        return jsonify({"events": [], "error": str(e)}), 500


# =====================================================================
# AZURE DEVOPS CLASSIC STYLE - PIPELINE RUNS (BUILD CI)
# =====================================================================

@app.route("/api/pipelines/<int:pipeline_id>/run", methods=["POST"])
@require_operator
def run_pipeline_build(pipeline_id):
    """
    Executa um pipeline (Build/CI) e retorna o run_id.
    Similar ao 'Run Pipeline' do Azure DevOps.
    """
    try:
        start_time = datetime.now()
        user_name = request.current_user["username"]
        environment_id = request.headers.get("X-Environment-Id")
        trigger_type = 'manual'

        # Validar environment_id
        if not environment_id:
            return jsonify({"error": "Cabeçalho X-Environment-Id é obrigatório"}), 400

        conn = get_db()
        cursor = conn.cursor()
        
        # Verificar se pipeline existe
        pipeline = cursor.execute(
            "SELECT * FROM pipelines WHERE id = %s", 
            (pipeline_id,)
        )
        pipeline = cursor.fetchone()
        
        if not pipeline:
            conn.close()
            return jsonify({"error": "Pipeline não encontrado"}), 404
        
        pipeline = dict(pipeline)  # Converter Row para dict
        
        # Buscar comandos do pipeline
        commands_raw = cursor.execute("""
            SELECT c.* FROM commands c
            JOIN pipeline_commands pc ON c.id = pc.command_id
            WHERE pc.pipeline_id = %s
            ORDER BY pc.sequence_order
        """, (pipeline_id,))
        commands_raw = cursor.fetchall()
        commands = [dict(row) for row in commands_raw]
        
        if not commands:
            conn.close()
            return jsonify({"error": "Pipeline sem comandos configurados"}), 400
        
        # Obter próximo run_number
        last_run = cursor.execute(
            "SELECT MAX(run_number) as last FROM pipeline_runs WHERE pipeline_id = %s",
            (pipeline_id,)
        )
        last_run = cursor.fetchone()
        
        run_number = (dict(last_run)["last"] or 0) + 1
        
        # Buscar user_id primeiro
        cursor.execute("SELECT id FROM users WHERE username = %s", (user_name,))
        user_id_result = cursor.fetchone()
        user_id = user_id_result['id'] if user_id_result else None
        
        # Criar novo run
        cursor.execute("""
                INSERT INTO pipeline_runs 
                (pipeline_id, run_number, status, started_at, started_by, environment_id, trigger_type)
                VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
        """, (pipeline_id, run_number, 'running', start_time.isoformat(), 
                  user_id, environment_id, trigger_type))
        
        run_id = cursor.fetchone()['id']
        conn.commit()
        conn.close()
        
        # Iniciar execução em thread separada (passando app para contexto)
        thread = threading.Thread(
            target=execute_pipeline_run,
            args=(app, run_id, pipeline_id, commands),
            daemon=True
        )
        thread.start()
        
        return jsonify({
            "success": True,
            "run_id": run_id,
            "run_number": run_number,
            "message": f"Pipeline #{run_number} iniciado"
        }), 200
        
    except Exception as e:
        app.logger.error(f"Erro ao executar pipeline: {e}")
        return jsonify({"error": str(e)}), 500


def execute_pipeline_run(flask_app, run_id, pipeline_id, commands):
    """
    Executa os comandos do pipeline em sequência.
    Thread separada para não bloquear o servidor.
    """
    with flask_app.app_context():
        conn = get_db()
        cursor = conn.cursor()
        
        try:
            # Buscar BASE_DIR do ambiente da pipeline (seguindo padrão das rotas)
            BASE_DIR = get_base_dir_for_pipeline(cursor, pipeline_id)
            
            # Define working_dir como BASE_DIR sem depender de repositórios
            working_dir = BASE_DIR
            
            # 🆕 BUSCAR TODAS AS VARIÁVEIS DE AMBIENTE DO BANCO
            env_vars = os.environ.copy()  # Começa com variáveis do sistema
            
            # Buscar todas as server_variables do banco
            all_vars = cursor.execute(
                "SELECT name, value FROM server_variables"
            )
            all_vars = cursor.fetchall()
            
            # Adicionar ao dicionário de ambiente
            for var in all_vars:
                env_vars[var["name"]] = var["value"]
            
            flask_app.logger.info(f"🔧 Variáveis carregadas: {list(env_vars.keys())}")

            # Executar cada comando
            for idx, command in enumerate(commands, True):
                # Criar log entry para comando
                cursor.execute("""
                    INSERT INTO pipeline_run_logs (
                        run_id, command_id, command_order, 
                        status, started_at
                    ) VALUES (%s, %s, %s, 'running', %s) RETURNING id
                """, (run_id, command["id"], idx, datetime.now()))
                
                log_id = cursor.fetchone()['id']
                conn.commit()

                # ========================================================
                # DEBUG: Informações do comando
                # ========================================================
                flask_app.logger.info(f"🔍 DEBUG - Executando comando {idx}")
                flask_app.logger.info(f"🔍 DEBUG - Nome: {command.get('name', 'Sem nome')}")
                flask_app.logger.info(f"🔍 DEBUG - Tipo: {command.get('type', 'INDEFINIDO')}")
                flask_app.logger.info(f"🔍 DEBUG - Working Dir: {working_dir}")
                flask_app.logger.info(f"🔍 DEBUG - Script (200 chars): {command['script'][:200]}")

                # Executar comando
                try:
                    # Substituir variáveis no comando
                    cmd_text = command["script"]
                    if "${BASE_DIR}" in cmd_text:
                        cmd_text = cmd_text.replace("${BASE_DIR}", BASE_DIR)

                    # ========================================================
                    # EXECUÇÃO COM MESMA LÓGICA: Linux (Bash) e Windows (PowerShell)
                    # ========================================================
                    # ========================================================
                    # SUBSTITUIR VARIÁVEIS ${VAR} POR VALORES REAIS
                    # PowerShell NÃO expande ${VAR}, apenas Bash faz isso!
                    # Solução: substituir em Python antes de executar
                    # ========================================================
                    import re

                    # Obter sufixo do ambiente da pipeline para substituição de variáveis
                    cursor.execute("SELECT environment_id FROM pipelines WHERE id = %s", (pipeline_id,))
                    pipe_env = cursor.fetchone()
                    env_suffix = ""
                    if pipe_env:
                        cursor.execute("SELECT name FROM environments WHERE id = %s", (pipe_env['environment_id'],))
                        env_row = cursor.fetchone()
                        if env_row:
                            suffix_map = {'Produção': 'PRD', 'Homologação': 'HOM', 'Desenvolvimento': 'DEV', 'Testes': 'TST'}
                            env_suffix = suffix_map.get(env_row['name'], '')
                    
                    flask_app.logger.info(f"🔍 DEBUG - Sufixo do ambiente: {env_suffix}")

                    # Para PowerShell: substitui TODAS as variáveis ${NOME} pelos valores
                    if command.get("type") == "powershell":
                        flask_app.logger.info(f"🔍 DEBUG - Substituindo variáveis no script PowerShell")

                        # Encontra todas as variáveis ${VAR} no script
                        variables_found = re.findall(r'\$\{([A-Z_0-9]+)\}', cmd_text)
                        flask_app.logger.info(f"🔍 DEBUG - Variáveis encontradas: {variables_found}")

                        # Substitui cada variável pelo valor do env_vars
                        for var_name in variables_found:
                            old_pattern = f"${{{var_name}}}"
                            
                            # Tenta primeiro com sufixo do ambiente (ex: BUILD_DIR_HOM)
                            var_with_suffix = f"{var_name}_{env_suffix}" if env_suffix else var_name
                            
                            if var_with_suffix in env_vars:
                                new_value = env_vars[var_with_suffix]
                                cmd_text = cmd_text.replace(old_pattern, new_value)
                                flask_app.logger.info(f"🔍 DEBUG - Substituiu ${{{var_name}}} por {new_value} (usando {var_with_suffix})")
                            elif var_name in env_vars:
                                # Fallback: tenta sem sufixo
                                new_value = env_vars[var_name]
                                cmd_text = cmd_text.replace(old_pattern, new_value)
                                flask_app.logger.info(f"🔍 DEBUG - Substituiu ${{{var_name}}} por {new_value} (sem sufixo)")
                            else:
                                flask_app.logger.warning(f"⚠️ Variável ${{{var_name}}} nem {var_with_suffix} encontrada em env_vars!")

                    # Determina o comando correto baseado no tipo
                    if command.get("type") == "powershell":
                        # PowerShell: usar arquivo temporário .ps1 é mais rápido que -Command
                        import tempfile
                        
                        # Prefixo para garantir UTF-8 e desabilitar progress bars
                        ps_header = "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8\n$ProgressPreference = 'SilentlyContinue'\n"
                        full_script = ps_header + cmd_text
                        
                        # Criar arquivo temporário .ps1 com BOM UTF-8 (PowerShell reconhece)
                        temp_script = tempfile.NamedTemporaryFile(
                            mode='w',
                            suffix='.ps1',
                            delete=False,
                            encoding='utf-8-sig'  # UTF-8 com BOM
                        )
                        temp_script.write(full_script)
                        temp_script.close()
                        temp_script_path = temp_script.name
                        
                        exec_command = [
                            "powershell.exe",
                            "-NoProfile",
                            "-NoLogo",
                            "-ExecutionPolicy", "Bypass",
                            "-File", temp_script_path
                        ]
                        use_shell = False

                        flask_app.logger.info(f"🔍 DEBUG - Executando PowerShell via -File (otimizado): {temp_script_path}")

                    elif command.get("type") == "bash":
                        # Bash: usa shell=True (Linux)
                        exec_command = cmd_text
                        use_shell = True

                        flask_app.logger.info(f"🔍 DEBUG - Executando Bash com shell=True")

                    else:
                        # Outros: usa shell padrão
                        exec_command = cmd_text
                        use_shell = True

                    import time
                    
                    # Buffer para salvar no banco NO FINAL (histórico)
                    log_buffer = []
                    
                    def log_build(message, level="info"):
                        # 1. Envia para stream em memória (tempo real - SSE)
                        push_live_log(run_id, message, level)
                        # 2. Acumula para salvar no banco depois (histórico)
                        log_buffer.append((run_id, message, level, datetime.now()))
                    
                    # Executa com logs em tempo real usando Popen
                    flask_app.logger.info(f"🔍 DEBUG - Iniciando execução do comando com streaming...")

                    start_exec_time = time.time()
                    
                    log_build(f"🚀 Iniciando comando: {command.get('name', 'Comando')}", "info")
                    log_build(f"📋 Tipo: {command.get('type', 'bash')}", "info")
                    log_build("─" * 50, "info")
                    
                    # Usar Popen para capturar output em tempo real
                    process = subprocess.Popen(
                        exec_command,
                        shell=use_shell,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        encoding='utf-8',
                        errors='replace',
                        cwd=working_dir if command.get("type") != "powershell" else None,
                        env=env_vars
                    )
                    
                    output_lines = []
                    
                    # Ler output linha por linha (simples e direto)
                    try:
                        for line in process.stdout:
                            line = line.rstrip('\n\r')
                            if line:
                                output_lines.append(line)
                                log_build(line, "output")
                        
                        process.wait(timeout=3600)
                        
                        # Cleanup do script temporário PowerShell
                        if command.get("type") == "powershell" and 'temp_script_path' in locals():
                            try:
                                os.unlink(temp_script_path)
                                flask_app.logger.info(f"🧹 Arquivo temporário removido: {temp_script_path}")
                            except Exception as e:
                                flask_app.logger.warning(f"⚠️ Erro ao remover temp: {e}")

                    except subprocess.TimeoutExpired:
                        process.kill()
                        log_build("❌ Comando excedeu o tempo limite de 1 hora", "error")
                        raise

                    exec_duration = time.time() - start_exec_time
                    flask_app.logger.info(f"🔍 DEBUG - Comando executado em {exec_duration:.2f}s, returncode: {process.returncode}")

                    output = '\n'.join(output_lines)
                    status = "success" if process.returncode == 0 else "failed"
                    
                    # Log de conclusão
                    if status == "success":
                        log_build(f"✅ Comando concluído com sucesso! (Duração: {exec_duration:.2f}s)", "success")
                    else:
                        log_build(f"❌ Comando falhou com código {process.returncode}", "error")
                    
                    # 🚀 SALVAR LOGS EM BACKGROUND (não bloqueia)
                    save_logs_background(flask_app, log_buffer.copy(), log_id, output, status)
                    
                    # Se comando falhou, parar pipeline
                    if status == "failed":
                        raise Exception(f"Comando '{command.get('name', 'desconhecido')}' falhou com código {result.returncode}")
                        
                except subprocess.TimeoutExpired:
                    error_msg = f"Comando excedeu o tempo limite de 1 hora"
                    cursor.execute("""
                        UPDATE pipeline_run_logs 
                        SET output = %s, status = 'failed', finished_at = %s
                        WHERE id = %s
                    """, (error_msg, datetime.now(), log_id))
                    conn.commit()
                    raise Exception(error_msg)
                    
                except Exception as e:
                    # 🆕 NÃO sobrescrever output - já foi salvo com a saída completa do script
                    # Apenas garantir que status está como 'failed'
                    cursor.execute("""
                        UPDATE pipeline_run_logs 
                        SET status = 'failed', finished_at = %s
                        WHERE id = %s
                    """, (datetime.now(), log_id))
                    conn.commit()
                    raise
            
            # Pipeline executado com sucesso
            cursor.execute("""
                UPDATE pipeline_runs 
                SET status = 'success', finished_at = %s
                WHERE id = %s
            """, (datetime.now(), run_id))
            conn.commit()
            
            # ✅ Atualizar status do stream APENAS quando TODOS os comandos terminarem
            set_live_stream_status(run_id, 'success')
            
            # 🆕 Se foi execução via schedule e incluiu comandos de deploy, criar release automaticamente
            cursor.execute("""
                SELECT trigger_type, environment_id, pipeline_id, started_by 
                FROM pipeline_runs 
                WHERE id = %s
            """, (run_id,))
            run_info = cursor.fetchone()

            if run_info and run_info['trigger_type'] == 'scheduled':
                # Verificar se algum comando executado foi do tipo deploy
                has_deploy = any(cmd.get('command_category') == 'deploy' for cmd in commands)

                if has_deploy:
                    # Buscar deploy_command_id da pipeline
                    cursor.execute(
                        "SELECT deploy_command_id FROM pipelines WHERE id = %s",
                        (run_info['pipeline_id'],)
                    )
                    pipeline_info = cursor.fetchone()
                    deploy_command_id = pipeline_info['deploy_command_id'] if pipeline_info else None

                    if deploy_command_id:
                        # Obter próximo release_number
                        cursor.execute(
                            "SELECT MAX(release_number) as last FROM releases WHERE pipeline_id = %s",
                            (run_info['pipeline_id'],)
                        )
                        last_release = cursor.fetchone()
                        release_number = (last_release['last'] if last_release['last'] else 0) + 1

                        # Criar registro de release com sucesso
                        cursor.execute("""
                            INSERT INTO releases (
                                pipeline_id, run_id, release_number, environment_id, 
                                deployed_by, deploy_command_id, status, started_at, finished_at
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """, (
                            run_info['pipeline_id'],
                            run_id,
                            release_number,
                            run_info['environment_id'],
                            run_info['started_by'],  # Será NULL para schedules
                            deploy_command_id,
                            'success',
                            datetime.now(),
                            datetime.now()
                        ))
                        conn.commit()

                        flask_app.logger.info(f"✅ Release #{release_number} criado automaticamente pelo schedule para run {run_id}")
            
        except Exception as e:
            # Pipeline falhou
            cursor.execute("""
                UPDATE pipeline_runs 
                SET status = 'failed', finished_at = %s, error_message = %s
                WHERE id = %s
            """, (datetime.now(), str(e), run_id))
            conn.commit()
            flask_app.logger.error(f"Pipeline run {run_id} falhou: {e}")
            
            # ❌ Atualizar status do stream quando falhar
            set_live_stream_status(run_id, 'failed')
            
        finally:
            conn.close()


@app.route("/api/pipelines/<int:pipeline_id>/runs", methods=["GET"])
@require_auth
def get_pipeline_runs(pipeline_id):
    """
    Retorna histórico de execuções (runs) de um pipeline.
    """
    try:
        page = int(request.args.get('page', True))
        limit = int(request.args.get('limit', 20))
        offset = (page - 1) * limit
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Buscar runs
        cursor.execute("""
            SELECT 
                pr.id, pr.run_number, pr.status, pr.started_at, pr.finished_at,
                pr.environment_id, pr.trigger_type, pr.error_message,
                CASE 
                    WHEN pr.trigger_type = 'scheduled' THEN 'Schedule'
                    ELSE COALESCE(u.username, 'Desconhecido')
                END as started_by_name,
                p.deploy_command_id
            FROM pipeline_runs pr
            LEFT JOIN users u ON pr.started_by = u.id
            LEFT JOIN pipelines p ON pr.pipeline_id = p.id
            WHERE pr.pipeline_id = %s
            ORDER BY pr.started_at DESC
            LIMIT %s OFFSET %s
        """, (pipeline_id, limit, offset))
        runs = cursor.fetchall()
        
        # Contar total
        cursor.execute(
            "SELECT COUNT(*) as count FROM pipeline_runs WHERE pipeline_id = %s",
            (pipeline_id,)
        )
        total_row = cursor.fetchone()
        total = total_row["count"] if total_row else 0
        
        conn.close()
        
        return jsonify({
            "runs": [dict(row) for row in runs],
            "total": total,
            "page": page,
            "limit": limit
        }), 200
        
    except Exception as e:
        app.logger.error(f"Erro ao buscar runs: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/runs/<int:run_id>/logs", methods=["GET"])
@require_auth
def get_run_logs(run_id):
    """
    Retorna logs em tempo real de uma execução de pipeline.
    """
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Verificar se run existe
        run = cursor.execute(
            "SELECT * FROM pipeline_runs WHERE id = %s",
            (run_id,)
        )
        run = cursor.fetchone()
        
        if not run:
            conn.close()
            return jsonify({"error": "Run não encontrado"}), 404
        
        # Buscar logs dos comandos
        logs = cursor.execute("""
            SELECT 
                prl.*,
                c.name as command_name,
                c.description as command_description
            FROM pipeline_run_logs prl
            LEFT JOIN commands c ON prl.command_id = c.id
            WHERE prl.run_id = %s
            ORDER BY prl.command_order
        """, (run_id,))
        logs = cursor.fetchall()
        
        conn.close()
        
        return jsonify({
            "run": dict(run),
            "logs": [dict(row) for row in logs]
        }), 200
        
    except Exception as e:
        app.logger.error(f"Erro ao buscar logs do run: {e}")
        return jsonify({"error": str(e)}), 500


# =====================================================================
# AZURE DEVOPS CLASSIC STYLE - RELEASES (DEPLOY CD)
# =====================================================================

@app.route("/api/runs/<int:run_id>/release", methods=["POST"])
@require_operator
def create_release_from_run(run_id):
    """
    Cria um release (deploy) associado a um RUN específico.
    Só permite criar release se o RUN estiver com status 'success'.
    """
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # 1. Verificar se o RUN existe e foi bem-sucedido
        run = cursor.execute("""
            SELECT pr.*, p.name as pipeline_name, p.deploy_command_id
            FROM pipeline_runs pr
            JOIN pipelines p ON pr.pipeline_id = p.id
            WHERE pr.id = %s
        """, (run_id,))
        run = cursor.fetchone()
        
        if not run:
            conn.close()
            return jsonify({"error": "Run não encontrado"}), 404
        
        run_dict = dict(run)
        
        # 2. Validar se o RUN foi bem-sucedido
        if run_dict['status'] != 'success':
            conn.close()
            return jsonify({
                "error": "Release não permitido",
                "message": f"O build precisa ter status 'success'. Status atual: '{run_dict['status']}'"
            }), 400
        
        # 3. 🆕 Verificar se pipeline tem comando de deploy configurado
        if not run_dict['deploy_command_id']:
            conn.close()
            return jsonify({
                "error": "Deploy não configurado",
                "message": "Este pipeline não tem um comando de deploy associado"
            }), 400
        
        # 4. 🆕 Buscar comando de deploy diretamente
        command = cursor.execute(
            "SELECT * FROM commands WHERE id = %s AND command_category = 'deploy'",
            (run_dict['deploy_command_id'],)
        )
        command = cursor.fetchone()
        
        if not command:
            conn.close()
            return jsonify({"error": "Comando de deploy não encontrado"}), 404
        
        # 5. Obter próximo release_number para este pipeline
        last_release = cursor.execute(
            "SELECT MAX(release_number) as last FROM releases WHERE pipeline_id = %s",
            (run_dict['pipeline_id'],)
        )
        last_release = cursor.fetchone()
        
        release_number = (dict(last_release)["last"] or 0) + 1
        
        # 6. Criar registro do release
        environment_id = request.headers.get('X-Environment-Id')
        
        cursor.execute("""
            INSERT INTO releases (
                pipeline_id, run_id, release_number, environment_id, deployed_by, 
                deploy_command_id, status, started_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
        """, (
            run_dict['pipeline_id'],
            run_id,
            release_number,
            environment_id,
            request.current_user['id'],
            run_dict['deploy_command_id'],
            'running',
            datetime.now()
        ))
        
        release_id = cursor.fetchone()['id']
        conn.commit()
        conn.close()
        
        # 7. Executar deploy em thread separada
        thread = threading.Thread(
            target=execute_release,
            args=(release_id, run_id, dict(command))
        )
        thread.daemon = True
        thread.start()
        
        app.logger.info(f"✅ Release {release_id} iniciado para run {run_id}")
        
        return jsonify({
            "success": True,
            "release_id": release_id,
            "message": f"Release iniciado para o build #{run_dict['run_number']}"
        }), 201
        
    except Exception as e:
        app.logger.error(f"❌ Erro ao criar release: {e}")
        return jsonify({"error": str(e)}), 500


def execute_release(release_id, run_id, command):
    """
    Executa o deploy de um release em background.
    Associado a um RUN específico.
    """
    conn = get_db()
    cursor = conn.cursor()
    
    def log_release(message, level="info"):
        """Registra log do release no banco"""
        cursor.execute("""
            INSERT INTO release_logs (release_id, output, log_type, created_at)
            VALUES (%s, %s, %s, %s)
        """, (release_id, message, level, datetime.now()))
        conn.commit()
        app.logger.info(f"[Release {release_id}] {message}")
    
    try:
        # Buscar informações do run
        run = cursor.execute(
            "SELECT * FROM pipeline_runs WHERE id = %s",
            (run_id,)
        )
        run = cursor.fetchone()
        
        if not run:
            raise Exception(f"Run {run_id} não encontrado")
        
        run_dict = dict(run)
        
        log_release(f"🚀 Iniciando deploy do build #{run_dict['run_number']}", "info")
        log_release(f"📋 Comando: {command['name']}", "info")
        log_release(f"⚙️  Executando deploy...", "info")
        
        # 🆕 BUSCAR TODAS AS VARIÁVEIS DE AMBIENTE DO BANCO
        env_vars = os.environ.copy()  # Começa com variáveis do sistema
        
        # Buscar todas as server_variables do banco
        all_vars = cursor.execute(
            "SELECT name, value FROM server_variables"
        )
        all_vars = cursor.fetchall()
        
        # Adicionar ao dicionário de ambiente
        for var in all_vars:
            env_vars[var["name"]] = var["value"]
        
        app.logger.info(f"🔧 Variáveis carregadas para release {release_id}: {list(env_vars.keys())}")
        
        # ========================================================
        # EXECUÇÃO COM MESMA LÓGICA DO PIPELINE
        # ========================================================
        import re
        
        cmd_text = command['script']
        cmd_type = command.get('type', 'bash')
        
        app.logger.info(f"[Release {release_id}] 🔍 DEBUG - Tipo do comando: {cmd_type}")
        
        # Para PowerShell: substitui TODAS as variáveis ${NOME} pelos valores
        if cmd_type == "powershell":
            app.logger.info(f"[Release {release_id}] 🔍 DEBUG - Substituindo variáveis no script PowerShell")
            
            # Encontra todas as variáveis ${VAR} no script
            variables_found = re.findall(r'\$\{([A-Z_0-9]+)\}', cmd_text)
            
            # Substitui cada variável pelo valor do env_vars
            for var_name in variables_found:
                if var_name in env_vars:
                    old_pattern = f"${{{var_name}}}"
                    new_value = env_vars[var_name]
                    cmd_text = cmd_text.replace(old_pattern, new_value)
                    app.logger.info(f"[Release {release_id}] 🔍 DEBUG - Substituiu ${{{var_name}}} por {new_value}")
            
            # PowerShell: chama diretamente (não usa shell=True)
            exec_command = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd_text]
            use_shell = False
            
            app.logger.info(f"[Release {release_id}] 🔍 DEBUG - Executando PowerShell direto")
            
        elif cmd_type == "bash":
            # Bash: usa shell=True (Linux)
            exec_command = cmd_text
            use_shell = True
            
            app.logger.info(f"[Release {release_id}] 🔍 DEBUG - Executando Bash com shell=True")
            
        else:
            # Outros: usa shell padrão
            exec_command = cmd_text
            use_shell = True
        
        # Executar comando de deploy
        result = subprocess.run(
            exec_command,
            shell=use_shell,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=600,  # 10 minutos
            env=env_vars
        )
        
        # Registrar saída
        if result.stdout:
            log_release(f"📤 Output:\n{result.stdout}", "info")
        
        if result.stderr:
            log_release(f"⚠️  Stderr:\n{result.stderr}", "warning")
        
        # Determinar status
        status = "success"
        error_msg = None
        
        if result.returncode == 0:
            log_release(f"✅ Deploy concluído com sucesso!", "success")
        else:
            log_release(f"❌ Deploy falhou com código {result.returncode}", "error")
            status = "failed"
            error_msg = result.stderr or "Erro desconhecido"
        
        # Atualizar status do release
        cursor.execute("""
            UPDATE releases 
            SET status = %s, finished_at = %s, error_message = %s
            WHERE id = %s
        """, (status, datetime.now(), error_msg, release_id))
        conn.commit()
        
        # Adicionar saída completa do deploy nos logs do run (igual aos comandos de build)
        try:
            # Buscar o último command_order usado no run
            last_order = cursor.execute("""
                SELECT MAX(command_order) as max_order 
                FROM pipeline_run_logs 
                WHERE run_id = %s
            """, (run_id,))
            last_order = cursor.fetchone()
            
            next_order = (dict(last_order)['max_order'] or 0) + 1

            # Construir saída completa do deploy (stdout + stderr)
            deploy_output = ""
            
            # Adicionar stdout se existir
            if result.stdout:
                deploy_output += result.stdout
            
            # Adicionar stderr se existir (em caso de avisos)
            if result.stderr and status == 'success':
                deploy_output += f"\n\n{'='*60}\n⚠️ AVISOS:\n{'='*60}\n{result.stderr}"
            
            # Se não tem nenhuma saída, usar mensagem padrão
            if not deploy_output.strip():
                deploy_output = f"🚀 Deploy executado!\nRelease #{release_id}\nComando: {command['name']}"
            
            # Inserir log com saída completa do script
            cursor.execute("""
                INSERT INTO pipeline_run_logs (
                    run_id, command_id, command_order, status, output, 
                    started_at, finished_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                run_id,
                command['id'],  # ? ID correto do comando
                next_order,     # ? Ordem sequencial correta
                'success' if status == 'success' else 'failed',
                deploy_output,  # ? SAÍDA COMPLETA DO SCRIPT
                datetime.now(),
                datetime.now()
            ))
            conn.commit()
            app.logger.info(f"✅ Log completo do release {release_id} (comando '{command['name']}') adicionado ao run {run_id}")
        except Exception as log_error:
            app.logger.warning(f"⚠️ Não foi possível adicionar log do release aos logs do run: {log_error}")

    except subprocess.TimeoutExpired:
        log_release("⏱️ Deploy excedeu o tempo limite", "error")
        cursor.execute("""
            UPDATE releases 
            SET status = 'failed', finished_at = %s, error_message = %s
            WHERE id = %s
        """, (datetime.now(), "Timeout", release_id))
        conn.commit()
        
    except Exception as e:
        log_release(f"💥 Erro durante deploy: {str(e)}", "error")
        cursor.execute("""
            UPDATE releases 
            SET status = 'failed', finished_at = %s, error_message = %s
            WHERE id = %s
        """, (datetime.now(), str(e), release_id))
        conn.commit()
        app.logger.error(f"Release {release_id} falhou: {e}")
        
    finally:
        conn.close()


@app.route("/api/runs/<int:run_id>/releases", methods=["GET"])
@require_auth
def get_run_releases(run_id):
    """
    Retorna releases associados a um RUN específico.
    """
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                r.*,
                u.username as deployed_by_name,
                e.name as environment_name,
                pr.run_number as build_number
            FROM releases r
            LEFT JOIN users u ON r.deployed_by = u.id
            LEFT JOIN environments e ON r.environment_id = e.id
            LEFT JOIN pipeline_runs pr ON r.run_id = pr.id
            WHERE r.run_id = %s
            ORDER BY r.started_at DESC
        """, (run_id,))
        releases = cursor.fetchall()
        
        conn.close()
        
        return jsonify({
            "releases": [dict(row) for row in releases]
        }), 200
        
    except Exception as e:
        app.logger.error(f"Erro ao buscar releases do run: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/releases/<int:release_id>/logs", methods=["GET"])
@require_auth
def get_release_logs(release_id):
    """
    Retorna logs em tempo real de um release.
    Com tratamento robusto de erros.
    """
    conn = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Verificar se release existe
        release = cursor.execute(
            "SELECT * FROM releases WHERE id = %s",
            (release_id,)
        )
        release = cursor.fetchone()
        
        if not release:
            return jsonify({"error": "Release não encontrado"}), 404
        
        # Buscar logs do release (pode estar vazio)
        logs = cursor.execute("""
            SELECT * FROM release_logs 
            WHERE release_id = %s
            ORDER BY created_at ASC
        """, (release_id,))
        logs = cursor.fetchall()
        
        return jsonify({
            "release": dict(release),
            "logs": [dict(row) for row in logs] if logs else []
        }), 200
        
    except PsycopgError as e:
        app.logger.error(f"Erro de banco ao buscar logs do release {release_id}: {e}")
        return jsonify({
            "error": "Erro ao acessar banco de dados",
            "details": str(e) if app.debug else "Erro interno"
        }), 500
        
    except Exception as e:
        app.logger.error(f"Erro ao buscar logs do release {release_id}: {e}")
        app.logger.error(traceback.format_exc())
        return jsonify({
            "error": "Erro ao buscar logs do release",
            "details": str(e) if app.debug else "Erro interno"
        }), 500
        
    finally:
        if conn:
            conn.close()


@app.route("/api/runs/<int:run_id>/logs/stream", methods=["GET"])
@require_auth
def stream_run_logs(run_id):
    """
    Stream de logs em tempo real de uma execução de pipeline.
    Similar ao Azure DevOps Classic.
    """
    def generate():
        conn = get_db()
        cursor = conn.cursor()
        
        last_log_id = 0
        max_iterations = 300  # 5 minutos com intervalo de 1s
        iterations = 0
        
        while iterations < max_iterations:
            # Buscar run status
            run = cursor.execute(
                "SELECT status FROM pipeline_runs WHERE id = %s",
                (run_id,)
            )
            run = cursor.fetchone()
            
            if not run:
                yield f"data: {json.dumps({'error': 'Run não encontrado'})}\n\n"
                break
            
            # Buscar novos logs
            logs = cursor.execute("""
                SELECT 
                    prl.*,
                    c.name as command_name
                FROM pipeline_run_logs prl
                LEFT JOIN commands c ON prl.command_id = c.id
                WHERE prl.run_id = %s AND prl.id > %s
                ORDER BY prl.command_order
            """, (run_id, last_log_id))
            logs = cursor.fetchall()
            
            # Enviar novos logs
            for log in logs:
                log_dict = dict(log)
                yield f"data: {json.dumps(convert_datetime_to_str(log_dict), ensure_ascii=False)}\n\n"


                last_log_id = log_dict['id']
            
            # Verificar se run terminou
            run_status = dict(run)["status"]
            if run_status in ["success", "failed"]:
                yield f"data: {json.dumps({'status': 'completed', 'final_status': run_status})}\n\n"
                break
            
            iterations += 1
            time.sleep(1)
        
        conn.close()
    
    return app.response_class(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )

@app.route("/api/runs/<int:run_id>/output/stream", methods=["GET"])
@require_auth
def stream_build_logs(run_id):
    """
    Stream de logs em tempo real de uma execução de build.
    Lê diretamente da memória para máxima performance.
    """
    def generate():
        last_index = 0
        max_iterations = 1200  # 10 minutos com intervalo de 0.5s
        iterations = 0
        
        while iterations < max_iterations:
            stream = get_live_stream(run_id)
            logs = list(stream['logs'])
            
            # Enviar novos logs
            if len(logs) > last_index:
                for log in logs[last_index:]:
                    yield f"data: {json.dumps(log, ensure_ascii=False)}\n\n"
                last_index = len(logs)
            
            # Verificar se terminou
            if stream['status'] in ['success', 'failed']:
                # Enviar logs finais
                logs = list(stream['logs'])
                if len(logs) > last_index:
                    for log in logs[last_index:]:
                        yield f"data: {json.dumps(log, ensure_ascii=False)}\n\n"
                
                yield f"data: {json.dumps({'status': 'completed', 'final_status': stream['status']})}\n\n"
                
                # Cleanup imediato
                cleanup_live_stream(run_id)
                break
            
            iterations += 1
            time.sleep(0.1)  # Polling mais rápido: 100ms
        
    return app.response_class(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )

@app.route("/api/releases/<int:release_id>/logs/stream", methods=["GET"])
@require_auth
def stream_release_logs(release_id):
    """
    Stream de logs em tempo real de um release.
    Similar ao Azure DevOps Classic.
    """
    def generate():
        conn = get_db()
        cursor = conn.cursor()
        
        last_log_id = 0
        max_iterations = 600  # 10 minutos com intervalo de 1s
        iterations = 0
        
        while iterations < max_iterations:
            # Buscar release status
            release = cursor.execute(
                "SELECT status FROM releases WHERE id = %s",
                (release_id,)
            )
            release = cursor.fetchone()
            
            if not release:
                yield f"data: {json.dumps({'error': 'Release não encontrado'})}\n\n"
                break

            # Buscar novos logs
            logs = cursor.execute("""
                SELECT * FROM release_logs 
                WHERE release_id = %s AND id > %s
                ORDER BY created_at
            """, (release_id, last_log_id))
            logs = cursor.fetchall()
            
            # Enviar novos logs
            for log in logs:
                log_dict = dict(log)
                yield f"data: {json.dumps(convert_datetime_to_str(log_dict), ensure_ascii=False)}\n\n"
                last_log_id = log_dict['id']
            
            # Verificar se release terminou
            release_status = dict(release)["status"]
            if release_status in ["success", "failed"]:
                # ✅ CORREÇÃO: Buscar e enviar TODOS os logs restantes antes de finalizar
                remaining_logs = cursor.execute("""
                    SELECT * FROM release_logs 
                    WHERE release_id = %s AND id > %s
                    ORDER BY created_at
                """, (release_id, last_log_id))
                remaining_logs = cursor.fetchall()
                
                # Enviar logs restantes
                for log in remaining_logs:
                    log_dict = dict(log)
                    yield f"data: {json.dumps(convert_datetime_to_str(log_dict), ensure_ascii=False)}\n\n"
                    last_log_id = log_dict['id']
                
                # Dar um delay para garantir que os logs foram enviados
                time.sleep(0.5)
                
                # Agora sim enviar o evento de conclusão
                yield f"data: {json.dumps({'status': 'completed', 'final_status': release_status})}\n\n"
                break
            
            iterations += 1
            time.sleep(1)
        
        conn.close()
    
    return app.response_class(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )

# =====================================================================
# LICENSING API ENDPOINTS
# =====================================================================
@app.route("/api/license/status", methods=["GET"])
@require_admin
def api_license_status():
    """Retorna status da licença"""
    status = get_license_status()
    return jsonify(status)

# =============================================================================
# ROTAS DE LICENCIAMENTO - Versão Simplificada (Sem Trial)
# =============================================================================

# -----------------------------------------------------------------------------
# Página de Ativação de Licença
# -----------------------------------------------------------------------------

@app.route('/activate')
def activate_page():
    """Página de ativação de licença"""
    html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'activate_license.html')
    try:
        with open(html_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return f"Erro: Arquivo não encontrado em {html_path}", 404
    except Exception as e:
        return f"Erro ao carregar página: {str(e)}", 500

# -----------------------------------------------------------------------------
# API: Validar Acesso Admin para Ativação de Licença
# -----------------------------------------------------------------------------

@app.route('/api/license/validate-admin', methods=['POST'])
def validate_admin_for_license():
    """
    Valida se o usuário é admin (root) ou tem perfil admin
    para acessar a página de ativação de licença.
    """
    try:
        data = request.get_json()
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()
        
        if not username or not password:
            return jsonify({
                'success': False,
                'error': 'Usuário e senha são obrigatórios'
            }), 400
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Buscar usuário (incluindo password_salt)
        cursor.execute(
            "SELECT id, username, password, password_salt, profile, active FROM users WHERE username = %s",
            (username,)
        )
        user = cursor.fetchone()
        conn.close()
        
        if not user:
            return jsonify({
                'success': False,
                'error': 'Credenciais inválidas'
            }), 401
        
        user_dict = dict(user)
        
        # Verificar se está ativo
        if not user_dict.get('active', True):
            return jsonify({
                'success': False,
                'error': 'Usuário desativado'
            }), 401
        
        # Verificar senha usando a função existente do sistema
        if not verify_password(user_dict['password'], user_dict['password_salt'], password):
            return jsonify({
                'success': False,
                'error': 'Credenciais inválidas'
            }), 401
        
        # Verificar se é admin (root) ou perfil admin
        is_root_admin = user_dict['username'] == 'admin'
        is_profile_admin = user_dict['profile'] == 'admin'
        
        if not is_root_admin and not is_profile_admin:
            return jsonify({
                'success': False,
                'error': 'Acesso restrito a administradores'
            }), 403
        
        return jsonify({
            'success': True,
            'message': 'Acesso autorizado',
            'redirect': '/activate'
        })
        
    except Exception as e:
        app.logger.error(f"Erro ao validar admin para licença: {e}")
        return jsonify({
            'success': False,
            'error': 'Erro interno do servidor'
        }), 500
    
# -----------------------------------------------------------------------------
# API: Informações de Licença e Trial
# -----------------------------------------------------------------------------

@app.route('/api/license/info', methods=['GET'])
def license_info():
    """
    Retorna informações sobre licença e hardware ID
    """
    try:
        init_license_cache_db()
        hardware_id = get_hardware_id()
        license_status = get_license_status_realtime()
        
        # Verificar se há função get_trial_status disponível
        trial_status = None
        try:
            from license_system import get_trial_status
            trial_status = get_trial_status()
        except (ImportError, AttributeError):
            # Função não existe na versão atual
            pass
        
        # Extrair dados da licença corretamente
        license_data = None
        if license_status.get('active'):
            license_data = license_status.get('license', {})
            license_data['active'] = True  # Adicionar flag de ativo
        
        return jsonify({
            'success': True,
            'hardware_id': hardware_id,
            'license': license_data,
            'license_key': license_status.get('license_key'),
            'trial': trial_status
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# -----------------------------------------------------------------------------
# API: Ativar Licença
# -----------------------------------------------------------------------------

@app.route('/api/license/activate', methods=['POST'])
def activate_license_api():
    """
    Ativa uma licença com a chave fornecida
    """
    try:
        init_license_cache_db()
        data = request.get_json()
        license_key = data.get('license_key', '').strip()
        
        if not license_key:
            return jsonify({
                'success': False,
                'error': 'Chave de licença não fornecida'
            }), 400
        
        # Validar formato básico
        clean_key = license_key.replace('-', '')
        if len(clean_key) != 20:
            return jsonify({
                'success': False,
                'error': 'Formato de chave inválido. Formato esperado: XXXX-XXXX-XXXX-XXXX-XXXX'
            }), 400
        
        # Limpar cache antigo
        clear_license_cache()
        
        # Salvar chave
        if not save_license_key(license_key):
            return jsonify({
                'success': False,
                'error': 'Erro ao salvar chave de licença'
            }), 500
        
        # Validar licença
        result = validate_license_hybrid(license_key)
        
        if result['valid']:
            return jsonify({
                'success': True,
                'message': 'Licença ativada com sucesso!',
                'license': result['license']
            })
        else:
            # Remover chave inválida
            try:
                if os.path.exists(LICENSE_FILE):
                    os.remove(LICENSE_FILE)
            except:
                pass
            
            return jsonify({
                'success': False,
                'error': result.get('error', 'Licença inválida')
            }), 400
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Erro ao ativar licença: {str(e)}'
        }), 500

# -----------------------------------------------------------------------------
# API: Status da Licença
# -----------------------------------------------------------------------------

@app.route('/api/license/status', methods=['GET'])
def license_status_api():
    """
    Retorna status atual da licença
    """
    try:
        status = get_license_status()
        return jsonify({
            'success': True,
            'status': status
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
    
if __name__ == "__main__":
    initialize_system()
    app.run(debug=False, host="0.0.0.0", port=5000)
