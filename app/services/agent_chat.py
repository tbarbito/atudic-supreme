"""
Motor do GolIAs — Agente Inteligente do AtuDIC.

Dois modos de operação:
1. Rule-based: pattern matching + BM25 + consultas PostgreSQL (sem LLM)
2. LLM-augmented: coleta contexto (BM25 + KB + alertas) e envia para LLM

O contexto coletado é o mesmo em ambos os modos — a diferença é quem
compõe a resposta final (templates vs LLM).
"""

import os
import re
import json
import logging

# Módulos extraídos para tools/
from app.services.tools.parser import parse_tool_call, looks_like_plan_not_action
from app.services.tools.prompt_loader import (
    load_system_prompt as _load_system_prompt,
    reload_system_prompt,
)

from app.services.agent_memory import get_agent_memory
from app.services.agent_tools import get_available_tools, execute_tool, AGENT_TOOLS, format_tool_result_for_llm
from app.services.agent_skills import get_skill_registry
from app.services.agent_specialists import get_specialist_registry
from app.services.agent_config import agent_config as cfg
from app.services.agent_intent import (
    detect_intent,
    extract_entities,
    classify_complexity,
    user_skips_confirmation,
)
from app.services.agent_context import ContextBuilder
from app.services.agent_composer import ResponseComposer
from app.services.agent_history import HistoryManager
from app.services.agent_chains import get_chain_registry, get_chain_executor
from app.services.agent_planner import TaskPlanner, PlanExecutor, needs_planning
from app.services.agent_working_memory import get_working_memory

logger = logging.getLogger(__name__)

# System prompt — carregado de tools/prompt_loader.py (com cache)
# _load_system_prompt e reload_system_prompt importados no topo


# =====================================================================
# INTENTS, ENTITIES, COMPLEXIDADE — delegados para agent_intent.py
# =====================================================================
# Aliases locais para retrocompatibilidade interna
_user_skips_confirmation = user_skips_confirmation
_classify_complexity = classify_complexity


def _get_specialist_for_intent(intent):
    """Retorna o Specialist para o intent detectado (via YAML registry)."""
    return get_specialist_registry().get_specialist_for_intent(intent)


class AgentChatEngine:
    """Motor do agente inteligente (rule-based + LLM)."""

    def __init__(self):
        self.memory = get_agent_memory()
        self._llm_provider = None
        # Componentes decompostos
        self._context_builder = ContextBuilder(self.memory)
        self._composer = ResponseComposer()
        self._history = HistoryManager(self.memory)

    def set_llm_provider(self, provider):
        """Define o provider LLM ativo (ou None para rule-based puro)."""
        self._llm_provider = provider
        self._history.set_llm_provider(provider)
        self._context_builder.set_llm_provider(provider)

    def get_active_mode(self):
        """Retorna o modo ativo: 'llm' ou 'rule-based'."""
        return "llm" if self._llm_provider else "rule-based"

    def _emit_agent_step(self, environment_id, step_data):
        """Emite step do agente via EventManager (SSE para o frontend)."""
        try:
            from app.services.events import event_manager

            event_manager.broadcast(
                json.dumps(
                    {
                        "type": "agent_step",
                        "environment_id": environment_id,
                        "data": step_data,
                    }
                )
            )
        except Exception as e:
            logger.debug("Erro ao emitir agent_step: %s", e)

    # =================================================================
    # EXECUCAO DIRETA DE ACAO CONFIRMADA (sem LLM)
    # =================================================================

    def _check_auto_execute_preview(self, message, session_id, environment_id, user_info):
        """Se a ultima tool foi preview_equalization/preview_ingestion e usuario confirma, executa.

        Resolve o problema do LLM inventar sucesso sem chamar execute.
        Detecta confirmacao via palavras-chave simples.
        """
        import re
        _CONFIRM_PATTERN = re.compile(
            r"^\s*(sim|s|ok|pode|aplica|confirma|confirmo|manda|vai|yes|y|go|approve)\s*[!.?]?\s*$",
            re.IGNORECASE,
        )
        if not _CONFIRM_PATTERN.match(message.strip()):
            return None

        # Verificar se ultima tool call na sessao foi um preview
        wm = get_working_memory()
        pad = wm._sessions.get(session_id)
        if not pad or not pad.get("tool_call_history"):
            return None

        last_call = pad["tool_call_history"][-1]
        last_tool = last_call.get("tool", "")
        last_params = last_call.get("params", {})

        # Mapear preview → execute
        _PREVIEW_TO_EXECUTE = {
            "preview_equalization": "execute_equalization",
            "preview_ingestion": "execute_ingestion",
        }

        execute_tool_name = _PREVIEW_TO_EXECUTE.get(last_tool)
        if not execute_tool_name:
            return None

        # Verificar se tem confirmation_token no resultado do preview
        # O token esta nos tool_results (summary)
        token = last_params.get("confirmation_token")
        if not token:
            # Buscar nos tool_results
            for tr in reversed(pad.get("tool_results", [])):
                if "confirmation_token" in tr.get("summary", ""):
                    # Extrair token do summary (formato: ...token: abc123...)
                    import re as _re
                    match = _re.search(r'"confirmation_token"\s*:\s*"([^"]+)"', tr["summary"])
                    if match:
                        token = match.group(1)
                        break

        if not token:
            logger.info("Auto-execute: preview encontrado mas sem confirmation_token no historico")
            return None

        logger.info("Auto-execute: usuario confirmou '%s' → executando %s com token", message.strip(), execute_tool_name)

        # Montar params do execute a partir do preview
        execute_params = dict(last_params)
        execute_params["confirmation_token"] = token
        execute_params["confirmed"] = True

        user_profile = (user_info or {}).get("profile", "viewer")
        user_id = (user_info or {}).get("user_id")

        tool_result = execute_tool(
            execute_tool_name,
            execute_params,
            user_profile=user_profile,
            environment_id=environment_id,
            user_id=user_id,
            session_id=session_id,
        )

        # Formatar resposta
        success = tool_result.get("success", False)
        data = tool_result.get("data", {})

        if success and isinstance(data, dict) and data.get("success"):
            executed = data.get("executed", 0)
            status = data.get("status", "success")
            duration = data.get("duration_ms", 0)
            text = (
                f"Equalizacao executada com sucesso.\n\n"
                f"- **Statements executados:** {executed}\n"
                f"- **Status:** {status}\n"
                f"- **Duracao:** {duration}ms"
            )
            if data.get("tcrefresh", {}).get("called"):
                text += f"\n- **TcRefresh:** {'OK' if data['tcrefresh'].get('success') else 'Falhou (DDL/DML OK, cache pode precisar de restart)'}"
        else:
            error = data.get("error", "") if isinstance(data, dict) else tool_result.get("error", "Erro desconhecido")
            text = f"Equalizacao falhou: {error}"

        # Salvar no historico
        self._history.save_messages(
            session_id, environment_id, message,
            "dictionary_analysis", 1.0, text
        )

        return {
            "intent": "dictionary_analysis",
            "confidence": 1.0,
            "text": text,
            "sections": [],
            "links": [],
            "sources_consulted": [execute_tool_name],
            "entities": {},
            "mode": "auto-execute",
            "tools_used": [execute_tool_name],
        }

    def execute_confirmed_action(self, pending_action, session_id, environment_id=None, user_info=None):
        """Executa acao confirmada pelo usuario sem passar pelo LLM.

        Quando o usuario confirma uma acao pendente (sim/pode/manda), o frontend
        envia o pending_action diretamente. Isso evita que modelos menores
        (Gemini Flash, Ollama) se percam tentando re-gerar o tool call.
        """
        tool_name = pending_action.get("tool", "")
        tool_params = pending_action.get("params", {})
        tool_params["confirmed"] = True  # Marcar como confirmado

        user_profile = (user_info or {}).get("profile", "viewer")
        user_id = (user_info or {}).get("user_id")
        env_id = environment_id or (user_info or {}).get("environment_id")

        if env_id and "environment_id" not in tool_params:
            tool_params["environment_id"] = env_id

        logger.info("🔧 Acao confirmada pelo usuario: %s(%s)", tool_name, tool_params)

        # Executar a ferramenta diretamente
        tool_result = execute_tool(
            tool_name,
            tool_params,
            user_profile=user_profile,
            environment_id=env_id,
            user_id=user_id,
            session_id=session_id,
        )

        tools_used = [tool_name]

        # Se tem LLM, pedir pra formatar a resposta
        if self._llm_provider:
            try:
                result_text = format_tool_result_for_llm(tool_name, tool_result)

                user_ctx = ContextBuilder.build_user_context(user_info)
                system = _load_system_prompt().replace("{user_context}", user_ctx).replace("{context}", "")

                # LLM formata a resposta usando os dados reais
                messages = [
                    {
                        "role": "user",
                        "content": (
                            f"O usuario confirmou a execucao da ferramenta '{tool_name}'. "
                            f"Dados retornados (EXATOS — use somente estes):\n"
                            f"<tool_data>\n{result_text}\n</tool_data>\n\n"
                            f"Responda de forma CURTA e direta (3-5 linhas max). "
                            f"Diga O QUE encontrou, NAO como consultou. "
                            f"NAO diga 'Status:', 'Acao:', 'Resultado:'. NAO liste proximos passos. "
                            f"COPIE valores EXATAMENTE como estao em <tool_data>. "
                            f"NAO invente dados. NAO use TOOL_CALL."
                        ),
                    }
                ]

                llm_result = self._llm_provider.chat(
                    messages=messages,
                    system_prompt=system,
                    temperature=0.1,
                    max_tokens=1024,
                )
                response_text = llm_result.get("content", "").strip()
                # Limpar tool calls residuais
                response_text = re.sub(r'```json\s*\{["\']tool["\'].*?```', "", response_text, flags=re.DOTALL).strip()

            except Exception as e:
                logger.warning("Erro ao formatar resultado via LLM: %s", e)
                response_text = self._format_tool_result_simple(tool_name, tool_result)
        else:
            response_text = self._format_tool_result_simple(tool_name, tool_result)

        response = {
            "intent": "tool_execution",
            "confidence": 1.0,
            "text": response_text,
            "sections": [],
            "links": [],
            "sources_consulted": [f"TOOL:{tool_name}"],
            "entities": {},
            "mode": "confirmed_action",
            "tools_used": tools_used,
        }

        # Persistir mensagens
        self._history.save_messages(session_id, environment_id, f"[Confirmado: {tool_name}]", "tool_execution", 1.0, response)

        return response

    def _format_tool_result_simple(self, tool_name, result):
        """Formata resultado de tool sem LLM (fallback).

        Usa format_tool_result_for_llm para formatação inteligente,
        evitando JSON bruto truncado que pode causar alucinação.
        """
        if isinstance(result, dict) and result.get("error"):
            return f"Erro ao executar {tool_name}: {result['error']}"

        formatted = format_tool_result_for_llm(tool_name, result)
        return f"**{tool_name}** executado com sucesso.\n\n{formatted}"

    # =================================================================
    # PROCESSAMENTO DE MENSAGEM
    # =================================================================

    def process_message(self, message, session_id, environment_id=None, user_info=None, attachments=None):
        """Processa mensagem do usuário e retorna resposta estruturada.

        Args:
            message: texto do usuário
            session_id: ID da sessão
            environment_id: ID do ambiente ativo
            user_info: dict com info do usuário
            attachments: lista de anexos [{type, name, content, mime_type}]
        """
        # 0. Auto-execute: se ultima tool foi preview e usuario confirma, executar direto
        auto_result = self._check_auto_execute_preview(message, session_id, environment_id, user_info)
        if auto_result:
            return auto_result

        # 1. Detectar intenção
        intent, confidence = self._detect_intent(message)

        # 2. Extrair entidades
        entities = self._extract_entities(message)

        # 2b. Registrar entidades na working memory
        wm = get_working_memory()
        wm.add_entities_from_extracted(session_id, entities)

        # 3. Consultar fontes relevantes
        context = self._context_builder.gather_context(intent, message, entities, environment_id)
        # Salvar user_info no contexto para o rule-based acessar
        context["_user_info"] = user_info or {}

        # 4. Processar attachments (texto dos arquivos injetado na mensagem)
        attachment_text = self._process_attachments(attachments or [])
        if attachment_text:
            message = message + "\n\n" + attachment_text

        # 5. Compor resposta — mode selector: orquestrador, sub-agente, plan-execute, react, two-step ou rule-based
        if self._llm_provider:
            # Guard de modelo: sub-agentes so ativam em modelos capazes de multi-turn tool calling
            # Gemini Flash, modelos pequenos e locais usam fluxo legado (two-step) que ja funciona
            provider_id = getattr(self._llm_provider, "provider_id", "")
            model_id = getattr(self._llm_provider, "model_id", "")
            _capable_for_agent = self._is_model_capable_for_agent(provider_id, model_id)

            specialist = _get_specialist_for_intent(intent)
            response = None

            # Fase 3: Tentar orquestracao multi-agente (so modelos capazes)
            if _capable_for_agent:
                orch_response = self._try_orchestrate(
                    message, intent, confidence, entities, context,
                    session_id, environment_id, user_info,
                )
                if orch_response is not None:
                    response = orch_response

            # Fase 2: Dispatch single-agent (so modelos capazes)
            if response is None and _capable_for_agent:
                if specialist and getattr(specialist, "agent_enabled", False) and specialist.name != "general":
                    agent_response = self._try_dispatch_to_agent(
                        specialist, message, intent, confidence, entities, context,
                        session_id, environment_id, user_info,
                    )
                    # Fallback agressivo: se sub-agente retornou texto vazio, ignorar e usar legacy
                    if agent_response is not None and (agent_response.get("text") or "").strip():
                        response = agent_response
                    elif agent_response is not None:
                        logger.warning(
                            "⚠️ Sub-agente '%s' retornou texto vazio, fallback para legacy",
                            specialist.name,
                        )

            # Fallback: fluxo legado (two-step/react/plan-execute)
            if response is None:
                response = self._fallback_legacy_mode(
                    message, intent, confidence, entities, context,
                    session_id, environment_id, user_info, attachments,
                )
        else:
            response = self._composer.compose_response(intent, confidence, message, entities, context)

        # 6. Persistir mensagens
        self._history.save_messages(session_id, environment_id, message, intent, confidence, response)

        # 7. Registrar consumo de tokens no audit_log (para conta-giro)
        self._log_token_usage(response, session_id, environment_id, user_info)

        return response

    def _log_token_usage(self, response, session_id, environment_id, user_info):
        """Grava consumo de tokens no agent_audit_log para metricas."""
        try:
            if not isinstance(response, dict):
                return

            # token_usage (react) ou llm_usage (two-step) — verificar ambos
            token_usage = response.get("token_usage") or {}
            llm_usage = response.get("llm_usage") or {}

            total_tokens = (
                token_usage.get("total_tokens", 0)
                or (llm_usage.get("prompt_tokens", 0) + llm_usage.get("completion_tokens", 0))
                or llm_usage.get("input_tokens", 0) + llm_usage.get("output_tokens", 0)
            )
            if not total_tokens:
                return
            if total_tokens <= 0:
                return

            provider = response.get("llm_provider", "")
            model = response.get("llm_model", "")

            # Extrair input/output separados para custo preciso
            prompt_tokens = (
                token_usage.get("prompt_tokens", 0)
                or llm_usage.get("prompt_tokens", 0)
                or llm_usage.get("input_tokens", 0)
            )
            completion_tokens = (
                token_usage.get("completion_tokens", 0)
                or llm_usage.get("completion_tokens", 0)
                or llm_usage.get("output_tokens", 0)
            )

            from app.database import get_db, release_db_connection
            conn = get_db()
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO agent_audit_log
                    (user_id, username, environment_id, session_id, action, params, result_status, tokens_used, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                """, (
                    (user_info or {}).get("user_id"),
                    (user_info or {}).get("username", ""),
                    environment_id,
                    session_id,
                    "llm_chat",
                    json.dumps({
                        "provider": provider, "model": model,
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                    }, ensure_ascii=False)[:500],
                    "success",
                    total_tokens,
                ))
                conn.commit()
            except Exception:
                conn.rollback()
            finally:
                release_db_connection(conn)
        except Exception:
            pass  # Nao bloquear resposta por falha de metricas

    # =================================================================
    # RESPOSTA VIA LLM
    # =================================================================

    def _compose_response_llm(
        self, intent, confidence, message, entities, context, session_id, user_info=None, attachments=None
    ):
        """Compõe resposta usando LLM com contexto coletado + tool calling."""
        from app.services.llm_providers import LLMError

        # Montar contexto do usuário
        user_ctx = ContextBuilder.build_user_context(user_info)
        user_profile = (user_info or {}).get("profile", "viewer")
        user_id = (user_info or {}).get("user_id")
        env_id = (user_info or {}).get("environment_id")
        if not env_id:
            # Fallback: extrair do contexto de ambientes
            for env in context.get("environments", []):
                if env.get("name") == (user_info or {}).get("environment_name"):
                    env_id = env.get("id")
                    break

        # [19B] Verificar se há chain que matcha a mensagem
        chain_result = None
        chain = get_chain_registry().match_chain(message)
        if chain:
            chain_result = get_chain_executor().execute(
                chain, message, user_profile=user_profile,
                environment_id=env_id, user_id=user_id,
            )
            if chain_result and chain_result.get("results"):
                # Injetar resultados da chain no contexto
                context["_chain_result"] = chain_result
                logger.info(
                    "⛓️ Chain '%s': %d/%d steps OK",
                    chain.name, chain_result["successful_steps"], chain_result["total_steps"],
                )

        # Montar contexto textual para o system prompt
        context_text = ContextBuilder.build_context_text(intent, entities, context)
        system_template = _load_system_prompt()
        system = system_template.replace("{user_context}", user_ctx).replace("{context}", context_text)

        # Injetar working memory da sessão (20D)
        wm_text = get_working_memory().to_prompt(session_id)
        if wm_text:
            system += wm_text

        # Determinar specialist mode baseado no intent (via YAML registry)
        specialist = _get_specialist_for_intent(intent)
        specialist_name = specialist.name if specialist else "general"

        # Carregar skills relevantes para specialist + intent + mensagem
        skill_registry = get_skill_registry()
        active_skills = skill_registry.get_skills_for_specialist(specialist_name, intent, message)
        if active_skills:
            system += skill_registry.format_skills_prompt(active_skills)
            logger.info("📚 Specialist: %s | Skills ativas: %s", specialist_name, [s.name for s in active_skills])

        # Adicionar ferramentas disponiveis ao system prompt — filtradas pelo specialist
        all_tools = get_available_tools(user_profile)
        if all_tools and specialist:
            allowed_tool_names = get_specialist_registry().get_tool_names_for_specialist(specialist)
            if allowed_tool_names:
                # Filtrar tools: apenas as do specialist (filtragem no chat engine, NAO no registry)
                tools = [t for t in all_tools if t["name"] in allowed_tool_names]
            else:
                # Specialist sem tools definidas = todas disponiveis
                tools = all_tools
        else:
            tools = all_tools

        if tools:
            system += self._build_tools_prompt(tools)
            logger.info("🔧 Tools filtradas: %d/%d para specialist %s", len(tools), len(all_tools), specialist_name)

        # Carregar historico recente com sumarizacao das mensagens antigas
        raw_history = self._history.get_recent_history(session_id, limit=cfg.HISTORY_LIMIT_TWOSTEOP)
        chat_history = self._history.build_history_with_summary(session_id, raw_history)

        # Instrucao anti-repeticao (critico para modelos menores)
        if chat_history:
            system += (
                "\n\n## REGRA ANTI-REPETICAO (OBRIGATORIO)"
                "\n- NAO repita informacoes de mensagens anteriores"
                "\n- Responda APENAS a ultima mensagem do usuario"
                "\n- NAO mencione o conteudo de perguntas/respostas passadas"
                "\n- Se o usuario perguntou algo novo, responda SOMENTE sobre o tema novo"
                "\n- Va direto ao ponto, sem saudacao"
            )

        # [9K-T4] Classificar complexidade e injetar planning prompt com priorizacao
        complexity = _classify_complexity(message)
        if complexity == "complex":
            system += (
                "\n\n## TAREFA COMPLEXA DETECTADA\n"
                "A mensagem requer multiplos passos. Siga o protocolo:\n"
                "1. CLASSIFIQUE a prioridade: CRITICA (producao fora) > ALTA (bloqueio) > NORMAL > BAIXA\n"
                "2. Liste os passos necessarios (max 5), indicando dependencias\n"
                "3. Para cada passo, indique qual ferramenta usar\n"
                "4. Identifique o que pode rodar em paralelo vs sequencial\n"
                "5. Execute o primeiro passo agora\n"
                "6. Se um passo falhar, REPLANEJE os passos seguintes em vez de abortar"
            )
            logger.info("📋 Tarefa complexa detectada — planning prompt v2.0 injetado")

        # Montar mensagens para o LLM — historico com truncamento por role
        messages = []
        for msg in chat_history:
            content = msg["content"]
            if msg["role"] == "assistant":
                # Truncar respostas do assistente agressivamente — so manter o essencial
                # para continuidade (qual conexao usou, etc), nao a resposta completa
                if len(content) > cfg.ASSISTANT_MSG_TRUNCATE:
                    content = content[:cfg.ASSISTANT_MSG_TRUNCATE] + "..."
            elif msg["role"] == "user" and len(content) > cfg.USER_MSG_TRUNCATE:
                content = content[:cfg.USER_MSG_TRUNCATE] + "..."
            messages.append({"role": msg["role"], "content": content})

        # Injetar lembrete anti-repeticao no fluxo de mensagens (mais efetivo que so system prompt)
        # Modelos como Gemini ignoram instrucoes no system quando o historico tem conteudo rico
        if chat_history:
            messages.append({
                "role": "user",
                "content": "Lembrete: responda apenas a proxima pergunta, sem resumir ou repetir respostas anteriores.",
            })
            messages.append({
                "role": "assistant",
                "content": "Entendido. Vou responder apenas o que for perguntado agora.",
            })

        # Montar mensagem do usuário (com suporte a imagem se provider tem vision)
        image_attachments = [a for a in (attachments or []) if a.get("type") == "image"]
        has_vision = getattr(self._llm_provider, "supports_vision", False)

        if image_attachments and has_vision:
            # Mensagem multimodal (texto + imagem)
            user_content = [{"type": "text", "text": message}]
            for img in image_attachments:
                mime = img.get("mime_type", "image/png")
                user_content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{img['content']}"}})
            messages.append({"role": "user", "content": user_content})
        elif image_attachments and not has_vision:
            # Provider sem vision — avisar na mensagem
            msg_with_warning = (
                message
                + "\n\n⚠️ [Imagens foram anexadas, mas o modelo atual não suporta análise de imagens. Troque para um provider com suporte a vision (OpenAI, Claude, Gemini, Grok) para análise visual.]"
            )
            messages.append({"role": "user", "content": msg_with_warning})
        else:
            messages.append({"role": "user", "content": message})

        # Log do tamanho do prompt para diagnostico
        total_msg_chars = sum(len(str(m.get("content", ""))) for m in messages)
        logger.info(
            "🤖 LLM call: system=%d chars, messages=%d (%d chars), specialist=%s",
            len(system),
            len(messages),
            total_msg_chars,
            specialist_name,
        )

        # SSE: indicar que o agente está processando (two-step)
        self._emit_agent_step(env_id, {
            "step": "thinking",
            "type": "thinking",
            "description": "Analisando mensagem...",
            "specialist": specialist_name,
        })

        try:
            # Temperatura adaptada por provider (Gemini Flash precisa de temp baixa para tool calling)
            temperature = cfg.TEMPERATURE_DEFAULT
            provider_id = getattr(self._llm_provider, "provider_id", "")
            if provider_id == "gemini":
                temperature = 0.4

            result = self._llm_provider.chat(
                messages=messages,
                system_prompt=system,
                temperature=temperature,
                max_tokens=cfg.MAX_TOKENS_DEFAULT,
            )

            response_text = result["content"]
            tools_used = []

            # Detectar tool calls na resposta do LLM
            tool_call = self._parse_tool_call(response_text)

            # Retry: se LLM respondeu com plano/lista em vez de executar, forçar tool call
            if not tool_call and tools and self._looks_like_plan_not_action(response_text):
                logger.info("🔄 LLM respondeu com plano, forçando re-tentativa com tool call")
                retry_messages = list(messages)
                retry_messages.append({"role": "assistant", "content": response_text})
                retry_messages.append({
                    "role": "user",
                    "content": (
                        "EXECUTE agora. Responda APENAS com o JSON da ferramenta, sem texto:\n"
                        '```json\n{"tool": "nome", "params": {...}}\n```'
                    ),
                })
                retry_result = self._llm_provider.chat(
                    messages=retry_messages,
                    system_prompt=system,
                    temperature=0.2,
                    max_tokens=cfg.MAX_TOKENS_DEFAULT,
                )
                retry_tool = self._parse_tool_call(retry_result["content"])
                if retry_tool:
                    tool_call = retry_tool
                    response_text = retry_result["content"]
                    result = retry_result
            if tool_call:
                tool_name = tool_call["tool"]
                tool_params = tool_call.get("params", {})

                logger.info("🔧 Tool call detectado: %s(%s)", tool_name, tool_params)
                tools_used.append(tool_name)

                # SSE: indicar tool call no two-step
                self._emit_agent_step(env_id, {
                    "step": "tool_call",
                    "type": "tool_call",
                    "tool": tool_name,
                    "description": f"Consultando {tool_name}...",
                })

                # Verificar se e acao que requer confirmacao
                # query_database e compare_dictionary sao leitura (SELECT only) — nao pedem confirmacao
                needs_confirm = AGENT_TOOLS.get(tool_name, {}).get("requires_confirmation", False)
                confirmed = tool_call.get("params", {}).get("confirmed", False)

                # Detectar se o usuario ja autorizou na propria mensagem
                if needs_confirm and not confirmed:
                    skip_confirm = _user_skips_confirmation(message)
                    if skip_confirm:
                        confirmed = True
                        tool_params["confirmed"] = True

                if needs_confirm and not confirmed:
                    # Retornar pedido de confirmacao em vez de executar
                    return self._build_confirmation_response(
                        intent, confidence, tool_name, tool_params, entities, context
                    )

                # Executar a ferramenta (passa user_id, env_id e session_id para inferencia)
                tool_result = execute_tool(
                    tool_name,
                    tool_params,
                    user_profile=user_profile,
                    environment_id=env_id,
                    user_id=user_id,
                    session_id=session_id,
                )

                # Registrar resultado na working memory (20D)
                wm = get_working_memory()
                result_summary = json.dumps(tool_result.get("data", tool_result), ensure_ascii=False, default=str)[:200]
                wm.add_tool_result(session_id, tool_name, result_summary)

                # LLM formata a resposta usando os dados reais
                tool_result_text = format_tool_result_for_llm(tool_name, tool_result)

                messages.append({"role": "assistant", "content": f"[Executando ferramenta: {tool_name}]"})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"Resultado da ferramenta {tool_name}. "
                            f"Dados retornados (EXATOS — use somente estes):\n"
                            f"<tool_data>\n{tool_result_text}\n</tool_data>\n\n"
                            f"Responda de forma CURTA e direta (3-5 linhas max para respostas simples). "
                            f"Diga O QUE encontrou, NAO como consultou. "
                            f"NAO diga 'Status:', 'Acao:', 'Resultado:', 'Proximo Passo:'. "
                            f"NAO liste 'proximos passos possiveis'. NAO exponha IDs internos ou nomes de ferramentas. "
                            f"COPIE nomes e valores EXATAMENTE como estao em <tool_data>. "
                            f"NAO invente dados. NAO use TOOL_CALL."
                        ),
                    }
                )

                # SSE: indicar composição da resposta final
                self._emit_agent_step(env_id, {
                    "step": "composing",
                    "type": "composing",
                    "description": "Compondo resposta...",
                })

                result = self._llm_provider.chat(
                    messages=messages,
                    system_prompt=system,
                    temperature=0.1,
                    max_tokens=cfg.MAX_TOKENS_DEFAULT,
                )
                response_text = result["content"]

                # Limpar qualquer TOOL_CALL residual (code blocks e JSON inline)
                response_text = re.sub(r'```json\s*\{["\']tool["\'].*?```', "", response_text, flags=re.DOTALL)
                response_text = re.sub(r'\{["\']tool["\']\s*:\s*["\'][^"\']+["\'].*?\}', "", response_text, flags=re.DOTALL)
                response_text = re.sub(r'(?i)(PLANO|PLAN)\s*:', "", response_text)
                response_text = response_text.strip()

            # Proteger contra resposta vazia — fallback com dados crus da tool
            if not response_text and tools_used:
                logger.warning("⚠️ LLM retornou resposta vazia apos tool call, usando fallback")
                response_text = f"Executei a consulta via `{tools_used[-1]}`. Dados retornados:"
                try:
                    if tool_result_text:
                        response_text += f"\n\n{tool_result_text}"
                except NameError:
                    response_text += "\n\n(Sem dados para exibir)"

            # Montar seções do contexto (para exibir no frontend)
            sections = ResponseComposer.build_sections_from_context(context)
            links = ResponseComposer.build_links_from_context(context)
            sources = ResponseComposer.list_sources(context)
            if tools_used:
                sources.extend([f"TOOL:{t}" for t in tools_used])

            # [9K-T6] Feedback loop de intent detection
            HistoryManager.log_intent_feedback(intent, specialist_name, tools_used)

            return {
                "intent": intent,
                "confidence": round(confidence, 2),
                "text": response_text,
                "sections": sections,
                "links": links,
                "sources_consulted": sources,
                "entities": entities,
                "mode": "llm",
                "tools_used": tools_used,
                "skills_active": [s.name for s in active_skills],
                "llm_model": result.get("model", ""),
                "llm_provider": result.get("provider", ""),
                "llm_usage": result.get("usage", {}),
            }

        except LLMError as e:
            logger.warning("Erro LLM (%s), fallback para rule-based: %s", e.code, e)
            response = self._composer.compose_response(intent, confidence, message, entities, context)
            response["mode"] = "rule-based (fallback)"
            response["llm_error"] = str(e)
            return response
        except Exception as e:
            logger.error("Erro inesperado no LLM, fallback para rule-based: %s", e, exc_info=True)
            response = self._composer.compose_response(intent, confidence, message, entities, context)
            response["mode"] = "rule-based (fallback)"
            response["llm_error"] = str(e)
            return response

    # =================================================================
    # GUARD DE MODELO PARA SUB-AGENTES
    # =================================================================

    @staticmethod
    def _is_model_capable_for_agent(provider_id, model_id):
        """Verifica se o modelo e capaz de executar o fluxo multi-turn de sub-agente.

        Modelos capazes: Claude (Sonnet/Opus), GPT-4o, GPT-4-turbo, DeepSeek-V3.
        Modelos incapazes: Gemini Flash, modelos pequenos, ollama local.
        O fluxo two-step (legado) ja funciona bem para todos.
        """
        provider_lower = (provider_id or "").lower()
        model_lower = (model_id or "").lower()

        # Providers que suportam multi-turn tool calling robusto
        if provider_lower == "anthropic":
            return True
        if provider_lower == "openai" and ("gpt-4" in model_lower or "o1" in model_lower or "o3" in model_lower):
            return True
        if provider_lower == "deepseek":
            return True

        # Gemini Flash e modelos pequenos — two-step funciona, sub-agente nao
        if provider_lower in ("gemini", "ollama", "groq", "together"):
            return False

        # OpenRouter: depende do modelo roteado
        if provider_lower == "openrouter":
            if "claude" in model_lower or "gpt-4" in model_lower:
                return True
            return False

        # Default: conservador, usar legacy
        return False

    # =================================================================
    # FALLBACK PARA MODO LEGADO
    # =================================================================

    def _fallback_legacy_mode(self, message, intent, confidence, entities, context,
                              session_id, environment_id, user_info, attachments):
        """Executa no modo legado: plan-execute, react ou two-step."""
        mode = self._select_mode(message, intent, confidence, environment_id)
        if mode == "plan":
            return self._plan_and_execute(
                message, intent, confidence, entities, context, session_id, user_info
            )
        elif mode == "react":
            return self._react_loop(
                message, intent, confidence, entities, context,
                session_id, environment_id, user_info, attachments=attachments,
            )
        else:
            return self._compose_response_llm(
                intent, confidence, message, entities, context,
                session_id, user_info, attachments=attachments,
            )

    # =================================================================
    # ORQUESTRACAO MULTI-AGENTE (Fase 3)
    # =================================================================

    def _try_orchestrate(self, message, intent, confidence, entities, context,
                         session_id, environment_id, user_info):
        """Tenta orquestracao multi-agente (fan-out ou chain).

        Retorna dict de resposta se orquestrado, ou None para tentar dispatch simples.
        So ativa quando detecta multiplos dominios na mensagem.
        """
        try:
            from app.services.agent_orchestrator import AgentOrchestrator

            user_profile = (user_info or {}).get("profile", "viewer")
            user_id = (user_info or {}).get("user_id")
            env_id = environment_id or (user_info or {}).get("environment_id")

            orchestrator = AgentOrchestrator(
                llm_provider=self._llm_provider,
                user_profile=user_profile,
                environment_id=env_id,
                user_id=user_id,
                user_info=user_info,
                emit_step_fn=self._emit_agent_step,
            )

            # Analisar tarefa — so retorna plano se detectar multi-dominio
            plan = orchestrator.analyze_task(message, intent, entities)

            if plan is None or plan.pattern == "single":
                return None  # Single-agent ou sem plano, usar dispatch da Fase 2

            # Multi-agente detectado (fan_out ou chain)
            logger.info("🎯 Orquestracao multi-agente ativada: %s", plan.to_display())

            context_text = ContextBuilder.build_context_text(intent, entities, context)
            orch_result = orchestrator.execute(plan, context_text)

            # Montar resposta no formato padrao do chat engine
            sections = ResponseComposer.build_sections_from_context(context)
            links = ResponseComposer.build_links_from_context(context)
            sources = ResponseComposer.list_sources(context)
            if orch_result.get("tools_used"):
                sources.extend([f"TOOL:{t}" for t in orch_result["tools_used"]])

            return {
                "intent": intent,
                "confidence": round(confidence, 2),
                "text": orch_result["text"],
                "sections": sections,
                "links": links,
                "sources_consulted": sources,
                "entities": entities,
                "mode": f"orchestrated:{orch_result['pattern']}",
                "tools_used": orch_result["tools_used"],
                "skills_active": [],
                "orchestration": {
                    "pattern": orch_result["pattern"],
                    "agents_used": orch_result["agents_used"],
                    "status": orch_result["status"],
                    "total_tokens": orch_result["total_tokens"],
                    "has_escalation": orch_result.get("has_escalation", False),
                },
                "llm_model": "",
                "llm_provider": "",
            }

        except Exception as e:
            logger.warning(
                "Erro na orquestracao multi-agente, fallback para dispatch simples: %s",
                e, exc_info=True,
            )
            return None

    # =================================================================
    # HISTORICO PARA SUB-AGENTE
    # =================================================================

    def _build_chat_summary_for_agent(self, session_id, current_message):
        """Monta resumo do historico recente para o sub-agente manter continuidade.

        Inclui as ultimas mensagens do chat para que o sub-agente entenda
        referencias como "esse campo", "o mesmo", "desse compare".
        """
        try:
            recent = self._history.get_recent_history(session_id, limit=6)
            if not recent:
                return ""

            lines = ["## Historico recente da conversa (para contexto)"]
            lines.append("Use este historico para entender referencias como 'esse', 'desse', 'o mesmo'.\n")

            for msg in recent[-6:]:
                role = msg.get("role", "")
                content = msg.get("content", "")
                if not content:
                    continue
                # Truncar mensagens longas
                if len(content) > 300:
                    content = content[:300] + "..."
                prefix = "**Operador:**" if role == "user" else "**GolIAs:**"
                lines.append(f"{prefix} {content}")

            return "\n".join(lines)
        except Exception as e:
            logger.warning("Erro ao montar historico para sub-agente: %s", e)
            return ""

    # =================================================================
    # DISPATCH PARA SUB-AGENTE (Fase 2)
    # =================================================================

    def _try_dispatch_to_agent(self, specialist, message, intent, confidence,
                               entities, context, session_id, environment_id, user_info):
        """Tenta despachar a tarefa para um sub-agente autonomo.

        Retorna dict de resposta se despachado, ou None para fluxo legado.
        """
        # Verificar se specialist tem agent_enabled
        if not specialist or not getattr(specialist, "agent_enabled", False):
            return None

        # Nao despachar para general (ele e o fallback, usa fluxo legado)
        if specialist.name == "general":
            return None

        # Verificar se LLM esta disponivel
        if not self._llm_provider:
            return None

        try:
            from app.services.agent_base import BaseSpecialistAgent

            user_profile = (user_info or {}).get("profile", "viewer")
            user_id = (user_info or {}).get("user_id")
            env_id = environment_id or (user_info or {}).get("environment_id")

            # Criar sub-agente
            agent = BaseSpecialistAgent(
                specialist=specialist,
                llm_provider=self._llm_provider,
                user_profile=user_profile,
                environment_id=env_id,
                user_id=user_id,
            )

            # Montar contexto para o sub-agente
            context_text = ContextBuilder.build_context_text(intent, entities, context)

            # Injetar historico recente do chat para continuidade de conversa
            chat_summary = self._build_chat_summary_for_agent(session_id, message)

            logger.info(
                "🤖 Despachando para sub-agente '%s' (budget=%d, max_iter=%d)",
                specialist.name, specialist.agent_budget, specialist.agent_max_iterations,
            )

            # SSE: indicar dispatch para sub-agente
            self._emit_agent_step(env_id, {
                "step": "agent_dispatch",
                "type": "agent_dispatch",
                "description": f"Despachando para agente especialista: {specialist.name}",
                "specialist": specialist.name,
            })

            # Executar sub-agente com historico
            result = agent.execute(
                task_description=message,
                context_text=context_text,
                extra_context=chat_summary,
            )

            # Montar resposta no formato padrao do chat engine
            sections = ResponseComposer.build_sections_from_context(context)
            links = ResponseComposer.build_links_from_context(context)
            sources = ResponseComposer.list_sources(context)
            if result.tools_used:
                sources.extend([f"TOOL:{t}" for t in result.tools_used])

            # Log do resultado
            logger.info(
                "🤖 Sub-agente '%s': success=%s, tools=%s, tokens=%s",
                specialist.name, result.success, result.tools_used,
                result.token_usage.get("total_tokens", "?"),
            )

            response_text = result.text
            if result.needs_escalation:
                response_text += (
                    f"\n\n---\n*Agente '{specialist.name}' solicitou escalonamento. "
                    f"Motivo: {result.error or 'limite de iteracoes atingido'}*"
                )

            return {
                "intent": intent,
                "confidence": round(confidence, 2),
                "text": response_text,
                "sections": sections,
                "links": links,
                "sources_consulted": sources,
                "entities": entities,
                "mode": f"agent:{specialist.name}",
                "tools_used": result.tools_used,
                "skills_active": [],
                "agent_result": result.to_dict(),
                "token_usage": result.token_usage,
                "llm_model": getattr(self._llm_provider, "model", ""),
                "llm_provider": getattr(self._llm_provider, "provider_id", ""),
            }

        except Exception as e:
            logger.warning(
                "Erro ao despachar para sub-agente '%s', fallback para fluxo legado: %s",
                specialist.name if specialist else "?", e, exc_info=True,
            )
            return None

    # =================================================================
    # MODE SELECTOR (9J)
    # =================================================================

    def _select_mode(self, message, intent, confidence, environment_id=None):
        """Decide o modo de execução: plan, react, ou two-step.

        Criterios:
        1. Sandbox config por ambiente (react_enabled)
        2. Intents simples → two-step
        3. Plan-and-Execute para tarefas com múltiplos verbos de ação
        4. ReAct para complexidade genérica
        5. Default → two-step
        """
        from app.services.agent_sandbox import SandboxPolicy

        # 1. Verificar se ReAct esta habilitado no ambiente
        sandbox = SandboxPolicy(environment_id=environment_id)
        if not sandbox.react_enabled:
            return "two-step"

        # 2. Intents simples → two-step (nao precisa loop)
        SIMPLE_INTENTS = {"user_context", "environment_status", "knowledge_search", "general"}
        if intent in SIMPLE_INTENTS and confidence >= cfg.SIMPLE_INTENT_CONFIDENCE_THRESHOLD:
            return "two-step"

        # 3. Plan-and-Execute para tarefas compostas (verbo + "e" + verbo)
        if needs_planning(message):
            logger.info("📋 Modo Plan-and-Execute selecionado")
            return "plan"

        # 4. Classificador de complexidade genérica → react
        if _classify_complexity(message) == "complex":
            logger.info("🔄 Modo ReAct selecionado para mensagem complexa")
            return "react"

        # 5. Default
        return "two-step"

    # =================================================================
    # PLAN-AND-EXECUTE (19A)
    # =================================================================

    def _plan_and_execute(self, message, intent, confidence, entities, context, session_id, user_info):
        """Decompõe tarefa complexa em plano e executa step a step."""
        from app.services.llm_providers import LLMError

        user_profile = (user_info or {}).get("profile", "viewer")
        env_id = (user_info or {}).get("environment_id")
        user_id = (user_info or {}).get("user_id")

        # SSE: informar início do planejamento
        self._emit_agent_step(env_id, {
            "step": "planning",
            "type": "planning",
            "description": "Criando plano de execução...",
        })

        # 1. Criar plano via LLM
        available_tools = get_available_tools(user_profile)
        planner = TaskPlanner(self._llm_provider)
        plan = planner.create_plan(message, available_tools)

        if not plan:
            # Fallback para two-step se não conseguir planejar
            logger.warning("📋 Não conseguiu criar plano, fallback para two-step")
            return self._compose_response_llm(
                intent, confidence, message, entities, context, session_id, user_info
            )

        # SSE: mostrar plano
        self._emit_agent_step(env_id, {
            "step": "plan_ready",
            "type": "plan_ready",
            "description": f"Plano criado: {len(plan.steps)} passos",
        })

        # 2. Executar plano
        executor = PlanExecutor(
            llm_provider=self._llm_provider,
            emit_step_fn=self._emit_agent_step,
        )
        exec_result = executor.execute_plan(
            plan,
            user_profile=user_profile,
            environment_id=env_id,
            user_id=user_id,
        )

        # 3. Usar LLM para formatar resposta final com os resultados
        # Formatar cada resultado de step com format_tool_result_for_llm
        formatted_parts = []
        for step_key, step_result in exec_result.get("results", {}).items():
            tool_name_part = step_key.split(":")[-1] if ":" in str(step_key) else str(step_key)
            formatted_parts.append(
                f"[{tool_name_part}]\n{format_tool_result_for_llm(tool_name_part, step_result)}"
            )
        results_text = "\n\n".join(formatted_parts) if formatted_parts else "(sem resultados)"
        if len(results_text) > 4000:
            results_text = results_text[:4000] + "\n... (truncado)"

        final_result = {}
        try:
            user_ctx = ContextBuilder.build_user_context(user_info)
            system = _load_system_prompt().replace("{user_context}", user_ctx).replace("{context}", "")

            # LLM formata a resposta usando os dados reais
            final_result = self._llm_provider.chat(
                messages=[
                    {"role": "user", "content": message},
                    {
                        "role": "assistant",
                        "content": f"Executei o seguinte plano:\n{exec_result['plan_display']}",
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Dados retornados (EXATOS — use somente estes):\n"
                            f"<tool_data>\n{results_text}\n</tool_data>\n\n"
                            f"Responda de forma CURTA e direta (3-5 linhas max). "
                            f"Diga O QUE encontrou, NAO como consultou. "
                            f"NAO diga 'Status:', 'Acao:', 'Resultado:'. NAO liste proximos passos. "
                            f"COPIE valores EXATAMENTE como estao em <tool_data>. "
                            f"NAO invente dados. NAO use TOOL_CALL."
                        ),
                    },
                ],
                system_prompt=system,
                temperature=0.1,
                max_tokens=cfg.MAX_TOKENS_DEFAULT,
            )

            response_text = final_result.get("content", "").strip()

        except (LLMError, Exception) as e:
            logger.warning("Erro ao formatar resposta do plano: %s", e)
            # Fallback: exibir plano + resultados diretamente
            parts = [exec_result["plan_display"], ""]
            for r in exec_result["results"]:
                icon = "✅" if r.get("success", True) else "❌"
                parts.append(f"{icon} **Passo {r['step']}:** {r['description']}")
                if r.get("error"):
                    parts.append(f"   Erro: {r['error']}")
            response_text = "\n".join(parts)

        # Montar response no formato padrão
        sections = ResponseComposer.build_sections_from_context(context)
        sources = ResponseComposer.list_sources(context)
        sources.extend([f"TOOL:{t}" for t in exec_result.get("tools_used", [])])

        return {
            "intent": intent,
            "confidence": round(confidence, 2),
            "text": response_text,
            "sections": sections,
            "links": ResponseComposer.build_links_from_context(context),
            "sources_consulted": sources,
            "entities": entities,
            "mode": "plan-execute",
            "tools_used": exec_result.get("tools_used", []),
            "plan_steps": exec_result.get("results", []),
            "skills_active": [],
            "llm_model": final_result.get("model", "") if isinstance(final_result, dict) else "",
            "llm_provider": final_result.get("provider", "") if isinstance(final_result, dict) else "",
            "llm_usage": final_result.get("usage", {}) if isinstance(final_result, dict) else {},
        }

    # =================================================================
    # REACT LOOP (9J)
    # =================================================================

    def _react_loop(
        self, message, intent, confidence, entities, context, session_id, environment_id, user_info, attachments=None
    ):
        """Loop ReAct multi-step para tarefas compostas.

        PENSAR → DECIDIR ACAO → EXECUTAR → OBSERVAR → REPETIR
        Retorna o mesmo formato de resposta que _compose_response_llm().
        """
        from app.services.llm_providers import LLMError
        from app.services.agent_sandbox import SandboxPolicy
        from app.services.agent_budget import TokenBudget

        user_profile = (user_info or {}).get("profile", "viewer")
        user_id = (user_info or {}).get("user_id")
        env_id = environment_id or (user_info or {}).get("environment_id")

        sandbox = SandboxPolicy(environment_id=env_id)
        budget = TokenBudget(max_tokens=sandbox.token_budget)
        tools_used = []
        steps = []

        # SYSTEM TOOLS que precisam de validacao de sandbox
        SYSTEM_TOOLS = {"read_file", "write_file", "list_directory", "search_files", "get_file_info", "run_command"}

        user_skips = _user_skips_confirmation(message)

        # Montar system prompt (reutiliza logica do two-step)
        user_ctx = ContextBuilder.build_user_context(user_info)
        context_text = ContextBuilder.build_context_text(intent, entities, context)
        system_template = _load_system_prompt()
        system = system_template.replace("{user_context}", user_ctx).replace("{context}", context_text)

        # Specialist + skills
        specialist = _get_specialist_for_intent(intent)
        specialist_name = specialist.name if specialist else "general"
        skill_registry = get_skill_registry()
        active_skills = skill_registry.get_skills_for_specialist(specialist_name, intent, message)
        if active_skills:
            system += skill_registry.format_skills_prompt(active_skills)

        # Tools filtradas por specialist
        all_tools = get_available_tools(user_profile)
        if specialist:
            allowed_tool_names = get_specialist_registry().get_tool_names_for_specialist(specialist)
            # Em modo react, incluir system tools tambem
            allowed_tool_names = allowed_tool_names | SYSTEM_TOOLS if allowed_tool_names else set()
            tools = [t for t in all_tools if t["name"] in allowed_tool_names]
        else:
            tools = all_tools
        if tools:
            system += self._build_tools_prompt(tools)

        # Instrucao de planning para react (v2.0 — protocolo de execucao + resiliencia)
        system += (
            "\n\n## MODO REACT ATIVO\n"
            "Voce esta em modo multi-step. Pode executar MULTIPLAS ferramentas em sequencia.\n"
            "1. PLANEJE os passos necessarios (identifique dependencias entre eles)\n"
            "2. Execute UMA ferramenta por vez\n"
            "3. VALIDE o resultado antes do proximo passo (status esperado? dados fazem sentido?)\n"
            "4. Quando tiver TUDO que precisa, responda ao usuario SEM usar ferramenta\n"
            "5. NAO chame ferramenta na resposta final — apenas texto\n\n"
            "## PROTOCOLO DE ERROS NO REACT\n"
            "Se uma ferramenta falhar durante a execucao:\n"
            "- Nivel 1 (auto-recuperacao): tente rota alternativa ou ajuste parametros (max 3 retries)\n"
            "- Nivel 2 (assistida): se precisa de decisao do operador, apresente diagnostico + opcoes (A/B/C)\n"
            "- Nivel 3 (escalonamento): se bloqueio total, reporte: Tarefa | Causa | Tentativas | Sugestao | Impacto\n"
            "NUNCA reporte sucesso quando houve falha parcial. NUNCA silencie erros."
        )

        # Historico
        chat_history = self._history.get_recent_history(session_id, limit=6)
        if chat_history:
            system += "\n\nIMPORTANTE: Esta NÃO é a primeira mensagem. Vá direto ao ponto."

        # Montar mensagens iniciais
        messages = []
        for msg in chat_history:
            content = msg["content"]
            if msg["role"] == "assistant" and len(content) > 500:
                content = content[:500] + "..."
            messages.append({"role": msg["role"], "content": content})

        # Mensagem do usuario (sem suporte a vision no react por ora)
        messages.append({"role": "user", "content": message})

        response_text = ""
        # Acumular dados formatados das tools para garantia anti-alucinação
        raw_tool_data_parts = []

        try:
            for iteration in range(sandbox.max_iterations):
                # 1. Verificar budget
                if not budget.should_continue():
                    steps.append({"type": "budget_exceeded", "iteration": iteration})
                    if not response_text:
                        response_text = "Budget de tokens excedido. Resultados parciais acima."
                    break

                # 2. Chamar LLM
                result = self._llm_provider.chat(
                    messages=messages,
                    system_prompt=system,
                    temperature=0.5,
                    max_tokens=2048,
                )

                response_text = result["content"]
                usage = result.get("usage", {})
                budget.consume(
                    usage.get("prompt_tokens", budget.estimate_tokens(str(messages))),
                    usage.get("completion_tokens", budget.estimate_tokens(response_text)),
                    iteration,
                )

                # 3. Detectar tool call
                tool_call = self._parse_tool_call(response_text)

                if not tool_call:
                    # LLM respondeu com texto final — encerrar loop
                    steps.append({"type": "final_response", "iteration": iteration})
                    break

                tool_name = tool_call["tool"]
                tool_params = tool_call.get("params", {})

                # 4. Validar sandbox para system tools
                if tool_name in SYSTEM_TOOLS:
                    if not sandbox.system_tools_enabled:
                        messages.append({"role": "assistant", "content": response_text})
                        messages.append(
                            {
                                "role": "user",
                                "content": f"SANDBOX: Tool '{tool_name}' bloqueada — system tools nao habilitadas neste ambiente. "
                                "Use as ferramentas padrao do AtuDIC ou encerre.",
                            }
                        )
                        steps.append(
                            {
                                "type": "blocked",
                                "tool": tool_name,
                                "reason": "system_tools_disabled",
                                "iteration": iteration,
                            }
                        )
                        sandbox.audit_log(
                            f"BLOCKED:{tool_name}",
                            tool_params,
                            {"error": "system_tools_disabled"},
                            user_info,
                            session_id=session_id,
                            iteration=iteration,
                        )
                        continue

                    allowed, reason = sandbox.validate_tool_call(tool_name, tool_params)
                    if not allowed:
                        messages.append({"role": "assistant", "content": response_text})
                        messages.append(
                            {
                                "role": "user",
                                "content": f"SANDBOX: Acao bloqueada — {reason}. Tente abordagem diferente ou encerre.",
                            }
                        )
                        steps.append({"type": "blocked", "tool": tool_name, "reason": reason, "iteration": iteration})
                        sandbox.audit_log(
                            f"BLOCKED:{tool_name}",
                            tool_params,
                            {"error": reason},
                            user_info,
                            session_id=session_id,
                            iteration=iteration,
                        )
                        continue

                # 5. Verificar confirmacao para acoes destrutivas
                needs_confirm = AGENT_TOOLS.get(tool_name, {}).get("requires_confirmation", False)
                confirmed = tool_params.get("confirmed", False) or user_skips

                if needs_confirm and not confirmed:
                    return self._build_confirmation_response(
                        intent, confidence, tool_name, tool_params, entities, context
                    )

                # 6. Executar tool (com session_id para inferencia de params)
                tool_result = execute_tool(
                    tool_name,
                    tool_params,
                    user_profile=user_profile,
                    environment_id=env_id,
                    user_id=user_id,
                    session_id=session_id,
                )

                tools_used.append(tool_name)
                steps.append(
                    {
                        "type": "tool_executed",
                        "tool": tool_name,
                        "success": not (isinstance(tool_result, dict) and tool_result.get("error")),
                        "iteration": iteration,
                    }
                )

                # 7. Audit log
                sandbox.audit_log(
                    tool_name,
                    tool_params,
                    tool_result,
                    user_info,
                    session_id=session_id,
                    iteration=iteration,
                    tokens_used=budget.tokens_used,
                )

                # 8. SSE: emitir step para o frontend
                self._emit_agent_step(env_id, steps[-1])

                # 9. Injetar resultado formatado no contexto
                result_text = format_tool_result_for_llm(tool_name, tool_result)
                raw_tool_data_parts.append(f"[{tool_name}]\n{result_text}")

                messages.append({"role": "assistant", "content": response_text})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"Dados retornados por {tool_name} (EXATOS — use somente estes):\n"
                            f"<tool_data>\n{result_text}\n</tool_data>\n"
                            f"Iteracao {iteration + 1}/{sandbox.max_iterations}. "
                            f"Budget restante: {budget.max_tokens - budget.tokens_used} tokens. "
                            f"Continue com a proxima acao ou responda. "
                            f"COPIE os nomes/chaves/valores EXATAMENTE de <tool_data>. NAO invente dados."
                        ),
                    }
                )

            # Limpar tool calls residuais da resposta final
            response_text = re.sub(r'```json\s*\{["\']tool["\'].*?```', "", response_text, flags=re.DOTALL).strip()

            # Montar resposta final
            sections = ResponseComposer.build_sections_from_context(context)
            links = ResponseComposer.build_links_from_context(context)
            sources = ResponseComposer.list_sources(context)
            sources.extend([f"TOOL:{t}" for t in tools_used])

            return {
                "intent": intent,
                "confidence": round(confidence, 2),
                "text": response_text,
                "sections": sections,
                "links": links,
                "sources_consulted": sources,
                "entities": entities,
                "mode": "react",
                "tools_used": tools_used,
                "react_steps": steps,
                "token_usage": budget.get_summary(),
                "skills_active": [s.name for s in active_skills],
                "llm_model": result.get("model", ""),
                "llm_provider": result.get("provider", ""),
            }

        except LLMError as e:
            logger.warning("Erro LLM no react loop (%s), fallback para rule-based: %s", e.code, e)
            response = self._composer.compose_response(intent, confidence, message, entities, context)
            response["mode"] = "rule-based (react-fallback)"
            response["llm_error"] = str(e)
            return response

    def _process_attachments(self, attachments):
        """Processa anexos e retorna texto para injetar na mensagem."""
        if not attachments:
            return ""

        parts = []
        for att in attachments:
            att_type = att.get("type", "")
            att_name = att.get("name", "arquivo")
            content = att.get("content", "")

            if att_type == "text":
                # Arquivo de texto — injetar conteúdo direto
                # Truncar se muito grande
                if len(content) > 10000:
                    content = content[:10000] + "\n... (truncado, arquivo muito grande)"
                parts.append(f"--- Arquivo anexado: {att_name} ---\n{content}\n--- Fim do arquivo ---")

            elif att_type == "image":
                # Imagem — será tratada no _compose_response_llm
                # Aqui só adiciona descrição textual
                parts.append(f"[Imagem anexada: {att_name}]")

        return "\n\n".join(parts)

    def _build_confirmation_response(self, intent, confidence, tool_name, tool_params, entities, context):
        """Retorna resposta pedindo confirmação antes de executar ação."""
        TOOL_LABELS = {
            "run_pipeline": "Executar pipeline",
            "execute_service_action": "Executar ação de serviço",
            "git_pull": "Git pull (atualizar repositório)",
            "query_database": "Executar query no banco",
            "compare_dictionary": "Comparar dicionário",
            "acknowledge_alerts_bulk": "Reconhecer alertas em lote",
        }

        label = TOOL_LABELS.get(tool_name, tool_name)
        params_text = ", ".join(f"{k}={v}" for k, v in tool_params.items() if k != "confirmed")

        text = f"⚠️ **Confirmação necessária**\n\n"
        text += f"Vou executar: **{label}**\n"
        if params_text:
            text += f"Parâmetros: `{params_text}`\n"
        text += f"\nDeseja que eu prossiga? Responda **sim** para confirmar."

        return {
            "intent": intent,
            "confidence": round(confidence, 2),
            "text": text,
            "sections": [],
            "links": [],
            "sources_consulted": [],
            "entities": entities,
            "mode": "llm",
            "tools_used": [],
            "pending_action": {
                "tool": tool_name,
                "params": tool_params,
            },
        }

    def _build_tools_prompt(self, tools):
        """Gera a lista de ferramentas para o system prompt (compacta)."""
        lines = ["\n\n## Ferramentas disponiveis neste modo"]
        for tool in tools:
            params_desc = ""
            if tool["parameters"]:
                params_list = [f"{p['name']}" for p in tool["parameters"]]
                params_desc = f" ({', '.join(params_list)})"
            lines.append(f"- `{tool['name']}`{params_desc}: {tool['description']}")

        return "\n".join(lines)

    def _parse_tool_call(self, response_text):
        """Delega para tools.parser.parse_tool_call()."""
        return parse_tool_call(response_text)

    @staticmethod
    def _looks_like_plan_not_action(text):
        """Delega para tools.parser.looks_like_plan_not_action()."""
        return looks_like_plan_not_action(text)

    # =================================================================
    # DELEGAÇÕES PARA COMPONENTES EXTRAÍDOS
    # =================================================================
    # Lógica movida para: agent_intent.py, agent_context.py, agent_composer.py, agent_history.py

    def _detect_intent(self, message):
        """Delega para agent_intent.detect_intent() com LLM fallback."""
        return detect_intent(message, llm_provider=self._llm_provider)

    def _extract_entities(self, message):
        """Delega para agent_intent.extract_entities()."""
        return extract_entities(message)

    def get_chat_history(self, session_id, limit=50):
        """Delega para HistoryManager."""
        return self._history.get_chat_history(session_id, limit=limit)

    def summarize_session(self, session_id):
        """Delega para HistoryManager."""
        return self._history.summarize_session(session_id)

# =================================================================
# SINGLETON
# =================================================================

_chat_engine = None


def get_chat_engine():
    """Retorna instância singleton do AgentChatEngine."""
    global _chat_engine
    if _chat_engine is None:
        _chat_engine = AgentChatEngine()
    return _chat_engine
