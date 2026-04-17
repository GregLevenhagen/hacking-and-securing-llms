"""Direct LLM client with NO APIM gateway governance.

Calls the LLM directly with no rate limiting, no caching, and no
content safety screening. Every request goes straight through regardless
of volume or content, demonstrating the risk of unprotected LLM access.
"""

import sys
from pathlib import Path
from typing import Any

from openai.types.chat import ChatCompletionMessageParam

_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root))

from shared.python.ollama_client import OllamaClient  # noqa: E402

SYSTEM_PROMPT = "You are a helpful assistant. Answer questions accurately."


class DirectClient:
    """LLM client with no API gateway — no rate limits, no cache.

    Every call goes directly to the LLM backend. There is no protection
    against burst traffic, no cost controls, and no content screening.
    """

    def __init__(self, client: Any = None) -> None:
        self.client = client or OllamaClient()
        self.call_count = 0

    def call(self, prompt: str) -> dict[str, Any]:
        """Send a prompt directly to the LLM with no governance.

        Args:
            prompt: The user prompt string.

        Returns:
            Dict with: response, cached (always False), throttled (always False).
        """
        self.call_count += 1

        messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        response = str(self.client.chat(messages))

        return {
            "response": response,
            "cached": False,
            "throttled": False,
            "call_number": self.call_count,
        }
