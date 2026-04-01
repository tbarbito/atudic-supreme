"""Process Tracer — engenharia reversa do fluxo de execução real de um processo.

Em vez de listar tabelas e fontes, este módulo RASTREIA o passo a passo técnico:
1. Identifica ponto de entrada (menu/rotina/job)
2. Segue as funções chamadas, lê o código, identifica operações
3. Para cada RecLock/ExecBlock, mapeia tabela + campos + condição
4. Identifica jobs/schedules que participam do fluxo
5. Monta narrativa técnica sequencial

Usa Plan-and-Execute + Verification para qualidade.
"""
import json
import asyncio
import re
import sqlite3
from pathlib import Path
from typing import Optional


def _safe_json(val):
    if not val:
        return []
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return []


def _get_db():
    """Get client database connection."""
    from app.services.workspace.config import load_config, get_client_workspace
    from app.services.workspace.workspace_db import Database
    config = load_config(Path("config.json"))
    if not config or not config.active_client:
        return None
    client_dir = get_client_workspace(Path("workspace"), config.active_client)
    db_path = client_dir / "db" / "extrairpo.db"
    if not db_path.exists():
        return None
    db = Database(db_path)
    db.initialize()
    return db


# ── Step 1: Discover entry points ────────────────────────────────────────────

def discover_entry_points(db, tabelas: list[str]) -> dict:
    """Find all entry points for a process: menus, jobs, schedules, PEs.

    Returns:
        {
            "menus": [{"rotina": str, "nome": str, "modulo": str}],
            "jobs": [{"rotina": str, "sessao": str, "refresh_rate": str}],
            "schedules": [{"rotina": str, "codigo": str, "tipo_recorrencia": str}],
            "fontes_escrita": [{"arquivo": str, "funcoes": [...], "write_tables": [...]}],
            "pes_implementados": [{"arquivo": str, "pes": [...]}],
        }
    """
    result = {"menus": [], "jobs": [], "schedules": [], "fontes_escrita": [], "pes_implementados": []}

    # Collect all fontes that write to process tables
    fontes_processo = set()
    for tab in tabelas:
        rows = db.execute(
            "SELECT arquivo FROM fontes WHERE write_tables LIKE ?", (f'%"{tab}"%',)
        ).fetchall()
        for r in rows:
            fontes_processo.add(r[0])

    # Find menus for these fontes
    for fonte in sorted(fontes_processo):
        rot_name = fonte.replace('.prw', '').replace('.PRW', '').replace('.tlpp', '').replace('.TLPP', '').upper()
        menus = db.execute(
            "SELECT rotina, nome, modulo FROM menus WHERE UPPER(rotina) = ? LIMIT 3",
            (rot_name,)
        ).fetchall()
        for m in menus:
            if not any(x["rotina"] == m[0] for x in result["menus"]):
                result["menus"].append({"rotina": m[0], "nome": m[1], "modulo": m[2]})

    # Find jobs
    for fonte in sorted(fontes_processo):
        rot_name = fonte.replace('.prw', '').replace('.PRW', '').upper()
        jobs = db.execute(
            "SELECT rotina, sessao, refresh_rate FROM jobs WHERE UPPER(rotina) = ?",
            (rot_name,)
        ).fetchall()
        for j in jobs:
            result["jobs"].append({"rotina": j[0], "sessao": j[1], "refresh_rate": j[2]})

    # Find schedules
    for fonte in sorted(fontes_processo):
        rot_name = fonte.replace('.prw', '').replace('.PRW', '').upper()
        scheds = db.execute(
            "SELECT rotina, codigo, tipo_recorrencia, status FROM schedules WHERE UPPER(rotina) = ? AND status != 'inativo'",
            (rot_name,)
        ).fetchall()
        for s in scheds:
            result["schedules"].append({"rotina": s[0], "codigo": s[1], "tipo_recorrencia": s[2], "status": s[3]})

    # Fontes with their functions and write tables
    for fonte in sorted(fontes_processo):
        row = db.execute(
            "SELECT arquivo, funcoes, write_tables, pontos_entrada, calls_u, tabelas_ref FROM fontes WHERE arquivo = ?",
            (fonte,)
        ).fetchone()
        if row:
            funcoes = _safe_json(row[1])
            write_tables = _safe_json(row[2])
            pes = _safe_json(row[3])
            calls_u = _safe_json(row[4])
            tabs_ref = _safe_json(row[5])
            result["fontes_escrita"].append({
                "arquivo": row[0],
                "funcoes": funcoes[:15],
                "write_tables": write_tables,
                "tabelas_ref": tabs_ref[:10],
                "calls_u": calls_u[:10],
            })
            if pes:
                result["pes_implementados"].append({"arquivo": row[0], "pes": pes})

    return result


# ── Step 2: Trace function execution flow ─────────────────────────────────────

def trace_function_flow(db, arquivo: str) -> list[dict]:
    """Trace the execution flow within a source file.

    For each function, extracts:
    - What it writes (RecLock operations)
    - What it calls (U_ functions)
    - What conditions control writes
    - What PEs/ExecBlocks are called
    - Parameters used

    Returns list of function trace dicts.
    """
    traces = []

    # Get function details from funcao_docs
    funcs = db.execute(
        "SELECT funcao, tipo, assinatura, tabelas_ref, campos_ref, chama, chamada_por, params "
        "FROM funcao_docs WHERE arquivo = ? ORDER BY funcao",
        (arquivo,)
    ).fetchall()

    # Get write operations per function
    ops = db.execute(
        "SELECT funcao, tipo, tabela, campos, origens, condicao, linha "
        "FROM operacoes_escrita WHERE arquivo = ? ORDER BY linha",
        (arquivo,)
    ).fetchall()
    ops_by_func = {}
    for op in ops:
        ops_by_func.setdefault(op[0], []).append({
            "tipo": op[1], "tabela": op[2],
            "campos": _safe_json(op[3])[:8],
            "origens": json.loads(op[4]) if op[4] else {},
            "condicao": op[5][:100] if op[5] else "",
            "linha": op[6],
        })

    for func in funcs:
        funcao, tipo, assinatura, tabs_ref, campos_ref, chama, chamada_por, params = func
        func_ops = ops_by_func.get(funcao, [])

        trace = {
            "funcao": funcao,
            "tipo": tipo,
            "assinatura": assinatura,
            "tabelas_ref": _safe_json(tabs_ref)[:8],
            "calls_u": _safe_json(chama)[:8],
            "chamada_por": _safe_json(chamada_por)[:5],
            "params": json.loads(params) if params else {},
            "operacoes_escrita": func_ops,
        }
        traces.append(trace)

    return traces


# ── Step 3: Build execution narrative ─────────────────────────────────────────

TRACER_PROMPT = """Voce e um engenheiro reverso especialista em TOTVS Protheus.
Analise os dados tecnicos abaixo e construa um PASSO A PASSO TECNICO do processo.

PROCESSO: {nome}
DESCRICAO: {descricao}
TABELAS: {tabelas}

PONTOS DE ENTRADA DO PROCESSO:
{entry_points}

FLUXO DE FUNCOES POR FONTE:
{function_traces}

INSTRUCOES CRITICAS:
1. Monte o fluxo TEMPORAL — o que acontece PRIMEIRO, SEGUNDO, etc.
2. Para cada passo, indique:
   - QUEM dispara (usuario via menu? job automatico? PE?)
   - O QUE acontece (qual funcao, qual tabela grava, quais campos)
   - CONDICAO (se houver — "somente se bEmite = .T.")
   - CONSEQUENCIA (o que esse passo habilita para o proximo)
3. Identifique LOOPS (ex: "volta para aprovador N+1 ate ultimo nivel")
4. Identifique PONTOS DE DECISAO (ex: "se valor > alcada, bloqueia")
5. Inclua jobs/schedules como passos ASSINCRÔNOS
6. NÃO invente passos que não estejam nos dados
7. Cite arquivo::funcao() para cada passo

FORMATO DE SAIDA — JSON:
{{
  "titulo": "Passo a passo tecnico do processo",
  "passos": [
    {{
      "ordem": 1,
      "ator": "Usuario|Job|PE|Sistema",
      "acao": "Descricao do que acontece",
      "rotina": "MGFCOM92",
      "funcao": "xGerGrd",
      "tabelas_afetadas": ["SCR", "SC7"],
      "campos_gravados": ["CR_FILIAL", "CR_NUM", "C7_CONAPRO"],
      "condicao": "nTotal >= ZAD_VALINI",
      "consequencia": "Cria registro de alcada para aprovacao"
    }}
  ],
  "jobs_envolvidos": [
    {{
      "rotina": "MGFFATB4",
      "frequencia": "5min",
      "funcao": "Atualiza status de bloqueio"
    }}
  ],
  "pontos_decisao": [
    {{
      "descricao": "Valor do pedido vs alcada da grade",
      "local": "MGFCOM92::xEncAlc",
      "resultado_sim": "Gera bloqueio em SZV",
      "resultado_nao": "Pedido liberado diretamente"
    }}
  ],
  "pes_envolvidos": [
    {{
      "nome": "xjMF07VldUs",
      "arquivo": "MGFFAT07.prw",
      "funcao": "Valida usuario aprovador"
    }}
  ]
}}"""


VERIFY_TRACE_PROMPT = """Verifique se o passo a passo abaixo e PRECISO e COMPLETO.

DADOS TECNICOS ORIGINAIS:
{raw_data}

PASSO A PASSO GERADO:
{trace_json}

Verifique:
1. Cada passo cita um arquivo::funcao() que EXISTE nos dados?
2. As tabelas e campos citados EXISTEM nos dados de operacoes_escrita?
3. Faltou algum passo importante (funcao que grava mas nao foi mencionada)?
4. A ordem temporal faz sentido?
5. Os pontos de decisao estao corretos?

Responda JSON:
{{
  "valido": true/false,
  "problemas": ["problema 1", "problema 2"],
  "passos_faltando": ["passo que deveria existir"],
  "correcoes": ["correcao sugerida"]
}}"""


async def trace_process(
    db,
    llm,
    processo: dict,
) -> dict:
    """Full process tracing pipeline: discover → trace → narrate → verify.

    Args:
        db: Database connection
        llm: LLMService instance
        processo: dict with nome, descricao, tabelas

    Returns:
        dict with passo_a_passo (markdown), trace_json (structured), confidence
    """
    nome = processo.get("nome", "")
    descricao = processo.get("descricao", "")
    tabelas = processo.get("tabelas", [])

    # ── Phase 1: Discover entry points ────────────────────────────────
    entry_points = discover_entry_points(db, tabelas)

    # ── Phase 2: Trace functions in each source ───────────────────────
    all_traces = {}
    for fonte in entry_points["fontes_escrita"][:10]:
        arquivo = fonte["arquivo"]
        traces = trace_function_flow(db, arquivo)
        if traces:
            all_traces[arquivo] = traces

    # ── Phase 3: Format data for LLM ─────────────────────────────────
    # Entry points summary
    ep_lines = []
    if entry_points["menus"]:
        ep_lines.append("MENUS (usuario abre manualmente):")
        for m in entry_points["menus"][:8]:
            ep_lines.append(f"  - {m['rotina']}: {m['nome']} ({m['modulo']})")
    if entry_points["jobs"]:
        ep_lines.append("JOBS (execucao automatica):")
        for j in entry_points["jobs"][:5]:
            rate = f"cada {j['refresh_rate']}s" if j['refresh_rate'] else "manual"
            ep_lines.append(f"  - {j['rotina']} (sessao: {j['sessao']}, {rate})")
    if entry_points["schedules"]:
        ep_lines.append("SCHEDULES:")
        for s in entry_points["schedules"][:5]:
            ep_lines.append(f"  - {s['rotina']} ({s['tipo_recorrencia']}, {s['status']})")
    if entry_points["pes_implementados"]:
        ep_lines.append("PEs IMPLEMENTADOS:")
        for p in entry_points["pes_implementados"][:5]:
            ep_lines.append(f"  - {p['arquivo']}: {', '.join(p['pes'][:5])}")

    # Function traces
    trace_lines = []
    for arquivo, traces in all_traces.items():
        trace_lines.append(f"\n### {arquivo}")
        for t in traces:
            if not t["operacoes_escrita"] and not t["calls_u"]:
                continue  # Skip functions that don't write or call others
            trace_lines.append(f"  {t['tipo']} {t['assinatura']}")
            if t["calls_u"]:
                trace_lines.append(f"    Chama: {', '.join(t['calls_u'])}")
            if t["chamada_por"]:
                trace_lines.append(f"    Chamada por: {', '.join(t['chamada_por'])}")
            if t["params"].get("sx6"):
                params_str = ", ".join(p["var"] for p in t["params"]["sx6"])
                trace_lines.append(f"    Parametros: {params_str}")
            if t["params"].get("sx1"):
                trace_lines.append(f"    Perguntas SX1: {', '.join(t['params']['sx1'])}")
            for op in t["operacoes_escrita"]:
                campos_str = ", ".join(op["campos"][:5])
                cond = f" [SE {op['condicao']}]" if op["condicao"] else ""
                trace_lines.append(f"    >> {op['tipo']}: {op['tabela']} ({campos_str}){cond} linha {op['linha']}")

    entry_points_text = "\n".join(ep_lines) or "Nenhum ponto de entrada identificado."
    traces_text = "\n".join(trace_lines) or "Nenhum trace de funcao disponivel."

    # ── Phase 4: LLM generates narrative ──────────────────────────────
    prompt = TRACER_PROMPT.format(
        nome=nome,
        descricao=descricao,
        tabelas=", ".join(tabelas),
        entry_points=entry_points_text,
        function_traces=traces_text[:10000],
    )

    try:
        response = await asyncio.to_thread(
            llm._call,
            [{"role": "user", "content": prompt}],
            temperature=0.2,
            use_gen=False,  # use strong model for accuracy
            timeout=90,
        )
    except Exception as e:
        return {"passo_a_passo": f"Erro ao gerar trace: {str(e)[:200]}", "trace_json": {}, "confidence": 0.0}

    # Parse JSON response
    trace_json = {}
    try:
        text = response.strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        trace_json = json.loads(text)
    except (json.JSONDecodeError, IndexError):
        # Try to extract JSON from response
        match = re.search(r'\{[\s\S]+\}', response)
        if match:
            try:
                trace_json = json.loads(match.group())
            except json.JSONDecodeError:
                pass

    if not trace_json:
        return {"passo_a_passo": response, "trace_json": {}, "confidence": 0.3}

    # ── Phase 5: Verification ─────────────────────────────────────────
    raw_data_summary = entry_points_text + "\n\n" + traces_text[:5000]
    verify_prompt = VERIFY_TRACE_PROMPT.format(
        raw_data=raw_data_summary,
        trace_json=json.dumps(trace_json, ensure_ascii=False, indent=2)[:5000],
    )

    confidence = 0.8
    try:
        verify_response = await asyncio.to_thread(
            llm._call,
            [{"role": "user", "content": verify_prompt}],
            temperature=0.1,
            use_gen=True,
            timeout=30,
        )
        vtext = verify_response.strip()
        if "```" in vtext:
            vtext = vtext.split("```")[1]
            if vtext.startswith("json"):
                vtext = vtext[4:]
            vtext = vtext.strip()
        verification = json.loads(vtext)
        if not verification.get("valido", True):
            confidence = 0.5
            # Append problems as notes
            problems = verification.get("problemas", [])
            if problems:
                trace_json.setdefault("notas_verificacao", problems)
            missing = verification.get("passos_faltando", [])
            if missing:
                trace_json.setdefault("passos_faltando", missing)
    except Exception:
        pass  # Verification failure doesn't block the trace

    # ── Phase 6: Generate markdown narrative ──────────────────────────
    markdown = _trace_to_markdown(trace_json, nome)

    return {
        "passo_a_passo": markdown,
        "trace_json": trace_json,
        "confidence": confidence,
    }


def _trace_to_markdown(trace_json: dict, nome: str) -> str:
    """Convert structured trace JSON to readable markdown."""
    lines = [f"## Passo a Passo Técnico: {nome}\n"]

    passos = trace_json.get("passos", [])
    if passos:
        lines.append("### Fluxo de Execução\n")
        for p in passos:
            ordem = p.get("ordem", "?")
            ator = p.get("ator", "Sistema")
            acao = p.get("acao", "")
            rotina = p.get("rotina", "")
            funcao = p.get("funcao", "")
            tabelas = p.get("tabelas_afetadas", [])
            campos = p.get("campos_gravados", [])
            condicao = p.get("condicao", "")
            consequencia = p.get("consequencia", "")

            lines.append(f"**Passo {ordem}** — {ator}")
            lines.append(f"  {acao}")
            if rotina or funcao:
                lines.append(f"  - Rotina: `{rotina}::{funcao}()`")
            if tabelas:
                lines.append(f"  - Tabelas: {', '.join(tabelas)}")
            if campos:
                lines.append(f"  - Campos: {', '.join(campos[:8])}")
            if condicao:
                lines.append(f"  - Condição: `{condicao}`")
            if consequencia:
                lines.append(f"  - → {consequencia}")
            lines.append("")

    # Decision points
    decisoes = trace_json.get("pontos_decisao", [])
    if decisoes:
        lines.append("### Pontos de Decisão\n")
        for d in decisoes:
            lines.append(f"- **{d.get('descricao', '')}** (`{d.get('local', '')}`)")
            lines.append(f"  - SIM → {d.get('resultado_sim', '')}")
            lines.append(f"  - NÃO → {d.get('resultado_nao', '')}")
        lines.append("")

    # Jobs
    jobs = trace_json.get("jobs_envolvidos", [])
    if jobs:
        lines.append("### Jobs Assíncronos\n")
        for j in jobs:
            lines.append(f"- **{j.get('rotina', '')}** ({j.get('frequencia', '')}): {j.get('funcao', '')}")
        lines.append("")

    # PEs
    pes = trace_json.get("pes_envolvidos", [])
    if pes:
        lines.append("### Pontos de Entrada (PEs)\n")
        for pe in pes:
            lines.append(f"- **{pe.get('nome', '')}** ({pe.get('arquivo', '')}): {pe.get('funcao', '')}")
        lines.append("")

    # Verification notes
    notas = trace_json.get("notas_verificacao", [])
    if notas:
        lines.append("### Notas de Verificação\n")
        for n in notas:
            lines.append(f"- ⚠️ {n}")

    return "\n".join(lines)
