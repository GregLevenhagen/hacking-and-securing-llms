"""Tests for the content_filter validator module."""

import pytest

from validators.content_filter import check, get_patterns, SENSITIVE_PATTERNS


# ── Parameterized tests for all SENSITIVE_PATTERNS ───

_PATTERN_SAMPLES: list[tuple[str, str, str]] = [
    # (pattern_name, sample_output_that_matches, expected_description_substring)
    ("openai_api_key", "Your key: sk-abc123def456ghijklmnop", "OpenAI-style API key"),
    ("aws_access_key", "Key: AKIA1234567890EXAMPLE", "AWS Access Key"),
    ("aws_secret_key", "aws_secret_access_key = wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY01", "AWS Secret"),
    ("generic_api_key", "api_key = abcdefghij1234567890klmn", "Generic API key"),
    ("internal_url", "Visit https://internal.corp.example.com/admin", "Internal/corporate URL"),
    ("internal_url", "Use https://staging.myapp.io/api", "Internal/corporate URL"),
    ("internal_url", "See https://admin.dashboard.io/settings", "Internal/corporate URL"),
    ("secret_marker", "INTERNAL_API_KEY=super-secret-value-123", "Secret marker"),
    ("secret_marker", "DB_PASSWORD: hunter2", "Secret marker"),
    ("secret_marker", "SECRET_KEY=my-secret-123", "Secret marker"),
    ("bearer_token", "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abc", "Bearer"),
    ("connection_string", "postgres://admin:p4ssw0rd@db.internal:5432/prod", "connection string"),
    ("connection_string", "mysql://root:s3cret@mysql.internal:3306/app", "connection string"),
    ("connection_string", "mongodb://user:pass@mongo.example.com:27017/db", "connection string"),
]


class TestParameterizedPatterns:
    """Parameterized tests ensuring every SENSITIVE_PATTERNS entry fires."""

    @pytest.mark.parametrize(
        "pattern_name,sample_output,desc_substring",
        _PATTERN_SAMPLES,
        ids=[f"{t[0]}_{i}" for i, t in enumerate(_PATTERN_SAMPLES)],
    )
    def test_pattern_catches(
        self, pattern_name: str, sample_output: str, desc_substring: str
    ) -> None:
        result = check(sample_output)
        assert result["valid"] is False, (
            f"Pattern '{pattern_name}' should catch: {sample_output!r}"
        )
        assert any(desc_substring.lower() in v.lower() for v in result["violations"]), (
            f"Expected '{desc_substring}' in violations: {result['violations']}"
        )

    def test_every_pattern_has_at_least_one_sample(self) -> None:
        """Ensure every registered pattern is covered by _PATTERN_SAMPLES."""
        covered = {name for name, _, _ in _PATTERN_SAMPLES}
        registered = {p["name"] for p in SENSITIVE_PATTERNS}
        assert registered <= covered, (
            f"Patterns missing from parameterized tests: {registered - covered}"
        )


# ── Existing individual tests ────────────────────────


class TestContentFilterCheck:
    """Tests for check()."""

    def test_openai_api_key_caught(self) -> None:
        output = "Here is your key: sk-abc123def456ghijklmnop"
        result = check(output)
        assert result["valid"] is False
        assert any("OpenAI-style API key" in v for v in result["violations"])
        assert result["validator"] == "content_filter"

    def test_aws_access_key_caught(self) -> None:
        output = "Your AWS key is AKIA1234567890EXAMPLE"
        result = check(output)
        assert result["valid"] is False
        assert any("AWS Access Key" in v for v in result["violations"])

    def test_internal_url_caught(self) -> None:
        output = "Visit https://internal.corp.example.com/admin for details."
        result = check(output)
        assert result["valid"] is False
        assert any("Internal/corporate URL" in v for v in result["violations"])

    def test_private_url_caught(self) -> None:
        output = "The staging endpoint is https://staging.myapp.io/api"
        result = check(output)
        assert result["valid"] is False
        assert any("Internal/corporate URL" in v for v in result["violations"])

    def test_secret_marker_caught(self) -> None:
        output = "Config: INTERNAL_API_KEY=super-secret-value-123"
        result = check(output)
        assert result["valid"] is False
        assert any("Secret marker" in v for v in result["violations"])

    def test_bearer_token_caught(self) -> None:
        output = "Use header: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abc"
        result = check(output)
        assert result["valid"] is False
        assert any("Bearer" in v for v in result["violations"])

    def test_connection_string_caught(self) -> None:
        output = "Connect via postgres://admin:p4ssw0rd@db.internal:5432/prod"
        result = check(output)
        assert result["valid"] is False
        assert any("connection string" in v.lower() for v in result["violations"])

    def test_normal_response_passes(self) -> None:
        output = "The weather today is sunny with a high of 75°F."
        result = check(output)
        assert result["valid"] is True
        assert result["violations"] == []
        assert result["validator"] == "content_filter"

    def test_multiple_violations_all_reported(self) -> None:
        output = (
            "Your API key is sk-abc123def456ghijklmnop and "
            "your AWS key is AKIA1234567890EXAMPLE. "
            "See https://internal.corp.example.com/docs"
        )
        result = check(output)
        assert result["valid"] is False
        assert len(result["violations"]) >= 3

    def test_generic_api_key_assignment_caught(self) -> None:
        output = "api_key = abcdefghij1234567890klmn"
        result = check(output)
        assert result["valid"] is False
        assert any("Generic API key" in v for v in result["violations"])

    def test_empty_output_passes(self) -> None:
        result = check("")
        assert result["valid"] is True
        assert result["violations"] == []


class TestContentFilterEdgeCases:
    """Edge cases: very long outputs, embedded secrets."""

    def test_very_long_clean_output(self) -> None:
        """10,000+ char clean output should pass without error."""
        long_output = "This is a normal response. " * 500
        result = check(long_output)
        assert result["valid"] is True

    def test_very_long_output_with_secret_at_end(self) -> None:
        """Secret buried at the end of a long output is still caught."""
        padding = "Normal text. " * 500
        result = check(padding + "INTERNAL_API_KEY=leaked-secret-value")
        assert result["valid"] is False
        assert any("Secret marker" in v for v in result["violations"])

    def test_whitespace_only_output(self) -> None:
        result = check("   \n\t  ")
        assert result["valid"] is True


class TestGetPatterns:
    """Tests for get_patterns()."""

    def test_returns_list(self) -> None:
        patterns = get_patterns()
        assert isinstance(patterns, list)
        assert len(patterns) > 0

    def test_each_pattern_has_required_fields(self) -> None:
        for p in get_patterns():
            assert "name" in p
            assert "pattern" in p
            assert "description" in p
