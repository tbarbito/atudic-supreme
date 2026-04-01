"""Context Manager — sumarização inteligente de resultados de tools.

Em vez de truncar JSON bruto em 2000 chars, cada tool tem um summarizer
que extrai fatos-chave estruturados. O contexto final é organizado por
tópico (não por ordem cronológica de chamada).
"""
import json
from typing import Any


def _safe_len(v: Any) -> int:
    """Length of a list/dict, 0 if not iterable."""
    if isinstance(v, (list, dict)):
        return len(v)
    return 0


# ── Per-tool summarizers ──────────────────────────────────────────────────────

def _summarize_quem_grava(args: dict, result: Any) -> dict:
    tabela = args.get("tabela", "?")
    campo = args.get("campo", "")
    if not isinstance(result, list):
        return {"summary": f"Nenhum ponto de escrita encontrado para {tabela}.{campo}", "key_facts": [], "entities": []}

    total = len(result)
    condicionais = [r for r in result if r.get("condicao")]
    arquivos = sorted(set(r.get("arquivo", "") for r in result if r.get("arquivo")))

    lines = []
    target = f"{tabela}.{campo}" if campo else tabela
    lines.append(f"{total} ponto(s) de escrita em {target}")
    if condicionais:
        lines.append(f"  {len(condicionais)} escrita(s) condicional(is)")

    facts = []
    entities = list(arquivos)
    for r in result[:8]:
        arq = r.get("arquivo", "?")
        func = r.get("funcao", "?")
        cond = r.get("condicao", "")
        origem = r.get("origem_campo", "")
        line = f"- {arq}::{func}()"
        if cond:
            line += f" [condicao: {cond[:80]}]"
        if origem:
            line += f" [origem: {origem[:60]}]"
        facts.append(line)

    return {
        "summary": "\n".join(lines),
        "key_facts": facts,
        "entities": entities,
    }


def _summarize_operacoes_escrita(args: dict, result: Any) -> dict:
    if not isinstance(result, dict):
        return {"summary": "Sem dados de operações", "key_facts": [], "entities": []}

    tabela = result.get("tabela", args.get("tabela", "?"))
    total = result.get("total_operacoes", 0)
    por_tipo = result.get("por_tipo", {})
    fontes = result.get("fontes", [])
    condicionais = result.get("escritas_condicionais", [])
    campos_top = result.get("campos_mais_escritos", [])

    tipo_str = ", ".join(f"{k}:{v}" for k, v in por_tipo.items()) if por_tipo else "nenhuma"

    facts = []
    facts.append(f"{tabela}: {total} operações de escrita ({tipo_str})")
    facts.append(f"  {len(fontes)} fonte(s): {', '.join(fontes[:5])}")
    if condicionais:
        facts.append(f"  {len(condicionais)} escrita(s) condicional(is):")
        for c in condicionais[:5]:
            facts.append(f"    - {c.get('arquivo','?')}::{c.get('funcao','?')} [{c.get('condicao','')[:60]}]")
    if campos_top:
        top = ", ".join(f"{c['campo']}({c['vezes']}x)" for c in campos_top[:5])
        facts.append(f"  Campos mais escritos: {top}")

    return {
        "summary": facts[0],
        "key_facts": facts[1:],
        "entities": fontes[:10],
    }


def _summarize_info_tabela(args: dict, result: Any) -> dict:
    if not isinstance(result, dict) or not result.get("existe", False):
        return {"summary": f"Tabela {args.get('tabela','?')} não encontrada", "key_facts": [], "entities": []}

    t = result
    summary = f"{t['tabela']} ({t.get('nome','')}) — {t.get('total_campos',0)} campos ({t.get('campos_custom',0)} custom), {t.get('indices',0)} índices"
    return {"summary": summary, "key_facts": [], "entities": [t["tabela"]]}


def _summarize_rastrear_condicao(args: dict, result: Any) -> dict:
    if not isinstance(result, dict):
        return {"summary": "Rastreamento falhou", "key_facts": [], "entities": []}

    var = result.get("variavel", args.get("variavel", "?"))
    encontrada = result.get("definicao_encontrada", False)
    expressao = result.get("expressao", "")
    deps = result.get("dependencias", [])
    blocos = result.get("blocos_alternativos", [])

    facts = []
    entities = []

    if encontrada:
        facts.append(f"Variável {var} definida como: {expressao[:120]}")
    else:
        facts.append(f"Variável {var}: definição não encontrada")

    for dep in deps[:5]:
        tipo = dep.get("tipo", "?")
        nome = dep.get("nome", "?")
        if tipo == "parametro":
            val = dep.get("valor_atual", "?")
            desc = dep.get("descricao", "")[:60]
            facts.append(f"  ← Parâmetro {nome} = {val} ({desc})")
            entities.append(nome)
        elif tipo == "campo_tabela":
            tab = dep.get("tabela", "?")
            titulo = dep.get("titulo", "")[:40]
            facts.append(f"  ← Campo {tab}->{nome} ({titulo})")
            entities.append(f"{tab}->{nome}")
        elif tipo == "funcao":
            arq = dep.get("arquivo", "?")
            resumo = dep.get("resumo", "")[:60]
            facts.append(f"  ← Função {nome}() em {arq} — {resumo}")
            sub = dep.get("sub_funcoes", [])
            for sf in sub[:3]:
                facts.append(f"      └ {sf.get('nome','?')}(): {sf.get('resumo','')[:50]}")
            entities.append(arq)
        else:
            facts.append(f"  ← {tipo}: {nome}")

    if blocos:
        facts.append(f"  {len(blocos)} bloco(s) alternativo(s) encontrado(s)")
        for b in blocos[:3]:
            facts.append(f"    - {b.get('funcao','?')}: {b.get('nota','')[:60]}")

    return {"summary": facts[0] if facts else f"Rastreamento de {var}", "key_facts": facts[1:], "entities": entities}


def _summarize_mapear_processo(args: dict, result: Any) -> dict:
    if not isinstance(result, dict):
        return {"summary": "Mapeamento falhou", "key_facts": [], "entities": []}

    proc = result.get("processo", {})
    estados = result.get("estados", [])
    companions = result.get("campos_companheiros", [])
    satellites = result.get("tabelas_satelite", [])
    fontes = result.get("fontes_no_fluxo", [])
    complexidade = result.get("complexidade", "?")

    facts = []
    facts.append(f"Processo {result.get('tabela','?')}.{result.get('campo','')} — complexidade {complexidade}")
    facts.append(f"  {proc.get('total_pontos_escrita',0)} pontos de escrita, {proc.get('total_fontes',0)} fontes, {proc.get('total_estados',0)} estados")

    if estados:
        est_str = ", ".join(f"{e['valor']}={e.get('significado','?')}" for e in estados[:6])
        facts.append(f"  Estados: {est_str}")

    if companions:
        comp_str = ", ".join(c["campo"] for c in companions[:5])
        facts.append(f"  Campos companheiros: {comp_str}")

    if satellites:
        sat_str = ", ".join(f"{s['tabela']}({s.get('nome','')})" for s in satellites[:5])
        facts.append(f"  Tabelas satélite: {sat_str}")

    entities = [f.get("arquivo", "") for f in fontes[:10]]
    return {"summary": facts[0], "key_facts": facts[1:], "entities": entities}


def _summarize_buscar_pes(args: dict, result: Any) -> dict:
    if not isinstance(result, list) or not result:
        return {"summary": f"Nenhum PE encontrado para {args.get('rotina', args.get('modulo', '?'))}", "key_facts": [], "entities": []}

    facts = [f"{len(result)} PE(s) catalogado(s)"]
    for pe in result[:8]:
        facts.append(f"  - {pe.get('nome','?')}: {pe.get('objetivo','')[:60]}")
    entities = [pe.get("nome", "") for pe in result]
    return {"summary": facts[0], "key_facts": facts[1:], "entities": entities}


def _summarize_ver_parametro(args: dict, result: Any) -> dict:
    if not isinstance(result, list) or not result:
        return {"summary": f"Parâmetro {args.get('nome','?')} não encontrado", "key_facts": [], "entities": []}

    facts = []
    entities = []
    for p in result[:5]:
        var = p.get("variavel", "?")
        val = p.get("conteudo", "?")
        desc = p.get("descricao", "")[:60]
        padrao = p.get("valor_padrao", "")
        line = f"{var} = {val}"
        if padrao and padrao != val:
            line += f" (padrão: {padrao})"
        if desc:
            line += f" — {desc}"
        facts.append(line)
        entities.append(var)
    return {"summary": f"{len(result)} parâmetro(s) encontrado(s)", "key_facts": facts, "entities": entities}


def _summarize_ver_fonte_cliente(args: dict, result: Any) -> dict:
    if not isinstance(result, dict) or not result.get("encontrado"):
        return {"summary": f"Fonte {args.get('arquivo','?')} não encontrado", "key_facts": [], "entities": []}

    content = result.get("content", "")
    lines = content.count("\n") + 1
    return {
        "summary": f"Código de {result.get('arquivo','?')}::{result.get('funcao','*')} ({lines} linhas)",
        "key_facts": [f"[código disponível — {lines} linhas]"],
        "entities": [result.get("arquivo", "")],
        "_raw_content": content,  # preserved for verification
    }


def _summarize_buscar_menus(args: dict, result: Any) -> dict:
    if not isinstance(result, list) or not result:
        return {"summary": f"Nenhum menu encontrado para '{args.get('termo','?')}'", "key_facts": [], "entities": []}

    facts = [f"{len(result)} rotina(s) encontrada(s) nos menus"]
    for m in result[:6]:
        facts.append(f"  - {m.get('rotina','?')}: {m.get('nome','')} ({m.get('modulo','')})")
    entities = [m.get("rotina", "") for m in result]
    return {"summary": facts[0], "key_facts": facts[1:], "entities": entities}


def _summarize_buscar_propositos(args: dict, result: Any) -> dict:
    if not isinstance(result, list) or not result:
        return {"summary": f"Nenhum fonte encontrado para '{args.get('termo','?')}'", "key_facts": [], "entities": []}

    facts = [f"{len(result)} fonte(s) relacionado(s)"]
    for p in result[:6]:
        facts.append(f"  - {p.get('arquivo','?')} ({p.get('modulo','')}): {p.get('proposito','')[:60]}")
    entities = [p.get("arquivo", "") for p in result]
    return {"summary": facts[0], "key_facts": facts[1:], "entities": entities}


def _summarize_processos_cliente(args: dict, result: Any) -> dict:
    if not isinstance(result, dict):
        return {"summary": "Sem processos", "key_facts": [], "entities": []}

    procs = result.get("processos", [])
    if not procs:
        return {"summary": "Nenhum processo detectado", "key_facts": [], "entities": []}

    facts = [f"{len(procs)} processo(s) detectado(s)"]
    for p in procs[:5]:
        facts.append(f"  - {p.get('nome','?')} ({p.get('tipo','')}, {p.get('criticidade','?')}): {p.get('descricao','')[:60]}")
    return {"summary": facts[0], "key_facts": facts[1:], "entities": []}


def _summarize_jobs_schedules(args: dict, result: Any) -> dict:
    if not isinstance(result, dict):
        return {"summary": "Sem jobs/schedules", "key_facts": [], "entities": []}

    jobs = result.get("jobs", [])
    scheds = result.get("schedules", [])
    facts = [f"{len(jobs)} job(s), {len(scheds)} schedule(s)"]
    for j in jobs[:3]:
        facts.append(f"  Job: {j.get('sessao','?')} → {j.get('rotina','?')} (refresh: {j.get('refresh_rate','')})")
    for s in scheds[:3]:
        facts.append(f"  Schedule: {s.get('codigo','?')} → {s.get('rotina','?')} ({s.get('tipo_recorrencia','')}, status: {s.get('status','')})")
    return {"summary": facts[0], "key_facts": facts[1:], "entities": []}


def _summarize_fonte_padrao(args: dict, result: Any) -> dict:
    if not isinstance(result, dict) or not result.get("encontrado"):
        return {"summary": f"Fonte padrão {args.get('arquivo','?')} não encontrado", "key_facts": [], "entities": []}

    funcoes = result.get("funcoes", [])
    facts = [f"PADRÃO {result['arquivo']}: {result.get('lines_of_code',0)} LOC, {len(funcoes)} funções, módulo {result.get('modulo','?')}"]
    for f in funcoes[:10]:
        facts.append(f"  - {f.get('tipo','')}: {f.get('assinatura', f.get('nome','?'))}")
    return {"summary": facts[0], "key_facts": facts[1:], "entities": [result.get("arquivo", "")]}


def _summarize_pes_disponiveis(args: dict, result: Any) -> dict:
    if not isinstance(result, list) or not result:
        return {"summary": f"Nenhum PE disponível para {args.get('rotina','?')}", "key_facts": [], "entities": []}

    facts = [f"{len(result)} PE(s) disponíveis no padrão para {args.get('rotina','?')}"]
    for pe in result[:10]:
        nome = pe.get("nome_pe", "?")
        op = pe.get("operacao", "")
        ret = pe.get("tipo_retorno", "nil")
        params = pe.get("parametros", "")
        comment = pe.get("comentario", "")[:50]
        line = f"  - {nome} ({op})" if op else f"  - {nome}"
        if ret != "nil":
            line += f" → retorno {ret}"
        if params:
            line += f" | params: {params[:40]}"
        if comment:
            line += f" — {comment}"
        facts.append(line)
    entities = [pe.get("nome_pe", "") for pe in result]
    return {"summary": facts[0], "key_facts": facts[1:], "entities": entities}


def _summarize_codigo_pe(args: dict, result: Any) -> dict:
    if not isinstance(result, list) or not result:
        return {"summary": f"Código do PE {args.get('nome_pe','?')} não encontrado", "key_facts": [], "entities": []}

    facts = [f"PE {args.get('nome_pe','?')} encontrado em {len(result)} local(is)"]
    for r in result[:3]:
        facts.append(f"  - {r.get('arquivo','?')}::{r.get('funcao','?')} linha {r.get('linha',0)}")
    return {
        "summary": facts[0],
        "key_facts": facts[1:],
        "entities": [r.get("arquivo", "") for r in result],
        "_raw_content": "\n".join(r.get("codigo", "") for r in result[:2]),
    }


def _summarize_buscar_funcao_padrao(args: dict, result: Any) -> dict:
    if not isinstance(result, list) or not result:
        return {"summary": f"Função {args.get('nome','?')} não encontrada no padrão", "key_facts": [], "entities": []}

    facts = [f"{len(result)} função(ões) encontrada(s) no padrão"]
    for f in result[:8]:
        facts.append(f"  - {f.get('tipo','')}: {f.get('assinatura', f.get('nome','?'))} em {f.get('arquivo','?')}")
    return {"summary": facts[0], "key_facts": facts[1:], "entities": [f.get("arquivo", "") for f in result]}


def _summarize_analise_aumento_campo(args: dict, result: Any) -> dict:
    if not isinstance(result, dict) or "erro" in result:
        return {"summary": "Análise de aumento falhou", "key_facts": [], "entities": []}

    resumo = result.get("resumo", {})
    campo = result.get("campo", "?")
    tabela = result.get("tabela", "?")
    tam_atual = result.get("tamanho_atual", 0)
    novo_tam = result.get("novo_tamanho", 0)

    facts = [f"Aumento de {tabela}.{campo} de {tam_atual} para {novo_tam} posições"]

    # Group info
    grupo = result.get("grupo_sxg", "")
    if grupo:
        facts.append(f"✅ Grupo SXG {grupo}: {resumo.get('mudam_automaticamente', 0)} campos mudam automaticamente via Configurador")
    else:
        facts.append("⚠️ Campo SEM grupo SXG — todos os campos precisam ser alterados manualmente")

    # Campos fora do grupo
    fora = result.get("campos_fora_grupo", [])
    if fora:
        facts.append(f"⚠️ {len(fora)} campo(s) com F3={tabela} mas FORA do grupo SXG — precisam ajuste MANUAL:")
        for c in fora[:10]:
            facts.append(f"  - {c['tabela']}.{c['campo']}: {c['titulo']} (tam={c['tamanho']}) — {c['risco']}")

    # PadR chumbado
    padr = result.get("padr_chumbado", [])
    if padr:
        arquivos_unicos = sorted(set(p["arquivo"] for p in padr))
        facts.append(f"⚠️ {len(arquivos_unicos)} fonte(s) com PadR CHUMBADO (tamanho {tam_atual}) — VÃO TRUNCAR o valor:")
        for a in arquivos_unicos[:8]:
            facts.append(f"  - {a}: PadR com tamanho fixo {tam_atual}")

    # TamSX3 OK
    tamsx3 = result.get("tamsx3_dinamico", [])
    if tamsx3:
        facts.append(f"✅ {len(tamsx3)} fonte(s) com TamSX3 dinâmico — se adaptam automaticamente")

    # Índices
    indices = result.get("indices_risco", [])
    if indices:
        facts.append(f"⚠️ {len(indices)} índice(s) podem ESTOURAR o limite de 250 chars:")
        for idx in indices[:5]:
            facts.append(f"  - {idx['tabela']} idx {idx['ordem']}: ~{idx['tamanho_estimado']} chars ({idx['risco']})")

    # MsExecAuto + integrações
    msexec = result.get("msexecauto", [])
    integ = result.get("integracoes", [])
    if msexec:
        facts.append(f"⚠️ {len(msexec)} MsExecAuto pode(m) enviar campo com tamanho antigo:")
        for m in msexec[:5]:
            facts.append(f"  - {m['arquivo']}: {m['risco'][:60]}")
    if integ:
        facts.append(f"⚠️ {len(integ)} integração(ões) que gravam na tabela:")
        for i in integ[:5]:
            facts.append(f"  - {i['arquivo']} ({i.get('modulo', '')})")

    entities = [c["arquivo"] for c in padr] + [m["arquivo"] for m in msexec]
    return {"summary": facts[0], "key_facts": facts[1:], "entities": sorted(set(entities))}


def _summarize_analise_impacto(args: dict, result: Any) -> dict:
    if not isinstance(result, dict):
        return {"summary": "Análise de impacto falhou", "key_facts": [], "entities": []}

    tabela = result.get("tabela", args.get("tabela", "?"))
    facts = [f"Impacto em {tabela}: {result.get('total_fontes_escrita', 0)} fontes de escrita, {result.get('total_msexecauto', 0)} MsExecAuto"]

    # MsExecAuto — CRITICAL for mandatory fields — PUT FIRST
    msexecauto = result.get("msexecauto_fontes", [])
    if msexecauto:
        facts.append(f"⚠️ RISCO CRITICO — {len(msexecauto)} fonte(s) com MsExecAuto que VÃO QUEBRAR se campo obrigatório não for tratado:")
        for m in msexecauto[:10]:
            facts.append(f"  - {m['arquivo']}: MsExecAuto({m['rotina_chamada']}) — PRECISA adicionar o campo no array do ExecAuto")
    else:
        facts.append("  Nenhum MsExecAuto detectado para esta tabela")

    # ExecAutos
    exec_autos = result.get("exec_autos", [])
    if exec_autos:
        facts.append(f"  {len(exec_autos)} fonte(s) com ExecBlock que gravam na tabela")
        for ea in exec_autos[:5]:
            facts.append(f"    - {ea['arquivo']}: ExecBlocks {ea['exec_autos'][:3]}")

    # Integrations
    integracoes = result.get("integracoes", [])
    if integracoes:
        facts.append(f"  {len(integracoes)} integração(ões)/WebService(s) que gravam na tabela:")
        for integ in integracoes[:5]:
            facts.append(f"    - {integ['arquivo']} ({integ.get('modulo', '')})")

    # Triggers
    gatilhos = result.get("gatilhos", [])
    if gatilhos:
        facts.append(f"  {len(gatilhos)} gatilho(s) na tabela")

    # Campo info
    campo_info = result.get("campo_info", {})
    if campo_info:
        facts.append(f"  Campo {campo_info.get('campo','')}: {campo_info.get('tipo','')}/{campo_info.get('tamanho','')} — {campo_info.get('titulo','')}")

    entities = [f.get("arquivo", "") for f in result.get("fontes_escrita", [])[:10]]
    entities.extend(m["arquivo"] for m in msexecauto)
    return {"summary": facts[0], "key_facts": facts[1:], "entities": entities}


def _summarize_generic(tool_name: str, args: dict, result: Any) -> dict:
    """Fallback summarizer for unknown tools."""
    text = json.dumps(result, ensure_ascii=False, default=str)
    if len(text) > 1500:
        text = text[:1500] + "... [truncado]"
    return {"summary": f"{tool_name}: {text[:100]}", "key_facts": [text], "entities": []}


# ── Summarizer registry ──────────────────────────────────────────────────────

_SUMMARIZERS = {
    "quem_grava": _summarize_quem_grava,
    "info_tabela": _summarize_info_tabela,
    "operacoes_escrita": _summarize_operacoes_escrita,
    "rastrear_condicao": _summarize_rastrear_condicao,
    "ver_parametro": _summarize_ver_parametro,
    "ver_fonte_cliente": _summarize_ver_fonte_cliente,
    "buscar_pes_cliente": _summarize_buscar_pes,
    "mapear_processo": _summarize_mapear_processo,
    "buscar_menus": _summarize_buscar_menus,
    "buscar_propositos": _summarize_buscar_propositos,
    "processos_cliente": _summarize_processos_cliente,
    "jobs_schedules": _summarize_jobs_schedules,
    "fonte_padrao": _summarize_fonte_padrao,
    "pes_disponiveis": _summarize_pes_disponiveis,
    "codigo_pe": _summarize_codigo_pe,
    "buscar_funcao_padrao": _summarize_buscar_funcao_padrao,
    "analise_impacto": _summarize_analise_impacto,
    "analise_aumento_campo": _summarize_analise_aumento_campo,
}


def summarize_tool_result(tool_name: str, args: dict, raw_result: Any) -> dict:
    """Summarize a tool result into structured facts.

    Returns:
        {
            "tool": str,
            "args": dict,
            "summary": str,        # one-line summary
            "key_facts": list[str], # bullet-point facts
            "entities": list[str],  # tables, files, params discovered
        }
    """
    summarizer = _SUMMARIZERS.get(tool_name, lambda a, r: _summarize_generic(tool_name, a, r))
    try:
        result = summarizer(args, raw_result)
    except Exception:
        result = _summarize_generic(tool_name, args, raw_result)

    result["tool"] = tool_name
    result["args"] = args
    return result


# ── Context builder ───────────────────────────────────────────────────────────

# Topic classification for tools
_TOPIC_MAP = {
    "quem_grava": "escrita",
    "operacoes_escrita": "escrita",
    "rastrear_condicao": "escrita",
    "info_tabela": "dicionario",
    "ver_parametro": "dicionario",
    "buscar_pes_cliente": "customizacao",
    "ver_fonte_cliente": "customizacao",
    "buscar_propositos": "customizacao",
    "mapear_processo": "processo",
    "processos_cliente": "processo",
    "buscar_menus": "processo",
    "jobs_schedules": "processo",
    "fonte_padrao": "padrao",
    "pes_disponiveis": "padrao",
    "codigo_pe": "padrao",
    "buscar_funcao_padrao": "padrao",
    "analise_impacto": "escrita",
    "analisar_fonte": "codigo",
    "gerar_codigo": "codigo",
}

_TOPIC_TITLES = {
    "escrita": "Pontos de Escrita e Condições",
    "dicionario": "Dicionário e Parâmetros",
    "customizacao": "Customizações do Cliente",
    "processo": "Processos e Rotinas",
    "padrao": "Comportamento Padrão Protheus",
    "codigo": "Análise de Código",
}

_TOPIC_ORDER = ["escrita", "dicionario", "padrao", "customizacao", "processo", "codigo"]


def build_investigation_context(summaries: list[dict]) -> str:
    """Build a focused context document organized by topic.

    Instead of chronological tool-call order, groups results by topic
    and presents key facts in a structured format.
    """
    if not summaries:
        return "Nenhum resultado de investigação."

    # Group by topic
    by_topic: dict[str, list[dict]] = {}
    for s in summaries:
        topic = _TOPIC_MAP.get(s.get("tool", ""), "outro")
        by_topic.setdefault(topic, []).append(s)

    # Collect all entities across all summaries
    all_entities = set()
    for s in summaries:
        all_entities.update(s.get("entities", []))

    # Build sections
    sections = []

    for topic in _TOPIC_ORDER:
        if topic not in by_topic:
            continue
        title = _TOPIC_TITLES.get(topic, topic.title())
        items = by_topic[topic]

        lines = [f"## {title}"]
        for item in items:
            lines.append(f"**{item.get('summary', '')}**")
            for fact in item.get("key_facts", []):
                lines.append(fact)
            lines.append("")  # blank line between tools

        sections.append("\n".join(lines))

    # Handle uncategorized
    if "outro" in by_topic:
        lines = ["## Outros"]
        for item in by_topic["outro"]:
            lines.append(f"**{item.get('summary', '')}**")
            for fact in item.get("key_facts", []):
                lines.append(fact)
        sections.append("\n".join(lines))

    # Key facts summary at the top
    key_facts_all = []
    for s in summaries:
        for f in s.get("key_facts", []):
            if f.startswith("  ") or f.startswith("    "):
                continue  # skip sub-items
            key_facts_all.append(f)

    header = "## Resumo da Investigação\n"
    header += f"Ferramentas consultadas: {len(summaries)}\n"
    header += f"Entidades encontradas: {', '.join(sorted(all_entities)[:15])}\n"

    return header + "\n\n" + "\n\n".join(sections)
