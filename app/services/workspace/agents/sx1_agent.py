"""SX1Agent — SX1 question group analysis and spec generation.

This agent handles demands related to Protheus SX1 question groups:
analyses existing groups, detects questions, and generates a complete
spec for creating or altering groups and their questions.
"""

import json
import unicodedata

from app.services.workspace.analista_tools import tool_buscar_perguntas

# ---------------------------------------------------------------------------
# Constants / Prompts
# ---------------------------------------------------------------------------

SX1_SYSTEM_PROMPT = """Você é um especialista em grupos de perguntas SX1 do TOTVS Protheus.
Especifique as perguntas do grupo:
- X1_GRUPO: código do grupo (ex: AFA001)
- X1_ORDEM: ordem (01, 02, ...)
- X1_PERGUNT: texto da pergunta (máx 40 chars)
- X1_TIPO: C, N, D, L
- X1_TAMANHO: tamanho da resposta
- X1_GSC: G (global), S (por empresa), C (por filial)
- X1_VAR01: variável que armazena resposta (MV_PAR01, MV_PAR02, ...)

CONTEXTO:
{search_context}"""

_ANALYZE_RESPONSE_SCHEMA = """\
Retorne APENAS JSON válido (sem markdown, sem ```json) com a estrutura:
{
  "intent": "<criar|alterar|descrever>",
  "perguntas_spec": [
    {
      "grupo": "<codigo do grupo>",
      "ordem": "<01|02|...>",
      "acao": "<criar|alterar>",
      "spec": {
        "X1_GRUPO": "<codigo>",
        "X1_ORDEM": "<01|02|...>",
        "X1_PERGUNT": "<texto max 40 chars>",
        "X1_TIPO": "<C|N|D|L>",
        "X1_TAMANHO": <int>,
        "X1_GSC": "<G|S|C>",
        "X1_VAR01": "<MV_PAR01|MV_PAR02|...>"
      }
    }
  ],
  "alertas": ["<string>"],
  "precisa_confirmar": ["<pergunta>"],
  "resposta_chat": "<string markdown para mostrar ao usuario>"
}"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_markdown_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        text = text.rsplit("```", 1)[0]
    return text.strip()


def _normalize(text: str) -> str:
    return unicodedata.normalize("NFD", text).encode("ascii", "ignore").decode("utf-8").lower()


def _detect_intent(demand_text: str) -> str:
    """Heuristic intent detection without LLM."""
    low = _normalize(demand_text)
    criar_kw = ["criar", "novo", "nova", "adicionar", "incluir", "implantar"]
    alterar_kw = ["alterar", "mudar", "corrigir", "modificar", "ajustar",
                  "atualizar", "trocar"]
    if any(kw in low for kw in criar_kw):
        return "criar"
    if any(kw in low for kw in alterar_kw):
        return "alterar"
    return "descrever"


# ---------------------------------------------------------------------------
# research()
# ---------------------------------------------------------------------------

def research(demand_text: str, entities: dict, db, vs=None) -> dict:
    """Autonomous research phase for a SX1 question group demand.

    Args:
        demand_text: raw demand text from the consultant.
        entities: dict with keys grupos_sx1, parametros, tabelas, etc. (from orchestrator).
        db: Database instance already initialized.
        vs: VectorStore instance (optional, currently unused).

    Returns:
        research_results dict.
    """
    grupos: list[str] = entities.get("grupos_sx1") or []
    intent = _detect_intent(demand_text)

    # ------------------------------------------------------------------
    # 1. For each group entity — lookup in SX1 via tool
    # ------------------------------------------------------------------
    grupos_info: dict[str, list[dict]] = {}

    for grp in grupos:
        try:
            results = tool_buscar_perguntas(grupo=grp)
            grupos_info[grp] = results if results else []
        except Exception:
            grupos_info[grp] = []

    # ------------------------------------------------------------------
    # 2. Detect if groups already exist (have questions)
    # ------------------------------------------------------------------
    grupos_existentes = [grp for grp, perguntas in grupos_info.items() if perguntas]
    grupos_novos = [grp for grp, perguntas in grupos_info.items() if not perguntas]

    # ------------------------------------------------------------------
    # 3. Build search_context string
    # ------------------------------------------------------------------
    parts_ctx: list[str] = []

    parts_ctx.append(f"## Demanda\n{demand_text}")
    parts_ctx.append(f"## Intenção Detectada\n{intent}")

    if grupos_info:
        lines = ["## Grupos SX1 Pesquisados"]
        for grp, perguntas in grupos_info.items():
            status = "EXISTE" if perguntas else "NÃO EXISTE (a criar)"
            lines.append(f"### Grupo {grp} — {status}")
            if perguntas:
                lines.append(f"  Total de perguntas: {len(perguntas)}")
                for p in perguntas:
                    lines.append(
                        f"  [{p.get('ordem', '?')}] {p.get('pergunta', '')} "
                        f"| tipo: {p.get('tipo', '')} | tam: {p.get('tamanho', '')} "
                        f"| var: {p.get('variavel', '')}"
                    )
        parts_ctx.append("\n".join(lines))

    if grupos_existentes:
        parts_ctx.append(f"## Grupos Existentes\n{', '.join(grupos_existentes)}")
    if grupos_novos:
        parts_ctx.append(f"## Grupos Novos (a criar)\n{', '.join(grupos_novos)}")

    search_context = "\n\n".join(parts_ctx)

    return {
        "intent": intent,
        "grupos_info": grupos_info,
        "grupos_existentes": grupos_existentes,
        "grupos_novos": grupos_novos,
        "search_context": search_context,
    }


# ---------------------------------------------------------------------------
# analyze()
# ---------------------------------------------------------------------------

def analyze(demand_text: str, research_results: dict, llm) -> dict:
    """Analyse research results with LLM and generate question group spec.

    Args:
        demand_text: raw demand text.
        research_results: dict returned by research().
        llm: LLMService instance with a _call(messages, temperature, use_gen) method.

    Returns:
        findings dict.
    """
    search_context = research_results.get("search_context", "")
    intent = research_results.get("intent", "descrever")

    system_content = SX1_SYSTEM_PROMPT.format(search_context=search_context)
    system_content += f"\n\n{_ANALYZE_RESPONSE_SCHEMA}"

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": demand_text},
    ]

    raw = ""
    findings: dict = {}
    last_error: Exception | None = None

    for attempt in range(2):
        try:
            raw = llm._call(messages, temperature=0.2, use_gen=True)
            cleaned = _strip_markdown_json(raw)
            findings = json.loads(cleaned)
            findings.setdefault("intent", intent)
            findings.setdefault("perguntas_spec", [])
            findings.setdefault("alertas", [])
            findings.setdefault("precisa_confirmar", [])
            findings.setdefault("resposta_chat", "")
            last_error = None
            break
        except (json.JSONDecodeError, ValueError, KeyError) as exc:
            last_error = exc
            if attempt == 0:
                messages.append({"role": "assistant", "content": raw})
                messages.append({
                    "role": "user",
                    "content": (
                        "Sua resposta não é JSON válido. "
                        "Retorne APENAS o JSON puro, sem markdown, sem texto adicional."
                    ),
                })
        except Exception as exc:
            last_error = exc
            break

    if last_error is not None or not findings:
        findings = {
            "intent": intent,
            "perguntas_spec": [],
            "alertas": [],
            "precisa_confirmar": [
                "Qual é o código do grupo SX1? (ex: AFA001)",
                "Quantas perguntas o grupo deve ter?",
                "Qual o escopo? G (global), S (por empresa) ou C (por filial)?",
            ],
            "resposta_chat": (
                "Não consegui gerar a especificação do grupo de perguntas automaticamente. "
                "Por favor, forneça mais detalhes: código do grupo, quantidade de perguntas "
                "e escopo (global, empresa ou filial)."
            ),
        }

    return findings


# ---------------------------------------------------------------------------
# needs_clarification()
# ---------------------------------------------------------------------------

def needs_clarification(findings: dict) -> list[str]:
    """Return list of clarification questions if agent needs more info.

    Returns [] if findings are complete enough to generate artifacts.
    """
    questions: list[str] = findings.get("precisa_confirmar") or []
    intent = findings.get("intent")
    perguntas_spec = findings.get("perguntas_spec") or []

    if intent not in ("criar", "alterar", "descrever"):
        return list(questions) if questions else [
            "Qual é a intenção da demanda? (criar grupo novo, alterar existente ou tirar dúvida?)"
        ]

    if not perguntas_spec and questions:
        return list(questions)

    return list(questions) if questions else []


# ---------------------------------------------------------------------------
# generate_artifacts()
# ---------------------------------------------------------------------------

def generate_artifacts(findings: dict) -> list[dict]:
    """Generate typed artifacts from findings.

    Returns a list of artifacts in the analista format.
    """
    perguntas_spec: list = findings.get("perguntas_spec") or []
    artifacts: list[dict] = []

    for perg_entry in perguntas_spec:
        if not isinstance(perg_entry, dict):
            continue
        grupo = perg_entry.get("grupo", "")
        ordem = perg_entry.get("ordem", "")
        acao = perg_entry.get("acao", "criar")
        spec = perg_entry.get("spec") or perg_entry
        artifacts.append({
            "tipo": "pergunta",
            "nome": f"{grupo}-{ordem}",
            "tabela": "SX1",
            "acao": acao,
            "spec_json": spec,
        })

    return artifacts
