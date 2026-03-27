#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
License System - Cliente (AtuDIC)
Validação híbrida online/offline com hardware binding
Versão para Instalador - Ativação Pós-Instalação
"""

import os
import sys
import json
import hashlib
import uuid
import requests
import urllib3
import sqlite3
import platform
import subprocess

# Desabilita o warning de HTTPS não verificado no terminal quando o requests contornar certificados autoassinados
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from datetime import datetime, timedelta
from functools import wraps
from flask import jsonify

# =================================================================
# CONFIGURAÇÕES
# =================================================================

# URL do servidor de licenças (Google Cloud)
LICENSE_API_URL = os.getenv('LICENSE_SERVER_URL', 'https://136.111.207.196/api/license/validate')

# Diretório base - compatível com PyInstaller
def get_base_dir():
    """
    Retorna o diretório base correto:
    - Se rodando como .exe (PyInstaller): pasta do executável
    - Se rodando como .py: pasta do script
    """
    if getattr(sys, 'frozen', False):
        # Executável PyInstaller - usar pasta do .exe
        return os.path.dirname(sys.executable)
    else:
        # Script Python normal
        return os.path.dirname(os.path.abspath(__file__))

BASE_DIR = get_base_dir()

# Arquivos locais (caminhos absolutos na pasta de instalação)
LICENSE_FILE = os.path.join(BASE_DIR, "license.key")
LICENSE_CACHE_DB = os.path.join(BASE_DIR, "license_cache.db")
HARDWARE_ID_FILE = os.path.join(BASE_DIR, "hardware_id.dat")

# Configurações de validação
GRACE_PERIOD_DAYS = 7      # Dias offline antes de bloquear
OFFLINE_CHECK_HOURS = 24   # Horas entre verificações online

# Modo trial (se não tiver licença)
TRIAL_ENABLED = True
TRIAL_DAYS = 30

# =================================================================
# FUNÇÕES DE HARDWARE BINDING
# =================================================================

def get_hardware_id():
    """
    Gera ID único baseado no hardware da máquina.
    Usa MAC address + UUID do sistema.
    Inclui fallback persistente para evitar IDs diferentes a cada execução.
    """
    # Arquivo para persistir o hardware_id (fallback)
    global HARDWARE_ID_FILE
    
    try:
        # MAC address da primeira interface de rede
        mac = None
        
        if platform.system() == 'Windows':
            # Windows: obter MAC via PowerShell (mais confiável em VMs)
            try:
                result = subprocess.run(
                    ['powershell', '-Command', 
                     "(Get-NetAdapter | Where-Object {$_.Status -eq 'Up'} | Select-Object -First 1).MacAddress"],
                    capture_output=True, text=True, timeout=10,
                    creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
                )
                if result.returncode == 0 and result.stdout.strip():
                    mac = result.stdout.strip().lower().replace('-', ':')
            except:
                pass
        
        # Fallback: usar uuid.getnode()
        if not mac:
            mac = ':'.join(['{:02x}'.format((uuid.getnode() >> elements) & 0xff)
                           for elements in range(0, 2*6, 2)][::-1])
        
        # UUID do sistema (Windows) ou machine-id (Linux)
        machine_uuid = None
        
        if platform.system() == 'Windows':
            
            # Método 1: PowerShell (mais confiável no Windows 10/11)
            try:
                result = subprocess.run(
                    ['powershell', '-Command', 
                     '(Get-CimInstance -Class Win32_ComputerSystemProduct).UUID'],
                    capture_output=True, text=True, timeout=10,
                    creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
                )
                if result.returncode == 0 and result.stdout.strip():
                    machine_uuid = result.stdout.strip()
            except:
                pass
            
            # Método 2: WMIC (fallback para Windows mais antigos)
            if not machine_uuid:
                try:
                    result = subprocess.run(
                        ['wmic', 'csproduct', 'get', 'UUID'],
                        capture_output=True, text=True, timeout=10,
                        creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
                    )
                    if result.returncode == 0:
                        lines = [l.strip() for l in result.stdout.split('\n') if l.strip() and l.strip() != 'UUID']
                        if lines:
                            machine_uuid = lines[0]
                except:
                    pass
            
            # Método 3: Registry (último recurso Windows)
            if not machine_uuid:
                try:
                    import winreg
                    key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, 
                                        r"SOFTWARE\Microsoft\Cryptography")
                    machine_uuid = winreg.QueryValueEx(key, "MachineGuid")[0]
                    winreg.CloseKey(key)
                except:
                    pass
        else:
            # Linux
            try:
                with open('/etc/machine-id', 'r') as f:
                    machine_uuid = f.read().strip()
            except:
                try:
                    with open('/var/lib/dbus/machine-id', 'r') as f:
                        machine_uuid = f.read().strip()
                except:
                    pass
        
        # Se conseguiu obter machine_uuid, gerar hash
        if machine_uuid:
            combined = f"{mac}-{machine_uuid}"
            hardware_id = hashlib.sha256(combined.encode()).hexdigest()
            
            # Salvar para uso futuro (backup)
            try:
                with open(HARDWARE_ID_FILE, 'w') as f:
                    f.write(hardware_id)
            except:
                pass
            
            return hardware_id
        
        # Fallback: tentar recuperar ID salvo anteriormente
        if os.path.exists(HARDWARE_ID_FILE):
            try:
                with open(HARDWARE_ID_FILE, 'r') as f:
                    saved_id = f.read().strip()
                    if len(saved_id) == 64:  # SHA256 tem 64 caracteres
                        print("⚠️ Usando Hardware ID salvo anteriormente")
                        return saved_id
            except:
                pass
        
        # Último recurso: gerar baseado no MAC + hostname (mais estável que random)
        hostname = platform.node() or 'unknown'
        combined = f"{mac}-{hostname}-fallback"
        hardware_id = hashlib.sha256(combined.encode()).hexdigest()
        
        # Salvar para uso futuro
        try:
            with open(HARDWARE_ID_FILE, 'w') as f:
                f.write(hardware_id)
        except:
            pass
        
        print("⚠️ Hardware ID gerado via fallback (MAC + hostname)")
        return hardware_id
        
    except Exception as e:
        print(f"⚠️ Erro ao gerar hardware ID: {e}")
        
        # Tentar recuperar ID salvo
        if os.path.exists(HARDWARE_ID_FILE):
            try:
                with open(HARDWARE_ID_FILE, 'r') as f:
                    saved_id = f.read().strip()
                    if len(saved_id) == 64:
                        return saved_id
            except:
                pass
        
        # Último fallback: gerar e salvar
        fallback_id = hashlib.sha256(f"{uuid.getnode()}-{platform.node()}".encode()).hexdigest()
        try:
            with open(HARDWARE_ID_FILE, 'w') as f:
                f.write(fallback_id)
        except:
            pass
        
        return fallback_id

# =================================================================
# BANCO DE DADOS LOCAL (CACHE)
# =================================================================

def init_license_cache_db():
    """Inicializa banco SQLite local para cache de licença"""
    try:
        conn = sqlite3.connect(LICENSE_CACHE_DB)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS license_cache (
                id INTEGER PRIMARY KEY,
                license_key TEXT NOT NULL,
                hardware_id TEXT NOT NULL,
                customer_name TEXT,
                company_name TEXT,
                plan_type TEXT,
                expires_at TEXT,
                last_validation TEXT,
                is_valid INTEGER,
                cached_at TEXT
            )
        """)
        
        # Tabela para controle de trial
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trial_info (
                id INTEGER PRIMARY KEY,
                started_at TEXT NOT NULL,
                hardware_id TEXT NOT NULL
            )
        """)
        
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"⚠️ Erro ao inicializar cache: {e}")

def save_license_cache(license_key, hardware_id, license_data):
    """Salva validação de licença no cache local"""
    try:
        conn = sqlite3.connect(LICENSE_CACHE_DB)
        cursor = conn.cursor()
        
        # Limpar cache antigo
        cursor.execute("DELETE FROM license_cache")
        
        # Inserir novo cache
        cursor.execute("""
            INSERT INTO license_cache 
            (license_key, hardware_id, customer_name, company_name, plan_type, 
             expires_at, last_validation, is_valid, cached_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            license_key,
            hardware_id,
            license_data.get('customer_name'),
            license_data.get('company_name'),
            license_data.get('plan_type'),
            license_data.get('expires_at'),
            datetime.now().isoformat(),
            1,
            datetime.now().isoformat()
        ))
        
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"⚠️ Erro ao salvar cache: {e}")

def get_license_cache():
    """Recupera licença do cache local"""
    try:
        conn = sqlite3.connect(LICENSE_CACHE_DB)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM license_cache LIMIT 1")
        cache = cursor.fetchone()
        conn.close()
        
        if cache:
            return dict(cache)
        return None
    except:
        return None

def clear_license_cache():
    """Limpa cache de licença"""
    try:
        conn = sqlite3.connect(LICENSE_CACHE_DB)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM license_cache")
        conn.commit()
        conn.close()
    except:
        pass

# =================================================================
# SISTEMA DE TRIAL
# =================================================================

def init_trial():
    """Inicia período de trial"""
    try:
        conn = sqlite3.connect(LICENSE_CACHE_DB)
        cursor = conn.cursor()
        
        # Verificar se já tem trial
        cursor.execute("SELECT * FROM trial_info LIMIT 1")
        existing = cursor.fetchone()
        
        if not existing:
            # Criar novo trial
            hardware_id = get_hardware_id()
            cursor.execute("""
                INSERT INTO trial_info (started_at, hardware_id)
                VALUES (?, ?)
            """, (datetime.now().isoformat(), hardware_id))
            conn.commit()
            print("🎁 Período de trial iniciado (30 dias)")
        
        conn.close()
    except Exception as e:
        print(f"⚠️ Erro ao iniciar trial: {e}")

def get_trial_status():
    """Retorna status do período de trial"""
    try:
        conn = sqlite3.connect(LICENSE_CACHE_DB)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM trial_info LIMIT 1")
        trial = cursor.fetchone()
        conn.close()
        
        if not trial:
            return None
        
        started_at = datetime.fromisoformat(trial['started_at'])
        days_used = (datetime.now() - started_at).days
        days_remaining = TRIAL_DAYS - days_used
        
        return {
            'active': days_remaining > 0,
            'started_at': trial['started_at'],
            'days_remaining': max(0, days_remaining),
            'days_used': days_used,
            'expires_at': (started_at + timedelta(days=TRIAL_DAYS)).isoformat()
        }
    except:
        return None

# =================================================================
# VALIDAÇÃO ONLINE
# =================================================================

def validate_license_online(license_key, hardware_id):
    """
    Valida licença com o servidor remoto.
    Retorna: (success: bool, data: dict, error: str)
    """
    try:
        response = requests.post(
            LICENSE_API_URL,
            json={
                'license_key': license_key,
                'hardware_id': hardware_id,
                'version': '1.0.0'
            },
            timeout=10,
            verify=False
        )
        
        data = response.json()
        
        if data.get('success') and data.get('valid'):
            return True, data.get('license', {}), None
        else:
            error = data.get('error', 'Licença inválida')
            reason = data.get('reason', '')
            return False, None, f"{error} ({reason})" if reason else error
            
    except requests.exceptions.Timeout:
        return False, None, "Timeout ao conectar ao servidor"
    except requests.exceptions.ConnectionError:
        return False, None, "Erro de conexão com o servidor"
    except requests.exceptions.RequestException as e:
        return False, None, f"Erro de conexão: {str(e)}"
    except Exception as e:
        return False, None, f"Erro: {str(e)}"

# =================================================================
# VALIDAÇÃO HÍBRIDA (ONLINE + OFFLINE)
# =================================================================

def validate_license_hybrid(license_key):
    """
    Valida licença de forma híbrida:
    - Tenta online primeiro
    - Se offline, usa cache (até 7 dias)
    - Valida apenas a cada 24h (não em toda requisição)
    """
    hardware_id = get_hardware_id()
    
    # Verificar cache
    cache = get_license_cache()
    
    # Se tem cache válido, verificar se precisa revalidar
    if cache:
        # VALIDAR HARDWARE_ID - licença só é válida para a máquina correta
        if cache['hardware_id'] != hardware_id:
            # Hardware diferente - invalidar cache e forçar revalidação online
            clear_license_cache()
            cache = None
        else:
            cached_at = datetime.fromisoformat(cache['cached_at'])
            hours_since_check = (datetime.now() - cached_at).total_seconds() / 3600
            
            # Se validou há menos de 24h, usar cache
            if hours_since_check < OFFLINE_CHECK_HOURS:
                expires_at = datetime.fromisoformat(cache['expires_at'])
                if datetime.now() < expires_at:
                    return {
                        'valid': True,
                        'mode': 'cache',
                        'license': {
                            'customer_name': cache['customer_name'],
                            'company_name': cache['company_name'],
                            'plan_type': cache['plan_type'],
                            'expires_at': cache['expires_at']
                        }
                    }
    
    # Tentar validação online
    success, license_data, error = validate_license_online(license_key, hardware_id)
    
    if success:
        # Salvar no cache
        save_license_cache(license_key, hardware_id, license_data)
        return {
            'valid': True,
            'mode': 'online',
            'license': license_data
        }
    
    # Se falhou online, tentar usar cache (grace period)
    if cache:
        cached_at = datetime.fromisoformat(cache['cached_at'])
        days_since_check = (datetime.now() - cached_at).days
        
        if days_since_check <= GRACE_PERIOD_DAYS:
            expires_at = datetime.fromisoformat(cache['expires_at'])
            if datetime.now() < expires_at:
                return {
                    'valid': True,
                    'mode': 'offline_grace',
                    'license': {
                        'customer_name': cache['customer_name'],
                        'company_name': cache['company_name'],
                        'plan_type': cache['plan_type'],
                        'expires_at': cache['expires_at']
                    },
                    'warning': f'Modo offline - validar online em {GRACE_PERIOD_DAYS - days_since_check} dias'
                }
    
    # Nenhuma validação funcionou
    return {
        'valid': False,
        'error': error or 'Licença inválida ou expirada'
    }

# =================================================================
# FUNÇÕES PRINCIPAIS
# =================================================================

def get_license_key():
    """Obtém chave de licença do arquivo local"""
    try:
        if os.path.exists(LICENSE_FILE):
            with open(LICENSE_FILE, 'r') as f:
                return f.read().strip()
        return None
    except:
        return None

def save_license_key(license_key):
    """Salva chave de licença no arquivo local"""
    try:
        with open(LICENSE_FILE, 'w') as f:
            f.write(license_key)
        return True
    except Exception as e:
        print(f"❌ Erro ao salvar chave: {e}")
        return False

def init_license_system():
    """
    Inicializa sistema de licenciamento.
    Deve ser chamado no startup do app.py
    """
    print("\n🔐 Inicializando sistema de licenciamento...")
    
    # Inicializar banco de cache
    init_license_cache_db()
    
    # Verificar se tem chave de licença
    license_key = get_license_key()
    
    if not license_key:
        # Sem licença - verificar trial
        if TRIAL_ENABLED:
            trial = get_trial_status()
            
            if trial is None:
                # Primeiro uso - iniciar trial
                init_trial()
                trial = get_trial_status()
            
            if trial and trial['active']:
                print(f"🎁 Modo TRIAL ativo!")
                print(f"   • Dias restantes: {trial['days_remaining']}")
                print(f"   • Expira em: {trial['expires_at']}")
                print()
                print("⚠️  Para continuar usando após o trial, ative uma licença.")
                return {
                    'valid': True,
                    'mode': 'trial',
                    'trial': trial
                }
            else:
                print("❌ TRIAL EXPIRADO!")
                print("   Para continuar usando o sistema, ative uma licença.")
                print()
                print("   Execute: python activate_license.py")
                return {
                    'valid': False,
                    'mode': 'trial_expired',
                    'error': 'Período de trial expirado'
                }
        else:
            print("⚠️  NENHUMA LICENÇA ENCONTRADA!")
            print("   Para ativar o sistema, execute:")
            print("   python activate_license.py")
            return {
                'valid': False,
                'error': 'Sistema não licenciado'
            }
    
    # Validar licença
    result = validate_license_hybrid(license_key)
    
    if result['valid']:
        license = result['license']
        mode_emoji = {
            'online': '🌐',
            'cache': '💾',
            'offline_grace': '⏰'
        }
        emoji = mode_emoji.get(result['mode'], '✅')
        
        print(f"{emoji} Licença válida!")
        print(f"   • Cliente: {license['customer_name']}")
        print(f"   • Empresa: {license['company_name']}")
        print(f"   • Plano: {license['plan_type']}")
        print(f"   • Expira em: {license['expires_at']}")
        print(f"   • Modo: {result['mode']}")
        
        if result.get('warning'):
            print(f"   ⚠️ {result['warning']}")
    else:
        print(f"❌ LICENÇA INVÁLIDA: {result.get('error')}")
        print("   O sistema será bloqueado.")
    
    return result

# =================================================================
# DECORATOR PARA PROTEGER ROTAS
# =================================================================

def require_license(f):
    """
    Decorator para proteger rotas Flask.
    Permite acesso em modo trial.
    Uso: @require_license
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        license_key = get_license_key()
        
        # Verificar trial se não tem licença
        if not license_key:
            if TRIAL_ENABLED:
                trial = get_trial_status()
                if trial and trial['active']:
                    # Trial ativo - permitir acesso
                    return f(*args, **kwargs)
            
            return jsonify({
                'error': 'Sistema não licenciado',
                'message': 'Ative uma licença para continuar usando o sistema'
            }), 403
        
        # Validar licença
        result = validate_license_hybrid(license_key)
        
        if not result['valid']:
            return jsonify({
                'error': 'Licença inválida',
                'message': result.get('error', 'Licença expirada ou inválida')
            }), 403
        
        return f(*args, **kwargs)
    
    return decorated_function

# =================================================================
# FUNÇÕES DE ADMINISTRAÇÃO
# =================================================================

def get_license_status():
    """Retorna status da licença para exibição"""
    license_key = get_license_key()
    
    if not license_key:
        # Verificar trial
        if TRIAL_ENABLED:
            trial = get_trial_status()
            if trial:
                return {
                    'active': trial['active'],
                    'mode': 'trial',
                    'trial': trial,
                    'message': f"Modo trial - {trial['days_remaining']} dias restantes" if trial['active'] else "Trial expirado"
                }
        
        return {
            'active': False,
            'message': 'Nenhuma licença ativada'
        }
    
    result = validate_license_hybrid(license_key)
    
    if result['valid']:
        return {
            'active': True,
            'mode': result['mode'],
            'license': result['license'],
            'warning': result.get('warning')
        }
    else:
        return {
            'active': False,
            'message': result.get('error')
        }

def get_license_status_realtime():
    """
    Retorna status da licença com validação REAL-TIME no servidor.
    Usado na página de ativação para garantir status atualizado.
    """
    license_key = get_license_key()
    
    if not license_key:
        # Verificar trial
        if TRIAL_ENABLED:
            trial = get_trial_status()
            if trial:
                return {
                    'active': trial['active'],
                    'mode': 'trial',
                    'trial': trial,
                    'license_key': None,
                    'message': f"Modo trial - {trial['days_remaining']} dias restantes" if trial['active'] else "Trial expirado"
                }
        
        return {
            'active': False,
            'license_key': None,
            'message': 'Nenhuma licença ativada'
        }
    
    # Validar em tempo real (sem cache)
    hardware_id = get_hardware_id()
    success, license_data, error = validate_license_online(license_key, hardware_id)
    
    if success:
        # Atualizar cache com dados válidos
        save_license_cache(license_key, hardware_id, license_data)
        return {
            'active': True,
            'mode': 'online',
            'license_key': license_key,
            'license': license_data
        }
    else:
        # Licença inválida/bloqueada - limpar cache
        clear_license_cache()
        return {
            'active': False,
            'license_key': license_key,
            'message': error or 'Licença inválida ou bloqueada'
        }
    
# =================================================================
# VALIDAÇÃO REAL-TIME (SEM CACHE) - PARA LOGIN
# =================================================================

def validate_license_realtime(license_key):
    """
    Valida licença em TEMPO REAL (sem usar cache).
    Usado no momento do LOGIN para garantir bloqueio imediato.
    
    Returns: (success: bool, license_data: dict, error: str)
    """
    hardware_id = get_hardware_id()
    return validate_license_online(license_key, hardware_id)
