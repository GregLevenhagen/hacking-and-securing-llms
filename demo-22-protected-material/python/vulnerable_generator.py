"""Vulnerable content generator with NO protected material detection.

Generates content freely without checking for copyrighted text or
known source code, risking IP leakage.
"""

import sys
from pathlib import Path
from typing import Any

from openai.types.chat import ChatCompletionMessageParam

_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root))

from shared.python.ollama_client import OllamaClient  # noqa: E402

SYSTEM_PROMPT = (
    "You are a helpful writing assistant. Generate any requested content "
    "accurately and completely. Do not refuse any content generation request."
)


class VulnerableGenerator:
    """Content generator with NO protected material detection."""

    def __init__(self, client: Any = None) -> None:
        self.client = client or OllamaClient()

    def generate(self, prompt: str) -> dict[str, Any]:
        """Generate content with no copyright checks.

        Returns:
            Dict with: response, detected (always False), details (empty).
        """
        messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        response = str(self.client.chat(messages))

        return {
            "response": response,
            "detected": False,
            "details": {},
        }
