"""Tests for Demo 3 document files — verifies legitimate and poisoned documents."""

from pathlib import Path

import pytest

# Document directories
_demo_root = Path(__file__).resolve().parents[2]
LEGIT_DIR = _demo_root / "documents" / "legitimate"
POISONED_DIR = _demo_root / "documents" / "poisoned"

INJECTION_STRING = "support@evil.example.com"

EXPECTED_LEGIT_FILES = [
    "company_policy.txt",
    "employee_handbook.txt",
    "product_faq.txt",
]


class TestLegitimateDocuments:
    """Tests for the 3 legitimate company documents."""

    def test_all_legitimate_docs_exist(self) -> None:
        for filename in EXPECTED_LEGIT_FILES:
            filepath = LEGIT_DIR / filename
            assert filepath.exists(), f"Missing: {filename}"

    def test_legitimate_docs_are_non_empty(self) -> None:
        for filename in EXPECTED_LEGIT_FILES:
            content = (LEGIT_DIR / filename).read_text()
            assert len(content.strip()) > 0, f"Empty: {filename}"

    def test_legitimate_dir_has_exactly_three_docs(self) -> None:
        txt_files = list(LEGIT_DIR.glob("*.txt"))
        assert len(txt_files) == 3

    def test_legitimate_docs_do_not_contain_injection(self) -> None:
        for filename in EXPECTED_LEGIT_FILES:
            content = (LEGIT_DIR / filename).read_text()
            assert INJECTION_STRING not in content, (
                f"{filename} contains injection string"
            )

    def test_legitimate_docs_contain_acmetech(self) -> None:
        """All legitimate docs should reference AcmeTech."""
        for filename in EXPECTED_LEGIT_FILES:
            content = (LEGIT_DIR / filename).read_text()
            assert "AcmeTech" in content, f"{filename} missing AcmeTech reference"


# Parameterized tests verifying each legitimate doc has expected content keywords
_LEGIT_DOC_KEYWORDS = [
    ("company_policy.txt", ["refund", "return", "30 day", "receipt"]),
    ("product_faq.txt", ["NovaBlade", "warranty", "support"]),
    ("employee_handbook.txt", ["employee", "conduct", "AcmeTech"]),
]


class TestLegitimateDocContentKeywords:
    """Verify each legitimate document contains expected domain-specific keywords."""

    @pytest.mark.parametrize("filename,keywords", _LEGIT_DOC_KEYWORDS)
    def test_doc_contains_keywords(self, filename: str, keywords: list[str]) -> None:
        content = (LEGIT_DIR / filename).read_text().lower()
        for kw in keywords:
            assert kw.lower() in content, f"{filename} missing keyword '{kw}'"


class TestPoisonedDocument:
    """Tests for the poisoned document."""

    def test_poisoned_doc_exists(self) -> None:
        filepath = POISONED_DIR / "poisoned_policy.txt"
        assert filepath.exists()

    def test_poisoned_doc_is_non_empty(self) -> None:
        content = (POISONED_DIR / "poisoned_policy.txt").read_text()
        assert len(content.strip()) > 0

    def test_poisoned_doc_contains_injection_string(self) -> None:
        content = (POISONED_DIR / "poisoned_policy.txt").read_text()
        assert INJECTION_STRING in content

    def test_poisoned_doc_contains_credit_card_lure(self) -> None:
        content = (POISONED_DIR / "poisoned_policy.txt").read_text()
        assert "credit card" in content.lower()

    def test_poisoned_doc_mimics_legitimate_format(self) -> None:
        """Poisoned doc should look like legitimate policy (has headers, sections)."""
        content = (POISONED_DIR / "poisoned_policy.txt").read_text()
        assert "AcmeTech" in content
        assert "Refund" in content


class TestSubtlePoisonedDocument:
    """Tests for the subtle poisoned document — mostly legitimate with hidden injection."""

    def test_subtle_doc_exists(self) -> None:
        filepath = POISONED_DIR / "subtle_policy_update.txt"
        assert filepath.exists()

    def test_subtle_doc_contains_injection(self) -> None:
        content = (POISONED_DIR / "subtle_policy_update.txt").read_text()
        assert INJECTION_STRING in content

    def test_subtle_doc_mostly_legitimate(self) -> None:
        """Subtle doc should have mostly legitimate content (warranty, escalation, etc.)."""
        content = (POISONED_DIR / "subtle_policy_update.txt").read_text()
        assert "AcmeTech" in content
        assert "WARRANTY" in content.upper()
        assert "ESCALATION" in content.upper()

    def test_subtle_doc_injection_is_small_fraction(self) -> None:
        """The injection should be a small part of the overall document."""
        content = (POISONED_DIR / "subtle_policy_update.txt").read_text()
        lines = [l.strip() for l in content.splitlines() if l.strip()]
        injection_lines = [l for l in lines if INJECTION_STRING in l]
        # Injection should be in at most 2 lines of a multi-line document
        assert len(injection_lines) <= 2
        assert len(lines) > 15, "Document should have substantial legitimate content"
