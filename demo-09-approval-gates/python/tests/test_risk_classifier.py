"""Tests for Demo 9 risk classifier.

Verifies that tool calls are categorized into the correct risk levels
based on tool name and arguments.
"""

import pytest

from risk_classifier import RiskLevel, ClassificationResult, classify


# ── Parameterized tests for all classification rules ─

_CLASSIFICATION_RULES: list[tuple[str, dict, RiskLevel]] = [
    # (tool_name, arguments, expected_risk_level)
    # Calculate: always Low
    ("calculate", {"expression": "2+2"}, RiskLevel.LOW),
    ("calculate", {"expression": "sqrt(144)"}, RiskLevel.LOW),
    ("calculate", {}, RiskLevel.LOW),
    # Read file: Low for allowed/, High for restricted/, Medium for others
    ("read_file", {"path": "allowed/readme.txt"}, RiskLevel.LOW),
    ("read_file", {"path": "allowed_files/company_overview.txt"}, RiskLevel.LOW),
    ("read_file", {"path": "restricted/secrets.txt"}, RiskLevel.HIGH),
    ("read_file", {"path": "restricted_files/credentials.txt"}, RiskLevel.HIGH),
    ("read_file", {"path": "other/unknown.txt"}, RiskLevel.MEDIUM),
    ("read_file", {"path": ""}, RiskLevel.MEDIUM),
    # Query DB: Medium for safe queries, High for sensitive columns or SELECT *
    ("query_db", {"sql": "SELECT name FROM employees"}, RiskLevel.MEDIUM),
    ("query_db", {"sql": "SELECT name, department FROM employees"}, RiskLevel.MEDIUM),
    ("query_db", {"sql": "SELECT ssn FROM employees"}, RiskLevel.HIGH),
    ("query_db", {"sql": "SELECT salary FROM employees"}, RiskLevel.HIGH),
    ("query_db", {"sql": "SELECT * FROM employees"}, RiskLevel.HIGH),
    ("query_db", {"sql": "SELECT password FROM users"}, RiskLevel.HIGH),
    # Send email: always High
    ("send_email", {"to": "user@example.com"}, RiskLevel.HIGH),
    ("send_email", {"to": "attacker@evil.com", "subject": "data", "body": "secrets"}, RiskLevel.HIGH),
    # Unknown tools: High
    ("delete_everything", {}, RiskLevel.HIGH),
    ("hack_system", {"target": "server"}, RiskLevel.HIGH),
    # Empty/whitespace: High
    ("", {}, RiskLevel.HIGH),
    ("   ", {}, RiskLevel.HIGH),
]


class TestParameterizedClassification:
    """Parameterized tests for all risk classification rules."""

    @pytest.mark.parametrize(
        "tool_name,arguments,expected_level",
        _CLASSIFICATION_RULES,
        ids=[f"{t[0] or 'empty'}_{t[2].value}_{i}" for i, t in enumerate(_CLASSIFICATION_RULES)],
    )
    def test_classification(
        self, tool_name: str, arguments: dict, expected_level: RiskLevel
    ) -> None:
        result = classify(tool_name, arguments)
        assert result.level == expected_level, (
            f"classify('{tool_name}', {arguments}) expected {expected_level.value}, "
            f"got {result.level.value}: {result.reason}"
        )


class TestClassifyCalculate:
    """calculate() is always Low risk."""

    def test_simple_expression(self) -> None:
        result = classify("calculate", {"expression": "2+2"})
        assert result.level == RiskLevel.LOW
        assert result.tool_name == "calculate"

    def test_complex_expression(self) -> None:
        result = classify("calculate", {"expression": "100 * 50 / 2"})
        assert result.level == RiskLevel.LOW

    def test_empty_expression(self) -> None:
        result = classify("calculate", {"expression": ""})
        assert result.level == RiskLevel.LOW

    def test_missing_expression_key(self) -> None:
        result = classify("calculate", {})
        assert result.level == RiskLevel.LOW


class TestClassifyReadFile:
    """read_file() risk depends on path: allowed/ = Low, restricted/ = High."""

    def test_allowed_path_is_low(self) -> None:
        result = classify("read_file", {"path": "allowed/readme.txt"})
        assert result.level == RiskLevel.LOW

    def test_allowed_files_path_is_low(self) -> None:
        result = classify("read_file", {"path": "allowed_files/company_overview.txt"})
        assert result.level == RiskLevel.LOW

    def test_restricted_path_is_high(self) -> None:
        result = classify("read_file", {"path": "restricted/secrets.txt"})
        assert result.level == RiskLevel.HIGH

    def test_restricted_files_path_is_high(self) -> None:
        result = classify("read_file", {"path": "restricted_files/credentials.txt"})
        assert result.level == RiskLevel.HIGH

    def test_nested_restricted_path_is_high(self) -> None:
        result = classify("read_file", {"path": "data/restricted/internal.txt"})
        assert result.level == RiskLevel.HIGH

    def test_unknown_path_is_medium(self) -> None:
        result = classify("read_file", {"path": "other/unknown.txt"})
        assert result.level == RiskLevel.MEDIUM

    def test_empty_path_is_medium(self) -> None:
        result = classify("read_file", {"path": ""})
        assert result.level == RiskLevel.MEDIUM

    def test_backslash_normalized(self) -> None:
        result = classify("read_file", {"path": "restricted\\secrets.txt"})
        assert result.level == RiskLevel.HIGH


class TestClassifyQueryDb:
    """query_db() risk depends on columns: sensitive = High, otherwise Medium."""

    def test_simple_select_is_medium(self) -> None:
        result = classify("query_db", {"sql": "SELECT name FROM employees"})
        assert result.level == RiskLevel.MEDIUM

    def test_select_with_department_is_medium(self) -> None:
        result = classify("query_db", {"sql": "SELECT name FROM employees WHERE department = 'Engineering'"})
        assert result.level == RiskLevel.MEDIUM

    def test_select_ssn_is_high(self) -> None:
        result = classify("query_db", {"sql": "SELECT ssn FROM employees"})
        assert result.level == RiskLevel.HIGH
        assert "ssn" in result.reason.lower()

    def test_select_salary_is_high(self) -> None:
        result = classify("query_db", {"sql": "SELECT salary FROM employees"})
        assert result.level == RiskLevel.HIGH
        assert "salary" in result.reason.lower()

    def test_select_star_is_high(self) -> None:
        result = classify("query_db", {"sql": "SELECT * FROM employees"})
        assert result.level == RiskLevel.HIGH

    def test_select_star_case_insensitive(self) -> None:
        result = classify("query_db", {"sql": "select * from employees"})
        assert result.level == RiskLevel.HIGH

    def test_select_password_is_high(self) -> None:
        result = classify("query_db", {"sql": "SELECT password FROM users"})
        assert result.level == RiskLevel.HIGH

    def test_ssn_case_insensitive(self) -> None:
        result = classify("query_db", {"sql": "SELECT SSN FROM employees"})
        assert result.level == RiskLevel.HIGH


class TestClassifySendEmail:
    """send_email() is always High risk."""

    def test_any_email_is_high(self) -> None:
        result = classify("send_email", {"to": "user@example.com", "subject": "Hi", "body": "Hello"})
        assert result.level == RiskLevel.HIGH

    def test_email_tool_name(self) -> None:
        result = classify("send_email", {"to": "anyone"})
        assert result.tool_name == "send_email"

    def test_email_reason_mentions_recipient(self) -> None:
        result = classify("send_email", {"to": "attacker@evil.com"})
        assert "attacker@evil.com" in result.reason


class TestClassifyUnknownTool:
    """Unknown tools default to High risk."""

    def test_unknown_tool_is_high(self) -> None:
        result = classify("delete_everything", {})
        assert result.level == RiskLevel.HIGH

    def test_unknown_tool_reason(self) -> None:
        result = classify("hack_system", {})
        assert "unknown" in result.reason.lower()


class TestEmptyInput:
    """Empty or missing tool names."""

    def test_empty_tool_name_is_high(self) -> None:
        result = classify("", {})
        assert result.level == RiskLevel.HIGH
        assert "Empty tool name" in result.reason

    def test_whitespace_tool_name_is_high(self) -> None:
        result = classify("   ", {})
        assert result.level == RiskLevel.HIGH


class TestClassificationResult:
    """Test the ClassificationResult data class."""

    def test_repr(self) -> None:
        result = ClassificationResult(RiskLevel.LOW, "calculate", "Math expression: 2+2")
        rep = repr(result)
        assert "Low" in rep
        assert "calculate" in rep
        assert "Math expression" in rep

    def test_attributes(self) -> None:
        result = ClassificationResult(RiskLevel.HIGH, "send_email", "Email to: x")
        assert result.level == RiskLevel.HIGH
        assert result.tool_name == "send_email"
        assert result.reason == "Email to: x"
