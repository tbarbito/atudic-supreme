"""
Detecção de intent e extração de entidades do GolIAs.

Responsabilidades:
- Classificar a intenção da mensagem do usuário (9 intents)
- Extrair entidades (tabelas, campos, códigos de erro, funções)
- Classificar complexidade da tarefa
- Detectar confirmação implícita do usuário
"""

import re
import logging

from app.services.agent_config import agent_config as cfg

logger = logging.getLogger(__name__)

# Cache de classificação LLM por sessão (evita re-classificar mesma mensagem)
# Formato: {message_hash: (intent, confidence)}
_llm_intent_cache = {}
_LLM_INTENT_CACHE_MAX = 100


# Cada intent tem: patterns (regex de alta confiança), keywords (palavras-chave), priority
INTENT_RULES = {
    "error_analysis": {
        "patterns": [
            r"ORA-\d+",
            r"TOPCONN[\s-]*\d+",
            r"thread\s*error",
            r"erro\s+\d+",
            r"error\s+\d+",
            r"stack\s*overflow",
            r"memory\s*(leak|fault)",
            r"segmentation\s*fault",
            r"lock\s+(timeout|deadlock)",
        ],
        "keywords": [
            "erro",
            "error",
            "falha",
            "crash",
            "bug",
            "problema",
            "travando",
            "travou",
            "caiu",
            "parou",
            "lento",
            "lentidão",
            "timeout",
            "monitor",
            "monitoramento",
            "alerta",
            "log",
            "scan",
        ],
        "priority": 10,
    },
    "ini_audit": {
        "patterns": [
            r"audit(ar|oria)\s+(ini|appserver|dbaccess)",
            r"analis(ar|e)\s+(ini|appserver\.ini|dbaccess\.ini)",
            r"\.ini\b",
            r"appserver\.ini",
            r"dbaccess\.ini",
            r"smartclient\.ini",
        ],
        "keywords": [
            "ini",
            "auditoria",
            "auditar",
            "appserver.ini",
            "dbaccess.ini",
            "smartclient.ini",
            "chave",
            "configuração",
            "boas práticas",
            "best practices",
        ],
        "priority": 8,
    },
    "table_info": {
        "patterns": [
            r"\bS[A-Z][0-9A-Z]\b",  # Tabelas Protheus: SC5, SA1, SB1, etc
            r"\bSX[1-9B]\b",  # Metadados: SX1, SX2, SX3, SX5, SXB
            r"\bSIX\b",  # Índices
            r"\b[A-Z][A-Z0-9]_[A-Z]{2,}\b",  # Campos: C5_NUM, D1_DOC
            r"\bMV_[A-Z]+\b",  # Parâmetros Protheus: MV_ESTNEG, MV_SPEDURL
            r"\bconex(ão|ao|ões|oes)\s+(de\s+)?banco\b",  # Conexões de banco
            r"\bbanco\s+(hml|prd|dev|producao|homologacao|teste)\b",  # banco HML, banco PRD
            r"compar(ar|e|ação|acao|ou)\s+(dicion|SX|banco|HML|PRD)",  # Comparação de dicionário
            r"equaliz(ar|e|ação|acao)",  # Equalização
            r"diferença|divergência|divergencia",  # Diferenças (contexto DB)
            r"histórico\s+de\s+(compar|equaliz|dicion)",  # Histórico de comparações
            r"\b(cliente|fornecedor|produto|pedido|nota|titulo|item|cadastro)s?\s.*(banco|base|hml|prd)",  # Consultas Protheus por entidade
            r"\b(trag|busqu|consult|list|mostr)\w*\s.*(banco|base|hml|prd|sql)",  # Ações em banco
        ],
        "keywords": [
            "tabela",
            "table",
            "campo",
            "field",
            "coluna",
            "column",
            "dicionário",
            "dictionary",
            "dicionario",
            "metadado",
            "metadata",
            "schema",
            "conexão de banco",
            "conexões de banco",
            "conexao de banco",
            "banco de dados",
            "database",
            "query",
            "sql",
            "consulta",
            "parametro",
            "parâmetro",
            "comparação",
            "comparacao",
            "compare",
            "equalizar",
            "equalizacao",
            "diferença",
            "diferenca",
            "divergência",
            "divergencia",
            "historico de comparacao",
        ],
        "priority": 7,
        "case_sensitive": True,  # Tabelas Protheus sao SEMPRE maiusculas — evita false positive com "sim", "sub", etc
    },
    "procedure_lookup": {
        "patterns": [
            r"como\s+(faço|faz|fazer|aplicar|atualizar|compilar|gerar)",
            r"passo\s*a\s*passo",
            r"procedimento\s+(de|para|do)",
        ],
        "keywords": [
            "como",
            "procedimento",
            "passo",
            "patch",
            "atualizar",
            "atualização",
            "RPO",
            "tombamento",
            "compilar",
            "backup",
        ],
        "priority": 6,
    },
    "alert_recurrence": {
        "patterns": [
            r"(erro|alerta)s?\s+recorrente",
            r"mais\s+(frequente|comum|repetido)",
        ],
        "keywords": ["recorrente", "frequente", "repetido", "tendência", "trend", "top erros", "mais comum"],
        "priority": 9,
    },
    "environment_status": {
        "patterns": [
            r"ambiente\s+(de\s+)?(produção|homologação|desenvolvimento|teste)",
            r"(PRD|HML|DEV|TST)\b",
        ],
        "keywords": [
            "ambiente",
            "ambientes",
            "environment",
            "servidor",
            "server",
            "serviço",
            "service",
            "AppServer",
            "DbAccess",
            "disponível",
            "disponíveis",
        ],
        "priority": 5,
    },
    "user_context": {
        "patterns": [
            r"(qual|em qual)\s+ambiente\s+(estou|eu estou|tou|to)\b",
            r"(estou|tou|to)\s+logad[oa]",
            r"(meu|minha)\s+(perfil|usuario|ambiente|sessão|sessao)",
            r"quem\s+(sou|eu sou)\s+eu",
            r"(qual|quais)\s+(meu|minha|minhas)\s+(permiss|acesso|perfil|papel)",
            r"qual\s+deles\s+(estou|tou|to)",
            r"em\s+qual\s+(deles|dele|delas)\b",
            r"ambiente\s+(estou|eu\s+estou)\s+logad",
            r"logad[oa]\s+(em\s+qual|em\s+que|onde|no\s+qual)",
            r"(me\s+diz|diga|fala|diz)\s+qual\s+(ambiente|meu)",
            r"qual\s+\w+\s+(estou|tou)\s+logad",
        ],
        "keywords": [
            "logado",
            "logada",
            "meu perfil",
            "meu ambiente",
            "minha sessão",
            "quem sou",
            "meu usuario",
            "meu acesso",
            "minhas permissões",
            "qual deles",
            "em qual deles",
        ],
        "priority": 12,
    },
    "knowledge_search": {
        "patterns": [
            r"artigo\s+(sobre|de|para)",
            r"(buscar|procurar|encontrar)\s+na\s+(base|KB)",
        ],
        "keywords": ["artigo", "conhecimento", "solução", "KB", "base de conhecimento", "documentação", "referência"],
        "priority": 4,
    },
    "settings_management": {
        "patterns": [
            r"cri(ar|e)\s+(ambiente|variável|variavel)",
            r"configur(ar|e)\s+(ambiente|variável|variavel|notificação|notificacao)",
            r"(criar|alterar|remover|deletar)\s+(ambiente|variável|variavel)",
        ],
        "keywords": [
            "variável de servidor", "variavel de servidor", "notificação", "notificacao",
            "configurar ambiente", "criar ambiente", "alterar ambiente", "remover ambiente",
        ],
        "priority": 6,
    },
    "admin_management": {
        "patterns": [
            r"webhook",
            r"(criar|listar|remover|testar)\s+webhook",
            r"rate.?limit",
        ],
        "keywords": ["webhook", "admin", "rate limit", "log sistema", "usuários"],
        "priority": 6,
    },
    "pipeline_status": {
        "patterns": [
            r"pipeline\s+(de\s+)?(deploy|build|ci|cd)",
            r"(rodar|executar|disparar)\s+pipeline",
            r"status\s+(do|da|de)\s+pipeline",
        ],
        "keywords": [
            "pipeline", "deploy", "build", "ci/cd", "cicd",
            "rodar pipeline", "executar pipeline", "status pipeline",
        ],
        "priority": 7,
    },
    "repository_operations": {
        "patterns": [
            r"git\s+(pull|push|clone|status|log|branch)",
            r"reposit[oó]rio",
        ],
        "keywords": [
            "repositório", "repositorio", "git", "branch", "pull",
            "push", "clone", "commit",
        ],
        "priority": 6,
    },
    "service_operations": {
        "patterns": [
            r"servi[cç]o[s]?\s+(windows|protheus|totvs|dbaccess|appserver|rest|license)",
            r"(criar|iniciar|parar|reiniciar|listar|start|stop|restart)\s+servi[cç]o",
            r"(iniciar|parar|reiniciar|start|stop|restart)\s+(appserver|dbaccess|protheus|license)",
            r"\.(totvs|protheus)\w*\b",
        ],
        "keywords": [
            "serviço", "servico", "serviços", "servicos",
            "service", "services", "iniciar", "parar", "reiniciar",
            "start", "stop", "restart", "appserver", "dbaccess",
            "license server",
        ],
        "priority": 8,
    },
    "schedule_management": {
        "patterns": [
            r"agend(ar|amento)\s+(pipeline|tarefa|job|task)",
            r"(criar|alterar|remover|desativar)\s+agendamento",
            r"cron|schedule",
        ],
        "keywords": [
            "agendamento", "agendar", "schedule", "cron",
            "horário", "horario", "programar",
        ],
        "priority": 6,
    },
}


def detect_intent(message, llm_provider=None):
    """Detecta intenção via cascata: regex → keywords → LLM → fallback.

    Fase 1: regex de alta confiança — coleta TODOS os matches e retorna o
             de maior prioridade.
    Fase 2: keywords por contagem normalizada.
    Fase 3: LLM fallback (se confidence < threshold e LLM disponível).
    Fase 4: fallback "general".

    Args:
        message: texto do usuário
        llm_provider: provider LLM opcional para fallback de classificação

    Returns:
        tuple: (intent_name, confidence)
    """
    msg_lower = message.lower().strip()

    # Fase 1: Padrões regex de alta confiança — coletar todos os matches
    phase1_matches = []
    for intent_name, rules in INTENT_RULES.items():
        flags = 0 if rules.get("case_sensitive") else re.IGNORECASE
        for pattern in rules["patterns"]:
            if re.search(pattern, message, flags):
                phase1_matches.append((intent_name, rules["priority"]))
                break

    if phase1_matches:
        best = max(phase1_matches, key=lambda x: x[1])
        return best[0], 0.90

    # Fase 2: Contagem de keywords com confidence calibrada
    scores = {}
    for intent_name, rules in INTENT_RULES.items():
        count = 0
        for kw in rules["keywords"]:
            if re.search(r"\b" + re.escape(kw) + r"\b", msg_lower, re.IGNORECASE):
                count += 1
        if count > 0:
            # match_ratio: 0.0-1.0 (proporcao de keywords que bateram)
            match_ratio = count / len(rules["keywords"])
            # confidence: base 0.55 + ratio boost (0-0.25) + priority bonus (0-0.05)
            # Mantém range 0.55-0.85 para nao degradar roteamento
            conf = 0.55 + (match_ratio * 0.25) + min(0.05, rules["priority"] / 200)
            scores[intent_name] = min(0.85, conf)

    if scores:
        best = max(scores, key=scores.get)
        confidence = scores[best]

        # Fase 3: Se confiança baixa e LLM disponível, pedir classificação ao LLM
        if confidence < cfg.LLM_INTENT_FALLBACK_THRESHOLD and llm_provider:
            llm_intent, llm_conf = _classify_intent_llm(message, llm_provider)
            if llm_intent and llm_conf > confidence:
                logger.info(
                    "🧠 LLM reclassificou intent: %s (%.2f) → %s (%.2f)",
                    best, confidence, llm_intent, llm_conf,
                )
                return llm_intent, llm_conf

        return best, confidence

    # Fase 3b: Sem keywords — tentar LLM diretamente
    if llm_provider:
        llm_intent, llm_conf = _classify_intent_llm(message, llm_provider)
        if llm_intent:
            return llm_intent, llm_conf

    # Fase 4: Fallback
    return "general", 0.30


def _classify_intent_llm(message, llm_provider):
    """Classifica intent via LLM (prompt curto, ~200 tokens).

    Usa cache para evitar re-classificação da mesma mensagem.

    Returns:
        tuple: (intent_name, confidence) ou (None, 0) se falhar
    """
    # Cache hit
    cache_key = hash(message[:200])
    if cache_key in _llm_intent_cache:
        return _llm_intent_cache[cache_key]

    intent_list = "\n".join(f"- {k}" for k in INTENT_RULES.keys())
    prompt = (
        f"Classifique a intencao do usuario entre as opcoes abaixo.\n\n"
        f"Opcoes:\n{intent_list}\n- general\n\n"
        f"Mensagem do usuario: \"{message[:300]}\"\n\n"
        f"Responda com UMA UNICA PALAVRA: o nome exato do intent. Nada mais."
    )

    try:
        result = llm_provider.chat(
            messages=[{"role": "user", "content": prompt}],
            system_prompt="Voce e um classificador de intencoes. Responda APENAS com o nome do intent, sem explicacao.",
            temperature=0.0,
            max_tokens=20,
        )

        raw = result.get("content", "").strip().lower().replace('"', "").replace("'", "")
        # Validar que o intent retornado existe
        valid_intents = set(INTENT_RULES.keys()) | {"general"}
        if raw in valid_intents:
            entry = (raw, 0.75)
        else:
            # Tentar match parcial
            for vi in valid_intents:
                if vi in raw:
                    entry = (vi, 0.70)
                    break
            else:
                entry = (None, 0)

        # Cachear (com limite de tamanho)
        if len(_llm_intent_cache) >= _LLM_INTENT_CACHE_MAX:
            _llm_intent_cache.clear()
        _llm_intent_cache[cache_key] = entry

        if entry[0]:
            logger.info("🧠 LLM intent classification: '%s' → %s (%.2f)", message[:50], entry[0], entry[1])

        return entry

    except Exception as e:
        logger.debug("LLM intent fallback falhou: %s", e)
        return (None, 0)


def extract_entities(message):
    """Extrai entidades relevantes da mensagem."""
    entities = {
        "error_codes": [],
        "table_names": [],
        "field_names": [],
        "function_names": [],
    }

    # Códigos de erro Oracle
    for m in re.finditer(r"ORA-(\d+)", message, re.IGNORECASE):
        entities["error_codes"].append(f"ORA-{m.group(1)}")

    # Códigos de erro genéricos
    for m in re.finditer(r"(?:erro|error)\s+(\d+)", message, re.IGNORECASE):
        entities["error_codes"].append(f"Error {m.group(1)}")

    # Nomes de tabela Protheus (S + letra + alfanumérico)
    for m in re.finditer(r"\b(S[A-Z][0-9A-Z])\b", message):
        if m.group(1) not in entities["table_names"]:
            entities["table_names"].append(m.group(1))

    # SIX, SXB e outras tabelas de metadados
    for m in re.finditer(r"\b(SX[1-9B]|SIX|XXA|XAM|XAL)\b", message, re.IGNORECASE):
        name = m.group(1).upper()
        if name not in entities["table_names"]:
            entities["table_names"].append(name)

    # Nomes de campo (C5_NUM, D1_DOC, etc)
    for m in re.finditer(r"\b([A-Z][A-Z0-9]_[A-Z]{2,})\b", message):
        if m.group(1) not in entities["field_names"]:
            entities["field_names"].append(m.group(1))

    # Nomes de função AdvPL
    for m in re.finditer(r"\b([A-Z][a-zA-Z]+)\s*\(\)", message):
        entities["function_names"].append(m.group(1))

    return entities


# Indicadores de tarefa complexa (multi-step)
_COMPLEX_TASK_PATTERNS = [
    r"analis[ea].*e\s+(sugir|corrig|recomend|propon)",
    r"compar[ea].*e\s+(corri[gj]|equaliz|sincroni)",
    r"verifi[cq].*depois",
    r"primeiro.*depois",
    r"passo\s+a\s+passo",
    r"investig[ue]",
    r"diagnostiqu[e]",
    r"identifi[cq].*e\s+(corrig|resolv|sugir)",
]


def classify_complexity(message):
    """Classifica se a tarefa e simples ou complexa.

    Retorna 'complex' se a mensagem indica tarefa multi-step,
    'simple' caso contrario. Usado para injetar prompt de planning.
    """
    for pattern in _COMPLEX_TASK_PATTERNS:
        if re.search(pattern, message, re.IGNORECASE):
            return "complex"
    return "simple"


def user_skips_confirmation(message):
    """Detecta se o usuario autorizou a execucao na propria mensagem.

    Frases como "nem precisa perguntar", "pode ir direto", "manda ver",
    "executa logo" indicam que o usuario nao quer confirmacao.
    """
    skip_patterns = [
        r"n[aã]o\s+precisa\s+perguntar",
        r"nem\s+precisa\s+perguntar",
        r"nem\s+precisa\s+confirmar",
        r"pode\s+ir\s+direto",
        r"pode\s+executar",
        r"pode\s+rodar",
        r"manda\s+ver",
        r"executa\s+logo",
        r"vai\s+direto",
        r"sem\s+confirm",
        r"j[aá]\s+pode",
        r"faz\s+direto",
        r"roda\s+direto",
    ]
    msg_lower = message.lower()
    return any(re.search(p, msg_lower) for p in skip_patterns)
