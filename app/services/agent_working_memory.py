"""
Working Memory do GolIAs — scratchpad de sessão.

Separa o que é relevante AGORA (sessão corrente) do conhecimento
permanente (memória semântica/procedural). Acumula fatos da sessão
e é descartado no final (após consolidação).

Injetado no contexto do LLM como seção compacta (~200-500 tokens).
"""

import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Limites para evitar crescimento excessivo
MAX_ENTITIES = 30
MAX_DECISIONS = 10
MAX_TOOL_SUMMARIES = 15


class WorkingMemory:
    """Scratchpad por sessão — acumula contexto transiente."""

    def __init__(self):
        # Armazena por session_id
        self._sessions = {}

    def get_or_create(self, session_id):
        """Retorna ou cria scratchpad para a sessão."""
        if session_id not in self._sessions:
            self._sessions[session_id] = {
                "entities": {},
                "decisions": [],
                "tool_results": [],
                "current_plan": None,
                "created_at": datetime.now().isoformat(),
            }
        return self._sessions[session_id]

    def add_entity(self, session_id, entity_type, value):
        """Registra entidade mencionada na sessão."""
        pad = self.get_or_create(session_id)
        entities = pad["entities"]
        if entity_type not in entities:
            entities[entity_type] = []
        if value not in entities[entity_type] and len(entities[entity_type]) < MAX_ENTITIES:
            entities[entity_type].append(value)

    def add_entities_from_extracted(self, session_id, entities_dict):
        """Registra entidades do _extract_entities automaticamente."""
        for etype, values in entities_dict.items():
            for v in values:
                self.add_entity(session_id, etype, v)

    def add_decision(self, session_id, decision):
        """Registra decisão tomada na sessão."""
        pad = self.get_or_create(session_id)
        if len(pad["decisions"]) < MAX_DECISIONS:
            pad["decisions"].append(decision)

    def add_tool_result(self, session_id, tool_name, summary):
        """Registra resumo do resultado de uma tool call."""
        pad = self.get_or_create(session_id)
        if len(pad["tool_results"]) < MAX_TOOL_SUMMARIES:
            pad["tool_results"].append({
                "tool": tool_name,
                "summary": summary[:300] if summary else "",
            })

    def set_plan(self, session_id, plan_display):
        """Define o plano ativo da sessão."""
        pad = self.get_or_create(session_id)
        pad["current_plan"] = plan_display

    def clear_plan(self, session_id):
        """Remove plano ativo após conclusão."""
        pad = self.get_or_create(session_id)
        pad["current_plan"] = None

    def to_prompt(self, session_id):
        """Formata working memory como texto para injeção no system prompt.

        Compacto (~200-500 tokens). Só incluído se tem conteúdo.
        """
        pad = self._sessions.get(session_id)
        if not pad:
            return ""

        parts = []

        # Entidades mencionadas
        if pad["entities"]:
            entity_parts = []
            for etype, values in pad["entities"].items():
                if values:
                    entity_parts.append(f"  - {etype}: {', '.join(str(v) for v in values[:10])}")
            if entity_parts:
                parts.append("**Entidades desta sessão:**")
                parts.extend(entity_parts)

        # Resultados de tools
        if pad["tool_results"]:
            parts.append("**Dados já consultados:**")
            for tr in pad["tool_results"][-5:]:  # Últimos 5
                parts.append(f"  - `{tr['tool']}`: {tr['summary'][:150]}")

        # Decisões
        if pad["decisions"]:
            parts.append("**Decisões tomadas:**")
            for d in pad["decisions"][-5:]:
                parts.append(f"  - {d}")

        # Plano ativo
        if pad["current_plan"]:
            parts.append(f"**Plano ativo:**\n{pad['current_plan']}")

        if not parts:
            return ""

        return "\n## Working Memory (contexto da sessão atual)\n" + "\n".join(parts)

    def discard(self, session_id):
        """Descarta working memory da sessão (após consolidação)."""
        self._sessions.pop(session_id, None)

    def get_facts_for_consolidation(self, session_id):
        """Retorna fatos da sessão para consolidação em memória permanente."""
        pad = self._sessions.get(session_id)
        if not pad:
            return []

        facts = []

        if pad["entities"]:
            for etype, values in pad["entities"].items():
                if values:
                    facts.append(f"Entidades {etype}: {', '.join(str(v) for v in values)}")

        for d in pad["decisions"]:
            facts.append(f"Decisão: {d}")

        for tr in pad["tool_results"]:
            facts.append(f"Consultou {tr['tool']}: {tr['summary'][:100]}")

        return facts


# Singleton
_working_memory = None


def get_working_memory():
    """Retorna instância singleton da WorkingMemory."""
    global _working_memory
    if _working_memory is None:
        _working_memory = WorkingMemory()
    return _working_memory
