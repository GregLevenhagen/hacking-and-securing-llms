"""Approval gate for agent tool calls.

Implements the approval flow based on risk classification:
  - Low risk:    auto-approve immediately
  - Medium risk: log the action and auto-approve
  - High risk:   block until explicitly approved or denied

The gate is designed to be pluggable — the approval callback can be
replaced for different UIs (terminal prompt, web modal, API endpoint).
"""

from enum import Enum
from typing import Any, Callable

from risk_classifier import ClassificationResult, RiskLevel, classify


class ApprovalStatus(Enum):
    APPROVED = "approved"
    DENIED = "denied"
    PENDING = "pending"


class ApprovalResult:
    """Result of the approval gate check."""

    def __init__(
        self,
        status: ApprovalStatus,
        risk: ClassificationResult,
        message: str,
    ) -> None:
        self.status = status
        self.risk = risk
        self.message = message

    def __repr__(self) -> str:
        return (
            f"ApprovalResult(status={self.status.value}, "
            f"risk={self.risk.level.value}, message={self.message})"
        )


# Type for the approval callback: takes a ClassificationResult, returns True (approve) or False (deny)
ApprovalCallback = Callable[[ClassificationResult], bool]


def _default_approval_callback(risk: ClassificationResult) -> bool:
    """Default callback that auto-denies all high-risk actions.

    In the terminal demo, this is replaced with a user prompt.
    In the web UI, this is replaced with a modal callback.
    """
    return False


# Action log for Medium-risk actions (and all actions when verbose)
ACTION_LOG: list[dict[str, Any]] = []


def clear_action_log() -> None:
    """Clear the action log."""
    ACTION_LOG.clear()


def get_action_log() -> list[dict[str, Any]]:
    """Return a copy of the action log."""
    return list(ACTION_LOG)


def check(
    tool_name: str,
    arguments: dict[str, Any],
    approval_callback: ApprovalCallback | None = None,
) -> ApprovalResult:
    """Check whether a tool call should be allowed to proceed.

    Args:
        tool_name: Name of the tool being called.
        arguments: Arguments passed to the tool.
        approval_callback: Optional callback for high-risk approval.
            If None, high-risk actions are auto-denied.

    Returns:
        ApprovalResult with the approval status, risk classification, and message.
    """
    risk = classify(tool_name, arguments)

    if risk.level == RiskLevel.LOW:
        result = ApprovalResult(
            ApprovalStatus.APPROVED,
            risk,
            f"[ AUTHORIZED ] {tool_name} — auto-approved (Low risk)",
        )
        _log_action(result)
        return result

    if risk.level == RiskLevel.MEDIUM:
        result = ApprovalResult(
            ApprovalStatus.APPROVED,
            risk,
            f"[ LOGGED ] {tool_name} — auto-approved with logging (Medium risk: {risk.reason})",
        )
        _log_action(result)
        return result

    # High risk — needs explicit approval
    callback = approval_callback or _default_approval_callback
    try:
        approved = callback(risk)
    except Exception:
        # Callback failure defaults to deny for safety
        approved = False

    if approved:
        result = ApprovalResult(
            ApprovalStatus.APPROVED,
            risk,
            f"[ APPROVED ] {tool_name} — human-approved (High risk: {risk.reason})",
        )
    else:
        result = ApprovalResult(
            ApprovalStatus.DENIED,
            risk,
            f"[ DENIED ] {tool_name} — blocked (High risk: {risk.reason})",
        )

    _log_action(result)
    return result


def approve(
    tool_name: str,
    arguments: dict[str, Any],
) -> ApprovalResult:
    """Explicitly approve a tool call (bypasses risk check)."""
    risk = classify(tool_name, arguments)
    result = ApprovalResult(
        ApprovalStatus.APPROVED,
        risk,
        f"[ FORCE APPROVED ] {tool_name} — explicitly approved",
    )
    _log_action(result)
    return result


def deny(
    tool_name: str,
    arguments: dict[str, Any],
) -> ApprovalResult:
    """Explicitly deny a tool call."""
    risk = classify(tool_name, arguments)
    result = ApprovalResult(
        ApprovalStatus.DENIED,
        risk,
        f"[ FORCE DENIED ] {tool_name} — explicitly denied",
    )
    _log_action(result)
    return result


def _log_action(result: ApprovalResult) -> None:
    """Append an action to the log."""
    ACTION_LOG.append({
        "tool": result.risk.tool_name,
        "risk_level": result.risk.level.value,
        "status": result.status.value,
        "reason": result.risk.reason,
        "message": result.message,
    })
