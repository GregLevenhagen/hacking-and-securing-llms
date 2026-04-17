"""Tests for source_verifier defense module."""

from retrieval_defenses import source_verifier


class TestHighTrustSources:
    """Documents from legitimate/verified paths should get high trust."""

    def test_legitimate_path_high_trust(self) -> None:
        result = source_verifier.check("data/legitimate/company_policy.txt")
        assert result["trusted"] is True
        assert result["score"] == 1.0
        assert result["layer"] == "source_verifier"
        assert "high" in result["reason"]

    def test_verified_path_high_trust(self) -> None:
        result = source_verifier.check("data/verified/handbook.txt")
        assert result["trusted"] is True
        assert result["score"] == 1.0

    def test_legitimate_nested_path(self) -> None:
        result = source_verifier.check("/docs/legitimate/subfolder/file.txt")
        assert result["trusted"] is True


class TestMediumTrustSources:
    """Internal documents should get medium trust."""

    def test_internal_path_trusted(self) -> None:
        result = source_verifier.check("data/internal/memo.txt")
        assert result["trusted"] is True  # 0.7 >= 0.5 threshold
        assert result["score"] == 0.7


class TestLowTrustSources:
    """External/user-uploaded documents should get low trust."""

    def test_external_path_untrusted(self) -> None:
        result = source_verifier.check("data/external/scraped.txt")
        assert result["trusted"] is False  # 0.3 < 0.5 threshold
        assert result["score"] == 0.3

    def test_user_uploaded_untrusted(self) -> None:
        result = source_verifier.check("data/user_uploaded/resume.pdf")
        assert result["trusted"] is False
        assert result["score"] == 0.3


class TestUntrustedSources:
    """Poisoned/unknown documents should get untrusted (0.0)."""

    def test_poisoned_path_untrusted(self) -> None:
        result = source_verifier.check("data/poisoned/injected_doc.txt")
        assert result["trusted"] is False
        assert result["score"] == 0.0
        assert "untrusted" in result["reason"]

    def test_unknown_path_untrusted(self) -> None:
        result = source_verifier.check("data/unknown/mystery.txt")
        assert result["trusted"] is False
        assert result["score"] == 0.0


class TestUnknownPaths:
    """Paths matching no rule should default to low trust."""

    def test_no_matching_rule(self) -> None:
        result = source_verifier.check("data/random/file.txt")
        assert result["trusted"] is False
        assert result["score"] == 0.3  # TRUST_LEVELS["low"]
        assert "no matching trust rule" in result["reason"]

    def test_bare_filename(self) -> None:
        result = source_verifier.check("file.txt")
        assert result["trusted"] is False


class TestCustomThreshold:
    """Custom threshold parameter changes trust decisions."""

    def test_low_threshold_trusts_external(self) -> None:
        result = source_verifier.check("data/external/doc.txt", threshold=0.2)
        assert result["trusted"] is True  # 0.3 >= 0.2
        assert result["score"] == 0.3

    def test_high_threshold_rejects_internal(self) -> None:
        result = source_verifier.check("data/internal/doc.txt", threshold=0.9)
        assert result["trusted"] is False  # 0.7 < 0.9


class TestCustomTrustRules:
    """Custom trust_rules parameter overrides defaults."""

    def test_custom_rules(self) -> None:
        custom_rules = [
            {"pattern": "safe/", "trust_level": "high", "description": "Safe docs"},
            {"pattern": "danger/", "trust_level": "untrusted", "description": "Dangerous"},
        ]
        result = source_verifier.check("data/safe/file.txt", trust_rules=custom_rules)
        assert result["trusted"] is True
        assert result["score"] == 1.0

    def test_first_matching_rule_wins(self) -> None:
        custom_rules = [
            {"pattern": "data/", "trust_level": "high", "description": "All data"},
            {"pattern": "poisoned/", "trust_level": "untrusted", "description": "Poisoned"},
        ]
        # "data/" matches first even though path also contains another pattern
        result = source_verifier.check("data/poisoned/file.txt", trust_rules=custom_rules)
        assert result["trusted"] is True
        assert result["score"] == 1.0


class TestEmptyInput:
    """Empty or whitespace source paths."""

    def test_empty_path_untrusted(self) -> None:
        result = source_verifier.check("")
        assert result["trusted"] is False
        assert result["score"] == 0.0
        assert "Empty source path" in result["reason"]

    def test_whitespace_only_path_untrusted(self) -> None:
        result = source_verifier.check("   ")
        assert result["trusted"] is False
        assert result["score"] == 0.0
