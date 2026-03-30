"""
BaseSpecialistAgent — Interface de sub-agente autonomo para o orquestrador GolIAs.

Cada specialist pode ser "promovido" a agente autonomo. Isso significa que ele:
- Tem seu proprio system prompt (identidade de especialista)
- Recebe um subset filtrado de tools
- Tem budget de tokens independente
- Executa de forma autonoma (pode chamar multiplas tools)
- Retorna resultado estruturado ao orquestrador

O orquestrador (AgentChatEngine) despacha para o SpecialistAgent quando
o specialist tem agent_prompt configurado. Caso contrario, usa o fluxo legado.
"""

import json
import logging
import os
import re

from app.services.agent_tools import execute_tool, format_tool_result_for_llm, get_available_tools
from app.services.agent_budget import TokenBudget
from app.services.agent_config import agent_config as cfg

logger = logging.getLogger(__name__)

# Cache de prompts de specialists carregados do disco
_SPECIALIST_PROMPTS_CACHE = {}


def _load_specialist_prompt(specialist_name):
    """Carrega o system prompt de um specialist do arquivo prompt/specialists/<name>.md"""
    if specialist_name in _SPECIALIST_PROMPTS_CACHE:
        return _SPECIALIST_PROMPTS_CACHE[specialist_name]

    # Tentar caminhos possiveis
    candidates = [
        os.path.join(os.path.dirname(__file__), "..", "..", "prompt", "specialists", f"{specialist_name}.md"),
    ]

    # PyInstaller
    base = getattr(__import__("sys"), "_MEIPASS", None)
    if base:
        candidates.insert(0, os.path.join(base, "prompt", "specialists", f"{specialist_name}.md"))

    for path in candidates:
        abs_path = os.path.abspath(path)
        if os.path.isfile(abs_path):
            try:
                with open(abs_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                _SPECIALIST_PROMPTS_CACHE[specialist_name] = content
                logger.info("📋 Prompt do specialist '%s' carregado: %d chars", specialist_name, len(content))
                return content
            except Exception as e:
                logger.warning("Erro ao ler prompt do specialist '%s': %s", specialist_name, e)

    _SPECIALIST_PROMPTS_CACHE[specialist_name] = None
    return None


def reload_specialist_prompts():
    """Limpa cache de prompts de specialists (para hot-reload)."""
    _SPECIALIST_PROMPTS_CACHE.clear()
    logger.info("🔄 Cache de prompts de specialists limpo")


class SpecialistAgentResult:
    """Resultado estruturado retornado por um SpecialistAgent ao orquestrador."""

    __slots__ = (
        "specialist_name", "success", "text", "tools_used",
        "token_usage", "error", "steps", "needs_escalation",
    )

    def __init__(self, specialist_name, success=True, text="", tools_used=None,
                 token_usage=None, error=None, steps=None, needs_escalation=False):
        self.specialist_name = specialist_name
        self.success = success
        self.text = text
        self.tools_used = tools_used or []
        self.token_usage = token_usage or {}
        self.error = error
        self.steps = steps or []
        self.needs_escalation = needs_escalation

    def to_dict(self):
        return {
            "specialist": self.specialist_name,
            "success": self.success,
            "text": self.text,
            "tools_used": self.tools_used,
            "token_usage": self.token_usage,
            "error": self.error,
            "steps": self.steps,
            "needs_escalation": self.needs_escalation,
        }


class BaseSpecialistAgent:
    """
    Agente especialista autonomo.

    Recebe uma tarefa do orquestrador, executa com seus tools e budget,
    e retorna um SpecialistAgentResult estruturado.

    O orquestrador pode:
    - Despachar para 1 agente (tarefa simples)
    - Despachar para N agentes (tarefas independentes)
    - Encadear agentes (output de A -> input de B)
    """

    # Maximo de iteracoes (tool calls) por execucao
    MAX_ITERATIONS = 5

    def __init__(self, specialist, llm_provider, user_profile="viewer",
                 environment_id=None, user_id=None):
        """
        Args:
            specialist: Specialist object (do registry)
            llm_provider: Provider LLM configurado
            user_profile: Perfil RBAC do usuario
            environment_id: ID do ambiente ativo
            user_id: ID do usuario
        """
        self.specialist = specialist
        self.name = specialist.name
        self._llm = llm_provider
        self._user_profile = user_profile
        self._environment_id = environment_id
        self._user_id = user_id

        # Budget proprio (menor que o global — sub-agente nao deve consumir tudo)
        max_tokens = getattr(specialist, "agent_budget", 15000)
        self._budget = TokenBudget(max_tokens=max_tokens)

        # Max iteracoes proprio
        self._max_iterations = getattr(specialist, "agent_max_iterations", self.MAX_ITERATIONS)

        # Tools filtradas para este specialist
        self._tools = self._load_tools()

        # System prompt proprio
        self._system_prompt = self._build_system_prompt()

    def _load_tools(self):
        """Carrega tools filtradas por specialist + RBAC."""
        all_tools = get_available_tools(self._user_profile)
        if not self.specialist.tools:
            return all_tools

        allowed = set(self.specialist.tools)
        return [t for t in all_tools if t["name"] in allowed]

    def _build_system_prompt(self):
        """Monta o system prompt do sub-agente."""
        # Tentar carregar prompt especifico do specialist
        specialist_prompt = _load_specialist_prompt(self.name)

        if specialist_prompt:
            prompt = specialist_prompt
        else:
            # Fallback: prompt generico com nome do specialist
            prompt = (
                f"Voce e um agente especialista em **{self.specialist.description or self.name}** "
                f"dentro da plataforma BiizHubOps.\n"
                f"Sua funcao e executar tarefas do dominio '{self.name}' de forma autonoma.\n"
            )

        # Adicionar tools disponiveis
        if self._tools:
            prompt += "\n\n## Ferramentas disponiveis\n"
            for tool in self._tools:
                params_list = [p["name"] for p in tool.get("parameters", [])]
                params_desc = f" ({', '.join(params_list)})" if params_list else ""
                prompt += f"- `{tool['name']}`{params_desc}: {tool['description']}\n"

        # Injetar environment_id real para evitar que o LLM invente
        if self._environment_id:
            prompt += (
                f"\n\n## Ambiente ativo\n"
                f"- **environment_id:** {self._environment_id} (use este valor EXATO em todas as ferramentas)\n"
                f"- NUNCA passe nomes como 'hml' ou 'prd' como environment_id — use SEMPRE o numero acima\n"
            )

        # Instrucoes de execucao
        prompt += (
            "\n\n## Protocolo de execucao\n"
            "1. Analise a tarefa recebida do orquestrador\n"
            "2. Execute UMA ferramenta por vez usando JSON: {\"tool\": \"nome\", \"params\": {...}}\n"
            "3. Valide o resultado antes de prosseguir\n"
            "4. Quando concluir, responda com texto (SEM tool call)\n"
            "5. Se nao conseguir resolver, indique que precisa de escalonamento\n\n"
            "## Formato de resposta final\n"
            "Responda de forma CURTA (3-5 linhas max). Diga O QUE encontrou. "
            "NAO diga 'Status:', 'Acao:', 'Resultado:', 'Proximo Passo:'. "
            "NAO liste proximos passos possiveis. NAO exponha IDs ou nomes de ferramentas. "
            "Se o usuario referenciou algo da conversa anterior ('esse', 'desse', 'o mesmo'), "
            "consulte o contexto para entender a referencia.\n"
        )

        return prompt

    def execute(self, task_description, context_text="", extra_context=""):
        """
        Executa a tarefa de forma autonoma.

        Args:
            task_description: O que o orquestrador quer que este agente faca
            context_text: Contexto do sistema (alertas, KB, etc)
            extra_context: Contexto extra (output de outro agente, etc)

        Returns:
            SpecialistAgentResult
        """
        if not self._llm:
            return SpecialistAgentResult(
                self.name, success=False,
                error="LLM nao configurado para este agente",
                needs_escalation=True,
            )

        tools_used = []
        steps = []

        # Montar system prompt completo
        system = self._system_prompt
        if context_text:
            system += f"\n\n## Contexto do sistema\n{context_text}"
        if extra_context:
            system += f"\n\n## Contexto adicional (de outro agente)\n{extra_context}"

        # Mensagens iniciais
        messages = [
            {"role": "user", "content": task_description},
        ]

        # Loop de execucao (ReAct simplificado)
        for iteration in range(self._max_iterations):
            if not self._budget.should_continue():
                logger.warning(
                    "🔴 Specialist '%s': budget esgotado na iteracao %d",
                    self.name, iteration,
                )
                steps.append({
                    "iteration": iteration,
                    "type": "budget_exceeded",
                    "detail": "Token budget esgotado",
                })
                break

            try:
                result = self._llm.chat(
                    messages=messages,
                    system_prompt=system,
                    temperature=0.3,
                    max_tokens=cfg.MAX_TOKENS_DEFAULT,
                )
            except Exception as e:
                logger.error("Specialist '%s' LLM error: %s", self.name, e)
                return SpecialistAgentResult(
                    self.name, success=False,
                    error=f"Erro LLM: {e}",
                    tools_used=tools_used,
                    steps=steps,
                    needs_escalation=True,
                )

            # Rastrear tokens
            prompt_tokens = result.get("prompt_tokens", 0) or self._budget.estimate_tokens(str(messages))
            completion_tokens = result.get("completion_tokens", 0) or self._budget.estimate_tokens(result.get("content", ""))
            self._budget.consume(prompt_tokens, completion_tokens, iteration)

            content = result.get("content", "").strip()

            # Tentar extrair tool call do response
            tool_call = self._extract_tool_call(content)

            if not tool_call:
                # Sem tool call = resposta final do agente
                # Proteger contra resposta vazia
                if not content and tools_used:
                    content = f"A consulta via `{tools_used[-1]}` foi executada, mas nao consegui formatar o resultado. Tente novamente."
                    logger.warning("⚠️ Specialist '%s': LLM retornou vazio, usando fallback", self.name)

                steps.append({
                    "iteration": iteration,
                    "type": "final_response",
                    "detail": content[:200],
                })
                return SpecialistAgentResult(
                    self.name,
                    success=bool(content),
                    text=content,
                    tools_used=tools_used,
                    token_usage=self._budget.get_summary(),
                    steps=steps,
                )

            # Executar tool
            tool_name = tool_call.get("tool", "")
            tool_params = tool_call.get("params", {})

            # Validar se a tool existe nas permitidas para este specialist
            allowed_names = {t["name"] for t in self._tools}
            if tool_name not in allowed_names:
                # LLM alucinhou nome de tool — tentar match parcial
                best_match = None
                for allowed in allowed_names:
                    if tool_name in allowed or allowed in tool_name:
                        best_match = allowed
                        break

                if best_match:
                    logger.warning(
                        "⚠️ Specialist '%s': LLM chamou tool inexistente '%s', corrigindo para '%s'",
                        self.name, tool_name, best_match,
                    )
                    tool_name = best_match
                else:
                    logger.warning(
                        "⚠️ Specialist '%s': LLM alucinhou tool '%s' (disponiveis: %s)",
                        self.name, tool_name, ", ".join(sorted(allowed_names)),
                    )
                    # Injetar erro e continuar o loop para o LLM se corrigir
                    messages.append({"role": "assistant", "content": content})
                    messages.append({
                        "role": "user",
                        "content": (
                            f"ERRO: A ferramenta '{tool_name}' nao existe. "
                            f"Ferramentas disponiveis: {', '.join(sorted(allowed_names))}. "
                            f"Escolha uma das ferramentas disponiveis ou responda diretamente."
                        ),
                    })
                    continue

            steps.append({
                "iteration": iteration,
                "type": "tool_call",
                "tool": tool_name,
                "params": tool_params,
            })

            logger.info(
                "🔧 Specialist '%s' [iter %d]: %s(%s)",
                self.name, iteration, tool_name, tool_params,
            )

            # Executar com RBAC e environment_id
            tool_result = execute_tool(
                tool_name,
                tool_params,
                user_profile=self._user_profile,
                environment_id=self._environment_id,
                user_id=self._user_id,
            )
            tools_used.append(tool_name)

            # Formatar resultado para o LLM
            tool_result_text = format_tool_result_for_llm(tool_name, tool_result)

            # Adicionar ao historico de mensagens
            messages.append({"role": "assistant", "content": content})
            messages.append({
                "role": "user",
                "content": (
                    f"Resultado da ferramenta {tool_name}:\n"
                    f"<tool_data>\n{tool_result_text}\n</tool_data>\n\n"
                    f"Analise o resultado e decida: executar outra ferramenta ou responder ao orquestrador.\n"
                    f"Se responder, use o formato padrao: Status/Acao/Resultado/Proximo Passo."
                ),
            })

            steps[-1]["success"] = tool_result.get("success", False)
            steps[-1]["result_preview"] = tool_result_text[:100]

        # Se esgotou iteracoes sem resposta final
        last_content = messages[-1]["content"] if messages else ""
        return SpecialistAgentResult(
            self.name,
            success=False,
            text=f"Agente '{self.name}' atingiu limite de {self._max_iterations} iteracoes sem conclusao.",
            tools_used=tools_used,
            token_usage=self._budget.get_summary(),
            steps=steps,
            needs_escalation=True,
        )

    def _extract_tool_call(self, content):
        """Extrai tool call JSON do conteudo da resposta LLM."""
        # Tentar extrair de code block
        match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(1))
                if "tool" in parsed:
                    return parsed
            except json.JSONDecodeError:
                pass

        # Tentar extrair JSON inline
        match = re.search(r'\{\s*"tool"\s*:\s*"[^"]+"\s*,\s*"params"\s*:', content)
        if match:
            # Encontrar o JSON completo
            start = match.start()
            brace_count = 0
            for i in range(start, len(content)):
                if content[i] == "{":
                    brace_count += 1
                elif content[i] == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        try:
                            parsed = json.loads(content[start:i + 1])
                            if "tool" in parsed:
                                return parsed
                        except json.JSONDecodeError:
                            pass
                        break

        return None

    def get_status(self):
        """Retorna status atual do agente (para monitoramento)."""
        return {
            "name": self.name,
            "description": self.specialist.description,
            "tools_count": len(self._tools),
            "budget": self._budget.get_summary(),
            "max_iterations": self._max_iterations,
            "has_custom_prompt": _load_specialist_prompt(self.name) is not None,
        }
