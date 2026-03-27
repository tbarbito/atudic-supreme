"""
Tool-Use Chains do GolIAs — encadeamento automático de ferramentas.

Chains são sequências pré-definidas de tools que o agente executa
como uma operação atômica. Mais rápido que N tool calls individuais.

Carregadas de prompt/chains.yml (extensível sem deploy).
"""

import os
import re
import logging

from app.services.agent_tools import execute_tool

logger = logging.getLogger(__name__)


class Chain:
    """Representa uma chain de tools."""

    def __init__(self, name, description, trigger, steps):
        self.name = name
        self.description = description
        self.trigger = trigger
        self.steps = steps  # [{tool, params}, ...]


class ChainRegistry:
    """Carrega e gerencia chains de prompt/chains.yml."""

    def __init__(self):
        self._chains = {}
        self._loaded = False

    def load(self):
        """Carrega chains do arquivo YAML."""
        if self._loaded:
            return

        paths = [
            os.path.join(os.path.dirname(__file__), "..", "..", "prompt", "chains.yml"),
        ]

        for path in paths:
            abs_path = os.path.abspath(path)
            if os.path.exists(abs_path):
                try:
                    data = _parse_chains_yaml(abs_path)
                    for name, chain_data in data.items():
                        self._chains[name] = Chain(
                            name=name,
                            description=chain_data.get("description", ""),
                            trigger=chain_data.get("trigger", ""),
                            steps=chain_data.get("steps", []),
                        )
                    logger.info("⛓️ %d chains carregadas de %s", len(self._chains), abs_path)
                except Exception as e:
                    logger.warning("Erro ao carregar chains: %s", e)
                break

        self._loaded = True

    def reload(self):
        """Força recarga das chains."""
        self._chains = {}
        self._loaded = False
        self.load()

    def match_chain(self, message):
        """Retorna a chain que melhor casa com a mensagem, ou None."""
        self.load()
        msg_lower = message.lower()

        for chain in self._chains.values():
            if not chain.trigger:
                continue
            if re.search(chain.trigger, msg_lower, re.IGNORECASE):
                return chain

        return None

    def get_chain(self, name):
        """Retorna chain pelo nome."""
        self.load()
        return self._chains.get(name)

    def list_chains(self):
        """Lista todas as chains registradas."""
        self.load()
        return [
            {"name": c.name, "description": c.description, "steps": len(c.steps)}
            for c in self._chains.values()
        ]


class ChainExecutor:
    """Executa uma chain de tools e consolida os resultados."""

    def execute(self, chain, message, user_profile="viewer", environment_id=None, user_id=None):
        """Executa todos os steps da chain e retorna resultado consolidado.

        Args:
            chain: Chain object
            message: mensagem original do usuário (para substituir {message})
            user_profile: perfil do usuário
            environment_id: ID do ambiente ativo
            user_id: ID do usuário

        Returns:
            dict com results (lista), summary, tools_used, errors
        """
        results = []
        tools_used = []
        errors = []

        logger.info("⛓️ Executando chain '%s' (%d steps)", chain.name, len(chain.steps))

        for i, step in enumerate(chain.steps):
            tool_name = step.get("tool")
            if not tool_name:
                continue

            # Resolver variáveis nos params ({message}, {environment_id}, etc.)
            params = _resolve_params(step.get("params", {}), {
                "message": message,
                "environment_id": environment_id,
                "user_id": user_id,
            })

            result = execute_tool(
                tool_name,
                params,
                user_profile=user_profile,
                environment_id=environment_id,
                user_id=user_id,
            )

            if result.get("success"):
                results.append({
                    "tool": tool_name,
                    "step": i + 1,
                    "data": result.get("data"),
                    "fallback": result.get("fallback", False),
                    "warning": result.get("warning"),
                })
                tools_used.append(tool_name)
            else:
                errors.append({
                    "tool": tool_name,
                    "step": i + 1,
                    "error": result.get("error", "Erro desconhecido"),
                })
                logger.warning("⛓️ Step %d/%d falhou: %s — %s", i + 1, len(chain.steps), tool_name, result.get("error"))

        return {
            "chain": chain.name,
            "description": chain.description,
            "results": results,
            "tools_used": tools_used,
            "errors": errors,
            "total_steps": len(chain.steps),
            "successful_steps": len(results),
        }


def _resolve_params(params, context):
    """Substitui {variáveis} nos valores dos params."""
    resolved = {}
    for key, value in params.items():
        if isinstance(value, str) and "{" in value:
            for ctx_key, ctx_val in context.items():
                if ctx_val is not None:
                    value = value.replace(f"{{{ctx_key}}}", str(ctx_val))
        resolved[key] = value
    return resolved


def _parse_chains_yaml(filepath):
    """Parser YAML mínimo para chains (sem dependência de PyYAML).

    Suporta: chaves top-level, valores string, listas de dicts aninhados.
    """
    chains = {}
    current_chain = None
    in_steps = False
    current_step = None
    in_params = False

    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            raw = line.rstrip()

            # Ignorar comentários e linhas vazias
            if not raw or raw.lstrip().startswith("#"):
                continue

            indent = len(raw) - len(raw.lstrip())
            stripped = raw.strip()

            # Chain name (indent 0, termina com :)
            if indent == 0 and stripped.endswith(":") and not stripped.startswith("-"):
                # Salvar step pendente
                if current_step and current_chain:
                    chains[current_chain].setdefault("steps", []).append(current_step)
                    current_step = None

                name = stripped[:-1]
                chains[name] = {}
                current_chain = name
                in_steps = False
                in_params = False
                continue

            if not current_chain:
                continue

            # Atributo da chain (indent 2)
            if indent == 2 and ":" in stripped and not stripped.startswith("-"):
                # Salvar step pendente antes de mudar de seção
                if current_step:
                    chains[current_chain].setdefault("steps", []).append(current_step)
                    current_step = None

                key, _, val = stripped.partition(":")
                key = key.strip()
                val = val.strip().strip('"').strip("'")

                if key == "steps":
                    in_steps = True
                    in_params = False
                    chains[current_chain]["steps"] = []
                else:
                    in_steps = False
                    in_params = False
                    chains[current_chain][key] = val
                continue

            # Step item (indent 4+, começa com -)
            if in_steps and stripped.startswith("- "):
                if current_step:
                    chains[current_chain].setdefault("steps", []).append(current_step)

                content = stripped[2:].strip()
                if ":" in content:
                    k, _, v = content.partition(":")
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    current_step = {k: v, "params": {}}
                else:
                    current_step = {"tool": content, "params": {}}
                in_params = False
                continue

            # Dentro de um step — sub-keys
            if in_steps and current_step and not stripped.startswith("-"):
                if ":" in stripped:
                    k, _, v = stripped.partition(":")
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")

                    if k == "params":
                        in_params = True
                        if v == "{}":
                            current_step["params"] = {}
                            in_params = False
                    elif in_params:
                        # Param value
                        if v.isdigit():
                            v = int(v)
                        current_step["params"][k] = v
                    else:
                        # Step attribute (tool, etc)
                        current_step[k] = v
                continue

        # Salvar último step
        if current_step and current_chain:
            chains[current_chain].setdefault("steps", []).append(current_step)

    return chains


# Singleton
_chain_registry = None
_chain_executor = None


def get_chain_registry():
    """Retorna instância singleton do ChainRegistry."""
    global _chain_registry
    if _chain_registry is None:
        _chain_registry = ChainRegistry()
    return _chain_registry


def get_chain_executor():
    """Retorna instância singleton do ChainExecutor."""
    global _chain_executor
    if _chain_executor is None:
        _chain_executor = ChainExecutor()
    return _chain_executor
