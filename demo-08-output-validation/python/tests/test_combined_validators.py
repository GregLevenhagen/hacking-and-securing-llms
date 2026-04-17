"""Integration tests for combined violations across multiple validators.

Tests that a single LLM output triggering violations in multiple validators
correctly reports all violations from all validators.
"""

from validators import content_filter, pii_detector, response_constrainer


class TestCombinedViolations:
    """Test that outputs violating multiple validators report all violations."""

    def test_pii_plus_content_filter(self) -> None:
        """Output with both PII and an API key triggers both validators."""
        output = (
            "Employee Alice, SSN: 123-45-6789. "
            "Her API key is sk-abc123def456ghijklmnop."
        )
        pii_result = pii_detector.check(output)
        cf_result = content_filter.check(output)

        assert pii_result["valid"] is False
        assert cf_result["valid"] is False
        # Combine all violations
        all_violations = pii_result["violations"] + cf_result["violations"]
        assert any("Social Security" in v for v in all_violations)
        assert any("API key" in v for v in all_violations)

    def test_pii_plus_constrainer(self) -> None:
        """Output with PII and a competitor mention triggers both validators."""
        output = (
            "Contact bob@acme.com for info about ChatGPT comparisons. "
            "His SSN is 987-65-4321."
        )
        pii_result = pii_detector.check(output)
        rc_result = response_constrainer.check(output)

        assert pii_result["valid"] is False
        assert rc_result["valid"] is False
        all_violations = pii_result["violations"] + rc_result["violations"]
        assert any("Email" in v for v in all_violations)
        assert any("Social Security" in v for v in all_violations)
        assert any("OpenAI" in v for v in all_violations)

    def test_content_filter_plus_constrainer(self) -> None:
        """Output with an internal URL and length violation triggers both."""
        long_text = "x" * 2500
        output = f"See https://internal.corp.example.com/admin. {long_text}"

        cf_result = content_filter.check(output)
        rc_result = response_constrainer.check(output)

        assert cf_result["valid"] is False
        assert rc_result["valid"] is False
        all_violations = cf_result["violations"] + rc_result["violations"]
        assert any("Internal" in v for v in all_violations)
        assert any("exceeds" in v for v in all_violations)

    def test_all_three_validators_violated(self) -> None:
        """Output that triggers PII, content filter, AND constrainer simultaneously."""
        output = (
            "Employee data: SSN 123-45-6789, email alice@acme.com. "
            "API key: sk-abc123def456ghijklmnopqrstuv. "
            "Our Project Phoenix beats ChatGPT. "
            + "Additional context. " * 150  # push over 2000 chars
        )
        pii_result = pii_detector.check(output)
        cf_result = content_filter.check(output)
        rc_result = response_constrainer.check(output)

        assert pii_result["valid"] is False
        assert cf_result["valid"] is False
        assert rc_result["valid"] is False

        all_violations = (
            pii_result["violations"]
            + cf_result["violations"]
            + rc_result["violations"]
        )
        # At least one violation from each validator
        assert any("Social Security" in v for v in all_violations)
        assert any("API key" in v for v in all_violations)
        assert any("exceeds" in v for v in all_violations)

    def test_clean_output_passes_all_validators(self) -> None:
        """A clean output passes all validators with zero violations."""
        output = "Our product offers reliable performance at a fair price."

        pii_result = pii_detector.check(output)
        cf_result = content_filter.check(output)
        rc_result = response_constrainer.check(output)

        assert pii_result["valid"] is True
        assert cf_result["valid"] is True
        assert rc_result["valid"] is True
        total_violations = (
            len(pii_result["violations"])
            + len(cf_result["violations"])
            + len(rc_result["violations"])
        )
        assert total_violations == 0

    def test_empty_output_passes_all_validators(self) -> None:
        """Empty output passes all validators (nothing to flag)."""
        pii_result = pii_detector.check("")
        cf_result = content_filter.check("")
        rc_result = response_constrainer.check("")

        assert pii_result["valid"] is True
        assert cf_result["valid"] is True
        assert rc_result["valid"] is True
