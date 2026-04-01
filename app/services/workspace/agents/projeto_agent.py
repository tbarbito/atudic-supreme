"""ProjetoAgent — new project/feature analysis, artifact suggestion and AtuDic-ready output.

This agent handles demands of type 'projeto' or 'nova funcionalidade': researches the
technical context (tables, PEs, parameters, question groups, relevant sources), calls
an LLM to produce a complete solution proposal, and generates structured artifacts.
"""

import json
import re

# ---------------------------------------------------------------------------
# Constants / Prompts
# ---------------------------------------------------------------------------

PROJETO_SYSTEM_PROMPT = """Você é um analista técnico senior de ambientes TOTVS Protheus.
O consultor descreveu uma necessidade de novo projeto/funcionalidade. Com base no contexto pesquisado:

1. Analise a viabilidade e descreva a solução técnica
2. Identifique os artefatos necessários (campos, PEs, fontes, tabelas, gatilhos, parâmetros)
3. Mapeie os riscos e pontos de atenção (ExecAutos, integrações, campos obrigatórios)
4. Sugira os artefatos para o projeto

REGRAS:
- Seja proativo. Traga a solução JA PRONTA com riscos mapeados.
- Use os dados do CONTEXTO para listar fontes, integrações e ExecAutos concretos.
- Para campos novos: sempre com prefixo Z (A1_ZCAMPO).
- Para PEs: cite nome, rotina e paramixb.
- Para fontes novas: sugira tipo (user_function, report, job).
- Ao final, liste os artefatos sugeridos em JSON após ###ARTEFATOS###

CONTEXTO PESQUISADO:
{search_context}

ARTEFATOS EXISTENTES NO PROJETO:
{artefatos_existentes}
"""

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


def _extract_param_refs(demand_text: str) -> list[str]:
    """Extract SX6 parameter references (MV_XXXX, MGF_XXXX) from demand text."""
    return re.findall(r'\b(MV_\w+|MGF_\w+)\b', demand_text.upper())


def _extract_sx1_refs(demand_text: str) -> list[str]:
    """Extract SX1 group references (e.g. MTR001) from demand text."""
    return re.findall(r'\b([A-Z]{3}\d{3})\b', demand_text.upper())


# ---------------------------------------------------------------------------
# research()
# ---------------------------------------------------------------------------

def research(demand_text: str, entities: dict, db, vs=None) -> dict:
    """Autonomous research phase for a project/feature demand.

    NO LLM is called here — only database and vector index lookups.

    Args:
        demand_text: raw demand text from the consultant.
        entities: dict with keys tabelas, campos, modulos, parametros, fontes (from orchestrator).
        db: Database instance already initialized.
        vs: VectorStore instance (optional).

    Returns:
        research_results dict with keys:
            tabelas_impacto, tabelas_info, pes_disponiveis, parametros,
            perguntas, fontes_relevantes, search_context.
    """
    tabelas: list[str] = entities.get("tabelas") or []
    modulos: list[str] = entities.get("modulos") or []
    campos_entities: list[str] = entities.get("campos") or []
    parametros_entities: list[str] = entities.get("parametros") or []

    # ------------------------------------------------------------------
    # 1. Tables — impact analysis + info + deep field analysis
    # ------------------------------------------------------------------
    tabelas_impacto: dict[str, dict] = {}
    tabelas_info: dict[str, dict] = {}

    for tabela in tabelas[:3]:
        # Impact analysis — fontes that write, triggers, custom fields, ExecAutos, integrations
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

            gatilhos_rows = db.execute(
                "SELECT campo_origem, campo_destino, regra, tipo FROM gatilhos WHERE tabela=?",
                (tabela,),
            ).fetchall()
            gatilhos = [
                {
                    "campo_origem": g[0], "campo_destino": g[1],
                    "regra": g[2] or "", "tipo": g[3] or "",
                }
                for g in gatilhos_rows
            ]

            campos_custom_rows = db.execute(
                "SELECT campo, tipo, tamanho, titulo, descricao FROM campos "
                "WHERE upper(tabela)=? AND custom=1",
                (tabela.upper(),),
            ).fetchall()
            campos_custom = [
                {
                    "campo": c[0], "tipo": c[1], "tamanho": c[2],
                    "titulo": c[3] or "", "descricao": c[4] or "",
                }
                for c in campos_custom_rows
            ]

            exec_auto_rows = db.execute(
                "SELECT arquivo, modulo, calls_execblock, lines_of_code "
                "FROM fontes WHERE calls_execblock IS NOT NULL AND calls_execblock != '[]' "
                "AND write_tables LIKE ?",
                (f'%"{tabela}"%',),
            ).fetchall()
            exec_autos = [
                {
                    "arquivo": r[0], "modulo": r[1] or "",
                    "exec_autos": _safe_json(r[2]), "loc": r[3] or 0,
                }
                for r in exec_auto_rows
                if _safe_json(r[2])
            ]

            integ_rows = db.execute(
                "SELECT arquivo, modulo, write_tables, lines_of_code "
                "FROM fontes WHERE write_tables LIKE ? AND "
                "(upper(arquivo) LIKE '%WS%' OR upper(arquivo) LIKE '%INTEG%' "
                "OR upper(arquivo) LIKE '%API%' OR upper(arquivo) LIKE '%REST%' "
                "OR upper(arquivo) LIKE '%EDI%')",
                (f'%"{tabela}"%',),
            ).fetchall()
            integracoes = [
                {"arquivo": r[0], "modulo": r[1] or "", "loc": r[3] or 0}
                for r in integ_rows
            ]

            tabelas_impacto[tabela] = {
                "tabela": tabela,
                "fontes_escrita": fontes_escrita,
                "gatilhos": gatilhos,
                "campos_custom": campos_custom,
                "exec_autos": exec_autos,
                "integracoes": integracoes,
                "total_fontes_escrita": len(fontes_escrita),
                "total_exec_autos": len(exec_autos),
                "total_integracoes": len(integracoes),
            }
        except Exception:
            tabelas_impacto[tabela] = {
                "tabela": tabela, "fontes_escrita": [], "gatilhos": [],
                "campos_custom": [], "exec_autos": [], "integracoes": [],
                "total_fontes_escrita": 0, "total_exec_autos": 0, "total_integracoes": 0,
            }

        # Table info — name, field count, custom fields, indices
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

                # Deep field analysis — fetch top custom fields with full spec
                deep_campos: list[dict] = []
                try:
                    campo_rows = db.execute(
                        "SELECT campo, tipo, tamanho, titulo, descricao, validacao, "
                        "vlduser, inicializador, obrigatorio, browse "
                        "FROM campos WHERE upper(tabela)=? AND custom=1 LIMIT 20",
                        (tabela.upper(),),
                    ).fetchall()
                    for cr in campo_rows:
                        deep_campos.append({
                            "campo": cr[0], "tipo": cr[1], "tamanho": cr[2],
                            "titulo": cr[3] or "", "descricao": cr[4] or "",
                            "validacao": cr[5] or "", "vlduser": cr[6] or "",
                            "inicializador": cr[7] or "",
                            "obrigatorio": cr[8] or "N", "browse": cr[9] or "N",
                        })
                except Exception:
                    pass

                tabelas_info[tabela] = {
                    "tabela": row[0], "nome": row[1], "existe": True,
                    "total_campos": total, "campos_custom": custom, "indices": indices,
                    "deep_campos": deep_campos,
                }
            else:
                tabelas_info[tabela] = {"tabela": tabela, "existe": False}
        except Exception:
            tabelas_info[tabela] = {"tabela": tabela, "existe": False, "erro": "db_error"}

    # ------------------------------------------------------------------
    # 2. PEs available for each mentioned module
    # ------------------------------------------------------------------
    pes_disponiveis: list[dict] = []

    for mod in modulos[:2]:
        try:
            rows = db.execute(
                "SELECT nome, objetivo, modulo, rotina FROM padrao_pes WHERE upper(modulo) LIKE ?",
                (f"%{mod.upper()}%",),
            ).fetchall()
            for r in rows:
                pes_disponiveis.append({
                    "nome": r[0], "objetivo": r[1] or "",
                    "modulo": r[2] or "", "rotina": r[3] or "",
                })
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 3. SX6 Parameters — by table and by direct references in demand text
    # ------------------------------------------------------------------
    parametros: list[dict] = []
    _seen_params: set[str] = set()

    def _fetch_param(variavel: str) -> dict | None:
        try:
            row = db.execute(
                "SELECT variavel, tipo, descricao, conteudo, custom FROM parametros WHERE variavel=? LIMIT 1",
                (variavel,),
            ).fetchone()
            if row:
                padrao = db.execute(
                    "SELECT conteudo FROM padrao_parametros WHERE variavel=? LIMIT 1",
                    (row[0],),
                ).fetchone()
                return {
                    "variavel": row[0], "tipo": row[1] or "", "descricao": row[2] or "",
                    "conteudo": row[3] or "", "custom": row[4],
                    "valor_padrao": padrao[0] if padrao else "",
                }
        except Exception:
            pass
        return None

    # By table (params used by fontes that reference the table)
    for tabela in tabelas[:3]:
        try:
            fonte_rows = db.execute(
                "SELECT arquivo FROM fontes WHERE write_tables LIKE ? OR tabelas_ref LIKE ?",
                (f'%"{tabela}"%', f'%"{tabela}"%'),
            ).fetchall()
            for fr in fonte_rows:
                fd_rows = db.execute(
                    "SELECT params FROM funcao_docs WHERE arquivo=? AND params IS NOT NULL",
                    (fr[0],),
                ).fetchall()
                for fd in fd_rows:
                    parsed = _safe_json(fd[0])
                    if isinstance(parsed, dict):
                        for p in parsed.get("sx6", []):
                            var = p.get("var", "")
                            if var and var not in _seen_params:
                                _seen_params.add(var)
                                result = _fetch_param(var)
                                if result:
                                    result["usado_por_tabela"] = tabela
                                    parametros.append(result)
        except Exception:
            pass

    # Direct references in demand text
    param_refs = _extract_param_refs(demand_text)
    for pref in param_refs[:5]:
        if pref not in _seen_params:
            _seen_params.add(pref)
            try:
                rows = db.execute(
                    "SELECT variavel, tipo, descricao, conteudo, custom FROM parametros "
                    "WHERE upper(variavel) LIKE ? OR upper(descricao) LIKE ? LIMIT 5",
                    (f"%{pref.upper()}%", f"%{pref.upper()}%"),
                ).fetchall()
                for row in rows:
                    if row[0] not in _seen_params:
                        _seen_params.add(row[0])
                        padrao = db.execute(
                            "SELECT conteudo FROM padrao_parametros WHERE variavel=? LIMIT 1",
                            (row[0],),
                        ).fetchone()
                        parametros.append({
                            "variavel": row[0], "tipo": row[1] or "",
                            "descricao": row[2] or "", "conteudo": row[3] or "",
                            "custom": row[4],
                            "valor_padrao": padrao[0] if padrao else "",
                        })
            except Exception:
                pass

    # Explicitly listed parameters from entities
    for param in parametros_entities[:5]:
        if param not in _seen_params:
            _seen_params.add(param)
            result = _fetch_param(param)
            if result:
                parametros.append(result)

    # ------------------------------------------------------------------
    # 4. SX1 Question groups mentioned in demand text
    # ------------------------------------------------------------------
    perguntas: list[dict] = []
    sx1_refs = _extract_sx1_refs(demand_text)

    for grp in sx1_refs[:3]:
        try:
            rows = db.execute(
                "SELECT grupo, ordem, pergunta, tipo, tamanho FROM perguntas "
                "WHERE upper(grupo) LIKE ? ORDER BY grupo, ordem LIMIT 30",
                (f"%{grp.upper()}%",),
            ).fetchall()
            for r in rows:
                perguntas.append({
                    "grupo": r[0] or "", "ordem": r[1] or "",
                    "pergunta": r[2] or "", "tipo": r[3] or "", "tamanho": r[4] or "",
                })
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 5. Semantic search for relevant custom sources (if vs available)
    # ------------------------------------------------------------------
    fontes_relevantes: list[dict] = []

    if vs is not None:
        try:
            # Build query from demand text + entity names
            query_parts = [demand_text[:200]]
            query_parts.extend(tabelas[:3])
            query_parts.extend(modulos[:2])
            query = " ".join(query_parts)
            results = vs.search("fontes_custom", query, n_results=5)
            for r in results:
                arq = r.get("metadata", {}).get("arquivo", "")
                if arq:
                    fontes_relevantes.append({
                        "arquivo": arq,
                        "score": r.get("score", 0),
                        "metadata": r.get("metadata", {}),
                    })
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 6. Consolidate search_context string for LLM
    # ------------------------------------------------------------------
    parts_ctx: list[str] = []

    parts_ctx.append(f"## Demanda\n{demand_text}")

    if tabelas_info:
        lines = ["## Info das Tabelas Envolvidas"]
        for tabela, info in tabelas_info.items():
            if info.get("existe"):
                lines.append(
                    f"### {tabela} — {info.get('nome', '')} | "
                    f"campos: {info.get('total_campos', 0)} (custom: {info.get('campos_custom', 0)}) | "
                    f"índices: {info.get('indices', 0)}"
                )
                deep = info.get("deep_campos") or []
                if deep:
                    lines.append(f"  Campos customizados existentes ({len(deep)}):")
                    for dc in deep[:10]:
                        lines.append(
                            f"    - {dc['campo']} ({dc['tipo']}/{dc['tamanho']}) "
                            f"'{dc['titulo']}' obrig={dc['obrigatorio']}"
                        )
            else:
                lines.append(f"- **{tabela}** — não encontrada no dicionário do cliente")
        parts_ctx.append("\n".join(lines))

    if tabelas_impacto:
        lines = ["## Análise de Impacto nas Tabelas"]
        for tabela, imp in tabelas_impacto.items():
            fontes_e = imp.get("fontes_escrita", [])
            exec_a = imp.get("exec_autos", [])
            integs = imp.get("integracoes", [])
            gatilhos = imp.get("gatilhos", [])
            campos_c = imp.get("campos_custom", [])

            lines.append(f"### {tabela}")
            if fontes_e:
                lines.append(f"  Fontes que gravam ({len(fontes_e)}):")
                for f in fontes_e[:8]:
                    pes_str = ", ".join(f["pontos_entrada"][:3]) if f.get("pontos_entrada") else ""
                    pe_note = f" | PEs: {pes_str}" if pes_str else ""
                    lines.append(f"    - {f['arquivo']} ({f['modulo']}, {f['loc']} LOC){pe_note}")
            else:
                lines.append("  Nenhuma fonte grava nesta tabela.")

            if exec_a:
                lines.append(f"  ATENÇÃO — ExecAutos ({len(exec_a)} fontes):")
                for ea in exec_a[:5]:
                    execs_str = ", ".join(ea["exec_autos"][:3])
                    lines.append(f"    - {ea['arquivo']} ({ea['modulo']}) chama: {execs_str}")

            if integs:
                lines.append(f"  ATENÇÃO — Integrações ({len(integs)} fontes):")
                for intg in integs[:5]:
                    lines.append(f"    - {intg['arquivo']} ({intg['modulo']})")

            if gatilhos:
                lines.append(f"  Gatilhos ({len(gatilhos)}):")
                for g in gatilhos[:5]:
                    lines.append(f"    - {g['campo_origem']} -> {g['campo_destino']}: {g['regra'][:60]}")

            if campos_c:
                lines.append(f"  Campos custom existentes ({len(campos_c)}):")
                for c in campos_c[:8]:
                    lines.append(f"    - {c['campo']} ({c['tipo']}/{c['tamanho']}) '{c['titulo']}'")

        parts_ctx.append("\n".join(lines))

    if pes_disponiveis:
        lines = ["## Pontos de Entrada Disponíveis"]
        for pe in pes_disponiveis[:15]:
            lines.append(
                f"- **{pe['nome']}** | rotina: {pe['rotina']} | módulo: {pe['modulo']} | "
                f"objetivo: {pe['objetivo'][:80]}"
            )
        parts_ctx.append("\n".join(lines))

    if parametros:
        lines = ["## Parâmetros SX6 Relevantes"]
        for p in parametros[:15]:
            val = p["conteudo"] or "(vazio)"
            vp = p.get("valor_padrao", "")
            custom = " [CUSTOM]" if p.get("custom") else ""
            desc = p["descricao"][:80] if p.get("descricao") else "(sem descrição)"
            usado = f" | tabela: {p['usado_por_tabela']}" if p.get("usado_por_tabela") else ""
            lines.append(f"- **{p['variavel']}**: valor={val}, padrão={vp}, desc={desc}{custom}{usado}")
        parts_ctx.append("\n".join(lines))

    if perguntas:
        lines = ["## Grupos de Perguntas SX1"]
        current_group = None
        for pg in perguntas:
            if pg["grupo"] != current_group:
                current_group = pg["grupo"]
                lines.append(f"### Grupo {current_group}")
            lines.append(f"  - {pg['ordem']}: {pg['pergunta']} ({pg['tipo']}/{pg['tamanho']})")
        parts_ctx.append("\n".join(lines))

    if fontes_relevantes:
        lines = ["## Fontes Relevantes (Busca Semântica)"]
        for f in fontes_relevantes:
            lines.append(f"- {f['arquivo']}")
        parts_ctx.append("\n".join(lines))

    search_context = "\n\n".join(parts_ctx)

    return {
        "tabelas_impacto": tabelas_impacto,
        "tabelas_info": tabelas_info,
        "pes_disponiveis": pes_disponiveis,
        "parametros": parametros,
        "perguntas": perguntas,
        "fontes_relevantes": fontes_relevantes,
        "search_context": search_context,
    }


# ---------------------------------------------------------------------------
# analyze()
# ---------------------------------------------------------------------------

def analyze(demand_text: str, research_results: dict, llm, artefatos_existentes: str = "") -> dict:
    """Analyse research results with LLM and propose project artifacts.

    Args:
        demand_text: raw demand text.
        research_results: dict returned by research().
        llm: LLMService instance with a _call(messages, temperature, use_gen) method.
        artefatos_existentes: text listing artifacts already in the project (optional).

    Returns:
        findings dict with keys: resposta_chat, artefatos_sugeridos, precisa_confirmar.
    """
    search_context = research_results.get("search_context", "")

    system_content = PROJETO_SYSTEM_PROMPT.format(
        search_context=search_context,
        artefatos_existentes=artefatos_existentes or "Nenhum artefato ainda.",
    )

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": demand_text},
    ]

    raw = ""
    last_error: Exception | None = None

    for attempt in range(2):
        try:
            raw = llm._call(messages, temperature=0.3, use_gen=True)
            break
        except Exception as exc:
            last_error = exc
            if attempt == 0:
                # Brief retry on transient errors
                continue
            break

    if last_error is not None or not raw:
        return {
            "resposta_chat": (
                "Não consegui analisar a demanda automaticamente. "
                "Por favor, forneça mais detalhes sobre o projeto."
            ),
            "artefatos_sugeridos": [],
            "precisa_confirmar": [
                "Quais tabelas Protheus serão envolvidas?",
                "Qual o módulo principal da funcionalidade?",
                "Há campos novos ou apenas novos programas?",
            ],
        }

    # Parse ###ARTEFATOS### block from LLM response
    artefatos_sugeridos: list[dict] = []
    if "###ARTEFATOS###" in raw:
        parts = raw.split("###ARTEFATOS###", 1)
        chat_text = parts[0].strip()
        try:
            artefatos_raw = parts[1].strip()
            artefatos_raw = _strip_markdown_json(artefatos_raw)
            artefatos_sugeridos = json.loads(artefatos_raw)
            if not isinstance(artefatos_sugeridos, list):
                artefatos_sugeridos = []
        except (json.JSONDecodeError, IndexError):
            artefatos_sugeridos = []
    else:
        chat_text = raw

    return {
        "resposta_chat": chat_text,
        "artefatos_sugeridos": artefatos_sugeridos,
        "precisa_confirmar": [],
    }


# ---------------------------------------------------------------------------
# needs_clarification()
# ---------------------------------------------------------------------------

def needs_clarification(findings: dict) -> list[str]:
    """Return list of clarification questions if agent needs more info.

    For projects, clarification is rarely needed after research.
    Returns [] unless artifacts are empty AND no tables or sources were found in context.
    """
    artefatos = findings.get("artefatos_sugeridos") or []
    precisa = findings.get("precisa_confirmar") or []

    # If we have artefatos, no clarification needed
    if artefatos:
        return []

    # If explicitly flagged, surface the questions
    if precisa:
        return list(precisa)

    return []


# ---------------------------------------------------------------------------
# generate_artifacts()
# ---------------------------------------------------------------------------

def generate_artifacts(findings: dict) -> list[dict]:
    """Convert artefatos_sugeridos to the standard analista artifact format.

    Returns a list of artifacts in the analista format:
        tipo, nome, tabela, acao, spec_json.
    """
    artefatos_sugeridos: list = findings.get("artefatos_sugeridos") or []
    artifacts: list[dict] = []

    for art in artefatos_sugeridos:
        if not isinstance(art, dict):
            continue
        artifacts.append({
            "tipo": art.get("tipo"),
            "nome": art.get("nome"),
            "tabela": art.get("tabela", ""),
            "acao": art.get("acao", "criar"),
            "spec_json": {
                k: v for k, v in art.items()
                if k not in ("tipo", "nome", "tabela", "acao")
            },
        })

    return artifacts
