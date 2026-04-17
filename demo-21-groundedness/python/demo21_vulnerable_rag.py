"""Vulnerable RAG chatbot with NO groundedness checking.

Answers questions using source articles but does not verify whether
the LLM response is actually grounded in the source material.
This allows hallucinated facts to flow freely.
"""

import sys
from pathlib import Path
from typing import Any

from openai.types.chat import ChatCompletionMessageParam

_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root))

from shared.python.ollama_client import OllamaClient  # noqa: E402

SYSTEM_PROMPT = (
    "You are a helpful research assistant. Answer questions based on the "
    "provided source material. If the source material doesn't contain enough "
    "information, supplement with your general knowledge."
)


class VulnerableRAG:
    """RAG chatbot that does NOT verify groundedness of responses."""

    def __init__(self, client: Any = None) -> None:
        self.client = client or OllamaClient()

    def answer(
        self,
        question: str,
        source_text: str,
    ) -> dict[str, Any]:
        """Answer a question using source text, with no groundedness check.

        Returns:
            Dict with: response, grounded (always None — not checked).
        """
        messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Source Material:\n{source_text}\n\n"
                    f"Question: {question}\n\n"
                    f"Answer the question using the source material."
                ),
            },
        ]

        response = str(self.client.chat(messages))

        return {
            "response": response,
            "grounded": None,
            "groundedness_check": None,
        }
