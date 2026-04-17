"""Tests for Demo 9 approval gate.

Verifies the approval flow: auto-approve Low, log-and-approve Medium,
block-until-approved High.
"""

from approval_gate import (
    ApprovalStatus,
    ApprovalResult,
    ACTION_LOG,
    check,
    approve,
    deny,
    clear_action_log,
    get_action_log,
)
from risk_classifier import ClassificationResult, RiskLevel


class TestCheckLowRisk:
    """Low-risk actions are auto-approved immediately."""

    def setup_method(self) -> None:
        clear_action_log()

    def test_calculate_auto_approved(self) -> None:
        result = check("calculate", {"expression": "2+2"})
        assert result.status == ApprovalStatus.APPROVED
        assert result.risk.level == RiskLevel.LOW

    def test_allowed_file_auto_approved(self) -> None:
        result = check("read_file", {"path": "allowed/readme.txt"})
        assert result.status == ApprovalStatus.APPROVED
        assert result.risk.level == RiskLevel.LOW

    def test_low_risk_message_contains_authorized(self) -> None:
        result = check("calculate", {"expression": "1+1"})
        assert "AUTHORIZED" in result.message

    def test_low_risk_is_logged(self) -> None:
        check("calculate", {"expression": "5*5"})
        log = get_action_log()
        assert len(log) == 1
        assert log[0]["status"] == "approved"
        assert log[0]["risk_level"] == "Low"


class TestCheckMediumRisk:
    """Medium-risk actions are logged but auto-approved."""

    def setup_method(self) -> None:
        clear_action_log()

    def test_simple_query_auto_approved(self) -> None:
        result = check("query_db", {"sql": "SELECT name FROM employees"})
        assert result.status == ApprovalStatus.APPROVED
        assert result.risk.level == RiskLevel.MEDIUM

    def test_medium_risk_message_contains_logged(self) -> None:
        result = check("query_db", {"sql": "SELECT name FROM employees"})
        assert "LOGGED" in result.message

    def test_medium_risk_is_logged(self) -> None:
        check("query_db", {"sql": "SELECT department FROM employees"})
        log = get_action_log()
        assert len(log) == 1
        assert log[0]["risk_level"] == "Medium"

    def test_unknown_path_medium_auto_approved(self) -> None:
        result = check("read_file", {"path": "other/file.txt"})
        assert result.status == ApprovalStatus.APPROVED
        assert result.risk.level == RiskLevel.MEDIUM


class TestCheckHighRisk:
    """High-risk actions block until approved or denied via callback."""

    def setup_method(self) -> None:
        clear_action_log()

    def test_high_risk_default_denied(self) -> None:
        """Without callback, high-risk actions are auto-denied."""
        result = check("send_email", {"to": "user@example.com", "subject": "Hi", "body": "Hello"})
        assert result.status == ApprovalStatus.DENIED
        assert result.risk.level == RiskLevel.HIGH

    def test_high_risk_approved_via_callback(self) -> None:
        """When callback returns True, high-risk action is approved."""
        result = check("send_email", {"to": "user@example.com"}, approval_callback=lambda _: True)
        assert result.status == ApprovalStatus.APPROVED
        assert result.risk.level == RiskLevel.HIGH
        assert "APPROVED" in result.message

    def test_high_risk_denied_via_callback(self) -> None:
        """When callback returns False, high-risk action is denied."""
        result = check("send_email", {"to": "user@example.com"}, approval_callback=lambda _: False)
        assert result.status == ApprovalStatus.DENIED
        assert result.risk.level == RiskLevel.HIGH
        assert "DENIED" in result.message

    def test_restricted_file_high_risk(self) -> None:
        result = check("read_file", {"path": "restricted/secrets.txt"})
        assert result.status == ApprovalStatus.DENIED
        assert result.risk.level == RiskLevel.HIGH

    def test_sensitive_query_high_risk(self) -> None:
        result = check("query_db", {"sql": "SELECT ssn FROM employees"})
        assert result.status == ApprovalStatus.DENIED
        assert result.risk.level == RiskLevel.HIGH

    def test_high_risk_is_logged(self) -> None:
        check("send_email", {"to": "x@y.com"})
        log = get_action_log()
        assert len(log) == 1
        assert log[0]["status"] == "denied"
        assert log[0]["risk_level"] == "High"

    def test_callback_receives_classification_result(self) -> None:
        """The callback receives the ClassificationResult for inspection."""
        received: list[ClassificationResult] = []

        def capture_callback(risk: ClassificationResult) -> bool:
            received.append(risk)
            return True

        check("send_email", {"to": "test@test.com"}, approval_callback=capture_callback)
        assert len(received) == 1
        assert received[0].tool_name == "send_email"
        assert received[0].level == RiskLevel.HIGH


class TestApproveAndDeny:
    """Test explicit approve() and deny() functions."""

    def setup_method(self) -> None:
        clear_action_log()

    def test_explicit_approve(self) -> None:
        result = approve("send_email", {"to": "user@example.com"})
        assert result.status == ApprovalStatus.APPROVED
        assert "FORCE APPROVED" in result.message

    def test_explicit_deny(self) -> None:
        result = deny("send_email", {"to": "user@example.com"})
        assert result.status == ApprovalStatus.DENIED
        assert "FORCE DENIED" in result.message

    def test_approve_logs(self) -> None:
        approve("calculate", {"expression": "1+1"})
        log = get_action_log()
        assert len(log) == 1
        assert log[0]["status"] == "approved"

    def test_deny_logs(self) -> None:
        deny("read_file", {"path": "restricted/x.txt"})
        log = get_action_log()
        assert len(log) == 1
        assert log[0]["status"] == "denied"


class TestActionLog:
    """Test the action log management."""

    def setup_method(self) -> None:
        clear_action_log()

    def test_clear_action_log(self) -> None:
        check("calculate", {"expression": "1+1"})
        assert len(get_action_log()) == 1
        clear_action_log()
        assert len(get_action_log()) == 0

    def test_get_action_log_returns_copy(self) -> None:
        check("calculate", {"expression": "1+1"})
        log = get_action_log()
        log.clear()
        assert len(get_action_log()) == 1  # original unaffected

    def test_multiple_actions_logged(self) -> None:
        check("calculate", {"expression": "1+1"})
        check("query_db", {"sql": "SELECT name FROM employees"})
        check("send_email", {"to": "x@y.com"})
        log = get_action_log()
        assert len(log) == 3
        assert log[0]["risk_level"] == "Low"
        assert log[1]["risk_level"] == "Medium"
        assert log[2]["risk_level"] == "High"


class TestCallbackEdgeCases:
    """Edge cases for approval callbacks."""

    def setup_method(self) -> None:
        clear_action_log()

    def test_callback_raising_exception_denies(self) -> None:
        """If the callback raises, the action should be denied safely."""
        def exploding_callback(risk: ClassificationResult) -> bool:
            raise RuntimeError("Callback crashed!")

        result = check("send_email", {"to": "test@test.com"}, approval_callback=exploding_callback)
        # Should not crash — should default to denied
        assert result.status == ApprovalStatus.DENIED

    def test_callback_returning_non_bool_truthy(self) -> None:
        """Callback returning truthy non-bool should still approve."""
        result = check("send_email", {"to": "test@test.com"}, approval_callback=lambda _: 1)  # type: ignore[arg-type,return-value]
        assert result.status == ApprovalStatus.APPROVED

    def test_callback_returning_none_denies(self) -> None:
        """Callback returning None (falsy) should deny."""
        result = check("send_email", {"to": "test@test.com"}, approval_callback=lambda _: None)  # type: ignore[arg-type,return-value]
        assert result.status == ApprovalStatus.DENIED


class TestApprovalResult:
    """Test the ApprovalResult data class."""

    def test_repr(self) -> None:
        from risk_classifier import ClassificationResult
        risk = ClassificationResult(RiskLevel.HIGH, "send_email", "Email to: test")
        result = ApprovalResult(ApprovalStatus.DENIED, risk, "Blocked")
        rep = repr(result)
        assert "denied" in rep
        assert "High" in rep
