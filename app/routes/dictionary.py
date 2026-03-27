"""
Rotas de Comparacao de Dicionario, Validacao de Integridade e Equalizacao Protheus.
"""

import csv
import io
import time
import json
from flask import Blueprint, request, jsonify, make_response
from app.utils.security import require_admin
from app.services import dictionary_compare as dc
from app.services import dictionary_equalizer as deq
from app.services import dictionary_ingestor as ding

dictionary_bp = Blueprint("dictionary", __name__)


@dictionary_bp.route("/api/dictionary/companies/<int:conn_id>", methods=["GET"])
@require_admin
def list_companies(conn_id):
    """Lista empresas disponiveis (SYS_COMPANY) de uma conexao."""
    try:
        companies = dc.get_companies(conn_id)
        return jsonify({"companies": companies})
    except Exception as e:
        return jsonify({"error": str(e)[:500]}), 500


@dictionary_bp.route("/api/dictionary/compare", methods=["POST"])
@require_admin
def compare():
    """Compara dicionario entre duas conexoes."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Payload JSON obrigatorio"}), 400

    conn_id_a = data.get("conn_id_a")
    conn_id_b = data.get("conn_id_b")
    company_code = data.get("company_code")
    tables = data.get("tables")
    alias_filter = data.get("alias_filter")
    include_deleted = data.get("include_deleted", False)

    if not conn_id_a or not conn_id_b:
        return jsonify({"error": "conn_id_a e conn_id_b sao obrigatorios"}), 400
    if not company_code:
        return jsonify({"error": "company_code e obrigatorio"}), 400

    try:
        start = time.time()
        result = dc.compare_dictionaries(conn_id_a, conn_id_b, company_code, tables, alias_filter=alias_filter, include_deleted=include_deleted)
        duration_ms = int((time.time() - start) * 1000)

        # Montar resumo
        total_diffs = 0
        tables_with_diffs = 0
        for table_name, info in result.items():
            ndiffs = len(info.get("only_a", [])) + len(info.get("only_b", [])) + len(info.get("different", []))
            if ndiffs > 0:
                tables_with_diffs += 1
            total_diffs += ndiffs

        summary = {
            "tables_compared": len(result),
            "tables_with_diffs": tables_with_diffs,
            "total_diffs": total_diffs,
            "duration_ms": duration_ms,
        }

        # Salvar no historico
        environment_id = request.args.get("environment_id") or data.get("environment_id")
        try:
            history_id = dc.save_history(
                environment_id=environment_id,
                operation_type="compare",
                conn_a_id=conn_id_a,
                conn_b_id=conn_id_b,
                company_code=company_code,
                summary=summary,
                details=result,
                user_id=request.current_user["id"],
                duration_ms=duration_ms,
            )
            summary["history_id"] = history_id
        except Exception:
            pass  # Historico e opcional, nao falhar a operacao

        return jsonify({"summary": summary, "results": result})

    except Exception as e:
        return jsonify({"error": str(e)[:500]}), 500


@dictionary_bp.route("/api/dictionary/validate", methods=["POST"])
@require_admin
def validate():
    """Valida integridade de uma conexao."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Payload JSON obrigatorio"}), 400

    connection_id = data.get("connection_id")
    company_code = data.get("company_code")
    layers = data.get("layers")  # lista de camadas opcionais

    if not connection_id:
        return jsonify({"error": "connection_id e obrigatorio"}), 400
    if not company_code:
        return jsonify({"error": "company_code e obrigatorio"}), 400

    try:
        start = time.time()
        result = dc.validate_integrity(connection_id, company_code, layers=layers)
        duration_ms = int((time.time() - start) * 1000)

        # Montar resumo (generico para N camadas)
        checks = {}
        total_ok = 0
        total_issues = 0
        skip_keys = ("existing_tables", "ok", "total", "skipped", "virtual_skipped", "error")
        for layer, info in result.items():
            n_ok = info.get("ok", 0)
            # Contar issues genericamente: qualquer lista no resultado
            n_issues = 0
            for key, val in info.items():
                if isinstance(val, list) and key not in skip_keys:
                    n_issues += len(val)
            checks[layer] = {"ok": n_ok, "issues": n_issues, "has_error": "error" in info}
            total_ok += n_ok
            total_issues += n_issues

        summary = {
            "checks": checks,
            "total_ok": total_ok,
            "total_issues": total_issues,
            "duration_ms": duration_ms,
        }

        # Salvar no historico
        environment_id = request.args.get("environment_id") or data.get("environment_id")
        try:
            history_id = dc.save_history(
                environment_id=environment_id,
                operation_type="validate",
                conn_a_id=connection_id,
                conn_b_id=None,
                company_code=company_code,
                summary=summary,
                details=result,
                user_id=request.current_user["id"],
                duration_ms=duration_ms,
            )
            summary["history_id"] = history_id
        except Exception:
            pass

        return jsonify({"summary": summary, "results": result})

    except Exception as e:
        return jsonify({"error": str(e)[:500]}), 500


@dictionary_bp.route("/api/dictionary/history", methods=["GET"])
@require_admin
def history():
    """Retorna historico de operacoes de dicionario."""
    environment_id = request.args.get("environment_id")
    limit = min(int(request.args.get("limit", 20)), 100)
    try:
        items = dc.get_history(environment_id, limit)
        return jsonify({"history": items})
    except Exception as e:
        return jsonify({"error": str(e)[:500]}), 500


@dictionary_bp.route("/api/dictionary/history/<int:history_id>", methods=["GET"])
@require_admin
def history_detail(history_id):
    """Retorna detalhes completos de um registro do historico."""
    try:
        item = dc.get_history_detail(history_id)
        if not item:
            return jsonify({"error": "Registro nao encontrado"}), 404
        return jsonify(item)
    except Exception as e:
        return jsonify({"error": str(e)[:500]}), 500


@dictionary_bp.route("/api/dictionary/history/<int:history_id>", methods=["DELETE"])
@require_admin
def history_delete(history_id):
    """Exclui um registro do historico."""
    try:
        deleted = dc.delete_history(history_id)
        if not deleted:
            return jsonify({"error": "Registro nao encontrado"}), 404
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)[:500]}), 500


@dictionary_bp.route("/api/dictionary/export/<operation_type>/<int:history_id>", methods=["GET"])
@require_admin
def export_csv(operation_type, history_id):
    """Exporta resultado de compare ou validate como CSV."""
    from app.database import get_db, release_db_connection

    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT details, operation_type FROM dictionary_history WHERE id = %s", (history_id,))
        row = cursor.fetchone()
        if not row:
            return jsonify({"error": "Registro nao encontrado"}), 404

        record = dict(row)
        details = record["details"]
        if isinstance(details, str):
            details = json.loads(details)

        output = io.StringIO()
        writer = csv.writer(output, delimiter=";")

        if record["operation_type"] == "compare":
            writer.writerow(["Tabela", "Tipo", "Chave", "Campo", "Valor_A", "Valor_B"])
            for table_name, info in details.items():
                for item in info.get("only_a", []):
                    writer.writerow([table_name, "Apenas em A", item.get("key", ""), "", "", ""])
                for item in info.get("only_b", []):
                    writer.writerow([table_name, "Apenas em B", item.get("key", ""), "", "", ""])
                for item in info.get("different", []):
                    for field in item.get("fields", []):
                        writer.writerow([
                            table_name, "Diferente", item.get("key", ""),
                            field.get("field", ""),
                            str(field.get("val_a", "")),
                            str(field.get("val_b", "")),
                        ])

        elif record["operation_type"] == "validate":
            writer.writerow(["Camada", "Tipo", "Tabela", "Campo", "Detalhe"])
            skip_keys = ("ok", "total", "skipped", "virtual_skipped", "error", "existing_tables")
            for layer_key, layer_data in details.items():
                if not isinstance(layer_data, dict):
                    continue
                for key, val in layer_data.items():
                    if not isinstance(val, list) or key in skip_keys:
                        continue
                    for item in val:
                        table = item.get("table", item.get("x2_chave", item.get("expected_table", "")))
                        field = item.get("field", item.get("column", item.get("alias", "")))
                        detail_parts = []
                        for dk, dv in item.items():
                            if dk not in ("table", "field", "column", "alias", "x2_chave", "expected_table"):
                                detail_parts.append(f"{dk}={dv}")
                        writer.writerow([layer_key, key, table, field, "; ".join(detail_parts)])

        elif record["operation_type"] in ("equalize", "ingest"):
            writer.writerow(["Fase", "Descricao", "SQL", "Origem"])
            statements = details.get("statements", [])
            origem = "ingest" if record["operation_type"] == "ingest" else "equalize"
            for stmt in statements:
                phase = stmt.get("phase", "")
                desc = stmt.get("description", "")
                sql = stmt.get("sql", "")
                writer.writerow([f"Fase {phase}", desc, sql, origem])

        csv_content = output.getvalue()
        response = make_response(csv_content)
        response.headers["Content-Type"] = "text/csv; charset=utf-8"
        response.headers["Content-Disposition"] = f"attachment; filename=dictionary_{operation_type}_{history_id}.csv"
        return response

    finally:
        release_db_connection(conn)


# =====================================================================
# EQUALIZACAO
# =====================================================================


@dictionary_bp.route("/api/dictionary/equalize/preview", methods=["POST"])
@require_admin
def equalize_preview():
    """Gera preview de SQL para equalizacao sem executar."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Payload JSON obrigatorio"}), 400

    source_conn_id = data.get("source_conn_id")
    target_conn_id = data.get("target_conn_id")
    company_code = data.get("company_code")
    items = data.get("items")

    if not source_conn_id or not target_conn_id:
        return jsonify({"error": "source_conn_id e target_conn_id sao obrigatorios"}), 400
    if not company_code:
        return jsonify({"error": "company_code e obrigatorio"}), 400
    if not items or not isinstance(items, list):
        return jsonify({"error": "items deve ser uma lista nao vazia"}), 400

    try:
        result = deq.generate_equalize_preview(
            source_conn_id=int(source_conn_id),
            target_conn_id=int(target_conn_id),
            company_code=company_code,
            items=items,
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)[:500]}), 500


@dictionary_bp.route("/api/dictionary/equalize/execute", methods=["POST"])
@require_admin
def equalize_execute():
    """Executa equalizacao em transacao atomica."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Payload JSON obrigatorio"}), 400

    target_conn_id = data.get("target_conn_id")
    source_conn_id = data.get("source_conn_id")
    company_code = data.get("company_code")
    sql_statements = data.get("sql_statements")
    confirmation_token = data.get("confirmation_token")

    if not target_conn_id or not source_conn_id:
        return jsonify({"error": "target_conn_id e source_conn_id sao obrigatorios"}), 400
    if not company_code:
        return jsonify({"error": "company_code e obrigatorio"}), 400
    if not sql_statements or not isinstance(sql_statements, list):
        return jsonify({"error": "sql_statements deve ser uma lista nao vazia"}), 400
    if not confirmation_token:
        return jsonify({"error": "confirmation_token e obrigatorio"}), 400

    try:
        environment_id = data.get("environment_id")
        result = deq.execute_equalization(
            target_conn_id=int(target_conn_id),
            source_conn_id=int(source_conn_id),
            company_code=company_code,
            sql_statements=sql_statements,
            confirmation_token=confirmation_token,
            user_id=request.current_user["id"],
            environment_id=int(environment_id) if environment_id else None,
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)[:500]}), 500


# =====================================================================
# INGESTOR DE DICIONARIO
# =====================================================================


@dictionary_bp.route("/api/dictionary/ingest/upload", methods=["POST"])
@require_admin
def ingest_upload():
    """Recebe arquivo de ingestao (JSON ou MD) e faz parse.

    Aceita:
        - multipart/form-data com campo 'file'
        - application/json com campo 'content' (string) e 'filename'
    """
    try:
        file_content = None
        filename = ""

        if request.content_type and "multipart/form-data" in request.content_type:
            uploaded = request.files.get("file")
            if not uploaded:
                return jsonify({"error": "Campo 'file' obrigatorio no upload"}), 400
            file_content = uploaded.read()
            filename = uploaded.filename or ""
        else:
            data = request.get_json()
            if not data:
                return jsonify({"error": "Payload JSON ou multipart obrigatorio"}), 400
            file_content = data.get("content", "")
            filename = data.get("filename", "")
            if not file_content:
                return jsonify({"error": "Campo 'content' obrigatorio"}), 400

        # Salvar arquivo
        filepath = ding.save_uploaded_file(file_content, filename or "ingest_file")

        # Parsear
        parsed = ding.parse_ingest_file(file_content, filename)

        # Resumo dos items parseados
        type_counts = {}
        for item in parsed["items"]:
            t = item.get("type", "unknown")
            type_counts[t] = type_counts.get(t, 0) + 1

        return jsonify({
            "success": True,
            "filepath": filepath,
            "metadata": parsed["metadata"],
            "item_count": len(parsed["items"]),
            "item_types": type_counts,
            "parse_warnings": parsed.get("parse_warnings", []),
            "items": parsed["items"],
        })

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)[:500]}), 500


@dictionary_bp.route("/api/dictionary/ingest/preview", methods=["POST"])
@require_admin
def ingest_preview():
    """Gera preview de SQL para ingestao sem executar.

    Payload:
        target_conn_id: ID da conexao de destino
        company_code: codigo da empresa
        items: lista de items (do upload)
        metadata: metadata do arquivo (opcional)
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "Payload JSON obrigatorio"}), 400

    target_conn_id = data.get("target_conn_id")
    company_code = data.get("company_code")
    items = data.get("items")

    if not target_conn_id:
        return jsonify({"error": "target_conn_id e obrigatorio"}), 400
    if not company_code:
        return jsonify({"error": "company_code e obrigatorio"}), 400
    if not items or not isinstance(items, list):
        return jsonify({"error": "items deve ser uma lista nao vazia"}), 400

    try:
        parsed_data = {
            "items": items,
            "metadata": data.get("metadata", {}),
            "parse_warnings": [],
        }
        result = ding.generate_ingest_preview(
            target_conn_id=int(target_conn_id),
            company_code=company_code,
            parsed_data=parsed_data,
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)[:500]}), 500


@dictionary_bp.route("/api/dictionary/ingest/execute", methods=["POST"])
@require_admin
def ingest_execute():
    """Executa ingestao em transacao atomica."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Payload JSON obrigatorio"}), 400

    target_conn_id = data.get("target_conn_id")
    company_code = data.get("company_code")
    sql_statements = data.get("sql_statements")
    confirmation_token = data.get("confirmation_token")

    if not target_conn_id:
        return jsonify({"error": "target_conn_id e obrigatorio"}), 400
    if not company_code:
        return jsonify({"error": "company_code e obrigatorio"}), 400
    if not sql_statements or not isinstance(sql_statements, list):
        return jsonify({"error": "sql_statements deve ser uma lista nao vazia"}), 400
    if not confirmation_token:
        return jsonify({"error": "confirmation_token e obrigatorio"}), 400

    try:
        environment_id = data.get("environment_id")
        file_metadata = data.get("file_metadata")
        result = ding.execute_ingestion(
            target_conn_id=int(target_conn_id),
            company_code=company_code,
            sql_statements=sql_statements,
            confirmation_token=confirmation_token,
            user_id=request.current_user["id"],
            environment_id=int(environment_id) if environment_id else None,
            file_metadata=file_metadata,
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)[:500]}), 500
