from flask import Blueprint, request, jsonify
from psycopg2 import Error as PsycopgError
from datetime import datetime
import os
import shutil
import subprocess
import base64

from app.database import get_db, release_db_connection
from app.utils.security import (
    require_auth,
    require_operator,
    require_admin
)
from app.utils.validators import (
    sanitize_path_component,
    sanitize_branch_name,
    sanitize_commit_message,
    validate_git_url,
    execute_git_command_safely
)
from app.utils.rate_limiter import rate_limit
from app.utils.helpers import get_base_dir_for_repo, CLONE_DIR
from app.utils import crypto

# Importa helpers do módulo de serviço (lógica centralizada)
from app.services.repo_helpers import resolve_repo_path, validate_file_path, decrypt_github_token
from app.services import github_integration
from app.services.branch_policy_service import validate_operation as _validate_branch_policy

repositories_bp = Blueprint('repositories', __name__)


# Re-exports para compatibilidade (source_control.py importa com prefixo _)
_resolve_repo_path = resolve_repo_path
_validate_file_path = validate_file_path
_decrypt_github_token = decrypt_github_token

# =====================================================================
# ROTAS DE REPOSITÓRIOS
# =====================================================================


@repositories_bp.route("/api/repositories", methods=["GET"])
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
    release_db_connection(conn)
    return jsonify(repositories)


@repositories_bp.route("/api/repositories", methods=["POST"])
@require_admin
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
            # Inserir NOVO registro, agora incluindo o environment_id
            cursor.execute(                
                """
                INSERT INTO repositories (environment_id, github_id, name, full_name, description, private,
                                        html_url, clone_url, language, default_branch, size, updated_at, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    env_id,
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
            saved_count += 1

    conn.commit()
    release_db_connection(conn)

    return jsonify(
        {
            "success": True,
            "saved": saved_count,
            "message": f"{saved_count} novos repositórios salvos neste ambiente.",
        }
    )


@repositories_bp.route("/api/repositories/<int:repo_id>/clone", methods=["POST"])
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
    
    release_db_connection(conn)

    if not repo:
        return jsonify({"error": "Repositório não encontrado"}), 404
    if not settings or not settings["token"]:
        return jsonify({"error": "Token do GitHub não configurado"}), 400

    # Descriptografa token usando helper
    github_token = _decrypt_github_token(settings["token"])
    
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


@repositories_bp.route("/api/repositories/<int:repo_id>/pull", methods=["POST"])
@require_operator
@rate_limit(max_requests=10, window_seconds=60)  # 10 pulls/min
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
        "SELECT name, environment_id FROM repositories WHERE id = %s", (repo_id,)
    )
    repo = cursor.fetchone()

    if not repo:
        release_db_connection(conn)
        return jsonify({"error": "Repositório não encontrado"}), 404

    # Valida politica de branch-ambiente
    policy_check = _validate_branch_policy(cursor, repo.get('environment_id'), repo['name'], branch_name, 'pull')
    release_db_connection(conn)
    if not policy_check['allowed']:
        return jsonify({"error": policy_check['reason']}), 403

    try:
        # Sanitização
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
        # Comandos Git seguros
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


@repositories_bp.route("/api/repositories/<int:repo_id>/push", methods=["POST"])
@require_operator
@rate_limit(max_requests=10, window_seconds=60)  # 10 pushes/min
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

    if not repo:
        release_db_connection(conn)
        return jsonify({"error": "Repositório não encontrado"}), 404

    # Valida politica de branch-ambiente
    policy_check = _validate_branch_policy(cursor, repo.get('environment_id'), repo['name'], branch_name, 'push')
    release_db_connection(conn)
    if not policy_check['allowed']:
        return jsonify({"error": policy_check['reason']}), 403

    try:
        # Sanitização de todas as entradas
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
            git_user = request.current_user.get("name", "BiizHubOps")
            git_email = request.current_user.get("email", "devops@atudic.local")
        
        execute_git_command_safely(['git', 'config', 'user.name', git_user], cwd=repo_path)
        execute_git_command_safely(['git', 'config', 'user.email', git_email], cwd=repo_path)
        
        # Sequência segura de comandos Git
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


@repositories_bp.route("/api/repositories/<int:repo_id>", methods=["DELETE"])
@require_admin
def delete_repository(repo_id):
    """Remove repositório da lista"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM repositories WHERE id = %s", (repo_id,))
    conn.commit()
    release_db_connection(conn)

    return jsonify({"success": True, "message": "Repositório removido"})


@repositories_bp.route("/api/repositories/<int:repo_id>/tag", methods=["POST"])
@require_operator
@rate_limit(max_requests=10, window_seconds=60)  # 10 tags/min
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
    release_db_connection(conn)

    if not repo:
        return jsonify({"error": "Repositório não encontrado"}), 404

    repo_name = repo["name"]
    # Nota: tag_repository original usa CLONE_DIR direto, mas deveria usar get_base_dir_for_repo?
    # O código original usava CLONE_DIR: repo_path = os.path.join(CLONE_DIR, repo_name)
    # Mas se houver ambientes múltiplos, isso pode dar errado se o repo não estiver no CLONE_DIR default.
    # Vou manter CLONE_DIR por compatibilidade com o original, mas idealmente seria get_base_dir_for_repo?
    # O problema é que get_base_dir_for_repo retorna um path. Onde a tag é criada? Em qual clone?
    # O original assume apenas um clone por repo (no CLONE_DIR).
    # Com get_base_dir_for_repo, o repo pode estar em outro lugar.
    # Mas repo_path precisa apontar para um diretório .git válido.
    
    # Se usarmos get_base_dir_for_repo, precisamos saber em qual branch fazer a tag?
    # O código original assume CLONE_DIR/repo_name.
    # Vou usar CLONE_DIR como no original para não quebrar comportamento, mas adicionar TODO.
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
        # Configurar a identidade para o commit da tag
        user_name = request.current_user["name"]
        user_email = request.current_user["email"]
        subprocess.run(
            ["git", "config", "user.name", f'"{user_name}"'],
            cwd=repo_path, check=True, encoding='utf-8', errors='replace'
        )
        subprocess.run(
            ["git", "config", "user.email", f'"{user_email}"'],
            cwd=repo_path, check=True, encoding='utf-8', errors='replace'
        )

        # Passo 1: Criar a tag anotada
        subprocess.run(
            ["git", "tag", "-a", tag_name, "-m", message],
            cwd=repo_path,
            check=True,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
        )

        # Passo 2: Empurrar a nova tag para o 'origin' (GitHub)
        result = subprocess.run(
            ["git", "push", "origin", tag_name],
            cwd=repo_path,
            check=True,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
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


@repositories_bp.route("/api/repositories/<int:repo_id>/branches", methods=["GET"])
@require_auth
def list_branches(repo_id):
    """Lista branches disponíveis de um repositório (git ou filesystem)."""
    conn = get_db()
    cursor = conn.cursor()
    BASE_DIR = get_base_dir_for_repo(cursor, repo_id)

    cursor.execute("SELECT name, default_branch FROM repositories WHERE id = %s", (repo_id,))
    repo = cursor.fetchone()
    release_db_connection(conn)

    if not repo:
        return jsonify({"error": "Repositorio nao encontrado"}), 404

    repo_name = repo["name"]

    for base in [BASE_DIR, CLONE_DIR]:
        repo_dir = os.path.join(base, repo_name)
        if not os.path.isdir(repo_dir):
            continue

        # Verifica se é estrutura branch-por-pasta (BiizHubOps pattern):
        # BASE_DIR/repo/master/.git, BASE_DIR/repo/homolog/.git, etc.
        # Cada subpasta é um clone --single-branch separado
        try:
            subdirs = [d for d in sorted(os.listdir(repo_dir))
                       if os.path.isdir(os.path.join(repo_dir, d)) and not d.startswith('.')]
        except OSError:
            continue

        if subdirs:
            # Se pelo menos uma subpasta tem .git, é estrutura branch-por-pasta
            # Retorna nomes das subpastas como branches disponíveis
            has_git_subdirs = any(
                os.path.isdir(os.path.join(repo_dir, d, '.git'))
                for d in subdirs
            )
            if has_git_subdirs:
                return jsonify(subdirs)

            # Subpastas sem .git (artefatos Protheus) — também retorna como branches
            return jsonify(subdirs)

        # Sem subpastas — verifica se o próprio diretório é um repo git
        if os.path.isdir(os.path.join(repo_dir, '.git')):
            try:
                result = subprocess.run(
                    ["git", "branch", "-r"],
                    cwd=repo_dir,
                    capture_output=True, text=True,
                    encoding='utf-8', errors='replace', timeout=30
                )
                if result.returncode == 0 and result.stdout.strip():
                    branches = []
                    for line in result.stdout.strip().split("\n"):
                        if "->" not in line and line.strip():
                            branches.append(line.strip().replace("origin/", ""))
                    if branches:
                        return jsonify(branches)
            except (subprocess.TimeoutExpired, Exception):
                pass

    # Nenhum diretório encontrado — repositório não está clonado no servidor
    return jsonify([])


@repositories_bp.route("/api/repositories/<int:repo_id>/remote-branches", methods=["GET"])
@require_operator
@rate_limit(max_requests=20, window_seconds=60)
def list_remote_branches(repo_id):
    """Lista branches remotas do GitHub via API (admin e operator).
    Usado no fluxo de Clonar/Resetar e no seletor de branches do card."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT name, full_name, default_branch FROM repositories WHERE id = %s", (repo_id,))
    repo = cursor.fetchone()
    release_db_connection(conn)

    if not repo:
        return jsonify({"error": "Repositorio nao encontrado"}), 404

    token, _ = github_integration.get_github_credentials()
    if not token:
        return jsonify({"error": "GitHub nao configurado"}), 400

    branches, error, status_code = github_integration.list_remote_branches(token, repo["full_name"])
    if error:
        return jsonify(error), status_code
    return jsonify(branches)


@repositories_bp.route("/api/repositories/<int:repo_id>/branch", methods=["POST"])
@require_operator
@rate_limit(max_requests=10, window_seconds=60)  # 10 branches/min
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
        "SELECT name, environment_id FROM repositories WHERE id = %s", (repo_id,)
    )
    repo = cursor.fetchone()

    if not repo:
        release_db_connection(conn)
        return jsonify({"error": "Repositório não encontrado"}), 404

    # Valida politica de branch-ambiente
    policy_check = _validate_branch_policy(cursor, repo.get('environment_id'), repo['name'], base_branch_name, 'create_branch')
    release_db_connection(conn)
    if not policy_check['allowed']:
        return jsonify({"error": policy_check['reason']}), 403

    try:
        # Sanitização
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
        # Comandos Git seguros
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
# EXPLORAÇÃO LOCAL DE ARQUIVOS
# =====================================================================


@repositories_bp.route("/api/repositories/<int:repo_id>/files", methods=["GET"])
@require_auth
@rate_limit(max_requests=120, window_seconds=60)
def list_local_files(repo_id):
    """Lista arquivos do repositório clonado localmente via git ls-tree.
    Retorna formato compatível com a API do GitHub para reuso do frontend."""
    path = request.args.get('path', '')
    branch = request.args.get('branch', '')

    conn = get_db()
    cursor = conn.cursor()
    BASE_DIR = get_base_dir_for_repo(cursor, repo_id)

    cursor.execute(
        "SELECT name, default_branch FROM repositories WHERE id = %s", (repo_id,)
    )
    repo = cursor.fetchone()
    release_db_connection(conn)

    if not repo:
        return jsonify({"error": "Repositório não encontrado"}), 404

    repo_name = repo["name"]
    branch_name = branch or repo["default_branch"]

    try:
        repo_name = sanitize_path_component(repo_name)
        branch_name = sanitize_branch_name(branch_name)
    except ValueError as e:
        return jsonify({"error": f"Validação falhou: {str(e)}"}), 400

    # Tenta localizar o repositório em diferentes caminhos possíveis
    candidates = [
        os.path.join(BASE_DIR, repo_name, branch_name),   # padrão: BASE_DIR/repo/branch
        os.path.join(BASE_DIR, repo_name),                 # sem subpasta de branch
        os.path.join(CLONE_DIR, repo_name, branch_name),   # fallback CLONE_DIR
        os.path.join(CLONE_DIR, repo_name),                # fallback CLONE_DIR sem branch
    ]

    repo_path = None
    is_git_repo = False
    for candidate in candidates:
        real_candidate = os.path.realpath(candidate)
        real_base = os.path.realpath(BASE_DIR)
        real_clone = os.path.realpath(CLONE_DIR)
        if not (real_candidate.startswith(real_base) or real_candidate.startswith(real_clone)):
            continue
        if os.path.exists(candidate) and os.path.isdir(candidate):
            repo_path = candidate
            is_git_repo = os.path.isdir(os.path.join(candidate, '.git'))
            break

    if not repo_path:
        return jsonify({
            "error": f"Diretório do repositório '{repo_name}' não encontrado no servidor ou branch não clonada."
        }), 404

    # Sanitiza o path interno (subpasta) — impede path traversal com ../
    if path:
        for component in path.split('/'):
            if component in ('..', '.') or component.startswith('.'):
                return jsonify({"error": "Path inválido"}), 400

    try:
        # ===== MODO GIT: usa git ls-tree + filesystem (para incluir untracked) =====
        if is_git_repo:
            tree_ref = f"HEAD:{path}" if path else "HEAD"
            result = subprocess.run(
                ['git', 'ls-tree', '-l', tree_ref],
                cwd=repo_path,
                capture_output=True, text=True,
                encoding='utf-8', errors='replace', timeout=30
            )

            items = []
            tracked_names = set()

            if result.returncode == 0 and result.stdout.strip():
                for line in result.stdout.strip().split('\n'):
                    if not line:
                        continue
                    parts = line.split('\t', 1)
                    if len(parts) != 2:
                        continue
                    meta, name = parts
                    meta_parts = meta.split()
                    if len(meta_parts) < 4:
                        continue

                    obj_type = meta_parts[1]
                    size = meta_parts[3]
                    item_path = f"{path}/{name}" if path else name
                    is_dir = obj_type == 'tree'

                    items.append({
                        'name': name,
                        'path': item_path,
                        'type': 'dir' if is_dir else 'file',
                        'size': 0 if is_dir else int(size) if size != '-' else 0,
                        'download_url': None
                    })
                    tracked_names.add(name)

            # Mesclar arquivos nao rastreados (untracked) do filesystem
            # para que novos arquivos aparecam no explorador antes do commit
            target_dir = os.path.join(repo_path, path.replace('/', os.sep)) if path else repo_path
            real_repo = os.path.realpath(repo_path)
            real_target = os.path.realpath(target_dir)
            if real_target.startswith(real_repo) and os.path.isdir(target_dir):
                for entry in sorted(os.listdir(target_dir)):
                    if entry.startswith('.') or entry in tracked_names:
                        continue
                    full_entry = os.path.join(target_dir, entry)
                    item_path = f"{path}/{entry}" if path else entry
                    is_dir = os.path.isdir(full_entry)
                    try:
                        size = 0 if is_dir else os.path.getsize(full_entry)
                    except OSError:
                        size = 0
                    items.append({
                        'name': entry,
                        'path': item_path,
                        'type': 'dir' if is_dir else 'file',
                        'size': size,
                        'download_url': None,
                        'untracked': True,
                    })

            if items:
                # Ordenar: pastas primeiro, depois por nome
                items.sort(key=lambda x: (0 if x['type'] == 'dir' else 1, x['name'].lower()))
                return jsonify(items)

            # Se ls-tree falhou e nao tem itens, pode ser um arquivo — tenta git show
            if path:
                file_ref = f"HEAD:{path}"
                size_result = subprocess.run(
                    ['git', 'cat-file', '-s', file_ref],
                    cwd=repo_path,
                    capture_output=True, text=True,
                    encoding='utf-8', errors='replace', timeout=10
                )
                if size_result.returncode == 0:
                    return _read_git_file(repo_path, path, file_ref, size_result)

                # Fallback filesystem para arquivos untracked (novos, nao commitados)
                fs_path = os.path.join(repo_path, path.replace('/', os.sep))
                real_fs = os.path.realpath(fs_path)
                if real_fs.startswith(os.path.realpath(repo_path)) and os.path.isfile(fs_path):
                    return _read_fs_file(fs_path, path)

            return jsonify({"error": "Caminho não encontrado no repositório"}), 404

        # ===== MODO FILESYSTEM: listagem direta (artefatos sem .git) =====
        target_dir = os.path.join(repo_path, path.replace('/', os.sep)) if path else repo_path

        # Valida path traversal no target final
        real_repo = os.path.realpath(repo_path)
        real_target = os.path.realpath(target_dir)
        if not real_target.startswith(real_repo):
            return jsonify({"error": "Path inválido"}), 400

        if os.path.isfile(target_dir):
            return _read_fs_file(target_dir, path)

        if not os.path.isdir(target_dir):
            return jsonify({"error": "Caminho não encontrado"}), 404

        items = []
        for entry in sorted(os.listdir(target_dir)):
            # Ignora arquivos/pastas ocultos
            if entry.startswith('.'):
                continue
            full_path = os.path.join(target_dir, entry)
            item_path = f"{path}/{entry}" if path else entry
            is_dir = os.path.isdir(full_path)
            try:
                size = 0 if is_dir else os.path.getsize(full_path)
            except OSError:
                size = 0

            items.append({
                'name': entry,
                'path': item_path,
                'type': 'dir' if is_dir else 'file',
                'size': size,
                'download_url': None
            })
        return jsonify(items)

    except subprocess.TimeoutExpired:
        return jsonify({"error": "Timeout ao listar arquivos"}), 504
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _read_git_file(repo_path, path, file_ref, size_result):
    """Lê conteúdo de arquivo via git show (repositórios git)."""
    file_size = int(size_result.stdout.strip())
    file_name = path.split('/')[-1]

    if file_size > 1_048_576:  # 1MB
        return jsonify({
            'name': file_name, 'path': path, 'type': 'file',
            'size': file_size, 'content': None, 'download_url': None
        })

    content_result = subprocess.run(
        ['git', 'show', file_ref],
        cwd=repo_path, capture_output=True, timeout=10
    )
    if content_result.returncode != 0:
        return jsonify({"error": "Erro ao ler arquivo"}), 500

    try:
        encoded = base64.b64encode(content_result.stdout).decode('ascii')
        return jsonify({
            'name': file_name, 'path': path, 'type': 'file',
            'size': file_size, 'content': encoded,
            'download_url': None, 'html_url': None
        })
    except Exception:
        return jsonify({
            'name': file_name, 'path': path, 'type': 'file',
            'size': file_size, 'content': None, 'download_url': None
        })


def _read_fs_file(file_path, rel_path):
    """Lê conteúdo de arquivo via filesystem (artefatos sem git)."""
    file_name = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)

    if file_size > 1_048_576:  # 1MB
        return jsonify({
            'name': file_name, 'path': rel_path, 'type': 'file',
            'size': file_size, 'content': None, 'download_url': None
        })

    try:
        with open(file_path, 'rb') as f:
            raw = f.read()
        # Tenta decodificar como texto
        raw.decode('utf-8')
        encoded = base64.b64encode(raw).decode('ascii')
        return jsonify({
            'name': file_name, 'path': rel_path, 'type': 'file',
            'size': file_size, 'content': encoded,
            'download_url': None, 'html_url': None
        })
    except (UnicodeDecodeError, Exception):
        return jsonify({
            'name': file_name, 'path': rel_path, 'type': 'file',
            'size': file_size, 'content': None, 'download_url': None
        })


# =====================================================================
# ROTAS DE INTEGRAÇÃO GITHUB (proxy backend)
# =====================================================================


@repositories_bp.route("/api/github/discover", methods=["POST"])
@require_admin
@rate_limit(max_requests=10, window_seconds=60)
def discover_repositories():
    """Descobre repositórios do GitHub via API (servidor faz a chamada).
    O token nunca sai do backend."""
    token, _ = github_integration.get_github_credentials()
    if not token:
        return jsonify({"error": "GitHub nao configurado. Configure token e username."}), 400

    repos, error, status_code = github_integration.discover_repos(token)
    if error:
        return jsonify(error), status_code
    return jsonify(repos)


@repositories_bp.route("/api/github/test-connection", methods=["POST"])
@require_admin
@rate_limit(max_requests=10, window_seconds=60)
def test_github_connection():
    """Testa conexão com GitHub usando token e username fornecidos.
    Usado no formulário de configuração antes de salvar."""
    data = request.json
    token = data.get("token", "").strip()
    username = data.get("username", "").strip()

    if not token or not username:
        return jsonify({"error": "Token e username obrigatorios"}), 400

    result, error, status_code = github_integration.test_connection(token, username)
    if error:
        return jsonify(error), status_code
    return jsonify(result)


@repositories_bp.route("/api/github/status", methods=["GET"])
@require_auth
def github_status():
    """Retorna se GitHub esta configurado (sem expor dados sensiveis).
    Acessivel por todos os perfis autenticados."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT token, username FROM github_settings WHERE id = 1")
    settings = cursor.fetchone()
    release_db_connection(conn)

    configured = bool(settings and settings.get("token") and settings.get("username"))
    return jsonify({"configured": configured})


# =====================================================================
# ROTAS DE CONFIGURAÇÕES GITHUB
# =====================================================================


@repositories_bp.route("/api/github-settings", methods=["GET"])
@require_admin
def get_github_settings():
    """Busca configurações GitHub — retorna apenas username e status (token nunca exposto)"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT token, username, saved_at FROM github_settings WHERE id = 1")
    settings = cursor.fetchone()
    release_db_connection(conn)

    if settings:
        settings_dict = dict(settings)
        has_token = bool(settings_dict.get('token'))
        return jsonify({
            "has_token": has_token,
            "token_masked": "ghp_****" if has_token else "",
            "username": settings_dict.get("username", ""),
            "saved_at": settings_dict.get("saved_at")
        })

    return jsonify({"has_token": False, "token_masked": "", "username": "", "saved_at": None})


@repositories_bp.route("/api/github-settings", methods=["POST"])
@require_admin
@rate_limit(max_requests=5, window_seconds=60)  # 5 saves/min
def save_github_settings():
    """Salva configurações GitHub (criptografa token antes de salvar)"""
    data = request.json

    if not data.get("token") or not data.get("username"):
        return jsonify({"error": "Token e username são obrigatórios"}), 400
    
    # Valida formato do token
    token = data["token"]
    if not (token.startswith('ghp_') or token.startswith('github_pat_')):
        return jsonify({"error": "Formato de token GitHub inválido"}), 400

    # Criptografa token antes de salvar
    if crypto.token_encryption and crypto.token_encryption.is_initialized():
        encrypted_token = crypto.token_encryption.encrypt_token(token)
    else:
        # Fallback (não recomendado, mas necessário se criptografia falhar)
        # Idealmente deveria lançar erro
        # Por enquanto vamos salvar raw e logar erro no console do server?
        # Ou retornar erro?
        # Vamos assumir que se falhar, retorna erro.
        return jsonify({"error": "Sistema de criptografia não inicializado."}), 500
    
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
        release_db_connection(conn)
