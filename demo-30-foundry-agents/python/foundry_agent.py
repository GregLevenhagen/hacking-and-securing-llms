"""Foundry Agent with guardrails — content safety, tool governance, session isolation.

Demonstrates the security controls available in Azure AI Foundry Agents:
  - Content safety pre-screening on user inputs
  - Tool governance: input validation, allowed paths, query whitelisting
  - Session isolation: each session has its own data boundary
  - Audit logging for all tool executions
"""

import json
import re
import sys
from pathlib import Path
from typing import Any

_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root))


# ── Content safety patterns ──────────────────────────────────────────

HARMFUL_INPUT_PATTERNS = [
    r"(?i)(drop\s+table|delete\s+from|truncate)",
    r"(?i)(\/etc\/(passwd|shadow|hosts))",
    r"(?i)(\.\./\.\./|\.\.\\\.\.\\)",  # path traversal
    r"(?i)(attacker|evil\.com|malicious)",
    r"(?i)(admin\s+privileges|role\s*=\s*['\"]?admin)",
    r"(?i)(all\s+other\s+users|user_id\s*!=)",
]

# ── Tool governance rules ────────────────────────────────────────────

# Allowed file paths (whitelist)
ALLOWED_FILE_PATHS = [
    "/app/data/",
    "/app/public/",
    "/tmp/",
]

# Allowed email domains (whitelist)
ALLOWED_EMAIL_DOMAINS = [
    "company.com",
    "example.org",
]

# Blocked SQL patterns
BLOCKED_SQL_PATTERNS = [
    r"(?i)(DROP|DELETE|TRUNCATE|ALTER|UPDATE|INSERT)\s+",
    r"(?i)(GRANT|REVOKE)\s+",
    r"(?i)user_id\s*!=",
    r"(?i)current_user\(\)",
]


def _is_content_safe(text: str) -> tuple[bool, str]:
    """Check user input for harmful content patterns.

    Returns:
        Tuple of (is_safe, reason). If not safe, reason describes the violation.
    """
    for pattern in HARMFUL_INPUT_PATTERNS:
        match = re.search(pattern, text)
        if match:
            return False, f"Content safety violation: detected '{match.group()}'"
    return True, ""


def _validate_file_reader(arguments: dict[str, Any]) -> tuple[bool, str]:
    """Validate file_reader tool arguments."""
    file_path = arguments.get("file_path", "")

    # Block path traversal
    if ".." in file_path:
        return False, f"Path traversal blocked: {file_path}"

    # Whitelist check
    if not any(file_path.startswith(allowed) for allowed in ALLOWED_FILE_PATHS):
        return False, f"File path not in allowed list: {file_path}"

    return True, ""


def _validate_email_sender(arguments: dict[str, Any]) -> tuple[bool, str]:
    """Validate email_sender tool arguments."""
    to_addr = arguments.get("to", "")

    # Extract domain
    if "@" not in to_addr:
        return False, f"Invalid email address: {to_addr}"

    domain = to_addr.split("@")[1].lower()
    if domain not in ALLOWED_EMAIL_DOMAINS:
        return False, f"Email domain not allowed: {domain}"

    return True, ""


def _validate_database_query(arguments: dict[str, Any]) -> tuple[bool, str]:
    """Validate database_query tool arguments."""
    query = arguments.get("query", "")

    for pattern in BLOCKED_SQL_PATTERNS:
        if re.search(pattern, query):
            return False, f"Blocked SQL operation detected in: {query[:60]}"

    return True, ""


TOOL_VALIDATORS: dict[str, Any] = {
    "file_reader": _validate_file_reader,
    "email_sender": _validate_email_sender,
    "database_query": _validate_database_query,
}


# ── Safe tool execution (same simulated behavior as local agent) ─────

def _execute_file_reader(arguments: dict[str, Any]) -> dict[str, Any]:
    file_path = arguments.get("file_path", "")
    return {
        "tool": "file_reader",
        "status": "executed",
        "file_path": file_path,
        "content": f"[Simulated] Contents of {file_path}",
    }


def _execute_email_sender(arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "tool": "email_sender",
        "status": "executed",
        "to": arguments.get("to", ""),
        "subject": arguments.get("subject", ""),
        "sent": True,
    }


def _execute_database_query(arguments: dict[str, Any]) -> dict[str, Any]:
    query = arguments.get("query", "")
    return {
        "tool": "database_query",
        "status": "executed",
        "query": query,
        "rows_affected": 0,
        "result": f"[Simulated] Query executed: {query}",
    }


TOOL_EXECUTORS: dict[str, Any] = {
    "file_reader": _execute_file_reader,
    "email_sender": _execute_email_sender,
    "database_query": _execute_database_query,
}


class FoundryAgent:
    """Guarded agent with Azure AI Foundry-style security controls.

    Enforces:
      - Content safety pre-screening on user inputs
      - Tool governance: input validation per tool type
      - Session isolation: each agent instance has its own session
      - Audit logging: all executions and blocks are logged

    Args:
        session_id: Unique session identifier for isolation.
        safety_client: Optional content safety client for advanced scanning.
    """

    def __init__(
        self,
        session_id: str = "default",
        safety_client: Any = None,
    ) -> None:
        self.session_id = session_id
        self.safety_client = safety_client
        self.execution_log: list[dict[str, Any]] = []
        self.block_log: list[dict[str, Any]] = []
        self.session_data: dict[str, Any] = {"session_id": session_id}

    def execute(
        self,
        user_request: str,
        tool_calls: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Execute tool calls with full guardrails.

        Args:
            user_request: The user's original request text.
            tool_calls: List of tool call dicts, each with "tool" (str)
                and "arguments" (dict) keys.

        Returns:
            Dict with: executed (list), blocked (list), total,
            executed_count, blocked_count.
        """
        executed = []
        blocked = []

        # Step 1: Content safety check on user request
        is_safe, reason = _is_content_safe(user_request)
        if not is_safe:
            block_entry = {
                "stage": "content_safety",
                "reason": reason,
                "user_request": user_request,
            }
            blocked.append(block_entry)
            self.block_log.append(block_entry)

            return {
                "executed": executed,
                "blocked": blocked,
                "total": len(tool_calls),
                "executed_count": 0,
                "blocked_count": len(tool_calls),
            }

        # Step 2: Validate and execute each tool call
        for tc in tool_calls:
            tool_name = tc.get("tool", "")
            arguments = tc.get("arguments", {})

            # Check tool exists
            executor = TOOL_EXECUTORS.get(tool_name)
            if executor is None:
                block_entry = {
                    "tool": tool_name,
                    "stage": "tool_governance",
                    "reason": f"Unknown tool: {tool_name}",
                }
                blocked.append(block_entry)
                self.block_log.append(block_entry)
                continue

            # Validate tool inputs
            validator = TOOL_VALIDATORS.get(tool_name)
            if validator:
                is_valid, validation_reason = validator(arguments)
                if not is_valid:
                    block_entry = {
                        "tool": tool_name,
                        "stage": "tool_governance",
                        "reason": validation_reason,
                        "arguments": arguments,
                    }
                    blocked.append(block_entry)
                    self.block_log.append(block_entry)
                    continue

            # Execute the tool call
            result = executor(arguments)
            executed.append(result)
            self.execution_log.append({
                "session_id": self.session_id,
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
            "blocked_count": len(blocked),
        }

    def get_session_info(self) -> dict[str, Any]:
        """Return session metadata for auditing."""
        return {
            "session_id": self.session_id,
            "total_executions": len(self.execution_log),
            "total_blocks": len(self.block_log),
        }

    def get_audit_trail(self) -> list[dict[str, Any]]:
        """Return a merged audit trail (executions + blocks) in order.

        Each entry includes ``action`` ("executed" or "blocked") and the
        original session_id for cross-session forensics.
        """
        trail: list[dict[str, Any]] = []
        for entry in self.execution_log:
            trail.append({**entry, "action": "executed"})
        for entry in self.block_log:
            trail.append({**entry, "action": "blocked", "session_id": self.session_id})
        return trail
