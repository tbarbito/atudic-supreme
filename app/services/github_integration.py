"""
Integração com a API do GitHub.

Centraliza chamadas HTTP ao GitHub API, isolando a lógica
de autenticação e tratamento de erros.
"""
import requests as http_requests

from app.database import get_db, release_db_connection
from app.services.repo_helpers import decrypt_github_token


GITHUB_HEADERS_BASE = {
    'Accept': 'application/vnd.github.v3+json',
    'User-Agent': 'AtuDIC-DevOps'
}


def _github_headers(token):
    """Monta headers de autenticação para o GitHub API."""
    headers = GITHUB_HEADERS_BASE.copy()
    headers['Authorization'] = f'token {token}'
    return headers


def get_github_credentials():
    """Busca e descriptografa credenciais do GitHub do banco.
    Retorna (token, username) ou (None, None) se não configurado.
    """
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT token, username FROM github_settings WHERE id = 1")
    settings = cursor.fetchone()
    release_db_connection(conn)

    if not settings or not settings["token"]:
        return None, None

    token = decrypt_github_token(settings["token"])
    username = settings.get("username")
    return token, username


def discover_repos(token):
    """Descobre repositórios do usuário autenticado via GitHub API.
    Retorna (repos_list, error_dict, status_code).
    """
    try:
        response = http_requests.get(
            'https://api.github.com/user/repos?per_page=100',
            headers=_github_headers(token),
            timeout=30
        )

        if response.status_code != 200:
            return None, {"error": f"GitHub API retornou status {response.status_code}"}, response.status_code

        return response.json(), None, 200

    except http_requests.exceptions.Timeout:
        return None, {"error": "Timeout ao conectar com GitHub API"}, 504
    except Exception as e:
        return None, {"error": f"Erro ao conectar com GitHub: {str(e)}"}, 500


def test_connection(token, username):
    """Testa conexão com GitHub usando token e username.
    Retorna (result_dict, error_dict, status_code).
    """
    try:
        response = http_requests.get(
            f'https://api.github.com/users/{username}',
            headers=_github_headers(token),
            timeout=15
        )

        if response.status_code == 200:
            user_data = response.json()
            return {"success": True, "login": user_data.get("login")}, None, 200
        else:
            return None, {"error": f"Falha na autenticacao: {response.status_code}"}, response.status_code

    except http_requests.exceptions.Timeout:
        return None, {"error": "Timeout ao conectar com GitHub"}, 504
    except Exception as e:
        return None, {"error": f"Erro: {str(e)}"}, 500


def list_remote_branches(token, repo_full_name):
    """Lista branches remotas de um repositório via GitHub API.
    Retorna (branches_list, error_dict, status_code).
    """
    try:
        response = http_requests.get(
            f'https://api.github.com/repos/{repo_full_name}/branches?per_page=100',
            headers=_github_headers(token),
            timeout=30
        )

        if response.status_code != 200:
            return None, {"error": f"GitHub API retornou status {response.status_code}"}, response.status_code

        branches_data = response.json()
        branches = [b["name"] for b in branches_data]
        return branches, None, 200

    except http_requests.exceptions.Timeout:
        return None, {"error": "Timeout ao conectar com GitHub API"}, 504
    except Exception as e:
        return None, {"error": f"Erro: {str(e)}"}, 500
