"""Action guard — gates agent tool execution by risk level.

Reuses Demo 9's risk classifier and approval gate:
  1. Risk classifier — categorizes tool calls as Low/Medium/High
  2. Approval gate — auto-approves Low/Medium, blocks High

For the capstone demo, high-risk actions are auto-denied (no interactive
approval) to enable automated comparison between vulnerable and secure systems.
"""

import sys
from pathlib import Path
from typing import Any, TypedDict

# Add project root and Demo 9 to path
_project_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_project_root))

_demo9_python = _project_root / "demo-09-approval-gates" / "python"
sys.path.insert(0, str(_demo9_python))

from risk_classifier import RiskLevel, classify  # noqa: E402
from approval_gate import ApprovalStatus, check as gate_check  # noqa: E402


class GuardResult(TypedDict):
    allowed: bool
    blocked_by: str
    reason: str


def check(
    tool_name: str,
    arguments: dict[str, Any],
) -> GuardResult:
    """Check whether a tool call should be allowed based on risk classification.

    High-risk actions are auto-denied in this capstone integration.
    Low and Medium risk actions are auto-approved.

    Args:
        tool_name: Name of the tool being called.
        arguments: Arguments passed to the tool.

    Returns:
        GuardResult with allowed=False if the action is High risk.
    """
    # Early return for empty/None tool name
    if not tool_name:
        return GuardResult(
            allowed=False, blocked_by="action_guard", reason="Empty tool name"
        )

    # Use the approval gate with auto-deny for high-risk actions
    gate_result = gate_check(
        tool_name,
        arguments,
        approval_callback=lambda _: False,  # Auto-deny high risk
    )

    if gate_result.status == ApprovalStatus.DENIED:
        return GuardResult(
            allowed=False,
            blocked_by="action_guard",
            reason=f"High-risk action denied: {gate_result.risk.reason}",
        )

    return GuardResult(
        allowed=True,
        blocked_by="",
        reason=gate_result.message,
    )
