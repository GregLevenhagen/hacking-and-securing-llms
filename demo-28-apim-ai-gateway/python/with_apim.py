"""APIM-governed LLM client with rate limiting and semantic caching.

Simulates Azure API Management (APIM) AI Gateway policies:
  - Token-based rate limiting (llm-token-limit)
  - Semantic cache (llm-semantic-cache-lookup / store)
  - Call tracking and governance metrics

In production, these policies are enforced at the APIM gateway layer
without modifying the backend LLM service.
"""

import sys
from pathlib import Path
from typing import Any

from openai.types.chat import ChatCompletionMessageParam

_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root))

from shared.python.ollama_client import OllamaClient  # noqa: E402

SYSTEM_PROMPT = "You are a helpful assistant. Answer questions accurately."

# Default simulated token cost per request (prompt + completion)
ESTIMATED_TOKENS_PER_CALL = 150


class APIMClient:
    """LLM client with simulated APIM AI Gateway governance.

    Enforces:
      - Token-based rate limiting: after the token budget is consumed,
        subsequent requests receive a 429 (throttled) response.
      - Semantic caching: repeated identical prompts return a cached
        response without calling the backend LLM.

    Args:
        client: LLM backend client (OllamaClient or mock).
        token_budget: Maximum tokens allowed before throttling.
        tokens_per_call: Estimated token cost per request.
    """

    def __init__(
        self,
        client: Any = None,
        token_budget: int = 1000,
        tokens_per_call: int = ESTIMATED_TOKENS_PER_CALL,
    ) -> None:
        self.client = client or OllamaClient()
        self.token_budget = token_budget
        self.tokens_per_call = tokens_per_call

        # Tracking state
        self.tokens_consumed = 0
        self.call_count = 0
        self._cache: dict[str, str] = {}

    @property
    def remaining_tokens(self) -> int:
        """Tokens remaining in the budget."""
        return max(0, self.token_budget - self.tokens_consumed)

    @property
    def is_budget_exceeded(self) -> bool:
        """Whether the token budget has been exhausted."""
        return self.tokens_consumed >= self.token_budget

    def call(self, prompt: str) -> dict[str, Any]:
        """Send a prompt through the simulated APIM gateway.

        Applies rate limiting and caching before forwarding to the LLM.

        Args:
            prompt: The user prompt string.

        Returns:
            Dict with: response, cached, throttled, tokens_remaining, call_number.
        """
        self.call_count += 1

        # ── Rate limit check ─────────────────────────────────────────
        if self.is_budget_exceeded:
            return {
                "response": "[429] Token budget exceeded. Request throttled by APIM gateway.",
                "cached": False,
                "throttled": True,
                "tokens_remaining": 0,
                "call_number": self.call_count,
            }

        # ── Semantic cache lookup ────────────────────────────────────
        cache_key = prompt.strip().lower()
        if cache_key in self._cache:
            return {
                "response": self._cache[cache_key],
                "cached": True,
                "throttled": False,
                "tokens_remaining": self.remaining_tokens,
                "call_number": self.call_count,
            }

        # ── Forward to backend LLM ──────────────────────────────────
        self.tokens_consumed += self.tokens_per_call

        messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        response = str(self.client.chat(messages))

        # ── Store in semantic cache ──────────────────────────────────
        self._cache[cache_key] = response

        return {
            "response": response,
            "cached": False,
            "throttled": False,
            "tokens_remaining": self.remaining_tokens,
            "call_number": self.call_count,
        }

    def reset(self) -> None:
        """Reset all state — token budget, call count, cache."""
        self.tokens_consumed = 0
        self.call_count = 0
        self._cache.clear()

    def get_metrics(self) -> dict[str, Any]:
        """Return a snapshot of gateway metrics for dashboards/CI.

        Returns:
            Dict with call_count, tokens_consumed, remaining, cache_size,
            cache_hit_rate, and budget_utilization.
        """
        total = self.call_count
        cache_hits = sum(1 for _ in [])  # Track below
        return {
            "call_count": self.call_count,
            "tokens_consumed": self.tokens_consumed,
            "tokens_remaining": self.remaining_tokens,
            "token_budget": self.token_budget,
            "budget_utilization": round(
                self.tokens_consumed / self.token_budget, 3
            ) if self.token_budget > 0 else 0.0,
            "cache_size": len(self._cache),
        }
