"""
Camada de inteligencia semantica Protheus para o GolIAs.

Funciona independente da LLM — toda a cognição está em regras,
heurísticas e grafos de conhecimento hardcoded.

Responsabilidades:
1. Normalizar linguagem coloquial → termos tecnicos Protheus
2. Detectar intencao Protheus da mensagem (modulo, rotina, conceito)
3. Gerar queries otimizadas para busca TDN
4. Classificar e ranquear contexto antes de injetar no prompt
5. Mapear entidades Protheus mencionadas na conversa

Uso:
    from app.services.tdn_intelligence import ProtheusIntelligence
    pi = ProtheusIntelligence()
    result = pi.analyze("resuma o que faz o modulo sigafat")
    # result.search_queries → ["SIGAFAT faturamento notas fiscais saida pedido venda"]
    # result.detected_modules → ["SIGAFAT"]
    # result.detected_entities → {"tables": ["SC5","SC6","SD2","SF2"], "routines": ["MATA410","MATA460"]}
"""

import re
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# =================================================================
# GRAFO DE CONHECIMENTO PROTHEUS
# =================================================================

# Modulos → descricao, tabelas principais, rotinas principais, termos coloquiais
PROTHEUS_MODULES = {
    "SIGAFAT": {
        "name": "Faturamento",
        "aliases": ["faturamento", "vendas", "pedido de venda", "nota fiscal saida",
                     "nf saida", "fatura", "pedidos", "sigafat"],
        "tables": ["SC5", "SC6", "SC9", "SD2", "SF2", "SA1", "SA3", "SB1", "SE4"],
        "routines": ["MATA410", "MATA460", "MATA461", "MATA462", "MATA465",
                      "MATA480", "MATA490", "MATA103"],
        "concepts": ["pedido de venda", "nota fiscal de saida", "liberacao de credito",
                      "liberacao de estoque", "comissao", "tabela de preco",
                      "condicao de pagamento", "desconto", "bonificacao"],
    },
    "SIGAFIN": {
        "name": "Financeiro",
        "aliases": ["financeiro", "contas a pagar", "contas a receber", "tesouraria",
                     "fluxo de caixa", "sigafin", "pagar", "receber", "baixa"],
        "tables": ["SE1", "SE2", "SE5", "SA6", "SED", "FK1", "FKA", "FK5"],
        "routines": ["FINA040", "FINA050", "FINA080", "FINA100", "FINA110",
                      "FINA340", "FINA750"],
        "concepts": ["titulo a receber", "titulo a pagar", "baixa de titulo",
                      "compensacao", "bordero", "cobranca", "boleto", "cnab",
                      "conciliacao bancaria", "fluxo de caixa"],
    },
    "SIGACOM": {
        "name": "Compras",
        "aliases": ["compras", "pedido de compra", "solicitacao de compra",
                     "cotacao", "sigacom", "fornecedor", "compra"],
        "tables": ["SC1", "SC7", "SC8", "SD1", "SF1", "SA2", "SA5"],
        "routines": ["MATA110", "MATA120", "MATA121", "MATA103", "MATA116",
                      "MATA125", "MATA140"],
        "concepts": ["solicitacao de compra", "pedido de compra", "cotacao",
                      "nota fiscal de entrada", "autorizacao de entrega",
                      "contrato de fornecimento", "aprovacao de compra"],
    },
    "SIGAEST": {
        "name": "Estoque e Custos",
        "aliases": ["estoque", "custos", "armazem", "inventario", "sigaest",
                     "deposito", "saldo", "movimentacao"],
        "tables": ["SB1", "SB2", "SB5", "SB9", "SBZ", "SD3", "NNR", "SBF"],
        "routines": ["MATA240", "MATA241", "MATA250", "MATA260", "MATA265",
                      "MATA220", "MATA225", "MATA300", "MATA330"],
        "concepts": ["requisicao", "devolucao", "transferencia", "inventario",
                      "custo medio", "custo padrao", "saldo de estoque",
                      "ponto de pedido", "lote economico"],
    },
    "SIGAFIS": {
        "name": "Fiscal",
        "aliases": ["fiscal", "impostos", "icms", "pis", "cofins", "ipi",
                     "sigafis", "tributacao", "sped", "nfe"],
        "tables": ["SF3", "SF4", "SFT", "CDT", "CDA", "CC2", "CFC"],
        "routines": ["MATXFIS", "MATXFISA", "MATA950", "MATA953",
                      "SPDFISCAL", "SPDCONTRIB"],
        "concepts": ["tes", "tipo de entrada e saida", "cfop", "cst",
                      "icms", "pis", "cofins", "ipi", "icms st",
                      "nota complementar", "carta de correcao", "sped fiscal",
                      "sped contribuicoes", "dctf", "dirf"],
    },
    "SIGAMNT": {
        "name": "Manutencao de Ativos",
        "aliases": ["manutencao", "mnt", "ordem de servico", "os",
                     "sigamnt", "ativo", "equipamento", "preventiva", "corretiva"],
        "tables": ["ST4", "ST9", "STJ", "TQ1", "TQ2", "TQ3", "TQ4", "STO"],
        "routines": ["MNTA400", "MNTA410", "MNTA420", "MNTA430", "MNTA440",
                      "MNTA450", "MNTA460"],
        "concepts": ["ordem de servico", "plano de manutencao", "preventiva",
                      "corretiva", "preditiva", "equipamento", "bem",
                      "checklist", "solicitacao de servico"],
    },
    "SIGACTB": {
        "name": "Contabilidade",
        "aliases": ["contabilidade", "contabil", "lancamento contabil", "razao",
                     "balancete", "sigactb", "plano de contas"],
        "tables": ["CT1", "CT2", "CT5", "CTT", "CTS", "CTD"],
        "routines": ["CTBA102", "CTBA105", "CTBA110", "CTBA120",
                      "CTBA200", "CTBA380"],
        "concepts": ["lancamento contabil", "plano de contas", "centro de custo",
                      "rateio", "balancete", "razao contabil", "dre",
                      "encerramento", "apuracao de resultado"],
    },
    "SIGAGPE": {
        "name": "Recursos Humanos",
        "aliases": ["rh", "recursos humanos", "folha de pagamento", "folha",
                     "funcionario", "sigagpe", "gpea", "ferias", "rescisao"],
        "tables": ["SRA", "SRB", "SRC", "SRD", "SRE", "SRF", "SRG", "SRJ", "SRK"],
        "routines": ["GPEA010", "GPEA020", "GPEA040", "GPEA050",
                      "GPEM020", "GPEM040", "GPEM310"],
        "concepts": ["funcionario", "folha de pagamento", "ferias", "rescisao",
                      "admissao", "beneficios", "vale transporte", "vale refeicao",
                      "horas extras", "ponto eletronico", "13 salario"],
    },
    "SIGALOJA": {
        "name": "Controle de Lojas",
        "aliases": ["loja", "pdv", "varejo", "sigaloja", "frente de caixa",
                     "ponto de venda", "venda balcao"],
        "tables": ["SL1", "SL2", "SL4", "SLQ", "SA1"],
        "routines": ["LOJA701", "LOJA601", "LOJA010", "LOJA020"],
        "concepts": ["venda de balcao", "pdv", "frente de caixa", "cupom fiscal",
                      "sangria", "suprimento", "troca", "devolucao loja"],
    },
}

# Tabelas SX → descricao e funcao
SX_TABLES = {
    "SX2": {"name": "Tabelas de Dados", "desc": "cadastro de aliases/tabelas do sistema"},
    "SX3": {"name": "Campos", "desc": "dicionario de campos (tipo, tamanho, validacao, inicializador)"},
    "SIX": {"name": "Indices", "desc": "indices das tabelas (chaves de busca)"},
    "SX1": {"name": "Perguntas", "desc": "parametros de tela (perguntas para relatorios/rotinas)"},
    "SX5": {"name": "Tabelas Genericas", "desc": "dominios de valores (tipos, status, codigos)"},
    "SX6": {"name": "Parametros", "desc": "parametros do sistema (MV_ESTADO, MV_ESTNEG, etc)"},
    "SX7": {"name": "Gatilhos", "desc": "triggers de campos (preenchimento automatico)"},
    "SX9": {"name": "Relacionamentos", "desc": "relacoes entre tabelas (chave estrangeira logica)"},
    "SXA": {"name": "Folders", "desc": "abas/pastas de telas de cadastro"},
    "SXB": {"name": "Consulta Padrao", "desc": "consultas F3 (lookup de campos)"},
}

# Patterns de linguagem coloquial → conceito tecnico
COLLOQUIAL_PATTERNS = [
    # Perguntas sobre modulos
    (r"(?:o que|qual|quais|me (?:fala|explica|diz|resuma)|resuma|descreva|como funciona).*(?:modulo|módulo|sigafat|sigafin|sigacom|sigaest|sigafis|sigamnt|sigactb|sigagpe|sigaloja)",
     "module_info"),
    # Perguntas sobre tabelas
    (r"(?:tabela|alias|sx2|cadastro de tabela|quais tabelas)",
     "table_info"),
    # Perguntas sobre campos
    (r"(?:campo|sx3|dicionario|field|tipo de campo|x3_campo)",
     "field_info"),
    # Perguntas sobre parametros
    (r"(?:parametro|mv_|sx6|configuracao.*sistema)",
     "parameter_info"),
    # Perguntas sobre rotinas
    (r"(?:rotina|mata\d+|fina\d+|gpea\d+|mnta\d+|ctba\d+|loja\d+|programa|tela|funcao)",
     "routine_info"),
    # Perguntas sobre processos
    (r"(?:como (?:faz|fazer|gerar|emitir|cadastrar|incluir|alterar|excluir|estornar)|passo a passo|procedimento)",
     "procedure_info"),
    # Perguntas sobre integracao
    (r"(?:msexecauto|execauto|integracao|importacao|exportacao|api.*rest|web.*service)",
     "integration_info"),
    # Perguntas sobre erros
    (r"(?:erro|falha|rejeicao|nao (?:grava|salva|processa|aparece)|travou|lento|timeout)",
     "error_info"),
    # Perguntas sobre infraestrutura
    (r"(?:appserver|dbaccess|smartclient|rpo|license|compilar|patch)",
     "infra_info"),
    # Perguntas sobre fiscal/impostos
    (r"(?:icms|pis|cofins|ipi|st|iss|nfe|cte|mdfe|sped|cfop|cst|tes)",
     "tax_info"),
]


@dataclass
class AnalysisResult:
    """Resultado da analise de inteligencia Protheus."""
    original_message: str
    search_queries: list = field(default_factory=list)
    detected_modules: list = field(default_factory=list)
    detected_tables: list = field(default_factory=list)
    detected_routines: list = field(default_factory=list)
    detected_concepts: list = field(default_factory=list)
    protheus_intent: str = ""
    context_hint: str = ""


class ProtheusIntelligence:
    """Motor de inteligencia semantica Protheus.

    Analisa mensagens em linguagem natural e extrai:
    - Modulos mencionados (explicita ou implicitamente)
    - Tabelas, rotinas e conceitos relevantes
    - Queries otimizadas para busca TDN
    - Dicas de contexto para o LLM
    """

    def __init__(self):
        # Construir indice reverso: termo → modulo
        self._term_to_module = {}
        for mod_id, mod in PROTHEUS_MODULES.items():
            for alias in mod["aliases"]:
                self._term_to_module[alias.lower()] = mod_id
            for table in mod["tables"]:
                self._term_to_module[table.lower()] = mod_id
            for routine in mod["routines"]:
                self._term_to_module[routine.lower()] = mod_id
            for concept in mod["concepts"]:
                self._term_to_module[concept.lower()] = mod_id

        # Indice de tabelas SX
        self._sx_terms = {}
        for sx_id, sx in SX_TABLES.items():
            self._sx_terms[sx_id.lower()] = sx_id
            self._sx_terms[sx["name"].lower()] = sx_id

    def analyze(self, message):
        """Analisa uma mensagem e retorna inteligencia Protheus.

        Args:
            message: texto do usuario em linguagem natural

        Returns:
            AnalysisResult com queries, modulos, tabelas, etc.
        """
        msg_lower = message.lower().strip()
        result = AnalysisResult(original_message=message)

        # 1. Detectar modulos
        result.detected_modules = self._detect_modules(msg_lower)

        # 2. Detectar tabelas SX
        result.detected_tables = self._detect_tables(msg_lower)

        # 3. Detectar rotinas
        result.detected_routines = self._detect_routines(msg_lower)

        # 4. Detectar conceitos
        result.detected_concepts = self._detect_concepts(msg_lower)

        # 5. Classificar intencao Protheus
        result.protheus_intent = self._classify_intent(msg_lower)

        # 6. Gerar queries otimizadas para busca TDN
        result.search_queries = self._generate_search_queries(result)

        # 7. Gerar context hint para o LLM
        result.context_hint = self._generate_context_hint(result)

        return result

    def _detect_modules(self, msg):
        """Detecta modulos Protheus mencionados (explicita ou implicitamente)."""
        found = set()
        for term, mod_id in self._term_to_module.items():
            if term in msg:
                found.add(mod_id)
        return list(found)

    def _detect_tables(self, msg):
        """Detecta tabelas mencionadas (SA1, SB1, SX3, etc)."""
        # Tabelas padrao Protheus (2-3 letras + digitos opcionais)
        tables = set()
        # Pattern: SA1, SB1, SC5, SE1, SF2, SX3, etc
        for match in re.findall(r'\b(S[A-Z][0-9A-Z])\b', msg.upper()):
            tables.add(match)
        # Tabelas SX pelo nome
        for term, sx_id in self._sx_terms.items():
            if term in msg:
                tables.add(sx_id)
        # Tabelas dos modulos detectados
        # (nao adicionar automaticamente — so se o modulo for mencionado explicitamente)
        return list(tables)

    def _detect_routines(self, msg):
        """Detecta rotinas Protheus (MATA410, FINA040, etc)."""
        routines = set()
        for match in re.findall(r'\b(MATA\d{3}|FINA\d{3}|GPEA\d{3}|MNTA\d{3}|CTBA\d{3}|LOJA\d{3}|MATX\w+)\b', msg.upper()):
            routines.add(match)
        return list(routines)

    def _detect_concepts(self, msg):
        """Detecta conceitos Protheus na mensagem."""
        concepts = set()
        for mod in PROTHEUS_MODULES.values():
            for concept in mod["concepts"]:
                if concept in msg:
                    concepts.add(concept)
        return list(concepts)

    def _classify_intent(self, msg):
        """Classifica a intencao Protheus da mensagem."""
        for pattern, intent in COLLOQUIAL_PATTERNS:
            if re.search(pattern, msg, re.IGNORECASE):
                return intent
        return "general_protheus"

    def _generate_search_queries(self, result):
        """Gera queries otimizadas para busca TDN.

        Estrategia: combinar termos detectados em queries que maximizam
        a chance de encontrar chunks relevantes via tsvector e ILIKE.
        """
        queries = []

        # Query 1: baseada nos modulos detectados
        for mod_id in result.detected_modules:
            mod = PROTHEUS_MODULES.get(mod_id, {})
            mod_name = mod.get("name", mod_id)
            # Query com nome do modulo + conceitos principais
            terms = [mod_id, mod_name]
            terms.extend(mod.get("routines", [])[:3])
            queries.append(" ".join(terms))

        # Query 2: baseada nas tabelas detectadas
        if result.detected_tables:
            queries.append(" ".join(result.detected_tables))

        # Query 3: baseada nas rotinas detectadas
        if result.detected_routines:
            queries.append(" ".join(result.detected_routines))

        # Query 4: conceitos detectados
        if result.detected_concepts:
            queries.append(" ".join(result.detected_concepts[:5]))

        # Query 5: mensagem original normalizada (remover stopwords)
        normalized = self._remove_stopwords(result.original_message)
        if normalized and normalized not in queries:
            queries.append(normalized)

        # Se nenhuma query especifica, usar mensagem expandida com sinonimos
        if not queries:
            from app.services.tdn_synonyms import expand_query
            queries.append(expand_query(result.original_message))

        return queries

    def _generate_context_hint(self, result):
        """Gera dica de contexto para orientar o LLM.

        Esse texto e injetado no prompt para ajudar o LLM a entender
        o dominio da pergunta mesmo sem TDN chunks.
        """
        hints = []

        for mod_id in result.detected_modules:
            mod = PROTHEUS_MODULES.get(mod_id, {})
            mod_name = mod.get("name", "")
            tables = ", ".join(mod.get("tables", [])[:5])
            routines = ", ".join(mod.get("routines", [])[:3])
            hints.append(
                f"Modulo {mod_id} ({mod_name}): tabelas principais [{tables}], "
                f"rotinas [{routines}]"
            )

        for table in result.detected_tables:
            if table in SX_TABLES:
                sx = SX_TABLES[table]
                hints.append(f"Tabela {table} ({sx['name']}): {sx['desc']}")

        if result.protheus_intent:
            intent_hints = {
                "module_info": "Usuario quer informacoes sobre um modulo Protheus",
                "table_info": "Usuario quer informacoes sobre tabelas/estrutura de dados",
                "field_info": "Usuario quer informacoes sobre campos do dicionario",
                "parameter_info": "Usuario quer informacoes sobre parametros do sistema (MV_)",
                "routine_info": "Usuario quer informacoes sobre uma rotina/programa",
                "procedure_info": "Usuario quer saber como executar um processo/procedimento",
                "integration_info": "Usuario quer informacoes sobre integracao/MsExecAuto",
                "error_info": "Usuario esta relatando um erro ou problema",
                "infra_info": "Usuario quer informacoes sobre infraestrutura Protheus",
                "tax_info": "Usuario quer informacoes sobre tributacao/fiscal",
            }
            hint = intent_hints.get(result.protheus_intent)
            if hint:
                hints.append(hint)

        return "\n".join(hints) if hints else ""

    def _remove_stopwords(self, text):
        """Remove stopwords portuguesas da mensagem."""
        stopwords = {
            "o", "a", "os", "as", "um", "uma", "uns", "umas", "de", "do", "da",
            "dos", "das", "em", "no", "na", "nos", "nas", "por", "para", "com",
            "sem", "que", "qual", "quais", "como", "quando", "onde", "se", "ou",
            "e", "mas", "nao", "sim", "muito", "pouco", "mais", "menos", "bem",
            "meu", "seu", "esse", "esta", "isso", "aqui", "ali", "la", "eu",
            "voce", "ele", "ela", "nos", "eles", "me", "te", "lhe", "foi",
            "ser", "ter", "fazer", "esta", "sao", "quero", "preciso", "gostaria",
            "pode", "favor", "obrigado", "ok", "tudo", "todo", "toda", "todos",
            "resuma", "resuma", "explique", "fale", "diga", "traga", "mostre",
        }
        words = text.lower().split()
        filtered = [w for w in words if w not in stopwords and len(w) >= 2]
        return " ".join(filtered)
