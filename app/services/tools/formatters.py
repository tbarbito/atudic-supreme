"""
Formatadores de resultado de tools para o LLM.

Converte resultados brutos de tools em texto estruturado que o LLM
interpreta com precisão, evitando JSON truncado.
"""


def format_tool_result_for_llm(tool_name, result, max_chars=3000):
    """Formata resultado de tool para o LLM de forma inteligente."""
    if isinstance(result, dict) and result.get("error"):
        return f"ERRO: {result['error']}"

    # Desempacotar wrapper success/data
    inner = result
    if isinstance(result, dict) and result.get("success") and "data" in result:
        inner = result["data"]
        if not isinstance(inner, (dict, list)):
            inner = result

    # human_summary — resumo pre-formatado para o LLM
    if isinstance(inner, dict) and inner.get("human_summary"):
        return inner["human_summary"][:max_chars]

    # formatted_result (ex: compare_dictionary)
    if isinstance(inner, dict) and inner.get("formatted_result"):
        return inner["formatted_result"][:max_chars]

    data_to_scan = inner if isinstance(inner, dict) else result if isinstance(result, dict) else {}

    # Dispatch por tipo de dado
    if isinstance(data_to_scan, dict) and ("phase1_ddl" in data_to_scan or "phase2_dml" in data_to_scan):
        return _format_equalize_preview(data_to_scan, max_chars)

    if isinstance(data_to_scan, dict) and "checks" in data_to_scan and isinstance(data_to_scan["checks"], dict):
        return _format_validate_result(data_to_scan, max_chars)

    if isinstance(data_to_scan, dict) and "executed" in data_to_scan:
        return _format_equalize_execute(data_to_scan, max_chars)

    if isinstance(data_to_scan, dict) and "exit_code" in data_to_scan and "stdout" in data_to_scan:
        return _format_command_result(data_to_scan, max_chars)

    if isinstance(data_to_scan, dict) and "content" in data_to_scan and "path" in data_to_scan:
        return _format_file_content(data_to_scan, max_chars)

    if isinstance(data_to_scan, dict) and "environments" in data_to_scan and (
        "recent_alerts" in data_to_scan or "db_connections" in data_to_scan
    ):
        return _format_system_overview(data_to_scan, max_chars)

    # Listas de registros → tabela compacta
    list_keys = ["alerts", "connections", "environments", "variables", "services",
                 "users", "articles", "schedules", "recurring_errors", "monitors",
                 "webhooks", "summary", "rows", "results", "items", "records",
                 "entries", "matches", "tables", "history", "files", "audits",
                 "db_connections", "recent_pipelines", "recent_alerts", "repositories"]

    for key in list_keys:
        if key in data_to_scan and isinstance(data_to_scan[key], list):
            return _format_list_as_table(tool_name, key, data_to_scan, result, max_chars)

    # Fallback: qualquer lista de dicts
    if isinstance(data_to_scan, dict):
        for key, val in data_to_scan.items():
            if isinstance(val, list) and val and isinstance(val[0], dict):
                return _format_list_as_table(tool_name, key, data_to_scan, result, max_chars)

    # Dicts simples → key: value
    if isinstance(data_to_scan, dict):
        lines = []
        for k, v in data_to_scan.items():
            if k.startswith("_") or k in ("password", "password_salt", "api_key_encrypted"):
                continue
            v_str = str(v)
            if len(v_str) > 200:
                v_str = v_str[:197] + "..."
            lines.append(f"{k}: {v_str}")
        return "\n".join(lines)[:max_chars]

    text = str(result)
    return text[:max_chars] if len(text) > max_chars else text


def _format_list_as_table(tool_name, key, data_to_scan, result, max_chars=3000):
    """Formata lista de dicts como tabela compacta."""
    items = data_to_scan[key]
    total = data_to_scan.get("total", data_to_scan.get("total_matches", len(items)))

    if not items:
        return f"{tool_name}: nenhum resultado encontrado."

    if isinstance(items[0], dict):
        cols = list(items[0].keys())
        cols = [c for c in cols if c not in ("password", "password_salt", "api_key_encrypted")]

        lines = [f"{tool_name}: {total} resultado(s)"]
        lines.append(" | ".join(cols))
        lines.append("-" * min(len(" | ".join(cols)), 80))

        for item in items[:30]:
            vals = []
            for c in cols:
                v = str(item.get(c, ""))
                if len(v) > 50:
                    v = v[:47] + "..."
                vals.append(v)
            lines.append(" | ".join(vals))

        if len(items) > 30:
            lines.append(f"... e mais {len(items) - 30} registros")

        text = "\n".join(lines)
        for extra_key in ("note", "hint", "warning"):
            extra = data_to_scan.get(extra_key) or (result.get(extra_key) if isinstance(result, dict) else None)
            if extra:
                text += f"\n{extra}"
        return text[:max_chars]
    else:
        text = f"{tool_name}: {total} resultado(s)\n"
        text += "\n".join(f"- {str(item)[:100]}" for item in items[:30])
        return text[:max_chars]


def _format_equalize_preview(data, max_chars=3000):
    """Formata preview de equalização (DDL/DML)."""
    lines = []
    summary = data.get("summary", {})
    lines.append(f"Preview de equalização: {summary.get('total_statements', 0)} statements")
    lines.append(f"  DDL: {summary.get('ddl_count', 0)} | DML: {summary.get('dml_count', 0)} | "
                 f"Campos: {summary.get('fields', 0)} | Índices: {summary.get('indexes', 0)} | "
                 f"Tabelas: {summary.get('tables', 0)}")

    for phase_key, phase_label in [("phase1_ddl", "DDL"), ("phase2_dml", "DML")]:
        phase = data.get(phase_key, [])
        if phase:
            lines.append(f"\nFase — {phase_label} ({len(phase)} operações):")
            for stmt in phase[:15]:
                desc = stmt.get("description", "")
                sql = stmt.get("sql", "")
                if len(sql) > 120:
                    sql = sql[:117] + "..."
                lines.append(f"  • {desc}")
                lines.append(f"    SQL: {sql}")
            if len(phase) > 15:
                lines.append(f"  ... e mais {len(phase) - 15} operações")

    warnings = data.get("warnings", [])
    if warnings:
        lines.append(f"\nAvisos ({len(warnings)}):")
        for w in warnings[:10]:
            lines.append(f"  ⚠ {w}")

    token = data.get("confirmation_token", "")
    if token:
        lines.append(f"\nToken de confirmação: {token[:16]}...")

    return "\n".join(lines)[:max_chars]


def _format_validate_result(data, max_chars=3000):
    """Formata resultado de validação de integridade do dicionário."""
    lines = []
    conn_info = data.get("connection", {})
    if conn_info:
        lines.append(f"Validação de integridade — Conexão: {conn_info.get('name', '?')} (ID {conn_info.get('id', '?')})")
    else:
        lines.append("Validação de integridade do dicionário")

    checks = data.get("checks", {})
    total_errors = 0
    for check_name, check_data in checks.items():
        errors = check_data.get("errors", [])
        total = check_data.get("total", 0)
        status = "OK" if not errors else f"{len(errors)} erro(s)"
        total_errors += len(errors)
        lines.append(f"  • {check_name}: {status} ({total} registros)")
        for err in errors[:5]:
            lines.append(f"    - {err}")
        if len(errors) > 5:
            lines.append(f"    ... e mais {len(errors) - 5} erros")

    lines.insert(1, f"Resultado: {'TUDO OK' if total_errors == 0 else f'{total_errors} problema(s) encontrado(s)'}")
    return "\n".join(lines)[:max_chars]


def _format_equalize_execute(data, max_chars=3000):
    """Formata resultado de execução de equalização."""
    lines = []
    executed = data.get("executed", 0)
    failed = data.get("failed", 0)
    total = data.get("total", executed + failed)
    lines.append(f"Equalização executada: {executed}/{total} statements com sucesso")
    if failed:
        lines.append(f"  ❌ {failed} statement(s) falharam")
    for err in data.get("errors", [])[:10]:
        lines.append(f"  - {err}")
    for w in data.get("warnings", [])[:5]:
        lines.append(f"  ⚠ {w}")
    return "\n".join(lines)[:max_chars]


def _format_command_result(data, max_chars=3000):
    """Formata resultado de run_command."""
    lines = []
    cmd = data.get("command", "?")
    code = data.get("exit_code", -1)
    status = "OK" if code == 0 else f"ERRO (exit code {code})"
    lines.append(f"Comando: {cmd}")
    lines.append(f"Status: {status}")
    stdout = data.get("stdout", "").strip()
    stderr = data.get("stderr", "").strip()
    if stdout:
        lines.append(f"\nSaída:\n{stdout}")
    if stderr:
        lines.append(f"\nErros:\n{stderr}")
    return "\n".join(lines)[:max_chars]


def _format_file_content(data, max_chars=3000):
    """Formata resultado de read_file."""
    path = data.get("path", "?")
    size = data.get("size", 0)
    total_lines = data.get("lines", 0)
    truncated = data.get("truncated", False)
    content = data.get("content", "")

    header = f"Arquivo: {path} ({size} bytes, {total_lines} linhas)"
    if truncated:
        header += " [TRUNCADO]"

    content_budget = max_chars - len(header) - 20
    if len(content) > content_budget:
        content = content[:content_budget] + "\n... (truncado)"

    return f"{header}\n\n{content}"


def _format_system_overview(data, max_chars=3000):
    """Formata system_overview com múltiplas seções."""
    lines = ["Visão geral do sistema:"]

    for section_key, section_label in [
        ("environments", "Ambientes"),
        ("recent_pipelines", "Pipelines recentes"),
        ("recent_alerts", "Alertas recentes"),
        ("repositories", "Repositórios"),
        ("services", "Serviços"),
        ("db_connections", "Conexões de banco"),
    ]:
        items = data.get(section_key, [])
        if not items:
            continue
        lines.append(f"\n{section_label} ({len(items)}):")
        if isinstance(items[0], dict):
            cols = list(items[0].keys())
            cols = [c for c in cols if c not in ("password", "password_salt", "api_key_encrypted")]
            lines.append("  " + " | ".join(cols))
            for item in items[:10]:
                vals = [str(item.get(c, ""))[:40] for c in cols]
                lines.append("  " + " | ".join(vals))
            if len(items) > 10:
                lines.append(f"  ... e mais {len(items) - 10}")

    return "\n".join(lines)[:max_chars]
