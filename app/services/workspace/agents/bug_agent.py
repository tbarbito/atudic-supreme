"""BugAgent — autonomous bug research, analysis and fix generation for Protheus systems.

This agent handles demands of type 'bug' or 'erro': identifies root cause, reads
source code, proposes a fix, and produces structured output (findings + artifacts).
"""

import json
import re
import unicodedata
from pathlib import Path

from app.services.workspace.config import load_config, get_client_workspace

CONFIG_PATH = Path("config.json")
WORKSPACE = Path("workspace")

# ---------------------------------------------------------------------------
# Constants / Prompts
# ---------------------------------------------------------------------------

BUG_SYSTEM_PROMPT = """Você é um especialista em manutenção de sistemas TOTVS Protheus.
Analise o bug descrito e o contexto pesquisado. Identifique:
1. A causa raiz do erro
2. O trecho exato do código ou configuração que precisa mudar
3. A correção proposta
4. O impacto da correção (o que mais pode ser afetado)

REGRAS:
- Seja direto e específico. Cite nomes de arquivos, campos e linhas quando souber.
- Para bugs de campo/dicionário: descreva o field_diff necessário
- Para bugs de código fonte: mostre o trecho atual e o trecho corrigido
- Formato do trecho de código: use blocos ```advpl ... ```
- Se não tiver certeza da causa raiz, diga o que SUSPEITA e o que precisaria confirmar

CONTEXTO PESQUISADO:
{search_context}
"""

# Bug-type hints to guide the LLM
_BUG_TYPE_HINTS: dict[str, str] = {
    "user_function_missing_underscore": (
        "TIPO DETECTADO: função de usuário sem underscore (U_). "
        "Verifique se a chamada da função omite o prefixo 'U_' obrigatório em AdvPL."
    ),
    "query_issue": (
        "TIPO DETECTADO: problema em query/RECNO. "
        "Verifique o uso de aliases, ORDER BY, índices e condições de filtro."
    ),
    "missing_field_sx3": (
        "TIPO DETECTADO: campo inexistente no dicionário SX3. "
        "Confirme se o campo foi criado via AtuDic / UPDDISTR e se o filial está correto."
    ),
    "validation_error": (
        "TIPO DETECTADO: erro de validação. "
        "Verifique a expressão do campo Valid, VldUser, gatilhos e o contexto de chamada."
    ),
    "field_mandatory": (
        "TIPO DETECTADO: campo obrigatório bloqueando gravação. "
        "Verifique X3_OBRIGAT, inicializador e se o campo aparece no formulário."
    ),
    "general_code_bug": (
        "TIPO DETECTADO: bug genérico de código. "
        "Analise o fluxo lógico, variáveis não inicializadas e chamadas a funções externas."
    ),
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_json(val):
    if not val:
        return []
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return []


def _strip_markdown_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        text = text.rsplit("```", 1)[0]
    return text.strip()


def _normalize(text: str) -> str:
    return unicodedata.normalize('NFD', text).encode('ascii', 'ignore').decode('utf-8').lower()


def _detect_bug_type(demand_text: str) -> str:
    """Heuristic bug-type detection without LLM."""
    low = _normalize(demand_text)
    if "underscore" in low or "sublinhado" in low:
        return "user_function_missing_underscore"
    if "query" in low or "recno" in low:
        return "query_issue"
    if "campo nao existe" in low or "campo inexistente" in low:
        return "missing_field_sx3"
    if "validacao" in low or "validation" in low:
        return "validation_error"
    if "obrigatorio" in low:
        return "field_mandatory"
    return "general_code_bug"


def _find_physical_file(arquivo: str) -> Path | None:
    """Search for a .prw/.tlpp file in workspace/*/fontes/** using glob."""
    try:
        config = load_config(CONFIG_PATH)
        if config and config.active_client:
            base = get_client_workspace(WORKSPACE, config.active_client) / "fontes"
        else:
            base = WORKSPACE
    except Exception:
        base = WORKSPACE

    if not base.exists():
        return None

    # Try exact name first, then case variations
    names_to_try = [arquivo]
    stem = Path(arquivo).stem
    for ext in [".prw", ".PRW", ".tlpp", ".TLPP"]:
        names_to_try.append(stem + ext)

    for name in names_to_try:
        matches = list(base.glob(f"**/{name}"))
        if matches:
            return matches[0]
    return None


def _extract_relevant_lines(content: str, demand_text: str, max_lines: int = 200) -> str:
    """Extract up to max_lines from file content, prioritising sections relevant to the demand."""
    lines = content.splitlines()
    if len(lines) <= max_lines:
        return content

    # Build keyword set from demand text
    keywords = {w.lower() for w in re.split(r"\W+", demand_text) if len(w) > 3}

    # Score each line
    scored: list[tuple[int, int]] = []  # (score, index)
    for idx, line in enumerate(lines):
        low = line.lower()
        score = sum(1 for kw in keywords if kw in low)
        scored.append((score, idx))

    # Keep top-scored lines + neighbourhood
    scored.sort(key=lambda x: -x[0])
    selected: set[int] = set()
    for score, idx in scored:
        if len(selected) >= max_lines:
            break
        if score == 0:
            break
        for i in range(max(0, idx - 3), min(len(lines), idx + 4)):
            selected.add(i)

    # If we have fewer than max_lines, fill from the top of the file
    remaining = max_lines - len(selected)
    for i in range(min(remaining, len(lines))):
        selected.add(i)

    selected_sorted = sorted(selected)[:max_lines]
    return "\n".join(lines[i] for i in selected_sorted)


# ---------------------------------------------------------------------------
# research()
# ---------------------------------------------------------------------------

def research(demand_text: str, entities: dict, db, vs=None) -> dict:
    """Autonomous research phase for a bug demand.

    Args:
        demand_text: raw demand text from the consultant.
        entities: dict with keys tabelas, campos, fontes, parametros (from orchestrator).
        db: Database instance (extrairpo.db do cliente). Must already be initialized.
        vs: VectorStore instance (optional, currently unused).

    Returns:
        research_results dict.
    """
    fontes_solicitadas: list[str] = entities.get("fontes") or []
    tabelas: list[str] = entities.get("tabelas") or []
    campos: list[str] = entities.get("campos") or []
    # parametros not currently used in research but kept for future use
    # parametros: list[str] = entities.get("parametros") or []

    bug_type = _detect_bug_type(demand_text)

    # ------------------------------------------------------------------
    # 1. Fontes
    # ------------------------------------------------------------------
    fontes_encontradas: list[dict] = []
    fontes_conteudo: dict[str, str] = {}

    for arquivo in fontes_solicitadas:
        stem = Path(arquivo).stem
        try:
            rows = db.execute(
                "SELECT arquivo, modulo, lines_of_code, read_tables, write_tables, exec_autos "
                "FROM fontes WHERE arquivo LIKE ? OR arquivo LIKE ?",
                (f"%{arquivo}%", f"%{stem}%"),
            ).fetchall()
        except Exception:
            rows = []

        if not rows:
            fontes_encontradas.append({"arquivo": arquivo, "encontrado": False, "nota": "não indexado no BD"})

        for row in rows:
            fontes_encontradas.append({
                "arquivo": row[0],
                "modulo": row[1] or "",
                "lines_of_code": row[2] or 0,
                "read_tables": _safe_json(row[3]),
                "write_tables": _safe_json(row[4]),
                "exec_autos": _safe_json(row[5]),
            })

        # Try to read the physical file (use original name or DB name)
        file_names = [arquivo] + [r[0] for r in rows]
        for fname in file_names:
            physical = _find_physical_file(fname)
            if physical and physical.exists():
                try:
                    content = physical.read_text(encoding="utf-8", errors="replace")
                    fontes_conteudo[fname] = _extract_relevant_lines(content, demand_text)
                except Exception:
                    pass
                break

    # ------------------------------------------------------------------
    # 2. Tabelas — impacto + info
    # ------------------------------------------------------------------
    tabelas_info: dict[str, dict] = {}
    impacto: dict[str, dict] = {}

    for tabela in tabelas:
        # tool_info_tabela — inline to avoid re-opening the DB
        try:
            row = db.execute(
                "SELECT codigo, nome FROM tabelas WHERE upper(codigo)=?",
                (tabela.upper(),),
            ).fetchone()
            if row:
                total = db.execute(
                    "SELECT COUNT(*) FROM campos WHERE upper(tabela)=?",
                    (tabela.upper(),),
                ).fetchone()[0]
                custom = db.execute(
                    "SELECT COUNT(*) FROM campos WHERE upper(tabela)=? AND custom=1",
                    (tabela.upper(),),
                ).fetchone()[0]
                indices = db.execute(
                    "SELECT COUNT(*) FROM indices WHERE upper(tabela)=?",
                    (tabela.upper(),),
                ).fetchone()[0]
                tabelas_info[tabela] = {
                    "tabela": row[0], "nome": row[1], "existe": True,
                    "total_campos": total, "campos_custom": custom, "indices": indices,
                }
            else:
                tabelas_info[tabela] = {"tabela": tabela, "existe": False}
        except Exception:
            tabelas_info[tabela] = {"tabela": tabela, "existe": False, "erro": "db_error"}

        # tool_analise_impacto — inline to avoid re-opening the DB
        try:
            fontes_rows = db.execute(
                "SELECT arquivo, modulo, write_tables, pontos_entrada, lines_of_code "
                "FROM fontes WHERE write_tables LIKE ?",
                (f'%"{tabela}"%',),
            ).fetchall()
            fontes_escrita = [
                {
                    "arquivo": r[0],
                    "modulo": r[1] or "",
                    "write_tables": _safe_json(r[2]),
                    "pontos_entrada": _safe_json(r[3]),
                    "loc": r[4] or 0,
                }
                for r in fontes_rows
            ]
            impacto[tabela] = {
                "tabela": tabela,
                "fontes_escrita": fontes_escrita,
                "total_fontes_escrita": len(fontes_escrita),
            }
        except Exception:
            impacto[tabela] = {"tabela": tabela, "fontes_escrita": [], "total_fontes_escrita": 0}

    # ------------------------------------------------------------------
    # 3. Campos
    # ------------------------------------------------------------------
    campos_info: dict[str, dict] = {}

    for campo_full in campos:
        parts = campo_full.split("_", 1)
        if len(parts) != 2:
            continue
        prefix, _ = parts
        # Derive table alias from field prefix (e.g. A1 -> SA1, C5 -> SC5)
        tabela_guess = f"S{prefix}" if len(prefix) == 2 else ""

        try:
            row = db.execute(
                "SELECT tipo, tamanho, validacao, vlduser, inicializador "
                "FROM campos WHERE campo=? AND (upper(tabela)=? OR upper(tabela) LIKE ?)",
                (campo_full, tabela_guess.upper(), f"%{prefix.upper()}%"),
            ).fetchone()
            if row:
                campos_info[campo_full] = {
                    "campo": campo_full,
                    "tipo": row[0] or "",
                    "tamanho": row[1] or 0,
                    "validacao": row[2] or "",
                    "vlduser": row[3] or "",
                    "inicializador": row[4] or "",
                }
            else:
                # Try with explicit table from entities
                for tabela in tabelas:
                    row2 = db.execute(
                        "SELECT tipo, tamanho, validacao, vlduser, inicializador "
                        "FROM campos WHERE upper(tabela)=? AND upper(campo)=?",
                        (tabela.upper(), campo_full.upper()),
                    ).fetchone()
                    if row2:
                        campos_info[campo_full] = {
                            "campo": campo_full,
                            "tipo": row2[0] or "",
                            "tamanho": row2[1] or 0,
                            "validacao": row2[2] or "",
                            "vlduser": row2[3] or "",
                            "inicializador": row2[4] or "",
                        }
                        break
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 4. Consolidate search_context
    # ------------------------------------------------------------------
    parts_ctx: list[str] = []

    parts_ctx.append(f"## Demanda\n{demand_text}")
    parts_ctx.append(f"## Tipo de Bug Detectado\n{bug_type}")

    if fontes_encontradas:
        lines = ["## Fontes no Banco de Dados"]
        for f in fontes_encontradas:
            if not f.get("encontrado", True):
                lines.append(f"- **{f['arquivo']}** — AVISO: não encontrado no banco de dados indexado.")
            else:
                lines.append(
                    f"- **{f['arquivo']}** | módulo: {f['modulo']} | LOC: {f['lines_of_code']}"
                    f" | escreve: {f['write_tables']}"
                )
        parts_ctx.append("\n".join(lines))

    for arquivo in fontes_solicitadas:
        if any(f.get("arquivo") == arquivo and not f.get("encontrado", True) for f in fontes_encontradas):
            parts_ctx.append(f"AVISO: {arquivo} não encontrado no banco de dados indexado.\n")

    if fontes_conteudo:
        for fname, content in fontes_conteudo.items():
            parts_ctx.append(f"## Conteúdo de {fname} (até 200 linhas relevantes)\n```advpl\n{content}\n```")

    if tabelas_info:
        lines = ["## Info das Tabelas"]
        for tabela, info in tabelas_info.items():
            if info.get("existe"):
                lines.append(
                    f"- **{tabela}** — {info.get('nome', '')} | "
                    f"campos: {info.get('total_campos', 0)} (custom: {info.get('campos_custom', 0)}) | "
                    f"índices: {info.get('indices', 0)}"
                )
            else:
                lines.append(f"- **{tabela}** — não encontrada no dicionário do cliente")
        parts_ctx.append("\n".join(lines))

    if impacto:
        lines = ["## Fontes que Escrevem nas Tabelas Mencionadas"]
        for tabela, imp in impacto.items():
            fontes_e = imp.get("fontes_escrita", [])
            if fontes_e:
                lines.append(f"### {tabela} ({len(fontes_e)} fontes)")
                for f in fontes_e[:10]:
                    lines.append(f"  - {f['arquivo']} ({f['modulo']})")
            else:
                lines.append(f"### {tabela} — nenhum fonte grava nesta tabela")
        parts_ctx.append("\n".join(lines))

    if campos_info:
        lines = ["## Info dos Campos"]
        for campo, info in campos_info.items():
            lines.append(
                f"- **{campo}** | tipo: {info.get('tipo','')} | tam: {info.get('tamanho','')} | "
                f"valid: {info.get('validacao','')} | vlduser: {info.get('vlduser','')} | "
                f"init: {info.get('inicializador','')}"
            )
        parts_ctx.append("\n".join(lines))

    search_context = "\n\n".join(parts_ctx)

    return {
        "bug_type": bug_type,
        "fontes_encontradas": fontes_encontradas,
        "fontes_conteudo": fontes_conteudo,
        "tabelas_info": tabelas_info,
        "campos_info": campos_info,
        "impacto": impacto,
        "search_context": search_context,
    }


# ---------------------------------------------------------------------------
# analyze()
# ---------------------------------------------------------------------------

_ANALYZE_RESPONSE_SCHEMA = """\
Retorne APENAS JSON válido (sem markdown, sem ```json) com a estrutura:
{
  "causa_raiz": "<string>",
  "tipo_fix": "<dict_change|code_change|null>",
  "fix_descricao": "<string>",
  "fix_codigo_atual": "<string ou vazio>",
  "fix_codigo_novo": "<string ou vazio>",
  "fix_artefatos": [],
  "impacto_fix": "<string>",
  "precisa_confirmar": [],
  "resposta_chat": "<string markdown para mostrar ao usuário>"
}"""


def analyze(demand_text: str, research_results: dict, llm) -> dict:
    """Analyse research results with LLM and propose a fix.

    Args:
        demand_text: raw demand text.
        research_results: dict returned by research().
        llm: LLMService instance with a _call(messages, temperature, use_gen) method.

    Returns:
        findings dict.
    """
    bug_type = research_results.get("bug_type", "general_code_bug")
    search_context = research_results.get("search_context", "")

    # Build system prompt
    bug_hint = _BUG_TYPE_HINTS.get(bug_type, "")
    system_content = BUG_SYSTEM_PROMPT.format(search_context=search_context)
    if bug_hint:
        system_content += f"\n\n{bug_hint}"
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
            # Ensure required keys exist
            findings.setdefault("causa_raiz", "")
            findings.setdefault("tipo_fix", None)
            findings.setdefault("fix_descricao", "")
            findings.setdefault("fix_codigo_atual", "")
            findings.setdefault("fix_codigo_novo", "")
            findings.setdefault("fix_artefatos", [])
            findings.setdefault("impacto_fix", "")
            findings.setdefault("precisa_confirmar", [])
            findings.setdefault("resposta_chat", findings.get("fix_descricao", ""))
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
        # Graceful fallback
        findings = {
            "causa_raiz": "Não foi possível determinar automaticamente. Revisão manual necessária.",
            "tipo_fix": None,
            "fix_descricao": "",
            "fix_codigo_atual": "",
            "fix_codigo_novo": "",
            "fix_artefatos": [],
            "impacto_fix": "",
            "precisa_confirmar": [
                "Qual é a mensagem de erro exata?",
                "Em qual ambiente o erro ocorre (produção/homologação)?",
                "Quais passos reproduzem o erro?",
            ],
            "resposta_chat": (
                "Não consegui analisar o bug automaticamente. "
                "Por favor, forneça mais detalhes: mensagem de erro exata, "
                "passos para reproduzir e ambiente afetado."
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
    tipo_fix = findings.get("tipo_fix")

    # Only surface questions when we don't yet know what fix to apply
    if questions and tipo_fix is None:
        return list(questions)
    return []


# ---------------------------------------------------------------------------
# generate_artifacts()
# ---------------------------------------------------------------------------

def generate_artifacts(findings: dict) -> list[dict]:
    """Generate typed artifacts from findings.

    Returns a list of artifacts in the analista format.
    """
    tipo_fix = findings.get("tipo_fix")
    artifacts: list[dict] = []

    if tipo_fix == "dict_change":
        raw_artefatos: list = findings.get("fix_artefatos") or []
        for item in raw_artefatos:
            if not isinstance(item, dict):
                continue
            artifacts.append({
                "tipo": item.get("tipo", "campo"),
                "nome": item.get("nome", ""),
                "tabela": item.get("tabela", ""),
                "acao": item.get("acao", "alterar"),
                "spec_json": item.get("spec_json") or item,
            })

    elif tipo_fix == "code_change":
        # Determine the source file name from research context or findings
        fix_descricao = findings.get("fix_descricao", "")
        fix_codigo_atual = findings.get("fix_codigo_atual", "")
        fix_codigo_novo = findings.get("fix_codigo_novo", "")

        # Try to extract filename from fix_descricao or fall back to generic name
        nome_arquivo = "fonte_alterado.prw"
        file_pattern = re.search(r"\b(\w+\.(?:prw|PRW|tlpp|TLPP))\b", fix_descricao)
        if file_pattern:
            nome_arquivo = file_pattern.group(1)

        artifacts.append({
            "tipo": "fonte",
            "nome": nome_arquivo,
            "tabela": "",
            "acao": "alterar",
            "spec_json": {
                "arquivo": nome_arquivo,
                "codigo_atual": fix_codigo_atual,
                "codigo_novo": fix_codigo_novo,
                "descricao_fix": fix_descricao,
            },
        })

    return artifacts
