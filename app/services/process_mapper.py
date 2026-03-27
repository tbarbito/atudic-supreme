"""
Serviço de mapeamento de processos de negócio do ERP Protheus.

Gerencia processos, tabelas vinculadas, campos e fluxos de dados.
Inclui seed com processos padrão do Protheus.
"""

import logging

logger = logging.getLogger(__name__)

# =====================================================================
# MÓDULOS PADRÃO DO PROTHEUS
# =====================================================================
PROTHEUS_MODULES = [
    {"code": "FAT", "label": "Faturamento", "icon": "fa-file-invoice-dollar", "color": "#28a745"},
    {"code": "COM", "label": "Compras", "icon": "fa-shopping-cart", "color": "#17a2b8"},
    {"code": "FIN", "label": "Financeiro", "icon": "fa-coins", "color": "#ffc107"},
    {"code": "EST", "label": "Estoque/Custos", "icon": "fa-warehouse", "color": "#fd7e14"},
    {"code": "CON", "label": "Contabilidade", "icon": "fa-calculator", "color": "#6f42c1"},
    {"code": "FIS", "label": "Fiscal", "icon": "fa-balance-scale", "color": "#dc3545"},
    {"code": "ATF", "label": "Ativo Fixo", "icon": "fa-building", "color": "#6c757d"},
    {"code": "RH", "label": "Gestão de Pessoal", "icon": "fa-users", "color": "#20c997"},
    {"code": "MNT", "label": "Manutenção de Ativos", "icon": "fa-tools", "color": "#e83e8c"},
    {"code": "QUA", "label": "Qualidade", "icon": "fa-check-double", "color": "#007bff"},
]

# =====================================================================
# SEED DE PROCESSOS PADRÃO
# =====================================================================
DEFAULT_PROCESSES = [
    {
        "name": "Pedido de Venda",
        "description": "Processo completo de pedido de venda: cadastro, aprovação, liberação e geração de NF.",
        "module": "FAT",
        "module_label": "Faturamento",
        "icon": "fa-file-invoice-dollar",
        "color": "#28a745",
        "tables": [
            {"table_name": "SC5", "table_alias": "Cabeçalho do Pedido de Venda", "table_role": "principal",
             "fields": [
                 {"column_name": "C5_NUM", "column_label": "Número do Pedido", "is_key": True},
                 {"column_name": "C5_CLIENTE", "column_label": "Código do Cliente", "is_key": True},
                 {"column_name": "C5_LOJACLI", "column_label": "Loja do Cliente"},
                 {"column_name": "C5_EMISSAO", "column_label": "Data de Emissão"},
                 {"column_name": "C5_CONDPAG", "column_label": "Condição de Pagamento"},
                 {"column_name": "C5_LIBEROK", "column_label": "Liberado para Faturamento"},
             ]},
            {"table_name": "SC6", "table_alias": "Itens do Pedido de Venda", "table_role": "principal",
             "fields": [
                 {"column_name": "C6_NUM", "column_label": "Número do Pedido", "is_key": True},
                 {"column_name": "C6_ITEM", "column_label": "Item", "is_key": True},
                 {"column_name": "C6_PRODUTO", "column_label": "Código do Produto"},
                 {"column_name": "C6_QTDVEN", "column_label": "Quantidade Vendida"},
                 {"column_name": "C6_PRCVEN", "column_label": "Preço de Venda"},
                 {"column_name": "C6_VALOR", "column_label": "Valor Total do Item"},
             ]},
            {"table_name": "SA1", "table_alias": "Cadastro de Clientes", "table_role": "relacionada",
             "fields": [
                 {"column_name": "A1_COD", "column_label": "Código do Cliente", "is_key": True},
                 {"column_name": "A1_LOJA", "column_label": "Loja", "is_key": True},
                 {"column_name": "A1_NOME", "column_label": "Razão Social"},
                 {"column_name": "A1_CGC", "column_label": "CNPJ/CPF"},
             ]},
        ],
    },
    {
        "name": "Faturamento (NF Saída)",
        "description": "Geração de notas fiscais de saída a partir de pedidos liberados.",
        "module": "FAT",
        "module_label": "Faturamento",
        "icon": "fa-file-invoice",
        "color": "#28a745",
        "tables": [
            {"table_name": "SF2", "table_alias": "Cabeçalho da NF de Saída", "table_role": "principal",
             "fields": [
                 {"column_name": "F2_DOC", "column_label": "Número da NF", "is_key": True},
                 {"column_name": "F2_SERIE", "column_label": "Série", "is_key": True},
                 {"column_name": "F2_CLIENTE", "column_label": "Código do Cliente"},
                 {"column_name": "F2_LOJA", "column_label": "Loja do Cliente"},
                 {"column_name": "F2_EMISSAO", "column_label": "Data de Emissão"},
                 {"column_name": "F2_VALBRUT", "column_label": "Valor Bruto"},
             ]},
            {"table_name": "SD2", "table_alias": "Itens da NF de Saída", "table_role": "principal",
             "fields": [
                 {"column_name": "D2_DOC", "column_label": "Número da NF", "is_key": True},
                 {"column_name": "D2_ITEM", "column_label": "Item", "is_key": True},
                 {"column_name": "D2_COD", "column_label": "Código do Produto"},
                 {"column_name": "D2_QUANT", "column_label": "Quantidade"},
                 {"column_name": "D2_PRCVEN", "column_label": "Preço Unitário"},
                 {"column_name": "D2_TOTAL", "column_label": "Valor Total"},
             ]},
        ],
    },
    {
        "name": "Solicitação de Compras",
        "description": "Solicitações internas de compra de materiais e serviços.",
        "module": "COM",
        "module_label": "Compras",
        "icon": "fa-clipboard-list",
        "color": "#17a2b8",
        "tables": [
            {"table_name": "SC1", "table_alias": "Solicitações de Compras", "table_role": "principal",
             "fields": [
                 {"column_name": "C1_NUM", "column_label": "Número da Solicitação", "is_key": True},
                 {"column_name": "C1_ITEM", "column_label": "Item", "is_key": True},
                 {"column_name": "C1_PRODUTO", "column_label": "Código do Produto"},
                 {"column_name": "C1_QUANT", "column_label": "Quantidade Solicitada"},
                 {"column_name": "C1_DATPRF", "column_label": "Data de Necessidade"},
                 {"column_name": "C1_APROV", "column_label": "Status de Aprovação"},
             ]},
        ],
    },
    {
        "name": "Pedido de Compras",
        "description": "Pedidos de compra emitidos a fornecedores, vinculados a solicitações aprovadas.",
        "module": "COM",
        "module_label": "Compras",
        "icon": "fa-shopping-cart",
        "color": "#17a2b8",
        "tables": [
            {"table_name": "SC7", "table_alias": "Pedidos de Compra", "table_role": "principal",
             "fields": [
                 {"column_name": "C7_NUM", "column_label": "Número do Pedido", "is_key": True},
                 {"column_name": "C7_ITEM", "column_label": "Item", "is_key": True},
                 {"column_name": "C7_PRODUTO", "column_label": "Código do Produto"},
                 {"column_name": "C7_QUANT", "column_label": "Quantidade"},
                 {"column_name": "C7_PRECO", "column_label": "Preço Unitário"},
                 {"column_name": "C7_TOTAL", "column_label": "Valor Total"},
                 {"column_name": "C7_FORNECE", "column_label": "Código do Fornecedor"},
             ]},
            {"table_name": "SA2", "table_alias": "Cadastro de Fornecedores", "table_role": "relacionada",
             "fields": [
                 {"column_name": "A2_COD", "column_label": "Código do Fornecedor", "is_key": True},
                 {"column_name": "A2_LOJA", "column_label": "Loja", "is_key": True},
                 {"column_name": "A2_NOME", "column_label": "Razão Social"},
                 {"column_name": "A2_CGC", "column_label": "CNPJ"},
             ]},
        ],
    },
    {
        "name": "Entrada de NF (Recebimento)",
        "description": "Recebimento de notas fiscais de entrada de materiais e serviços.",
        "module": "COM",
        "module_label": "Compras",
        "icon": "fa-truck-loading",
        "color": "#17a2b8",
        "tables": [
            {"table_name": "SF1", "table_alias": "Cabeçalho da NF de Entrada", "table_role": "principal",
             "fields": [
                 {"column_name": "F1_DOC", "column_label": "Número da NF", "is_key": True},
                 {"column_name": "F1_SERIE", "column_label": "Série", "is_key": True},
                 {"column_name": "F1_FORNECE", "column_label": "Código do Fornecedor"},
                 {"column_name": "F1_EMISSAO", "column_label": "Data de Emissão"},
                 {"column_name": "F1_VALBRUT", "column_label": "Valor Bruto"},
             ]},
            {"table_name": "SD1", "table_alias": "Itens da NF de Entrada", "table_role": "principal",
             "fields": [
                 {"column_name": "D1_DOC", "column_label": "Número da NF", "is_key": True},
                 {"column_name": "D1_ITEM", "column_label": "Item", "is_key": True},
                 {"column_name": "D1_COD", "column_label": "Código do Produto"},
                 {"column_name": "D1_QUANT", "column_label": "Quantidade"},
                 {"column_name": "D1_VUNIT", "column_label": "Valor Unitário"},
                 {"column_name": "D1_TOTAL", "column_label": "Valor Total"},
             ]},
        ],
    },
    {
        "name": "Contas a Receber",
        "description": "Gestão de títulos a receber gerados pelo faturamento.",
        "module": "FIN",
        "module_label": "Financeiro",
        "icon": "fa-hand-holding-usd",
        "color": "#ffc107",
        "tables": [
            {"table_name": "SE1", "table_alias": "Contas a Receber", "table_role": "principal",
             "fields": [
                 {"column_name": "E1_PREFIXO", "column_label": "Prefixo", "is_key": True},
                 {"column_name": "E1_NUM", "column_label": "Número do Título", "is_key": True},
                 {"column_name": "E1_PARCELA", "column_label": "Parcela", "is_key": True},
                 {"column_name": "E1_TIPO", "column_label": "Tipo do Título"},
                 {"column_name": "E1_CLIENTE", "column_label": "Código do Cliente"},
                 {"column_name": "E1_EMISSAO", "column_label": "Data de Emissão"},
                 {"column_name": "E1_VENCTO", "column_label": "Data de Vencimento"},
                 {"column_name": "E1_VALOR", "column_label": "Valor do Título"},
                 {"column_name": "E1_SALDO", "column_label": "Saldo em Aberto"},
             ]},
        ],
    },
    {
        "name": "Contas a Pagar",
        "description": "Gestão de títulos a pagar gerados pelas compras e outras obrigações.",
        "module": "FIN",
        "module_label": "Financeiro",
        "icon": "fa-money-bill-wave",
        "color": "#ffc107",
        "tables": [
            {"table_name": "SE2", "table_alias": "Contas a Pagar", "table_role": "principal",
             "fields": [
                 {"column_name": "E2_PREFIXO", "column_label": "Prefixo", "is_key": True},
                 {"column_name": "E2_NUM", "column_label": "Número do Título", "is_key": True},
                 {"column_name": "E2_PARCELA", "column_label": "Parcela", "is_key": True},
                 {"column_name": "E2_TIPO", "column_label": "Tipo do Título"},
                 {"column_name": "E2_FORNECE", "column_label": "Código do Fornecedor"},
                 {"column_name": "E2_EMISSAO", "column_label": "Data de Emissão"},
                 {"column_name": "E2_VENCTO", "column_label": "Data de Vencimento"},
                 {"column_name": "E2_VALOR", "column_label": "Valor do Título"},
                 {"column_name": "E2_SALDO", "column_label": "Saldo em Aberto"},
             ]},
        ],
    },
    {
        "name": "Movimentação Bancária",
        "description": "Controle de movimentações financeiras nas contas bancárias.",
        "module": "FIN",
        "module_label": "Financeiro",
        "icon": "fa-university",
        "color": "#ffc107",
        "tables": [
            {"table_name": "SE5", "table_alias": "Movimentação Bancária", "table_role": "principal",
             "fields": [
                 {"column_name": "E5_DATA", "column_label": "Data do Movimento"},
                 {"column_name": "E5_BANCO", "column_label": "Código do Banco"},
                 {"column_name": "E5_AGENCIA", "column_label": "Agência"},
                 {"column_name": "E5_CONTA", "column_label": "Conta Corrente"},
                 {"column_name": "E5_VALOR", "column_label": "Valor"},
                 {"column_name": "E5_HISTOR", "column_label": "Histórico"},
             ]},
            {"table_name": "SA6", "table_alias": "Cadastro de Bancos", "table_role": "relacionada",
             "fields": [
                 {"column_name": "A6_COD", "column_label": "Código do Banco", "is_key": True},
                 {"column_name": "A6_AGENCIA", "column_label": "Agência", "is_key": True},
                 {"column_name": "A6_CONTA", "column_label": "Conta", "is_key": True},
                 {"column_name": "A6_NOME", "column_label": "Nome do Banco"},
             ]},
        ],
    },
    {
        "name": "Controle de Estoque",
        "description": "Gestão de saldos, movimentações e localização de produtos no estoque.",
        "module": "EST",
        "module_label": "Estoque/Custos",
        "icon": "fa-warehouse",
        "color": "#fd7e14",
        "tables": [
            {"table_name": "SB1", "table_alias": "Cadastro de Produtos", "table_role": "principal",
             "fields": [
                 {"column_name": "B1_COD", "column_label": "Código do Produto", "is_key": True},
                 {"column_name": "B1_DESC", "column_label": "Descrição"},
                 {"column_name": "B1_TIPO", "column_label": "Tipo do Produto"},
                 {"column_name": "B1_UM", "column_label": "Unidade de Medida"},
                 {"column_name": "B1_GRUPO", "column_label": "Grupo de Produto"},
                 {"column_name": "B1_PRV1", "column_label": "Preço de Venda"},
             ]},
            {"table_name": "SB2", "table_alias": "Saldos em Estoque", "table_role": "principal",
             "fields": [
                 {"column_name": "B2_COD", "column_label": "Código do Produto", "is_key": True},
                 {"column_name": "B2_LOCAL", "column_label": "Armazém", "is_key": True},
                 {"column_name": "B2_QATU", "column_label": "Quantidade Atual"},
                 {"column_name": "B2_RESERVA", "column_label": "Quantidade Reservada"},
                 {"column_name": "B2_CM1", "column_label": "Custo Médio"},
             ]},
            {"table_name": "SD3", "table_alias": "Movimentações Internas", "table_role": "auxiliar",
             "fields": [
                 {"column_name": "D3_DOC", "column_label": "Documento"},
                 {"column_name": "D3_COD", "column_label": "Código do Produto"},
                 {"column_name": "D3_QUANT", "column_label": "Quantidade"},
                 {"column_name": "D3_TM", "column_label": "Tipo de Movimento"},
                 {"column_name": "D3_EMISSAO", "column_label": "Data de Emissão"},
             ]},
        ],
    },
    {
        "name": "Contabilidade",
        "description": "Plano de contas e lançamentos contábeis do sistema.",
        "module": "CON",
        "module_label": "Contabilidade",
        "icon": "fa-calculator",
        "color": "#6f42c1",
        "tables": [
            {"table_name": "CT1", "table_alias": "Plano de Contas", "table_role": "principal",
             "fields": [
                 {"column_name": "CT1_CONTA", "column_label": "Conta Contábil", "is_key": True},
                 {"column_name": "CT1_DESC01", "column_label": "Descrição"},
                 {"column_name": "CT1_CLASSE", "column_label": "Classe (Sintética/Analítica)"},
                 {"column_name": "CT1_NORMAL", "column_label": "Natureza (D/C)"},
             ]},
            {"table_name": "CT2", "table_alias": "Lançamentos Contábeis", "table_role": "principal",
             "fields": [
                 {"column_name": "CT2_DATA", "column_label": "Data do Lançamento"},
                 {"column_name": "CT2_DEBITO", "column_label": "Conta Débito"},
                 {"column_name": "CT2_CREDIT", "column_label": "Conta Crédito"},
                 {"column_name": "CT2_VALOR", "column_label": "Valor"},
                 {"column_name": "CT2_HP", "column_label": "Histórico Padrão"},
             ]},
        ],
    },
    {
        "name": "Livros Fiscais",
        "description": "Apuração fiscal, livros de entrada/saída e obrigações acessórias.",
        "module": "FIS",
        "module_label": "Fiscal",
        "icon": "fa-balance-scale",
        "color": "#dc3545",
        "tables": [
            {"table_name": "SF3", "table_alias": "Livros Fiscais", "table_role": "principal",
             "fields": [
                 {"column_name": "F3_NFISCAL", "column_label": "Número da NF", "is_key": True},
                 {"column_name": "F3_SERIE", "column_label": "Série"},
                 {"column_name": "F3_CLIEFOR", "column_label": "Cliente/Fornecedor"},
                 {"column_name": "F3_ENTRADA", "column_label": "Entrada/Saída"},
                 {"column_name": "F3_CFO", "column_label": "CFOP"},
                 {"column_name": "F3_VALICM", "column_label": "Valor ICMS"},
             ]},
        ],
    },
    {
        "name": "Ativo Imobilizado",
        "description": "Controle patrimonial de bens do ativo fixo.",
        "module": "ATF",
        "module_label": "Ativo Fixo",
        "icon": "fa-building",
        "color": "#6c757d",
        "tables": [
            {"table_name": "SN1", "table_alias": "Cadastro de Ativos", "table_role": "principal",
             "fields": [
                 {"column_name": "N1_CBASE", "column_label": "Código Base do Ativo", "is_key": True},
                 {"column_name": "N1_ITEM", "column_label": "Item", "is_key": True},
                 {"column_name": "N1_DESCRIC", "column_label": "Descrição do Bem"},
                 {"column_name": "N1_DTAQUIS", "column_label": "Data de Aquisição"},
                 {"column_name": "N1_VORIG1", "column_label": "Valor Original"},
                 {"column_name": "N1_GRUPO", "column_label": "Grupo do Bem"},
             ]},
            {"table_name": "SN3", "table_alias": "Movimentações do Ativo", "table_role": "auxiliar",
             "fields": [
                 {"column_name": "N3_CBASE", "column_label": "Código Base"},
                 {"column_name": "N3_ITEM", "column_label": "Item"},
                 {"column_name": "N3_TIPO", "column_label": "Tipo de Movimentação"},
                 {"column_name": "N3_DATA", "column_label": "Data do Movimento"},
             ]},
        ],
    },
]

# Fluxos padrão entre processos
DEFAULT_FLOWS = [
    {"source": "Solicitação de Compras", "target": "Pedido de Compras", "flow_type": "trigger",
     "description": "Solicitação aprovada gera pedido de compra", "source_table": "SC1", "target_table": "SC7"},
    {"source": "Pedido de Compras", "target": "Entrada de NF (Recebimento)", "flow_type": "trigger",
     "description": "Pedido de compra gera nota de entrada", "source_table": "SC7", "target_table": "SF1"},
    {"source": "Entrada de NF (Recebimento)", "target": "Contas a Pagar", "flow_type": "data",
     "description": "NF de entrada gera título a pagar", "source_table": "SF1", "target_table": "SE2"},
    {"source": "Entrada de NF (Recebimento)", "target": "Controle de Estoque", "flow_type": "data",
     "description": "NF de entrada movimenta o estoque", "source_table": "SD1", "target_table": "SB2"},
    {"source": "Pedido de Venda", "target": "Faturamento (NF Saída)", "flow_type": "trigger",
     "description": "Pedido liberado gera nota fiscal de saída", "source_table": "SC5", "target_table": "SF2"},
    {"source": "Faturamento (NF Saída)", "target": "Contas a Receber", "flow_type": "data",
     "description": "NF de saída gera título a receber", "source_table": "SF2", "target_table": "SE1"},
    {"source": "Faturamento (NF Saída)", "target": "Controle de Estoque", "flow_type": "data",
     "description": "NF de saída baixa o estoque", "source_table": "SD2", "target_table": "SB2"},
    {"source": "Contas a Receber", "target": "Movimentação Bancária", "flow_type": "data",
     "description": "Baixa de título gera movimentação bancária", "source_table": "SE1", "target_table": "SE5"},
    {"source": "Contas a Pagar", "target": "Movimentação Bancária", "flow_type": "data",
     "description": "Pagamento de título gera movimentação bancária", "source_table": "SE2", "target_table": "SE5"},
    {"source": "Faturamento (NF Saída)", "target": "Livros Fiscais", "flow_type": "data",
     "description": "NF de saída registra nos livros fiscais", "source_table": "SF2", "target_table": "SF3"},
    {"source": "Entrada de NF (Recebimento)", "target": "Livros Fiscais", "flow_type": "data",
     "description": "NF de entrada registra nos livros fiscais", "source_table": "SF1", "target_table": "SF3"},
    {"source": "Movimentação Bancária", "target": "Contabilidade", "flow_type": "data",
     "description": "Movimentações bancárias geram lançamentos contábeis", "source_table": "SE5", "target_table": "CT2"},
]


def get_protheus_modules():
    """Retorna lista de módulos padrão do Protheus."""
    return PROTHEUS_MODULES


def seed_default_processes(cursor, user_id=None):
    """
    Popula processos padrão do Protheus com tabelas, campos e fluxos.
    Retorna quantidade de processos inseridos.
    """
    inserted = 0

    for proc in DEFAULT_PROCESSES:
        # Verifica se já existe
        cursor.execute("SELECT id FROM business_processes WHERE name = %s", (proc["name"],))
        existing = cursor.fetchone()
        if existing:
            continue

        # Insere processo
        cursor.execute(
            """
            INSERT INTO business_processes (name, description, module, module_label, icon, color, is_system, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, TRUE, %s)
            RETURNING id
            """,
            (proc["name"], proc["description"], proc["module"], proc["module_label"],
             proc["icon"], proc["color"], user_id),
        )
        process_id = cursor.fetchone()["id"]
        inserted += 1

        # Insere tabelas e campos
        for idx, tbl in enumerate(proc.get("tables", [])):
            cursor.execute(
                """
                INSERT INTO process_tables (process_id, table_name, table_alias, table_role, sort_order)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
                """,
                (process_id, tbl["table_name"], tbl["table_alias"], tbl["table_role"], idx),
            )
            pt_id = cursor.fetchone()["id"]

            for fidx, fld in enumerate(tbl.get("fields", [])):
                cursor.execute(
                    """
                    INSERT INTO process_fields (process_table_id, column_name, column_label, is_key, sort_order)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (pt_id, fld["column_name"], fld["column_label"], fld.get("is_key", False), fidx),
                )

    # Insere fluxos padrão
    for flow in DEFAULT_FLOWS:
        cursor.execute("SELECT id FROM business_processes WHERE name = %s", (flow["source"],))
        src = cursor.fetchone()
        cursor.execute("SELECT id FROM business_processes WHERE name = %s", (flow["target"],))
        tgt = cursor.fetchone()
        if src and tgt:
            cursor.execute(
                "SELECT id FROM process_flows WHERE source_process_id = %s AND target_process_id = %s",
                (src["id"], tgt["id"]),
            )
            if not cursor.fetchone():
                cursor.execute(
                    """
                    INSERT INTO process_flows (source_process_id, target_process_id, source_table, target_table,
                                               flow_type, description)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (src["id"], tgt["id"], flow["source_table"], flow["target_table"],
                     flow["flow_type"], flow["description"]),
                )

    logger.info(f"Seed de processos: {inserted} processos inseridos")
    return inserted


def auto_map_fields(cursor, process_table_id, connection_id):
    """
    Importa campos do schema_cache para process_fields automaticamente.
    Retorna quantidade de campos importados.
    """
    # Busca a tabela vinculada
    cursor.execute("SELECT table_name FROM process_tables WHERE id = %s", (process_table_id,))
    pt = cursor.fetchone()
    if not pt:
        return 0

    table_name = pt["table_name"]

    # Busca campos no schema_cache
    cursor.execute(
        """
        SELECT column_name, column_type, is_key, column_order
        FROM schema_cache
        WHERE connection_id = %s AND table_name LIKE %s
        ORDER BY column_order
        """,
        (connection_id, f"%{table_name}%"),
    )
    cached_fields = cursor.fetchall()

    imported = 0
    for fld in cached_fields:
        # Verifica se já existe
        cursor.execute(
            "SELECT id FROM process_fields WHERE process_table_id = %s AND column_name = %s",
            (process_table_id, fld["column_name"]),
        )
        if cursor.fetchone():
            continue

        cursor.execute(
            """
            INSERT INTO process_fields (process_table_id, column_name, column_label, is_key, sort_order)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (process_table_id, fld["column_name"], fld["column_name"], fld["is_key"], fld["column_order"]),
        )
        imported += 1

    return imported
