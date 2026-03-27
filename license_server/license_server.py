#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
License Server - AtuDIC/DevOps
Servidor de validação de licenças (PostgreSQL)
Deploy: Google Cloud VM
"""

import os
import sys
import json
import hashlib
import secrets
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import IntegrityError, Error as PsycopgError
from cryptography.fernet import Fernet
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

# =================================================================
# AUTENTICAÇÃO E SESSÃO
# =================================================================

def admin_required(f):
    """Decorator para proteger rotas administrativas"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_logged_in' not in session:
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

# =================================================================
# CONFIGURAÇÕES
# =================================================================

app = Flask(__name__)
CORS(app)
app.secret_key = 'sua-chave-secreta-super-segura-aqui-123456'  # ALTERAR EM PRODUÇÃO
app.config['SESSION_TYPE'] = 'filesystem'

# Configuração do banco PostgreSQL
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', '5432')),
    'database': os.getenv('DB_NAME', 'licenses'),
    'user': os.getenv('DB_USER', 'licenseuser'),
    'password': os.getenv('DB_PASSWORD', '')
}

# Secret para autenticação da API
API_SECRET = os.getenv('API_SECRET', 'change-this-secret-key-in-production')

# =================================================================
# FUNÇÕES DE BANCO DE DADOS
# =================================================================

def get_db():
    """Conecta ao banco de dados PostgreSQL"""
    try:
        conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
        return conn
    except PsycopgError as e:
        print(f"❌ Erro ao conectar ao PostgreSQL: {e}")
        raise

def init_database():
    """Inicializa as tabelas do banco de dados"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Tabela de licenças
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS licenses (
            id SERIAL PRIMARY KEY,
            license_key VARCHAR(50) UNIQUE NOT NULL,
            customer_name VARCHAR(255) NOT NULL,
            customer_email VARCHAR(255) NOT NULL,
            cnpj VARCHAR(20),
            endereco VARCHAR(70),
            telefone VARCHAR(20),
            company_name VARCHAR(255),
            plan_type VARCHAR(50) NOT NULL,
            hardware_id VARCHAR(255),
            created_at TIMESTAMP NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            is_active BOOLEAN DEFAULT TRUE,
            max_users INTEGER DEFAULT 10,
            max_repos INTEGER DEFAULT 50,
            features JSONB,
            last_validation TIMESTAMP,
            validation_count INTEGER DEFAULT 0
        )
    """)
    
    # Tabela de logs de validação
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS validation_logs (
            id SERIAL PRIMARY KEY,
            license_key VARCHAR(50) NOT NULL,
            hardware_id VARCHAR(255),
            ip_address VARCHAR(50),
            status VARCHAR(50) NOT NULL,
            message TEXT,
            created_at TIMESTAMP NOT NULL,
            FOREIGN KEY (license_key) REFERENCES licenses (license_key) ON DELETE CASCADE
        )
    """)
    
    # Índices para performance
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_license_key ON licenses(license_key)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_hardware_id ON licenses(hardware_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_validation_logs_key ON validation_logs(license_key)")
    
    conn.commit()
    conn.close()
    print("✅ Banco de dados inicializado com sucesso!")

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    """Login administrativo"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # Credenciais (em produção, usar hash e banco de dados)
        ADMIN_USER = os.getenv('ADMIN_USER', 'admin')
        ADMIN_PASS = os.getenv('ADMIN_PASS', 'Admin@01')
        
        if username == ADMIN_USER and password == ADMIN_PASS:
            session['admin_logged_in'] = True
            session['admin_username'] = username
            return redirect(url_for('admin_dashboard'))
        else:
            return render_template('admin_login.html', error='Credenciais inválidas')
    
    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    """Logout administrativo"""
    session.pop('admin_logged_in', None)
    session.pop('admin_username', None)
    return redirect(url_for('admin_login'))

# =================================================================
# DECORADORES DE AUTENTICAÇÃO
# =================================================================

def require_api_secret(f):
    """Valida o API secret nas requisições"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('X-API-Secret')
        if not auth_header or auth_header != API_SECRET:
            return jsonify({
                'success': False,
                'error': 'Unauthorized',
                'message': 'Invalid API secret'
            }), 401
        return f(*args, **kwargs)
    return decorated_function

# =================================================================
# FUNÇÕES AUXILIARES
# =================================================================

def generate_license_key():
    """
    Gera uma chave de licença no formato XXXX-XXXX-XXXX-XXXX-XXXX
    Igual ao generate_license.py
    """
    import secrets
    import string
    
    # Caracteres permitidos (sem ambíguos: 0, O, I, l)
    chars = string.ascii_uppercase + string.digits
    chars = chars.replace('O', '').replace('I', '').replace('0', '')
    
    # Gerar 5 blocos de 4 caracteres
    blocks = []
    for _ in range(5):
        block = ''.join(secrets.choice(chars) for _ in range(4))
        blocks.append(block)
    
    return '-'.join(blocks)

def log_validation(license_key, hardware_id, ip_address, status, message):
    """Registra log de validação"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO validation_logs 
            (license_key, hardware_id, ip_address, status, message, created_at)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (license_key, hardware_id, ip_address, status, message, datetime.now()))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"⚠️ Erro ao registrar log: {e}")

# =================================================================
# ROTAS DA API
# =================================================================

@app.route('/health', methods=['GET'])
def health_check():
    """Health check do servidor"""
    try:
        conn = get_db()
        conn.close()
        return jsonify({
            'status': 'healthy',
            'service': 'License Server',
            'version': '1.0.0',
            'database': 'connected'
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 500

@app.route('/api/license/validate', methods=['POST'])
def validate_license():
    """
    Valida uma licença
    Body: {
        "license_key": "XXXX-XXXX-XXXX-XXXX-XXXX",
        "hardware_id": "abc123...",
        "version": "1.0.0"
    }
    """
    try:
        data = request.json
        license_key = data.get('license_key')
        hardware_id = data.get('hardware_id')
        client_ip = request.remote_addr
        
        if not license_key or not hardware_id:
            return jsonify({
                'success': False,
                'valid': False,
                'error': 'Missing required fields'
            }), 400
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Buscar licença
        cursor.execute("""
            SELECT * FROM licenses WHERE license_key = %s
        """, (license_key,))
        
        license_data = cursor.fetchone()
        
        if not license_data:
            log_validation(license_key, hardware_id, client_ip, 'INVALID', 'License key not found')
            conn.close()
            return jsonify({
                'success': True,
                'valid': False,
                'error': 'Invalid license key'
            }), 200
        
        # Converter para dict
        license_data = dict(license_data)
        
        # Verificar se está ativa
        if not license_data['is_active']:
            log_validation(license_key, hardware_id, client_ip, 'BLOCKED', 'License is inactive')
            conn.close()
            return jsonify({
                'success': True,
                'valid': False,
                'error': 'License is inactive',
                'reason': 'blocked'
            }), 200
        
        # Verificar expiração
        if license_data['expires_at'] < datetime.now():
            log_validation(license_key, hardware_id, client_ip, 'EXPIRED', 'License has expired')
            conn.close()
            return jsonify({
                'success': True,
                'valid': False,
                'error': 'License has expired',
                'reason': 'expired',
                'expires_at': license_data['expires_at'].isoformat()
            }), 200
        
        # Verificar hardware binding
        if license_data['hardware_id'] is None:
            # Primeira ativação - vincular hardware
            cursor.execute("""
                UPDATE licenses 
                SET hardware_id = %s, last_validation = %s, validation_count = validation_count + 1
                WHERE license_key = %s
            """, (hardware_id, datetime.now(), license_key))
            conn.commit()
            log_validation(license_key, hardware_id, client_ip, 'ACTIVATED', 'First activation successful')
        elif license_data['hardware_id'] != hardware_id:
            log_validation(license_key, hardware_id, client_ip, 'HARDWARE_MISMATCH', 'Hardware ID does not match')
            conn.close()
            return jsonify({
                'success': True,
                'valid': False,
                'error': 'License is bound to another machine',
                'reason': 'hardware_mismatch'
            }), 200
        else:
            # Validação normal - atualizar contadores
            cursor.execute("""
                UPDATE licenses 
                SET last_validation = %s, validation_count = validation_count + 1
                WHERE license_key = %s
            """, (datetime.now(), license_key))
            conn.commit()
            log_validation(license_key, hardware_id, client_ip, 'SUCCESS', 'Validation successful')
        
        conn.close()
        
        # Retornar sucesso com dados da licença
        return jsonify({
            'success': True,
            'valid': True,
            'license': {
                'customer_name': license_data['customer_name'],
                'company_name': license_data['company_name'],
                'plan_type': license_data['plan_type'],
                'expires_at': license_data['expires_at'].isoformat(),
                'max_users': license_data['max_users'],
                'max_repos': license_data['max_repos'],
                'features': license_data['features']
            }
        }), 200
        
    except Exception as e:
        print(f"❌ Erro na validação: {e}")
        return jsonify({
            'success': False,
            'error': 'Internal server error',
            'message': str(e)
        }), 500

@app.route('/api/license/create', methods=['POST'])
@require_api_secret
def create_license():
    """
    Cria uma nova licença (admin only)
    Body: {
        "customer_name": "João Silva",
        "customer_email": "joao@empresa.com",
        "company_name": "Empresa XYZ",
        "plan_type": "premium",
        "days": 365
    }
    """
    try:
        data = request.json
        
        # Validações
        required_fields = ['customer_name', 'customer_email', 'plan_type', 'days']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing field: {field}'}), 400
        
        # Gerar chave única
        license_key = generate_license_key()
        
        # Calcular data de expiração
        created_at = datetime.now()
        expires_at = created_at + timedelta(days=int(data['days']))
        
        # Features padrão por plano
        features = {
            'basic': {'max_users': 5, 'max_repos': 20, 'api_access': False},
            'standard': {'max_users': 10, 'max_repos': 50, 'api_access': True},
            'premium': {'max_users': 999, 'max_repos': 999, 'api_access': True},
        }
        
        plan_features = features.get(data['plan_type'], features['basic'])
        
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO licenses 
            (license_key, customer_name, customer_email, cnpj, endereco, telefone, company_name, plan_type,
             hardware_id, created_at, expires_at, is_active, max_users, max_repos, features)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            license_key,
            data['customer_name'],
            data['customer_email'],
            data.get('cnpj', ''),
            data.get('endereco', ''),
            data.get('telefone', ''),
            data.get('company_name', ''),
            data['plan_type'],
            data.get('hardware_id'),
            created_at,
            expires_at,
            True,
            plan_features['max_users'],
            plan_features['max_repos'],
            json.dumps(plan_features)
        ))
        
        license_id = cursor.fetchone()['id']
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'license_key': license_key,
            'license_id': license_id,
            'expires_at': expires_at.isoformat()
        }), 201
        
    except Exception as e:
        print(f"❌ Erro ao criar licença: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/license/<license_key>/status', methods=['GET'])
@require_api_secret
def get_license_status(license_key):
    """Retorna status detalhado de uma licença (admin only)"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM licenses WHERE license_key = %s", (license_key,))
        license_data = cursor.fetchone()
        
        if not license_data:
            conn.close()
            return jsonify({'error': 'License not found'}), 404
        
        # Buscar logs recentes
        cursor.execute("""
            SELECT * FROM validation_logs 
            WHERE license_key = %s 
            ORDER BY created_at DESC 
            LIMIT 10
        """, (license_key,))
        
        logs = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        # Converter datetime para string
        license_dict = dict(license_data)
        for key, value in license_dict.items():
            if isinstance(value, datetime):
                license_dict[key] = value.isoformat()
        
        for log in logs:
            for key, value in log.items():
                if isinstance(value, datetime):
                    log[key] = value.isoformat()
        
        return jsonify({
            'success': True,
            'license': license_dict,
            'recent_logs': logs
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/license/<license_key>/block', methods=['POST'])
@require_api_secret
def block_license(license_key):
    """Bloqueia uma licença (admin only)"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE licenses SET is_active = FALSE WHERE license_key = %s
            RETURNING id
        """, (license_key,))
        
        result = cursor.fetchone()
        
        if not result:
            conn.close()
            return jsonify({'error': 'License not found'}), 404
        
        conn.commit()
        conn.close()
        
        log_validation(license_key, None, request.remote_addr, 'BLOCKED_BY_ADMIN', 'License blocked by administrator')
        
        return jsonify({
            'success': True,
            'message': 'License blocked successfully'
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/license/<license_key>/activate', methods=['POST'])
@require_api_secret
def activate_license(license_key):
    """Reativa uma licença (admin only)"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE licenses SET is_active = TRUE WHERE license_key = %s
            RETURNING id
        """, (license_key,))
        
        result = cursor.fetchone()
        
        if not result:
            conn.close()
            return jsonify({'error': 'License not found'}), 404
        
        conn.commit()
        conn.close()
        
        log_validation(license_key, None, request.remote_addr, 'ACTIVATED_BY_ADMIN', 'License activated by administrator')
        
        return jsonify({
            'success': True,
            'message': 'License activated successfully'
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/license/<license_key>/renew', methods=['POST'])
@require_api_secret
def renew_license(license_key):
    """
    Renova uma licença (admin only)
    Body: {"days": 365}
    """
    try:
        data = request.json
        days = int(data.get('days', 365))
        
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE licenses 
            SET expires_at = expires_at + INTERVAL '%s days'
            WHERE license_key = %s
            RETURNING expires_at
        """, (days, license_key))
        
        result = cursor.fetchone()
        
        if not result:
            conn.close()
            return jsonify({'error': 'License not found'}), 404
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': f'License renewed for {days} days',
            'new_expires_at': result['expires_at'].isoformat()
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/licenses/create', methods=['POST'])
@admin_required
def admin_create_license():
    """Criar nova licença - seguindo padrão do generate_license.py"""
    try:
        # Suportar tanto JSON quanto FormData
        if request.is_json:
            data = request.json
            customer_name = data.get('customer_name', '').strip()
            customer_email = data.get('customer_email', '').strip()
            cnpj = data.get('cnpj', '').strip()
            endereco = data.get('endereco', '').strip()
            telefone = data.get('telefone', '').strip()
            company_name = data.get('company_name', '').strip()
            plan_type = data.get('plan_type', '').strip()
            validity_days = data.get('days', 365)
            hardware_id = data.get('hardware_id', '').strip()
        else:
            customer_name = request.form.get('customer_name', '').strip()
            customer_email = request.form.get('customer_email', '').strip()
            cnpj = request.form.get('cnpj', '').strip()
            endereco = request.form.get('endereco', '').strip()
            telefone = request.form.get('telefone', '').strip()
            company_name = request.form.get('company_name', '').strip()
            plan_type = request.form.get('plan_type', '').strip()
            validity_days = request.form.get('validity_days', '365')
            hardware_id = request.form.get('hardware_id', '').strip()
        
        # Validar campos obrigatórios
        if not customer_name or not customer_email or not company_name or not plan_type or not hardware_id:
            return jsonify({
                'success': False,
                'error': 'Todos os campos são obrigatórios'
            }), 400
        
        try:
            validity_days = int(validity_days)
            if validity_days <= 0:
                raise ValueError()
        except:
            return jsonify({
                'success': False,
                'error': 'Validade deve ser um número positivo'
            }), 400
        
        # Features padrão por plano
        features = {
            'basic': {'max_users': 5, 'max_repos': 20, 'api_access': False},
            'standard': {'max_users': 10, 'max_repos': 50, 'api_access': True},
            'premium': {'max_users': 999, 'max_repos': 999, 'api_access': True},
            'enterprise': {'max_users': 999, 'max_repos': 999, 'api_access': True}
        }
        plan_features = features.get(plan_type, features['basic'])
        
        # Gerar chave única
        license_key = generate_license_key()
        expires_at = datetime.now() + timedelta(days=validity_days)
        
        # Inserir no banco
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO licenses 
            (license_key, customer_name, customer_email, cnpj, endereco, telefone, company_name, plan_type, 
             hardware_id, expires_at, is_active, max_users, max_repos, features, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, %s, %s, %s, NOW())
        """, (
            license_key, 
            customer_name, 
            customer_email,
            cnpj,
            endereco,
            telefone,
            company_name, 
            plan_type, 
            hardware_id,
            expires_at,
            plan_features['max_users'],
            plan_features['max_repos'],
            json.dumps(plan_features)
        ))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': 'Licença criada com sucesso',
            'license_key': license_key,
            'license': {
                'license_key': license_key,
                'customer_name': customer_name,
                'customer_email': customer_email,
                'cnpj': cnpj,
                'endereco': endereco,
                'telefone': telefone,
                'company_name': company_name,
                'plan_type': plan_type,
                'hardware_id': hardware_id,
                'expires_at': expires_at.strftime('%Y-%m-%d %H:%M:%S')
            }
        })
        
    except Exception as e:
        app.logger.error(f"Erro ao criar licença: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Erro ao criar licença: {str(e)}'
        }), 500

@app.route('/admin/licenses/<license_key>/block', methods=['POST'])
@admin_required
def admin_block_license(license_key):
    """Bloquear ou desbloquear licença"""
    try:
        action = request.json.get('action', 'block')  # 'block' ou 'unblock'
        is_active = (action != 'block')
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Verificar se licença existe
        cursor.execute("SELECT license_key FROM licenses WHERE license_key = %s", (license_key,))
        if not cursor.fetchone():
            conn.close()
            return jsonify({
                'success': False,
                'error': 'Licença não encontrada'
            }), 404
        
        # Atualizar status
        cursor.execute("""
            UPDATE licenses 
            SET is_active = %s
            WHERE license_key = %s
        """, (is_active, license_key))
        
        conn.commit()
        conn.close()
        
        status_text = 'bloqueada' if not is_active else 'desbloqueada'
        
        return jsonify({
            'success': True,
            'message': f'Licença {status_text} com sucesso'
        })
        
    except Exception as e:
        app.logger.error(f"Erro ao bloquear/desbloquear licença: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Erro: {str(e)}'
        }), 500

@app.route('/admin/licenses/<license_key>/toggle', methods=['POST'])
@admin_required
def admin_toggle_license(license_key):
    """Alternar status da licença (bloquear/desbloquear)"""
    try:
        block = request.json.get('block', True)
        is_active = not block
        
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("SELECT license_key FROM licenses WHERE license_key = %s", (license_key,))
        if not cursor.fetchone():
            conn.close()
            return jsonify({'success': False, 'error': 'Licença não encontrada'}), 404
        
        cursor.execute("UPDATE licenses SET is_active = %s WHERE license_key = %s", (is_active, license_key))
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': f"Licença {'bloqueada' if block else 'desbloqueada'} com sucesso"
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    
@app.route('/admin/licenses/<license_key>/renew', methods=['POST'])
@admin_required
def admin_renew_license(license_key):
    """Renovar licença adicionando dias"""
    try:
        additional_days = request.json.get('days')
        
        if not additional_days:
            return jsonify({
                'success': False,
                'error': 'Número de dias não informado'
            }), 400
        
        try:
            additional_days = int(additional_days)
            if additional_days <= 0:
                raise ValueError()
        except:
            return jsonify({
                'success': False,
                'error': 'Número de dias deve ser positivo'
            }), 400
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Buscar licença atual
        cursor.execute("""
            SELECT expires_at FROM licenses 
            WHERE license_key = %s
        """, (license_key,))
        
        result = cursor.fetchone()
        if not result:
            conn.close()
            return jsonify({
                'success': False,
                'error': 'Licença não encontrada'
            }), 404
        
        current_expires = result['expires_at']
        
        # Se já expirou, renovar a partir de hoje
        if current_expires < datetime.now():
            new_expires = datetime.now() + timedelta(days=additional_days)
        else:
            # Se ainda válida, adicionar dias à data atual
            new_expires = current_expires + timedelta(days=additional_days)
        
        # Atualizar no banco
        cursor.execute("""
            UPDATE licenses 
            SET expires_at = %s
            WHERE license_key = %s
        """, (new_expires, license_key))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': f'Licença renovada por {additional_days} dias',
            'new_expires_at': new_expires.strftime('%Y-%m-%d %H:%M:%S')
        })
        
    except Exception as e:
        app.logger.error(f"Erro ao renovar licença: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Erro: {str(e)}'
        }), 500

@app.route('/admin/licenses/<license_key>/delete', methods=['POST'])
@admin_required
def admin_delete_license(license_key):
    """Deletar licença permanentemente"""
    try:
        confirm = request.json.get('confirm', False)
        
        if not confirm:
            return jsonify({
                'success': False,
                'error': 'Confirmação necessária para deletar'
            }), 400
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Verificar se existe
        cursor.execute("SELECT license_key FROM licenses WHERE license_key = %s", (license_key,))
        if not cursor.fetchone():
            conn.close()
            return jsonify({
                'success': False,
                'error': 'Licença não encontrada'
            }), 404
        
        # Deletar
        cursor.execute("DELETE FROM licenses WHERE license_key = %s", (license_key,))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': 'Licença deletada com sucesso'
        })
        
    except Exception as e:
        app.logger.error(f"Erro ao deletar licença: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Erro: {str(e)}'
        }), 500

@app.route('/admin/licenses/<license_key>/details', methods=['GET'])
@admin_required
def admin_license_details(license_key):
    """Retorna detalhes completos de uma licença com logs"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM licenses WHERE license_key = %s", (license_key,))
        license_data = cursor.fetchone()
        
        if not license_data:
            conn.close()
            return jsonify({'success': False, 'error': 'Licença não encontrada'}), 404
        
        cursor.execute("""
            SELECT status, message, ip_address, 
                   TO_CHAR(created_at, 'DD/MM/YYYY HH24:MI') as created_at
            FROM validation_logs 
            WHERE license_key = %s 
            ORDER BY validation_logs.created_at DESC 
            LIMIT 10
        """, (license_key,))
        logs = cursor.fetchall()
        conn.close()
        
        license_info = dict(license_data)
        if license_info.get('created_at'):
            license_info['created_at'] = license_info['created_at'].strftime('%d/%m/%Y %H:%M')
        if license_info.get('expires_at'):
            license_info['expires_at'] = license_info['expires_at'].strftime('%d/%m/%Y %H:%M')
        
        return jsonify({
            'success': True,
            'license': license_info,
            'logs': [dict(log) for log in logs]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    
@app.route('/admin/licenses/<license_key>/update_client', methods=['POST'])
@admin_required
def admin_update_client(license_key):
    """Atualizar dados do cliente de uma licença específica"""
    try:
        if request.is_json:
            data = request.json
        else:
            data = request.form
            
        cnpj = data.get('cnpj', '').strip()
        company_name = data.get('company_name', '').strip()
        customer_name = data.get('customer_name', '').strip()
        customer_email = data.get('customer_email', '').strip()
        endereco = data.get('endereco', '').strip()
        telefone = data.get('telefone', '').strip()

        if not customer_name or not customer_email or not company_name:
            return jsonify({
                'success': False,
                'error': 'Nome do cliente, email e empresa são obrigatórios'
            }), 400

        conn = get_db()
        cursor = conn.cursor()

        # Verificar se licença existe
        cursor.execute("SELECT license_key FROM licenses WHERE license_key = %s", (license_key,))
        if not cursor.fetchone():
            conn.close()
            return jsonify({'success': False, 'error': 'Licença não encontrada'}), 404

        cursor.execute("""
            UPDATE licenses 
            SET customer_name = %s,
                customer_email = %s,
                cnpj = %s,
                endereco = %s,
                telefone = %s,
                company_name = %s
            WHERE license_key = %s
        """, (customer_name, customer_email, cnpj, endereco, telefone, company_name, license_key))

        conn.commit()
        conn.close()

        return jsonify({'success': True, 'message': 'Cliente atualizado com sucesso'})

    except Exception as e:
        app.logger.error(f"Erro ao atualizar cliente: {str(e)}")
        return jsonify({'success': False, 'error': f'Erro: {str(e)}'}), 500

@app.route('/admin')
@admin_required
def admin_dashboard():
    """Dashboard principal de administração"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Buscar todas as licenças com status calculado
        cursor.execute("""
            SELECT 
                license_key,
                customer_name,
                customer_email,
                cnpj,
                endereco,
                telefone,
                company_name,
                plan_type,
                expires_at,
                is_active,
                hardware_id,
                created_at,
                                CASE 
                    WHEN expires_at < NOW() THEN true
                    ELSE false
                END as is_expired
            FROM licenses
            ORDER BY created_at DESC
        """)
        
        licenses = cursor.fetchall()
        
        # Estatísticas otimizadas
        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE is_active = TRUE AND expires_at > NOW()) as active,
                COUNT(*) FILTER (WHERE is_active = FALSE) as blocked,
                COUNT(*) FILTER (WHERE expires_at BETWEEN NOW() AND NOW() + INTERVAL '30 days' AND is_active = TRUE) as expiring
            FROM licenses
        """)
        
        stats_row = cursor.fetchone()
        stats = {
            'total': stats_row['total'],
            'active': stats_row['active'],
            'blocked': stats_row['blocked'],
            'expiring': stats_row['expiring']
        }
        
        conn.close()
        
        return render_template('admin_dashboard.html', licenses=licenses, stats=stats)
        
    except Exception as e:
        app.logger.error(f"Erro ao carregar dashboard: {str(e)}")
        return f"Erro ao carregar dashboard: {str(e)}", 500
                    
# =================================================================
# INICIALIZAÇÃO
# =================================================================

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='License Server')
    parser.add_argument('--init-db', action='store_true', help='Initialize database')
    parser.add_argument('--port', type=int, default=5000, help='Port to run on')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to')
    
    args = parser.parse_args()
    
    if args.init_db:
        print("🔧 Inicializando banco de dados...")
        init_database()
        sys.exit(0)
    
    print("🚀 License Server iniciando...")
    print(f"📡 Servidor: http://{args.host}:{args.port}")
    print(f"🔒 API Secret: {API_SECRET[:10]}...")
    print(f"💾 Database: {DB_CONFIG['database']}")
    
    app.run(host=args.host, port=args.port, debug=False)
