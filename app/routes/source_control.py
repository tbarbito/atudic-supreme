"""
Source Control — Endpoints de Controle de Versão (Git).

Gerencia status, diff, staging, commit, push e discard de arquivos
nos repositórios clonados pelo BiizHubOps.
"""
from flask import Blueprint, request, jsonify
from datetime import datetime, timezone
import os
import re
import shutil

from app.database import get_db, release_db_connection
from app.utils.security import require_auth, require_operator
from app.utils.rate_limiter import rate_limit
from app.utils.validators import (
    sanitize_branch_name,
    sanitize_commit_message,
    execute_git_command_safely
)
from app.services.repo_helpers import resolve_repo_path as _resolve_repo_path
from app.services.repo_helpers import validate_file_path as _validate_file_path
from app.services.repo_helpers import decrypt_github_token as _decrypt_github_token
from app.services.branch_policy_service import validate_operation as _validate_branch_policy

source_control_bp = Blueprint("source_control", __name__)


# =====================================================================
# STATUS
# =====================================================================

@source_control_bp.route("/api/repositories/<int:repo_id>/status", methods=["GET"])
@require_auth
@rate_limit(max_requests=60, window_seconds=60)
def git_status(repo_id):
    """Retorna git status categorizado (staged, modified, untracked)."""
    branch_name = request.args.get("branch")
    if not branch_name:
        return jsonify({"error": "Parâmetro 'branch' é obrigatório"}), 400

    repo_path, repo, error = _resolve_repo_path(repo_id, branch_name)
    if error:
        return error

    try:
        result = execute_git_command_safely(
            ['git', 'status', '--porcelain=v1'],
            cwd=repo_path, timeout=30
        )
    except Exception as e:
        return jsonify({"error": f"Erro ao obter status: {str(e)}"}), 500

    staged = []
    modified = []
    untracked = []

    status_labels = {
        'M': 'modificado', 'A': 'adicionado', 'D': 'removido',
        'R': 'renomeado', 'C': 'copiado', '?': 'não rastreado'
    }

    for line in result.stdout.split('\n'):
        if not line.strip() or len(line) < 4:
            continue
        index_status = line[0]   # staging area
        work_status = line[1]    # working tree
        file_path = line[3:]     # file path

        # Arquivo staged (index tem mudança)
        if index_status not in (' ', '?'):
            staged.append({
                "path": file_path,
                "status": index_status,
                "status_label": status_labels.get(index_status, index_status)
            })

        # Arquivo modificado no worktree (não staged)
        if work_status not in (' ', '?') and index_status != '?':
            modified.append({
                "path": file_path,
                "status": work_status,
                "status_label": status_labels.get(work_status, work_status)
            })

        # Arquivo não rastreado
        if index_status == '?' and work_status == '?':
            untracked.append({
                "path": file_path,
                "status": "?",
                "status_label": "não rastreado"
            })

    return jsonify({
        "staged": staged,
        "modified": modified,
        "untracked": untracked,
        "summary": {
            "staged": len(staged),
            "modified": len(modified),
            "untracked": len(untracked)
        }
    })


# =====================================================================
# DIFF
# =====================================================================

@source_control_bp.route("/api/repositories/<int:repo_id>/diff", methods=["GET"])
@require_auth
@rate_limit(max_requests=60, window_seconds=60)
def git_diff(repo_id):
    """Retorna diff unificado de um arquivo específico."""
    branch_name = request.args.get("branch")
    file_path = request.args.get("file_path")
    is_staged = request.args.get("staged", "false").lower() == "true"
    is_untracked = request.args.get("untracked", "false").lower() == "true"

    if not branch_name or not file_path:
        return jsonify({"error": "Parâmetros 'branch' e 'file_path' são obrigatórios"}), 400

    repo_path, repo, error = _resolve_repo_path(repo_id, branch_name)
    if error:
        return error

    safe_file, file_error = _validate_file_path(file_path, repo_path)
    if file_error:
        return jsonify({"error": file_error}), 400

    # Verifica se é arquivo binário
    full_file_path = os.path.join(repo_path, safe_file)
    is_binary = False
    try:
        with open(full_file_path, 'rb') as f:
            chunk = f.read(8192)
            if b'\x00' in chunk:
                is_binary = True
    except (FileNotFoundError, PermissionError):
        pass

    if is_binary:
        return jsonify({
            "file_path": safe_file,
            "diff": "",
            "is_new": False,
            "is_binary": True
        })

    # Arquivo não rastreado — retorna conteúdo completo
    if is_untracked:
        try:
            with open(full_file_path, 'r', errors='replace') as f:
                content = f.read(1048576)  # Max 1MB
            return jsonify({
                "file_path": safe_file,
                "diff": content,
                "is_new": True,
                "is_binary": False
            })
        except Exception as e:
            return jsonify({"error": f"Erro ao ler arquivo: {str(e)}"}), 500

    # git diff (staged ou unstaged)
    try:
        cmd = ['git', 'diff']
        if is_staged:
            cmd.append('--cached')
        cmd.extend(['--', safe_file])

        result = execute_git_command_safely(cmd, cwd=repo_path, timeout=30)
        diff_output = result.stdout

        # Se diff retornou vazio para arquivo staged, tenta fallbacks
        if is_staged and not diff_output.strip():
            # Fallback 1: git diff HEAD -- <file> (cobre edge cases)
            try:
                fb_result = execute_git_command_safely(
                    ['git', 'diff', 'HEAD', '--', safe_file],
                    cwd=repo_path, timeout=30
                )
                if fb_result.stdout.strip():
                    return jsonify({
                        "file_path": safe_file,
                        "diff": fb_result.stdout[:1048576],
                        "is_new": False,
                        "is_binary": False
                    })
            except Exception:
                pass

            # Fallback 2: arquivo novo (não existe em HEAD) — mostra conteúdo
            try:
                show_result = execute_git_command_safely(
                    ['git', 'show', f':{safe_file}'],
                    cwd=repo_path, timeout=30
                )
                if show_result.stdout.strip():
                    return jsonify({
                        "file_path": safe_file,
                        "diff": show_result.stdout[:1048576],
                        "is_new": True,
                        "is_binary": False
                    })
            except Exception:
                pass

            # Fallback 3: lê do filesystem
            try:
                with open(full_file_path, 'r', errors='replace') as f:
                    content = f.read(1048576)
                if content.strip():
                    return jsonify({
                        "file_path": safe_file,
                        "diff": content,
                        "is_new": True,
                        "is_binary": False
                    })
            except Exception:
                pass

        return jsonify({
            "file_path": safe_file,
            "diff": diff_output[:1048576],  # Max 1MB
            "is_new": False,
            "is_binary": False
        })
    except Exception as e:
        return jsonify({"error": f"Erro ao obter diff: {str(e)}"}), 500


# =====================================================================
# LOG / HISTÓRICO
# =====================================================================

@source_control_bp.route("/api/repositories/<int:repo_id>/log", methods=["GET"])
@require_auth
@rate_limit(max_requests=60, window_seconds=60)
def git_log(repo_id):
    """Retorna histórico de commits recentes."""
    branch_name = request.args.get("branch")
    limit = min(int(request.args.get("limit", 20)), 50)

    if not branch_name:
        return jsonify({"error": "Parâmetro 'branch' é obrigatório"}), 400

    repo_path, repo, error = _resolve_repo_path(repo_id, branch_name)
    if error:
        return error

    try:
        result = execute_git_command_safely(
            ['git', 'log', f'--format=%H|%h|%an|%ae|%at|%s', f'-n{limit}'],
            cwd=repo_path, timeout=30
        )
    except Exception as e:
        return jsonify({"error": f"Erro ao obter log: {str(e)}"}), 500

    commits = []
    for line in result.stdout.strip().split('\n'):
        if not line:
            continue
        parts = line.split('|', 5)
        if len(parts) == 6:
            ts = int(parts[4])
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            commits.append({
                "hash": parts[0],
                "short_hash": parts[1],
                "author": parts[2],
                "email": parts[3],
                "date": dt.isoformat(),
                "message": parts[5]
            })

    return jsonify({"commits": commits})


@source_control_bp.route("/api/repositories/<int:repo_id>/commit-files", methods=["GET"])
@require_auth
@rate_limit(max_requests=60, window_seconds=60)
def git_commit_files(repo_id):
    """Retorna lista de arquivos alterados em um commit específico."""
    branch_name = request.args.get("branch")
    commit_hash = request.args.get("hash")

    if not branch_name or not commit_hash:
        return jsonify({"error": "Parâmetros 'branch' e 'hash' são obrigatórios"}), 400

    if not re.match(r'^[a-f0-9]{7,40}$', commit_hash):
        return jsonify({"error": "Hash de commit inválido"}), 400

    repo_path, repo, error = _resolve_repo_path(repo_id, branch_name)
    if error:
        return error

    try:
        result = execute_git_command_safely(
            ['git', 'diff-tree', '--no-commit-id', '--name-status', '-r', commit_hash],
            cwd=repo_path, timeout=30
        )
    except Exception as e:
        return jsonify({"error": f"Erro ao obter arquivos do commit: {str(e)}"}), 500

    status_labels = {
        'M': 'modificado', 'A': 'adicionado', 'D': 'removido',
        'R': 'renomeado', 'C': 'copiado'
    }

    files = []
    for line in result.stdout.strip().split('\n'):
        if not line:
            continue
        parts = line.split('\t', 1)
        if len(parts) == 2:
            status = parts[0].strip()
            file_path = parts[1].strip()
            files.append({
                "path": file_path,
                "status": status[0] if status else '?',
                "status_label": status_labels.get(status[0], status)
            })

    return jsonify({"files": files, "hash": commit_hash})


@source_control_bp.route("/api/repositories/<int:repo_id>/commit-diff", methods=["GET"])
@require_auth
@rate_limit(max_requests=60, window_seconds=60)
def git_commit_diff(repo_id):
    """Retorna diff de um arquivo em um commit específico."""
    branch_name = request.args.get("branch")
    commit_hash = request.args.get("hash")
    file_path = request.args.get("file_path")

    if not branch_name or not commit_hash or not file_path:
        return jsonify({"error": "Parâmetros 'branch', 'hash' e 'file_path' são obrigatórios"}), 400

    if not re.match(r'^[a-f0-9]{7,40}$', commit_hash):
        return jsonify({"error": "Hash de commit inválido"}), 400

    repo_path, repo, error = _resolve_repo_path(repo_id, branch_name)
    if error:
        return error

    safe_file, file_error = _validate_file_path(file_path, repo_path)
    if file_error:
        return jsonify({"error": file_error}), 400

    try:
        result = execute_git_command_safely(
            ['git', 'diff', f'{commit_hash}~1', commit_hash, '--', safe_file],
            cwd=repo_path, timeout=30
        )
        return jsonify({
            "file_path": safe_file,
            "diff": result.stdout[:1048576],
            "hash": commit_hash
        })
    except Exception:
        # Fallback para primeiro commit (sem pai)
        try:
            result = execute_git_command_safely(
                ['git', 'diff', '--no-index', '/dev/null', safe_file],
                cwd=repo_path, timeout=30
            )
            return jsonify({
                "file_path": safe_file,
                "diff": result.stdout[:1048576],
                "hash": commit_hash
            })
        except Exception as e:
            return jsonify({"error": f"Erro ao obter diff: {str(e)}"}), 500


# =====================================================================
# STAGE / UNSTAGE
# =====================================================================

@source_control_bp.route("/api/repositories/<int:repo_id>/stage", methods=["POST"])
@require_operator
@rate_limit(max_requests=60, window_seconds=60)
def git_stage(repo_id):
    """Stage ou unstage arquivos individuais."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Dados não fornecidos"}), 400

    branch_name = data.get("branch_name")
    files = data.get("files", [])
    action = data.get("action", "stage")  # 'stage' ou 'unstage'

    if not branch_name or not files:
        return jsonify({"error": "branch_name e files são obrigatórios"}), 400

    if action not in ("stage", "unstage"):
        return jsonify({"error": "action deve ser 'stage' ou 'unstage'"}), 400

    repo_path, repo, error = _resolve_repo_path(repo_id, branch_name)
    if error:
        return error

    safe_files = []
    for fp in files:
        safe, err = _validate_file_path(fp, repo_path)
        if err:
            return jsonify({"error": f"Arquivo inválido '{fp}': {err}"}), 400
        safe_files.append(safe)

    try:
        if action == "stage":
            cmd = ['git', 'add', '--'] + safe_files
        else:
            cmd = ['git', 'reset', 'HEAD', '--'] + safe_files

        execute_git_command_safely(cmd, cwd=repo_path, timeout=30)

        verb = "adicionado(s) ao staging" if action == "stage" else "removido(s) do staging"
        return jsonify({
            "success": True,
            "message": f"{len(safe_files)} arquivo(s) {verb}"
        })
    except Exception as e:
        return jsonify({"error": f"Erro ao {action}: {str(e)}"}), 500


# =====================================================================
# COMMIT
# =====================================================================

@source_control_bp.route("/api/repositories/<int:repo_id>/commit", methods=["POST"])
@require_operator
@rate_limit(max_requests=30, window_seconds=60)
def git_commit(repo_id):
    """Realiza commit das alterações staged (sem push)."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Dados não fornecidos"}), 400

    branch_name = data.get("branch_name")
    commit_message = data.get("commit_message", "").strip()

    if not branch_name or not commit_message:
        return jsonify({"error": "branch_name e commit_message são obrigatórios"}), 400

    repo_path, repo, error = _resolve_repo_path(repo_id, branch_name)
    if error:
        return error

    # Valida politica de branch-ambiente
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT environment_id, name FROM repositories WHERE id = %s", (repo_id,))
    repo_row = cursor.fetchone()
    if repo_row:
        policy_check = _validate_branch_policy(cursor, repo_row.get('environment_id'), repo_row['name'], branch_name, 'commit')
        if not policy_check['allowed']:
            release_db_connection(conn)
            return jsonify({"error": policy_check['reason']}), 403

    safe_message = sanitize_commit_message(commit_message)

    # Configura user para o commit
    cursor.execute("SELECT username FROM github_settings WHERE id = 1")
    gh_row = cursor.fetchone()
    release_db_connection(conn)

    git_user = gh_row["username"] if gh_row else "atudic"
    git_email = f"{git_user}@atudic.local"

    try:
        execute_git_command_safely(['git', 'config', 'user.name', git_user], cwd=repo_path)
        execute_git_command_safely(['git', 'config', 'user.email', git_email], cwd=repo_path)
        execute_git_command_safely(['git', 'commit', '-m', safe_message], cwd=repo_path)

        result = execute_git_command_safely(
            ['git', 'rev-parse', '--short', 'HEAD'],
            cwd=repo_path, timeout=10
        )
        commit_hash = result.stdout.strip()

        return jsonify({
            "success": True,
            "message": f"Commit realizado: {commit_hash}",
            "commit_hash": commit_hash
        })
    except Exception as e:
        return jsonify({"error": f"Erro ao commitar: {str(e)}"}), 500


# =====================================================================
# PUSH
# =====================================================================

@source_control_bp.route("/api/repositories/<int:repo_id>/push-only", methods=["POST"])
@require_operator
@rate_limit(max_requests=10, window_seconds=300)
def git_push_only(repo_id):
    """Push de commits já realizados para o remote."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Dados não fornecidos"}), 400

    branch_name = data.get("branch_name")
    if not branch_name:
        return jsonify({"error": "branch_name é obrigatório"}), 400

    repo_path, repo, error = _resolve_repo_path(repo_id, branch_name)
    if error:
        return error

    # Valida politica de branch-ambiente e injeta token na URL de push
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT environment_id, name FROM repositories WHERE id = %s", (repo_id,))
    repo_row = cursor.fetchone()
    if repo_row:
        policy_check = _validate_branch_policy(cursor, repo_row.get('environment_id'), repo_row['name'], branch_name, 'push')
        if not policy_check['allowed']:
            release_db_connection(conn)
            return jsonify({"error": policy_check['reason']}), 403

    cursor.execute("SELECT token FROM github_settings WHERE id = 1")
    gh_row = cursor.fetchone()
    release_db_connection(conn)

    if gh_row and gh_row.get("token"):
        token = _decrypt_github_token(gh_row["token"])
        try:
            result = execute_git_command_safely(
                ['git', 'remote', 'get-url', 'origin'],
                cwd=repo_path, timeout=10
            )
            origin_url = result.stdout.strip()
            if origin_url.startswith("https://") and "@" not in origin_url:
                auth_url = origin_url.replace("https://", f"https://{token}@")
                execute_git_command_safely(
                    ['git', 'remote', 'set-url', 'origin', auth_url],
                    cwd=repo_path, timeout=10
                )
        except Exception:
            pass

    try:
        safe_branch = sanitize_branch_name(branch_name)
        execute_git_command_safely(
            ['git', 'push', 'origin', safe_branch],
            cwd=repo_path, timeout=120
        )

        # Restaura URL sem token
        try:
            result = execute_git_command_safely(
                ['git', 'remote', 'get-url', 'origin'],
                cwd=repo_path, timeout=10
            )
            current_url = result.stdout.strip()
            if "@" in current_url and "https://" in current_url:
                clean_url = "https://" + current_url.split("@", 1)[1]
                execute_git_command_safely(
                    ['git', 'remote', 'set-url', 'origin', clean_url],
                    cwd=repo_path, timeout=10
                )
        except Exception:
            pass

        return jsonify({"success": True, "message": "Push realizado com sucesso!"})
    except Exception as e:
        return jsonify({"error": f"Erro ao fazer push: {str(e)}"}), 500


# =====================================================================
# DISCARD
# =====================================================================

@source_control_bp.route("/api/repositories/<int:repo_id>/discard", methods=["POST"])
@require_operator
@rate_limit(max_requests=30, window_seconds=60)
def git_discard(repo_id):
    """Descarta alterações de arquivos individuais."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Dados não fornecidos"}), 400

    branch_name = data.get("branch_name")
    files = data.get("files", [])
    file_type = data.get("file_type", "modified")  # 'modified', 'staged', 'untracked'

    if not branch_name or not files:
        return jsonify({"error": "branch_name e files são obrigatórios"}), 400

    repo_path, repo, error = _resolve_repo_path(repo_id, branch_name)
    if error:
        return error

    safe_files = []
    for fp in files:
        safe, err = _validate_file_path(fp, repo_path)
        if err:
            return jsonify({"error": f"Arquivo inválido '{fp}': {err}"}), 400
        safe_files.append(safe)

    try:
        if file_type in ("staged", "modified"):
            try:
                execute_git_command_safely(
                    ['git', 'checkout', 'HEAD', '--'] + safe_files,
                    cwd=repo_path, timeout=30
                )
            except Exception:
                try:
                    execute_git_command_safely(
                        ['git', 'reset', 'HEAD', '--'] + safe_files,
                        cwd=repo_path, timeout=30
                    )
                except Exception:
                    pass

                for sf in safe_files:
                    full = os.path.join(repo_path, sf)
                    real_repo = os.path.realpath(repo_path)
                    real_full = os.path.realpath(full)
                    if real_full.startswith(real_repo) and os.path.exists(full):
                        if os.path.isdir(full):
                            shutil.rmtree(full)
                        else:
                            os.remove(full)
        elif file_type == "untracked":
            for sf in safe_files:
                full = os.path.join(repo_path, sf)
                real_repo = os.path.realpath(repo_path)
                real_full = os.path.realpath(full)
                if real_full.startswith(real_repo) and os.path.exists(full):
                    if os.path.isdir(full):
                        shutil.rmtree(full)
                    else:
                        os.remove(full)

        return jsonify({
            "success": True,
            "message": f"Alterações descartadas em {len(safe_files)} arquivo(s)"
        })
    except Exception as e:
        return jsonify({"error": f"Erro ao descartar: {str(e)}"}), 500
