"""
Plan-and-Execute Engine do GolIAs.

Para tarefas complexas, o agente primeiro cria um plano (lista de steps),
depois executa cada step, podendo replanjar se algo falha.

Modo de ativação:
- Classificador de complexidade detecta tarefa multi-step
- agent_chat.py redireciona para plan_and_execute() em vez de two-step/react

Fase 3: O planner agora tem awareness de sub-agentes disponiveis. Steps que
envolvem dominios especificos podem ser delegados a sub-agentes autonomos
em vez de executar tools diretamente.
"""

import json
import re
import logging

from app.services.agent_tools import execute_tool

logger = logging.getLogger(__name__)

# Indicadores de tarefa que exige planejamento
_PLAN_INDICATORS = [
    r"analis[ea].*e\s+(sugir|corrig|recomend|compar|propon)",
    r"compar[ea].*e\s+(corri[gj]|equaliz|sincroni|sugir)",
    r"verifi[cq].*depois",
    r"primeiro.*depois",
    r"investig[ue].*e\s+(resolv|corrig|sugir)",
    r"diagnostiqu[e].*e\s+(corrig|resolv)",
    r"identifi[cq].*e\s+(corrig|resolv|sugir)",
    r"faz[ea].*tudo",
]


def needs_planning(message):
    """Detecta se a mensagem indica tarefa que precisa de planejamento.

    Complementa o classify_complexity() do agent_intent — aqui o foco
    é especificamente em tarefas que têm múltiplos verbos de ação.
    """
    for pattern in _PLAN_INDICATORS:
        if re.search(pattern, message, re.IGNORECASE):
            return True
    return False


class TaskPlan:
    """Representa um plano de execução com steps."""

    def __init__(self, goal, steps):
        self.goal = goal
        self.steps = steps  # [{description, tool, params, depends_on, status, result}]
        self.replanned = False

    def to_display(self):
        """Formata plano para exibição ao usuário."""
        lines = [f"**Plano de execução** ({len(self.steps)} passos):"]
        for i, step in enumerate(self.steps, 1):
            status_icon = {"pending": "⬜", "running": "🔄", "done": "✅", "failed": "❌"}.get(
                step.get("status", "pending"), "⬜"
            )
            desc = step.get("description", "?")
            tool = step.get("tool", "")
            tool_info = f" (`{tool}`)" if tool else ""
            lines.append(f"{status_icon} {i}. {desc}{tool_info}")
        return "\n".join(lines)


class TaskPlanner:
    """Cria planos de execução a partir de tarefas complexas."""

    def __init__(self, llm_provider):
        self._llm = llm_provider

    def create_plan(self, message, available_tools, context_summary=""):
        """Usa LLM para decompor tarefa em steps executáveis.

        Args:
            message: tarefa do usuário
            available_tools: lista de tools disponíveis [{name, description}]
            context_summary: resumo do contexto atual

        Returns:
            TaskPlan ou None se não conseguir criar
        """
        tool_list = "\n".join(f"- {t['name']}: {t['description']}" for t in available_tools[:15])

        prompt = (
            f"Decomponha esta tarefa em 2-5 passos executáveis.\n\n"
            f"Tarefa: \"{message}\"\n\n"
            f"Ferramentas disponíveis:\n{tool_list}\n\n"
            f"{'Contexto: ' + context_summary if context_summary else ''}\n\n"
            f"Para cada passo, responda EXATAMENTE neste formato JSON:\n"
            f'{{"steps": [\n'
            f'  {{"description": "o que fazer", "tool": "nome_da_tool", "params": {{}}}},\n'
            f'  {{"description": "analisar resultado", "tool": "reason", "params": {{}}}}\n'
            f"]}}\n\n"
            f"Regras:\n"
            f'- Use "tool": "reason" para steps que não precisam de ferramenta (apenas raciocínio)\n'
            f"- Máximo 5 steps\n"
            f"- Responda APENAS o JSON, nada mais"
        )

        try:
            result = self._llm.chat(
                messages=[{"role": "user", "content": prompt}],
                system_prompt="Você decompõe tarefas em planos executáveis. Responda apenas JSON válido.",
                temperature=0.3,
                max_tokens=500,
            )

            raw = result.get("content", "").strip()
            plan_data = self._parse_plan_json(raw)

            if not plan_data or not plan_data.get("steps"):
                logger.warning("LLM não retornou plano válido")
                return None

            steps = []
            for s in plan_data["steps"][:5]:
                steps.append({
                    "description": s.get("description", "?"),
                    "tool": s.get("tool", "reason"),
                    "params": s.get("params", {}),
                    "status": "pending",
                    "result": None,
                })

            plan = TaskPlan(goal=message, steps=steps)
            logger.info("📋 Plano criado: %d steps para '%s'", len(steps), message[:50])
            return plan

        except Exception as e:
            logger.warning("Erro ao criar plano: %s", e)
            return None

    def _parse_plan_json(self, raw):
        """Extrai JSON do plano da resposta do LLM (tolerante a markdown)."""
        # Remover code blocks
        cleaned = re.sub(r"```json\s*", "", raw)
        cleaned = re.sub(r"```\s*", "", cleaned)
        cleaned = cleaned.strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            # Tentar encontrar JSON dentro do texto
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
        return None


class PlanExecutor:
    """Executa steps de um TaskPlan sequencialmente."""

    def __init__(self, llm_provider=None, emit_step_fn=None):
        self._llm = llm_provider
        self._emit_step = emit_step_fn

    def execute_plan(self, plan, user_profile="viewer", environment_id=None, user_id=None):
        """Executa todos os steps do plano e retorna resultados.

        Returns:
            dict com plan_display, results, tools_used, final_summary
        """
        tools_used = []
        all_results = []

        for i, step in enumerate(plan.steps):
            step["status"] = "running"

            # Emitir SSE
            if self._emit_step:
                self._emit_step(environment_id, {
                    "step": f"plan_step_{i+1}",
                    "type": "plan_step",
                    "description": f"Passo {i+1}/{len(plan.steps)}: {step['description']}",
                    "tool": step["tool"],
                })

            if step["tool"] == "reason":
                # Step de raciocínio — sem tool call
                step["status"] = "done"
                step["result"] = {"reasoning": step["description"]}
                all_results.append({
                    "step": i + 1,
                    "description": step["description"],
                    "type": "reasoning",
                })
                continue

            # Executar tool
            try:
                result = execute_tool(
                    step["tool"],
                    dict(step["params"]),
                    user_profile=user_profile,
                    environment_id=environment_id,
                    user_id=user_id,
                )

                if result.get("success"):
                    step["status"] = "done"
                    step["result"] = result.get("data")
                    tools_used.append(step["tool"])
                    all_results.append({
                        "step": i + 1,
                        "description": step["description"],
                        "tool": step["tool"],
                        "success": True,
                        "data_summary": _summarize_data(result.get("data")),
                    })
                else:
                    step["status"] = "failed"
                    step["result"] = result.get("error")
                    all_results.append({
                        "step": i + 1,
                        "description": step["description"],
                        "tool": step["tool"],
                        "success": False,
                        "error": result.get("error"),
                    })
                    logger.warning("📋 Step %d/%d falhou: %s", i + 1, len(plan.steps), result.get("error"))

            except Exception as e:
                step["status"] = "failed"
                step["result"] = str(e)
                all_results.append({
                    "step": i + 1,
                    "description": step["description"],
                    "tool": step["tool"],
                    "success": False,
                    "error": str(e),
                })

        return {
            "plan_display": plan.to_display(),
            "results": all_results,
            "tools_used": tools_used,
            "total_steps": len(plan.steps),
            "successful_steps": sum(1 for r in all_results if r.get("success", True)),
        }


def _summarize_data(data, max_len=500):
    """Resume dados de tool result para contexto compacto."""
    if data is None:
        return ""
    text = json.dumps(data, ensure_ascii=False, default=str)
    if len(text) > max_len:
        return text[:max_len] + "..."
    return text


def get_available_agents_summary():
    """Retorna resumo dos sub-agentes disponiveis para o planner.

    Permite que o LLM saiba quais agentes podem ser delegados
    ao criar planos de execucao.
    """
    try:
        from app.services.agent_specialists import get_specialist_registry
        registry = get_specialist_registry()
        registry.load()

        agents = []
        for spec_data in registry.get_all_specialists():
            if spec_data.get("agent_enabled") and spec_data["name"] != "general":
                agents.append({
                    "name": spec_data["name"],
                    "description": spec_data["description"],
                    "tools_count": len(spec_data.get("tools", [])),
                })
        return agents
    except Exception:
        return []
