"""Memory Extractor — auto-learns patterns from conversations.

After a conversation with artifacts, analyzes what was discovered
and extracts reusable knowledge:
- Patterns that could become recipes
- Heuristic rules about the client environment
- Field/table relationships discovered

Runs as a lightweight post-processing step (no LLM needed for basic extraction).
"""
import re
import yaml
import time
from pathlib import Path
from typing import Optional


class MemoryExtractor:
    """Extracts learnable patterns from conversation results."""

    def __init__(self, client_dir: Path, knowledge_dir: Path = None):
        self.client_dir = client_dir
        self.knowledge_dir = knowledge_dir or Path("knowledge")
        self.patterns_dir = client_dir / "memory" / "patterns"
        self.patterns_dir.mkdir(parents=True, exist_ok=True)

    def extract_from_investigation(
        self,
        message: str,
        modo: str,
        action_type: str,
        tools_used: list[str],
        artifacts_by_type: dict[str, list],
        context_text: str,
        conversa_id: int = 0,
    ) -> list[dict]:
        """Extract learnable patterns from an investigation.

        Returns list of extracted patterns with type and content.
        """
        extracted = []

        # 1. Extract table-PE relationships
        pe_relations = self._extract_pe_relations(artifacts_by_type, context_text)
        if pe_relations:
            extracted.extend(pe_relations)

        # 2. Extract field dependencies
        field_deps = self._extract_field_dependencies(artifacts_by_type, context_text)
        if field_deps:
            extracted.extend(field_deps)

        # 3. Extract integration mappings
        integ_maps = self._extract_integration_mappings(artifacts_by_type)
        if integ_maps:
            extracted.extend(integ_maps)

        # 4. Detect potential new recipe patterns
        recipe_hint = self._detect_recipe_pattern(
            message, modo, action_type, tools_used, artifacts_by_type
        )
        if recipe_hint:
            extracted.append(recipe_hint)

        # Save all extracted patterns
        for pattern in extracted:
            self._save_pattern(pattern, conversa_id)

        return extracted

    def _extract_pe_relations(self, artifacts_by_type: dict, context: str) -> list[dict]:
        """Extract which PEs are associated with which tables/rotinas."""
        patterns = []
        pes = artifacts_by_type.get("pe", [])
        tabelas = set()

        # Collect tables from other artifacts
        for tipo in ["campo", "tabela"]:
            for a in artifacts_by_type.get(tipo, []):
                t = a.get("tabela", a.get("codigo", ""))
                if t:
                    tabelas.add(t.upper())

        if pes and tabelas:
            pe_names = [p.get("nome", "") for p in pes[:20]]
            patterns.append({
                "type": "pe_relation",
                "tables": list(tabelas),
                "pes": pe_names,
                "content": f"Tabelas {', '.join(tabelas)} tem {len(pe_names)} PEs: {', '.join(pe_names[:10])}",
            })

        return patterns

    def _extract_field_dependencies(self, artifacts_by_type: dict, context: str) -> list[dict]:
        """Extract field dependency chains discovered during investigation."""
        patterns = []

        fontes = artifacts_by_type.get("fonte", [])
        campos = artifacts_by_type.get("campo", [])

        if not fontes or not campos:
            return patterns

        # Group fontes by table they reference
        table_fontes = {}
        for f in fontes:
            arquivo = f.get("arquivo", "")
            # Try to find which table this fonte relates to
            for c in campos:
                tabela = c.get("tabela", "")
                if tabela:
                    table_fontes.setdefault(tabela, set()).add(arquivo)

        for tabela, fonte_set in table_fontes.items():
            if len(fonte_set) >= 3:
                patterns.append({
                    "type": "field_dependency",
                    "table": tabela,
                    "fontes_count": len(fonte_set),
                    "content": f"Tabela {tabela} tem {len(fonte_set)} fontes customizados que mexem nela: {', '.join(list(fonte_set)[:5])}",
                })

        return patterns

    def _extract_integration_mappings(self, artifacts_by_type: dict) -> list[dict]:
        """Extract integration/webservice mappings."""
        patterns = []
        integ = artifacts_by_type.get("integracao", [])

        if integ:
            arquivos = [i.get("arquivo", "") for i in integ]
            patterns.append({
                "type": "integration_map",
                "integrations": arquivos,
                "content": f"Integracoes encontradas: {', '.join(arquivos)}",
            })

        return patterns

    def _detect_recipe_pattern(
        self, message: str, modo: str, action_type: str,
        tools_used: list[str], artifacts_by_type: dict,
    ) -> Optional[dict]:
        """Detect if this investigation pattern could be a new recipe."""
        # Check if we already have a recipe for this action_type
        recipe_path = self.knowledge_dir / "recipes"
        existing_recipes = set()
        if recipe_path.exists():
            for f in recipe_path.glob("*.yaml"):
                try:
                    with open(f, encoding="utf-8") as fh:
                        data = yaml.safe_load(fh)
                    if data and data.get("action_type"):
                        existing_recipes.add(data["action_type"])
                except Exception:
                    pass

        if action_type in existing_recipes or action_type == "default":
            return None

        # New action type discovered — suggest recipe
        if len(tools_used) >= 2:
            return {
                "type": "recipe_hint",
                "modo": modo,
                "action_type": action_type,
                "tools": tools_used,
                "message_sample": message[:200],
                "content": f"Possivel nova receita: modo={modo}, tipo={action_type}, tools={', '.join(tools_used)}",
            }

        return None

    def _save_pattern(self, pattern: dict, conversa_id: int):
        """Save an extracted pattern to disk."""
        pattern_type = pattern.get("type", "unknown")
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        slug = f"{pattern_type}_{timestamp}"

        data = {
            **pattern,
            "conversa_id": conversa_id,
            "extracted_at": time.strftime("%Y-%m-%d %H:%M"),
        }

        filepath = self.patterns_dir / f"{slug}.yaml"
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
        except Exception as e:
            print(f"[memory_extractor] save error: {e}")

    def get_recent_patterns(self, limit: int = 20) -> list[dict]:
        """Get recently extracted patterns."""
        patterns = []
        if not self.patterns_dir.exists():
            return patterns

        files = sorted(self.patterns_dir.glob("*.yaml"), reverse=True)
        for f in files[:limit]:
            try:
                with open(f, encoding="utf-8") as fh:
                    data = yaml.safe_load(fh)
                if data:
                    patterns.append(data)
            except Exception:
                pass

        return patterns

    def get_recipe_hints(self) -> list[dict]:
        """Get all recipe hints (potential new recipes to create)."""
        return [p for p in self.get_recent_patterns(100) if p.get("type") == "recipe_hint"]
