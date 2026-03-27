"""
Agent Specialists — Modos especializados do GolIAs.

Cada specialist agrupa intents, skills e tools de um dominio especifico.
O chat engine seleciona o specialist baseado no intent detectado e filtra
o contexto (skills + tools) para enviar ao LLM apenas o que e relevante.

Fase 2: Specialists com agent_enabled=true podem ser promovidos a sub-agentes
autonomos via BaseSpecialistAgent (agent_base.py). O orquestrador despacha
a tarefa para o sub-agente, que executa de forma independente e retorna
um resultado estruturado (SpecialistAgentResult).

Registro carregado de prompt/specialists.yml (extensivel sem deploy).

Arquitetura:
  prompt/specialists.yml  ->  SpecialistRegistry (singleton)  ->  agent_chat.py
                                                                      |
                                                              filtra skills + tools
                                                              OU despacha para sub-agente
"""

import os
import sys
import re
import logging

logger = logging.getLogger(__name__)


def _resolve_specialists_path():
    """Resolve o caminho do specialists.yml, compativel com PyInstaller."""
    # 1. PyInstaller
    if getattr(sys, "_MEIPASS", None):
        candidate = os.path.join(sys._MEIPASS, "prompt", "specialists.yml")
        if os.path.isfile(candidate):
            return candidate

    # 2. Desenvolvimento
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    candidate = os.path.join(base, "prompt", "specialists.yml")
    if os.path.isfile(candidate):
        return candidate

    # 3. Fallback cwd
    return os.path.join(os.getcwd(), "prompt", "specialists.yml")


def _parse_yaml_simple(content):
    """Parser YAML minimalista para o formato do specialists.yml.

    Evita dependencia de pyyaml. Suporta:
    - Chaves top-level (sem indentacao, terminando em :)
    - Chaves de segundo nivel (2 espacos, terminando em :)
    - Valores string (entre aspas ou sem)
    - Listas (itens com - prefixo)
    - Booleans (true/false)
    - null
    """
    result = {}
    current_top = None
    current_key = None

    for line in content.split("\n"):
        # Ignorar comentarios e linhas vazias
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # Calcular indentacao
        indent = len(line) - len(line.lstrip())

        # Top-level key (sem indentacao)
        if indent == 0 and stripped.endswith(":"):
            current_top = stripped[:-1].strip()
            result[current_top] = {}
            current_key = None
            continue

        if current_top is None:
            continue

        # Segundo nivel (2 espacos)
        if indent == 2 and ":" in stripped:
            key, _, value = stripped.partition(":")
            key = key.strip()
            value = value.strip()

            if not value:
                # Lista vazia ou bloco — iniciar lista
                result[current_top][key] = []
                current_key = key
            elif value == "[]":
                # Lista vazia inline
                result[current_top][key] = []
                current_key = None
            elif value == "null":
                result[current_top][key] = None
                current_key = None
            elif value in ("true", "false"):
                result[current_top][key] = value == "true"
                current_key = None
            elif re.match(r"^-?\d+$", value):
                result[current_top][key] = int(value)
                current_key = None
            elif re.match(r"^-?\d+\.\d+$", value):
                result[current_top][key] = float(value)
                current_key = None
            else:
                # Remover aspas
                value = value.strip("'\"")
                result[current_top][key] = value
                current_key = None
            continue

        # Item de lista (4 espacos + -)
        if indent >= 4 and stripped.startswith("- ") and current_key is not None:
            item = stripped[2:].strip().strip("'\"")
            if isinstance(result[current_top].get(current_key), list):
                result[current_top][current_key].append(item)
            continue

    return result


class Specialist:
    """Um modo especialista do agente.

    Campos de agente (Fase 2):
        agent_enabled: Se true, pode ser promovido a sub-agente autonomo
        agent_budget: Tokens maximo para execucao do sub-agente (default: 15000)
        agent_max_iterations: Max tool calls por execucao (default: 5)
    """

    __slots__ = (
        "name", "description", "intents", "skills", "tools",
        "greeting", "autonomous",
        "agent_enabled", "agent_budget", "agent_max_iterations",
    )

    def __init__(self, name, data):
        self.name = name
        self.description = data.get("description", "")
        self.intents = data.get("intents", [])
        self.skills = data.get("skills", [])
        self.tools = data.get("tools", [])
        self.greeting = data.get("greeting")
        self.autonomous = data.get("autonomous", False)
        # Campos de sub-agente (Fase 2)
        self.agent_enabled = data.get("agent_enabled", False)
        self.agent_budget = data.get("agent_budget", 15000)
        self.agent_max_iterations = data.get("agent_max_iterations", 5)

    def to_dict(self):
        """Serializa para JSON (admin/debug)."""
        return {
            "name": self.name,
            "description": self.description,
            "intents": self.intents,
            "skills": self.skills,
            "tools": self.tools,
            "greeting": self.greeting,
            "autonomous": self.autonomous,
            "agent_enabled": self.agent_enabled,
            "agent_budget": self.agent_budget,
            "agent_max_iterations": self.agent_max_iterations,
        }


class SpecialistRegistry:
    """Carrega e gerencia specialists do YAML."""

    def __init__(self, yml_path=None):
        self._specialists: dict[str, Specialist] = {}
        self._intent_map: dict[str, str] = {}  # intent -> specialist_name
        self._yml_path = yml_path or _resolve_specialists_path()
        self._loaded = False

    def load(self):
        """Carrega specialists do YAML."""
        if self._loaded:
            return

        if not os.path.isfile(self._yml_path):
            logger.warning("Arquivo specialists.yml nao encontrado: %s", self._yml_path)
            self._load_fallback()
            self._loaded = True
            return

        try:
            with open(self._yml_path, "r", encoding="utf-8") as f:
                content = f.read()

            data = _parse_yaml_simple(content)

            for name, spec_data in data.items():
                if not isinstance(spec_data, dict):
                    continue
                spec = Specialist(name, spec_data)
                self._specialists[name] = spec
                # Mapear intents -> specialist
                for intent in spec.intents:
                    self._intent_map[intent] = name

            self._loaded = True
            logger.info("🎯 %d specialists carregados de %s", len(self._specialists), self._yml_path)

        except Exception as e:
            logger.error("Erro ao carregar specialists.yml: %s", e)
            self._load_fallback()
            self._loaded = True

    def _load_fallback(self):
        """Fallback hardcoded caso o YAML nao exista."""
        fallback = {
            "general": {
                "description": "Modo geral",
                "intents": ["general", "user_context", "environment_status"],
                "skills": [],
                "tools": [],
            }
        }
        for name, data in fallback.items():
            spec = Specialist(name, data)
            self._specialists[name] = spec
            for intent in spec.intents:
                self._intent_map[intent] = name

    def get_specialist_for_intent(self, intent):
        """Retorna o specialist adequado para o intent detectado."""
        self.load()
        name = self._intent_map.get(intent, "general")
        return self._specialists.get(name, self._specialists.get("general"))

    def get_specialist_by_name(self, name):
        """Retorna specialist por nome."""
        self.load()
        return self._specialists.get(name)

    def get_tool_names_for_specialist(self, specialist):
        """Retorna set de nomes de tools permitidas para o specialist."""
        if specialist is None:
            return set()
        return set(specialist.tools)

    def get_all_specialists(self):
        """Retorna todos os specialists (admin/debug)."""
        self.load()
        return [s.to_dict() for s in self._specialists.values()]

    def reload(self):
        """Forca recarga do YAML."""
        self._specialists.clear()
        self._intent_map.clear()
        self._loaded = False
        self.load()
        return {"specialists_loaded": len(self._specialists)}


# Singleton
_registry = None


def get_specialist_registry():
    """Retorna o registry singleton."""
    global _registry
    if _registry is None:
        _registry = SpecialistRegistry()
        _registry.load()
    return _registry
