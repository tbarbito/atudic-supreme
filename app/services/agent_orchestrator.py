"""
Agent Orchestrator — Camada de orquestracao multi-agente do GolIAs (Fase 3).

Tres padroes de orquestracao:
1. Single dispatch: tarefa simples → 1 sub-agente (ja implementado na Fase 2)
2. Fan-out / Fan-in: tarefa multi-dominio → N sub-agentes em paralelo → merge
3. Chain (pipeline): output do agente A → input do agente B → resultado final

O orquestrador analisa a tarefa, decide o padrao, despacha, agrega e responde.
Se algum sub-agente falha, o orquestrador pode replanar usando agentes alternativos.
"""

import json
import logging
import re
from app.services.agent_base import BaseSpecialistAgent, SpecialistAgentResult
from app.services.agent_specialists import get_specialist_registry
from app.services.agent_context import ContextBuilder
from app.services.agent_config import agent_config as cfg

logger = logging.getLogger(__name__)

# Mapeamento de dominios → specialist para roteamento semantico
# Keywords devem ser ESPECIFICAS para evitar falsos positivos
# Score minimo de 2 keywords para ativar multi-dominio
_DOMAIN_KEYWORDS = {
    "diagnostico": [
        "erro", "error", "alerta", "alert", "falha", "crash", "timeout",
        "monitor", "diagnostico", "diagnosticar", "lento", "travou",
        # Protheus: TSS, fiscal, erros comuns
        "tss", "rejeicao", "sefaz", "certificado", "contingencia",
        "spedprocserver", "nfe", "cte", "mdfe",
    ],
    "database": [
        "banco", "database", "conexao", "connection", "dicionario", "dictionary",
        "tabela", "table", "campo", "field", "sx2", "sx3", "six", "equalizacao",
        "query", "sql", "select", "schema", "parametro", "mv_",
        # Protheus: modulos, cadastros, documentos
        "sigafin", "sigacom", "sigafat", "sigaest", "sigafis", "sigamnt",
        "sa1", "sa2", "sb1", "sc5", "sc6", "se1", "se2", "sf1", "sf2",
        "cliente", "fornecedor", "produto", "pedido", "nota fiscal",
        "titulo", "sx1", "sx5", "sx6", "sx7", "sx9", "sxa", "sxb",
    ],
    "auditor": [
        "auditoria", "audit", "appserver.ini", "dbaccess.ini", "smartclient.ini",
        "auditar", "secao ini", "chave ini",
    ],
    "settings": [
        "ambiente", "environment", "variavel servidor", "notificacao",
        "notification", "configurar ambiente",
    ],
    "admin_ops": [
        "webhook", "permissao", "permission", "admin usuario",
    ],
    "devops": [
        "pipeline", "deploy", "build", "ci/cd", "repositorio", "repositório",
        "git", "servico", "serviço", "service", "services", "agendamento",
        "schedule", "iniciar", "parar", "reiniciar", "start", "stop", "restart",
        "appserver", "dbaccess", "license server", "protheus",
        # Protheus: RPO, compilacao
        "rpo", "compilar", "patch", "ptm", "troca quente",
    ],
    "knowledge": [
        "conhecimento", "knowledge", "procedimento", "procedure", "como fazer",
        "passo a passo", "referencia", "documentacao",
        # Protheus: funcoes, classes, padroes
        "advpl", "tlpp", "mvc", "fwbrowse", "fwformview", "msexecauto",
        "ponto de entrada", "gatilho", "treport", "fwrest",
    ],
    "general": [
        "sistema", "plataforma", "atudc", "atudic", "golias",
        "status geral", "visao geral", "overview",
    ],
}

# Score minimo para considerar um dominio ativo
_MIN_DOMAIN_SCORE = 1
# Score minimo do segundo dominio para ativar multi-agente
_MIN_SECONDARY_SCORE = 2


class OrchestrationPlan:
    """Plano de orquestracao gerado pelo orchestrator."""

    __slots__ = ("pattern", "steps", "goal")

    def __init__(self, pattern, steps, goal=""):
        self.pattern = pattern  # "single", "fan_out", "chain"
        self.steps = steps  # [{"specialist": name, "task": description, "depends_on": idx|None}]
        self.goal = goal

    def to_display(self):
        """Formata plano para log/debug."""
        icon = {"single": "➡️", "fan_out": "⚡", "chain": "🔗"}.get(self.pattern, "?")
        lines = [f"{icon} Orquestracao: {self.pattern} ({len(self.steps)} agentes)"]
        for i, step in enumerate(self.steps):
            dep = f" (depende de #{step['depends_on']+1})" if step.get("depends_on") is not None else ""
            lines.append(f"  {i+1}. [{step['specialist']}] {step['task'][:80]}{dep}")
        return "\n".join(lines)


class AgentOrchestrator:
    """Orquestrador multi-agente do GolIAs.

    Decide se a tarefa precisa de 1 ou N agentes e coordena a execucao.
    """

    # Maximo de agentes em paralelo
    MAX_PARALLEL_AGENTS = 3

    # Maximo de steps em cadeia
    MAX_CHAIN_STEPS = 4

    def __init__(self, llm_provider, user_profile="viewer",
                 environment_id=None, user_id=None, user_info=None,
                 emit_step_fn=None):
        self._llm = llm_provider
        self._user_profile = user_profile
        self._environment_id = environment_id
        self._user_id = user_id
        self._user_info = user_info or {}
        self._emit_step = emit_step_fn
        self._registry = get_specialist_registry()

    # =================================================================
    # ANALISE E ROTEAMENTO
    # =================================================================

    def analyze_task(self, message, intent, entities):
        """Analisa a tarefa e decide o padrao de orquestracao.

        Returns:
            OrchestrationPlan ou None (se nao precisa de orquestracao multi-agente)
        """
        # Detectar dominios mencionados na mensagem
        domains = self._detect_domains(message)

        if len(domains) == 0:
            return None  # Nenhum dominio detectado, fluxo legado

        if len(domains) == 1:
            specialist = self._registry.get_specialist_by_name(domains[0])
            if specialist and specialist.agent_enabled:
                return OrchestrationPlan(
                    pattern="single",
                    steps=[{"specialist": domains[0], "task": message, "depends_on": None}],
                    goal=message,
                )
            return None  # Specialist sem agente, fluxo legado

        # Multi-dominio: decidir entre fan-out e chain
        plan = self._decide_multi_agent_plan(message, domains)
        return plan

    def _detect_domains(self, message):
        """Detecta quais dominios sao relevantes para a mensagem.

        Para evitar falsos positivos:
        - O primeiro dominio precisa de score >= 1
        - Dominios adicionais precisam de score >= 2 (evita ativacao por 1 keyword ambigua)
        """
        msg_lower = message.lower()
        scored = {}

        for domain, keywords in _DOMAIN_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in msg_lower)
            if score >= _MIN_DOMAIN_SCORE:
                scored[domain] = score

        if not scored:
            return []

        # Ordenar por relevancia
        sorted_domains = sorted(scored.keys(), key=lambda d: scored[d], reverse=True)

        # Primeiro dominio: sempre inclui (maior score)
        # Dominios adicionais: so se score >= _MIN_SECONDARY_SCORE
        candidates = []
        for i, domain in enumerate(sorted_domains):
            if i == 0 or scored[domain] >= _MIN_SECONDARY_SCORE:
                candidates.append(domain)

        # Filtrar: so manter dominios com agent_enabled
        result = []
        for domain in candidates:
            specialist = self._registry.get_specialist_by_name(domain)
            if specialist and specialist.agent_enabled:
                result.append(domain)

        logger.info(
            "🎯 Dominios detectados: %s (scores: %s) → filtrados: %s",
            sorted_domains, {d: scored[d] for d in sorted_domains}, result,
        )

        return result[:self.MAX_PARALLEL_AGENTS]

    def _decide_multi_agent_plan(self, message, domains):
        """Decide entre fan-out e chain para tarefa multi-dominio."""
        msg_lower = message.lower()

        # Indicadores de cadeia (sequencial): "primeiro X depois Y", "analise e depois corrija"
        chain_patterns = [
            r"primeir[oa].*depois",
            r"analis[ea].*e\s+(depois|entao|ai)",
            r"verifi[cq].*e\s+(depois|entao|ai)",
            r"compar[ea].*e\s+(depois|entao|corri[gj]|equaliz)",
            r"diagnostic[oa].*e\s+(resolv|corrig|sugir)",
        ]

        is_chain = any(re.search(p, msg_lower) for p in chain_patterns)

        if is_chain and len(domains) >= 2:
            # Chain: agentes em sequencia, output de um → input do proximo
            steps = []
            for i, domain in enumerate(domains[:self.MAX_CHAIN_STEPS]):
                steps.append({
                    "specialist": domain,
                    "task": message,  # Cada agente recebe a tarefa original + contexto
                    "depends_on": i - 1 if i > 0 else None,
                })
            return OrchestrationPlan(pattern="chain", steps=steps, goal=message)
        else:
            # Fan-out: agentes em paralelo, cada um com sua perspectiva
            steps = []
            for domain in domains[:self.MAX_PARALLEL_AGENTS]:
                steps.append({
                    "specialist": domain,
                    "task": message,
                    "depends_on": None,
                })
            return OrchestrationPlan(pattern="fan_out", steps=steps, goal=message)

    # =================================================================
    # EXECUCAO
    # =================================================================

    def execute(self, plan, context_text=""):
        """Executa o plano de orquestracao.

        Args:
            plan: OrchestrationPlan
            context_text: Contexto do sistema

        Returns:
            dict com resultados agregados
        """
        logger.info("🎯 Orquestracao: %s", plan.to_display())

        if self._emit_step:
            self._emit_step(self._environment_id, {
                "step": "orchestration_start",
                "type": "orchestration",
                "description": f"Orquestracao {plan.pattern}: {len(plan.steps)} agentes",
                "pattern": plan.pattern,
                "agents": [s["specialist"] for s in plan.steps],
            })

        if plan.pattern == "fan_out":
            return self._execute_fan_out(plan, context_text)
        elif plan.pattern == "chain":
            return self._execute_chain(plan, context_text)
        else:
            # Single: dispatch direto (compatibilidade)
            return self._execute_single(plan, context_text)

    def _execute_single(self, plan, context_text):
        """Executa um unico sub-agente."""
        step = plan.steps[0]
        result = self._run_agent(step["specialist"], step["task"], context_text)
        return self._build_response([result], plan)

    def _execute_fan_out(self, plan, context_text):
        """Executa N sub-agentes sequencialmente e agrega resultados.

        Nota: execucao sequencial (nao paralela) porque sub-agentes usam
        _internal_api que depende do Flask request context, e threads
        perdem esse contexto. Futuro: migrar para async com app_context.
        """
        results = []

        for step in plan.steps:
            specialist_name = step["specialist"]

            if self._emit_step:
                self._emit_step(self._environment_id, {
                    "step": f"fan_out_{specialist_name}",
                    "type": "fan_out_step",
                    "description": f"Executando agente: {specialist_name}",
                })

            try:
                result = self._run_agent(specialist_name, step["task"], context_text)
                results.append(result)
                logger.info(
                    "⚡ Fan-out: agente '%s' concluiu (success=%s)",
                    specialist_name, result.success,
                )
            except Exception as e:
                logger.error("⚡ Fan-out: agente '%s' falhou: %s", specialist_name, e)
                results.append(SpecialistAgentResult(
                    specialist_name, success=False,
                    error=str(e), needs_escalation=True,
                ))

        return self._build_response(results, plan)

    def _execute_chain(self, plan, context_text):
        """Executa sub-agentes em cadeia: output de A → input de B."""
        results = []
        accumulated_context = context_text

        for i, step in enumerate(plan.steps):
            if self._emit_step:
                self._emit_step(self._environment_id, {
                    "step": f"chain_step_{i+1}",
                    "type": "chain_step",
                    "description": f"Chain {i+1}/{len(plan.steps)}: agente '{step['specialist']}'",
                })

            result = self._run_agent(
                step["specialist"], step["task"],
                context_text=accumulated_context,
            )
            results.append(result)

            logger.info(
                "🔗 Chain step %d/%d: agente '%s' (success=%s)",
                i + 1, len(plan.steps), step["specialist"], result.success,
            )

            if result.success and result.text:
                # Output deste agente vira contexto do proximo
                accumulated_context += (
                    f"\n\n## Resultado do agente '{step['specialist']}'\n{result.text}"
                )
            elif not result.success:
                # Tentar replanejamento se agente falhou
                replan_result = self._try_replan(step, result, accumulated_context)
                if replan_result:
                    results[-1] = replan_result
                    if replan_result.success and replan_result.text:
                        accumulated_context += (
                            f"\n\n## Resultado do agente '{replan_result.specialist_name}' (replanejado)\n"
                            f"{replan_result.text}"
                        )
                else:
                    # Agente falhou e nao conseguiu replanar — continuar com aviso
                    accumulated_context += (
                        f"\n\n## Agente '{step['specialist']}' FALHOU\n"
                        f"Erro: {result.error or 'desconhecido'}"
                    )

        return self._build_response(results, plan)

    # =================================================================
    # EXECUCAO DE AGENTE INDIVIDUAL
    # =================================================================

    def _run_agent(self, specialist_name, task, context_text=""):
        """Cria e executa um sub-agente para o specialist."""
        specialist = self._registry.get_specialist_by_name(specialist_name)
        if not specialist:
            return SpecialistAgentResult(
                specialist_name, success=False,
                error=f"Specialist '{specialist_name}' nao encontrado",
                needs_escalation=True,
            )

        try:
            agent = BaseSpecialistAgent(
                specialist=specialist,
                llm_provider=self._llm,
                user_profile=self._user_profile,
                environment_id=self._environment_id,
                user_id=self._user_id,
            )
            return agent.execute(task_description=task, context_text=context_text)
        except Exception as e:
            logger.error("Erro ao executar agente '%s': %s", specialist_name, e)
            return SpecialistAgentResult(
                specialist_name, success=False,
                error=str(e), needs_escalation=True,
            )

    # =================================================================
    # REPLANNING
    # =================================================================

    def _try_replan(self, failed_step, failed_result, context_text):
        """Tenta replanar quando um agente da cadeia falha.

        Estrategia: procurar outro specialist que cubra o dominio.
        Ex: se 'diagnostico' falhou, tentar 'knowledge' como fallback.
        """
        failed_name = failed_step["specialist"]

        # Mapa de fallback entre specialists
        fallback_map = {
            "diagnostico": "knowledge",
            "database": "knowledge",
            "devops": "diagnostico",
            "auditor": "knowledge",
            "settings": "admin_ops",
            "admin_ops": "settings",
            "knowledge": None,  # Knowledge nao tem fallback
            "proactive": "diagnostico",
        }

        fallback_name = fallback_map.get(failed_name)
        if not fallback_name:
            logger.warning("🔄 Replan: sem fallback para '%s'", failed_name)
            return None

        fallback_specialist = self._registry.get_specialist_by_name(fallback_name)
        if not fallback_specialist or not fallback_specialist.agent_enabled:
            return None

        logger.info(
            "🔄 Replan: '%s' falhou, tentando '%s' como fallback",
            failed_name, fallback_name,
        )

        if self._emit_step:
            self._emit_step(self._environment_id, {
                "step": "replan",
                "type": "replan",
                "description": f"Replanejando: {failed_name} → {fallback_name}",
                "original": failed_name,
                "fallback": fallback_name,
            })

        # Adicionar contexto de falha para o agente fallback
        enriched_context = (
            f"{context_text}\n\n"
            f"## AVISO: Agente '{failed_name}' falhou\n"
            f"Erro: {failed_result.error or 'desconhecido'}\n"
            f"Voce e o agente fallback. Tente resolver com suas ferramentas disponiveis."
        )

        return self._run_agent(
            fallback_name, failed_step["task"], enriched_context,
        )

    # =================================================================
    # AGREGACAO DE RESULTADOS
    # =================================================================

    def _build_response(self, results, plan):
        """Agrega resultados de multiplos sub-agentes em resposta unificada."""
        all_tools = []
        all_steps = []
        texts = []
        has_failure = False
        has_escalation = False

        for result in results:
            all_tools.extend(result.tools_used)
            all_steps.extend(result.steps)

            if result.success and result.text:
                if len(results) > 1:
                    texts.append(f"### Agente: {result.specialist_name}\n{result.text}")
                else:
                    texts.append(result.text)
            elif not result.success:
                has_failure = True
                error_text = result.error or "Erro desconhecido"
                texts.append(
                    f"### Agente: {result.specialist_name} (FALHA)\n"
                    f"**Erro:** {error_text}"
                )
            if result.needs_escalation:
                has_escalation = True

        # Determinar status geral
        if all(r.success for r in results):
            status = "success"
        elif any(r.success for r in results):
            status = "partial"
        else:
            status = "failed"

        # Calcular tokens totais
        total_tokens = sum(
            r.token_usage.get("total_tokens", 0) for r in results
        )

        # Texto final
        if plan.pattern == "fan_out" and len(results) > 1:
            final_text = (
                f"**Orquestracao:** {len(results)} agentes em paralelo\n\n"
                + "\n\n---\n\n".join(texts)
            )
        elif plan.pattern == "chain" and len(results) > 1:
            final_text = (
                f"**Orquestracao:** cadeia de {len(results)} agentes\n\n"
                + "\n\n---\n\n".join(texts)
            )
        else:
            final_text = "\n\n".join(texts)

        if has_escalation:
            final_text += (
                "\n\n---\n*Um ou mais agentes solicitaram escalonamento. "
                "Verifique os detalhes acima.*"
            )

        return {
            "text": final_text,
            "status": status,
            "pattern": plan.pattern,
            "agents_used": [r.specialist_name for r in results],
            "tools_used": all_tools,
            "steps": all_steps,
            "total_tokens": total_tokens,
            "has_escalation": has_escalation,
            "agent_results": [r.to_dict() for r in results],
        }
