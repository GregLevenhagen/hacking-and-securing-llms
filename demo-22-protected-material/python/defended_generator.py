"""Defended content generator with Azure Protected Material Detection.

Scans LLM output for copyrighted text and known source code,
blocking or flagging protected content before delivery.
"""

import sys
from pathlib import Path
from typing import Any

from openai.types.chat import ChatCompletionMessageParam

_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root))

from shared.python.ollama_client import OllamaClient  # noqa: E402

SYSTEM_PROMPT = (
    "You are a helpful writing assistant. When asked to reproduce copyrighted "
    "content, instead provide a summary or original paraphrase. "
    "For code, always cite the source and license."
)


class DefendedGenerator:
    """Content generator with Azure Protected Material Detection."""

    def __init__(
        self,
        client: Any = None,
        safety_client: Any = None,
        confidence_threshold: float = 0.5,
    ) -> None:
        """
        Args:
            client: LLM client.
            safety_client: Azure Content Safety client.
            confidence_threshold: Minimum confidence (0.0-1.0) to treat a
                detection as actionable.  Detections below this threshold
                are reported but not blocked.
        """
        self.client = client or OllamaClient()
        self.safety_client = safety_client
        self.confidence_threshold = confidence_threshold

    def generate(self, prompt: str) -> dict[str, Any]:
        """Generate content and scan for protected material.

        Returns:
            Dict with: response, detected (bool), details (dict).
        """
        messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        response = str(self.client.chat(messages))

        # Check for protected material
        detection = self._check_protected(response)

        confidence = detection.get("details", {}).get("confidence", 1.0)
        if detection.get("detected", False) and confidence >= self.confidence_threshold:
            return {
                "response": (
                    f"[BLOCKED] Protected material detected in generated content.\n"
                    f"Details: {detection.get('details', {})}\n"
                    f"Confidence: {confidence:.0%}\n\n"
                    f"The content was redacted to prevent IP/copyright violation."
                ),
                "detected": True,
                "blocked": True,
                "details": detection.get("details", {}),
                "original_response": response,
            }

        if detection.get("detected", False):
            # Below threshold — flag but don't block
            return {
                "response": response,
                "detected": True,
                "blocked": False,
                "details": detection.get("details", {}),
            }

        return {
            "response": response,
            "detected": False,
            "details": detection.get("details", {}),
        }

    def _check_protected(self, text: str) -> dict[str, Any]:
        """Check text for protected material."""
        if not self.safety_client:
            return {"detected": False, "details": {}}

        return self.safety_client.detect_protected_material(text)
