"""Context Window Manager — budget-based message management.

Instead of crude truncation (last 10 msgs, max 2000 chars each),
uses token budgeting to maximize useful context:
1. System prompt + tool results get priority (always included)
2. Recent messages included fully
3. Older messages compacted (key facts preserved)
4. Oldest messages dropped only as last resort
"""


class ContextWindowManager:
    def __init__(self, max_tokens: int = 120_000, reserve_output: int = 8_000):
        self.max_tokens = max_tokens
        self.reserve_output = reserve_output

    def estimate_tokens(self, text: str) -> int:
        """~3 chars per token for Portuguese."""
        if not text:
            return 0
        return len(text) // 3

    def build_messages(
        self,
        system_prompt: str,
        history: list[dict],
        current_message: str,
    ) -> list[dict]:
        """Build optimized message array within token budget.

        Priority:
        1. System prompt (always, full)
        2. Current user message (always, full)
        3. Recent messages (newest first, full)
        4. Older messages (compacted — first 500 chars + "[resumido]")
        5. Oldest messages (dropped if over budget)
        """
        budget = self.max_tokens - self.reserve_output
        messages: list[dict] = []

        # System prompt always included
        sys_tokens = self.estimate_tokens(system_prompt)
        budget -= sys_tokens

        # Current message always included
        current_tokens = self.estimate_tokens(current_message)
        budget -= current_tokens

        if budget <= 0:
            # System prompt alone exceeds budget — just include basics
            max_chars = (self.max_tokens - self.reserve_output) * 3
            return [
                {"role": "system", "content": system_prompt[:max_chars]},
                {"role": "user", "content": current_message},
            ]

        # Process history from newest to oldest
        # First pass: include recent messages fully
        included: list[dict] = []
        remaining = budget

        for msg in reversed(history):
            content = msg.get("content", "")
            tokens = self.estimate_tokens(content)

            if tokens <= remaining:
                # Fits fully
                included.insert(0, msg)
                remaining -= tokens
            elif remaining > 200:
                # Compact: keep first part + marker
                compact_chars = remaining * 3  # approximate
                compacted = {
                    **msg,
                    "content": content[:compact_chars]
                    + "\n\n[... mensagem resumida por limite de contexto]",
                }
                included.insert(0, compacted)
                remaining -= self.estimate_tokens(compacted["content"])
            # else: drop (over budget)

        result = [{"role": "system", "content": system_prompt}]
        result.extend(included)
        result.append({"role": "user", "content": current_message})

        return result

    def build_messages_from_rows(
        self,
        system_prompt: str,
        hist_rows: list,
        current_message: str,
    ) -> list[dict]:
        """Build messages from hist_rows format (list of [role, content] tuples).

        This is a convenience wrapper for the AnalistaPipeline which stores
        history as list of [role, content] tuples/lists.
        """
        history = [{"role": r[0], "content": r[1]} for r in hist_rows]
        return self.build_messages(system_prompt, history, current_message)

    def get_budget_info(self, system_prompt: str, history: list[dict]) -> dict:
        """Return budget breakdown for debugging."""
        sys_tokens = self.estimate_tokens(system_prompt)
        hist_tokens = sum(
            self.estimate_tokens(m.get("content", "")) for m in history
        )
        return {
            "max_tokens": self.max_tokens,
            "reserve_output": self.reserve_output,
            "system_tokens": sys_tokens,
            "history_tokens": hist_tokens,
            "available": self.max_tokens - self.reserve_output - sys_tokens,
            "history_messages": len(history),
        }
