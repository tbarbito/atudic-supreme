"""Investigation Planner — Plan-and-Execute pattern for the Analista.

Instead of letting the LLM pick tools ad-hoc, this module creates a
structured investigation plan BEFORE execution. The plan maps question
type to required tools, then the LLM refines it.
"""
import json
import asyncio
from typing import Optional

from app.services.workspace.padrao_crossref import auto_crossref_steps


# ── Plan templates by (modo, action_type) ─────────────────────────────────────
# These guide the LLM planner — not rigid, but a strong starting point.

PLAN_TEMPLATES = {
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
}


# ── Action type detection ─────────────────────────────────────────────────────

_ACTION_KEYWORDS = {
    "nao_salva": ["nao salva", "nao grava", "não salva", "não grava", "nao esta gravando",
                   "nao esta salvando", "não está gravando", "não está salvando", "nao gravar"],
    "erro": ["erro", "error", "fatal", "crash", "trava", "travando", "quebra",
             "nao abre", "não abre", "nao funciona", "não funciona"],
    "valor_errado": ["valor errado", "valor incorreto", "calculando errado", "calculo errado",
                     "mostrando errado", "valor diferente", "valor zerado", "zerando"],
    "processo": ["processo", "fluxo", "como funciona", "etapas", "workflow", "ciclo"],
    "tabela": ["tabela", "campos", "dicionario", "sx3", "estrutura"],
    "pe": ["ponto de entrada", "pe ", "execblock", "customizar rotina", "hook"],
    "campo": ["novo campo", "criar campo", "adicionar campo", "alterar campo", "incluir campo"],
    "aumento_campo": ["aumentar", "aumento", "ampliar", "expandir", "tamanho", "posicoes",
                       "posições", "de 15 para", "de 6 para", "para 30", "para 20"],
    "parametro": ["parametro", "mv_", "mgf_", "criar parametro"],
}


def _detect_action_type(message: str) -> str:
    """Detect action type from message keywords."""
    msg_lower = message.lower()
    for action_type, keywords in _ACTION_KEYWORDS.items():
        for kw in keywords:
            if kw in msg_lower:
                return action_type
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

    # Get template
    template_key = (modo, action_type)
    template = PLAN_TEMPLATES.get(template_key, PLAN_TEMPLATES.get((modo, "default"), []))

    # Format suggested steps
    suggested = "\n".join(
        f"  {i+1}. {s['tool']}: {s['reason']}"
        for i, s in enumerate(template)
    )

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
            return None

        # Ensure reasonable limits
        if len(plan["steps"]) > 8:
            plan["steps"] = plan["steps"][:8]
        plan.setdefault("reactive_steps", 2)
        plan.setdefault("cross_reference_padrao", False)
        plan.setdefault("objective", message[:100])

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

    except Exception:
        return None  # Fallback to unplanned ReAct
