"""Investigation Planner — Plan-and-Execute pattern for the Analista.

Instead of letting the LLM pick tools ad-hoc, this module creates a
structured investigation plan BEFORE execution. The plan maps question
type to required tools, then the LLM refines it.
"""
import json
import asyncio
import logging
from pathlib import Path
from typing import Optional

import yaml

from app.services.workspace.padrao_crossref import auto_crossref_steps

logger = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_RECIPES_DIR = _PROJECT_ROOT / "knowledge" / "recipes"
_ACTION_KEYWORDS_PATH = _PROJECT_ROOT / "knowledge" / "maps" / "action_keywords.yaml"

# ── Hardcoded fallbacks (used when YAML loading fails) ────────────────────────

_FALLBACK_PLAN_TEMPLATES = {
    # Ajuste (debugging)
    ("ajuste", "nao_salva"): [
        {"tool": "operacoes_escrita", "reason": "Mapear todos os pontos de escrita na tabela"},
        {"tool": "quem_grava", "reason": "Identificar quem grava especificamente o campo"},
        {"tool": "rastrear_condicao", "reason": "Rastrear origem de condições em escritas condicionais"},
        {"tool": "fonte_padrao", "reason": "Verificar comportamento padrão da rotina"},
    ],
    ("ajuste", "erro"): [
        {"tool": "buscar_menus", "reason": "Identificar a rotina pelo nome/tela"},
        {"tool": "ver_fonte_cliente", "reason": "Ler o código que gera o erro"},
        {"tool": "rastrear_condicao", "reason": "Rastrear a condição que causa o erro"},
        {"tool": "buscar_pes_cliente", "reason": "Verificar se há PE customizado interferindo"},
    ],
    ("ajuste", "valor_errado"): [
        {"tool": "quem_grava", "reason": "Quem grava o campo com valor errado"},
        {"tool": "rastrear_condicao", "reason": "De onde vem o valor"},
        {"tool": "ver_parametro", "reason": "Verificar parâmetros que influenciam"},
        {"tool": "ver_fonte_cliente", "reason": "Ler o código para entender a lógica"},
    ],
    ("ajuste", "default"): [
        {"tool": "buscar_menus", "reason": "Localizar a rotina"},
        {"tool": "operacoes_escrita", "reason": "Mapear escritas na tabela"},
        {"tool": "ver_fonte_cliente", "reason": "Ler código relevante"},
    ],

    # Duvida (understanding)
    ("duvida", "processo"): [
        {"tool": "buscar_menus", "reason": "Identificar rotinas do processo"},
        {"tool": "processos_cliente", "reason": "Verificar processos já detectados"},
        {"tool": "mapear_processo", "reason": "Mapa completo do processo"},
        {"tool": "pes_disponiveis", "reason": "PEs disponíveis nas rotinas"},
    ],
    ("duvida", "tabela"): [
        {"tool": "info_tabela", "reason": "Metadata da tabela"},
        {"tool": "operacoes_escrita", "reason": "Quem escreve nesta tabela"},
        {"tool": "buscar_fontes_tabela", "reason": "Fontes que acessam a tabela"},
    ],
    ("duvida", "pe"): [
        {"tool": "pes_disponiveis", "reason": "PEs disponíveis na rotina padrão"},
        {"tool": "codigo_pe", "reason": "Código fonte onde o PE é chamado"},
        {"tool": "buscar_pes_cliente", "reason": "Se o cliente já implementou"},
    ],
    ("duvida", "parametro"): [
        {"tool": "ver_parametro", "reason": "Consultar valor e descrição do parâmetro"},
        {"tool": "buscar_texto_fonte", "reason": "Buscar onde o parâmetro é usado nos fontes"},
        {"tool": "buscar_propositos", "reason": "Fontes que podem usar o parâmetro"},
    ],
    ("duvida", "default"): [
        {"tool": "buscar_menus", "reason": "Localizar rotinas relacionadas"},
        {"tool": "info_tabela", "reason": "Dados da tabela principal"},
        {"tool": "buscar_propositos", "reason": "Fontes relacionados por propósito"},
    ],

    # Melhoria (creating/altering)
    ("melhoria", "campo"): [
        {"tool": "info_tabela", "reason": "Verificar tabela destino e campos existentes"},
        {"tool": "analise_impacto", "reason": "Análise COMPLETA: fontes de escrita, MsExecAuto, integracoes, gatilhos — CRITICO para campo obrigatório"},
        {"tool": "operacoes_escrita", "reason": "Detalhe de todas operações de escrita na tabela"},
        {"tool": "buscar_pes_cliente", "reason": "PEs existentes para a rotina"},
        {"tool": "pes_disponiveis", "reason": "PEs disponíveis no padrão para customizar"},
    ],
    ("melhoria", "pe"): [
        {"tool": "pes_disponiveis", "reason": "PEs disponíveis na rotina padrão"},
        {"tool": "codigo_pe", "reason": "Como o PE é chamado no padrão"},
        {"tool": "fonte_padrao", "reason": "Estrutura da rotina padrão"},
        {"tool": "buscar_pes_cliente", "reason": "PEs já implementados pelo cliente"},
    ],
    ("melhoria", "aumento_campo"): [
        {"tool": "analise_aumento_campo", "reason": "Análise COMPLETA de aumento: grupo SXG, campos fora do grupo, PadR chumbado, índices, MsExecAuto"},
        {"tool": "info_tabela", "reason": "Metadata da tabela para contexto"},
        {"tool": "operacoes_escrita", "reason": "Fontes que gravam na tabela"},
    ],
    ("melhoria", "parametro"): [
        {"tool": "ver_parametro", "reason": "Verificar se parâmetro já existe"},
        {"tool": "buscar_propositos", "reason": "Fontes que poderiam usar o parâmetro"},
    ],
    ("melhoria", "default"): [
        {"tool": "buscar_menus", "reason": "Localizar rotinas impactadas"},
        {"tool": "info_tabela", "reason": "Dados da tabela principal"},
        {"tool": "operacoes_escrita", "reason": "Pontos de escrita"},
        {"tool": "pes_disponiveis", "reason": "Oportunidades de customização via PE"},
    ],

    # Gatilho (debugging)
    ("ajuste", "gatilho"): [
        {"tool": "info_tabela", "reason": "Ver gatilhos cadastrados na tabela"},
        {"tool": "ver_fonte_cliente", "reason": "Se gatilho chama funcao, ler o fonte"},
        {"tool": "buscar_texto_fonte", "reason": "Buscar a funcao do gatilho no codigo"},
        {"tool": "fonte_padrao", "reason": "Comparar com comportamento padrao"},
    ],
}

_FALLBACK_ACTION_KEYWORDS = {
    "nao_salva": ["nao salva", "nao grava", "não salva", "não grava", "nao esta gravando",
                   "nao esta salvando", "não está gravando", "não está salvando", "nao gravar"],
    "erro": ["erro", "error", "fatal", "crash", "trava", "travando", "quebra",
             "nao abre", "não abre", "nao funciona", "não funciona"],
    "valor_errado": ["valor errado", "valor incorreto", "calculando errado", "calculo errado",
                     "mostrando errado", "valor diferente", "valor zerado", "zerado", "zerando"],
    "processo": ["processo", "fluxo", "como funciona", "etapas", "workflow", "ciclo"],
    "tabela": ["tabela", "campos", "dicionario", "sx3", "estrutura"],
    "pe": ["ponto de entrada", "pontos de entrada", "pe ", "execblock", "customizar rotina", "hook"],
    "campo": ["novo campo", "criar campo", "adicionar campo", "alterar campo", "incluir campo",
              "obrigatorio", "obrigatório", "tornar obrigatorio"],
    "aumento_campo": ["aumentar", "aumento", "ampliar", "expandir", "tamanho", "posicoes",
                       "posições", "de 15 para", "de 6 para", "para 30", "para 20"],
    "parametro": ["parametro", "mv_", "mgf_", "ti_", "sy_", "xg_", "tx_", "mf_", "pt_",
                  "criar parametro", "supergetmv", "getmv", "putmv", "getnewpar"],
}

# ── YAML loaders (cached at module level) ────────────────────────────────────

_cached_recipes: Optional[list] = None
_cached_action_keywords: Optional[dict] = None
_cached_sx6_prefixes: Optional[list] = None


def _get_sx6_prefixes() -> list[str]:
    """Load parameter prefixes from client's SX6 table (cached).

    Returns list like ['MV_', 'MGF_', 'TI_', ...] — actual prefixes
    from the client's database, not hardcoded.
    """
    global _cached_sx6_prefixes
    if _cached_sx6_prefixes is not None:
        return _cached_sx6_prefixes

    try:
        import sqlite3
        from app.services.workspace.config import load_config, get_client_workspace
        config = load_config(Path("config.json"))
        client_dir = get_client_workspace(Path("workspace"), config.active_client)
        db_path = client_dir / "db" / "extrairpo.db"
        if not db_path.exists():
            _cached_sx6_prefixes = []
            return []

        db = sqlite3.connect(str(db_path))
        rows = db.execute(
            "SELECT DISTINCT SUBSTR(variavel, 1, INSTR(variavel, '_')) "
            "FROM parametros WHERE INSTR(variavel, '_') > 0"
        ).fetchall()
        db.close()

        _cached_sx6_prefixes = [r[0] for r in rows if r[0] and len(r[0]) >= 2]
        logger.info(f"Loaded {len(_cached_sx6_prefixes)} SX6 prefixes from client DB")
        return _cached_sx6_prefixes
    except Exception as e:
        logger.warning(f"Failed to load SX6 prefixes: {e}")
        _cached_sx6_prefixes = []
        return []


def _load_recipes() -> list:
    """Read all YAML files from knowledge/recipes/ and return as a list of dicts.

    Each dict has at least: id, modo, action_type, steps (list of {tool, reason}).
    Results are cached after first successful load.
    """
    global _cached_recipes
    if _cached_recipes is not None:
        return _cached_recipes

    recipes = []
    if not _RECIPES_DIR.is_dir():
        logger.warning("Recipes directory not found: %s — using fallback templates", _RECIPES_DIR)
        return recipes

    for yaml_path in sorted(_RECIPES_DIR.glob("*.yaml")):
        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if not isinstance(data, dict):
                continue
            # Ensure required fields
            if "modo" in data and "action_type" in data and "steps" in data:
                # Normalize steps to [{tool, reason}]
                steps = []
                for s in data["steps"]:
                    if isinstance(s, dict) and "tool" in s:
                        steps.append({"tool": s["tool"], "reason": s.get("reason", "")})
                data["steps"] = steps
                recipes.append(data)
        except Exception as e:
            logger.warning("Failed to load recipe %s: %s", yaml_path.name, e)

    if recipes:
        logger.info("Loaded %d investigation recipes from YAML", len(recipes))
        _cached_recipes = recipes
    else:
        logger.warning("No valid recipes found in %s — using fallback templates", _RECIPES_DIR)

    return recipes


def _load_action_keywords() -> dict:
    """Read action_keywords.yaml and return {action_type: [keywords]}.

    Falls back to _FALLBACK_ACTION_KEYWORDS on any error.
    Results are cached after first successful load.
    """
    global _cached_action_keywords
    if _cached_action_keywords is not None:
        return _cached_action_keywords

    try:
        with open(_ACTION_KEYWORDS_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict) or "action_types" not in data:
            raise ValueError("Missing 'action_types' key")

        keywords = {}
        for action_type, spec in data["action_types"].items():
            if isinstance(spec, dict) and "keywords" in spec:
                keywords[action_type] = spec["keywords"]

        if keywords:
            logger.info("Loaded %d action types from YAML", len(keywords))
            _cached_action_keywords = keywords
            return keywords
        else:
            raise ValueError("No action types parsed")
    except Exception as e:
        logger.warning("Failed to load action_keywords YAML: %s — using fallback", e)
        _cached_action_keywords = _FALLBACK_ACTION_KEYWORDS
        return _FALLBACK_ACTION_KEYWORDS


def _get_plan_template(modo: str, action_type: str) -> list:
    """Look up the matching recipe from loaded YAMLs.

    Falls back to _FALLBACK_PLAN_TEMPLATES if no YAML recipe matches.
    """
    recipes = _load_recipes()

    # First try exact match
    for recipe in recipes:
        if recipe.get("modo") == modo and recipe.get("action_type") == action_type:
            return recipe["steps"]

    # No YAML match — use hardcoded fallback
    template_key = (modo, action_type)
    return _FALLBACK_PLAN_TEMPLATES.get(
        template_key,
        _FALLBACK_PLAN_TEMPLATES.get((modo, "default"), []),
    )


# ── Public aliases for backward compatibility ─────────────────────────────────

PLAN_TEMPLATES = _FALLBACK_PLAN_TEMPLATES
_ACTION_KEYWORDS = _FALLBACK_ACTION_KEYWORDS


def _detect_action_type(message: str) -> str:
    """Detect action type from message keywords (loaded from YAML, fallback to hardcoded).

    Also checks dynamic SX6 prefixes for parameter detection.
    """
    msg_lower = message.lower()
    action_keywords = _load_action_keywords()
    for action_type, keywords in action_keywords.items():
        for kw in keywords:
            if kw in msg_lower:
                return action_type

    # Dynamic check: if message contains any SX6 prefix, it's about a parameter
    sx6_prefixes = _get_sx6_prefixes()
    if sx6_prefixes:
        for prefix in sx6_prefixes:
            if prefix.lower() in msg_lower:
                return "parametro"

    return "default"


# ── Plan creation ─────────────────────────────────────────────────────────────

PLANNER_PROMPT = """Voce e um planejador de investigacao tecnica Protheus.
Dado a pergunta do usuario e o contexto inicial, crie um plano de investigacao.

PERGUNTA: {message}
MODO: {modo}
CONTEXTO RESOLVIDO: {resolved_context}

PLANO SUGERIDO (baseado no tipo de questao):
{suggested_steps}

FERRAMENTAS DISPONIVEIS:
{tool_descriptions}

MAPEAMENTO DE ENTIDADES PROTHEUS (use para preencher args):
- Produto / codigo do produto → tabela=SB1, campo=B1_COD
- Cliente / codigo do cliente → tabela=SA1, campo=A1_COD
- Fornecedor → tabela=SA2, campo=A2_COD
- Pedido de venda → tabela=SC5, campo=C5_NUM
- Pedido de compra → tabela=SC7, campo=C7_NUM
- Nota fiscal entrada → tabela=SF1, campo=F1_DOC
- Nota fiscal saida → tabela=SF2, campo=F2_DOC
- Titulo financeiro → tabela=SE1/SE2, campo=E1_NUM/E2_NUM

INSTRUCOES:
1. Revise o plano sugerido e ajuste para a pergunta especifica
2. Adicione ou remova steps conforme necessario
3. Preencha os "args" corretos para cada tool — use o MAPEAMENTO acima para resolver nomes genericos
4. Se a pergunta envolve uma rotina especifica, inclua "fonte_padrao" e "pes_disponiveis"
5. Se a pergunta envolve escrita/gravacao, inclua "rastrear_condicao" quando houver condicoes
6. Maximo 8 steps (incluindo reactivos)
7. Defina "cross_reference_padrao": true se faz sentido comparar com padrao

Responda APENAS com JSON:
{{
  "objective": "O que estamos investigando",
  "steps": [
    {{"tool": "nome", "args": {{"param": "valor"}}, "reason": "por que"}},
    ...
  ],
  "cross_reference_padrao": true/false,
  "reactive_steps": 2
}}"""


def _extract_entities_from_message(message: str, classification: dict) -> dict:
    """Extract table, field, rotina, parametro, and numeric values from message.

    Returns: {tabelas: [], campos: [], rotinas: [], parametros: [], tamanho: int|None}
    """
    import re
    msg_upper = message.upper()
    tabelas = list(classification.get("tabelas", []))
    campos = re.findall(r'\b([A-Z][A-Z0-9]{1,2}_\w+)\b', msg_upper)

    # Extract rotina codes (MATA410, FINA050, CTBA102, etc.)
    rotinas = re.findall(
        r'\b((?:MATA|FINA|CTBA|MATF|MATR|TMKA|GPEA|CNTA|ATFA|PONA)\d{3}[A-Z]?)\b',
        msg_upper
    )

    # Extract parameter names — detect by SX6 prefixes + function context
    parametros = []
    # 1. Load real prefixes from SX6 (cached)
    sx6_prefixes = _get_sx6_prefixes()
    if sx6_prefixes:
        # Build regex from actual client prefixes
        prefix_pattern = "|".join(re.escape(p.rstrip("_")) for p in sx6_prefixes)
        parametros.extend(re.findall(
            r'\b((?:' + prefix_pattern + r')_\w+)\b', msg_upper
        ))
    else:
        # Fallback: common prefixes
        parametros.extend(re.findall(r'\b((?:MV|MGF|TI|SY|XG|TX|MF|PT|MFG)_\w+)\b', msg_upper))
    # 2. Anything in quotes after GetMV/SuperGetMV/PutMV — universal detection
    param_in_quotes = re.findall(r'(?:super)?getmv[(\s]*["\'](\w+)["\']', message, re.IGNORECASE)
    parametros.extend([p.upper() for p in param_in_quotes])
    # 3. Anything explicitly called "parametro X" in the message
    param_named = re.findall(r'param(?:etro)?\s+(\w{2,}_\w+)', message, re.IGNORECASE)
    parametros.extend([p.upper() for p in param_named])
    parametros = list(dict.fromkeys(parametros))  # deduplicate

    # Don't infer table from parameter names (MGF_FT58VL is NOT table SMG)
    campos_for_table = [c for c in campos if not c.startswith(("MV_", "MGF_"))]

    # Infer tables from field prefixes (but not from parameters)
    if not tabelas and campos_for_table:
        for campo in campos_for_table:
            prefix = campo[:2]
            table = "S" + prefix
            if re.match(r'^S[A-Z][A-Z0-9]$', table) and table not in tabelas:
                tabelas.append(table)

    # Extract numeric values (for tamanho)
    numbers = re.findall(r'\b(\d{1,3})\b', message)
    tamanho = None
    for n in numbers:
        val = int(n)
        if 10 <= val <= 250:
            tamanho = val

    return {
        "tabelas": tabelas,
        "campos": campos,
        "rotinas": rotinas,
        "parametros": parametros,
        "tamanho": tamanho,
    }


def _fill_template_args(template: list, entities: dict) -> list:
    """Fill template steps with extracted entities as args.

    This ensures the plan has concrete args even if the LLM doesn't fill them.
    """
    tabela = entities["tabelas"][0] if entities["tabelas"] else ""
    campo = entities["campos"][0] if entities["campos"] else ""
    tamanho = entities.get("tamanho")
    rotinas = entities.get("rotinas", [])
    parametros = entities.get("parametros", [])
    rotina = rotinas[0] if rotinas else ""
    parametro = parametros[0] if parametros else ""

    filled = []
    for step in template:
        s = dict(step)
        args = dict(s.get("args", {}))
        tool = s["tool"]

        # Fill args based on tool type
        if tool in ("analise_impacto", "info_tabela", "operacoes_escrita",
                     "buscar_fontes_tabela", "processos_cliente"):
            if tabela and "tabela" not in args:
                args["tabela"] = tabela
            if campo and "campo" not in args and tool == "analise_impacto":
                args["campo"] = campo

        elif tool == "analise_aumento_campo":
            if tabela and "tabela" not in args:
                args["tabela"] = tabela
            if campo and "campo" not in args:
                args["campo"] = campo
            if tamanho and "novo_tamanho" not in args:
                args["novo_tamanho"] = tamanho

        elif tool in ("quem_grava",):
            if tabela and "tabela" not in args:
                args["tabela"] = tabela
            if campo and "campo" not in args:
                args["campo"] = campo

        elif tool in ("buscar_pes_cliente", "pes_disponiveis"):
            # Use explicit rotina from message first
            if rotina and "rotina" not in args:
                args["rotina"] = rotina
            elif tabela and "rotina" not in args:
                # Fallback: infer rotina from table
                for r, info in ROTINA_MAP.items():
                    if info.get("tabela") == tabela:
                        args["rotina"] = r
                        break

        elif tool == "codigo_pe":
            # If we have a specific PE name from rotina context
            if rotina and "nome_pe" not in args:
                # Don't fill — let LLM decide which PE
                pass

        elif tool == "ver_parametro":
            if parametro and "nome" not in args:
                args["nome"] = parametro

        elif tool in ("ver_fonte_cliente", "buscar_texto_fonte"):
            pass  # These need specific arquivo — LLM fills

        s["args"] = args
        filled.append(s)
    return filled


# Rotina map for arg filling (imported from query_decomposer data)
try:
    from app.services.workspace.query_decomposer import ROTINA_MAP
except ImportError:
    ROTINA_MAP = {}


async def create_investigation_plan(
    llm,
    message: str,
    classification: dict,
    resolved_context: str,
    modo: str,
    tool_descriptions: str,
) -> Optional[dict]:
    """Create a structured investigation plan.

    Returns a plan dict or None if planning fails (fallback to ReAct).
    """
    action_type = _detect_action_type(message)
    entities = _extract_entities_from_message(message, classification)

    # Get template (from YAML recipes, fallback to hardcoded)
    template = _get_plan_template(modo, action_type)

    # Pre-fill template with extracted entities
    filled_template = _fill_template_args(template, entities)

    # Format suggested steps (with args for LLM context)
    suggested_parts = []
    for i, s in enumerate(filled_template):
        args_str = ""
        if s.get("args"):
            args_str = " " + json.dumps(s["args"], ensure_ascii=False)
        suggested_parts.append(f"  {i+1}. {s['tool']}{args_str}: {s['reason']}")
    suggested = "\n".join(suggested_parts)

    prompt = PLANNER_PROMPT.format(
        message=message,
        modo=modo,
        resolved_context=resolved_context[:2000],
        suggested_steps=suggested or "Nenhum template — LLM decide livremente",
        tool_descriptions=tool_descriptions,
    )

    try:
        response = await asyncio.to_thread(
            llm._call,
            [{"role": "user", "content": prompt}],
            temperature=0.1,
            use_gen=True,
            timeout=20,
        )

        # Parse JSON
        text = response.strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        plan = json.loads(text)

        # Validate plan structure
        if "steps" not in plan or not isinstance(plan["steps"], list):
            # LLM failed — use pre-filled template directly
            logger.warning("LLM plan invalid, using pre-filled template")
            plan = {
                "objective": message[:100],
                "steps": filled_template,
                "reactive_steps": 2,
                "cross_reference_padrao": False,
            }

        # Ensure reasonable limits
        if len(plan["steps"]) > 8:
            plan["steps"] = plan["steps"][:8]
        plan.setdefault("reactive_steps", 2)
        plan.setdefault("cross_reference_padrao", False)
        plan.setdefault("objective", message[:100])

        # Ensure critical tools from template aren't dropped by LLM
        plan_tools = {s.get("tool") for s in plan["steps"]}
        critical_tools = {"analise_impacto", "analise_aumento_campo"}
        for step in filled_template:
            if step["tool"] in critical_tools and step["tool"] not in plan_tools:
                logger.info(f"Re-injecting critical tool: {step['tool']}")
                plan["steps"].insert(0, step)

        # Auto-inject cross-reference steps if the plan or context mentions routines
        if plan.get("cross_reference_padrao", False):
            crossref_steps = auto_crossref_steps(classification, resolved_context)
            # Only add crossref steps that aren't already in the plan
            existing_tools = {(s.get("tool"), json.dumps(s.get("args", {}), sort_keys=True)) for s in plan["steps"]}
            for cs in crossref_steps:
                key = (cs["tool"], json.dumps(cs.get("args", {}), sort_keys=True))
                if key not in existing_tools:
                    plan["steps"].append(cs)

        return plan

    except Exception as e:
        # LLM failed entirely — use pre-filled template as plan
        logger.warning(f"Plan creation failed ({e}), using pre-filled template")
        if filled_template:
            return {
                "objective": message[:100],
                "steps": filled_template,
                "reactive_steps": 2,
                "cross_reference_padrao": False,
            }
        return None  # Fallback to unplanned ReAct
