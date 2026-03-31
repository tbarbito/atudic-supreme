"""
Query Templates Protheus — o LLM escolhe o template, o codigo monta o SQL.

Em vez do LLM escrever SQL bruto (e errar sufixo, empresa, nomes de coluna),
ele chama query_database com template + params semanticos simples.

O codigo injeta sufixo correto, monta a query e executa.
"""

import logging

logger = logging.getLogger(__name__)

# Templates de query parametrizados
# Cada template tem: descricao, sql (com {suffix} para injecao), params esperados
TEMPLATES = {
    "parametro": {
        "description": "Buscar valor de parametro MV_* na SX6",
        "sql": "SELECT X6_VAR, X6_CONTEUD, X6_TIPO, X6_DESCRIC FROM SX6{suffix} WHERE X6_VAR = '{param_name}'",
        "params": ["param_name"],
        "example": '{"template": "parametro", "param_name": "MV_ESTNEG"}',
    },
    "parametros_modulo": {
        "description": "Listar parametros MV_* de um modulo/prefixo",
        "sql": "SELECT TOP {limit} X6_VAR, X6_CONTEUD, X6_TIPO, X6_DESCRIC FROM SX6{suffix} WHERE X6_VAR LIKE '{prefix}%' ORDER BY X6_VAR",
        "params": ["prefix"],
        "defaults": {"limit": "20"},
        "example": '{"template": "parametros_modulo", "prefix": "MV_COM"}',
    },
    "campos_tabela": {
        "description": "Listar campos de uma tabela Protheus (SX3)",
        "sql": "SELECT X3_CAMPO, X3_TITULO, X3_DESCRIC, X3_TIPO, X3_TAMANHO, X3_DECIMAL, X3_OBRIGAT FROM SX3{suffix} WHERE X3_ARQUIVO = '{table_alias}' ORDER BY X3_ORDEM",
        "params": ["table_alias"],
        "example": '{"template": "campos_tabela", "table_alias": "SA1"}',
    },
    "indices_tabela": {
        "description": "Listar indices de uma tabela (SIX)",
        "sql": "SELECT INDICE, ORDEM, CHAVE, DESCRICAO, SHOWPESQ FROM SIX{suffix} WHERE INDICE = '{table_alias}' ORDER BY ORDEM",
        "params": ["table_alias"],
        "example": '{"template": "indices_tabela", "table_alias": "SA1"}',
    },
    "tabelas": {
        "description": "Listar tabelas do dicionario (SX2)",
        "sql": "SELECT X2_CHAVE AS ALIAS, X2_NOME AS NOME, X2_MODO AS MODO FROM SX2{suffix} ORDER BY X2_CHAVE",
        "params": [],
        "example": '{"template": "tabelas"}',
    },
    "tabela_info": {
        "description": "Info de uma tabela especifica (SX2)",
        "sql": "SELECT X2_CHAVE, X2_NOME, X2_MODO, X2_MODOUN FROM SX2{suffix} WHERE X2_CHAVE = '{table_alias}'",
        "params": ["table_alias"],
        "example": '{"template": "tabela_info", "table_alias": "SA1"}',
    },
    "gatilhos_campo": {
        "description": "Gatilhos (triggers) de um campo (SX7)",
        "sql": "SELECT X7_CAMPO, X7_SEQUENC, X7_CDOMIN, X7_TIPO, X7_REGRA, X7_SEEK FROM SX7{suffix} WHERE X7_CAMPO = '{field_name}' ORDER BY X7_SEQUENC",
        "params": ["field_name"],
        "example": '{"template": "gatilhos_campo", "field_name": "A1_COD"}',
    },
    "tabelas_genericas": {
        "description": "Consultar tabela generica SX5 por chave",
        "sql": "SELECT X5_TABELA, X5_CHAVE, X5_DESCRI FROM SX5{suffix} WHERE X5_TABELA = '{tab_key}' ORDER BY X5_CHAVE",
        "params": ["tab_key"],
        "example": '{"template": "tabelas_genericas", "tab_key": "01"}',
    },
    "empresas": {
        "description": "Listar empresas cadastradas (SYS_COMPANY)",
        "sql": "SELECT M0_CODIGO, M0_NOME, M0_CGC FROM SYS_COMPANY WHERE D_E_L_E_T_ = ' ' ORDER BY M0_CODIGO",
        "params": [],
        "no_suffix": True,
        "example": '{"template": "empresas"}',
    },
    "dados_tabela": {
        "description": "Consultar dados de uma tabela de negocio (SA1, SC5, etc.)",
        "sql": "SELECT TOP {limit} * FROM {table_alias}{suffix} WHERE D_E_L_E_T_ = ' ' {where_clause} ORDER BY R_E_C_N_O_ DESC",
        "params": ["table_alias"],
        "defaults": {"limit": "10", "where_clause": ""},
        "example": '{"template": "dados_tabela", "table_alias": "SA1", "limit": "5"}',
    },
    "count_tabela": {
        "description": "Contar registros de uma tabela",
        "sql": "SELECT COUNT(*) AS TOTAL FROM {table_alias}{suffix} WHERE D_E_L_E_T_ = ' '",
        "params": ["table_alias"],
        "example": '{"template": "count_tabela", "table_alias": "SA1"}',
    },
}


def get_suffix_for_connection(conn_id, precomputed_context):
    """Retorna o sufixo correto para uma conexao a partir do contexto pre-computado.

    Se ha 1 empresa, retorna o sufixo diretamente.
    Se ha N empresas, retorna None (LLM precisa perguntar).
    """
    companies = precomputed_context.get("companies", {}).get(conn_id, [])
    # Tambem aceita conn_id como int ou str
    if not companies:
        companies = precomputed_context.get("companies", {}).get(int(conn_id) if isinstance(conn_id, str) else conn_id, [])

    if len(companies) == 1:
        return companies[0]["suffix"]
    return None


def resolve_template(template_name, params, conn_id, precomputed_context):
    """Resolve um template em uma query SQL pronta para execucao.

    Args:
        template_name: Nome do template (ex: "parametro")
        params: Dict com parametros do template (ex: {"param_name": "MV_ESTNEG"})
        conn_id: ID da conexao (para buscar sufixo)
        precomputed_context: Contexto pre-computado da sessao

    Returns:
        tuple: (query_sql, error_message)
        Se sucesso: (sql, None)
        Se erro: (None, mensagem_de_erro)
    """
    template = TEMPLATES.get(template_name)
    if not template:
        available = ", ".join(sorted(TEMPLATES.keys()))
        return None, f"Template '{template_name}' nao encontrado. Disponiveis: {available}"

    # Verificar params obrigatorios
    for p in template["params"]:
        if p not in params or not params[p]:
            return None, f"Parametro '{p}' e obrigatorio para o template '{template_name}'. Exemplo: {template['example']}"

    # Resolver sufixo
    suffix = ""
    if not template.get("no_suffix"):
        suffix = get_suffix_for_connection(conn_id, precomputed_context)
        if suffix is None:
            # Multiplas empresas — checar se o LLM informou company_code
            company_code = params.get("company_code")
            if company_code:
                suffix = f"{company_code.strip()}0"
            else:
                companies = precomputed_context.get("companies", {}).get(conn_id, [])
                if companies:
                    emp_list = ", ".join(f"{e['code']} ({e['name']})" for e in companies)
                    return None, f"Existem {len(companies)} empresas nesta conexao: {emp_list}. Informe company_code para montar o sufixo."
                else:
                    # Sem info de empresa — tentar sem sufixo
                    suffix = ""

    # Aplicar defaults
    for key, default in template.get("defaults", {}).items():
        if key not in params or not params[key]:
            params[key] = default

    # Montar SQL
    try:
        # Uppercase em valores de tabela/campo (Protheus exige)
        for key in ("table_alias", "field_name", "param_name", "prefix"):
            if key in params and isinstance(params[key], str):
                params[key] = params[key].upper()

        sql = template["sql"].format(suffix=suffix, **params)
        logger.info("Template '%s' resolvido: %s", template_name, sql[:200])
        return sql, None
    except KeyError as e:
        return None, f"Parametro faltante no template: {e}"


def get_templates_prompt():
    """Retorna descricao dos templates para injecao no prompt do LLM.

    Formato compacto para o LLM escolher o template correto.
    """
    lines = [
        "### Query Templates Protheus (use em vez de SQL bruto)",
        "Ao chamar `query_database`, prefira usar `template` + params em vez de `query` raw.",
        "O sistema injeta sufixo e empresa automaticamente.",
        "",
    ]

    for name, t in sorted(TEMPLATES.items()):
        params_str = ", ".join(t["params"]) if t["params"] else "(nenhum)"
        lines.append(f"- **{name}**: {t['description']} | params: {params_str}")
        lines.append(f"  Ex: {t['example']}")

    return "\n".join(lines)
