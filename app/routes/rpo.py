
import os
import hashlib
from datetime import datetime
from flask import Blueprint, request, jsonify, send_file, current_app
from werkzeug.utils import secure_filename
from app.database import get_db, release_db_connection
from app.utils.security import require_auth, require_operator

rpo_bp = Blueprint('rpo', __name__)

ALLOWED_EXTENSIONS = {'rpo', 'zip', 'rar'}
UPLOAD_FOLDER = 'storage/rpo'

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def calculate_md5(file_path):
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

@rpo_bp.route("/api/rpo/versions/<int:environment_id>", methods=["GET"])
@require_auth
def list_versions(environment_id):
    """Lista as versões de RPO de um ambiente."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT v.id, v.filename, v.version_hash, v.status, v.created_at, u.username as created_by
        FROM rpo_versions v
        LEFT JOIN users u ON v.created_by = u.id
        WHERE v.environment_id = %s
        ORDER BY v.created_at DESC
    """, (environment_id,))
    
    versions = [dict(row) for row in cursor.fetchall()]
    release_db_connection(conn)
    
    return jsonify(versions)

@rpo_bp.route("/api/rpo/upload/<int:environment_id>", methods=["POST"])
@require_operator
def upload_rpo(environment_id):
    """Upload de nova versão de RPO."""
    if 'file' not in request.files:
        return jsonify({"error": "Nenhum arquivo enviado"}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({"error": "Nenhum arquivo selecionado"}), 400
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Criar diretório se não existir
        env_folder = os.path.join(current_app.root_path, '..', UPLOAD_FOLDER, str(environment_id))
        os.makedirs(env_folder, exist_ok=True)
        
        # Salvar arquivo temporariamente para calcular hash
        temp_path = os.path.join(env_folder, f"temp_{timestamp}_{filename}")
        file.save(temp_path)
        
        file_hash = calculate_md5(temp_path)
        
        # Renomear com hash para evitar duplicatas reais
        final_filename = f"{timestamp}_{filename}"
        final_path = os.path.join(env_folder, final_filename)
        os.rename(temp_path, final_path)
        
        # Salvar no banco
        conn = get_db()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO rpo_versions (environment_id, filename, version_hash, file_path, created_by, created_at, status)
                VALUES (%s, %s, %s, %s, %s, %s, 'active')
                RETURNING id
            """, (environment_id, filename, file_hash, final_path, request.current_user['id'], datetime.now()))
            
            version_id = cursor.fetchone()['id']
            conn.commit()
            
            return jsonify({
                "success": True, 
                "message": "Upload concluído com sucesso",
                "version": {
                    "id": version_id,
                    "filename": filename,
                    "hash": file_hash,
                    "created_at": datetime.now()
                }
            })
            
        except Exception as e:
            conn.rollback()
            return jsonify({"error": f"Erro ao salvar registro: {e}"}), 500
        finally:
            release_db_connection(conn)
            
    return jsonify({"error": "Arquivo não permitido"}), 400

@rpo_bp.route("/api/rpo/download/<int:version_id>", methods=["GET"])
@require_auth
def download_rpo(version_id):
    """Download de versão específica."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT filename, file_path FROM rpo_versions WHERE id = %s", (version_id,))
    version = cursor.fetchone()
    release_db_connection(conn)
    
    if not version:
        return jsonify({"error": "Versão não encontrada"}), 404
    
    file_path = version['file_path']
    if not os.path.exists(file_path):
        return jsonify({"error": "Arquivo físico não encontrado no servidor"}), 404
        
    return send_file(file_path, as_attachment=True, download_name=version['filename'])
