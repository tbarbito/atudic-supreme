"""
Dicionario de sinonimos Protheus para expansao de queries.

Mapeia termos coloquiais/genericos para termos tecnicos do Protheus,
permitindo que buscas como "cadastro de cliente" encontrem chunks
sobre SA1, MATA030, CRMA980, etc.

Usado pelo:
- tdn_ingestor.search() para expandir queries full-text
- agent_context._fetch_tdn_context() para enriquecer contexto
- _DOMAIN_KEYWORDS do orquestrador para roteamento mais preciso
"""

# Mapeamento: termo coloquial → termos tecnicos Protheus
# Cada entrada e uma lista de aliases que devem ser buscados juntos
PROTHEUS_SYNONYMS = {
    # === MODULOS ===
    "financeiro": ["SIGAFIN", "SE1", "SE2", "SE5", "FK1", "FKA"],
    "compras": ["SIGACOM", "SC1", "SC7", "SD1", "SA2", "MATA120", "MATA121"],
    "vendas": ["SIGAFAT", "SC5", "SC6", "SC9", "SD2", "MATA410", "MATA460"],
    "faturamento": ["SIGAFAT", "SF2", "SD2", "MATA460", "MATA461", "MATXFISA"],
    "estoque": ["SIGAEST", "SB1", "SB2", "SB5", "SD3", "MATA240", "MATA250"],
    "fiscal": ["SIGAFIS", "SF3", "SF4", "SFT", "CDT", "CDA", "MATXFIS"],
    "contabil": ["SIGACTB", "CT1", "CT2", "CT5", "CTBA102"],
    "manutencao": ["SIGAMNT", "ST4", "ST9", "TQ1", "TQ2", "MNTA400"],
    "rh": ["SIGAGPE", "SRA", "SRB", "SRC", "SRD"],
    "pdv": ["SIGALOJA", "SL1", "SL2", "LOJA701"],

    # === CADASTROS PRINCIPAIS ===
    "cliente": ["SA1", "MATA030", "CRMA980", "cadastro cliente"],
    "fornecedor": ["SA2", "MATA020", "cadastro fornecedor"],
    "produto": ["SB1", "MATA010", "cadastro produto"],
    "item": ["SB1", "MATA010", "produto"],
    "banco": ["SA6", "MATA070", "cadastro banco"],
    "natureza": ["SED", "MATA360", "natureza financeira"],
    "condicao pagamento": ["SE4", "MATA360", "condicao pagto"],
    "centro custo": ["CTT", "CTBA180", "centro de custo"],
    "transportadora": ["SA4", "MATA050", "cadastro transportadora"],
    "vendedor": ["SA3", "MATA040", "cadastro vendedor"],
    "unidade medida": ["SAH", "unidade medida"],
    "moeda": ["SM2", "moedas"],
    "grupo produto": ["SBM", "grupo de produto"],
    "armazem": ["NNR", "SB2", "armazem deposito"],
    "filial": ["SM0", "filial empresa"],
    "usuario": ["SX2_USR", "SIGACFG", "usuario protheus"],

    # === DOCUMENTOS ===
    "pedido de venda": ["SC5", "SC6", "MATA410", "pedido venda"],
    "pedido de compra": ["SC1", "SC7", "MATA120", "pedido compra", "solicitacao compra"],
    "nota fiscal entrada": ["SF1", "SD1", "MATA103", "nf entrada"],
    "nota fiscal saida": ["SF2", "SD2", "MATA460", "nf saida"],
    "titulo pagar": ["SE2", "FINA050", "contas pagar"],
    "titulo receber": ["SE1", "FINA040", "contas receber"],
    "movimento bancario": ["SE5", "FINA100", "movimento banco"],
    "contrato": ["CN9", "CNA", "CNB", "CNTA120", "contrato"],
    "ordem producao": ["SC2", "MATA650", "ordem producao op"],
    "ordem servico": ["ST4", "TQ1", "MNTA400", "ordem servico os"],
    "solicitacao": ["SC1", "MATA110", "solicitacao compra"],

    # === DICIONARIO SX ===
    "sx2": ["SX2", "tabelas", "dicionario tabelas", "alias"],
    "sx3": ["SX3", "campos", "dicionario campos", "field", "X3_CAMPO"],
    "sx1": ["SX1", "perguntas", "parametros tela"],
    "sx5": ["SX5", "tabelas genericas", "tabela generica"],
    "sx6": ["SX6", "parametros", "MV_", "parametro sistema"],
    "sx7": ["SX7", "gatilhos", "trigger campo"],
    "sx9": ["SX9", "relacionamentos", "relacao tabelas"],
    "sxa": ["SXA", "folders", "pasta cadastro"],
    "sxb": ["SXB", "consulta padrao", "F3 consulta"],
    "six": ["SIX", "indices", "index tabela"],

    # === FUNCOES E CLASSES ADVPL ===
    "mvc": ["FWBrowse", "FWFormView", "FWFormStruct", "FWModel", "AxFunction", "ModelDef", "ViewDef"],
    "browse": ["FWBrowse", "MBrowse", "MarkBrowse", "AxPesqui"],
    "msexecauto": ["MsExecAuto", "MATA410", "MATA103", "MATA120", "execucao automatica"],
    "gatilho": ["SX7", "trigger", "gatilho campo", "SetTrigger"],
    "ponto de entrada": ["User Function", "PE", "point of entry", "MATA410PE"],
    "relatorio": ["TReport", "SetPrint", "PREPARE ENVIRONMENT", "SetDefault"],
    "web service": ["WsMethod", "WsSend", "WsReceive", "FWRest", "REST"],
    "rest": ["FWRest", "HTTPREST", "REST API", "endpoint"],

    # === INFRAESTRUTURA ===
    "appserver": ["AppServer", "appserver.ini", "TOTVS Application Server"],
    "dbaccess": ["DBAccess", "dbaccess.ini", "TOTVS DBAccess"],
    "smartclient": ["SmartClient", "smartclient.ini", "interface"],
    "rpo": ["RPO", "repositorio objetos", "TotvsAppMonitor"],
    "license server": ["License Server", "licenca", "hardlock"],
    "tss": ["TSS", "TOTVS Service SOA", "SPEDPROCSERVER", "documento fiscal"],
}

# Mapeamento inverso: termo tecnico → termo coloquial principal
# Util para enriquecer respostas do agente
REVERSE_MAP = {}
for _colloquial, _technicals in PROTHEUS_SYNONYMS.items():
    for _tech in _technicals:
        _tech_lower = _tech.lower()
        if _tech_lower not in REVERSE_MAP:
            REVERSE_MAP[_tech_lower] = _colloquial


def expand_query(query):
    """Expande uma query com sinonimos Protheus.

    Args:
        query: texto de busca original

    Returns:
        str: query expandida com termos adicionais (OR semantico)

    Exemplo:
        expand_query("cadastro de cliente") → "cadastro de cliente SA1 MATA030 CRMA980"
    """
    query_lower = query.lower()
    extra_terms = set()

    for colloquial, technicals in PROTHEUS_SYNONYMS.items():
        # Verificar se o termo coloquial aparece na query
        if colloquial in query_lower:
            extra_terms.update(technicals)
            continue

        # Verificar se algum termo tecnico aparece na query
        for tech in technicals:
            if tech.lower() in query_lower:
                extra_terms.update(technicals)
                # Adicionar o termo coloquial tambem
                extra_terms.add(colloquial)
                break

    if not extra_terms:
        return query

    # Remover termos que ja estao na query
    new_terms = [t for t in extra_terms if t.lower() not in query_lower]

    # Limitar expansao para nao poluir a query (max 8 termos)
    new_terms = sorted(new_terms)[:8]

    return f"{query} {' '.join(new_terms)}"


def get_domain_for_terms(message):
    """Identifica dominios Protheus relevantes para uma mensagem.

    Retorna lista de dominios detectados com score, util para
    enriquecer o roteamento do orquestrador.

    Args:
        message: texto da mensagem do usuario

    Returns:
        list[tuple[str, int]]: [(dominio, score), ...] ordenado por score desc
    """
    msg_lower = message.lower()
    scores = {}

    # Mapear sinonimos para dominios do orquestrador
    synonym_to_domain = {
        "financeiro": "database",
        "compras": "database",
        "vendas": "database",
        "faturamento": "database",
        "estoque": "database",
        "fiscal": "database",
        "contabil": "database",
        "manutencao": "database",
        "rh": "database",
        "pdv": "database",
        "cliente": "database",
        "fornecedor": "database",
        "produto": "database",
        "mvc": "knowledge",
        "browse": "knowledge",
        "msexecauto": "knowledge",
        "ponto de entrada": "knowledge",
        "relatorio": "knowledge",
        "web service": "knowledge",
        "rest": "knowledge",
        "appserver": "devops",
        "dbaccess": "devops",
        "rpo": "devops",
        "license server": "devops",
        "tss": "diagnostico",
    }

    for colloquial, technicals in PROTHEUS_SYNONYMS.items():
        domain = synonym_to_domain.get(colloquial)
        if not domain:
            continue

        # Verificar coloquial na mensagem
        if colloquial in msg_lower:
            scores[domain] = scores.get(domain, 0) + 2

        # Verificar tecnicos na mensagem
        for tech in technicals:
            if tech.lower() in msg_lower:
                scores[domain] = scores.get(domain, 0) + 1

    return sorted(scores.items(), key=lambda x: x[1], reverse=True)
