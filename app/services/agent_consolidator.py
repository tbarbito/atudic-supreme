"""
Consolidação de memória do GolIAs — extrai fatos de sessões.

Ao final de cada sessão (ou após N mensagens), extrai fatos,
decisões e aprendizados como entradas indexáveis na memória semântica.
"""

import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Máximo de fatos por sessão (evitar poluição da memória)
MAX_FACTS_PER_SESSION = 5


class MemoryConsolidator:
    """Extrai e indexa fatos de sessões de chat."""

    def __init__(self, memory, llm_provider=None):
        self.memory = memory
        self._llm = llm_provider

    def set_llm_provider(self, provider):
        self._llm = provider

    def consolidate_session(self, session_id, working_memory_facts=None):
        """Extrai fatos da sessão e indexa como memória semântica.

        Usa LLM se disponível, senão usa fatos da working memory.

        Args:
            session_id: ID da sessão
            working_memory_facts: lista de fatos da WorkingMemory (opcional)

        Returns:
            list de fatos extraídos e indexados, ou []
        """
        facts = []

        # 1. Tentar extração via LLM (mais inteligente)
        if self._llm:
            facts = self._extract_facts_llm(session_id)

        # 2. Fallback: usar fatos da working memory
        if not facts and working_memory_facts:
            facts = working_memory_facts[:MAX_FACTS_PER_SESSION]

        if not facts:
            return []

        # 3. Indexar fatos na memória semântica
        indexed = 0
        for fact in facts[:MAX_FACTS_PER_SESSION]:
            try:
                # Verificar duplicata (buscar BM25 — se já existe algo muito similar, pular)
                existing = self.memory.search_bm25(fact, chunk_type="semantic", limit=1)
                if existing and existing[0].get("content", "").strip() == fact.strip():
                    continue

                self.memory.add_semantic_entry(
                    title=f"Fato extraído — Sessão {session_id[:8]} ({datetime.now():%Y-%m-%d})",
                    content=fact,
                )
                indexed += 1
            except Exception as e:
                logger.warning("Erro ao indexar fato: %s", e)

        if indexed > 0:
            logger.info(
                "📝 Consolidação: %d fatos extraídos e indexados da sessão %s",
                indexed, session_id[:8],
            )

        return facts[:MAX_FACTS_PER_SESSION]

    def _extract_facts_llm(self, session_id):
        """Extrai fatos via LLM a partir do histórico da sessão."""
        from app.services.agent_history import HistoryManager

        history_mgr = HistoryManager(self.memory, self._llm)
        messages = history_mgr.get_chat_history(session_id, limit=20)

        if len(messages) < 3:
            return []

        # Montar conversa compacta
        conversation = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")[:150]
            conversation.append(f"[{role}] {content}")

        conversation_text = "\n".join(conversation)

        prompt = (
            "Extraia FATOS concretos e verificáveis desta conversa. Formato:\n"
            "- Um fato por linha, prefixado com '- '\n"
            "- Máximo 5 fatos\n"
            "- Apenas fatos operacionais relevantes (decisões, diagnósticos, erros encontrados)\n"
            "- Sem opiniões, sem repetir o que o usuário disse\n"
            "- Cada fato deve ser auto-contido (compreensível sem contexto)\n\n"
            f"Conversa:\n{conversation_text}\n\n"
            "Fatos:"
        )

        try:
            result = self._llm.chat(
                messages=[{"role": "user", "content": prompt}],
                system_prompt="Você extrai fatos concretos de conversas técnicas. Apenas fatos, sem análise.",
                temperature=0.2,
                max_tokens=400,
            )

            raw = result.get("content", "").strip()
            # Parsear linhas que começam com "- "
            facts = []
            for line in raw.split("\n"):
                line = line.strip()
                if line.startswith("- "):
                    fact = line[2:].strip()
                    if fact and len(fact) > 10:
                        facts.append(fact)

            return facts[:MAX_FACTS_PER_SESSION]

        except Exception as e:
            logger.warning("Erro na extração de fatos via LLM: %s", e)
            return []
