from flask import Blueprint, request, jsonify, current_app
import os

from app.database import get_db, release_db_connection
from app.utils.security import verify_password, require_admin

from license_system import (
    init_license_cache_db,
    get_hardware_id,
    save_license_key,
    get_license_status,
    validate_license_hybrid,
    clear_license_cache,
    LICENSE_FILE,
    get_license_status_realtime
)

license_bp = Blueprint('license', __name__)

@license_bp.route("/api/license/status-admin", methods=["GET"])
@require_admin
def api_license_status():
    """Retorna status da licença (formato direto) - Apenas Admin"""
    status = get_license_status()
    return jsonify(status)

@license_bp.route('/activate')
def activate_page():
    """Página de ativação de licença"""
    # HTML está na raiz empacotada (suportado pelo PyInstaller sys._MEIPASS)
    html_path = os.path.join(current_app.root_path, 'activate_license.html')
    
    try:
        with open(html_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return f"Erro: Arquivo não encontrado em {html_path}", 404
    except Exception as e:
        return f"Erro ao carregar página: {str(e)}", 500

@license_bp.route('/api/license/validate-admin', methods=['POST'])
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
        release_db_connection(conn)
        
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
        current_app.logger.error(f"Erro ao validar admin para licença: {e}")
        return jsonify({
            'success': False,
            'error': 'Erro interno do servidor'
        }), 500

@license_bp.route('/api/license/info', methods=['GET'])
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

@license_bp.route('/api/license/activate', methods=['POST'])
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

@license_bp.route('/api/license/status', methods=['GET'])
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
