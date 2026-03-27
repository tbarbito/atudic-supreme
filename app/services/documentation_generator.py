"""
Servico de Geracao Automatica de Documentacao.
Gera documentacao tecnica em Markdown a partir dos dados dos modulos existentes:
- Dicionario de Dados (schema_cache)
- Mapa de Processos (business_processes)
- Guia de Erros (knowledge_articles)
"""

import json
import logging
from datetime import datetime

from jinja2 import Template

logger = logging.getLogger(__name__)

# ============================================================
# TEMPLATES MARKDOWN (Jinja2)
# ============================================================

TEMPLATE_DICIONARIO = Template("""# Dicionario de Dados
> Gerado em {{ generated_at }} | Conexao: {{ connection_name }} ({{ driver }})

## Sumario

- **{{ table_count }}** tabelas catalogadas
- **{{ column_count }}** campos mapeados

---

{% for table in tables %}
## {{ table.table_name }}{% if table.table_alias %} — {{ table.table_alias }}{% endif %}

| # | Campo | Tipo | Tamanho | Decimal | Chave | Nulo |
|---|-------|------|---------|---------|-------|------|
{% for col in table.columns %}| {{ loop.index }} | {{ col.column_name }} | {{ col.column_type }} | {{ col.column_size or '-' }} |\
 {{ col.column_decimal or '-' }} | {{ 'PK' if col.is_key else '' }} | {{ 'Sim' if col.is_nullable else 'Nao' }} |
{% endfor %}
{% endfor %}

---

*Documento gerado automaticamente pelo AtuDIC.*
""")

TEMPLATE_PROCESSOS = Template("""# Mapa de Processos do ERP Protheus
> Gerado em {{ generated_at }}{% if module_filter %} | Modulo: {{ module_filter }}{% endif %}

## Sumario

- **{{ process_count }}** processos mapeados
- **{{ table_count }}** tabelas vinculadas
- **{{ flow_count }}** fluxos de dados

---

{% for mod_code, mod_data in modules.items() %}
## Modulo: {{ mod_data.label }} ({{ mod_code }})

{% for proc in mod_data.processes %}
### {{ proc.name }}

{{ proc.description or 'Sem descricao.' }}

{% if proc.tables %}
**Tabelas envolvidas:**

| Tabela | Alias | Papel | Campos-chave |
|--------|-------|-------|--------------|
{% for t in proc.tables %}| {{ t.table_name }} | {{ t.table_alias or '-' }} | {{ t.table_role }} |\
 {{ t.key_fields or '-' }} |
{% endfor %}
{% endif %}

{% if proc.fields_detail %}
<details>
<summary>Campos detalhados ({{ proc.fields_detail | length }})</summary>

| Tabela | Campo | Descricao | Chave |
|--------|-------|-----------|-------|
{% for f in proc.fields_detail %}| {{ f.table_name }} | {{ f.column_name }} | {{ f.column_label or '-' }} |\
 {{ 'Sim' if f.is_key else '' }} |
{% endfor %}

</details>
{% endif %}

{% endfor %}
{% endfor %}

{% if flows %}
---

## Fluxos de Dados

| Origem | Destino | Descricao | Tabelas |
|--------|---------|-----------|---------|
{% for f in flows %}| {{ f.source_name }} | {{ f.target_name }} | {{ f.flow_label or '-' }} |\
 {{ f.flow_tables or '-' }} |
{% endfor %}
{% endif %}

---

*Documento gerado automaticamente pelo AtuDIC.*
""")

TEMPLATE_ERROS = Template("""# Guia de Erros do Protheus
> Gerado em {{ generated_at }}{% if category_filter %} | Categoria: {{ category_filter }}{% endif %}

## Sumario

- **{{ article_count }}** erros documentados
- **{{ category_count }}** categorias

---

{% for cat, articles in categories.items() %}
## {{ cat }} ({{ articles | length }} artigos)

{% for art in articles %}
### {{ art.title }}

{% if art.description %}{{ art.description }}{% endif %}

{% if art.error_pattern %}**Padrao de erro:** `{{ art.error_pattern }}`{% endif %}

{% if art.causes %}
**Causas possiveis:**
{{ art.causes }}
{% endif %}

{% if art.solution %}
**Solucao:**
{{ art.solution }}
{% endif %}

{% if art.code_snippet %}
```advpl
{{ art.code_snippet }}
```
{% endif %}

{% if art.reference_url %}**Referencia:** {{ art.reference_url }}{% endif %}

{% if art.recurrence %}> Recorrencia: {{ art.recurrence.count }}x | Ultima: {{ art.recurrence.last_seen }}{% endif %}

---

{% endfor %}
{% endfor %}

*Documento gerado automaticamente pelo AtuDIC.*
""")

TEMPLATE_COMBINADO = Template("""# Documentacao Tecnica Completa
> Gerado em {{ generated_at }}

## Indice

1. [Dicionario de Dados](#dicionario-de-dados)
2. [Mapa de Processos](#mapa-de-processos-do-erp-protheus)
3. [Guia de Erros](#guia-de-erros-do-protheus)

---

{{ section_dicionario }}

---

{{ section_processos }}

---

{{ section_erros }}
""")


# ============================================================
# FUNCOES DE GERACAO
# ============================================================


def generate_data_dictionary(cursor, connection_id=None):
    """
    Gera documentacao do dicionario de dados a partir do schema_cache.
    Se connection_id for informado, filtra por conexao; senao, gera de todas.
    """
    if connection_id:
        cursor.execute(
            "SELECT id, name, driver, host, port, database_name FROM database_connections WHERE id = %s",
            (connection_id,),
        )
        conn_info = cursor.fetchone()
        if not conn_info:
            raise ValueError(f"Conexao {connection_id} nao encontrada")
        conn_info = dict(conn_info)
        connection_name = conn_info["name"]
        driver = conn_info.get("driver", "desconhecido")

        cursor.execute(
            """
            SELECT DISTINCT table_name, table_alias
            FROM schema_cache
            WHERE connection_id = %s
            ORDER BY table_name
            """,
            (connection_id,),
        )
    else:
        connection_name = "Todas as conexoes"
        driver = "multi"
        cursor.execute("""
            SELECT DISTINCT table_name, table_alias
            FROM schema_cache
            ORDER BY table_name
            """)

    tables_raw = [dict(row) for row in cursor.fetchall()]
    tables = []
    total_columns = 0

    for t in tables_raw:
        if connection_id:
            cursor.execute(
                """
                SELECT column_name, column_type, column_size, column_decimal,
                       is_key, is_nullable, column_order
                FROM schema_cache
                WHERE connection_id = %s AND table_name = %s
                ORDER BY column_order
                """,
                (connection_id, t["table_name"]),
            )
        else:
            cursor.execute(
                """
                SELECT column_name, column_type, column_size, column_decimal,
                       is_key, is_nullable, column_order
                FROM schema_cache
                WHERE table_name = %s
                ORDER BY column_order
                """,
                (t["table_name"],),
            )
        columns = [dict(row) for row in cursor.fetchall()]
        total_columns += len(columns)
        tables.append(
            {
                "table_name": t["table_name"],
                "table_alias": t.get("table_alias", ""),
                "columns": columns,
            }
        )

    content_md = TEMPLATE_DICIONARIO.render(
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        connection_name=connection_name,
        driver=driver,
        table_count=len(tables),
        column_count=total_columns,
        tables=tables,
    )

    metadata = {
        "connection_id": connection_id,
        "connection_name": connection_name,
        "table_count": len(tables),
        "column_count": total_columns,
    }

    return {"title": f"Dicionario de Dados - {connection_name}", "content_md": content_md, "metadata": metadata}


def generate_process_map(cursor, module=None):
    """
    Gera documentacao do mapa de processos a partir de business_processes.
    Se module for informado, filtra por modulo.
    """
    if module:
        cursor.execute(
            """
            SELECT id, name, description, module, module_label, icon, color
            FROM business_processes
            WHERE module = %s AND status = 'active'
            ORDER BY module, name
            """,
            (module,),
        )
    else:
        cursor.execute("""
            SELECT id, name, description, module, module_label, icon, color
            FROM business_processes
            WHERE status = 'active'
            ORDER BY module, name
            """)

    processes = [dict(row) for row in cursor.fetchall()]
    modules = {}
    total_tables = 0

    for proc in processes:
        mod = proc["module"]
        if mod not in modules:
            modules[mod] = {"label": proc.get("module_label", mod), "processes": []}

        # Buscar tabelas do processo
        cursor.execute(
            """
            SELECT id, table_name, table_alias, table_role, description
            FROM process_tables
            WHERE process_id = %s
            ORDER BY sort_order
            """,
            (proc["id"],),
        )
        tables = [dict(row) for row in cursor.fetchall()]
        total_tables += len(tables)

        # Para cada tabela, buscar campos-chave
        fields_detail = []
        for t in tables:
            cursor.execute(
                """
                SELECT column_name, column_label, is_key
                FROM process_fields
                WHERE process_table_id = %s
                ORDER BY is_key DESC, column_name
                """,
                (t["id"],),
            )
            fields = [dict(row) for row in cursor.fetchall()]
            t["key_fields"] = ", ".join(f["column_name"] for f in fields if f.get("is_key"))
            for f in fields:
                f["table_name"] = t["table_name"]
                fields_detail.append(f)

        proc_data = {
            "name": proc["name"],
            "description": proc.get("description", ""),
            "tables": tables,
            "fields_detail": fields_detail,
        }
        modules[mod]["processes"].append(proc_data)

    # Buscar fluxos
    if module:
        cursor.execute(
            """
            SELECT pf.id, pf.description as flow_label,
                   pf.source_table || ' -> ' || pf.target_table as flow_tables,
                   pf.flow_type,
                   sp.name as source_name, tp.name as target_name
            FROM process_flows pf
            JOIN business_processes sp ON pf.source_process_id = sp.id
            JOIN business_processes tp ON pf.target_process_id = tp.id
            WHERE sp.module = %s OR tp.module = %s
            ORDER BY sp.name, tp.name
            """,
            (module, module),
        )
    else:
        cursor.execute("""
            SELECT pf.id, pf.description as flow_label,
                   pf.source_table || ' -> ' || pf.target_table as flow_tables,
                   pf.flow_type,
                   sp.name as source_name, tp.name as target_name
            FROM process_flows pf
            JOIN business_processes sp ON pf.source_process_id = sp.id
            JOIN business_processes tp ON pf.target_process_id = tp.id
            ORDER BY sp.name, tp.name
            """)
    flows = [dict(row) for row in cursor.fetchall()]

    content_md = TEMPLATE_PROCESSOS.render(
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        module_filter=module,
        process_count=len(processes),
        table_count=total_tables,
        flow_count=len(flows),
        modules=modules,
        flows=flows,
    )

    metadata = {
        "module": module,
        "process_count": len(processes),
        "table_count": total_tables,
        "flow_count": len(flows),
    }

    title = "Mapa de Processos"
    if module:
        title += f" - {module}"

    return {"title": title, "content_md": content_md, "metadata": metadata}


def generate_error_guide(cursor, category=None):
    """
    Gera guia de erros a partir dos knowledge_articles e alert_recurrence.
    Se category for informado, filtra por categoria.
    """
    if category:
        cursor.execute(
            """
            SELECT id, title, category, error_pattern, description, causes,
                   solution, code_snippet, reference_url, tags, usage_count
            FROM knowledge_articles
            WHERE is_active = TRUE AND category = %s
            ORDER BY category, usage_count DESC, title
            """,
            (category,),
        )
    else:
        cursor.execute("""
            SELECT id, title, category, error_pattern, description, causes,
                   solution, code_snippet, reference_url, tags, usage_count
            FROM knowledge_articles
            WHERE is_active = TRUE
            ORDER BY category, usage_count DESC, title
            """)

    articles = [dict(row) for row in cursor.fetchall()]

    # Buscar recorrencia dos erros (se existir tabela alert_recurrence)
    recurrence_map = {}
    try:
        cursor.execute("SAVEPOINT sp_recurrence")
        cursor.execute("""
            SELECT category, alert_hash, count, last_seen, suggestion
            FROM alert_recurrence
            ORDER BY count DESC
            """)
        for row in cursor.fetchall():
            r = dict(row)
            key = r["category"]
            if key not in recurrence_map:
                recurrence_map[key] = r
        cursor.execute("RELEASE SAVEPOINT sp_recurrence")
    except Exception:
        try:
            cursor.execute("ROLLBACK TO SAVEPOINT sp_recurrence")
        except Exception:
            pass

    categories = {}
    for art in articles:
        cat = art["category"]
        if cat not in categories:
            categories[cat] = []
        art["recurrence"] = recurrence_map.get(cat)
        categories[cat].append(art)

    content_md = TEMPLATE_ERROS.render(
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        category_filter=category,
        article_count=len(articles),
        category_count=len(categories),
        categories=categories,
    )

    metadata = {
        "category": category,
        "article_count": len(articles),
        "category_count": len(categories),
    }

    title = "Guia de Erros"
    if category:
        title += f" - {category}"

    return {"title": title, "content_md": content_md, "metadata": metadata}


def generate_combined(cursor, connection_id=None, module=None, category=None):
    """
    Gera documentacao combinada com todas as secoes.
    """
    sections = {}

    # Dicionario de dados (so se tiver conexao ou schema_cache)
    try:
        cursor.execute("SAVEPOINT sp_dict")
        dict_result = generate_data_dictionary(cursor, connection_id)
        sections["dicionario"] = dict_result["content_md"]
        cursor.execute("RELEASE SAVEPOINT sp_dict")
    except Exception as e:
        logger.warning("generate_combined: dicionario falhou: %s", e)
        cursor.execute("ROLLBACK TO SAVEPOINT sp_dict")
        sections["dicionario"] = "*Nenhuma conexao de banco configurada.*"

    # Mapa de processos
    try:
        cursor.execute("SAVEPOINT sp_proc")
        proc_result = generate_process_map(cursor, module)
        sections["processos"] = proc_result["content_md"]
        cursor.execute("RELEASE SAVEPOINT sp_proc")
    except Exception as e:
        logger.warning("generate_combined: processos falhou: %s", e)
        cursor.execute("ROLLBACK TO SAVEPOINT sp_proc")
        sections["processos"] = "*Nenhum processo mapeado.*"

    # Guia de erros
    try:
        cursor.execute("SAVEPOINT sp_err")
        err_result = generate_error_guide(cursor, category)
        sections["erros"] = err_result["content_md"]
        cursor.execute("RELEASE SAVEPOINT sp_err")
    except Exception as e:
        logger.warning("generate_combined: erros falhou: %s", e)
        cursor.execute("ROLLBACK TO SAVEPOINT sp_err")
        sections["erros"] = "*Nenhum artigo na base de conhecimento.*"

    content_md = TEMPLATE_COMBINADO.render(
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        section_dicionario=sections["dicionario"],
        section_processos=sections["processos"],
        section_erros=sections["erros"],
    )

    metadata = {
        "connection_id": connection_id,
        "module": module,
        "category": category,
        "type": "combinado",
    }

    return {"title": "Documentacao Tecnica Completa", "content_md": content_md, "metadata": metadata}


# ============================================================
# FUNCOES CRUD
# ============================================================


def save_document(cursor, title, doc_type, content_md, metadata, user_id):
    """
    Salva documento gerado com versionamento.
    Se ja existir documento com mesmo titulo, incrementa versao.
    """
    # Verificar versao anterior
    cursor.execute(
        "SELECT id, version FROM generated_docs WHERE title = %s ORDER BY version DESC LIMIT 1",
        (title,),
    )
    existing = cursor.fetchone()

    if existing:
        existing = dict(existing)
        new_version = existing["version"] + 1
        parent_id = existing["id"]
    else:
        new_version = 1
        parent_id = None

    file_size = len(content_md.encode("utf-8"))

    cursor.execute(
        """
        INSERT INTO generated_docs (title, doc_type, content_md, metadata, version, parent_id, file_size, generated_by)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (title, doc_type, content_md, json.dumps(metadata), new_version, parent_id, file_size, user_id),
    )

    doc_id = cursor.fetchone()["id"]
    return {"id": doc_id, "version": new_version, "file_size": file_size}


def list_documents(cursor, doc_type=None, limit=50, offset=0):
    """
    Lista documentos sem content_md (performance).
    """
    conditions = ["1=1"]
    params = []

    if doc_type:
        conditions.append("gd.doc_type = %s")
        params.append(doc_type)

    where = " AND ".join(conditions)

    cursor.execute(f"SELECT COUNT(*) as total FROM generated_docs gd WHERE {where}", params)
    total = cursor.fetchone()["total"]

    cursor.execute(
        f"""
        SELECT gd.id, gd.title, gd.doc_type, gd.doc_format, gd.metadata,
               gd.version, gd.parent_id, gd.file_size, gd.generated_at,
               u.username as generated_by_name
        FROM generated_docs gd
        LEFT JOIN users u ON gd.generated_by = u.id
        WHERE {where}
        ORDER BY gd.generated_at DESC
        LIMIT %s OFFSET %s
        """,
        params + [limit, offset],
    )

    docs = []
    for row in cursor.fetchall():
        doc = dict(row)
        if doc.get("generated_at"):
            doc["generated_at"] = doc["generated_at"].isoformat()
        if doc.get("metadata") and isinstance(doc["metadata"], str):
            doc["metadata"] = json.loads(doc["metadata"])
        docs.append(doc)

    return {"docs": docs, "total": total}


def get_document(cursor, doc_id):
    """Retorna documento completo incluindo content_md."""
    cursor.execute(
        """
        SELECT gd.*, u.username as generated_by_name
        FROM generated_docs gd
        LEFT JOIN users u ON gd.generated_by = u.id
        WHERE gd.id = %s
        """,
        (doc_id,),
    )
    row = cursor.fetchone()
    if not row:
        return None

    doc = dict(row)
    if doc.get("generated_at"):
        doc["generated_at"] = doc["generated_at"].isoformat()
    if doc.get("metadata") and isinstance(doc["metadata"], str):
        doc["metadata"] = json.loads(doc["metadata"])
    return doc


def get_document_versions(cursor, doc_id):
    """Lista versoes anteriores de um documento."""
    cursor.execute("SELECT title FROM generated_docs WHERE id = %s", (doc_id,))
    row = cursor.fetchone()
    if not row:
        return []

    title = dict(row)["title"]

    cursor.execute(
        """
        SELECT gd.id, gd.version, gd.file_size, gd.generated_at,
               u.username as generated_by_name
        FROM generated_docs gd
        LEFT JOIN users u ON gd.generated_by = u.id
        WHERE gd.title = %s
        ORDER BY gd.version DESC
        """,
        (title,),
    )

    versions = []
    for row in cursor.fetchall():
        v = dict(row)
        if v.get("generated_at"):
            v["generated_at"] = v["generated_at"].isoformat()
        versions.append(v)

    return versions


def delete_document(cursor, doc_id):
    """Remove documento."""
    cursor.execute("SELECT id FROM generated_docs WHERE id = %s", (doc_id,))
    if not cursor.fetchone():
        return False
    cursor.execute("DELETE FROM generated_docs WHERE id = %s", (doc_id,))
    return True
