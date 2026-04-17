"""Defended chatbot with Azure Content Safety scanning.

Scans both user input AND LLM output through Azure AI Content Safety's
analyze_text() API, blocking content above configurable severity thresholds
across 4 categories: Hate, Violence, Sexual, SelfHarm.
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
    "If asked about harmful topics, provide safe and responsible information instead."
)

# Default severity thresholds (0-7 scale): block at medium severity or above
DEFAULT_THRESHOLDS: dict[str, int] = {
    "Hate": 2,
    "Violence": 2,
    "Sexual": 2,
    "SelfHarm": 2,
}


class DefendedChatbot:
    """Chatbot with Azure Content Safety filtering on input and output."""

    def __init__(
        self,
        client: Any = None,
        safety_client: Any = None,
        thresholds: dict[str, int] | None = None,
    ) -> None:
        self.client = client or OllamaClient()
        self.safety_client = safety_client
        self.thresholds = thresholds or dict(DEFAULT_THRESHOLDS)

    def _check_content(self, text: str) -> dict[str, Any]:
        """Analyze text for harmful content across all 4 categories.

        Returns:
            Dict with 'blocked' (bool), 'categories' (dict of results),
            and 'blocked_categories' (list of categories that exceeded threshold).
        """
        if not self.safety_client:
            return {"blocked": False, "categories": {}, "blocked_categories": []}

        categories = self.safety_client.analyze_text(text)
        blocked_cats = []

        for cat_name, result in categories.items():
            threshold = self.thresholds.get(cat_name, 2)
            if result.get("severity", 0) >= threshold:
                blocked_cats.append(cat_name)

        return {
            "blocked": len(blocked_cats) > 0,
            "categories": categories,
            "blocked_categories": blocked_cats,
        }

    def send(self, user_input: str) -> dict[str, Any]:
        """Send user input with content safety checks on both input and output.

        Returns:
            Dict with: response, blocked, categories, input_check, output_check.
        """
        # Step 1: Check user input
        input_check = self._check_content(user_input)
        if input_check["blocked"]:
            return {
                "response": (
                    f"[BLOCKED] Your message was blocked by content safety. "
                    f"Triggered categories: {', '.join(input_check['blocked_categories'])}"
                ),
                "blocked": True,
                "blocked_at": "input",
                "categories": input_check["categories"],
                "input_check": input_check,
                "output_check": None,
            }

        # Step 2: Get LLM response
        messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_input},
        ]
        response = str(self.client.chat(messages))

        # Step 3: Check LLM output
        output_check = self._check_content(response)
        if output_check["blocked"]:
            return {
                "response": (
                    f"[BLOCKED] The LLM response was blocked by content safety. "
                    f"Triggered categories: {', '.join(output_check['blocked_categories'])}"
                ),
                "blocked": True,
                "blocked_at": "output",
                "categories": output_check["categories"],
                "input_check": input_check,
                "output_check": output_check,
            }

        return {
            "response": response,
            "blocked": False,
            "blocked_at": None,
            "categories": output_check.get("categories", {}),
            "input_check": input_check,
            "output_check": output_check,
        }
