"""Cost Tracker — tracks token usage and cost per operation/mode/tool.

Provides per-conversation and aggregate cost tracking to understand
which operations are expensive and optimize spending.
"""
import time
import json
from pathlib import Path
from typing import Optional


class CostTracker:
    """Tracks costs for a single conversation."""

    def __init__(self, conversa_id: int = 0, modo: str = ""):
        self.conversa_id = conversa_id
        self.modo = modo
        self.started_at = time.time()
        self.events: list[dict] = []
        self._total_input_tokens = 0
        self._total_output_tokens = 0

    def track_llm_call(self, purpose: str, input_tokens: int, output_tokens: int,
                       model: str = "", duration_ms: int = 0):
        """Track an LLM API call."""
        cost = self._estimate_cost(input_tokens, output_tokens, model)
        self.events.append({
            "type": "llm_call",
            "purpose": purpose,
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": cost,
            "duration_ms": duration_ms,
            "timestamp": time.time(),
        })
        self._total_input_tokens += input_tokens
        self._total_output_tokens += output_tokens

    def track_tool_call(self, tool_name: str, duration_ms: int,
                        result_size: int = 0, error: bool = False):
        """Track a tool execution (no direct cost, but time)."""
        self.events.append({
            "type": "tool_call",
            "tool": tool_name,
            "duration_ms": duration_ms,
            "result_size": result_size,
            "error": error,
            "timestamp": time.time(),
        })

    def _estimate_cost(self, input_tokens: int, output_tokens: int, model: str) -> float:
        """Estimate cost in USD based on model pricing."""
        # Approximate pricing per 1M tokens
        pricing = {
            "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0},
            "claude-opus-4-20250514": {"input": 15.0, "output": 75.0},
            "gpt-4.1": {"input": 2.0, "output": 8.0},
            "gpt-4.1-mini": {"input": 0.4, "output": 1.6},
        }

        # Find matching model
        rates = None
        for key, val in pricing.items():
            if key in model.lower():
                rates = val
                break

        if not rates:
            rates = {"input": 3.0, "output": 15.0}  # default to sonnet

        cost = (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000
        return round(cost, 6)

    def get_summary(self) -> dict:
        """Get cost summary for this conversation."""
        total_cost = sum(e.get("cost_usd", 0) for e in self.events)
        total_duration = int((time.time() - self.started_at) * 1000)

        llm_calls = [e for e in self.events if e["type"] == "llm_call"]
        tool_calls = [e for e in self.events if e["type"] == "tool_call"]
        tool_errors = [e for e in tool_calls if e.get("error")]

        # Group by purpose/tool
        by_purpose = {}
        for e in llm_calls:
            p = e["purpose"]
            by_purpose.setdefault(p, {"calls": 0, "cost": 0, "tokens": 0})
            by_purpose[p]["calls"] += 1
            by_purpose[p]["cost"] += e.get("cost_usd", 0)
            by_purpose[p]["tokens"] += e.get("input_tokens", 0) + e.get("output_tokens", 0)

        by_tool = {}
        for e in tool_calls:
            t = e["tool"]
            by_tool.setdefault(t, {"calls": 0, "total_ms": 0, "errors": 0})
            by_tool[t]["calls"] += 1
            by_tool[t]["total_ms"] += e.get("duration_ms", 0)
            if e.get("error"):
                by_tool[t]["errors"] += 1

        return {
            "conversa_id": self.conversa_id,
            "modo": self.modo,
            "total_cost_usd": round(total_cost, 6),
            "total_duration_ms": total_duration,
            "total_input_tokens": self._total_input_tokens,
            "total_output_tokens": self._total_output_tokens,
            "llm_calls": len(llm_calls),
            "tool_calls": len(tool_calls),
            "tool_errors": len(tool_errors),
            "by_purpose": by_purpose,
            "by_tool": by_tool,
        }


# Aggregate tracker (across conversations)
class AggregateTracker:
    """Tracks aggregate costs across all conversations."""

    def __init__(self, storage_path: Path = None):
        self.storage_path = storage_path or Path("workspace/cost_tracking.json")
        self._data = self._load()

    def record_conversation(self, summary: dict):
        """Record a conversation cost summary."""
        self._data.setdefault("conversations", []).append({
            "conversa_id": summary.get("conversa_id"),
            "modo": summary.get("modo"),
            "cost_usd": summary.get("total_cost_usd"),
            "duration_ms": summary.get("total_duration_ms"),
            "llm_calls": summary.get("llm_calls"),
            "tool_calls": summary.get("tool_calls"),
            "timestamp": time.strftime("%Y-%m-%d %H:%M"),
        })

        # Keep last 500 conversations
        if len(self._data["conversations"]) > 500:
            self._data["conversations"] = self._data["conversations"][-500:]

        # Update totals
        totals = self._data.setdefault("totals", {
            "total_cost_usd": 0, "total_conversations": 0,
            "total_llm_calls": 0, "total_tool_calls": 0,
        })
        totals["total_cost_usd"] += summary.get("total_cost_usd", 0)
        totals["total_conversations"] += 1
        totals["total_llm_calls"] += summary.get("llm_calls", 0)
        totals["total_tool_calls"] += summary.get("tool_calls", 0)

        # Update per-mode stats
        modo = summary.get("modo", "unknown")
        by_modo = self._data.setdefault("by_modo", {})
        modo_stats = by_modo.setdefault(modo, {"cost": 0, "count": 0})
        modo_stats["cost"] += summary.get("total_cost_usd", 0)
        modo_stats["count"] += 1

        self._save()

    def get_stats(self) -> dict:
        """Get aggregate statistics."""
        return {
            "totals": self._data.get("totals", {}),
            "by_modo": self._data.get("by_modo", {}),
            "recent_conversations": self._data.get("conversations", [])[-10:],
        }

    def _load(self) -> dict:
        if self.storage_path.exists():
            try:
                with open(self.storage_path, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"conversations": [], "totals": {}, "by_modo": {}}

    def _save(self):
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[cost_tracker] save error: {e}")
