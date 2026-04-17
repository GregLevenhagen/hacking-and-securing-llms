"""Azure OpenAI content filter result parser and display.

Sends prompts through Azure OpenAI and parses the content_filter_results
from the API response to show which filters triggered, severity levels,
and finish_reason.
"""

import sys
from pathlib import Path
from typing import Any

_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root))


class FilterResultParser:
    """Parses and formats Azure OpenAI content filter results."""

    def __init__(self, azure_openai_client: Any = None) -> None:
        self.client = azure_openai_client

    def send_and_analyze(
        self, prompt: str, system_prompt: str = "You are a helpful assistant."
    ) -> dict[str, Any]:
        """Send a prompt through Azure OpenAI and analyze filter results.

        Returns:
            Dict with: response, finish_reason, filters_triggered (list),
            content_filter_results (raw), blocked (bool).
        """
        if not self.client:
            return {
                "response": "",
                "finish_reason": "stop",
                "filters_triggered": [],
                "content_filter_results": {},
                "blocked": False,
            }

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]
        result = self.client.chat(messages)

        # Parse which filters triggered
        filters = self._extract_triggered_filters(
            result.get("content_filter_results", {})
        )

        return {
            "response": result.get("content", ""),
            "finish_reason": result.get("finish_reason", "stop"),
            "filters_triggered": filters,
            "content_filter_results": result.get("content_filter_results", {}),
            "blocked": result.get("finish_reason") == "content_filter",
        }

    def _extract_triggered_filters(
        self, filter_results: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Extract list of triggered filters with details."""
        triggered = []
        for category in ("hate", "violence", "sexual", "self_harm"):
            info = filter_results.get(category, {})
            if info.get("filtered", False):
                triggered.append({
                    "category": category,
                    "severity": info.get("severity", "unknown"),
                    "filtered": True,
                })
            elif info.get("severity") and info["severity"] != "safe":
                triggered.append({
                    "category": category,
                    "severity": info["severity"],
                    "filtered": False,
                })

        for special in ("jailbreak", "protected_material_text", "protected_material_code"):
            info = filter_results.get(special, {})
            if info.get("detected", False) or info.get("filtered", False):
                triggered.append({
                    "category": special,
                    "detected": info.get("detected", False),
                    "filtered": info.get("filtered", False),
                })

        return triggered

    def format_pipeline_summary(self, analysis: dict[str, Any]) -> str:
        """Format a human-readable pipeline summary showing each filter stage.

        Returns an ASCII diagram like::

            [INPUT] → [Prompt Shields] → [LLM] → [Output Filters] → [RESPONSE]
                                                    ↳ hate: medium (filtered)
        """
        lines = ["[INPUT] → [Prompt Shields] → [LLM] → [Output Filters] → [RESPONSE]"]
        if analysis["blocked"]:
            lines[0] = "[INPUT] → [Prompt Shields] → [LLM] → [Output Filters] → [BLOCKED]"
        for filt in analysis.get("filters_triggered", []):
            cat = filt["category"]
            if "severity" in filt:
                status = "filtered" if filt.get("filtered") else "flagged"
                lines.append(f"    ↳ {cat}: {filt['severity']} ({status})")
            else:
                lines.append(f"    ↳ {cat}: detected={filt.get('detected', False)}")
        return "\n".join(lines)
