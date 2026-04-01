"""ParamAgent — SX6 parameter analysis and spec generation.

This agent handles demands related to Protheus SX6 parameters (MV_XXXX):
analyses existing params, detects usage in sources, and generates a complete
spec for creating or altering the parameter.
"""

import json
import unicodedata

from app.services.workspace.analista_tools import tool_buscar_parametros

# ---------------------------------------------------------------------------
# Constants / Prompts
# ---------------------------------------------------------------------------

PARAM_SYSTEM_PROMPT = """Você é um especialista em parâmetros SX6 do TOTVS Protheus.
Analise a demanda e especifique o parâmetro SX6:
- X6_VAR: nome (padrão MV_XXXX)
- X6_TIPO: N (numérico), C (caractere), D (data), L (lógico)
- X6_DESCRIC: descrição clara (máx 60 chars)
- X6_CONTEUD: valor atual/padrão
- X6_CONT1: valor mínimo (se numérico)
- X6_CONT2: valor máximo (se numérico)

CONTEXTO:
{search_context}"""

_ANALYZE_RESPONSE_SCHEMA = """\
Retorne APENAS JSON válido (sem markdown, sem ```json) com a estrutura:
{
  "intent": "<criar|alterar|descrever>",
  "parametros_spec": [
    {
      "variavel": "<MV_XXXX>",
      "acao": "<criar|alterar>",
      "spec": {
        "X6_VAR": "<MV_XXXX>",
        "X6_TIPO": "<N|C|D|L>",
        "X6_DESCRIC": "<descricao max 60 chars>",
        "X6_CONTEUD": "<valor padrao>",
        "X6_CONT1": "<valor minimo ou vazio>",
        "X6_CONT2": "<valor maximo ou vazio>"
      }
    }
  ],
  "fontes_impactadas": ["<arquivo>"],
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
    alterar_kw = ["alterar", "mudar", "corrigir", "obrigatorio", "modificar",
                  "ajustar", "atualizar", "trocar"]
    if any(kw in low for kw in criar_kw):
        return "criar"
    if any(kw in low for kw in alterar_kw):
        return "alterar"
    return "descrever"


# ---------------------------------------------------------------------------
# research()
# ---------------------------------------------------------------------------

def research(demand_text: str, entities: dict, db, vs=None) -> dict:
    """Autonomous research phase for a SX6 parameter demand.

    Args:
        demand_text: raw demand text from the consultant.
        entities: dict with keys parametros, tabelas, campos, fontes (from orchestrator).
        db: Database instance already initialized.
        vs: VectorStore instance (optional, currently unused).

    Returns:
        research_results dict.
    """
    parametros: list[str] = entities.get("parametros") or []
    intent = _detect_intent(demand_text)

    # ------------------------------------------------------------------
    # 1. For each parameter entity — lookup in SX6 via tool
    # ------------------------------------------------------------------
    parametros_info: list[dict] = []

    for param in parametros:
        try:
            results = tool_buscar_parametros(termo=param)
            if results:
                parametros_info.extend(results)
            else:
                parametros_info.append({
                    "variavel": param,
                    "descricao": "",
                    "conteudo": "",
                    "valor_padrao": "",
                    "tipo": "",
                    "custom": False,
                    "existe": False,
                })
        except Exception:
            parametros_info.append({
                "variavel": param,
                "descricao": "",
                "conteudo": "",
                "valor_padrao": "",
                "tipo": "",
                "custom": False,
                "existe": False,
            })

    # ------------------------------------------------------------------
    # 2. Find sources that use each parameter
    # ------------------------------------------------------------------
    fontes_usando: list[dict] = []

    for param in parametros:
        try:
            rows = db.execute(
                "SELECT arquivo, modulo FROM fontes WHERE conteudo_resumo LIKE ?",
                (f"%{param}%",),
            ).fetchall()
            for row in rows:
                entry = {"arquivo": row[0], "modulo": row[1] or "", "parametro": param}
                if entry not in fontes_usando:
                    fontes_usando.append(entry)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 3. Build search_context string
    # ------------------------------------------------------------------
    parts_ctx: list[str] = []

    parts_ctx.append(f"## Demanda\n{demand_text}")
    parts_ctx.append(f"## Intenção Detectada\n{intent}")

    if parametros_info:
        lines = ["## Parâmetros SX6 Pesquisados"]
        for p in parametros_info:
            existe = p.get("existe", True) if "existe" in p else bool(p.get("descricao"))
            status = "EXISTE" if existe else "NÃO EXISTE (a criar)"
            lines.append(f"### {p.get('variavel', '')} — {status}")
            if p.get("descricao"):
                lines.append(f"  descricao: {p['descricao']}")
            if p.get("conteudo"):
                lines.append(f"  conteudo: {p['conteudo']}")
            if p.get("valor_padrao"):
                lines.append(f"  valor_padrao: {p['valor_padrao']}")
            if p.get("tipo"):
                lines.append(f"  tipo: {p['tipo']}")
            if p.get("custom"):
                lines.append("  [CUSTOMIZADO]")
        parts_ctx.append("\n".join(lines))

    if fontes_usando:
        lines = ["## Fontes que Usam os Parâmetros"]
        for f in fontes_usando[:20]:
            lines.append(f"  - {f['arquivo']} ({f['modulo']}) — usa: {f['parametro']}")
        parts_ctx.append("\n".join(lines))
    else:
        parts_ctx.append("## Fontes que Usam os Parâmetros\nNenhuma fonte encontrada no BD.")

    search_context = "\n\n".join(parts_ctx)

    return {
        "intent": intent,
        "parametros_info": parametros_info,
        "fontes_usando": fontes_usando,
        "search_context": search_context,
    }


# ---------------------------------------------------------------------------
# analyze()
# ---------------------------------------------------------------------------

def analyze(demand_text: str, research_results: dict, llm) -> dict:
    """Analyse research results with LLM and generate parameter spec.

    Args:
        demand_text: raw demand text.
        research_results: dict returned by research().
        llm: LLMService instance with a _call(messages, temperature, use_gen) method.

    Returns:
        findings dict.
    """
    search_context = research_results.get("search_context", "")
    intent = research_results.get("intent", "descrever")
    fontes_usando = research_results.get("fontes_usando", [])

    system_content = PARAM_SYSTEM_PROMPT.format(search_context=search_context)
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
            findings.setdefault("parametros_spec", [])
            findings.setdefault("fontes_impactadas", [f["arquivo"] for f in fontes_usando])
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
            "parametros_spec": [],
            "fontes_impactadas": [f["arquivo"] for f in fontes_usando],
            "alertas": [],
            "precisa_confirmar": [
                "Qual é o nome do parâmetro SX6 a criar/alterar (ex: MV_XXXX)?",
                "Qual o tipo do parâmetro? (N numérico, C caractere, D data, L lógico)",
                "Qual o valor padrão do parâmetro?",
            ],
            "resposta_chat": (
                "Não consegui gerar a especificação do parâmetro automaticamente. "
                "Por favor, forneça mais detalhes: nome do parâmetro (MV_XXXX), "
                "tipo e valor padrão esperado."
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
    parametros_spec = findings.get("parametros_spec") or []

    if intent not in ("criar", "alterar", "descrever"):
        return list(questions) if questions else [
            "Qual é a intenção da demanda? (criar novo parâmetro, alterar existente ou tirar dúvida?)"
        ]

    if not parametros_spec and questions:
        return list(questions)

    return list(questions) if questions else []


# ---------------------------------------------------------------------------
# generate_artifacts()
# ---------------------------------------------------------------------------

def generate_artifacts(findings: dict) -> list[dict]:
    """Generate typed artifacts from findings.

    Returns a list of artifacts in the analista format.
    """
    parametros_spec: list = findings.get("parametros_spec") or []
    artifacts: list[dict] = []

    for param_entry in parametros_spec:
        if not isinstance(param_entry, dict):
            continue
        var = param_entry.get("variavel", "")
        acao = param_entry.get("acao", "criar")
        spec = param_entry.get("spec") or param_entry
        artifacts.append({
            "tipo": "parametro",
            "nome": var,
            "tabela": "SX6",
            "acao": acao,
            "spec_json": spec,
        })

    return artifacts
