"""
Gerenciamento de histórico e sessões do GolIAs.

Responsabilidades:
- Carregar histórico recente do chat
- Sumarizar histórico antigo (sliding window + LLM)
- Persistir mensagens (user + assistant) no SQLite
- Retornar histórico para API
- Gerar resumo automático de sessão (memória episódica)
- Registrar feedback de intent detection
"""

import json
import logging
from datetime import datetime

from app.services.agent_config import agent_config as cfg

logger = logging.getLogger(__name__)


class HistoryManager:
    """Gerencia histórico de chat, sumarização e persistência."""

    def __init__(self, memory, llm_provider=None):
        self.memory = memory
        self._llm_provider = llm_provider
        # Cache de sumarizacao por sessao: {session_id: {"summary": str, "msg_count": int}}
        self._summary_cache = {}

    def set_llm_provider(self, provider):
        """Atualiza o provider LLM (chamado quando ativa/desativa LLM)."""
        self._llm_provider = provider

    def get_recent_history(self, session_id, limit=10):
        """Retorna histórico recente da sessão para contexto do LLM."""
        conn = self.memory._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT role, content FROM chat_messages
            WHERE session_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        """,
            (session_id, limit),
        )
        rows = [dict(r) for r in cursor.fetchall()]
        rows.reverse()  # Ordem cronológica
        return rows

    def build_history_with_summary(self, session_id, raw_history):
        """Constroi historico com sumarizacao das mensagens antigas.

        Se o historico tem mais de HISTORY_SUMMARIZE_THRESHOLD mensagens,
        sumariza as mais antigas e mantem as ultimas HISTORY_KEEP_RECENT intactas.
        Usa cache para nao re-sumarizar a cada mensagem.
        """
        total = len(raw_history)

        # Historico curto — sem necessidade de sumarizar
        if total <= cfg.HISTORY_SUMMARIZE_THRESHOLD or not self._llm_provider:
            return raw_history

        keep = cfg.HISTORY_KEEP_RECENT
        old_msgs = raw_history[:-keep]
        recent_msgs = raw_history[-keep:]

        # Verificar cache: so re-sumarizar se houve mensagens novas suficientes
        cached = self._summary_cache.get(session_id)
        if cached and (total - cached["msg_count"]) < cfg.HISTORY_RESUMMARIZE_DELTA:
            summary_msg = {"role": "user", "content": cached["summary"]}
            return [summary_msg] + recent_msgs

        # Gerar resumo via LLM
        try:
            old_text = "\n".join(
                f"{m['role'].upper()}: {m['content'][:200]}" for m in old_msgs
            )
            summary_prompt = (
                "Resuma esta conversa anterior em 3-5 linhas, preservando: "
                "decisões tomadas, entidades mencionadas (pipelines, tabelas, erros), "
                "e o que foi resolvido. Apenas fatos, sem opinião.\n\n"
                f"{old_text}"
            )
            result = self._llm_provider.chat(
                messages=[{"role": "user", "content": summary_prompt}],
                system_prompt="Você é um assistente que resume conversas de forma concisa em português.",
                temperature=cfg.TEMPERATURE_SUMMARY,
                max_tokens=cfg.MAX_TOKENS_SUMMARY,
            )
            summary_text = f"[Resumo da conversa anterior: {result['content']}]"

            # Cachear
            self._summary_cache[session_id] = {
                "summary": summary_text,
                "msg_count": total,
            }

            logger.info(
                "📝 History sumarizado: %d msgs antigas → %d chars de resumo",
                len(old_msgs),
                len(summary_text),
            )

            summary_msg = {"role": "user", "content": summary_text}
            return [summary_msg] + recent_msgs

        except Exception as e:
            logger.warning("Erro ao sumarizar history, usando truncamento: %s", e)
            return recent_msgs

    def save_messages(self, session_id, environment_id, user_message, intent, confidence, response):
        """Salva mensagem do usuário e resposta do agente no SQLite."""
        conn = self.memory._get_conn()
        cursor = conn.cursor()

        # Mensagem do usuário
        cursor.execute(
            """
            INSERT INTO chat_messages (session_id, environment_id, role, content, intent, confidence)
            VALUES (?, ?, 'user', ?, ?, ?)
        """,
            (session_id, environment_id, user_message, intent, confidence),
        )

        # Resposta do agente (inclui metadata para restore de sessao)
        response_data = json.dumps(
            {
                "sections": response.get("sections", []),
                "links": response.get("links", []),
                "entities": response.get("entities", {}),
                "mode": response.get("mode", ""),
                "llm_provider": response.get("llm_provider", ""),
                "llm_model": response.get("llm_model", ""),
            },
            ensure_ascii=False,
        )

        sources = json.dumps(response.get("sources_consulted", []))

        cursor.execute(
            """
            INSERT INTO chat_messages (session_id, environment_id, role, content,
                                       intent, confidence, response_data, sources_consulted)
            VALUES (?, ?, 'assistant', ?, ?, ?, ?, ?)
        """,
            (session_id, environment_id, response.get("text", ""), intent, confidence, response_data, sources),
        )

        # Atualizar contador de queries na sessão
        cursor.execute(
            """
            UPDATE agent_sessions
            SET queries_made = queries_made + 1
            WHERE session_id = ?
        """,
            (session_id,),
        )

        conn.commit()

    def get_chat_history(self, session_id, limit=50):
        """Retorna histórico de mensagens de uma sessão."""
        conn = self.memory._get_conn()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT id, session_id, role, content, intent, confidence,
                   response_data, sources_consulted, created_at
            FROM chat_messages
            WHERE session_id = ?
            ORDER BY created_at ASC
            LIMIT ?
        """,
            (session_id, limit),
        )

        messages = []
        for row in cursor.fetchall():
            msg = dict(row)
            # Parsear JSON fields
            if msg.get("response_data"):
                try:
                    msg["response_data"] = json.loads(msg["response_data"])
                except (json.JSONDecodeError, TypeError):
                    pass
            if msg.get("sources_consulted"):
                try:
                    msg["sources_consulted"] = json.loads(msg["sources_consulted"])
                except (json.JSONDecodeError, TypeError):
                    pass
            # Extrair metadata do response_data para facilitar restore de sessao
            rd = msg.get("response_data")
            if isinstance(rd, dict) and msg.get("role") == "assistant":
                msg["mode"] = rd.get("mode", "")
                msg["llm_provider"] = rd.get("llm_provider", "")
                msg["llm_model"] = rd.get("llm_model", "")
            messages.append(msg)

        return messages

    def summarize_session(self, session_id):
        """Gera resumo automatico da sessao para memoria episodica."""
        if not self._llm_provider:
            return None

        messages = self.get_chat_history(session_id, limit=20)
        if len(messages) < 3:
            return None

        conversation = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")[:200]
            conversation.append(f"[{role}] {content}")

        conversation_text = "\n".join(conversation)

        try:
            result = self._llm_provider.chat(
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"Resuma esta conversa em 2-3 frases em portugues, focando em:\n"
                            f"- O que o usuario pediu\n"
                            f"- O que foi resolvido (ou nao)\n"
                            f"- Insights operacionais relevantes\n\n"
                            f"Conversa:\n{conversation_text}"
                        ),
                    }
                ],
                system_prompt="Voce e um assistente que gera resumos concisos de conversas tecnicas.",
                temperature=cfg.TEMPERATURE_SUMMARY,
                max_tokens=cfg.MAX_TOKENS_SUMMARY,
            )

            summary = result.get("content", "").strip()
            if not summary:
                return None

            try:
                self.memory.add_episodic_entry(
                    title=f"Sessao {session_id[:8]} — {datetime.now():%Y-%m-%d %H:%M}",
                    content=summary,
                )
                logger.info("📝 Resumo de sessao salvo: %s", session_id[:8])
            except Exception as e:
                logger.warning("Erro ao salvar resumo episodico: %s", e)

            return summary

        except Exception as e:
            logger.warning("Erro ao gerar resumo de sessao: %s", e)
            return None

    @staticmethod
    def log_intent_feedback(intent, specialist_name, tools_used):
        """Registra feedback do intent detection para melhoria futura."""
        from app.services.agent_specialists import get_specialist_registry

        if not tools_used:
            return

        def _get_specialist_for_intent(i):
            return get_specialist_registry().get_specialist_for_intent(i)

        specialist = _get_specialist_for_intent(intent)
        if not specialist:
            return

        expected_tools = set(specialist.tools)
        actual_tools = set(tools_used)
        match_rate = len(actual_tools & expected_tools) / max(len(actual_tools), 1)

        if match_rate < 0.5 and len(actual_tools) > 0:
            logger.warning(
                "INTENT_MISMATCH: detected=%s specialist=%s tools_used=%s match_rate=%.2f",
                intent,
                specialist_name,
                tools_used,
                match_rate,
            )
