"""Defended RAG chatbot with Azure Groundedness Detection.

Validates every LLM response against source documents using Azure
Content Safety's groundedness detection API, catching hallucinated
facts before they reach the user.
"""

import sys
from pathlib import Path
from typing import Any

from openai.types.chat import ChatCompletionMessageParam

_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root))

from shared.python.ollama_client import OllamaClient  # noqa: E402

SYSTEM_PROMPT = (
    "You are a helpful research assistant. Answer questions based ONLY on the "
    "provided source material. If the information is not in the source, say "
    "'The source material does not contain this information.' Do not speculate."
)


class DefendedRAG:
    """RAG chatbot with Azure Groundedness Detection on every response."""

    def __init__(
        self,
        client: Any = None,
        safety_client: Any = None,
        domain: str = "Generic",
        strictness: str = "warn",
    ) -> None:
        """
        Args:
            client: LLM client.
            safety_client: Azure Content Safety client.
            domain: Groundedness domain (``"Generic"`` or ``"Medical"``).
            strictness: ``"warn"`` appends a warning to ungrounded responses;
                        ``"block"`` replaces them entirely.
        """
        self.client = client or OllamaClient()
        self.safety_client = safety_client
        self.domain = domain
        self.strictness = strictness

    def answer(
        self,
        question: str,
        source_text: str,
        reasoning: bool = False,
    ) -> dict[str, Any]:
        """Answer a question and verify groundedness against source.

        Args:
            question: The user's question.
            source_text: The source material to answer from.
            reasoning: If True, include detailed reasoning about ungrounded segments.

        Returns:
            Dict with: response, grounded, groundedness_check.
        """
        messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Source Material:\n{source_text}\n\n"
                    f"Question: {question}\n\n"
                    f"Answer the question using ONLY the source material."
                ),
            },
        ]

        response = str(self.client.chat(messages))

        # Check groundedness
        groundedness_check = self._check_groundedness(
            response, source_text, reasoning=reasoning
        )

        grounded = groundedness_check.get("grounded", True)
        result: dict[str, Any] = {
            "response": response,
            "grounded": grounded,
            "groundedness_check": groundedness_check,
        }

        if not grounded:
            ungrounded_pct = groundedness_check.get("ungroundedPercentage", 0)
            if self.strictness == "block":
                result["response"] = (
                    f"🚫 [BLOCKED] Response contained {ungrounded_pct:.0f}% "
                    f"ungrounded content and was not shown."
                )
                result["blocked"] = True
            else:
                result["response"] = (
                    f"⚠️ [GROUNDEDNESS WARNING] The response contains "
                    f"{ungrounded_pct:.0f}% ungrounded content.\n\n"
                    f"Original response: {response}"
                )
                result["blocked"] = False
            if reasoning and groundedness_check.get("reasoning"):
                result["response"] += (
                    f"\n\nUngrounded segments:\n"
                    + "\n".join(
                        f"  - {r}" for r in groundedness_check["reasoning"]
                    )
                )

        return result

    def _check_groundedness(
        self,
        text: str,
        source_text: str,
        reasoning: bool = False,
    ) -> dict[str, Any]:
        """Check if text is grounded in the source material."""
        if not self.safety_client:
            return {"grounded": True, "ungroundedPercentage": 0.0, "reasoning": []}

        return self.safety_client.detect_groundedness(
            text=text,
            grounding_sources=[source_text],
            domain=self.domain,
            reasoning=reasoning,
        )
