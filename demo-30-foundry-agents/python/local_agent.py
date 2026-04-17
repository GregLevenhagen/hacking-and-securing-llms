"""Local agent with NO guardrails — executes all tool calls unchecked.

Demonstrates the risk of deploying an LLM agent that blindly executes
tool calls without validation, content safety checks, or governance.
The agent trusts all inputs and executes every requested operation.
"""

import json
import sys
from pathlib import Path
from typing import Any

_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root))


# ── Mock tool execution (simulates real tool behavior) ───────────────

def _execute_file_reader(arguments: dict[str, Any]) -> dict[str, Any]:
    """Simulate reading a file — no path validation."""
    file_path = arguments.get("file_path", "")
    return {
        "tool": "file_reader",
        "status": "executed",
        "file_path": file_path,
        "content": f"[Simulated] Contents of {file_path}",
    }


def _execute_email_sender(arguments: dict[str, Any]) -> dict[str, Any]:
    """Simulate sending an email — no recipient validation."""
    return {
        "tool": "email_sender",
        "status": "executed",
        "to": arguments.get("to", ""),
        "subject": arguments.get("subject", ""),
        "sent": True,
    }


def _execute_database_query(arguments: dict[str, Any]) -> dict[str, Any]:
    """Simulate executing a SQL query — no query validation."""
    query = arguments.get("query", "")
    return {
        "tool": "database_query",
        "status": "executed",
        "query": query,
        "rows_affected": 1,
        "result": f"[Simulated] Query executed: {query}",
    }


TOOL_EXECUTORS: dict[str, Any] = {
    "file_reader": _execute_file_reader,
    "email_sender": _execute_email_sender,
    "database_query": _execute_database_query,
}


class LocalAgent:
    """Unguarded agent that executes ALL tool calls without validation.

    Has no content safety checks, no tool governance, no input validation,
    and no session isolation. Every requested tool call is executed blindly.
    """

    def __init__(self) -> None:
        self.execution_log: list[dict[str, Any]] = []
        self.session_data: dict[str, Any] = {}

    def execute(
        self,
        user_request: str,
        tool_calls: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Execute all tool calls with no guardrails.

        Args:
            user_request: The user's original request text.
            tool_calls: List of tool call dicts, each with "tool" (str)
                and "arguments" (dict) keys.

        Returns:
            Dict with: executed (list of results), blocked (empty list),
            total, executed_count, blocked_count.
        """
        executed = []
        blocked: list[dict[str, Any]] = []

        for tc in tool_calls:
            tool_name = tc.get("tool", "")
            arguments = tc.get("arguments", {})

            executor = TOOL_EXECUTORS.get(tool_name)
            if executor is None:
                executed.append({
                    "tool": tool_name,
                    "status": "error",
                    "reason": f"Unknown tool: {tool_name}",
                })
                continue

            result = executor(arguments)
            executed.append(result)
            self.execution_log.append({
                "user_request": user_request,
                "tool": tool_name,
                "arguments": arguments,
                "result": result,
            })

        return {
            "executed": executed,
            "blocked": blocked,
            "total": len(tool_calls),
            "executed_count": len(executed),
            "blocked_count": 0,
        }
