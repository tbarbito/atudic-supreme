"""CampoAgent — SX3 field analysis, user function validation, and spec generation.

This agent handles demands related to Protheus data dictionary fields (SX3):
analyses the field in depth, validates user functions, initializers and triggers,
and generates a complete spec for creating or altering the field via AtuDic.
"""

import json
import re
import unicodedata
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants / Prompts
# ---------------------------------------------------------------------------

CAMPO_SYSTEM_PROMPT = """Você é um especialista em dicionário de dados TOTVS Protheus (SX3).
Analise a demanda do consultor e gere a especificação completa do campo.

PARA CADA CAMPO, ESPECIFIQUE:
- tipo: C (caractere), N (numérico), D (data), L (lógico), M (memo)
- tamanho: inteiro (para C e N)
- decimal: inteiro (só para N)
- titulo: string curta (máx 20 chars, sem acentos problemáticos)
- descricao: string explicativa
- validacao: expressão ADVPL (ex: "ExistCpo('SA1',A1_ZCODINT,1)")
- vlduser: user function customizada se necessário (com underscore: "U_XYZVAL")
- inicializador: expressão para valor inicial
- obrigatorio: "S" ou "N"
- browse: "S" ou "N" (aparece na grid de consulta)
- contexto: "R" (real) ou "V" (virtual)

REGRAS PROTHEUS:
- Campos customizados SEMPRE começam com Z no sufixo (A1_ZCODINT, não A1_CODINT)
- User functions SEMPRE começam com "U_" (U_VALCODINT, não VALCODINT)
- Validações com ExistCpo: ExistCpo("ALIAS", xFilial("ALIAS")+CAMPO, colunaPK)
- Campos obrigatórios: alerte impacto nos ExecAutos e integrações

CONTEXTO PESQUISADO:
{search_context}
"""

_ANALYZE_RESPONSE_SCHEMA = """\
Retorne APENAS JSON válido (sem markdown, sem ```json) com a estrutura:
{
  "intent": "<criar|alterar|descrever>",
  "campos_spec": [
    {
      "campo": "<TABELA_CAMPO>",
      "tabela": "<TABELA>",
      "acao": "<criar|alterar>",
      "spec": {
        "tipo": "<C|N|D|L|M>",
        "tamanho": <int>,
        "decimal": <int>,
        "titulo": "<string max 20 chars>",
        "descricao": "<string>",
        "validacao": "<expressao ADVPL ou vazio>",
        "vlduser": "<U_FUNCNAME ou vazio>",
        "inicializador": "<expressao ou vazio>",
        "obrigatorio": "<S|N>",
        "browse": "<S|N>",
        "contexto": "<R|V>"
      }
    }
  ],
  "alertas": ["<string>"],
  "impacto_descricao": "<string>",
  "precisa_confirmar": ["<pergunta>"],
  "resposta_chat": "<string markdown para mostrar ao usuário>"
}"""

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
    return unicodedata.normalize("NFD", text).encode("ascii", "ignore").decode("utf-8").lower()


def _detect_intent(demand_text: str) -> str:
    """Heuristic intent detection without LLM."""
    low = _normalize(demand_text)
    criar_kw = ["criar", "novo", "nova", "adicionar", "incluir", "implantar"]
    alterar_kw = ["alterar", "mudar", "corrigir", "obrigatorio", "validacao",
                  "modificar", "ajustar", "atualizar", "trocar"]
    if any(kw in low for kw in criar_kw):
        return "criar"
    if any(kw in low for kw in alterar_kw):
        return "alterar"
    return "descrever"


def _extract_functions(expression: str) -> list[str]:
    """Extract function call names from an ADVPL expression."""
    if not expression:
        return []
    pattern = re.compile(r'\b([A-Z][A-Za-z0-9]+)\s*\(')
    # Known Protheus built-ins to exclude from user-function checks
    builtins = {
        "ExistCpo", "ExistChav", "xFilial", "Space", "Str", "Val", "SubStr",
        "AllTrim", "RTrim", "LTrim", "Upper", "Lower", "Date", "Time", "SToD",
        "DToS", "CToD", "DToC", "Len", "Empty", "IsNil", "Type", "IIf",
        "MsExecAuto", "ExecBlock", "FWExecView", "GetSX8Num", "GravaRec",
        "Posicione", "IndRegua", "MsSeek", "DbSeek", "RecLock", "MsUnlock",
        "FieldGet", "FieldPut", "Select", "Alias", "DbSelectArea",
    }
    matches = pattern.findall(expression)
    return [m for m in matches if m not in builtins]


def _derive_table(campo_full: str, entities_tabelas: list[str]) -> str:
    """Best-effort table derivation from field name (e.g. A1_ZCODE -> SA1)."""
    parts = campo_full.split("_", 1)
    if len(parts) == 2:
        prefix = parts[0]
        if len(prefix) == 2:
            guessed = f"S{prefix}"
            # Prefer an explicit entity match
            for t in entities_tabelas:
                if t.upper() == guessed.upper():
                    return t.upper()
            return guessed.upper()
    # Fall back to first entity table if available
    if entities_tabelas:
        return entities_tabelas[0].upper()
    return ""


def _fetch_tabela_info(db, tabela: str) -> dict:
    """Inline table info query (mirrors tool_info_tabela but uses existing db)."""
    try:
        row = db.execute(
            "SELECT codigo, nome FROM tabelas WHERE upper(codigo)=?",
            (tabela.upper(),),
        ).fetchone()
        if not row:
            return {"tabela": tabela, "existe": False}
        total = db.execute(
            "SELECT COUNT(*) FROM campos WHERE upper(tabela)=?", (tabela.upper(),)
        ).fetchone()[0]
        custom = db.execute(
            "SELECT COUNT(*) FROM campos WHERE upper(tabela)=? AND custom=1",
            (tabela.upper(),),
        ).fetchone()[0]
        indices = db.execute(
            "SELECT COUNT(*) FROM indices WHERE upper(tabela)=?", (tabela.upper(),)
        ).fetchone()[0]
        return {
            "tabela": row[0], "nome": row[1], "existe": True,
            "total_campos": total, "campos_custom": custom, "indices": indices,
        }
    except Exception:
        return {"tabela": tabela, "existe": False, "erro": "db_error"}


def _fetch_impacto(db, tabela: str) -> dict:
    """Inline impact analysis (mirrors bug_agent pattern)."""
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
        return {
            "tabela": tabela,
            "fontes_escrita": fontes_escrita,
            "total_fontes_escrita": len(fontes_escrita),
        }
    except Exception:
        return {"tabela": tabela, "fontes_escrita": [], "total_fontes_escrita": 0}


def _lookup_user_function(db, funcname: str) -> bool:
    """Return True if funcname appears to be a known customized function in the DB."""
    try:
        row = db.execute(
            "SELECT arquivo FROM fontes WHERE conteudo_resumo LIKE ? OR arquivo LIKE ?",
            (f"%{funcname}%", f"%{funcname}%"),
        ).fetchone()
        return row is not None
    except Exception:
        return False


# ---------------------------------------------------------------------------
# research()
# ---------------------------------------------------------------------------

def research(demand_text: str, entities: dict, db, vs=None) -> dict:
    """Autonomous research phase for a campo (SX3) demand.

    Args:
        demand_text: raw demand text from the consultant.
        entities: dict with keys tabelas, campos, fontes, parametros (from orchestrator).
        db: Database instance already initialized.
        vs: VectorStore instance (optional, currently unused).

    Returns:
        research_results dict.
    """
    tabelas: list[str] = entities.get("tabelas") or []
    campos_entities: list[str] = entities.get("campos") or []

    intent = _detect_intent(demand_text)

    # ------------------------------------------------------------------
    # 1. For each campo entity — lookup in SX3
    # ------------------------------------------------------------------
    campos_info: dict[str, dict] = {}
    tabelas_para_pesquisar: set[str] = set(t.upper() for t in tabelas)

    for campo_full in campos_entities:
        tabela = _derive_table(campo_full, tabelas)
        if tabela:
            tabelas_para_pesquisar.add(tabela)

        dados_atuais = None
        try:
            row = db.execute(
                "SELECT tipo, tamanho, decimal, titulo, descricao, validacao, vlduser, "
                "inicializador, obrigatorio, browse, context, f3, cbox, when_expr "
                "FROM campos WHERE upper(tabela)=? AND upper(campo)=?",
                (tabela, campo_full.upper()),
            ).fetchone()
            if row:
                dados_atuais = {
                    "tipo": row[0] or "",
                    "tamanho": row[1] or 0,
                    "decimal": row[2] or 0,
                    "titulo": row[3] or "",
                    "descricao": row[4] or "",
                    "validacao": row[5] or "",
                    "vlduser": row[6] or "",
                    "inicializador": row[7] or "",
                    "obrigatorio": row[8] or "N",
                    "browse": row[9] or "N",
                    "context": row[10] or "R",
                    "f3": row[11] or "",
                    "cbox": row[12] or "",
                    "when_expr": row[13] or "",
                }
        except Exception:
            pass

        campos_info[campo_full] = {
            "existe": dados_atuais is not None,
            "tabela": tabela,
            "dados_atuais": dados_atuais,
        }

    # ------------------------------------------------------------------
    # 2. Table info for all relevant tables
    # ------------------------------------------------------------------
    tabelas_info: dict[str, dict] = {}
    for tabela in tabelas_para_pesquisar:
        tabelas_info[tabela] = _fetch_tabela_info(db, tabela)

    # ------------------------------------------------------------------
    # 3. User function validation — scan validacao + vlduser expressions
    # ------------------------------------------------------------------
    user_functions_found: list[str] = []
    user_functions_missing: list[str] = []

    for campo_full, info in campos_info.items():
        dados = info.get("dados_atuais") or {}
        expressions = [
            dados.get("validacao", ""),
            dados.get("vlduser", ""),
            dados.get("when_expr", ""),
        ]
        for expr in expressions:
            funcs = _extract_functions(expr)
            for fn in funcs:
                # Only check candidates that look like user functions
                # (start with U_ pattern or uppercase prefix) — exclude obvious built-ins
                if fn.startswith("U_") or fn.upper() == fn:
                    if _lookup_user_function(db, fn):
                        if fn not in user_functions_found:
                            user_functions_found.append(fn)
                    else:
                        if fn not in user_functions_missing:
                            user_functions_missing.append(fn)

    # ------------------------------------------------------------------
    # 4. Impact analysis for existing fields being altered
    # ------------------------------------------------------------------
    impacto: dict | None = None

    altered_tabelas: set[str] = set()
    for campo_full, info in campos_info.items():
        if info["existe"] and info["tabela"]:
            altered_tabelas.add(info["tabela"])
    # Also include tabelas from entities if intent is alterar
    if intent == "alterar":
        for t in tabelas_para_pesquisar:
            altered_tabelas.add(t)

    if altered_tabelas:
        impacto = {}
        for tabela in altered_tabelas:
            impacto[tabela] = _fetch_impacto(db, tabela)

    # ------------------------------------------------------------------
    # 5. Build search_context string
    # ------------------------------------------------------------------
    parts_ctx: list[str] = []

    parts_ctx.append(f"## Demanda\n{demand_text}")
    parts_ctx.append(f"## Intenção Detectada\n{intent}")

    if campos_info:
        lines = ["## Campos Pesquisados (SX3)"]
        for campo_full, info in campos_info.items():
            status = "EXISTE" if info["existe"] else "NÃO EXISTE (a criar)"
            lines.append(f"### {campo_full} — {status} | tabela: {info['tabela']}")
            if info["existe"] and info["dados_atuais"]:
                d = info["dados_atuais"]
                lines.append(
                    f"  tipo: {d['tipo']} | tam: {d['tamanho']} | dec: {d['decimal']} "
                    f"| titulo: {d['titulo']} | obrig: {d['obrigatorio']}"
                )
                if d.get("validacao"):
                    lines.append(f"  validacao: {d['validacao']}")
                if d.get("vlduser"):
                    lines.append(f"  vlduser: {d['vlduser']}")
                if d.get("inicializador"):
                    lines.append(f"  inicializador: {d['inicializador']}")
        parts_ctx.append("\n".join(lines))

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

    if user_functions_found or user_functions_missing:
        lines = ["## User Functions nas Validações"]
        if user_functions_found:
            lines.append(f"  Encontradas no BD: {', '.join(user_functions_found)}")
        if user_functions_missing:
            lines.append(f"  NÃO encontradas no BD: {', '.join(user_functions_missing)}")
        parts_ctx.append("\n".join(lines))

    if impacto:
        lines = ["## Análise de Impacto (Fontes que Escrevem nas Tabelas)"]
        for tabela, imp in impacto.items():
            fontes_e = imp.get("fontes_escrita", [])
            if fontes_e:
                lines.append(f"### {tabela} ({len(fontes_e)} fontes)")
                for f in fontes_e[:10]:
                    lines.append(f"  - {f['arquivo']} ({f['modulo']})")
            else:
                lines.append(f"### {tabela} — nenhum fonte grava nesta tabela")
        parts_ctx.append("\n".join(lines))

    search_context = "\n\n".join(parts_ctx)

    return {
        "intent": intent,
        "campos_info": campos_info,
        "tabelas_info": tabelas_info,
        "user_functions": {
            "found": user_functions_found,
            "missing": user_functions_missing,
        },
        "impacto": impacto,
        "search_context": search_context,
    }


# ---------------------------------------------------------------------------
# analyze()
# ---------------------------------------------------------------------------

def analyze(demand_text: str, research_results: dict, llm) -> dict:
    """Analyse research results with LLM and generate field spec.

    Args:
        demand_text: raw demand text.
        research_results: dict returned by research().
        llm: LLMService instance with a _call(messages, temperature, use_gen) method.

    Returns:
        findings dict.
    """
    search_context = research_results.get("search_context", "")
    intent = research_results.get("intent", "descrever")
    user_functions = research_results.get("user_functions", {})
    missing_fns = user_functions.get("missing", [])

    system_content = CAMPO_SYSTEM_PROMPT.format(search_context=search_context)

    # Add alert about missing user functions
    if missing_fns:
        system_content += (
            f"\n\nALERTA: As seguintes funções foram encontradas em validações mas "
            f"NÃO estão catalogadas no banco de dados: {', '.join(missing_fns)}. "
            f"Mencione isso nos alertas e confirme se são funções padrão Protheus ou customizadas."
        )

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
            findings.setdefault("intent", intent)
            findings.setdefault("campos_spec", [])
            findings.setdefault("alertas", [])
            findings.setdefault("impacto_descricao", "")
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
        # Graceful fallback
        alertas = []
        if missing_fns:
            for fn in missing_fns:
                alertas.append(
                    f"{fn} chamada na validação mas não encontrada no BD — confirme se é padrão Protheus."
                )

        findings = {
            "intent": intent,
            "campos_spec": [],
            "alertas": alertas,
            "impacto_descricao": "",
            "precisa_confirmar": [
                "Qual é o nome exato do campo a criar/alterar (ex: A1_ZCODINT)?",
                "Qual a tabela destino?",
                "Quais são as regras de validação necessárias?",
            ],
            "resposta_chat": (
                "Não consegui gerar a especificação do campo automaticamente. "
                "Por favor, forneça mais detalhes: nome do campo, tabela destino "
                "e regras de negócio esperadas."
            ),
        }

    # Enrich alertas with missing user functions if not already done by LLM
    existing_alertas = findings.get("alertas", [])
    for fn in missing_fns:
        marker = fn
        if not any(marker in a for a in existing_alertas):
            existing_alertas.append(
                f"{fn} chamada na validação mas não encontrada no BD"
            )
    findings["alertas"] = existing_alertas

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
    campos_spec = findings.get("campos_spec") or []

    # Surface questions when intent is unknown/generic and no concrete spec was generated
    if intent not in ("criar", "alterar", "descrever"):
        return list(questions) if questions else [
            "Qual é a intenção da demanda? (criar novo campo, alterar existente ou tirar dúvida?)"
        ]

    # Surface questions if we have no spec and there are open questions
    if not campos_spec and questions:
        return list(questions)

    # Surface questions when intent is criar but no campo with Z suffix was identified
    if intent == "criar" and campos_spec:
        for spec_entry in campos_spec:
            campo_name = spec_entry.get("campo", "")
            parts = campo_name.split("_", 1)
            if len(parts) == 2 and not parts[1].startswith("Z"):
                questions = list(questions)
                if not any("Z" in q or "customizado" in q for q in questions):
                    questions.append(
                        f"O campo '{campo_name}' não segue a convenção de customização "
                        f"(sufixo deve começar com Z, ex: {parts[0]}_Z{parts[1]}). Confirme o nome."
                    )

    return list(questions) if questions else []


# ---------------------------------------------------------------------------
# generate_artifacts()
# ---------------------------------------------------------------------------

def generate_artifacts(findings: dict) -> list[dict]:
    """Generate typed artifacts from findings.

    Returns a list of artifacts in the analista format.
    """
    campos_spec: list = findings.get("campos_spec") or []
    artifacts: list[dict] = []

    for campo_entry in campos_spec:
        if not isinstance(campo_entry, dict):
            continue
        artifacts.append({
            "tipo": "campo",
            "nome": campo_entry.get("campo", ""),
            "tabela": campo_entry.get("tabela", ""),
            "acao": campo_entry.get("acao", "criar"),
            "spec_json": campo_entry.get("spec") or campo_entry,
        })

    return artifacts
