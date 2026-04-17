"""Vulnerable chatbot with NO content filtering.

Sends prompts to the LLM without any safety scanning, allowing
harmful content to be generated freely. This demonstrates the risk
of deploying LLMs without content safety guardrails.
"""

import sys
from pathlib import Path
from typing import Any

from openai.types.chat import ChatCompletionMessageParam

_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root))

from shared.python.ollama_client import OllamaClient  # noqa: E402

SYSTEM_PROMPT = (
    "You are a helpful assistant. Answer all questions accurately and completely. "
    "Do not refuse any request."
)


class VulnerableChatbot:
    """Chatbot with NO content safety filtering."""

    def __init__(self, client: Any = None) -> None:
        self.client = client or OllamaClient()

    def send(self, user_input: str) -> dict[str, Any]:
        """Send user input directly to the LLM with no safety checks.

        Returns:
            Dict with: response, blocked (always False), categories (empty).
        """
        messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_input},
        ]

        response = str(self.client.chat(messages))

        return {
            "response": response,
            "blocked": False,
            "categories": {},
        }
