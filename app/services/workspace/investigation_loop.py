# backend/services/investigation_loop.py
"""Iterative investigation loop — LLM decides which tool to call at each step.

The LLM receives minimal initial context and requests specific tools
in a loop (max MAX_STEPS). Each tool result accumulates in context.
When the LLM has enough information, it signals 'pronto' to exit.
"""
import json
import asyncio
import time
from typing import AsyncGenerator

from app.services.workspace import analista_tools as at
from app.services.workspace import padrao_tools as pt
from app.services.workspace.context_manager import summarize_tool_result, build_investigation_context

MAX_STEPS = 5
MAX_PLANNED_STEPS = 8
MAX_PARALLEL = 5  # max concurrent read-only tools (avoid overwhelming the DB)

# ── Tool safety classification ────────────────────────────────────────────

# Tools safe to run in parallel (read-only, no side effects)
READ_ONLY_TOOLS = {
    "quem_grava", "info_tabela", "operacoes_escrita", "rastrear_condicao",
    "ver_parametro", "ver_fonte_cliente", "buscar_texto_fonte",
    "buscar_pes_cliente", "mapear_processo", "buscar_menus",
    "buscar_propositos", "analise_impacto", "analise_aumento_campo",
    "processos_cliente", "jobs_schedules", "buscar_fontes_tabela",
    # Padrão tools (read-only by nature)
    "fonte_padrao", "pes_disponiveis", "codigo_pe", "buscar_funcao_padrao",
}

# Tools that use LLM calls — can run parallel but limited concurrency
LLM_TOOLS = {"analisar_fonte", "gerar_codigo"}

# ── Tool registry ──────────────────────────────────────────────────────────

TOOL_MAP = {
    # Client tools
    "quem_grava": lambda **kw: at.tool_quem_grava_campo(kw.get("tabela", ""), kw.get("campo", "")),
    "info_tabela": lambda **kw: at.tool_info_tabela(kw.get("tabela", "")),
    "operacoes_escrita": lambda **kw: at.tool_operacoes_tabela(kw.get("tabela", "")),
    "rastrear_condicao": lambda **kw: at.tool_investigar_condicao(
        kw.get("arquivo", ""), kw.get("funcao", ""), kw.get("variavel", "")
    ),
    "ver_parametro": lambda **kw: at.tool_buscar_parametros(termo=kw.get("nome", ""), tabela=""),
    "ver_fonte_cliente": lambda **kw: at.tool_ler_fonte_cliente(kw.get("arquivo", ""), kw.get("funcao", "")),
    "buscar_texto_fonte": lambda **kw: at.tool_buscar_texto_fonte(kw.get("arquivo", ""), kw.get("texto", ""), int(kw.get("contexto", 15))),
    "buscar_pes_cliente": lambda **kw: at.tool_buscar_pes(rotina=kw.get("rotina", ""), modulo=kw.get("modulo", "")),
    "mapear_processo": lambda **kw: at.tool_mapear_processo(kw.get("tabela", ""), kw.get("campo", "")),
    "buscar_menus": lambda **kw: at.tool_buscar_menus(kw.get("termo", "")),
    "buscar_propositos": lambda **kw: at.tool_buscar_propositos(kw.get("termo", "")),
    "analise_impacto": lambda **kw: at.tool_analise_impacto(kw.get("tabela", ""), kw.get("campo", ""), kw.get("alteracao", "novo_campo")),
    "analise_aumento_campo": lambda **kw: _call_analise_aumento(**kw),
    "processos_cliente": lambda **kw: at.tool_processos_cliente(kw.get("tabelas")),
    "jobs_schedules": lambda **kw: {
        "jobs": at.tool_buscar_jobs(rotina=kw.get("rotina", "")),
        "schedules": at.tool_buscar_schedules(rotina=kw.get("rotina", "")),
    },
    # Padrão tools
    "fonte_padrao": lambda **kw: pt.tool_fonte_padrao(kw.get("arquivo", "")),
    "pes_disponiveis": lambda **kw: pt.tool_pes_disponiveis(kw.get("rotina", "")),
    "codigo_pe": lambda **kw: pt.tool_codigo_pe(kw.get("nome_pe", "")),
    "buscar_funcao_padrao": lambda **kw: pt.tool_buscar_funcao_padrao(kw.get("nome", "")),
    # Code specialist tools (require LLM — injected at runtime)
    "analisar_fonte": lambda **kw: _code_specialist_call("diagnosticar", kw),
    "gerar_codigo": lambda **kw: _code_specialist_call("gerar", kw),
}


def _call_analise_aumento(**kw) -> dict:
    from app.services.workspace.analise_campo_chave import tool_analise_aumento_campo
    return tool_analise_aumento_campo(kw.get("tabela", ""), kw.get("campo", ""), int(kw.get("novo_tamanho", 0)))


def _code_specialist_call(modo: str, kw: dict) -> dict:
    """Call code_specialist with injected LLM."""
    llm = kw.pop("_llm", None)
    if not llm:
        return {"erro": "LLM not available for code specialist"}
    from app.services.workspace.code_specialist import code_specialist
    dossie = {k: v for k, v in kw.items() if not k.startswith("_")}
    return code_specialist(llm, modo, dossie)


TOOL_DESCRIPTIONS = {
    "quem_grava": {"desc": "Quem grava em tabela/campo (pontos de escrita)", "args": "tabela, campo?"},
    "info_tabela": {"desc": "Metadata da tabela (campos, índices, custom)", "args": "tabela"},
    "operacoes_escrita": {"desc": "Resumo de todas operações de escrita na tabela", "args": "tabela"},
    "rastrear_condicao": {"desc": "Backward trace: de onde vem uma variável de condição", "args": "arquivo, funcao, variavel"},
    "ver_parametro": {"desc": "Consultar parâmetro SX6 (valor atual + descrição)", "args": "nome"},
    "ver_fonte_cliente": {"desc": "Ler código real de fonte do cliente", "args": "arquivo, funcao?"},
    "buscar_texto_fonte": {"desc": "Buscar TEXTO/TAG/VARIAVEL dentro de um fonte específico (lê o arquivo real do disco)", "args": "arquivo, texto, contexto?"},
    "buscar_pes_cliente": {"desc": "PEs implementados pelo cliente", "args": "rotina?, modulo?"},
    "mapear_processo": {"desc": "Mapa COMPLETO do processo (estados, satélites, companheiros)", "args": "tabela, campo"},
    "buscar_menus": {"desc": "Buscar rotinas nos menus do cliente", "args": "termo"},
    "buscar_propositos": {"desc": "Buscar fontes por propósito/descrição", "args": "termo"},
    "analise_impacto": {"desc": "Análise de impacto COMPLETA: fontes de escrita, MsExecAuto, integracoes, gatilhos — USAR para campo obrigatório", "args": "tabela, campo?, alteracao?"},
    "analise_aumento_campo": {"desc": "Análise de AUMENTO de campo chave (SXG): grupo de campos, campos fora do grupo, PadR chumbado, indices — USAR quando pedir para aumentar tamanho", "args": "tabela, campo, novo_tamanho?"},
    "processos_cliente": {"desc": "Processos de negócio detectados", "args": "tabelas?"},
    "jobs_schedules": {"desc": "Jobs e schedules da rotina", "args": "rotina"},
    "fonte_padrao": {"desc": "Metadata + funções de fonte PADRÃO Protheus", "args": "arquivo"},
    "pes_disponiveis": {"desc": "PEs disponíveis na rotina PADRÃO (ExecBlocks reais)", "args": "rotina"},
    "codigo_pe": {"desc": "Código fonte onde PE é chamado no PADRÃO", "args": "nome_pe"},
    "buscar_funcao_padrao": {"desc": "Buscar função no padrão (assinatura, arquivo)", "args": "nome"},
    "analisar_fonte": {"desc": "Analisar código ADVPL para diagnosticar problema", "args": "codigo, problema, rotina?, arquivo?"},
    "gerar_codigo": {"desc": "Gerar código ADVPL novo (PE, User Function, MVC)", "args": "tipo, nome, spec, contexto?"},
    "pronto": {"desc": "Já tenho informação suficiente para responder", "args": ""},
}


def build_tool_descriptions() -> str:
    """Build formatted tool list for LLM prompt."""
    lines = []
    for name, info in TOOL_DESCRIPTIONS.items():
        args = f"({info['args']})" if info['args'] else ""
        lines.append(f"- {name}{args}: {info['desc']}")
    return "\n".join(lines)


INVESTIGATION_PROMPT = """Voce e um investigador tecnico de ambientes TOTVS Protheus.
Seu objetivo e investigar o problema/requisicao do usuario usando as ferramentas disponiveis.

CONTEXTO INICIAL:
{initial_context}

FERRAMENTAS DISPONIVEIS:
{tool_descriptions}

INSTRUCOES:
1. Analise o contexto e decida qual ferramenta chamar para investigar
2. Chame UMA ferramenta por vez
3. Analise o resultado e decida se precisa de mais dados
4. Quando tiver informacao suficiente, chame "pronto"
5. Seja EFICIENTE — nao busque tudo, busque so o que precisa
6. Se encontrar escrita condicional, rastreie a condicao
7. Se precisar entender rotina padrao, consulte fonte_padrao ou pes_disponiveis
8. Nao busque mais que {max_steps} ferramentas

RESULTADOS ANTERIORES:
{accumulated_results}

Responda APENAS com JSON:
{{"tool": "nome_da_ferramenta", "args": {{"param": "valor"}}}}

Ou se ja tem tudo:
{{"tool": "pronto"}}"""


def _parse_tool_call(llm_response: str) -> dict:
    """Parse LLM response into a tool call."""
    text = llm_response.strip()

    # Try to extract JSON from response
    try:
        # Handle markdown-wrapped JSON
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        parsed = json.loads(text)
        if "tool" in parsed:
            return parsed
    except (json.JSONDecodeError, IndexError):
        pass

    # Try to find JSON in text
    import re
    match = re.search(r'\{[^}]+\}', text, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group())
            if "tool" in parsed:
                return parsed
        except json.JSONDecodeError:
            pass

    # Fallback: assume ready to answer
    return {"tool": "pronto"}


def _execute_tool(tool_name: str, args: dict, llm=None) -> dict:
    """Execute a tool by name with given arguments."""
    if tool_name not in TOOL_MAP:
        return {"erro": f"Ferramenta '{tool_name}' nao encontrada"}

    from app.services.workspace.tool_validator import validate_tool_args, fix_common_arg_issues

    # Auto-fix common issues
    args = fix_common_arg_issues(tool_name, args)

    # Validate
    is_valid, error_msg = validate_tool_args(tool_name, args)
    if not is_valid:
        return {"erro": f"Args invalidos para {tool_name}: {error_msg}"}

    try:
        # Inject LLM for code specialist tools
        if tool_name in ("analisar_fonte", "gerar_codigo") and llm:
            args = {**args, "_llm": llm}
        result = TOOL_MAP[tool_name](**args)
        return result
    except Exception as e:
        return {"erro": f"Erro ao executar {tool_name}: {str(e)[:200]}"}


def _is_error_result(result: dict) -> bool:
    """Check if a tool result represents an error."""
    return isinstance(result, dict) and "erro" in result


def _truncate_result(result: dict, max_chars: int = 2000) -> str:
    """Serialize and truncate a tool result for context accumulation.

    Error results are never truncated — they are small and critical
    for the LLM to adapt its strategy.
    """
    text = json.dumps(result, ensure_ascii=False, default=str)
    if _is_error_result(result):
        return text
    if len(text) > max_chars:
        text = text[:max_chars] + "... [truncado]"
    return text


def _group_steps_by_parallelism(valid_steps: list) -> list:
    """Group consecutive read-only steps for parallel execution.

    Returns a list of groups, where each group is a list of (orig_idx, step) tuples.
    Consecutive read-only steps form a single group (parallelizable).
    Non-read-only steps each get their own single-item group (sequential).
    """
    if not valid_steps:
        return []

    groups = []
    current_group = []

    for idx, step in valid_steps:
        tool_name = step.get("tool", "")
        is_parallel_safe = tool_name in READ_ONLY_TOOLS

        if is_parallel_safe:
            current_group.append((idx, step))
        else:
            # Flush any accumulated read-only group
            if current_group:
                groups.append(current_group)
                current_group = []
            # Non-read-only step gets its own group
            groups.append([(idx, step)])

    # Flush remaining read-only group
    if current_group:
        groups.append(current_group)

    return groups


def _process_tool_result(
    tool_name: str,
    tool_args: dict,
    result: dict,
    summaries: list,
    artifact_registry,
    prefix: str = "",
    elapsed: float = 0.0,
) -> list:
    """Process a single tool result: check errors, extract artifacts, summarize.

    Returns a list of event dicts to yield.
    """
    events = []
    elapsed_str = f" ({elapsed:.1f}s)" if elapsed > 0 else ""

    # Check for tool errors
    if _is_error_result(result):
        error_msg = result.get("erro", "Erro desconhecido")
        summary = summarize_tool_result(tool_name, tool_args, result)
        summaries.append(summary)
        events.append({
            "type": "status",
            "step": f"{prefix} Erro em {tool_name}: {error_msg[:150]}",
            "error": True,
        })
        events.append({
            "type": "tool_result",
            "tool": tool_name,
            "args": tool_args,
            "summary": f"ERRO: {error_msg[:300]}",
            "error": True,
        })
        return events

    # Extract artifacts from raw result (before summarization)
    if artifact_registry is not None:
        try:
            from app.services.workspace.artifact_registry import extract_artifacts
            extract_artifacts(tool_name, tool_args, result, artifact_registry)
        except Exception:
            pass

    # Summarize
    summary = summarize_tool_result(tool_name, tool_args, result)
    summaries.append(summary)

    events.append({
        "type": "tool_result",
        "tool": tool_name,
        "args": tool_args,
        "summary": summary.get("summary", "")[:300] + elapsed_str,
    })
    return events


async def run_investigation(
    llm,
    initial_context: str,
    modo: str = "ajuste",
) -> AsyncGenerator[dict, None]:
    """Run the iterative investigation loop.

    Yields SSE-compatible events:
        {"type": "status", "step": "Buscando quem grava no C5_LIBEROK..."}
        {"type": "tool_result", "tool": "quem_grava", "summary": "3 pontos encontrados"}
        {"type": "complete", "context": "accumulated context for final LLM call"}

    Args:
        llm: LLMService instance
        initial_context: Starting context (from classification + resolution)
        modo: Conversation mode (ajuste, melhoria, duvida)
    """
    summaries = []  # structured summaries from context_manager
    accumulated_raw = []  # raw text for LLM tool-selection prompt (backward compat)
    tool_descriptions = build_tool_descriptions()

    for step in range(MAX_STEPS):
        # Build prompt — LLM sees structured summaries for tool selection
        if summaries:
            acc_text = build_investigation_context(summaries)
        else:
            acc_text = "Nenhum resultado ainda."

        prompt = INVESTIGATION_PROMPT.format(
            initial_context=initial_context,
            tool_descriptions=tool_descriptions,
            accumulated_results=acc_text,
            max_steps=MAX_STEPS,
        )

        # Ask LLM which tool to call
        try:
            response = await asyncio.to_thread(
                llm._call,
                [{"role": "user", "content": prompt}],
                temperature=0.1,
                use_gen=True,
                timeout=30,
            )
        except Exception as e:
            yield {"type": "status", "step": f"Erro na análise: {str(e)[:100]}"}
            break

        decision = _parse_tool_call(response)
        tool_name = decision.get("tool", "pronto")
        tool_args = decision.get("args", {})

        if tool_name == "pronto":
            break

        # Status update
        desc = TOOL_DESCRIPTIONS.get(tool_name, {}).get("desc", tool_name)
        args_summary = ", ".join(f"{k}={v}" for k, v in tool_args.items()) if tool_args else ""
        yield {"type": "status", "step": f"Investigando: {desc} ({args_summary})..."}

        # Execute tool
        result = await asyncio.to_thread(_execute_tool, tool_name, tool_args, llm)

        # Check for tool errors — feed them back so the LLM can adapt
        if _is_error_result(result):
            error_msg = result.get("erro", "Erro desconhecido")
            # Summarize the error so it shows in accumulated context
            summary = summarize_tool_result(tool_name, tool_args, result)
            summaries.append(summary)
            yield {
                "type": "status",
                "step": f"Erro em {tool_name}: {error_msg[:150]}",
                "error": True,
            }
            yield {
                "type": "tool_result",
                "tool": tool_name,
                "args": tool_args,
                "summary": f"ERRO: {error_msg[:300]}",
                "error": True,
            }
            # Continue — the LLM will see the error and can try different args or tool
            continue

        # Summarize result using context_manager
        summary = summarize_tool_result(tool_name, tool_args, result)
        summaries.append(summary)

        yield {
            "type": "tool_result",
            "tool": tool_name,
            "args": tool_args,
            "summary": summary.get("summary", "")[:300],
        }

    # Return organized context (by topic, not chronological)
    final_context = build_investigation_context(summaries) if summaries else initial_context
    yield {"type": "complete", "context": final_context}


async def run_planned_investigation(
    llm,
    plan: dict,
    initial_context: str,
    modo: str = "ajuste",
    artifact_registry=None,
) -> AsyncGenerator[dict, None]:
    """Run investigation following a structured plan, then allow reactive steps.

    Phase 1: Execute planned steps in order (no LLM decision needed)
    Phase 2: Allow reactive_steps where LLM can request additional tools

    Yields same SSE events as run_investigation for compatibility.
    If artifact_registry is provided, extracts typed artifacts from raw results.
    """
    summaries = []
    planned_steps = plan.get("steps", [])
    reactive_allowed = plan.get("reactive_steps", 2)

    # ── Phase 1: Execute planned steps (with parallel grouping) ─────────
    # Filter valid steps first, keeping original indices for status messages
    valid_steps = []
    for i, step in enumerate(planned_steps):
        tool_name = step.get("tool", "")
        if tool_name == "pronto" or not tool_name:
            continue
        if tool_name not in TOOL_MAP:
            continue
        valid_steps.append((i, step))

    # Group consecutive read-only steps for parallel execution
    groups = _group_steps_by_parallelism(valid_steps)

    for group in groups:
        if len(group) == 1:
            # Single step — execute sequentially (original behavior)
            orig_idx, step = group[0]
            tool_name = step["tool"]
            tool_args = step.get("args", {})

            desc = TOOL_DESCRIPTIONS.get(tool_name, {}).get("desc", tool_name)
            args_summary = ", ".join(f"{k}={v}" for k, v in tool_args.items()) if tool_args else ""
            yield {"type": "status", "step": f"[{orig_idx+1}/{len(planned_steps)}] {desc} ({args_summary})..."}

            t0 = time.monotonic()
            result = await asyncio.to_thread(_execute_tool, tool_name, tool_args, llm)
            elapsed = time.monotonic() - t0

            for evt in _process_tool_result(
                tool_name, tool_args, result, summaries, artifact_registry,
                prefix=f"[{orig_idx+1}/{len(planned_steps)}]", elapsed=elapsed,
            ):
                yield evt
        else:
            # Parallel group — run all read-only tools concurrently
            tool_names_in_group = [s["tool"] for _, s in group]
            yield {
                "type": "status",
                "step": f"[{group[0][0]+1}-{group[-1][0]+1}/{len(planned_steps)}] "
                        f"Running {len(group)} tools in parallel: {', '.join(tool_names_in_group)}...",
            }

            semaphore = asyncio.Semaphore(MAX_PARALLEL)

            async def _run_one(orig_idx: int, step: dict) -> tuple:
                """Execute a single tool under semaphore control."""
                tn = step["tool"]
                ta = step.get("args", {})
                async with semaphore:
                    t0 = time.monotonic()
                    res = await asyncio.to_thread(_execute_tool, tn, ta, llm)
                    elapsed = time.monotonic() - t0
                return (orig_idx, tn, ta, res, elapsed)

            tasks = [_run_one(idx, s) for idx, s in group]
            t0_group = time.monotonic()
            results = await asyncio.gather(*tasks, return_exceptions=True)
            group_elapsed = time.monotonic() - t0_group

            # Process results in original order
            for res_item in results:
                if isinstance(res_item, Exception):
                    # Shouldn't happen since _execute_tool catches errors, but be safe
                    continue
                orig_idx, tool_name, tool_args, result, elapsed = res_item

                for evt in _process_tool_result(
                    tool_name, tool_args, result, summaries, artifact_registry,
                    prefix=f"[{orig_idx+1}/{len(planned_steps)}]", elapsed=elapsed,
                ):
                    yield evt

            yield {
                "type": "status",
                "step": f"Parallel group completed: {len(group)} tools in {group_elapsed:.1f}s",
            }

    # ── Phase 2: Reactive steps (LLM-driven, based on findings) ───────────
    if reactive_allowed > 0 and summaries:
        tool_descriptions = build_tool_descriptions()

        for step in range(reactive_allowed):
            acc_text = build_investigation_context(summaries)

            reactive_prompt = INVESTIGATION_PROMPT.format(
                initial_context=initial_context,
                tool_descriptions=tool_descriptions,
                accumulated_results=acc_text,
                max_steps=reactive_allowed,
            )
            # Add guidance about what's already been done
            reactive_prompt += (
                f"\n\nJa executamos {len(summaries)} ferramentas conforme o plano."
                f"\nSe precisa de MAIS dados para completar a investigacao, chame outra ferramenta."
                f"\nSe ja tem informacao suficiente, chame 'pronto'."
            )

            try:
                response = await asyncio.to_thread(
                    llm._call,
                    [{"role": "user", "content": reactive_prompt}],
                    temperature=0.1,
                    use_gen=True,
                    timeout=30,
                )
            except Exception:
                break

            decision = _parse_tool_call(response)
            tool_name = decision.get("tool", "pronto")
            tool_args = decision.get("args", {})

            if tool_name == "pronto":
                break

            desc = TOOL_DESCRIPTIONS.get(tool_name, {}).get("desc", tool_name)
            args_summary = ", ".join(f"{k}={v}" for k, v in tool_args.items()) if tool_args else ""
            yield {"type": "status", "step": f"[extra] {desc} ({args_summary})..."}

            result = await asyncio.to_thread(_execute_tool, tool_name, tool_args, llm)

            # Check for tool errors in reactive phase
            if _is_error_result(result):
                error_msg = result.get("erro", "Erro desconhecido")
                summary = summarize_tool_result(tool_name, tool_args, result)
                summaries.append(summary)
                yield {
                    "type": "status",
                    "step": f"[extra] Erro em {tool_name}: {error_msg[:150]}",
                    "error": True,
                }
                yield {
                    "type": "tool_result",
                    "tool": tool_name,
                    "args": tool_args,
                    "summary": f"ERRO: {error_msg[:300]}",
                    "error": True,
                }
                continue

            summary = summarize_tool_result(tool_name, tool_args, result)
            summaries.append(summary)

            yield {
                "type": "tool_result",
                "tool": tool_name,
                "args": tool_args,
                "summary": summary.get("summary", "")[:300],
            }

    # Return organized context
    final_context = build_investigation_context(summaries) if summaries else initial_context
    yield {"type": "complete", "context": final_context}
