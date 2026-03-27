"""
Rotas do Auditor de INI Protheus.

Upload, análise e histórico de auditorias de arquivos .ini
de servidores TOTVS Protheus.
"""

from flask import Blueprint, request, jsonify
from app.database import get_db, release_db_connection
from app.utils.security import require_auth, require_admin
from app.services.ini_auditor import (
    run_audit,
    get_audit_history,
    get_audit_detail,
    get_best_practices,
    seed_best_practices,
)

auditor_bp = Blueprint("auditor", __name__)

# Limite de tamanho do upload (1MB)
MAX_INI_SIZE = 1 * 1024 * 1024


# =========================================================
# UPLOAD E ANÁLISE
# =========================================================


@auditor_bp.route("/api/auditor/upload", methods=["POST"])
@require_auth
def upload_and_analyze():
    """Upload de arquivo .ini e análise automática."""
    # Aceitar tanto multipart/form-data quanto JSON com conteúdo inline
    if request.content_type and "multipart" in request.content_type:
        ini_file = request.files.get("ini_file")
        if not ini_file:
            return jsonify({"error": "Campo 'ini_file' é obrigatório"}), 400

        filename = ini_file.filename or "unknown.ini"
        if not filename.lower().endswith(".ini"):
            return jsonify({"error": "Apenas arquivos .ini são aceitos"}), 400

        content_bytes = ini_file.read()
        if len(content_bytes) > MAX_INI_SIZE:
            return jsonify({"error": "Arquivo excede limite de 1MB"}), 400

        # Decodificar: tenta UTF-8, fallback cp1252
        try:
            content = content_bytes.decode("utf-8")
        except UnicodeDecodeError:
            content = content_bytes.decode("cp1252", errors="replace")

        environment_id = request.form.get("environment_id", type=int)
    else:
        data = request.get_json(silent=True) or {}
        content = data.get("content", "")
        filename = data.get("filename", "custom.ini")
        environment_id = data.get("environment_id")

    # Fallback: pegar environment_id do header (padrão do api-client)
    if not environment_id:
        env_header = request.headers.get("X-Environment-Id")
        if env_header:
            try:
                environment_id = int(env_header)
            except (ValueError, TypeError):
                pass

        if not content:
            return jsonify({"error": "Campo 'content' é obrigatório"}), 400

    # Obter user_id do token
    user_id = getattr(request, "user_id", None)

    try:
        result = run_audit(content, filename, user_id, environment_id)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": f"Erro na análise: {str(e)}"}), 500


# =========================================================
# HISTÓRICO
# =========================================================


@auditor_bp.route("/api/auditor/history", methods=["GET"])
@require_auth
def list_history():
    """Lista histórico de auditorias."""
    environment_id = request.args.get("environment_id", type=int)
    limit = min(int(request.args.get("limit", 20)), 100)
    offset = int(request.args.get("offset", 0))

    try:
        result = get_audit_history(environment_id, limit, offset)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": f"Erro ao buscar histórico: {str(e)}"}), 500


@auditor_bp.route("/api/auditor/audit/<int:audit_id>", methods=["GET"])
@require_auth
def get_audit(audit_id):
    """Retorna detalhes de uma auditoria específica."""
    try:
        result = get_audit_detail(audit_id)
        if not result:
            return jsonify({"error": "Auditoria não encontrada"}), 404
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": f"Erro ao buscar auditoria: {str(e)}"}), 500


# =========================================================
# BOAS PRÁTICAS
# =========================================================


@auditor_bp.route("/api/auditor/best-practices", methods=["GET"])
@require_auth
def list_best_practices():
    """Lista boas práticas cadastradas."""
    ini_type = request.args.get("ini_type", "appserver")

    try:
        practices = get_best_practices(ini_type)
        return jsonify({"practices": practices, "total": len(practices)}), 200
    except Exception as e:
        return jsonify({"error": f"Erro ao buscar boas práticas: {str(e)}"}), 500


@auditor_bp.route("/api/auditor/best-practices/seed", methods=["POST"])
@require_admin
def seed_practices():
    """Popula boas práticas a partir do conhecimento TDN (admin only)."""
    try:
        count = seed_best_practices()
        return jsonify({"message": f"{count} regras inseridas com sucesso", "count": count}), 200
    except Exception as e:
        return jsonify({"error": f"Erro ao popular boas práticas: {str(e)}"}), 500


@auditor_bp.route("/api/auditor/best-practices/<int:bp_id>", methods=["PUT"])
@require_admin
def update_best_practice(bp_id):
    """Atualiza uma regra de boa prática (admin only)."""
    data = request.get_json(silent=True) or {}

    allowed_fields = {
        "recommended_value", "value_type", "min_value", "max_value",
        "enum_values", "severity", "description", "tdn_url",
        "is_required", "is_active",
    }
    updates = {k: v for k, v in data.items() if k in allowed_fields}

    if not updates:
        return jsonify({"error": "Nenhum campo válido para atualizar"}), 400

    conn = get_db()
    cursor = conn.cursor()
    try:
        set_parts = []
        params = []
        for key, value in updates.items():
            set_parts.append(f"{key} = %s")
            params.append(value)
        set_parts.append("updated_at = CURRENT_TIMESTAMP")
        params.append(bp_id)

        cursor.execute(
            f"UPDATE ini_best_practices SET {', '.join(set_parts)} WHERE id = %s",
            params,
        )
        if cursor.rowcount == 0:
            return jsonify({"error": "Regra não encontrada"}), 404

        conn.commit()
        return jsonify({"message": "Regra atualizada com sucesso"}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"error": f"Erro ao atualizar: {str(e)}"}), 500
    finally:
        release_db_connection(conn)


@auditor_bp.route("/api/auditor/audit/<int:audit_id>", methods=["DELETE"])
@require_admin
def delete_audit(audit_id):
    """Remove uma auditoria e seus resultados (admin only)."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM ini_audits WHERE id = %s", (audit_id,))
        if cursor.rowcount == 0:
            return jsonify({"error": "Auditoria não encontrada"}), 404
        conn.commit()
        return jsonify({"message": "Auditoria removida"}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"error": f"Erro ao remover: {str(e)}"}), 500
    finally:
        release_db_connection(conn)
