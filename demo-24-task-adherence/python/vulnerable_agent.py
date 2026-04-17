"""Vulnerable agent that executes tool calls without adherence checking.

Executes any tool call the LLM generates, even if it doesn't match
what the user actually asked for.
"""

import sys
from pathlib import Path
from typing import Any

_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root))


class VulnerableAgent:
    """Agent that executes tool calls without verifying alignment."""

    def execute_scenario(self, scenario: dict[str, Any]) -> dict[str, Any]:
        """Execute a tool call without checking adherence.

        Returns:
            Dict with: executed (always True), blocked (always False),
            tool_output, adherence_check (None).
        """
        return {
            "executed": True,
            "blocked": False,
            "tool_name": scenario["tool_name"],
            "tool_input": scenario["tool_input"],
            "tool_output": scenario.get("tool_output", "Action completed"),
            "adherence_check": None,
        }
