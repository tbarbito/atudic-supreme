"""
Agent Budget — Gestao de tokens para o loop ReAct.

Controla o consumo de tokens por mensagem para evitar custos descontrolados.
Cada iteracao do loop ReAct consome prompt + completion tokens, e o budget
e verificado antes de cada nova iteracao.
"""

import json
import logging

logger = logging.getLogger(__name__)


class TokenBudget:
    """Gerencia o budget de tokens para uma mensagem ReAct."""

    def __init__(self, max_tokens=50000):
        self.max_tokens = max_tokens
        self.tokens_used = 0
        self.iterations = []

    def estimate_tokens(self, text):
        """Estimativa de tokens (heuristica len/4)."""
        if isinstance(text, (dict, list)):
            text = json.dumps(text, default=str)
        return len(str(text)) // 4

    def consume(self, prompt_tokens, completion_tokens, iteration):
        """Registra consumo de uma iteracao.

        Args:
            prompt_tokens: tokens de entrada
            completion_tokens: tokens de saida
            iteration: numero da iteracao (0-based)

        Returns:
            int: total de tokens consumidos ate agora
        """
        total = prompt_tokens + completion_tokens
        self.tokens_used += total
        self.iterations.append(
            {
                "iteration": iteration,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total": total,
                "budget_remaining": self.max_tokens - self.tokens_used,
            }
        )
        return self.tokens_used

    def should_continue(self):
        """Verifica se ainda ha budget para continuar o loop."""
        return self.tokens_used < self.max_tokens

    def get_summary(self):
        """Resumo do consumo para incluir na resposta."""
        return {
            "total_tokens": self.tokens_used,
            "max_tokens": self.max_tokens,
            "iterations": len(self.iterations),
            "budget_remaining": self.max_tokens - self.tokens_used,
            "budget_percent_used": round(self.tokens_used / self.max_tokens * 100, 1) if self.max_tokens > 0 else 0,
            "cost_estimate_usd": self._estimate_cost(),
        }

    def _estimate_cost(self):
        """Estimativa de custo (baseado em Claude Sonnet como referencia).

        Precos aproximados: $3/1M input + $15/1M output.
        """
        if not self.iterations:
            return 0.0
        input_cost = sum(i["prompt_tokens"] for i in self.iterations) * 3 / 1_000_000
        output_cost = sum(i["completion_tokens"] for i in self.iterations) * 15 / 1_000_000
        return round(input_cost + output_cost, 6)
