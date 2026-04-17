"""Compare different Azure OpenAI content filter configurations.

Demonstrates how the same prompt produces different results under
different filter strictness levels.
"""

import sys
from pathlib import Path
from typing import Any

_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root))


# Filter configuration presets
FILTER_CONFIGS: dict[str, dict[str, Any]] = {
    "default": {
        "name": "Default (Medium)",
        "description": "All categories at medium severity threshold",
        "thresholds": {"hate": "medium", "violence": "medium", "sexual": "medium", "self_harm": "medium"},
    },
    "strict": {
        "name": "Strict (Low)",
        "description": "All categories at low severity — blocks mild content",
        "thresholds": {"hate": "low", "violence": "low", "sexual": "low", "self_harm": "low"},
    },
    "permissive": {
        "name": "Permissive (High only)",
        "description": "All categories at high severity — only blocks extreme content",
        "thresholds": {"hate": "high", "violence": "high", "sexual": "high", "self_harm": "high"},
    },
    "annotate_only": {
        "name": "Annotate Only",
        "description": "Returns severity scores but never blocks — for monitoring",
        "thresholds": {"hate": "annotate", "violence": "annotate", "sexual": "annotate", "self_harm": "annotate"},
    },
}


class FilterConfigComparer:
    """Compares filter behavior across different configurations."""

    def __init__(self, azure_openai_client: Any = None) -> None:
        self.client = azure_openai_client

    def compare_prompt(
        self,
        prompt: str,
        configs: list[str] | None = None,
    ) -> dict[str, Any]:
        """Send a prompt under different filter configs and compare results.

        Returns:
            Dict mapping config name to result.
        """
        config_names = configs or list(FILTER_CONFIGS.keys())
        results: dict[str, Any] = {}

        for config_name in config_names:
            config = FILTER_CONFIGS.get(config_name)
            if not config:
                continue

            if self.client:
                messages = [
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": prompt},
                ]
                result = self.client.chat(
                    messages,
                    content_filter_config=config["thresholds"],
                )
                results[config_name] = {
                    "config": config,
                    "response": result.get("content", "")[:100],
                    "finish_reason": result.get("finish_reason", "stop"),
                    "blocked": result.get("finish_reason") == "content_filter",
                    "filters": result.get("content_filter_results", {}),
                }
            else:
                results[config_name] = {
                    "config": config,
                    "response": "(Azure OpenAI required)",
                    "finish_reason": "stop",
                    "blocked": False,
                    "filters": {},
                }

        return results
