"""
Agent Skills — Sistema de conhecimento modular para o agente IA.

Skills sao fragmentos de prompt carregados sob demanda conforme a intencao
detectada. Isso evita injetar 53KB de contexto em toda mensagem — o agente
recebe apenas o que precisa para aquela tarefa especifica.

Arquitetura:
  prompt/skills/*.md  →  SkillRegistry (index em memoria)  →  agent_chat.py
                                                                 ↓
                                                         system_prompt + skills relevantes
"""

import os
import sys
import re
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


def _resolve_skills_dir():
    """Resolve o diretorio de skills, compativel com PyInstaller (.exe).

    PyInstaller extrai arquivos para sys._MEIPASS em tempo de execucao.
    Em dev, usa o caminho relativo ao projeto normalmente.
    """
    # 1. PyInstaller: sys._MEIPASS aponta para o diretorio temporario
    if getattr(sys, "_MEIPASS", None):
        candidate = os.path.join(sys._MEIPASS, "prompt", "skills")
        if os.path.isdir(candidate):
            return candidate

    # 2. Desenvolvimento: relativo ao arquivo atual (app/services/ → ../../prompt/skills)
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    candidate = os.path.join(base, "prompt", "skills")
    if os.path.isdir(candidate):
        return candidate

    # 3. Fallback: relativo ao cwd
    candidate = os.path.join(os.getcwd(), "prompt", "skills")
    return candidate


# Diretorio base das skills (resolvido uma vez)
_SKILLS_DIR = _resolve_skills_dir()


@dataclass
class Skill:
    """Uma skill modular do agente."""

    name: str
    description: str
    intents: list  # Intents que ativam esta skill
    keywords: list  # Palavras-chave adicionais para matching
    priority: int  # Maior = carrega primeiro (0-100)
    content: str  # Conteudo markdown da skill
    always_load: bool = False  # Carregar em toda mensagem (ex: quick_response)
    max_tokens_estimate: int = 0  # Estimativa de tokens (~4 chars/token)
    specialist: str = ""  # Specialist mode que usa esta skill (diagnostico, devops, database, knowledge, general, all)

    @property
    def token_estimate(self):
        if self.max_tokens_estimate:
            return self.max_tokens_estimate
        return len(self.content) // 4


class SkillRegistry:
    """Registra e carrega skills sob demanda."""

    def __init__(self, skills_dir=None):
        self._skills: dict[str, Skill] = {}
        self._skills_dir = skills_dir or _SKILLS_DIR
        self._loaded = False

    def load_all(self):
        """Carrega todas as skills do diretorio prompt/skills/."""
        if self._loaded:
            return

        if not os.path.isdir(self._skills_dir):
            logger.warning("Diretorio de skills nao encontrado: %s", self._skills_dir)
            self._loaded = True
            return

        count = 0
        for filename in sorted(os.listdir(self._skills_dir)):
            if not filename.endswith(".md"):
                continue
            filepath = os.path.join(self._skills_dir, filename)
            try:
                skill = self._parse_skill_file(filepath)
                if skill:
                    self._skills[skill.name] = skill
                    count += 1
            except Exception as e:
                logger.error("Erro ao carregar skill %s: %s", filename, e)

        self._loaded = True
        logger.info("📚 %d skills carregadas de %s", count, self._skills_dir)

    def _parse_skill_file(self, filepath):
        """Parseia arquivo .md com frontmatter YAML-like."""
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        # Extrair frontmatter entre ---
        fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", content, re.DOTALL)
        if not fm_match:
            logger.warning("Skill sem frontmatter: %s", filepath)
            return None

        frontmatter_text = fm_match.group(1)
        body = fm_match.group(2).strip()

        # Parse simples do frontmatter (sem dependencia de pyyaml)
        meta = {}
        for line in frontmatter_text.strip().split("\n"):
            line = line.strip()
            if ":" in line:
                key, value = line.split(":", 1)
                key = key.strip()
                value = value.strip()
                # Listas entre colchetes
                if value.startswith("[") and value.endswith("]"):
                    value = [v.strip().strip("'\"") for v in value[1:-1].split(",") if v.strip()]
                elif value.lower() in ("true", "false"):
                    value = value.lower() == "true"
                elif value.isdigit():
                    value = int(value)
                meta[key] = value

        if not meta.get("name"):
            meta["name"] = os.path.splitext(os.path.basename(filepath))[0]

        return Skill(
            name=meta.get("name", ""),
            description=meta.get("description", ""),
            intents=meta.get("intents", []),
            keywords=meta.get("keywords", []),
            priority=int(meta.get("priority", 50)),
            content=body,
            always_load=bool(meta.get("always_load", False)),
            max_tokens_estimate=int(meta.get("max_tokens", 0)),
            specialist=meta.get("specialist", ""),
        )

    def get_skills_for_intent(self, intent, message="", max_skills=5, max_total_tokens=4000):
        """Retorna skills relevantes para um intent + mensagem.

        Estrategia de matching:
        1. always_load → sempre inclui (nao conta no limite de max_skills)
        2. intent exato → match direto nos intents da skill
        3. keyword match → palavras da mensagem batem com keywords da skill
        4. Ordena por (match_score * priority) e aplica limite de tokens
        """
        self.load_all()

        if not self._skills:
            return []

        message_lower = message.lower()
        message_words = set(re.findall(r"\w+", message_lower))

        candidates = []
        always = []

        for skill in self._skills.values():
            if skill.always_load:
                always.append(skill)
                continue

            score = 0

            # Match por intent (peso alto)
            if intent in skill.intents:
                score += 10

            # Match por keywords na mensagem (peso medio)
            keyword_matches = sum(1 for kw in skill.keywords if kw.lower() in message_lower)
            score += keyword_matches * 2

            # Match por palavras da mensagem nos keywords (peso baixo)
            word_matches = sum(1 for w in message_words if any(w in kw.lower() for kw in skill.keywords))
            score += word_matches

            if score > 0:
                candidates.append((score * skill.priority, skill))

        # Ordenar por score descendente
        candidates.sort(key=lambda x: x[0], reverse=True)

        # Montar resultado respeitando limite de tokens
        result = list(always)  # always_load primeiro
        total_tokens = sum(s.token_estimate for s in result)

        for _score, skill in candidates[:max_skills]:
            if total_tokens + skill.token_estimate > max_total_tokens:
                continue
            result.append(skill)
            total_tokens += skill.token_estimate

        return result

    def format_skills_prompt(self, skills):
        """Formata skills selecionadas como bloco de prompt."""
        if not skills:
            return ""

        parts = ["\n\n## Skills ativas para esta mensagem\n"]
        for skill in skills:
            parts.append(f"### {skill.name}: {skill.description}")
            parts.append(skill.content)
            parts.append("")  # linha em branco entre skills

        return "\n".join(parts)

    def get_skills_for_specialist(self, specialist_name, intent, message="", max_skills=5, max_total_tokens=4000):
        """Retorna skills relevantes para um specialist + intent + mensagem.

        Prioriza skills do specialist informado, mas tambem inclui matches
        por intent/keyword de outros specialists se relevantes.
        """
        self.load_all()

        if not self._skills:
            return []

        message_lower = message.lower()
        message_words = set(re.findall(r"\w+", message_lower))

        candidates = []
        always = []

        for skill in self._skills.values():
            if skill.always_load:
                always.append(skill)
                continue

            score = 0

            # Boost por specialist match (peso muito alto)
            if skill.specialist and skill.specialist in (specialist_name, "all"):
                score += 15

            # Match por intent (peso alto)
            if intent in skill.intents:
                score += 10

            # Match por keywords na mensagem (peso medio)
            keyword_matches = sum(1 for kw in skill.keywords if kw.lower() in message_lower)
            score += keyword_matches * 2

            # Match por palavras da mensagem nos keywords (peso baixo)
            word_matches = sum(1 for w in message_words if any(w in kw.lower() for kw in skill.keywords))
            score += word_matches

            if score > 0:
                candidates.append((score * skill.priority, skill))

        # Ordenar por score descendente
        candidates.sort(key=lambda x: x[0], reverse=True)

        # Montar resultado respeitando limite de tokens
        result = list(always)
        total_tokens = sum(s.token_estimate for s in result)

        for _score, skill in candidates[:max_skills]:
            if total_tokens + skill.token_estimate > max_total_tokens:
                continue
            result.append(skill)
            total_tokens += skill.token_estimate

        return result

    def get_all_skills(self):
        """Retorna todas as skills registradas (para admin/debug)."""
        self.load_all()
        return [
            {
                "name": s.name,
                "description": s.description,
                "intents": s.intents,
                "keywords": s.keywords,
                "priority": s.priority,
                "always_load": s.always_load,
                "token_estimate": s.token_estimate,
                "specialist": s.specialist,
            }
            for s in sorted(self._skills.values(), key=lambda x: -x.priority)
        ]

    def reload(self):
        """Forca recarga de todas as skills."""
        self._skills.clear()
        self._loaded = False
        self.load_all()
        return {"skills_loaded": len(self._skills)}


# Singleton
_registry = None


def get_skill_registry():
    """Retorna o registry singleton."""
    global _registry
    if _registry is None:
        _registry = SkillRegistry()
        _registry.load_all()
    return _registry
