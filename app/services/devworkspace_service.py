"""
Servico do Dev Workspace — Desenvolvimento Assistido.

Funcionalidades:
- 1A: Navegador de fontes AdvPL (browse FONTES_DIR, viewer, search)
- 1B: Analise de impacto (cross-reference fontes com schema, processos, erros)
- 1C: Assistente de compilacao (diff FONTES_DIR vs repo, gerar compila.txt)
"""

import fnmatch
import hashlib
import json
import logging
import os
import platform
import re
import subprocess

logger = logging.getLogger(__name__)

# Extensoes de fontes AdvPL/TLPP
ADVPL_EXTENSIONS = {".prw", ".prx", ".tlpp", ".aph", ".ch", ".prg"}

# Regex para tabelas Protheus (ex: SA1, SE1, SC5, SB1, etc.)
TABLE_PATTERN = re.compile(r"\b(S[A-Z][0-9A-Z]|[A-Z]{2}[0-9])\b", re.IGNORECASE)

# Tabelas conhecidas do Protheus (prefixos comuns)
KNOWN_TABLE_PREFIXES = {
    "SA",
    "SB",
    "SC",
    "SD",
    "SE",
    "SF",
    "SG",
    "SH",
    "SI",
    "SN",
    "SR",
    "SX",
    "SZ",
    "CT",
    "CV",
    "DA",
    "CJ",
    "CK",
    "CQ",
    "SRA",
    "SRB",
    "SRC",
    "SRD",
    "SRE",
}

# Regex para funcoes AdvPL
FUNCTION_DEF_PATTERN = re.compile(r"^\s*(?:User\s+)?(?:Static\s+)?Function\s+(\w+)\s*\(", re.IGNORECASE | re.MULTILINE)

# Regex para #include
INCLUDE_PATTERN = re.compile(r'#include\s+["\']([^"\']+)["\']', re.IGNORECASE)

# Regex para chamadas de funcao
FUNCTION_CALL_PATTERN = re.compile(
    r"\b([A-Za-z_]\w+)\s*\(",
)


# =====================================================================
# 1A — NAVEGADOR DE FONTES
# =====================================================================


def get_fontes_dir(cursor, environment_id):
    """Retorna o FONTES_DIR configurado para o ambiente."""
    # Busca nome do ambiente para determinar sufixo
    cursor.execute("SELECT name FROM environments WHERE id = %s", (environment_id,))
    env = cursor.fetchone()
    if not env:
        return None

    suffix_map = {"Produção": "PRD", "Homologação": "HOM", "Desenvolvimento": "DEV", "Testes": "TST"}
    suffix = suffix_map.get(env["name"], "PRD")

    cursor.execute("SELECT value FROM server_variables WHERE name = %s", (f"FONTES_DIR_{suffix}",))
    row = cursor.fetchone()
    return row["value"] if row else None


def list_fontes_dirs(cursor, environment_id=None):
    """Lista FONTES_DIR disponiveis (todos os ambientes ou um especifico)."""
    if environment_id:
        fontes_dir = get_fontes_dir(cursor, environment_id)
        if fontes_dir:
            cursor.execute("SELECT name FROM environments WHERE id = %s", (environment_id,))
            env = cursor.fetchone()
            return [
                {
                    "environment_id": environment_id,
                    "environment_name": env["name"] if env else "",
                    "fontes_dir": fontes_dir,
                    "exists": os.path.isdir(fontes_dir),
                }
            ]
        return []

    # Lista todos os ambientes com FONTES_DIR
    cursor.execute("SELECT id, name FROM environments ORDER BY id")
    environments = cursor.fetchall()
    result = []
    for env in environments:
        fontes_dir = get_fontes_dir(cursor, env["id"])
        if fontes_dir:
            result.append(
                {
                    "environment_id": env["id"],
                    "environment_name": env["name"],
                    "fontes_dir": fontes_dir,
                    "exists": os.path.isdir(fontes_dir),
                }
            )
    return result


def browse_directory(base_path, relative_path=""):
    """Lista arquivos e pastas de um diretorio com filtro AdvPL."""
    if not os.path.isdir(base_path):
        return None, f"Diretorio nao encontrado: {base_path}"

    target = os.path.join(base_path, relative_path) if relative_path else base_path

    # Validacao path traversal
    real_base = os.path.realpath(base_path)
    real_target = os.path.realpath(target)
    if not real_target.startswith(real_base):
        return None, "Path traversal detectado"

    if not os.path.isdir(real_target):
        return None, "Diretorio nao encontrado"

    items = []
    try:
        entries = sorted(os.listdir(real_target))
    except PermissionError:
        return None, "Permissao negada"

    for entry in entries:
        if entry.startswith("."):
            continue
        full_path = os.path.join(real_target, entry)
        is_dir = os.path.isdir(full_path)
        item_path = f"{relative_path}/{entry}" if relative_path else entry

        ext = os.path.splitext(entry)[1].lower() if not is_dir else ""
        is_advpl = ext in ADVPL_EXTENSIONS

        try:
            size = 0 if is_dir else os.path.getsize(full_path)
            modified = os.path.getmtime(full_path)
        except OSError:
            size = 0
            modified = 0

        items.append(
            {
                "name": entry,
                "path": item_path,
                "type": "dir" if is_dir else "file",
                "size": size,
                "modified": modified,
                "is_advpl": is_advpl,
                "extension": ext,
            }
        )

    # Ordena: pastas primeiro, depois arquivos
    items.sort(key=lambda x: (0 if x["type"] == "dir" else 1, x["name"].lower()))
    return items, None


def read_source_file(base_path, file_path, max_size=2_097_152):
    """Le conteudo de um arquivo fonte."""
    if not file_path:
        return None, "Caminho do arquivo nao informado"

    # Rejeita componentes perigosos
    parts = file_path.replace("\\", "/").split("/")
    for part in parts:
        if part == ".." or part.startswith("~"):
            return None, "Caminho invalido"

    full_path = os.path.join(base_path, file_path)
    real_base = os.path.realpath(base_path)
    real_file = os.path.realpath(full_path)
    if not real_file.startswith(real_base):
        return None, "Path traversal detectado"

    if not os.path.isfile(real_file):
        return None, "Arquivo nao encontrado"

    file_size = os.path.getsize(real_file)
    if file_size > max_size:
        return None, f"Arquivo muito grande ({file_size} bytes, max {max_size})"

    try:
        # Arquivos AdvPL/TLPP sao tipicamente salvos em ANSI (cp1252)
        ext = os.path.splitext(real_file)[1].lower()
        advpl_exts = {".prw", ".prx", ".tlpp", ".aph", ".ch"}
        encoding = "cp1252" if ext in advpl_exts else "utf-8"
        with open(real_file, "r", encoding=encoding, errors="replace") as f:
            content = f.read()
        return {
            "path": file_path,
            "name": os.path.basename(file_path),
            "content": content,
            "size": file_size,
            "extension": os.path.splitext(file_path)[1].lower(),
            "lines": content.count("\n") + 1,
        }, None
    except Exception as e:
        return None, f"Erro ao ler arquivo: {str(e)}"


def search_sources(base_path, pattern, file_filter="*.prw", max_results=200):
    """Busca nos fontes. Usa grep no Linux/macOS ou Python puro no Windows."""
    if not os.path.isdir(base_path):
        return None, "Diretorio nao encontrado"

    if not pattern or len(pattern) < 2:
        return None, "Padrao de busca deve ter pelo menos 2 caracteres"

    is_windows = platform.system() == "Windows"

    if not is_windows:
        return _search_sources_grep(base_path, pattern, file_filter, max_results)
    else:
        return _search_sources_python(base_path, pattern, file_filter, max_results)


def _search_sources_grep(base_path, pattern, file_filter, max_results):
    """Busca usando grep (Linux/macOS)."""
    try:
        cmd = ["grep", "-rn", "--include", file_filter, "-i", "--max-count", "5", pattern, base_path]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)

        matches = []
        for line in result.stdout.split("\n"):
            if not line.strip():
                continue
            # formato: /path/file.prw:42:conteudo
            parts = line.split(":", 2)
            if len(parts) >= 3:
                file_path = parts[0]
                line_num = parts[1]
                content = parts[2].strip()
                rel_path = os.path.relpath(file_path, base_path)
                matches.append(
                    {"file": rel_path, "line": int(line_num) if line_num.isdigit() else 0, "content": content[:500]}
                )
                if len(matches) >= max_results:
                    break

        return {"pattern": pattern, "filter": file_filter, "total": len(matches), "matches": matches}, None

    except subprocess.TimeoutExpired:
        return None, "Timeout na busca (limite: 30s)"
    except Exception as e:
        return None, f"Erro na busca: {str(e)}"


def _search_sources_python(base_path, pattern, file_filter, max_results):
    """Busca usando Python puro (Windows-compatible)."""
    try:
        pattern_lower = pattern.lower()
        matches = []
        hits_per_file = 5  # equivalente ao --max-count 5 do grep

        for root, _dirs, files in os.walk(base_path):
            for filename in files:
                if not fnmatch.fnmatchcase(filename.lower(), file_filter.lower()):
                    continue

                full_path = os.path.join(root, filename)
                ext = os.path.splitext(filename)[1].lower()
                encoding = "cp1252" if ext in {".prw", ".prx", ".tlpp", ".aph", ".ch"} else "utf-8"

                try:
                    with open(full_path, "r", encoding=encoding, errors="replace") as f:
                        file_hits = 0
                        for line_num, line in enumerate(f, start=1):
                            if pattern_lower in line.lower():
                                rel_path = os.path.relpath(full_path, base_path)
                                matches.append({
                                    "file": rel_path,
                                    "line": line_num,
                                    "content": line.strip()[:500],
                                })
                                file_hits += 1
                                if file_hits >= hits_per_file:
                                    break
                except Exception:
                    continue

            if len(matches) >= max_results:
                break

        return {"pattern": pattern, "filter": file_filter, "total": len(matches), "matches": matches}, None

    except Exception as e:
        return None, f"Erro na busca: {str(e)}"


# =====================================================================
# 1B — ANALISE DE IMPACTO
# =====================================================================


def find_table_references(content):
    """Encontra referencias a tabelas Protheus no codigo."""
    tables = set()
    for match in TABLE_PATTERN.finditer(content):
        candidate = match.group(1).upper()
        prefix = candidate[:2]
        if prefix in KNOWN_TABLE_PREFIXES:
            tables.add(candidate)
    return sorted(tables)


def find_function_definitions(content):
    """Encontra definicoes de funcoes AdvPL."""
    functions = []
    for match in FUNCTION_DEF_PATTERN.finditer(content):
        func_name = match.group(1)
        # Calcula numero da linha
        line_num = content[: match.start()].count("\n") + 1
        functions.append({"name": func_name, "line": line_num})
    return functions


def find_includes(content):
    """Encontra diretivas #include."""
    includes = []
    for match in INCLUDE_PATTERN.finditer(content):
        includes.append(match.group(1))
    return includes


def analyze_impact(cursor, environment_id, base_path, file_path):
    """
    Analisa impacto de um arquivo fonte cruzando com BD, processos e erros.

    Retorna:
    - Tabelas referenciadas (com detalhes do schema_cache se disponivel)
    - Processos relacionados
    - Erros conhecidos relacionados
    - Funcoes definidas
    - Includes
    """
    # Le o arquivo
    file_data, error = read_source_file(base_path, file_path)
    if error:
        return None, error

    content = file_data["content"]

    # Analise do codigo
    tables_found = find_table_references(content)
    functions = find_function_definitions(content)
    includes = find_includes(content)

    # Cruza tabelas com schema_cache (filtrando por conexoes do ambiente ativo)
    table_details = []
    if tables_found:
        placeholders = ", ".join(["%s"] * len(tables_found))
        cursor.execute(
            f"""
            SELECT UPPER(sc.table_name) AS table_name,
                   COUNT(DISTINCT sc.column_name) AS column_count
            FROM schema_cache sc
            JOIN database_connections dc ON sc.connection_id = dc.id
            WHERE dc.environment_id = %s
              AND UPPER(sc.table_name) IN ({placeholders})
            GROUP BY UPPER(sc.table_name)
        """,
            [environment_id] + tables_found,
        )
        cached_tables = {row["table_name"]: dict(row) for row in cursor.fetchall()}

        for t in tables_found:
            detail = cached_tables.get(t, {})
            table_details.append(
                {
                    "table_name": t,
                    "in_schema_cache": t in cached_tables,
                    "column_count": detail.get("column_count", 0),
                }
            )

    # Cruza com processos
    related_processes = []
    if tables_found:
        placeholders = ", ".join(["%s"] * len(tables_found))
        cursor.execute(
            f"""
            SELECT DISTINCT bp.id, bp.name, bp.module, bp.module_label,
                   pt.table_name
            FROM business_processes bp
            JOIN process_tables pt ON pt.process_id = bp.id
            WHERE UPPER(pt.table_name) IN ({placeholders})
        """,
            tables_found,
        )
        for row in cursor.fetchall():
            related_processes.append(dict(row))

    # Cruza com erros conhecidos
    related_errors = []
    # Busca por nome de tabela ou funcao nos artigos da base de conhecimento
    search_terms = tables_found[:10]  # Limita para nao sobrecarregar
    if search_terms:
        like_clauses = " OR ".join(["title ILIKE %s OR description ILIKE %s"] * len(search_terms))
        params = []
        for term in search_terms:
            params.extend([f"%{term}%", f"%{term}%"])
        cursor.execute(
            f"""
            SELECT id, title, category, tags
            FROM knowledge_articles
            WHERE {like_clauses}
            LIMIT 20
        """,
            params,
        )
        for row in cursor.fetchall():
            related_errors.append(dict(row))

    # Calcula nivel de risco
    risk_score = len(tables_found) * 2 + len(related_processes) * 3 + len(related_errors)
    if risk_score >= 15:
        risk_level = "alto"
    elif risk_score >= 7:
        risk_level = "medio"
    else:
        risk_level = "baixo"

    # Salva no cache
    file_hash = hashlib.md5(content.encode()).hexdigest()
    try:
        cursor.execute(
            """
            INSERT INTO source_impact_cache
                (environment_id, file_path, file_hash, tables_referenced, functions_defined, includes)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
        """,
            (
                environment_id,
                file_path,
                file_hash,
                json.dumps(tables_found),
                json.dumps([f["name"] for f in functions]),
                json.dumps(includes),
            ),
        )
    except Exception:
        pass  # Cache eh opcional, nao deve bloquear

    return {
        "file": file_data["name"],
        "path": file_path,
        "lines": file_data["lines"],
        "size": file_data["size"],
        "tables": table_details,
        "functions": functions,
        "includes": includes,
        "related_processes": related_processes,
        "related_errors": related_errors,
        "risk_level": risk_level,
        "risk_score": risk_score,
    }, None


# =====================================================================
# 1C — ASSISTENTE DE COMPILACAO
# =====================================================================


def diff_fontes_repo(cursor, environment_id, repo_name, branch_name):
    """
    Compara FONTES_DIR com repositorio clonado.
    Retorna lista de arquivos diferentes, novos e removidos.
    """
    from app.utils.helpers import get_base_dir_for_repo, CLONE_DIR

    fontes_dir = get_fontes_dir(cursor, environment_id)
    if not fontes_dir or not os.path.isdir(fontes_dir):
        return None, "FONTES_DIR nao configurado ou nao encontrado para este ambiente"

    # Busca repo_id pelo nome
    cursor.execute("SELECT id FROM repositories WHERE name = %s AND environment_id = %s", (repo_name, environment_id))
    repo_row = cursor.fetchone()
    if not repo_row:
        return None, f"Repositorio '{repo_name}' nao encontrado no ambiente"

    base_dir = get_base_dir_for_repo(cursor, repo_row["id"])
    repo_path = os.path.join(base_dir, repo_name, branch_name)

    if not os.path.isdir(repo_path):
        # Fallback
        repo_path = os.path.join(CLONE_DIR, repo_name, branch_name)
        if not os.path.isdir(repo_path):
            return None, f"Branch '{branch_name}' nao clonada no servidor"

    # Coleta arquivos do FONTES_DIR
    fontes_files = _collect_advpl_files(fontes_dir)
    # Coleta arquivos do repo
    repo_files = _collect_advpl_files(repo_path)

    # Compara
    fontes_set = set(fontes_files.keys())
    repo_set = set(repo_files.keys())

    only_in_fontes = sorted(fontes_set - repo_set)
    only_in_repo = sorted(repo_set - fontes_set)
    in_both = sorted(fontes_set & repo_set)

    modified = []
    unchanged = []
    for fname in in_both:
        fontes_hash = _file_hash(fontes_files[fname])
        repo_hash = _file_hash(repo_files[fname])
        if fontes_hash != repo_hash:
            modified.append(fname)
        else:
            unchanged.append(fname)

    return {
        "fontes_dir": fontes_dir,
        "repo_path": repo_path,
        "summary": {
            "modified": len(modified),
            "only_fontes": len(only_in_fontes),
            "only_repo": len(only_in_repo),
            "unchanged": len(unchanged),
            "total_fontes": len(fontes_files),
            "total_repo": len(repo_files),
        },
        "modified": modified,
        "only_in_fontes": only_in_fontes,
        "only_in_repo": only_in_repo,
    }, None


def generate_compila_txt(cursor, environment_id, file_list):
    """Gera conteudo do arquivo compila.txt a partir da lista de arquivos."""
    if not file_list:
        return None, "Lista de arquivos vazia"

    # Filtra apenas extensoes AdvPL
    valid_files = []
    for f in file_list:
        ext = os.path.splitext(f)[1].lower()
        if ext in ADVPL_EXTENSIONS:
            valid_files.append(f)

    if not valid_files:
        return None, "Nenhum arquivo AdvPL na lista"

    content = "\n".join(sorted(valid_files))
    return {"content": content, "file_count": len(valid_files), "filename": "compila.txt"}, None


def _collect_advpl_files(directory):
    """Coleta arquivos AdvPL de um diretorio (nome -> caminho completo)."""
    files = {}
    if not os.path.isdir(directory):
        return files
    try:
        for entry in os.listdir(directory):
            ext = os.path.splitext(entry)[1].lower()
            if ext in ADVPL_EXTENSIONS:
                files[entry.lower()] = os.path.join(directory, entry)
    except PermissionError:
        pass
    return files


def _file_hash(filepath):
    """Calcula hash MD5 de um arquivo."""
    try:
        h = hashlib.md5()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None
