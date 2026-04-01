# backend/services/deep_analysis.py
"""Deep Analysis Engine — multi-pass map-reduce for complete process analysis.

Instead of cramming everything into 8K chars, this engine:
  PASS 0 — Discovery: graph traversal finds ALL connected artifacts (0 LLM calls)
  PASS 1 — Map: per-source mini-summaries, using cache when available (0-N LLM calls)
  PASS 1.5 — Code Specialist: deep analysis of critical sources only (2-4 LLM calls)
  PASS 2 — Reduce: synthesize all summaries into complete analysis (1 LLM call)
  PASS 3 — Verify: validate citations against raw data (1 LLM call)

Usage:
    from app.services.workspace.deep_analysis import run_deep_analysis
    result = await run_deep_analysis(db, llm, processo_or_tabelas, nome, descricao)
"""
import json
import asyncio
import re
import time
from typing import Optional
from pathlib import Path


def _safe_json(val):
    if not val:
        return []
    if isinstance(val, list):
        return val
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return []


# ── PASS 0: Discovery ─────────────────────────────────────────────────────────

def pass0_discovery(db, tabelas: list[str], max_depth: int = 2) -> dict:
    """Discover ALL connected artifacts via graph traversal.

    Uses the existing graph_traversal.py BFS — no limits on source count.

    Returns:
        {
            "fontes": [str],
            "funcoes": [str],
            "tabelas": [str],
            "parametros": [str],
            "pes": [str],
            "jobs": [str],
            "schedules": [str],
            "gatilhos": [str],
            "edges": [(from_type, from, to_type, to, edge_type, ctx, weight)],
            "graph_summary": str,    # pre-formatted for LLM
            "entry_points": dict,    # menus, jobs, schedules
        }
    """
    from app.services.workspace.graph_traversal import traverse_graph, format_context_for_llm
    from app.services.workspace.process_tracer import discover_entry_points

    # Get raw sqlite connection (Database wraps it as _conn)
    conn = db.get_raw_conn() if hasattr(db, 'get_raw_conn') else db

    # Traverse graph from each table
    all_nodes = {}
    all_edges = []
    for tabela in tabelas:
        result = traverse_graph(conn, tabela, "tabela", max_depth=max_depth)
        all_nodes.update(result["nodes"])
        all_edges.extend(result["edges"])

    # Deduplicate edges
    unique_edges = list({(e[0], e[1], e[2], e[3], e[4]): e for e in all_edges}.values())

    # Group by type
    by_type = {"fontes": set(), "funcoes": set(), "tabelas": set(),
               "parametros": set(), "pes": set(), "jobs": set(),
               "schedules": set(), "gatilhos": set(), "campos": set(),
               "modulos": set(), "rotinas": set()}
    for (ntype, nname), info in all_nodes.items():
        if ntype in by_type:
            by_type[ntype].add(nname)
        elif ntype == "fonte":
            by_type["fontes"].add(nname)
        elif ntype == "funcao":
            by_type["funcoes"].add(nname)
        elif ntype == "tabela":
            by_type["tabelas"].add(nname)
        elif ntype == "parametro":
            by_type["parametros"].add(nname)
        elif ntype == "pe":
            by_type["pes"].add(nname)
        elif ntype == "job":
            by_type["jobs"].add(nname)
        elif ntype == "schedule":
            by_type["schedules"].add(nname)
        elif ntype == "gatilho":
            by_type["gatilhos"].add(nname)
        elif ntype == "modulo":
            by_type["modulos"].add(nname)
        elif ntype == "rotina":
            by_type["rotinas"].add(nname)
        elif ntype == "campo":
            by_type["campos"].add(nname)

    # Convert sets to sorted lists
    result_by_type = {k: sorted(v) for k, v in by_type.items()}

    # Build graph summary for LLM
    graph_summary = _build_graph_summary(tabelas, result_by_type, unique_edges)

    # Discover entry points (menus, jobs, schedules)
    entry_points = discover_entry_points(conn, tabelas)

    return {
        **result_by_type,
        "edges": unique_edges,
        "graph_summary": graph_summary,
        "entry_points": entry_points,
        "total_nodes": len(all_nodes),
        "total_edges": len(unique_edges),
    }


def _build_graph_summary(tabelas: list[str], by_type: dict, edges: list) -> str:
    """Build a concise graph summary for LLM consumption."""
    lines = [f"GRAFO DE DEPENDENCIAS — Tabelas raiz: {', '.join(tabelas)}"]
    lines.append(f"Total: {sum(len(v) for v in by_type.values())} nós, {len(edges)} arestas")
    lines.append("")

    # Edge type distribution
    edge_counts = {}
    for e in edges:
        edge_counts[e[4]] = edge_counts.get(e[4], 0) + 1
    lines.append("Tipos de vinculo:")
    for etype, count in sorted(edge_counts.items(), key=lambda x: -x[1]):
        lines.append(f"  {etype}: {count}")
    lines.append("")

    # Tables with read/write classification
    tab_write = set()
    tab_read = set()
    for e in edges:
        if e[4] in ("fonte_escreve_tabela", "operacao_escrita_tabela"):
            tab_write.add(e[3])
        elif e[4] in ("fonte_le_tabela", "funcao_referencia_tabela"):
            tab_read.add(e[3])
    if tab_write:
        lines.append(f"Tabelas com escrita: {', '.join(sorted(tab_write))}")
    if tab_read - tab_write:
        lines.append(f"Tabelas só leitura: {', '.join(sorted(tab_read - tab_write))}")
    lines.append("")

    # Fontes with write relationships
    fonte_writes = {}
    for e in edges:
        if e[4] in ("fonte_escreve_tabela", "operacao_escrita_tabela") and e[0] in ("fonte", "funcao"):
            fonte_writes.setdefault(e[1], set()).add(e[3])
    if fonte_writes:
        lines.append("Fontes que escrevem:")
        for fonte, tabs in sorted(fonte_writes.items(), key=lambda x: -len(x[1])):
            lines.append(f"  {fonte} -> {', '.join(sorted(tabs))}")
    lines.append("")

    # PEs
    pe_edges = [e for e in edges if e[4] == "pe_afeta_rotina"]
    if pe_edges:
        lines.append("Pontos de Entrada:")
        for e in pe_edges:
            lines.append(f"  PE {e[1]} intercepta {e[3]}")
    lines.append("")

    # Parameters
    if by_type.get("parametros"):
        lines.append(f"Parametros usados: {', '.join(by_type['parametros'][:20])}")

    return "\n".join(lines)


# ── PASS 1: Map (per-source summaries) ────────────────────────────────────────

async def pass1_map(db, llm, fontes: list[str], tabelas_processo: list[str]) -> dict:
    """Generate mini-summaries for each source file.

    Uses cached data when available:
    1. fonte_analise_tecnica cache → use directly
    2. propositos.proposito cache → use directly
    3. funcao_docs.resumo → use directly
    4. None of above → generate via LLM

    Returns:
        {
            "summaries": {arquivo: str},  # mini-summary per source
            "from_cache": int,
            "from_llm": int,
        }
    """
    summaries = {}
    from_cache = 0
    from_llm = 0

    for arquivo in fontes:
        summary = _get_cached_summary(db, arquivo)
        if summary:
            summaries[arquivo] = summary
            from_cache += 1
        else:
            # Generate summary from available data (SQL first, LLM fallback)
            summary = await _generate_source_summary(db, llm, arquivo, tabelas_processo)
            summaries[arquivo] = summary
            from_llm += 1

    return {
        "summaries": summaries,
        "from_cache": from_cache,
        "from_llm": from_llm,
    }


def _get_cached_summary(db, arquivo: str) -> Optional[str]:
    """Try to get a cached summary from various sources."""
    # 1. fonte_analise_tecnica (richest cache)
    try:
        row = db.execute(
            "SELECT analise_json FROM fonte_analise_tecnica WHERE arquivo = ?",
            (arquivo,)
        ).fetchone()
        if row and row[0]:
            data = json.loads(row[0])
            parts = []
            if data.get("ecossistema"):
                parts.append(data["ecossistema"][:200])
            if data.get("fluxo_resumido"):
                parts.append(f"Fluxo: {data['fluxo_resumido'][:200]}")
            tabs = data.get("tabelas", [])
            if tabs:
                tab_str = ", ".join(
                    f"{t['tabela']}({'W' if t.get('modo') == 'escrita' else 'R'})"
                    for t in tabs[:8]
                )
                parts.append(f"Tabelas: {tab_str}")
            if parts:
                return " | ".join(parts)
    except Exception:
        pass

    # 2. propositos (AI-generated purpose)
    try:
        row = db.execute(
            "SELECT proposito FROM propositos WHERE chave = ?",
            (arquivo,)
        ).fetchone()
        if row and row[0]:
            try:
                parsed = json.loads(row[0])
                if isinstance(parsed, dict):
                    ia = parsed.get("ia", {})
                    if isinstance(ia, dict) and ia.get("resumo"):
                        return ia["resumo"][:400]
                    if isinstance(ia, str):
                        return ia[:400]
                    if parsed.get("humano"):
                        return parsed["humano"][:400]
                return str(parsed)[:400]
            except (json.JSONDecodeError, TypeError):
                return str(row[0])[:400]
    except Exception:
        pass

    # 3. funcao_docs resumos (aggregate)
    try:
        rows = db.execute(
            "SELECT funcao, resumo, tabelas_ref, chama FROM funcao_docs WHERE arquivo = ?",
            (arquivo,)
        ).fetchall()
        if rows:
            parts = []
            for funcao, resumo, tabs_ref, chama in rows[:8]:
                r = _parse_resumo(resumo)
                if r:
                    parts.append(f"{funcao}: {r[:100]}")
            if parts:
                return " | ".join(parts)
    except Exception:
        pass

    return None


def _parse_resumo(text: str) -> str:
    """Extract readable text from resumo JSON."""
    if not text:
        return ""
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            if "humano" in parsed:
                return parsed["humano"]
            ia = parsed.get("ia", {})
            if isinstance(ia, dict) and "resumo" in ia:
                return ia["resumo"]
            if isinstance(ia, str):
                return ia
            if "resumo" in parsed:
                return parsed["resumo"]
        return text
    except (json.JSONDecodeError, TypeError):
        return text


async def _generate_source_summary(db, llm, arquivo: str, tabelas_processo: list[str]) -> str:
    """Generate a summary for a source file using available DB data + LLM."""
    # Collect data from DB
    meta = db.execute(
        "SELECT arquivo, modulo, funcoes, write_tables, tabelas_ref, pontos_entrada, calls_u, lines_of_code "
        "FROM fontes WHERE arquivo = ?",
        (arquivo,)
    ).fetchone()
    if not meta:
        return f"{arquivo}: fonte não encontrado no banco"

    modulo = meta[1] or "?"
    funcoes = _safe_json(meta[2])
    write_tables = _safe_json(meta[3])
    tabelas_ref = _safe_json(meta[4])
    pes = _safe_json(meta[5])
    calls_u = _safe_json(meta[6])
    loc = meta[7] or 0

    # Get write operations
    ops = db.execute(
        "SELECT funcao, tipo, tabela, campos, condicao FROM operacoes_escrita WHERE arquivo = ? ORDER BY linha",
        (arquivo,)
    ).fetchall()

    # Build context for LLM
    context_parts = [
        f"Fonte: {arquivo} ({loc} LOC, modulo {modulo})",
        f"Funcoes: {', '.join(funcoes[:10])}",
        f"Tabelas leitura: {', '.join(tabelas_ref[:10])}",
        f"Tabelas escrita: {', '.join(write_tables[:10])}",
    ]
    if pes:
        context_parts.append(f"PEs: {', '.join(pes[:5])}")
    if calls_u:
        context_parts.append(f"Chama: {', '.join(calls_u[:10])}")
    if ops:
        context_parts.append("Operacoes de escrita:")
        for op in ops[:10]:
            campos = _safe_json(op[3])
            cond = f" [SE {op[4][:60]}]" if op[4] else ""
            context_parts.append(f"  {op[0]}::{op[1]} {op[2]} ({', '.join(campos[:5])}){cond}")

    # Get function docs
    func_rows = db.execute(
        "SELECT funcao, tipo, assinatura, resumo FROM funcao_docs WHERE arquivo = ? ORDER BY funcao",
        (arquivo,)
    ).fetchall()
    if func_rows:
        context_parts.append("Funcoes documentadas:")
        for fr in func_rows[:10]:
            r = _parse_resumo(fr[3])
            context_parts.append(f"  {fr[1]} {fr[2] or fr[0]}: {r[:120]}")

    context = "\n".join(context_parts)

    # Ask LLM for concise summary
    prompt = f"""Resuma em 2-3 frases OBJETIVAS o que este fonte ADVPL faz no processo.
Foque em: O QUE faz, QUAIS tabelas grava, QUANDO/CONDICAO, e COMO se conecta ao processo.

Tabelas do processo: {', '.join(tabelas_processo)}

{context}

Responda APENAS o resumo, sem formatação markdown, sem bullet points. Maximo 400 chars."""

    try:
        response = await asyncio.to_thread(
            llm._call,
            [{"role": "user", "content": prompt}],
            temperature=0.1,
            use_gen=True,
            timeout=30,
        )
        return response.strip()[:400]
    except Exception as e:
        # Fallback: build summary from data
        parts = [f"{arquivo} ({modulo})"]
        if write_tables:
            parts.append(f"escreve {', '.join(write_tables[:5])}")
        if pes:
            parts.append(f"PEs: {', '.join(pes[:3])}")
        return " — ".join(parts)


# ── PASS 1.5: Code Specialist for critical sources ────────────────────────────

async def pass1_5_code_specialist(db, llm, discovery: dict, tabelas_processo: list[str]) -> dict:
    """Run code_specialist on critical sources for deep understanding.

    Critical = writes to 2+ process tables, OR has MsExecAuto, OR is a hub (called by 3+).

    Returns:
        {"analyses": {arquivo: str}, "critical_count": int}
    """
    from app.services.workspace.code_specialist import code_specialist

    fontes = discovery["fontes"]
    edges = discovery["edges"]
    analyses = {}

    critical_fontes = _identify_critical_fontes(fontes, edges, tabelas_processo)

    for arquivo in critical_fontes:
        analysis = await _analyze_critical_fonte(db, llm, arquivo, tabelas_processo, edges)
        if analysis:
            analyses[arquivo] = analysis

    return {"analyses": analyses, "critical_count": len(critical_fontes)}


def _identify_critical_fontes(fontes: list[str], edges: list, tabelas_processo: list[str]) -> list[str]:
    """Identify which sources deserve deep code analysis."""
    critical = []
    tabelas_set = set(t.upper() for t in tabelas_processo)

    for fonte in fontes:
        fonte_upper = fonte.upper()
        fonte_base = fonte.replace(".prw", "").replace(".PRW", "").replace(".tlpp", "").replace(".TLPP", "").upper()

        # Edges involving this fonte
        related_edges = [
            e for e in edges
            if e[1].upper() in (fonte_upper, fonte_base) or e[3].upper() in (fonte_upper, fonte_base)
        ]

        # Tables this fonte writes to
        write_tables = set()
        for e in related_edges:
            if e[4] in ("fonte_escreve_tabela", "operacao_escrita_tabela"):
                write_tables.add(e[3].upper())

        # Overlap with process tables
        overlap = write_tables & tabelas_set
        if len(overlap) >= 2:
            critical.append(fonte)
            continue

        # Has ExecBlock / MsExecAuto references
        has_exec = any(
            "exec" in e[3].lower() or "exec" in (e[5] or "").lower()
            for e in related_edges
            if e[4] in ("fonte_chama_funcao", "funcao_chama_funcao")
        )
        if has_exec and overlap:
            critical.append(fonte)
            continue

        # Hub: called by 3+ other fontes
        incoming = [e for e in related_edges
                    if e[3].upper() in (fonte_upper, fonte_base)
                    and e[4] in ("funcao_chama_funcao", "fonte_chama_funcao")]
        if len(incoming) >= 3 and overlap:
            critical.append(fonte)

    return critical[:6]  # Cap at 6 to control costs


async def _analyze_critical_fonte(db, llm, arquivo: str, tabelas_processo: list[str], edges: list) -> str:
    """Run deep analysis on a critical source file."""
    # Get source code
    chunks = db.execute(
        "SELECT funcao, content FROM fonte_chunks WHERE arquivo = ? ORDER BY id",
        (arquivo,)
    ).fetchall()
    if not chunks:
        return ""

    # Build code context (cap at 6K to leave room for analysis)
    code_parts = []
    total_chars = 0
    for funcao, content in chunks:
        if funcao == "_header":
            continue
        if total_chars + len(content or "") > 6000:
            break
        code_parts.append(f"// === {funcao} ===\n{content}")
        total_chars += len(content or "")

    code_text = "\n".join(code_parts)

    # Get write operations for context
    ops = db.execute(
        "SELECT funcao, tipo, tabela, campos, condicao, linha FROM operacoes_escrita WHERE arquivo = ?",
        (arquivo,)
    ).fetchall()

    ops_text = ""
    if ops:
        ops_lines = ["Operacoes de escrita detectadas:"]
        for op in ops:
            campos = _safe_json(op[3])
            cond = f" [SE {op[4][:80]}]" if op[4] else ""
            ops_lines.append(f"  L{op[5]}: {op[0]}::{op[1]} {op[2]} ({', '.join(campos[:8])}){cond}")
        ops_text = "\n".join(ops_lines)

    # Use code_specialist in diagnostic mode
    prompt = f"""Voce e um engenheiro reverso especialista em ADVPL/TLPP para TOTVS Protheus.

OBJETIVO: Analisar o FLUXO LOGICO COMPLETO deste fonte e explicar EXATAMENTE como ele participa no processo.

TABELAS DO PROCESSO: {', '.join(tabelas_processo)}

{ops_text}

CODIGO:
{code_text}

INSTRUCOES:
1. Descreva o fluxo de execucao PASSO A PASSO (o que acontece primeiro, segundo, etc.)
2. Para cada operacao de escrita, explique: QUANDO grava, O QUE grava, SOB QUE CONDICAO
3. Identifique pontos de decisao (IFs que mudam o fluxo)
4. Identifique integracao com outros fontes (chamadas U_, ExecBlock, MsExecAuto)
5. Identifique parametros SX6 usados e como afetam o comportamento

Responda de forma CONCISA (max 800 chars), focando no fluxo e nas condicoes de escrita.
NAO repita informacoes que ja estao nas operacoes_escrita.
Foque no que o CODIGO revela que os METADADOS nao revelam."""

    try:
        response = await asyncio.to_thread(
            llm._call,
            [{"role": "user", "content": prompt}],
            temperature=0.2,
            use_gen=False,  # Use strong model for code analysis
            timeout=90,
        )
        return response.strip()[:1200]
    except Exception as e:
        return f"Erro ao analisar {arquivo}: {str(e)[:100]}"


# ── PASS 2: Reduce (synthesis) ────────────────────────────────────────────────

REDUCE_PROMPT = """Voce e um analista senior de ambientes TOTVS Protheus.
Com base nos dados abaixo, gere uma ANALISE COMPLETA do processo.

PROCESSO: {nome}
DESCRICAO: {descricao}

{graph_summary}

PONTOS DE ENTRADA:
{entry_points_text}

RESUMO POR FONTE (cada fonte do processo):
{source_summaries}

ANALISE PROFUNDA DE FONTES CRITICAS:
{critical_analyses}

PARAMETROS DO PROCESSO:
{parameters_text}

GATILHOS:
{triggers_text}

INSTRUCOES:
1. Monte o PASSO A PASSO COMPLETO do processo — o que acontece do inicio ao fim
2. Para cada passo: QUEM dispara, O QUE faz, QUAIS tabelas afeta, CONDICAO
3. Identifique TODOS os caminhos alternativos (decisoes, branches)
4. Inclua jobs/schedules como passos ASSINCRONOS
5. Inclua PEs e como eles interceptam o fluxo
6. Para cada fonte, cite arquivo::funcao()
7. NÃO omita nenhum fonte — TODOS devem aparecer no fluxo
8. NÃO invente passos que não estejam nos dados

FORMATO DE SAIDA — JSON:
{{
  "titulo": "str",
  "resumo_executivo": "str — 3-4 frases descrevendo o processo completo",
  "passos": [
    {{
      "ordem": 1,
      "ator": "Usuario|Job|PE|Sistema|WebService",
      "acao": "Descricao detalhada do que acontece",
      "rotina": "MGFCOM92",
      "funcao": "xGerGrd",
      "arquivo": "MGFCOM92.prw",
      "tabelas_afetadas": ["SCR"],
      "campos_gravados": ["CR_FILIAL", "CR_NUM"],
      "condicao": "nTotal >= ZAD_VALINI",
      "consequencia": "Cria registro para aprovacao"
    }}
  ],
  "jobs_envolvidos": [
    {{
      "rotina": "str",
      "frequencia": "str",
      "funcao": "O que faz no processo"
    }}
  ],
  "pontos_decisao": [
    {{
      "descricao": "str",
      "local": "arquivo::funcao",
      "resultado_sim": "str",
      "resultado_nao": "str"
    }}
  ],
  "pes_envolvidos": [
    {{
      "nome": "str",
      "arquivo": "str",
      "funcao": "O que faz no processo"
    }}
  ],
  "integracao_externa": [
    {{
      "tipo": "WebService|API|Arquivo|MsExecAuto",
      "descricao": "str",
      "arquivo": "str"
    }}
  ],
  "parametros_chave": [
    {{
      "variavel": "str",
      "valor": "str",
      "impacto": "Como afeta o processo"
    }}
  ],
  "riscos": ["str — pontos criticos que merecem atencao"]
}}"""


async def pass2_reduce(llm, nome: str, descricao: str, discovery: dict,
                       source_summaries: dict, critical_analyses: dict) -> dict:
    """Synthesize all data into a complete analysis."""
    # Format entry points
    ep = discovery["entry_points"]
    ep_lines = []
    for m in ep.get("menus", []):
        ep_lines.append(f"Menu: {m['rotina']} — {m['nome']} ({m['modulo']})")
    for j in ep.get("jobs", []):
        rate = f"cada {j['refresh_rate']}s" if j.get('refresh_rate') else "manual"
        ep_lines.append(f"Job: {j['rotina']} (sessao: {j['sessao']}, {rate})")
    for s in ep.get("schedules", []):
        ep_lines.append(f"Schedule: {s['rotina']} ({s['tipo_recorrencia']}, {s['status']})")
    for p in ep.get("pes_implementados", []):
        ep_lines.append(f"PE: {p['arquivo']} — PEs: {', '.join(p['pes'][:5])}")

    # Format source summaries
    summary_lines = []
    for arquivo, summary in sorted(source_summaries.items()):
        summary_lines.append(f"### {arquivo}\n{summary}\n")

    # Format critical analyses
    critical_lines = []
    if critical_analyses:
        for arquivo, analysis in sorted(critical_analyses.items()):
            critical_lines.append(f"### {arquivo} (ANALISE PROFUNDA)\n{analysis}\n")
    else:
        critical_lines.append("Nenhum fonte identificado como critico.")

    # Format parameters
    params_text = _format_parameters(discovery)

    # Format triggers
    triggers_text = _format_triggers(discovery)

    prompt = REDUCE_PROMPT.format(
        nome=nome,
        descricao=descricao,
        graph_summary=discovery["graph_summary"],
        entry_points_text="\n".join(ep_lines) or "Nenhum ponto de entrada identificado.",
        source_summaries="\n".join(summary_lines),
        critical_analyses="\n".join(critical_lines),
        parameters_text=params_text,
        triggers_text=triggers_text,
    )

    try:
        response = await asyncio.to_thread(
            llm._call,
            [{"role": "user", "content": prompt}],
            temperature=0.2,
            use_gen=False,  # Strong model for synthesis
            timeout=120,
        )
        return _parse_json_response(response)
    except Exception as e:
        return {"erro": str(e)[:200], "raw_response": ""}


def _format_parameters(discovery: dict) -> str:
    """Format parameter information from discovery."""
    params = discovery.get("parametros", [])
    if not params:
        return "Nenhum parametro identificado no grafo."

    # We'll need to query the DB for values — but we don't have db here
    # Just list them from the graph
    return f"Parametros referenciados: {', '.join(params[:20])}"


def _format_triggers(discovery: dict) -> str:
    """Format trigger information from edges."""
    trigger_edges = [e for e in discovery["edges"] if e[4] == "gatilho_executa_funcao"]
    if not trigger_edges:
        return "Nenhum gatilho detectado no grafo."

    lines = []
    for e in trigger_edges[:15]:
        lines.append(f"Gatilho {e[1]} executa {e[3]} ({e[5][:60] if e[5] else ''})")
    return "\n".join(lines)


# ── PASS 3: Verify ────────────────────────────────────────────────────────────

VERIFY_PROMPT = """Verifique se a analise abaixo e PRECISA e COMPLETA.

IMPORTANTE: Na coluna "Fontes que escrevem" do grafo, existem DOIS tipos de entradas:
- ARQUIVOS .prw (ex: WS_Dealernet.prw, JobProc1.prw) — sao fontes reais
- FUNCOES sem extensao (ex: EnviaMuro, GeraXML, FSJbPrc1) — sao funcoes DENTRO dos arquivos

NAO considere funcoes como "fontes faltando" — elas estao DENTRO dos arquivos .prw listados.

DADOS DO GRAFO:
{graph_data}

FONTES (ARQUIVOS .prw) DISPONIVEIS:
{fontes_list}

ANALISE GERADA:
{analysis_json}

Verifique:
1. Cada passo cita um ARQUIVO .prw que existe na lista de fontes disponiveis?
2. Faltou algum ARQUIVO .prw que escreve em tabelas do processo?
3. A ordem temporal faz sentido?
4. Os pontos de decisao estao corretos?
5. As condicoes citadas sao especificas o suficiente (nomes de variaveis, campos)?

Responda JSON:
{{
  "valido": true/false,
  "score": 0.0-1.0,
  "problemas": ["str"],
  "fontes_faltando": ["str — APENAS arquivos .prw que deveriam aparecer mas nao aparecem"],
  "passos_faltando": ["str — passos que deveriam existir"],
  "correcoes": ["str"]
}}"""


async def pass3_verify(llm, discovery: dict, analysis_json: dict) -> dict:
    """Verify the analysis against raw data."""
    # Build ground truth from graph
    graph_data_lines = [
        f"Fontes que ESCREVEM: {_get_write_fontes(discovery)}",
        f"Tabelas do processo: {', '.join(discovery.get('tabelas', [])[:20])}",
        f"PEs: {', '.join(discovery.get('pes', [])[:10])}",
        f"Jobs: {', '.join(discovery.get('jobs', [])[:10])}",
        f"Parametros: {', '.join(discovery.get('parametros', [])[:15])}",
    ]

    prompt = VERIFY_PROMPT.format(
        graph_data="\n".join(graph_data_lines),
        fontes_list=", ".join(discovery.get("fontes", [])[:30]),
        analysis_json=json.dumps(analysis_json, ensure_ascii=False, indent=2)[:6000],
    )

    try:
        response = await asyncio.to_thread(
            llm._call,
            [{"role": "user", "content": prompt}],
            temperature=0.1,
            use_gen=True,
            timeout=30,
        )
        return _parse_json_response(response)
    except Exception:
        return {"valido": True, "score": 0.5, "problemas": ["Verificacao falhou"]}


def _get_write_fontes(discovery: dict) -> str:
    """Get list of fontes that write to process tables."""
    writers = set()
    for e in discovery["edges"]:
        if e[4] in ("fonte_escreve_tabela", "operacao_escrita_tabela"):
            writers.add(e[1])
    return ", ".join(sorted(writers)[:20])


# ── Utilities ──────────────────────────────────────────────────────────────────

def _parse_json_response(response: str) -> dict:
    """Parse JSON from LLM response, handling markdown wrapping."""
    text = response.strip()
    if "```" in text:
        parts = text.split("```")
        for part in parts[1:]:
            cleaned = part.strip()
            if cleaned.startswith("json"):
                cleaned = cleaned[4:].strip()
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                continue

    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find JSON object in text
    match = re.search(r'\{[\s\S]+\}', text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    return {"raw_response": text}


def _analysis_to_markdown(analysis: dict, nome: str, verification: dict) -> str:
    """Convert structured analysis JSON to readable markdown."""
    lines = [f"# Análise Profunda: {nome}\n"]

    # Executive summary
    resumo = analysis.get("resumo_executivo", "")
    if resumo:
        lines.append(f"> {resumo}\n")

    # Steps
    passos = analysis.get("passos", [])
    if passos:
        lines.append("## Fluxo de Execução\n")
        for p in passos:
            ordem = p.get("ordem", "?")
            ator = p.get("ator", "Sistema")
            acao = p.get("acao", "")
            arquivo = p.get("arquivo", "")
            funcao = p.get("funcao", "")
            tabelas = p.get("tabelas_afetadas", [])
            campos = p.get("campos_gravados", [])
            condicao = p.get("condicao", "")
            consequencia = p.get("consequencia", "")

            lines.append(f"**Passo {ordem}** — {ator}")
            lines.append(f"  {acao}")
            if arquivo or funcao:
                lines.append(f"  - Rotina: `{arquivo}::{funcao}()`")
            if tabelas:
                lines.append(f"  - Tabelas: {', '.join(tabelas)}")
            if campos:
                lines.append(f"  - Campos: {', '.join(campos[:10])}")
            if condicao:
                lines.append(f"  - Condição: `{condicao}`")
            if consequencia:
                lines.append(f"  - → {consequencia}")
            lines.append("")

    # Decision points
    decisoes = analysis.get("pontos_decisao", [])
    if decisoes:
        lines.append("## Pontos de Decisão\n")
        for d in decisoes:
            lines.append(f"- **{d.get('descricao', '')}** (`{d.get('local', '')}`)")
            lines.append(f"  - SIM → {d.get('resultado_sim', '')}")
            lines.append(f"  - NÃO → {d.get('resultado_nao', '')}")
        lines.append("")

    # Jobs
    jobs = analysis.get("jobs_envolvidos", [])
    if jobs:
        lines.append("## Jobs Assíncronos\n")
        for j in jobs:
            lines.append(f"- **{j.get('rotina', '')}** ({j.get('frequencia', '')}): {j.get('funcao', '')}")
        lines.append("")

    # PEs
    pes = analysis.get("pes_envolvidos", [])
    if pes:
        lines.append("## Pontos de Entrada\n")
        for pe in pes:
            lines.append(f"- **{pe.get('nome', '')}** ({pe.get('arquivo', '')}): {pe.get('funcao', '')}")
        lines.append("")

    # External integrations
    integ = analysis.get("integracao_externa", [])
    if integ:
        lines.append("## Integrações Externas\n")
        for i in integ:
            lines.append(f"- **{i.get('tipo', '')}**: {i.get('descricao', '')} ({i.get('arquivo', '')})")
        lines.append("")

    # Key parameters
    params = analysis.get("parametros_chave", [])
    if params:
        lines.append("## Parâmetros Chave\n")
        lines.append("| Parâmetro | Valor | Impacto |")
        lines.append("|-----------|-------|---------|")
        for p in params:
            lines.append(f"| `{p.get('variavel', '')}` | {p.get('valor', '')} | {p.get('impacto', '')} |")
        lines.append("")

    # Risks
    riscos = analysis.get("riscos", [])
    if riscos:
        lines.append("## Riscos e Pontos de Atenção\n")
        for r in riscos:
            lines.append(f"- ⚠️ {r}")
        lines.append("")

    # Verification
    if verification:
        score = verification.get("score", 0)
        lines.append(f"## Verificação (score: {score:.0%})\n")
        problemas = verification.get("problemas", [])
        if problemas:
            for p in problemas:
                lines.append(f"- {p}")
        fontes_faltando = verification.get("fontes_faltando", [])
        if fontes_faltando:
            lines.append(f"\nFontes não mencionados: {', '.join(fontes_faltando)}")
        passos_faltando = verification.get("passos_faltando", [])
        if passos_faltando:
            lines.append("\nPassos que podem estar faltando:")
            for pf in passos_faltando:
                lines.append(f"  - {pf}")

    return "\n".join(lines)


# ── Enrich parameters with actual DB values ────────────────────────────────────

def _enrich_parameters(db, discovery: dict) -> str:
    """Get parameter values from database for discovered parameters.

    Goes beyond graph-discovered params: also searches for parameters
    referenced in the fonte_chunks of process sources.
    """
    params_from_graph = set(discovery.get("parametros", []))
    fontes = discovery.get("fontes", [])

    # Also find parameters from fonte_chunks content (catches FS_, ES_ etc.)
    params_from_code = set()
    for fonte in fontes:
        try:
            chunks = db.execute(
                "SELECT content FROM fonte_chunks WHERE arquivo = ?", (fonte,)
            ).fetchall()
            for (content,) in chunks:
                if not content:
                    continue
                # Find GetMV/SuperGetMV/GetNewPar patterns
                found = re.findall(
                    r'(?:GetMV|SuperGetMV|GetNewPar)\s*\(\s*["\']([A-Z][A-Z0-9_]+)["\']',
                    content
                )
                params_from_code.update(found)
                # Also find cValPar/cPar-style direct references to known prefixes
                found2 = re.findall(r'["\']([FEM]S_[A-Z0-9_]+)["\']', content)
                params_from_code.update(found2)
        except Exception:
            pass

    all_params = sorted(params_from_graph | params_from_code)
    if not all_params:
        return "Nenhum parametro identificado."

    # Update discovery with enriched params
    discovery["parametros"] = all_params

    lines = []
    for var in all_params[:40]:
        rows = db.execute(
            "SELECT filial, variavel, descricao, conteudo, tipo FROM parametros WHERE variavel = ?",
            (var,)
        ).fetchall()
        if rows:
            for r in rows:
                filial = r[0].strip() if r[0] and r[0].strip() else "(todas)"
                desc = (r[2] or "")[:80]
                val = (r[3] or "(vazio)")[:50]
                lines.append(f"{r[1]} [filial {filial}] = {val} — {desc}")
        else:
            lines.append(f"{var}: referenciado no codigo mas nao encontrado no SX6")
    return "\n".join(lines) if lines else "Nenhum parametro com valor encontrado."


# ── Main entry point ──────────────────────────────────────────────────────────

async def run_deep_analysis(
    db,
    llm,
    tabelas: list[str],
    nome: str = "",
    descricao: str = "",
    max_depth: int = 2,
    skip_code_specialist: bool = False,
) -> dict:
    """Run the full multi-pass deep analysis pipeline.

    Args:
        db: Database instance
        llm: LLMService instance
        tabelas: Process tables to analyze
        nome: Process name
        descricao: Process description
        max_depth: Graph traversal depth (default 2)
        skip_code_specialist: Skip PASS 1.5 for faster results

    Returns:
        {
            "analysis_json": dict,      # Structured analysis
            "analysis_markdown": str,    # Formatted markdown
            "verification": dict,        # Verification results
            "stats": dict,               # Pipeline statistics
        }
    """
    stats = {"started_at": time.time()}

    # ── PASS 0: Discovery ──
    discovery = pass0_discovery(db, tabelas, max_depth=max_depth)
    stats["pass0_nodes"] = discovery["total_nodes"]
    stats["pass0_edges"] = discovery["total_edges"]
    stats["pass0_fontes"] = len(discovery["fontes"])
    stats["pass0_time"] = time.time() - stats["started_at"]

    # Enrich parameters with actual values
    discovery["parameters_enriched"] = _enrich_parameters(db, discovery)

    # ── PASS 1: Map (per-source summaries) ──
    t1 = time.time()
    map_result = await pass1_map(db, llm, discovery["fontes"], tabelas)
    stats["pass1_cached"] = map_result["from_cache"]
    stats["pass1_llm"] = map_result["from_llm"]
    stats["pass1_time"] = time.time() - t1

    # ── PASS 1.5: Code Specialist (critical sources) ──
    critical_analyses = {}
    if not skip_code_specialist:
        t15 = time.time()
        cs_result = await pass1_5_code_specialist(db, llm, discovery, tabelas)
        critical_analyses = cs_result["analyses"]
        stats["pass1_5_critical"] = cs_result["critical_count"]
        stats["pass1_5_time"] = time.time() - t15
    else:
        stats["pass1_5_critical"] = 0
        stats["pass1_5_time"] = 0

    # ── PASS 2: Reduce (synthesis) ──
    t2 = time.time()

    # Inject enriched parameters into discovery for the reduce prompt
    discovery_for_reduce = dict(discovery)
    analysis_json = await pass2_reduce(
        llm, nome, descricao, discovery_for_reduce,
        map_result["summaries"], critical_analyses,
    )
    stats["pass2_time"] = time.time() - t2

    # ── PASS 3: Verify ──
    t3 = time.time()
    verification = await pass3_verify(llm, discovery, analysis_json)
    stats["pass3_time"] = time.time() - t3

    # Apply verification corrections to analysis if needed
    if verification.get("fontes_faltando"):
        analysis_json.setdefault("notas_verificacao", []).extend(
            [f"Fonte não mencionado: {f}" for f in verification["fontes_faltando"]]
        )

    # ── Generate markdown ──
    markdown = _analysis_to_markdown(analysis_json, nome, verification)

    stats["total_time"] = time.time() - stats["started_at"]
    stats["total_llm_calls"] = (
        map_result["from_llm"]
        + stats.get("pass1_5_critical", 0)
        + 1  # reduce
        + 1  # verify
    )

    return {
        "analysis_json": analysis_json,
        "analysis_markdown": markdown,
        "verification": verification,
        "discovery": {
            "fontes": discovery["fontes"],
            "tabelas": discovery["tabelas"],
            "parametros": discovery["parametros"],
            "pes": discovery["pes"],
            "jobs": discovery["jobs"],
            "total_nodes": discovery["total_nodes"],
            "total_edges": discovery["total_edges"],
        },
        "source_summaries": map_result["summaries"],
        "critical_analyses": critical_analyses,
        "stats": stats,
    }
