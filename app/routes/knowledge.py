"""
Rotas da Base de Conhecimento, Histórico de Correções,
Análise Inteligente de Logs e Regras de Notificação.
"""

from datetime import datetime
from flask import Blueprint, request, jsonify
from app.database import get_db, release_db_connection
from app.utils.security import require_auth, require_operator, require_admin

knowledge_bp = Blueprint("knowledge", __name__)


# =========================================================
# BASE DE CONHECIMENTO
# =========================================================


@knowledge_bp.route("/api/knowledge", methods=["GET"])
@require_auth
def list_articles():
    """Lista artigos da base de conhecimento com busca e filtros."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        query = request.args.get("q", "")
        category = request.args.get("category", "")
        source = request.args.get("source", "")
        limit = min(int(request.args.get("limit", 50)), 200)
        offset = int(request.args.get("offset", 0))

        conditions = ["is_active = TRUE"]
        params = []

        if query:
            conditions.append("""
                (title ILIKE %s OR description ILIKE %s
                 OR solution ILIKE %s OR tags ILIKE %s
                 OR causes ILIKE %s)
            """)
            like = f"%{query}%"
            params.extend([like, like, like, like, like])

        if category:
            conditions.append("category = %s")
            params.append(category)

        if source:
            conditions.append("source = %s")
            params.append(source)

        where = " AND ".join(conditions)

        cursor.execute(f"SELECT COUNT(*) as total FROM knowledge_articles WHERE {where}", params)
        total = cursor.fetchone()["total"]

        cursor.execute(
            f"""
            SELECT * FROM knowledge_articles
            WHERE {where}
            ORDER BY usage_count DESC, created_at DESC
            LIMIT %s OFFSET %s
        """,
            params + [limit, offset],
        )

        articles = []
        for row in cursor.fetchall():
            article = dict(row)
            for key in ("created_at", "updated_at"):
                if article.get(key):
                    article[key] = article[key].isoformat()
            articles.append(article)

        return (
            jsonify(
                {
                    "articles": articles,
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                }
            ),
            200,
        )
    finally:
        release_db_connection(conn)


@knowledge_bp.route("/api/knowledge/<int:article_id>", methods=["GET"])
@require_auth
def get_article(article_id):
    """Retorna um artigo específico e incrementa uso."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM knowledge_articles WHERE id = %s", (article_id,))
        article = cursor.fetchone()
        if not article:
            return jsonify({"error": "Artigo não encontrado"}), 404

        # Incrementar uso
        cursor.execute("UPDATE knowledge_articles SET usage_count = usage_count + 1 WHERE id = %s", (article_id,))
        conn.commit()

        result = dict(article)
        for key in ("created_at", "updated_at"):
            if result.get(key):
                result[key] = result[key].isoformat()
        return jsonify(result), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        release_db_connection(conn)


@knowledge_bp.route("/api/knowledge", methods=["POST"])
@require_operator
def create_article():
    """Cria um novo artigo na base de conhecimento."""
    data = request.get_json()
    if not data.get("title") or not data.get("category"):
        return jsonify({"error": "Título e categoria são obrigatórios"}), 400

    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO knowledge_articles
                (title, category, error_pattern, description, causes,
                 solution, code_snippet, reference_url, tags, source,
                 created_by, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """,
            (
                data["title"],
                data["category"],
                data.get("error_pattern", ""),
                data.get("description", ""),
                data.get("causes", ""),
                data.get("solution", ""),
                data.get("code_snippet", ""),
                data.get("reference_url", ""),
                data.get("tags", data["category"]),
                data.get("source", "manual"),
                request.current_user["id"],
                datetime.now(),
            ),
        )
        new_id = cursor.fetchone()["id"]
        conn.commit()
        return jsonify({"id": new_id, "message": "Artigo criado com sucesso"}), 201
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        release_db_connection(conn)


@knowledge_bp.route("/api/knowledge/<int:article_id>", methods=["PUT"])
@require_operator
def update_article(article_id):
    """Atualiza um artigo existente."""
    data = request.get_json()
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM knowledge_articles WHERE id = %s", (article_id,))
        if not cursor.fetchone():
            return jsonify({"error": "Artigo não encontrado"}), 404

        fields = []
        values = []
        updatable = [
            "title",
            "category",
            "error_pattern",
            "description",
            "causes",
            "solution",
            "code_snippet",
            "reference_url",
            "tags",
            "is_active",
        ]
        for field in updatable:
            if field in data:
                fields.append(f"{field} = %s")
                values.append(data[field])

        if not fields:
            return jsonify({"error": "Nenhum campo para atualizar"}), 400

        fields.append("updated_at = %s")
        values.append(datetime.now())
        values.append(article_id)

        cursor.execute(f"UPDATE knowledge_articles SET {', '.join(fields)} WHERE id = %s", values)
        conn.commit()
        return jsonify({"message": "Artigo atualizado com sucesso"}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        release_db_connection(conn)


@knowledge_bp.route("/api/knowledge/<int:article_id>", methods=["DELETE"])
@require_admin
def delete_article(article_id):
    """Remove um artigo da base de conhecimento."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM knowledge_articles WHERE id = %s", (article_id,))
        if not cursor.fetchone():
            return jsonify({"error": "Artigo não encontrado"}), 404
        cursor.execute("DELETE FROM knowledge_articles WHERE id = %s", (article_id,))
        conn.commit()
        return jsonify({"message": "Artigo removido com sucesso"}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        release_db_connection(conn)


@knowledge_bp.route("/api/knowledge/import", methods=["POST"])
@require_admin
def import_knowledge_base():
    """Importa artigos do arquivo erros_protheus.md (upload ou busca local)."""
    from flask import current_app
    from app.services.knowledge_base import seed_knowledge_base
    import os
    import tempfile

    # Opção 1: Upload de arquivo pelo browser
    if "file" in request.files:
        uploaded = request.files["file"]
        if not uploaded.filename:
            return jsonify({"error": "Nenhum arquivo selecionado"}), 400
        if not uploaded.filename.endswith(".md"):
            return jsonify({"error": "Apenas arquivos .md são aceitos"}), 400

        try:
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".md", mode="wb")
            uploaded.save(tmp)
            tmp.close()
            imported = seed_knowledge_base(tmp.name)
            os.unlink(tmp.name)
            return jsonify({
                "message": f"{imported} artigo(s) importado(s) com sucesso",
                "imported": imported,
            }), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # Opção 2: Fallback - busca local no servidor
    project_root = current_app.root_path
    possible_paths = [
        os.path.join(project_root, "..", ".claude", "erros_protheus.md"),
        os.path.join(project_root, ".claude", "erros_protheus.md"),
        os.path.join(os.path.expanduser("~"), "projetos", ".claude", "erros_protheus.md"),
    ]

    filepath = None
    for p in possible_paths:
        normalized = os.path.normpath(p)
        if os.path.exists(normalized):
            filepath = normalized
            break

    if not filepath:
        return jsonify({"error": "Envie o arquivo erros_protheus.md via upload"}), 400

    try:
        imported = seed_knowledge_base(filepath)
        return jsonify({
            "message": f"{imported} artigo(s) importado(s) com sucesso",
            "imported": imported,
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@knowledge_bp.route("/api/knowledge/categories", methods=["GET"])
@require_auth
def list_categories():
    """Lista categorias distintas da base de conhecimento."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT category, COUNT(*) as count
            FROM knowledge_articles
            WHERE is_active = TRUE
            GROUP BY category
            ORDER BY count DESC
        """)
        categories = [dict(row) for row in cursor.fetchall()]
        return jsonify(categories), 200
    finally:
        release_db_connection(conn)


# =========================================================
# ANÁLISE INTELIGENTE DE LOGS
# =========================================================


@knowledge_bp.route("/api/analysis/recurring", methods=["GET"])
@require_auth
def get_recurring():
    """Retorna erros recorrentes agrupados por padrão."""
    from app.services.knowledge_base import get_recurring_errors

    environment_id = request.args.get("environment_id")
    min_count = int(request.args.get("min_count", 3))
    days = int(request.args.get("days", 7))
    limit = min(int(request.args.get("limit", 20)), 100)

    errors = get_recurring_errors(
        environment_id=environment_id,
        min_count=min_count,
        days=days,
        limit=limit,
    )

    for err in errors:
        for key in ("first_seen_at", "last_seen_at"):
            if err.get(key):
                err[key] = err[key].isoformat()

    return jsonify(errors), 200


@knowledge_bp.route("/api/analysis/overview", methods=["GET"])
@require_auth
def get_analysis_overview():
    """Retorna análise inteligente de erros com tendências."""
    from app.services.knowledge_base import get_error_analysis

    environment_id = request.args.get("environment_id")
    days = int(request.args.get("days", 7))

    analysis = get_error_analysis(environment_id=environment_id, days=days)
    return jsonify(analysis), 200


@knowledge_bp.route("/api/analysis/suggest/<int:alert_id>", methods=["GET"])
@require_auth
def suggest_for_alert(alert_id):
    """Sugere artigos da base de conhecimento para um alerta específico."""
    from app.services.knowledge_base import find_matching_article, increment_article_usage

    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT category, message, raw_line FROM log_alerts WHERE id = %s", (alert_id,))
        alert = cursor.fetchone()
        if not alert:
            return jsonify({"error": "Alerta não encontrado"}), 404

        article = find_matching_article(alert["category"], alert["message"])
        if article:
            increment_article_usage(article["id"])
            return (
                jsonify(
                    {
                        "found": True,
                        "article": article,
                    }
                ),
                200,
            )

        return jsonify({"found": False, "article": None}), 200
    finally:
        release_db_connection(conn)


# =========================================================
# HISTÓRICO DE CORREÇÕES
# =========================================================


@knowledge_bp.route("/api/corrections", methods=["GET"])
@require_auth
def list_corrections():
    """Lista histórico de correções aplicadas."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        environment_id = request.args.get("environment_id")
        category = request.args.get("category")
        limit = min(int(request.args.get("limit", 50)), 200)
        offset = int(request.args.get("offset", 0))

        conditions = []
        params = []

        if environment_id:
            conditions.append("ch.environment_id = %s")
            params.append(environment_id)

        if category:
            conditions.append("ch.error_category = %s")
            params.append(category)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        cursor.execute(f"SELECT COUNT(*) as total FROM correction_history ch {where}", params)
        total = cursor.fetchone()["total"]

        cursor.execute(
            f"""
            SELECT ch.*, e.name as environment_name,
                   ka.title as article_title,
                   u.username as applied_by_username,
                   v.username as validated_by_username
            FROM correction_history ch
            LEFT JOIN environments e ON ch.environment_id = e.id
            LEFT JOIN knowledge_articles ka ON ch.article_id = ka.id
            LEFT JOIN users u ON ch.applied_by = u.id
            LEFT JOIN users v ON ch.validated_by = v.id
            {where}
            ORDER BY ch.applied_at DESC
            LIMIT %s OFFSET %s
        """,
            params + [limit, offset],
        )

        corrections = []
        for row in cursor.fetchall():
            item = dict(row)
            for key in ("applied_at", "validated_at"):
                if item.get(key):
                    item[key] = item[key].isoformat()
            corrections.append(item)

        return (
            jsonify(
                {
                    "corrections": corrections,
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                }
            ),
            200,
        )
    finally:
        release_db_connection(conn)


@knowledge_bp.route("/api/corrections", methods=["POST"])
@require_operator
def create_correction():
    """Registra uma nova correção no histórico."""
    data = request.get_json()
    required = ["error_category", "error_message", "correction_applied"]
    for field in required:
        if not data.get(field):
            return jsonify({"error": f"Campo obrigatório: {field}"}), 400

    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO correction_history
                (environment_id, alert_id, article_id, error_category,
                 error_message, source_file, correction_applied,
                 lesson_learned, status, applied_by, applied_at, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """,
            (
                data.get("environment_id"),
                data.get("alert_id"),
                data.get("article_id"),
                data["error_category"],
                data["error_message"],
                data.get("source_file", ""),
                data["correction_applied"],
                data.get("lesson_learned", ""),
                data.get("status", "applied"),
                request.current_user["id"],
                datetime.now(),
                data.get("notes", ""),
            ),
        )
        new_id = cursor.fetchone()["id"]
        conn.commit()
        return jsonify({"id": new_id, "message": "Correção registrada com sucesso"}), 201
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        release_db_connection(conn)


@knowledge_bp.route("/api/corrections/<int:correction_id>/validate", methods=["POST"])
@require_operator
def validate_correction(correction_id):
    """Marca uma correção como validada."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM correction_history WHERE id = %s", (correction_id,))
        if not cursor.fetchone():
            return jsonify({"error": "Correção não encontrada"}), 404

        cursor.execute(
            """
            UPDATE correction_history
            SET validated_at = %s, validated_by = %s, status = 'validated'
            WHERE id = %s
        """,
            (datetime.now(), request.current_user["id"], correction_id),
        )
        conn.commit()
        return jsonify({"message": "Correção validada com sucesso"}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        release_db_connection(conn)


# =========================================================
# REGRAS DE NOTIFICAÇÃO INTELIGENTE
# =========================================================


@knowledge_bp.route("/api/notification-rules", methods=["GET"])
@require_operator
def list_notification_rules():
    """Lista regras de notificação configuradas."""
    from app.services.smart_notifications import get_notification_stats

    environment_id = request.args.get("environment_id")
    rules = get_notification_stats(environment_id=environment_id)
    return jsonify(rules), 200


@knowledge_bp.route("/api/notification-rules", methods=["POST"])
@require_operator
def create_notification_rule():
    """Cria uma nova regra de notificação."""
    data = request.get_json()
    if not data.get("name") or not data.get("severity"):
        return jsonify({"error": "Nome e severidade são obrigatórios"}), 400

    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO notification_rules
                (name, environment_id, severity, category,
                 min_occurrences, time_window_minutes, cooldown_minutes,
                 notify_email, notify_whatsapp, notify_webhook,
                 recipients, is_active, created_by, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """,
            (
                data["name"],
                data.get("environment_id"),
                data["severity"],
                data.get("category", ""),
                data.get("min_occurrences", 1),
                data.get("time_window_minutes", 5),
                data.get("cooldown_minutes", 30),
                data.get("notify_email", True),
                data.get("notify_whatsapp", False),
                data.get("notify_webhook", False),
                data.get("recipients", ""),
                data.get("is_active", True),
                request.current_user["id"],
                datetime.now(),
            ),
        )
        new_id = cursor.fetchone()["id"]
        conn.commit()
        return jsonify({"id": new_id, "message": "Regra criada com sucesso"}), 201
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        release_db_connection(conn)


@knowledge_bp.route("/api/notification-rules/<int:rule_id>", methods=["PUT"])
@require_operator
def update_notification_rule(rule_id):
    """Atualiza uma regra de notificação."""
    data = request.get_json()
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM notification_rules WHERE id = %s", (rule_id,))
        if not cursor.fetchone():
            return jsonify({"error": "Regra não encontrada"}), 404

        fields = []
        values = []
        updatable = [
            "name",
            "environment_id",
            "severity",
            "category",
            "min_occurrences",
            "time_window_minutes",
            "cooldown_minutes",
            "notify_email",
            "notify_whatsapp",
            "notify_webhook",
            "recipients",
            "is_active",
        ]
        for field in updatable:
            if field in data:
                fields.append(f"{field} = %s")
                values.append(data[field])

        if not fields:
            return jsonify({"error": "Nenhum campo para atualizar"}), 400

        fields.append("updated_at = %s")
        values.append(datetime.now())
        values.append(rule_id)

        cursor.execute(f"UPDATE notification_rules SET {', '.join(fields)} WHERE id = %s", values)
        conn.commit()
        return jsonify({"message": "Regra atualizada com sucesso"}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        release_db_connection(conn)


@knowledge_bp.route("/api/notification-rules/<int:rule_id>", methods=["DELETE"])
@require_admin
def delete_notification_rule(rule_id):
    """Remove uma regra de notificação."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM notification_rules WHERE id = %s", (rule_id,))
        if not cursor.fetchone():
            return jsonify({"error": "Regra não encontrada"}), 404
        cursor.execute("DELETE FROM notification_rules WHERE id = %s", (rule_id,))
        conn.commit()
        return jsonify({"message": "Regra removida com sucesso"}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        release_db_connection(conn)
