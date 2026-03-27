"""
Rotas do Modulo Dev Workspace — Desenvolvimento Assistido.

Navegacao de fontes AdvPL, analise de impacto, assistente de compilacao
e politicas de branch-ambiente.
"""

from flask import Blueprint, request, jsonify, make_response
from app.database import get_db, release_db_connection
from app.database.core import TransactionContext
from app.utils.security import require_auth, require_admin, require_operator
from app.utils.rate_limiter import rate_limit
from app.services import devworkspace_service as dws
from app.services import branch_policy_service as bps

devworkspace_bp = Blueprint("devworkspace", __name__)


# =====================================================================
# 1A — NAVEGADOR DE FONTES
# =====================================================================


@devworkspace_bp.route("/api/devworkspace/fontes", methods=["GET"])
@require_auth
@rate_limit(max_requests=60, window_seconds=60)
def list_fontes():
    """Lista FONTES_DIR disponiveis por ambiente."""
    env_id = request.args.get("environment_id", type=int)

    conn = get_db()
    cursor = conn.cursor()
    try:
        result = dws.list_fontes_dirs(cursor, env_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        release_db_connection(conn)


@devworkspace_bp.route("/api/devworkspace/browse", methods=["GET"])
@require_auth
@rate_limit(max_requests=120, window_seconds=60)
def browse():
    """Navega diretorio de fontes."""
    env_id = request.args.get("environment_id", type=int)
    path = request.args.get("path", "")

    if not env_id:
        return jsonify({"error": "environment_id obrigatorio"}), 400

    conn = get_db()
    cursor = conn.cursor()
    try:
        fontes_dir = dws.get_fontes_dir(cursor, env_id)
        if not fontes_dir:
            return jsonify({"error": "FONTES_DIR nao configurado para este ambiente"}), 404

        items, error = dws.browse_directory(fontes_dir, path)
        if error:
            return jsonify({"error": error}), 400
        return jsonify({"path": path, "base": fontes_dir, "items": items})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        release_db_connection(conn)


@devworkspace_bp.route("/api/devworkspace/file", methods=["GET"])
@require_auth
@rate_limit(max_requests=120, window_seconds=60)
def read_file():
    """Le conteudo de um arquivo fonte."""
    env_id = request.args.get("environment_id", type=int)
    file_path = request.args.get("path", "")

    if not env_id or not file_path:
        return jsonify({"error": "environment_id e path obrigatorios"}), 400

    conn = get_db()
    cursor = conn.cursor()
    try:
        fontes_dir = dws.get_fontes_dir(cursor, env_id)
        if not fontes_dir:
            return jsonify({"error": "FONTES_DIR nao configurado para este ambiente"}), 404

        data, error = dws.read_source_file(fontes_dir, file_path)
        if error:
            return jsonify({"error": error}), 400
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        release_db_connection(conn)


@devworkspace_bp.route("/api/devworkspace/search", methods=["POST"])
@require_auth
@rate_limit(max_requests=30, window_seconds=60)
def search():
    """Busca nos fontes AdvPL."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Dados nao fornecidos"}), 400

    env_id = data.get("environment_id")
    pattern = data.get("pattern", "").strip()
    file_filter = data.get("file_filter", "*.prw")

    if not env_id or not pattern:
        return jsonify({"error": "environment_id e pattern obrigatorios"}), 400

    conn = get_db()
    cursor = conn.cursor()
    try:
        fontes_dir = dws.get_fontes_dir(cursor, env_id)
        if not fontes_dir:
            return jsonify({"error": "FONTES_DIR nao configurado para este ambiente"}), 404

        result, error = dws.search_sources(fontes_dir, pattern, file_filter)
        if error:
            return jsonify({"error": error}), 400
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        release_db_connection(conn)


# =====================================================================
# 1B — ANALISE DE IMPACTO
# =====================================================================


@devworkspace_bp.route("/api/devworkspace/impact", methods=["POST"])
@require_auth
@rate_limit(max_requests=30, window_seconds=60)
def impact_analysis():
    """Analise de impacto de um arquivo fonte."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Dados nao fornecidos"}), 400

    env_id = data.get("environment_id")
    file_path = data.get("file_path", "").strip()

    if not env_id or not file_path:
        return jsonify({"error": "environment_id e file_path obrigatorios"}), 400

    conn = get_db()
    cursor = conn.cursor()
    try:
        fontes_dir = dws.get_fontes_dir(cursor, env_id)
        if not fontes_dir:
            return jsonify({"error": "FONTES_DIR nao configurado para este ambiente"}), 404

        result, error = dws.analyze_impact(cursor, env_id, fontes_dir, file_path)
        if error:
            return jsonify({"error": error}), 400
        conn.commit()  # Salva cache de impacto
        return jsonify(result)
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        release_db_connection(conn)


# =====================================================================
# 1C — ASSISTENTE DE COMPILACAO
# =====================================================================


@devworkspace_bp.route("/api/devworkspace/diff", methods=["POST"])
@require_auth
@rate_limit(max_requests=20, window_seconds=60)
def diff_fontes():
    """Compara FONTES_DIR com repositorio clonado."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Dados nao fornecidos"}), 400

    env_id = data.get("environment_id")
    repo_name = data.get("repo_name", "").strip()
    branch_name = data.get("branch_name", "").strip()

    if not env_id or not repo_name or not branch_name:
        return jsonify({"error": "environment_id, repo_name e branch_name obrigatorios"}), 400

    conn = get_db()
    cursor = conn.cursor()
    try:
        result, error = dws.diff_fontes_repo(cursor, env_id, repo_name, branch_name)
        if error:
            return jsonify({"error": error}), 400
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        release_db_connection(conn)


@devworkspace_bp.route("/api/devworkspace/compila", methods=["POST"])
@require_admin
@rate_limit(max_requests=10, window_seconds=60)
def generate_compila():
    """Gera conteudo do arquivo compila.txt."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Dados nao fornecidos"}), 400

    env_id = data.get("environment_id")
    file_list = data.get("files", [])

    if not env_id or not file_list:
        return jsonify({"error": "environment_id e files obrigatorios"}), 400

    conn = get_db()
    cursor = conn.cursor()
    try:
        result, error = dws.generate_compila_txt(cursor, env_id, file_list)
        if error:
            return jsonify({"error": error}), 400

        # Retorna como download se solicitado
        if data.get("download"):
            response = make_response(result["content"])
            response.headers["Content-Type"] = "text/plain; charset=utf-8"
            response.headers["Content-Disposition"] = "attachment; filename=compila.txt"
            return response

        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        release_db_connection(conn)


# =====================================================================
# 1D — POLITICAS DE BRANCH-AMBIENTE
# =====================================================================


@devworkspace_bp.route("/api/devworkspace/policies", methods=["GET"])
@require_auth
@rate_limit(max_requests=60, window_seconds=60)
def list_policies():
    """Lista politicas de branch-ambiente."""
    env_id = request.args.get("environment_id", type=int)

    conn = get_db()
    cursor = conn.cursor()
    try:
        result = bps.list_policies(cursor, env_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        release_db_connection(conn)


@devworkspace_bp.route("/api/devworkspace/policies", methods=["POST"])
@require_admin
@rate_limit(max_requests=30, window_seconds=60)
def create_policy():
    """Cria politica de branch-ambiente."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Dados nao fornecidos"}), 400

    env_id = data.get("environment_id")
    repo_name = data.get("repo_name", "").strip()
    branch_name = data.get("branch_name", "").strip()

    if not env_id or not repo_name or not branch_name:
        return jsonify({"error": "environment_id, repo_name e branch_name obrigatorios"}), 400

    with TransactionContext() as (conn, cursor):
        # Verifica se ja existe
        existing = bps.get_policy(cursor, env_id, repo_name, branch_name)
        if existing:
            return jsonify({"error": f"Ja existe politica para {repo_name}/{branch_name} neste ambiente"}), 409

        rules = {
            "allow_push": data.get("allow_push", True),
            "allow_pull": data.get("allow_pull", True),
            "allow_commit": data.get("allow_commit", True),
            "allow_create_branch": data.get("allow_create_branch", False),
            "require_approval": data.get("require_approval", False),
            "is_default": data.get("is_default", False),
            "created_by": request.current_user.get("id"),
        }

        policy_id = bps.create_policy(cursor, env_id, repo_name, branch_name, rules)
        return (
            jsonify({"success": True, "id": policy_id, "message": f"Politica criada para {repo_name}/{branch_name}"}),
            201,
        )


@devworkspace_bp.route("/api/devworkspace/policies/<int:policy_id>", methods=["PUT"])
@require_admin
@rate_limit(max_requests=30, window_seconds=60)
def update_policy(policy_id):
    """Atualiza politica de branch-ambiente."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Dados nao fornecidos"}), 400

    with TransactionContext() as (conn, cursor):
        existing = bps.get_policy_by_id(cursor, policy_id)
        if not existing:
            return jsonify({"error": "Politica nao encontrada"}), 404

        rules = {}
        for field in [
            "allow_push",
            "allow_pull",
            "allow_commit",
            "allow_create_branch",
            "require_approval",
            "is_default",
        ]:
            if field in data:
                rules[field] = data[field]

        if not rules:
            return jsonify({"error": "Nenhum campo para atualizar"}), 400

        bps.update_policy(cursor, policy_id, rules)
        return jsonify({"success": True, "message": "Politica atualizada"})


@devworkspace_bp.route("/api/devworkspace/policies/<int:policy_id>", methods=["DELETE"])
@require_admin
@rate_limit(max_requests=30, window_seconds=60)
def delete_policy(policy_id):
    """Remove politica de branch-ambiente."""
    with TransactionContext() as (conn, cursor):
        deleted = bps.delete_policy(cursor, policy_id)
        if not deleted:
            return jsonify({"error": "Politica nao encontrada"}), 404
        return jsonify({"success": True, "message": "Politica removida"})


@devworkspace_bp.route("/api/devworkspace/policies/check", methods=["GET"])
@require_auth
@rate_limit(max_requests=120, window_seconds=60)
def check_policy():
    """Verifica se uma operacao eh permitida pela politica."""
    env_id = request.args.get("environment_id", type=int)
    repo_name = request.args.get("repo_name", "")
    branch_name = request.args.get("branch_name", "")
    operation = request.args.get("operation", "")

    if not env_id or not repo_name or not branch_name or not operation:
        return jsonify({"error": "Todos os parametros sao obrigatorios"}), 400

    conn = get_db()
    cursor = conn.cursor()
    try:
        result = bps.validate_operation(cursor, env_id, repo_name, branch_name, operation)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        release_db_connection(conn)
