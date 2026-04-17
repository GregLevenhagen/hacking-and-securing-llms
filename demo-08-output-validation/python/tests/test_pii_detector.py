"""Tests for the pii_detector validator module."""

import pytest

from validators import pii_detector


# --- Parameterized tests for every PII pattern ---
_PII_SAMPLES: list[tuple[str, str, str]] = [
    # (pattern_name, sample_text_containing_pii, expected_description_substring)
    ("ssn", "Employee SSN: 123-45-6789", "Social Security Number"),
    ("ssn", "SSN is 987-65-4321", "Social Security Number"),
    ("ssn", "Record: 456-78-9012 on file", "Social Security Number"),
    ("email", "Contact user@example.com for details", "Email address"),
    ("email", "Email: alice.jones+work@company.co.uk", "Email address"),
    ("email", "Send to admin@internal.corp.example.com", "Email address"),
    ("phone", "Call (555) 123-4567", "Phone number"),
    ("phone", "Phone: 555.123.4567", "Phone number"),
    ("phone", "Dial 555-987-6543", "Phone number"),
    ("phone", "Reach us at 5551234567", "Phone number"),
    ("credit_card", "Card: 4111 1111 1111 1111", "Credit card"),
    ("credit_card", "CC: 4111-1111-1111-1111", "Credit card"),
    ("credit_card", "Pay with 5500000000000004", "Credit card"),
]


class TestParameterizedPII:
    """Parameterized tests ensuring every PII pattern catches relevant content."""

    @pytest.mark.parametrize("pattern_name,sample_text,desc_substr", _PII_SAMPLES)
    def test_pii_caught(
        self, pattern_name: str, sample_text: str, desc_substr: str
    ) -> None:
        result = pii_detector.check(sample_text)
        assert result["valid"] is False, (
            f"Pattern '{pattern_name}' should catch PII in: {sample_text!r}"
        )
        assert any(desc_substr in v for v in result["violations"])

    def test_every_pii_pattern_has_at_least_one_sample(self) -> None:
        """Ensure every registered PII pattern has parameterized coverage."""
        covered = {name for name, _, _ in _PII_SAMPLES}
        registered = {p["name"] for p in pii_detector.PII_PATTERNS}
        assert registered <= covered, (
            f"PII patterns missing from parameterized tests: {registered - covered}"
        )


# --- Benign inputs that should not trigger PII detection ---
_BENIGN_PII_SAMPLES: list[tuple[str, str]] = [
    ("version_number", "The version is 1.2.3 and the build number is 42."),
    ("normal_text", "Our company was founded in 2010 and has grown steadily."),
    ("date_not_ssn", "Meeting on 2024-03-15 at room 301-A."),
    ("partial_number", "The code is 12345 which is only 5 digits."),
]


class TestParameterizedBenignPII:
    """Parameterized tests for inputs that should NOT trigger PII detection."""

    @pytest.mark.parametrize("label,sample_text", _BENIGN_PII_SAMPLES)
    def test_benign_passes(self, label: str, sample_text: str) -> None:
        result = pii_detector.check(sample_text)
        assert result["valid"] is True, (
            f"Benign input '{label}' should pass: {sample_text!r}"
        )


class TestPiiDetectorCheck:
    """Tests for pii_detector.check()."""

    def test_ssn_caught(self) -> None:
        output = "Employee SSN: 123-45-6789"
        result = pii_detector.check(output)
        assert result["valid"] is False
        assert any("Social Security Number" in v for v in result["violations"])
        assert result["validator"] == "pii_detector"

    def test_credit_card_caught(self) -> None:
        output = "Card number: 4111 1111 1111 1111"
        result = pii_detector.check(output)
        assert result["valid"] is False
        assert any("Credit card" in v for v in result["violations"])

    def test_email_caught(self) -> None:
        output = "Contact user@example.com for details."
        result = pii_detector.check(output)
        assert result["valid"] is False
        assert any("Email address" in v for v in result["violations"])

    def test_phone_caught(self) -> None:
        output = "Call us at (555) 123-4567 for support."
        result = pii_detector.check(output)
        assert result["valid"] is False
        assert any("Phone number" in v for v in result["violations"])

    def test_phone_with_dots_caught(self) -> None:
        output = "Phone: 555.123.4567"
        result = pii_detector.check(output)
        assert result["valid"] is False
        assert any("Phone number" in v for v in result["violations"])

    def test_no_pii_passes(self) -> None:
        output = "Our company was founded in 2010 and has grown steadily."
        result = pii_detector.check(output)
        assert result["valid"] is True
        assert result["violations"] == []
        assert result["validator"] == "pii_detector"

    def test_multiple_pii_types_all_reported(self) -> None:
        output = (
            "Employee John Doe, SSN: 123-45-6789, "
            "email: john.doe@company.com, "
            "phone: (555) 987-6543, "
            "card: 4111 1111 1111 1111"
        )
        result = pii_detector.check(output)
        assert result["valid"] is False
        # Should have at least 4 violations (one per PII type)
        assert len(result["violations"]) >= 4

    def test_credit_card_with_dashes_caught(self) -> None:
        output = "CC: 4111-1111-1111-1111"
        result = pii_detector.check(output)
        assert result["valid"] is False
        assert any("Credit card" in v for v in result["violations"])

    def test_empty_output_passes(self) -> None:
        result = pii_detector.check("")
        assert result["valid"] is True
        assert result["violations"] == []

    def test_whitespace_only_passes(self) -> None:
        result = pii_detector.check("   \t\n  ")
        assert result["valid"] is True
        assert result["violations"] == []

    def test_ssn_like_but_not_ssn_passes(self) -> None:
        # Dates in similar format should not be caught by the SSN pattern
        # because SSN requires exactly 3-2-4 digit grouping with word boundaries
        output = "The version is 1.2.3 and the build number is 42."
        result = pii_detector.check(output)
        assert result["valid"] is True


class TestPiiDetectorEdgeCases:
    """Edge cases: very long outputs, PII at boundaries."""

    def test_very_long_clean_output(self) -> None:
        """10,000+ char clean output should pass without error."""
        long_output = "This is a normal response. " * 500
        result = pii_detector.check(long_output)
        assert result["valid"] is True

    def test_very_long_output_with_pii_at_end(self) -> None:
        """PII buried at the end of a long output is still caught."""
        padding = "Normal text. " * 500
        result = pii_detector.check(padding + "SSN: 123-45-6789")
        assert result["valid"] is False

    def test_many_pii_items_all_counted(self) -> None:
        """Output with many SSNs reports all of them."""
        ssns = ", ".join(f"{i:03d}-{i:02d}-{i:04d}" for i in range(100, 106))
        result = pii_detector.check(f"SSNs: {ssns}")
        assert result["valid"] is False
        assert len(result["violations"]) >= 6


class TestGetPatterns:
    """Tests for pii_detector.get_patterns()."""

    def test_returns_list(self) -> None:
        patterns = pii_detector.get_patterns()
        assert isinstance(patterns, list)
        assert len(patterns) == 4  # SSN, email, phone, credit card

    def test_each_pattern_has_required_fields(self) -> None:
        for p in pii_detector.get_patterns():
            assert "name" in p
            assert "pattern" in p
            assert "description" in p
