"""Risk classifier for agent tool calls.

Categorizes each tool call into one of three risk levels:
  - Low:    auto-approve (safe operations like math, reading public files)
  - Medium: log but auto-approve (simple database reads of non-sensitive data)
  - High:   require human approval (email, restricted files, sensitive data queries)

The classification examines both the tool name AND its arguments to determine
the appropriate risk level — the same tool can be Low or High depending on
what it's operating on.
"""

import re
from enum import Enum
from typing import Any


class RiskLevel(Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


class ClassificationResult:
    """Result of classifying a tool call's risk level."""

    def __init__(self, level: RiskLevel, tool_name: str, reason: str) -> None:
        self.level = level
        self.tool_name = tool_name
        self.reason = reason

    def __repr__(self) -> str:
        return f"ClassificationResult(level={self.level.value}, tool={self.tool_name}, reason={self.reason})"


# Columns considered sensitive in the employee database
_SENSITIVE_COLUMNS = {"ssn", "salary", "social_security", "password", "secret"}

# Patterns indicating sensitive column access in SQL
_SENSITIVE_SQL_PATTERN = re.compile(
    r"\b(?:" + "|".join(_SENSITIVE_COLUMNS) + r")\b",
    re.IGNORECASE,
)

# SELECT * also exposes sensitive columns
_SELECT_STAR_PATTERN = re.compile(
    r"SELECT\s+\*",
    re.IGNORECASE,
)


def classify(tool_name: str, arguments: dict[str, Any]) -> ClassificationResult:
    """Classify a tool call by risk level based on tool name and arguments.

    Args:
        tool_name: Name of the tool being called.
        arguments: Arguments passed to the tool.

    Returns:
        ClassificationResult with the risk level, tool name, and reason.
    """
    if not tool_name or not tool_name.strip():
        return ClassificationResult(
            RiskLevel.HIGH, tool_name or "", "Empty tool name — defaulting to High risk"
        )

    if tool_name == "calculate":
        return _classify_calculate(arguments)
    elif tool_name == "read_file":
        return _classify_read_file(arguments)
    elif tool_name == "query_db":
        return _classify_query_db(arguments)
    elif tool_name == "send_email":
        return _classify_send_email(arguments)
    else:
        # Unknown tools default to High risk
        return ClassificationResult(
            RiskLevel.HIGH, tool_name, f"Unknown tool '{tool_name}' — defaulting to High risk"
        )


def _classify_calculate(arguments: dict[str, Any]) -> ClassificationResult:
    """Calculate is always Low risk — sandboxed math only."""
    expr = arguments.get("expression", "")
    return ClassificationResult(
        RiskLevel.LOW, "calculate", f"Math expression: {expr}"
    )


def _classify_read_file(arguments: dict[str, Any]) -> ClassificationResult:
    """Read file risk depends on the path: allowed/ = Low, restricted/ = High."""
    path = arguments.get("path", "")
    normalized = path.replace("\\", "/")

    if normalized.startswith("restricted") or "/restricted" in normalized:
        return ClassificationResult(
            RiskLevel.HIGH, "read_file", f"Restricted path: {path}"
        )
    elif normalized.startswith("allowed") or "/allowed" in normalized:
        return ClassificationResult(
            RiskLevel.LOW, "read_file", f"Allowed path: {path}"
        )
    else:
        # Unknown paths get Medium risk
        return ClassificationResult(
            RiskLevel.MEDIUM, "read_file", f"Unknown path: {path}"
        )


def _classify_query_db(arguments: dict[str, Any]) -> ClassificationResult:
    """Query risk depends on accessed columns: sensitive columns = High, otherwise Medium."""
    sql = arguments.get("sql", "")

    # SELECT * exposes everything including sensitive columns
    if _SELECT_STAR_PATTERN.search(sql):
        return ClassificationResult(
            RiskLevel.HIGH, "query_db", "SELECT * exposes sensitive columns (ssn, salary)"
        )

    # Check for sensitive column names in the query
    if _SENSITIVE_SQL_PATTERN.search(sql):
        matched = _SENSITIVE_SQL_PATTERN.findall(sql)
        return ClassificationResult(
            RiskLevel.HIGH, "query_db", f"Query accesses sensitive columns: {', '.join(matched)}"
        )

    # Non-sensitive SELECT queries are Medium
    return ClassificationResult(
        RiskLevel.MEDIUM, "query_db", f"Simple query: {sql}"
    )


def _classify_send_email(arguments: dict[str, Any]) -> ClassificationResult:
    """Send email is always High risk — potential data exfiltration vector."""
    to = arguments.get("to", "unknown")
    return ClassificationResult(
        RiskLevel.HIGH, "send_email", f"Email to: {to}"
    )
