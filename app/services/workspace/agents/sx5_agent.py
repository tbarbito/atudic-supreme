"""SX5Agent — SX5 generic table (combo) analysis and spec generation.

This agent handles demands related to Protheus SX5 generic tables (combos):
analyses existing tables, detects items, and generates a complete spec
for creating or altering combo items.
"""

import json
import unicodedata

from app.services.workspace.analista_tools import tool_buscar_tabela_generica

# ---------------------------------------------------------------------------
# Constants / Prompts
# ---------------------------------------------------------------------------

SX5_SYSTEM_PROMPT = """Você é um especialista em tabelas genéricas SX5 do TOTVS Protheus.
Especifique os itens da tabela genérica (combo):
- X5_TABELA: código da tabela (2 chars, ex: ZA)
- X5_CHAVE: chave do item (variável)
- X5_DESCRI: descrição em português (máx 30 chars)
- X5_DESCR2: descrição em inglês (opcional)
- X5_DESCR3: descrição em espanhol (opcional)

CONTEXTO:
{search_context}"""

_ANALYZE_RESPONSE_SCHEMA = """\
Retorne APENAS JSON válido (sem markdown, sem ```json) com a estrutura:
{
  "intent": "<criar|alterar|descrever>",
  "itens_spec": [
    {
      "tabela": "<XX>",
      "chave": "<chave>",
      "acao": "<criar|alterar>",
      "spec": {
        "X5_TABELA": "<XX>",
        "X5_CHAVE": "<chave>",
        "X5_DESCRI": "<descricao PT max 30 chars>",
        "X5_DESCR2": "<descricao EN ou vazio>",
        "X5_DESCR3": "<descricao ES ou vazio>"
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
    """Autonomous research phase for a SX5 generic table demand.

    Args:
        demand_text: raw demand text from the consultant.
        entities: dict with keys search_terms, tabelas, etc. (from orchestrator).
        db: Database instance already initialized.
        vs: VectorStore instance (optional, currently unused).

    Returns:
        research_results dict.
    """
    search_terms: list[str] = entities.get("search_terms") or []
    intent = _detect_intent(demand_text)

    # ------------------------------------------------------------------
    # 1. For each search term — lookup in SX5 via tool
    # ------------------------------------------------------------------
    tabelas_info: list[dict] = []
    seen_tabelas: set[str] = set()

    for termo in search_terms:
        try:
            results = tool_buscar_tabela_generica(termo=termo)
            for item in results:
                tabela_key = item.get("tabela", "")
                chave_key = item.get("chave", "")
                uid = f"{tabela_key}_{chave_key}"
                if uid not in seen_tabelas:
                    seen_tabelas.add(uid)
                    tabelas_info.append(item)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 2. Detect if referenced generic tables already exist
    # ------------------------------------------------------------------
    tabelas_existentes: set[str] = set()
    for item in tabelas_info:
        tabela = item.get("tabela", "")
        if tabela:
            tabelas_existentes.add(tabela)

    # ------------------------------------------------------------------
    # 3. Build search_context string
    # ------------------------------------------------------------------
    parts_ctx: list[str] = []

    parts_ctx.append(f"## Demanda\n{demand_text}")
    parts_ctx.append(f"## Intenção Detectada\n{intent}")

    if search_terms:
        parts_ctx.append(f"## Termos Pesquisados\n{', '.join(search_terms)}")

    if tabelas_info:
        lines = ["## Itens SX5 Encontrados"]
        # Group by tabela for readability
        by_tabela: dict[str, list[dict]] = {}
        for item in tabelas_info:
            t = item.get("tabela", "?")
            by_tabela.setdefault(t, []).append(item)
        for tabela, itens in by_tabela.items():
            lines.append(f"### Tabela {tabela} ({len(itens)} itens)")
            for it in itens:
                custom_flag = " [CUSTOM]" if it.get("custom") else ""
                lines.append(
                    f"  [{it.get('chave', '')}] {it.get('descricao', '')}{custom_flag}"
                )
        parts_ctx.append("\n".join(lines))
    else:
        parts_ctx.append("## Itens SX5 Encontrados\nNenhum item encontrado para os termos pesquisados.")

    if tabelas_existentes:
        parts_ctx.append(
            f"## Tabelas Genéricas Detectadas\n{', '.join(sorted(tabelas_existentes))}"
        )

    search_context = "\n\n".join(parts_ctx)

    return {
        "intent": intent,
        "tabelas_info": tabelas_info,
        "tabelas_existentes": sorted(tabelas_existentes),
        "search_context": search_context,
    }


# ---------------------------------------------------------------------------
# analyze()
# ---------------------------------------------------------------------------

def analyze(demand_text: str, research_results: dict, llm) -> dict:
    """Analyse research results with LLM and generate SX5 combo spec.

    Args:
        demand_text: raw demand text.
        research_results: dict returned by research().
        llm: LLMService instance with a _call(messages, temperature, use_gen) method.

    Returns:
        findings dict.
    """
    search_context = research_results.get("search_context", "")
    intent = research_results.get("intent", "descrever")

    system_content = SX5_SYSTEM_PROMPT.format(search_context=search_context)
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
            findings.setdefault("itens_spec", [])
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
            "itens_spec": [],
            "alertas": [],
            "precisa_confirmar": [
                "Qual é o código da tabela genérica SX5? (2 chars, ex: ZA)",
                "Quais são as chaves e descrições dos itens do combo?",
                "Os itens são customizados ou padrão Protheus?",
            ],
            "resposta_chat": (
                "Não consegui gerar a especificação da tabela genérica automaticamente. "
                "Por favor, forneça mais detalhes: código da tabela (2 chars), "
                "chaves e descrições dos itens do combo."
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
    itens_spec = findings.get("itens_spec") or []

    if intent not in ("criar", "alterar", "descrever"):
        return list(questions) if questions else [
            "Qual é a intenção da demanda? (criar tabela/item novo, alterar existente ou tirar dúvida?)"
        ]

    if not itens_spec and questions:
        return list(questions)

    return list(questions) if questions else []


# ---------------------------------------------------------------------------
# generate_artifacts()
# ---------------------------------------------------------------------------

def generate_artifacts(findings: dict) -> list[dict]:
    """Generate typed artifacts from findings.

    Returns a list of artifacts in the analista format.
    """
    itens_spec: list = findings.get("itens_spec") or []
    artifacts: list[dict] = []

    for item_entry in itens_spec:
        if not isinstance(item_entry, dict):
            continue
        tabela = item_entry.get("tabela", "")
        chave = item_entry.get("chave", "")
        acao = item_entry.get("acao", "criar")
        spec = item_entry.get("spec") or item_entry
        artifacts.append({
            "tipo": "combo",
            "nome": f"{tabela}/{chave}",
            "tabela": "SX5",
            "acao": acao,
            "spec_json": spec,
        })

    return artifacts
