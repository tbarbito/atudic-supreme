"""
Rotas de Integração com Banco de Dados do Protheus.

CRUD de conexões, navegação de schema, execução de queries read-only.
"""

from datetime import datetime
from flask import Blueprint, request, jsonify, make_response
from app.database import get_db, release_db_connection
from app.utils.security import require_admin
from app.utils import crypto

database_bp = Blueprint("database", __name__)


# =========================================================
# CONEXÕES COM BANCOS DE DADOS
# =========================================================


@database_bp.route("/api/db-connections", methods=["GET"])
@require_admin
def list_connections():
    """Lista conexões de banco de dados configuradas."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        environment_id = request.args.get("environment_id")
        conditions = []
        params = []

        if environment_id:
            conditions.append("dc.environment_id = %s")
            params.append(environment_id)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        cursor.execute(
            f"""
            SELECT dc.id, dc.environment_id, dc.name, dc.driver, dc.host,
                   dc.port, dc.database_name, dc.username, dc.is_active,
                   dc.is_readonly, dc.last_connected_at, dc.last_error,
                   dc.created_at, dc.updated_at,
                   dc.ref_environment_id, dc.connection_role, dc.rest_url,
                   e.name as environment_name,
                   re.name as ref_environment_name,
                   u.username as created_by_name
            FROM database_connections dc
            LEFT JOIN environments e ON dc.environment_id = e.id
            LEFT JOIN environments re ON dc.ref_environment_id = re.id
            LEFT JOIN users u ON dc.created_by = u.id
            {where}
            ORDER BY dc.name
            """,
            params,
        )

        connections = []
        for row in cursor.fetchall():
            item = dict(row)
            for key in ("last_connected_at", "created_at", "updated_at"):
                if item.get(key):
                    item[key] = item[key].isoformat()
            connections.append(item)

        return jsonify(connections), 200
    finally:
        release_db_connection(conn)


@database_bp.route("/api/db-connections", methods=["POST"])
@require_admin
def create_connection():
    """Cria uma nova conexão com banco de dados externo."""
    data = request.get_json()
    required = ["name", "driver", "host", "database_name", "username", "password"]
    for field in required:
        if not data.get(field):
            return jsonify({"error": f"Campo obrigatório: {field}"}), 400

    from app.services.database_browser import SUPPORTED_DRIVERS
    if data["driver"] not in SUPPORTED_DRIVERS:
        drivers = ", ".join(SUPPORTED_DRIVERS.keys())
        return jsonify({"error": f"Driver inválido. Suportados: {drivers}"}), 400

    # Criptografar senha
    if not crypto.token_encryption:
        return jsonify({"error": "Sistema de criptografia não inicializado"}), 500

    encrypted_pwd = crypto.token_encryption.encrypt_token(data["password"])
    default_port = SUPPORTED_DRIVERS[data["driver"]]["port"]

    conn = get_db()
    cursor = conn.cursor()
    try:
        # ref_environment_id: se nao informado, usa o environment_id (conexao principal)
        ref_env_id = data.get("ref_environment_id", data.get("environment_id"))

        cursor.execute(
            """
            INSERT INTO database_connections
                (environment_id, name, driver, host, port, database_name,
                 username, password_encrypted, extra_params, is_readonly,
                 ref_environment_id, connection_role, rest_url,
                 created_by, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                data.get("environment_id"),
                data["name"],
                data["driver"],
                data["host"],
                data.get("port", default_port),
                data["database_name"],
                data["username"],
                encrypted_pwd,
                data.get("extra_params", ""),
                data.get("is_readonly", True),
                ref_env_id,
                data.get("connection_role", "Protheus"),
                data.get("rest_url", ""),
                request.current_user["id"],
                datetime.now(),
            ),
        )
        new_id = cursor.fetchone()["id"]
        conn.commit()
        return jsonify({"id": new_id, "message": "Conexão criada com sucesso"}), 201
    except Exception as e:
        conn.rollback()
        if "idx_dbconn_unique" in str(e) or "already exists" in str(e):
            return jsonify({"error": "Já existe uma conexão com este servidor e banco de dados neste ambiente."}), 409
        return jsonify({"error": str(e)}), 500
    finally:
        release_db_connection(conn)


@database_bp.route("/api/db-connections/<int:conn_id>", methods=["PUT"])
@require_admin
def update_connection(conn_id):
    """Atualiza uma conexão existente."""
    data = request.get_json()
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM database_connections WHERE id = %s", (conn_id,))
        if not cursor.fetchone():
            return jsonify({"error": "Conexão não encontrada"}), 404

        fields = []
        values = []
        updatable = [
            "name", "driver", "host", "port", "database_name",
            "username", "extra_params", "is_active", "is_readonly",
            "environment_id", "ref_environment_id", "connection_role",
            "rest_url",
        ]
        for field in updatable:
            if field in data:
                fields.append(f"{field} = %s")
                values.append(data[field])

        # Se senha foi enviada, criptografar
        if data.get("password"):
            if not crypto.token_encryption:
                return jsonify({"error": "Sistema de criptografia não inicializado"}), 500
            fields.append("password_encrypted = %s")
            values.append(crypto.token_encryption.encrypt_token(data["password"]))

        if not fields:
            return jsonify({"error": "Nenhum campo para atualizar"}), 400

        fields.append("updated_at = %s")
        values.append(datetime.now())
        values.append(conn_id)

        cursor.execute(
            f"UPDATE database_connections SET {', '.join(fields)} WHERE id = %s",
            values,
        )
        conn.commit()
        return jsonify({"message": "Conexão atualizada com sucesso"}), 200
    except Exception as e:
        conn.rollback()
        if "idx_dbconn_unique" in str(e) or "already exists" in str(e):
            return jsonify({"error": "Já existe uma conexão com este servidor e banco de dados neste ambiente."}), 409
        return jsonify({"error": str(e)}), 500
    finally:
        release_db_connection(conn)


@database_bp.route("/api/db-connections/<int:conn_id>", methods=["DELETE"])
@require_admin
def delete_connection(conn_id):
    """Remove uma conexão de banco de dados."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM database_connections WHERE id = %s", (conn_id,))
        if not cursor.fetchone():
            return jsonify({"error": "Conexão não encontrada"}), 404
        cursor.execute("DELETE FROM database_connections WHERE id = %s", (conn_id,))
        conn.commit()
        return jsonify({"message": "Conexão removida com sucesso"}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        release_db_connection(conn)


# =========================================================
# TESTE DE CONEXÃO
# =========================================================


@database_bp.route("/api/db-connections/<int:conn_id>/test", methods=["POST"])
@require_admin
def test_connection(conn_id):
    """Testa conexão com banco de dados externo."""
    from app.services.database_browser import test_connection as _test

    ok, message, latency = _test(conn_id)
    payload = {
        "success": ok,
        "message": message,
        "latency_ms": latency,
    }
    if not ok:
        payload["error"] = message
    return jsonify(payload), 200 if ok else 400


# =========================================================
# NAVEGAÇÃO DE SCHEMA (TABELAS E CAMPOS)
# =========================================================


@database_bp.route("/api/db-connections/<int:conn_id>/discover", methods=["POST"])
@require_admin
def discover_schema(conn_id):
    """Descobre estrutura do banco e cacheia tabelas/campos."""
    from app.services.database_browser import discover_tables

    try:
        tables = discover_tables(conn_id)
        return jsonify({
            "message": f"{len(tables)} tabela(s) descoberta(s)",
            "table_count": len(tables),
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@database_bp.route("/api/db-connections/<int:conn_id>/tables", methods=["GET"])
@require_admin
def list_tables(conn_id):
    """Lista tabelas cacheadas de uma conexão."""
    from app.services.database_browser import get_cached_tables

    search = request.args.get("search", "")
    tables = get_cached_tables(conn_id, search=search if search else None)
    return jsonify(tables), 200


@database_bp.route("/api/db-connections/<int:conn_id>/tables/<table_name>/columns", methods=["GET"])
@require_admin
def list_columns(conn_id, table_name):
    """Lista colunas de uma tabela cacheada."""
    from app.services.database_browser import get_cached_columns

    columns = get_cached_columns(conn_id, table_name)
    if not columns:
        return jsonify({"error": "Tabela não encontrada no cache. Execute /discover primeiro."}), 404
    return jsonify(columns), 200


@database_bp.route("/api/db-connections/<int:conn_id>/tables/<table_name>/details", methods=["GET"])
@require_admin
def table_details(conn_id, table_name):
    """Retorna detalhes da tabela: indexes, triggers, constraints."""
    from app.services.database_browser import get_table_details

    try:
        result = get_table_details(conn_id, table_name)
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@database_bp.route("/api/db-connections/<int:conn_id>/tables/<table_name>/sample", methods=["GET"])
@require_admin
def table_sample(conn_id, table_name):
    """Retorna amostra de dados da tabela (SELECT * LIMIT N)."""
    from app.services.database_browser import get_table_sample

    limit = min(int(request.args.get("limit", 50)), 500)
    try:
        result = get_table_sample(conn_id, table_name, limit=limit)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =========================================================
# EXECUÇÃO DE QUERIES
# =========================================================


@database_bp.route("/api/db-connections/<int:conn_id>/query", methods=["POST"])
@require_admin
def execute_query(conn_id):
    """Executa query SELECT no banco externo."""
    from app.services.database_browser import execute_query as _exec

    data = request.get_json()
    query_text = data.get("query", "").strip()
    if not query_text:
        return jsonify({"error": "Query não pode ser vazia"}), 400

    max_rows = min(int(data.get("max_rows", 500)), 1000)

    try:
        result = _exec(conn_id, query_text, user_id=request.current_user["id"], max_rows=max_rows)
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@database_bp.route("/api/db-connections/<int:conn_id>/query/csv", methods=["POST"])
@require_admin
def export_query_csv(conn_id):
    """Executa query SELECT e retorna CSV sem limite de linhas."""
    import csv
    import io
    from app.services.database_browser import execute_query as _exec

    data = request.get_json()
    query_text = data.get("query", "").strip()
    if not query_text:
        return jsonify({"error": "Query não pode ser vazia"}), 400

    try:
        result = _exec(conn_id, query_text, user_id=request.current_user["id"], max_rows=999999)
        columns = result.get("columns", [])
        rows = result.get("rows", [])

        output = io.StringIO()
        output.write("\ufeff")  # BOM UTF-8 para Excel
        writer = csv.writer(output, delimiter=";", quoting=csv.QUOTE_MINIMAL)
        writer.writerow(columns)
        for row in rows:
            writer.writerow([row.get(c, "") for c in columns])

        response = make_response(output.getvalue())
        response.headers["Content-Type"] = "text/csv; charset=utf-8"
        response.headers["Content-Disposition"] = "attachment; filename=query_export.csv"
        return response
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@database_bp.route("/api/db-connections/<int:conn_id>/history", methods=["GET"])
@require_admin
def query_history(conn_id):
    """Retorna histórico de queries executadas."""
    from app.services.database_browser import get_query_history

    limit = min(int(request.args.get("limit", 50)), 200)
    history = get_query_history(conn_id, limit=limit)
    return jsonify(history), 200


# =========================================================
# DRIVERS DISPONÍVEIS
# =========================================================


@database_bp.route("/api/db-drivers", methods=["GET"])
@require_admin
def list_drivers():
    """Lista drivers de banco de dados suportados."""
    from app.services.database_browser import SUPPORTED_DRIVERS

    drivers = []
    for key, info in SUPPORTED_DRIVERS.items():
        drivers.append({
            "id": key,
            "label": info["label"],
            "default_port": info["port"],
            "module": info["module"],
        })
    return jsonify(drivers), 200
