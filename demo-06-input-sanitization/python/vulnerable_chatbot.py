"""Vulnerable customer support chatbot with no input defenses.

Accepts user input directly and sends it to the LLM with a permissive
system prompt. Because there are no input defense layers (regex filter,
sanitizer, LLM judge, etc.), prompt injection attacks succeed easily.
"""

import sys
from pathlib import Path
from typing import Any

from openai.types.chat import ChatCompletionMessageParam

# Add project root to path for shared imports
_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root))

from shared.python.ollama_client import OllamaClient  # noqa: E402

# Permissive system prompt — susceptible to prompt injection because
# the chatbot has no input defense layers to filter malicious input.
SYSTEM_PROMPT = (
    "You are a helpful customer support assistant for AcmeTech. "
    "Answer questions about our products and services. "
    "Be friendly and helpful."
)


class VulnerableChatbot:
    """Customer support chatbot with NO input defenses."""

    def __init__(self, client: Any = None) -> None:
        self.client = client or OllamaClient()
        self.system_prompt = SYSTEM_PROMPT

    def send(self, user_input: str) -> dict[str, Any]:
        """Send user input directly to the LLM with no filtering.

        Returns:
            Dict with keys: response, blocked, blocked_by, defense_results
        """
        messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_input},
        ]

        response = str(self.client.chat(messages))

        return {
            "response": response,
            "blocked": False,
            "blocked_by": None,
            "defense_results": [],
        }
