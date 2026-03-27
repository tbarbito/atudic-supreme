"""
Helpers compartilhados para operações com repositórios.

Funções utilitárias de resolução de path, validação e criptografia
usadas por repositories.py e source_control.py.
"""
import os

from flask import jsonify

from app.database import get_db, release_db_connection
from app.utils.helpers import get_base_dir_for_repo
from app.utils.validators import sanitize_path_component, sanitize_branch_name
from app.utils import crypto


def resolve_repo_path(repo_id, branch_name):
    """
    Resolve e valida o caminho do repositório/branch no filesystem.
    Retorna (repo_path, repo_dict, error_response).
    Se error_response não for None, a rota deve retorná-lo diretamente.
    """
    conn = get_db()
    cursor = conn.cursor()
    BASE_DIR = get_base_dir_for_repo(cursor, repo_id)

    cursor.execute("SELECT id, name, default_branch FROM repositories WHERE id = %s", (repo_id,))
    repo = cursor.fetchone()
    release_db_connection(conn)

    if not repo:
        return None, None, (jsonify({"error": "Repositório não encontrado"}), 404)

    try:
        repo_name = sanitize_path_component(repo["name"])
        safe_branch = sanitize_branch_name(branch_name)
    except ValueError as e:
        return None, None, (jsonify({"error": f"Validação falhou: {str(e)}"}), 400)

    repo_path = os.path.join(BASE_DIR, repo_name, safe_branch)

    real_base = os.path.realpath(BASE_DIR)
    real_target = os.path.realpath(repo_path)
    if not real_target.startswith(real_base):
        return None, None, (jsonify({"error": "Path traversal detectado"}), 400)

    if not os.path.isdir(repo_path):
        return None, None, (jsonify({
            "error": f"O branch '{branch_name}' não foi clonado no servidor."
        }), 404)

    return repo_path, dict(repo), None


def validate_file_path(file_path, repo_path):
    """Valida um caminho de arquivo contra path traversal."""
    if not file_path:
        return None, "Caminho do arquivo não informado"

    # Rejeita componentes perigosos
    parts = file_path.replace('\\', '/').split('/')
    for part in parts:
        if part == '..' or part.startswith('~'):
            return None, "Caminho inválido"

    full_path = os.path.join(repo_path, file_path)
    real_repo = os.path.realpath(repo_path)
    real_file = os.path.realpath(full_path)
    if not real_file.startswith(real_repo):
        return None, "Path traversal detectado"

    return file_path, None


def decrypt_github_token(encrypted_token):
    """Descriptografa token GitHub. Retorna token plain text ou o próprio valor como fallback."""
    if not encrypted_token:
        return None
    if crypto.token_encryption is not None and crypto.token_encryption.is_initialized():
        try:
            return crypto.token_encryption.decrypt_token(encrypted_token)
        except Exception:
            return encrypted_token  # Fallback: pode ser token plain text antigo
    return encrypted_token
