"""
Context Pre-computation Engine — auto-discovery global na sessao.

Em vez de depender do LLM para descobrir empresa, sufixo, servicos, etc.,
este modulo faz a descoberta automaticamente no inicio da sessao e injeta
os resultados na working memory. O LLM recebe tudo pronto.

Principio: o LLM interpreta a intencao, o CODIGO cuida da logica de dominio.
"""

import logging
from app.database import get_db, release_db_connection

logger = logging.getLogger(__name__)

# Cache global por environment (evita re-discovery entre sessoes)
_precompute_cache = {}


def invalidate_cache(environment_id=None):
    """Limpa cache de pre-computacao."""
    if environment_id:
        _precompute_cache.pop(int(environment_id), None)
    else:
        _precompute_cache.clear()


def precompute_session_context(environment_id):
    """Descobre e retorna contexto completo do ambiente.

    Executa auto-discovery de:
    - Conexoes de banco com IDs e nomes
    - Empresas Protheus (SYS_COMPANY) por conexao com sufixo calculado
    - Servicos disponiveis no ambiente
    - Pipelines disponiveis no ambiente
    - Repositorios disponiveis no ambiente

    Returns:
        dict com chaves: connections, companies, services, pipelines, repositories
        Cada valor e uma lista formatada para injecao na working memory.
    """
    if not environment_id:
        return {}

    env_id = int(environment_id)

    # Usar cache se disponivel
    if env_id in _precompute_cache:
        return _precompute_cache[env_id]

    context = {
        "connections": [],
        "companies": {},  # conn_id -> [{"code": "99", "name": "TESTE", "suffix": "990"}]
        "services": [],
        "pipelines": [],
        "repositories": [],
    }

    conn = get_db()
    cursor = conn.cursor()
    try:
        # 1. Conexoes de banco
        cursor.execute(
            "SELECT id, name, driver, host, database_name "
            "FROM database_connections WHERE environment_id = %s ORDER BY name",
            (env_id,),
        )
        connections = [dict(row) for row in cursor.fetchall()]
        context["connections"] = connections

        # 2. Servicos
        cursor.execute(
            "SELECT id, name, display_name, server_name "
            "FROM server_services WHERE environment_id = %s ORDER BY name",
            (env_id,),
        )
        context["services"] = [dict(row) for row in cursor.fetchall()]

        # 3. Pipelines
        cursor.execute(
            "SELECT id, name, description "
            "FROM pipelines WHERE environment_id = %s ORDER BY name",
            (env_id,),
        )
        context["pipelines"] = [dict(row) for row in cursor.fetchall()]

        # 4. Repositorios
        cursor.execute(
            "SELECT id, name, html_url, default_branch "
            "FROM repositories WHERE environment_id = %s ORDER BY name",
            (env_id,),
        )
        context["repositories"] = [dict(row) for row in cursor.fetchall()]

    except Exception as e:
        logger.warning("Erro no precompute da sessao (env %s): %s", env_id, e)
    finally:
        release_db_connection(conn)

    # 5. Empresas Protheus por conexao (via API interna — precisa do app running)
    for c in connections:
        try:
            companies = _discover_companies_for_connection(c["id"])
            if companies:
                context["companies"][c["id"]] = companies
        except Exception as e:
            logger.debug("SYS_COMPANY indisponivel para conexao %s: %s", c["id"], e)

    # Cachear resultado
    _precompute_cache[env_id] = context
    logger.info(
        "Precompute sessao (env %s): %d conexoes, %d com empresas, %d servicos, %d pipelines, %d repos",
        env_id, len(context["connections"]),
        len(context["companies"]),
        len(context["services"]),
        len(context["pipelines"]),
        len(context["repositories"]),
    )

    return context


def _discover_companies_for_connection(conn_id):
    """Descobre empresas Protheus de uma conexao via SYS_COMPANY.

    Calcula o sufixo automaticamente (M0_CODIGO + '0').
    """
    from app.services.tools.helpers import _internal_api

    result = _internal_api(
        "POST",
        f"/api/db-connections/{conn_id}/query",
        json_body={
            "query": "SELECT M0_CODIGO, M0_NOME FROM SYS_COMPANY WHERE D_E_L_E_T_ = ' ' ORDER BY M0_CODIGO",
            "max_rows": 50,
        },
    )

    if not result or not isinstance(result, dict) or not result.get("rows"):
        return []

    companies = []
    for row in result["rows"]:
        code = str(row.get("M0_CODIGO", row.get("m0_codigo", ""))).strip()
        name = str(row.get("M0_NOME", row.get("m0_nome", ""))).strip()
        if code:
            companies.append({
                "code": code,
                "name": name,
                "suffix": f"{code}0",
            })

    return companies


def format_precomputed_context(context):
    """Formata o contexto pre-computado para injecao no system prompt.

    Formato ultra-compacto (~300-600 tokens). O LLM recebe tudo pronto
    e nunca precisa 'descobrir' empresa, sufixo ou IDs.
    """
    if not context:
        return ""

    parts = []

    # Conexoes + Empresas (a info mais critica)
    if context.get("connections"):
        parts.append("## Ambiente Pre-computado (dados reais — USE diretamente, NAO descubra)")
        parts.append("")
        parts.append("### Conexoes de Banco")
        for c in context["connections"]:
            line = f"- **ID {c['id']}**: {c.get('name', '?')} ({c.get('driver', '?')}) — {c.get('host', '?')}/{c.get('database_name', '?')}"
            companies = context.get("companies", {}).get(c["id"], [])
            if companies:
                if len(companies) == 1:
                    emp = companies[0]
                    line += f" | Empresa: **{emp['code']}** ({emp['name']}), sufixo: **{emp['suffix']}**"
                else:
                    emp_list = ", ".join(f"{e['code']}({e['name']})" for e in companies)
                    line += f" | Empresas: {emp_list}"
            parts.append(line)

        # Se todas as conexoes tem 1 empresa, destacar o sufixo global
        all_single = all(
            len(context.get("companies", {}).get(c["id"], [])) == 1
            for c in context["connections"]
            if c["id"] in context.get("companies", {})
        )
        if all_single and context.get("companies"):
            first_companies = next(iter(context["companies"].values()), [])
            if first_companies:
                suffix = first_companies[0]["suffix"]
                parts.append(f"\n**SUFIXO PADRAO: {suffix}** — use em TODAS as tabelas Protheus (SX3{suffix}, SX6{suffix}, SA1{suffix}, etc.)")
                parts.append("Tabelas SEM sufixo: SYS_COMPANY, TOP_FIELD")

    # Servicos
    if context.get("services"):
        parts.append("\n### Servicos Disponiveis")
        for s in context["services"]:
            display = s.get("display_name") or s.get("name", "?")
            parts.append(f"- **ID {s['id']}**: {display} ({s.get('server_name', '?')})")

    # Pipelines
    if context.get("pipelines"):
        parts.append("\n### Pipelines Disponiveis")
        for p in context["pipelines"]:
            desc = f" — {p['description']}" if p.get("description") else ""
            parts.append(f"- **ID {p['id']}**: {p['name']}{desc}")

    # Repositorios
    if context.get("repositories"):
        parts.append("\n### Repositorios")
        for r in context["repositories"]:
            branch = r.get("default_branch", "main")
            parts.append(f"- **ID {r['id']}**: {r['name']} (branch: {branch})")

    return "\n".join(parts)


def seed_working_memory(wm, session_id, context):
    """Popula a working memory com o contexto pre-computado.

    Registra entidades chave para que o LLM tenha acesso rapido
    durante toda a sessao.
    """
    if not context:
        return

    # Conexoes
    for c in context.get("connections", []):
        wm.add_entity(session_id, "db_connection", f"ID {c['id']}: {c.get('name', '?')}")

    # Empresas por conexao
    for conn_id, companies in context.get("companies", {}).items():
        conn_name = next((c["name"] for c in context.get("connections", []) if c["id"] == conn_id), "?")
        for emp in companies:
            wm.add_entity(
                session_id, "protheus_company",
                f"{conn_name}: empresa {emp['code']} ({emp['name']}), sufixo {emp['suffix']}",
            )

    # Servicos
    for s in context.get("services", []):
        display = s.get("display_name") or s.get("name", "?")
        wm.add_entity(session_id, "service", f"ID {s['id']}: {display}")

    # Pipelines
    for p in context.get("pipelines", []):
        wm.add_entity(session_id, "pipeline", f"ID {p['id']}: {p['name']}")

    # Repositorios
    for r in context.get("repositories", []):
        wm.add_entity(session_id, "repository", f"ID {r['id']}: {r['name']}")
