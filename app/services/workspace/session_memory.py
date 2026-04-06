"""Session Memory — persists discoveries between conversations.

Stores and retrieves key findings per client so conversations
build on previous knowledge instead of starting from zero.

Structure:
    workspace/clients/{slug}/memory/
        index.yaml          # Light index, always loaded
        discoveries/
            {topic}.yaml    # Individual discoveries
"""
import re
import time
import yaml
from pathlib import Path
from typing import Optional


class SessionMemory:
    """Per-client memory that persists between conversations."""

    def __init__(self, client_dir: Path):
        self.memory_dir = client_dir / "memory"
        self.discoveries_dir = self.memory_dir / "discoveries"
        self.index_path = self.memory_dir / "index.yaml"

        # Ensure directories exist
        self.discoveries_dir.mkdir(parents=True, exist_ok=True)

    def save_discovery(self, topic: str, content: str, tags: list[str] = None,
                       source: str = "", conversa_id: int = 0) -> None:
        """Save a discovery for future sessions.

        Args:
            topic: Short topic identifier (e.g., "mata410_custom", "sb1_aumento")
            content: The discovery text
            tags: Search tags (e.g., ["MATA410", "PE", "customizacao"])
            source: Where this came from (e.g., "conversa:123")
            conversa_id: Conversation ID for reference
        """
        # Save discovery file
        slug = topic.lower().replace(" ", "_").replace("/", "_")[:50]
        discovery = {
            "topic": topic,
            "content": content,
            "tags": tags or [],
            "source": source,
            "conversa_id": conversa_id,
            "created_at": time.strftime("%Y-%m-%d %H:%M"),
        }

        discovery_path = self.discoveries_dir / f"{slug}.yaml"
        with open(discovery_path, "w", encoding="utf-8") as f:
            yaml.dump(discovery, f, allow_unicode=True, default_flow_style=False)

        # Update index
        self._update_index(slug, topic, tags or [])

    def load_relevant(self, message: str, max_results: int = 3) -> str:
        """Load memories relevant to the current message.

        Uses simple keyword matching against tags and topics.
        Returns formatted context string or empty.
        """
        if not self.index_path.exists():
            return ""

        try:
            with open(self.index_path, encoding="utf-8") as f:
                index = yaml.safe_load(f) or {}
        except Exception:
            return ""

        entries = index.get("entries", [])
        if not entries:
            return ""

        # Score each entry by keyword overlap
        msg_words = set(message.upper().split())
        # Also extract table/field codes
        msg_codes = set(re.findall(r'\b([A-Z][A-Z0-9]{2})\b', message.upper()))
        msg_fields = set(re.findall(r'\b([A-Z][A-Z0-9]{1,2}_\w+)\b', message.upper()))
        search_terms = msg_words | msg_codes | msg_fields

        scored = []
        for entry in entries:
            tags = set(t.upper() for t in entry.get("tags", []))
            topic = entry.get("topic", "").upper()

            # Score: number of matching tags/words
            score = len(tags & search_terms)
            if any(term in topic for term in search_terms):
                score += 2

            if score > 0:
                scored.append((score, entry))

        if not scored:
            return ""

        # Sort by score descending, take top N
        scored.sort(key=lambda x: -x[0])
        top = scored[:max_results]

        # Load full content of top matches
        parts = ["## Contexto de sessoes anteriores\n"]
        for _score, entry in top:
            slug = entry.get("slug", "")
            discovery_path = self.discoveries_dir / f"{slug}.yaml"
            if discovery_path.exists():
                try:
                    with open(discovery_path, encoding="utf-8") as f:
                        data = yaml.safe_load(f)
                    if data and data.get("content"):
                        parts.append(f"**{data['topic']}** ({data.get('created_at', '')})")
                        parts.append(data["content"])
                        parts.append("")
                except Exception:
                    pass

        if len(parts) <= 1:
            return ""

        return "\n".join(parts)

    def _update_index(self, slug: str, topic: str, tags: list[str]):
        """Update the memory index file."""
        index = {"entries": []}
        if self.index_path.exists():
            try:
                with open(self.index_path, encoding="utf-8") as f:
                    index = yaml.safe_load(f) or {"entries": []}
            except Exception:
                index = {"entries": []}

        # Remove existing entry with same slug
        entries = [e for e in index.get("entries", []) if e.get("slug") != slug]

        # Add new entry
        entries.append({
            "slug": slug,
            "topic": topic,
            "tags": tags,
            "updated_at": time.strftime("%Y-%m-%d %H:%M"),
        })

        # Keep index manageable (max 100 entries)
        if len(entries) > 100:
            entries = entries[-100:]

        index["entries"] = entries
        with open(self.index_path, "w", encoding="utf-8") as f:
            yaml.dump(index, f, allow_unicode=True, default_flow_style=False)

    def list_memories(self) -> list[dict]:
        """List all stored memories."""
        if not self.index_path.exists():
            return []
        try:
            with open(self.index_path, encoding="utf-8") as f:
                index = yaml.safe_load(f) or {}
            return index.get("entries", [])
        except Exception:
            return []
