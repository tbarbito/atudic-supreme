"""
Rotas do Módulo de Processos da Empresa.

CRUD de processos de negócio, tabelas vinculadas, campos e fluxos.
Acesso restrito a administradores.
"""

from datetime import datetime
from flask import Blueprint, request, jsonify
from app.database import get_db, release_db_connection
from app.utils.security import require_admin
from app.services.process_mapper import get_protheus_modules, seed_default_processes, auto_map_fields

processes_bp = Blueprint("processes", __name__)


# =========================================================
# MÓDULOS PROTHEUS (auxiliar)
# =========================================================


@processes_bp.route("/api/protheus-modules", methods=["GET"])
@require_admin
def list_protheus_modules():
    """Lista módulos padrão do Protheus para dropdown."""
    return jsonify(get_protheus_modules()), 200


@processes_bp.route("/api/processes/sx2-lookup", methods=["GET"])
@require_admin
def sx2_lookup():
    """Busca descricao de uma tabela na SX2 do banco Protheus externo."""
    conn_id = request.args.get("connection_id", type=int)
    alias = request.args.get("alias", "").strip().upper()
    if not conn_id or not alias:
        return jsonify({"description": ""}), 200

    # Sanitizar alias: apenas letras e numeros (padrao Protheus: SA1, SC7, ZZ4)
    import re as _re
    if not _re.match(r'^[A-Z0-9]{2,6}$', alias):
        return jsonify({"description": ""}), 200

    from app.services.database_browser import execute_query
    from app.services.dictionary_compare import _make_table_name
    import logging
    logger = logging.getLogger(__name__)

    try:
        # Regra Protheus: nome fisico = {PREFIX}{M0_CODIGO}0
        # Descobrir M0_CODIGO a partir do sufixo da tabela no schema_cache
        company_code = None
        conn = get_db()
        cursor = conn.cursor()
        try:
            # Buscar nome fisico da tabela selecionada no cache (ex: SC7990)
            cursor.execute(
                "SELECT DISTINCT table_name FROM schema_cache WHERE connection_id = %s AND table_name ILIKE %s",
                (conn_id, f"{alias}%"),
            )
            matched = [row["table_name"] for row in cursor.fetchall()]
            if matched:
                full_name = matched[0]  # Ex: SC7990
                if len(full_name) > len(alias):
                    suffix = full_name[len(alias):]  # Ex: 990
                    # Sufixo Protheus = M0_CODIGO + '0', entao M0_CODIGO = sufixo sem ultimo char
                    if len(suffix) >= 2:
                        company_code = suffix[:-1]  # 990 -> 99, 010 -> 01
                        logger.info("SX2 lookup: company_code=%s (de %s)", company_code, full_name)
        finally:
            release_db_connection(conn)

        if not company_code:
            logger.warning("SX2 lookup: company_code nao detectado para alias=%s conn_id=%s", alias, conn_id)
            return jsonify({"description": ""}), 200

        # Montar nome da SX2 usando mesma regra: SX2 + M0_CODIGO + 0
        sx2_name = _make_table_name("SX2", company_code)
        logger.info("SX2 lookup: buscando %s em %s", alias, sx2_name)

        result = execute_query(
            conn_id,
            f"SELECT X2_NOME FROM {sx2_name} WHERE X2_CHAVE = '{alias}' AND D_E_L_E_T_ = ' '",
            max_rows=1,
        )
        rows = result.get("rows", [])
        if rows and len(rows) > 0:
            row = rows[0]
            # Campo pode vir em qualquer case dependendo do driver
            desc = ""
            for key in row:
                if key.upper() == "X2_NOME":
                    desc = str(row[key] or "").strip()
                    break
            logger.info("SX2 lookup: %s = '%s'", alias, desc)
            return jsonify({"description": desc}), 200

        logger.info("SX2 lookup: %s nao encontrado na %s", alias, sx2_name)
        return jsonify({"description": ""}), 200
    except Exception as e:
        logger.error("SX2 lookup erro: %s", e)
        return jsonify({"description": "", "error": str(e)}), 200


# =========================================================
# SEED DE PROCESSOS PADRÃO
# =========================================================


@processes_bp.route("/api/processes/seed", methods=["POST"])
@require_admin
def run_seed():
    """Popula processos padrão do Protheus."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        user_id = request.current_user.get("id") if hasattr(request, "current_user") else None
        inserted = seed_default_processes(cursor, user_id)
        conn.commit()
        return jsonify({"success": True, "message": f"{inserted} processos inseridos", "count": inserted}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        release_db_connection(conn)


# =========================================================
# CRUD DE PROCESSOS
# =========================================================


@processes_bp.route("/api/processes", methods=["GET"])
@require_admin
def list_processes():
    """Lista processos com filtros opcionais."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        module = request.args.get("module")
        status = request.args.get("status")
        search = request.args.get("search")

        conditions = []
        params = []

        if module:
            conditions.append("bp.module = %s")
            params.append(module)
        if status:
            conditions.append("bp.status = %s")
            params.append(status)
        if search:
            conditions.append("(bp.name ILIKE %s OR bp.description ILIKE %s)")
            params.extend([f"%{search}%", f"%{search}%"])

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        cursor.execute(
            f"""
            SELECT bp.*,
                   u.username as created_by_name,
                   (SELECT COUNT(*) FROM process_tables pt WHERE pt.process_id = bp.id) as table_count,
                   (SELECT COUNT(*) FROM process_flows pf
                    WHERE pf.source_process_id = bp.id OR pf.target_process_id = bp.id) as flow_count
            FROM business_processes bp
            LEFT JOIN users u ON bp.created_by = u.id
            {where}
            ORDER BY bp.module, bp.name
            """,
            params,
        )

        processes = []
        for row in cursor.fetchall():
            item = dict(row)
            for key in ("created_at", "updated_at"):
                if item.get(key):
                    item[key] = item[key].isoformat()
            processes.append(item)

        return jsonify(processes), 200
    finally:
        release_db_connection(conn)


@processes_bp.route("/api/processes", methods=["POST"])
@require_admin
def create_process():
    """Cria um novo processo."""
    data = request.get_json()
    if not data or not data.get("name") or not data.get("module"):
        return jsonify({"error": "Nome e módulo são obrigatórios"}), 400

    conn = get_db()
    cursor = conn.cursor()
    try:
        user_id = request.current_user.get("id") if hasattr(request, "current_user") else None
        cursor.execute(
            """
            INSERT INTO business_processes (name, description, module, module_label, icon, color, status, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                data["name"], data.get("description", ""), data["module"],
                data.get("module_label", ""), data.get("icon", "fa-cogs"),
                data.get("color", "#007bff"), data.get("status", "active"), user_id,
            ),
        )
        process_id = cursor.fetchone()["id"]
        conn.commit()
        return jsonify({"success": True, "id": process_id}), 201
    except Exception as e:
        conn.rollback()
        if "unique" in str(e).lower():
            return jsonify({"error": "Já existe um processo com este nome"}), 409
        return jsonify({"error": str(e)}), 500
    finally:
        release_db_connection(conn)


@processes_bp.route("/api/processes/<int:process_id>", methods=["GET"])
@require_admin
def get_process(process_id):
    """Retorna detalhes do processo com tabelas, campos e fluxos."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        # Processo
        cursor.execute(
            """
            SELECT bp.*, u.username as created_by_name
            FROM business_processes bp
            LEFT JOIN users u ON bp.created_by = u.id
            WHERE bp.id = %s
            """,
            (process_id,),
        )
        proc = cursor.fetchone()
        if not proc:
            return jsonify({"error": "Processo não encontrado"}), 404

        result = dict(proc)
        for key in ("created_at", "updated_at"):
            if result.get(key):
                result[key] = result[key].isoformat()

        # Tabelas vinculadas
        cursor.execute(
            """
            SELECT pt.*, dc.name as connection_name
            FROM process_tables pt
            LEFT JOIN database_connections dc ON pt.connection_id = dc.id
            WHERE pt.process_id = %s
            ORDER BY pt.sort_order, pt.table_name
            """,
            (process_id,),
        )
        tables = []
        for tbl_row in cursor.fetchall():
            tbl = dict(tbl_row)
            if tbl.get("created_at"):
                tbl["created_at"] = tbl["created_at"].isoformat()

            # Campos de cada tabela
            cursor.execute(
                """
                SELECT * FROM process_fields
                WHERE process_table_id = %s
                ORDER BY sort_order, column_name
                """,
                (tbl["id"],),
            )
            tbl["fields"] = []
            for fld_row in cursor.fetchall():
                fld = dict(fld_row)
                if fld.get("created_at"):
                    fld["created_at"] = fld["created_at"].isoformat()
                tbl["fields"].append(fld)

            tables.append(tbl)

        result["tables"] = tables

        # Fluxos
        cursor.execute(
            """
            SELECT pf.*,
                   src.name as source_name, src.icon as source_icon, src.color as source_color,
                   tgt.name as target_name, tgt.icon as target_icon, tgt.color as target_color
            FROM process_flows pf
            JOIN business_processes src ON pf.source_process_id = src.id
            JOIN business_processes tgt ON pf.target_process_id = tgt.id
            WHERE pf.source_process_id = %s OR pf.target_process_id = %s
            ORDER BY pf.sort_order
            """,
            (process_id, process_id),
        )
        flows = []
        for flow_row in cursor.fetchall():
            flow = dict(flow_row)
            if flow.get("created_at"):
                flow["created_at"] = flow["created_at"].isoformat()
            flows.append(flow)

        result["flows"] = flows

        return jsonify(result), 200
    finally:
        release_db_connection(conn)


@processes_bp.route("/api/processes/<int:process_id>", methods=["PUT"])
@require_admin
def update_process(process_id):
    """Atualiza um processo."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Dados inválidos"}), 400

    conn = get_db()
    cursor = conn.cursor()
    try:
        fields = []
        params = []
        for col in ("name", "description", "module", "module_label", "icon", "color", "status"):
            if col in data:
                fields.append(f"{col} = %s")
                params.append(data[col])

        if not fields:
            return jsonify({"error": "Nenhum campo para atualizar"}), 400

        fields.append("updated_at = %s")
        params.append(datetime.utcnow())
        params.append(process_id)

        cursor.execute(
            f"UPDATE business_processes SET {', '.join(fields)} WHERE id = %s",
            params,
        )
        conn.commit()

        if cursor.rowcount == 0:
            return jsonify({"error": "Processo não encontrado"}), 404

        return jsonify({"success": True}), 200
    except Exception as e:
        conn.rollback()
        if "unique" in str(e).lower():
            return jsonify({"error": "Já existe um processo com este nome"}), 409
        return jsonify({"error": str(e)}), 500
    finally:
        release_db_connection(conn)


@processes_bp.route("/api/processes/<int:process_id>", methods=["DELETE"])
@require_admin
def delete_process(process_id):
    """Remove um processo (bloqueia se is_system=TRUE)."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT is_system FROM business_processes WHERE id = %s", (process_id,))
        proc = cursor.fetchone()
        if not proc:
            return jsonify({"error": "Processo não encontrado"}), 404
        if proc["is_system"]:
            return jsonify({"error": "Processo do sistema não pode ser removido"}), 403

        cursor.execute("DELETE FROM business_processes WHERE id = %s", (process_id,))
        conn.commit()
        return jsonify({"success": True}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        release_db_connection(conn)


# =========================================================
# TABELAS VINCULADAS
# =========================================================


@processes_bp.route("/api/processes/<int:process_id>/tables", methods=["GET"])
@require_admin
def list_process_tables(process_id):
    """Lista tabelas vinculadas a um processo."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT pt.*, dc.name as connection_name
            FROM process_tables pt
            LEFT JOIN database_connections dc ON pt.connection_id = dc.id
            WHERE pt.process_id = %s
            ORDER BY pt.sort_order, pt.table_name
            """,
            (process_id,),
        )
        tables = []
        for row in cursor.fetchall():
            item = dict(row)
            if item.get("created_at"):
                item["created_at"] = item["created_at"].isoformat()
            tables.append(item)
        return jsonify(tables), 200
    finally:
        release_db_connection(conn)


@processes_bp.route("/api/processes/<int:process_id>/tables", methods=["POST"])
@require_admin
def add_process_table(process_id):
    """Vincula uma tabela a um processo."""
    data = request.get_json()
    if not data or not data.get("table_name"):
        return jsonify({"error": "Nome da tabela é obrigatório"}), 400

    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO process_tables (process_id, connection_id, table_name, table_alias, table_role, description, sort_order)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                process_id, data.get("connection_id"), data["table_name"],
                data.get("table_alias", ""), data.get("table_role", "principal"),
                data.get("description", ""), data.get("sort_order", 0),
            ),
        )
        table_id = cursor.fetchone()["id"]
        conn.commit()
        return jsonify({"success": True, "id": table_id}), 201
    except Exception as e:
        conn.rollback()
        if "unique" in str(e).lower():
            return jsonify({"error": "Esta tabela já está vinculada ao processo"}), 409
        return jsonify({"error": str(e)}), 500
    finally:
        release_db_connection(conn)


@processes_bp.route("/api/processes/<int:process_id>/tables/<int:table_id>", methods=["PUT"])
@require_admin
def update_process_table(process_id, table_id):
    """Atualiza vínculo de tabela."""
    data = request.get_json()
    conn = get_db()
    cursor = conn.cursor()
    try:
        fields = []
        params = []
        for col in ("table_alias", "table_role", "description", "sort_order", "connection_id"):
            if col in data:
                fields.append(f"{col} = %s")
                params.append(data[col])

        if not fields:
            return jsonify({"error": "Nenhum campo para atualizar"}), 400

        params.extend([table_id, process_id])
        cursor.execute(
            f"UPDATE process_tables SET {', '.join(fields)} WHERE id = %s AND process_id = %s",
            params,
        )
        conn.commit()
        return jsonify({"success": True}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        release_db_connection(conn)


@processes_bp.route("/api/processes/<int:process_id>/tables/<int:table_id>", methods=["DELETE"])
@require_admin
def delete_process_table(process_id, table_id):
    """Remove vínculo de tabela."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "DELETE FROM process_tables WHERE id = %s AND process_id = %s",
            (table_id, process_id),
        )
        conn.commit()
        return jsonify({"success": True}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        release_db_connection(conn)


# =========================================================
# CAMPOS DE TABELA
# =========================================================


@processes_bp.route("/api/process-tables/<int:table_id>/fields", methods=["GET"])
@require_admin
def list_process_fields(table_id):
    """Lista campos de uma tabela vinculada."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT * FROM process_fields WHERE process_table_id = %s ORDER BY sort_order, column_name",
            (table_id,),
        )
        fields = []
        for row in cursor.fetchall():
            item = dict(row)
            if item.get("created_at"):
                item["created_at"] = item["created_at"].isoformat()
            fields.append(item)
        return jsonify(fields), 200
    finally:
        release_db_connection(conn)


@processes_bp.route("/api/process-tables/<int:table_id>/fields", methods=["POST"])
@require_admin
def add_process_field(table_id):
    """Adiciona campo a uma tabela vinculada."""
    data = request.get_json()
    if not data or not data.get("column_name"):
        return jsonify({"error": "Nome do campo é obrigatório"}), 400

    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO process_fields (process_table_id, column_name, column_label, is_key, is_required, business_rule, sort_order)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                table_id, data["column_name"], data.get("column_label", ""),
                data.get("is_key", False), data.get("is_required", False),
                data.get("business_rule", ""), data.get("sort_order", 0),
            ),
        )
        field_id = cursor.fetchone()["id"]
        conn.commit()
        return jsonify({"success": True, "id": field_id}), 201
    except Exception as e:
        conn.rollback()
        if "unique" in str(e).lower():
            return jsonify({"error": "Este campo já existe nesta tabela"}), 409
        return jsonify({"error": str(e)}), 500
    finally:
        release_db_connection(conn)


@processes_bp.route("/api/process-tables/<int:table_id>/fields/auto-map", methods=["POST"])
@require_admin
def auto_map_process_fields(table_id):
    """Importa campos do schema_cache automaticamente."""
    data = request.get_json()
    connection_id = data.get("connection_id") if data else None
    if not connection_id:
        return jsonify({"error": "connection_id é obrigatório"}), 400

    conn = get_db()
    cursor = conn.cursor()
    try:
        imported = auto_map_fields(cursor, table_id, connection_id)
        conn.commit()
        return jsonify({"success": True, "imported": imported, "message": f"{imported} campos importados"}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        release_db_connection(conn)


@processes_bp.route("/api/process-fields/<int:field_id>", methods=["PUT"])
@require_admin
def update_process_field(field_id):
    """Atualiza campo de tabela vinculada."""
    data = request.get_json()
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM process_fields WHERE id = %s", (field_id,))
        if not cursor.fetchone():
            return jsonify({"error": "Campo nao encontrado"}), 404

        fields = []
        values = []
        updatable = ["column_label", "is_key", "is_required", "business_rule", "sort_order"]
        for field in updatable:
            if field in data:
                fields.append(f"{field} = %s")
                values.append(data[field])

        if not fields:
            return jsonify({"error": "Nenhum campo para atualizar"}), 400

        values.append(field_id)
        cursor.execute(
            f"UPDATE process_fields SET {', '.join(fields)} WHERE id = %s",
            values,
        )
        conn.commit()
        return jsonify({"success": True}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        release_db_connection(conn)


@processes_bp.route("/api/process-fields/<int:field_id>", methods=["DELETE"])
@require_admin
def delete_process_field(field_id):
    """Remove campo."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM process_fields WHERE id = %s", (field_id,))
        conn.commit()
        return jsonify({"success": True}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        release_db_connection(conn)


# =========================================================
# FLUXOS ENTRE PROCESSOS
# =========================================================


@processes_bp.route("/api/processes/<int:process_id>/flows", methods=["GET"])
@require_admin
def list_process_flows(process_id):
    """Lista fluxos de/para o processo."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT pf.*,
                   src.name as source_name, src.icon as source_icon, src.color as source_color,
                   tgt.name as target_name, tgt.icon as target_icon, tgt.color as target_color
            FROM process_flows pf
            JOIN business_processes src ON pf.source_process_id = src.id
            JOIN business_processes tgt ON pf.target_process_id = tgt.id
            WHERE pf.source_process_id = %s OR pf.target_process_id = %s
            ORDER BY pf.sort_order
            """,
            (process_id, process_id),
        )
        flows = []
        for row in cursor.fetchall():
            item = dict(row)
            if item.get("created_at"):
                item["created_at"] = item["created_at"].isoformat()
            flows.append(item)
        return jsonify(flows), 200
    finally:
        release_db_connection(conn)


@processes_bp.route("/api/process-flows", methods=["POST"])
@require_admin
def create_flow():
    """Cria fluxo entre processos."""
    data = request.get_json()
    if not data or not data.get("source_process_id") or not data.get("target_process_id"):
        return jsonify({"error": "Processos de origem e destino são obrigatórios"}), 400

    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO process_flows (source_process_id, target_process_id, source_table, target_table,
                                       flow_type, description, sort_order)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                data["source_process_id"], data["target_process_id"],
                data.get("source_table", ""), data.get("target_table", ""),
                data.get("flow_type", "data"), data.get("description", ""),
                data.get("sort_order", 0),
            ),
        )
        flow_id = cursor.fetchone()["id"]
        conn.commit()
        return jsonify({"success": True, "id": flow_id}), 201
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        release_db_connection(conn)


@processes_bp.route("/api/process-flows/<int:flow_id>", methods=["DELETE"])
@require_admin
def delete_flow(flow_id):
    """Remove fluxo."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM process_flows WHERE id = %s", (flow_id,))
        conn.commit()
        return jsonify({"success": True}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        release_db_connection(conn)


@processes_bp.route("/api/process-flows/<int:flow_id>", methods=["PUT"])
@require_admin
def update_flow(flow_id):
    """Atualiza fluxo entre processos."""
    data = request.get_json()
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM process_flows WHERE id = %s", (flow_id,))
        if not cursor.fetchone():
            return jsonify({"error": "Fluxo nao encontrado"}), 404

        fields = []
        values = []
        updatable = ["source_table", "target_table", "flow_type", "description", "sort_order"]
        for field in updatable:
            if field in data:
                fields.append(f"{field} = %s")
                values.append(data[field])

        if not fields:
            return jsonify({"error": "Nenhum campo para atualizar"}), 400

        values.append(flow_id)
        cursor.execute(
            f"UPDATE process_flows SET {', '.join(fields)} WHERE id = %s",
            values,
        )
        conn.commit()
        return jsonify({"success": True}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        release_db_connection(conn)


# =========================================================
# FLUXO GLOBAL (TODOS OS PROCESSOS)
# =========================================================


@processes_bp.route("/api/processes/flow-map", methods=["GET"])
@require_admin
def get_flow_map():
    """Retorna todos os processos e fluxos para visualização do mapa completo."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        # Todos os processos ativos
        cursor.execute(
            """
            SELECT id, name, module, module_label, icon, color,
                   (SELECT COUNT(*) FROM process_tables pt WHERE pt.process_id = bp.id) as table_count
            FROM business_processes bp
            WHERE bp.status = 'active'
            ORDER BY bp.module, bp.name
            """
        )
        nodes = [dict(row) for row in cursor.fetchall()]

        # Todos os fluxos
        cursor.execute(
            """
            SELECT pf.id, pf.source_process_id, pf.target_process_id,
                   pf.source_table, pf.target_table, pf.flow_type, pf.description
            FROM process_flows pf
            JOIN business_processes src ON pf.source_process_id = src.id AND src.status = 'active'
            JOIN business_processes tgt ON pf.target_process_id = tgt.id AND tgt.status = 'active'
            ORDER BY pf.sort_order
            """
        )
        edges = [dict(row) for row in cursor.fetchall()]

        return jsonify({"nodes": nodes, "edges": edges}), 200
    finally:
        release_db_connection(conn)
