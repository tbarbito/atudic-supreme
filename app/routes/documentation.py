"""
Rotas do Modulo de Documentacao Automatica.

Geracao, listagem, visualizacao e download de documentacao tecnica.
Geracao restrita a administradores, visualizacao para usuarios autenticados.
"""

import re
from flask import Blueprint, request, jsonify, make_response
from app.database import get_db, release_db_connection
from app.utils.security import require_auth, require_admin
from app.services.documentation_generator import (
    generate_data_dictionary,
    generate_process_map,
    generate_error_guide,
    generate_combined,
    save_document,
    list_documents,
    get_document,
    get_document_versions,
    delete_document,
)

documentation_bp = Blueprint("documentation", __name__)

VALID_DOC_TYPES = ["dicionario_dados", "mapa_processos", "guia_erros", "combinado"]

DOC_TYPE_LABELS = {
    "dicionario_dados": "Dicionario de Dados",
    "mapa_processos": "Mapa de Processos",
    "guia_erros": "Guia de Erros",
    "combinado": "Documentacao Combinada",
}


# =========================================================
# LISTAGEM
# =========================================================


@documentation_bp.route("/api/docs", methods=["GET"])
@require_auth
def list_docs():
    """Lista documentos gerados com paginacao e filtro por tipo."""
    doc_type = request.args.get("doc_type")
    limit = min(int(request.args.get("limit", 50)), 200)
    offset = int(request.args.get("offset", 0))

    if doc_type and doc_type not in VALID_DOC_TYPES:
        return jsonify({"error": f"Tipo invalido. Use: {', '.join(VALID_DOC_TYPES)}"}), 400

    conn = get_db()
    cursor = conn.cursor()
    try:
        result = list_documents(cursor, doc_type=doc_type, limit=limit, offset=offset)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        release_db_connection(conn)


# =========================================================
# DETALHES
# =========================================================


@documentation_bp.route("/api/docs/<int:doc_id>", methods=["GET"])
@require_auth
def get_doc(doc_id):
    """Retorna documento completo com content_md."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        doc = get_document(cursor, doc_id)
        if not doc:
            return jsonify({"error": "Documento nao encontrado"}), 404
        return jsonify(doc), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        release_db_connection(conn)


# =========================================================
# GERACAO
# =========================================================


@documentation_bp.route("/api/docs/generate", methods=["POST"])
@require_admin
def generate_doc():
    """Gera novo documento a partir dos dados existentes."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body obrigatorio"}), 400

    doc_type = data.get("doc_type")
    title = data.get("title", "").strip()

    if not doc_type or doc_type not in VALID_DOC_TYPES:
        return jsonify({"error": f"doc_type obrigatorio. Use: {', '.join(VALID_DOC_TYPES)}"}), 400

    if not title:
        title = DOC_TYPE_LABELS.get(doc_type, "Documento")

    connection_id = data.get("connection_id")
    module = data.get("module")
    category = data.get("category")

    user_id = request.current_user.get("id") if hasattr(request, "current_user") else None

    conn = get_db()
    cursor = conn.cursor()
    try:
        if doc_type == "dicionario_dados":
            result = generate_data_dictionary(cursor, connection_id)
        elif doc_type == "mapa_processos":
            result = generate_process_map(cursor, module)
        elif doc_type == "guia_erros":
            result = generate_error_guide(cursor, category)
        elif doc_type == "combinado":
            result = generate_combined(cursor, connection_id, module, category)
        else:
            return jsonify({"error": "Tipo invalido"}), 400

        doc = save_document(cursor, title, doc_type, result["content_md"], result.get("metadata", {}), user_id)
        conn.commit()

        return (
            jsonify(
                {
                    "success": True,
                    "id": doc["id"],
                    "version": doc["version"],
                    "file_size": doc["file_size"],
                    "message": f"Documento gerado com sucesso (v{doc['version']})",
                }
            ),
            201,
        )
    except ValueError as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        conn.rollback()
        return jsonify({"error": f"Erro ao gerar documento: {str(e)}"}), 500
    finally:
        release_db_connection(conn)


# =========================================================
# DOWNLOAD
# =========================================================


@documentation_bp.route("/api/docs/<int:doc_id>/download", methods=["GET"])
@require_auth
def download_doc(doc_id):
    """Download do documento como arquivo .md."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        doc = get_document(cursor, doc_id)
        if not doc:
            return jsonify({"error": "Documento nao encontrado"}), 404

        safe_name = re.sub(r"[^\w\s-]", "", doc["title"]).strip().replace(" ", "_")
        if not safe_name:
            safe_name = f"doc_{doc_id}"
        filename = f"{safe_name}_v{doc['version']}.md"

        response = make_response(doc["content_md"])
        response.headers["Content-Type"] = "text/markdown; charset=utf-8"
        response.headers["Content-Disposition"] = f"attachment; filename={filename}"
        return response
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        release_db_connection(conn)


# =========================================================
# VERSOES
# =========================================================


@documentation_bp.route("/api/docs/<int:doc_id>/versions", methods=["GET"])
@require_auth
def list_versions(doc_id):
    """Lista versoes anteriores de um documento."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        versions = get_document_versions(cursor, doc_id)
        return jsonify({"versions": versions}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        release_db_connection(conn)


# =========================================================
# EXCLUSAO
# =========================================================


@documentation_bp.route("/api/docs/<int:doc_id>", methods=["DELETE"])
@require_admin
def remove_doc(doc_id):
    """Remove documento."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        deleted = delete_document(cursor, doc_id)
        if not deleted:
            return jsonify({"error": "Documento nao encontrado"}), 404
        conn.commit()
        return jsonify({"success": True, "message": "Documento removido"}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        release_db_connection(conn)


# =========================================================
# AUXILIARES (dropdowns para o frontend)
# =========================================================


@documentation_bp.route("/api/docs/connections", methods=["GET"])
@require_auth
def list_doc_connections():
    """Lista conexoes de banco disponiveis para geracao de dicionario."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, name, driver, host, database_name FROM database_connections ORDER BY name")
        connections = [dict(row) for row in cursor.fetchall()]
        return jsonify(connections), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        release_db_connection(conn)


@documentation_bp.route("/api/docs/categories", methods=["GET"])
@require_auth
def list_doc_categories():
    """Lista categorias de erros disponiveis para o guia."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT DISTINCT category, COUNT(*) as count
            FROM knowledge_articles
            WHERE is_active = TRUE
            GROUP BY category
            ORDER BY category
            """)
        categories = [dict(row) for row in cursor.fetchall()]
        return jsonify(categories), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        release_db_connection(conn)
