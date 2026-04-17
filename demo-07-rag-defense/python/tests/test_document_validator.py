"""Tests for document_validator defense module."""

from datetime import datetime, timedelta

from retrieval_defenses import document_validator


class TestValidDocument:
    """Documents with valid metadata should pass validation."""

    def test_fully_valid_document(self) -> None:
        doc = {
            "author": "hr_department",
            "source": "employee_handbook.txt",
            "date": datetime.now().isoformat(),
            "content": "Our PTO policy allows 20 days per year.",
        }
        result = document_validator.check(doc)
        assert result["trusted"] is True
        assert result["score"] == 1.0
        assert result["layer"] == "document_validator"

    def test_case_insensitive_author(self) -> None:
        doc = {
            "author": "HR_Department",
            "source": "company_policy.txt",
            "date": datetime.now().isoformat(),
        }
        result = document_validator.check(doc)
        assert result["trusted"] is True

    def test_valid_with_recent_date(self) -> None:
        recent = (datetime.now() - timedelta(days=30)).isoformat()
        doc = {"author": "engineering", "source": "internal_docs", "date": recent}
        result = document_validator.check(doc)
        assert result["trusted"] is True
        assert result["score"] == 1.0


class TestUnknownAuthor:
    """Documents with unknown authors should be flagged."""

    def test_unknown_author_flagged(self) -> None:
        doc = {
            "author": "random_attacker",
            "source": "company_policy.txt",
            "date": datetime.now().isoformat(),
        }
        result = document_validator.check(doc)
        assert result["trusted"] is False
        assert "Unknown author" in result["reason"]

    def test_empty_author_flagged(self) -> None:
        doc = {
            "author": "   ",
            "source": "company_policy.txt",
            "date": datetime.now().isoformat(),
        }
        result = document_validator.check(doc)
        assert result["trusted"] is False
        assert "Missing author" in result["reason"]


class TestMissingMetadata:
    """Documents with missing metadata should be flagged."""

    def test_missing_author(self) -> None:
        doc = {"source": "company_policy.txt", "date": datetime.now().isoformat()}
        result = document_validator.check(doc)
        assert result["trusted"] is False
        assert "Missing author" in result["reason"]

    def test_missing_source(self) -> None:
        doc = {"author": "hr_department", "date": datetime.now().isoformat()}
        result = document_validator.check(doc)
        assert result["trusted"] is False
        assert "Missing source" in result["reason"]

    def test_missing_both_author_and_source(self) -> None:
        doc = {"content": "Some text"}
        result = document_validator.check(doc)
        assert result["trusted"] is False
        assert "Missing author" in result["reason"]
        assert "Missing source" in result["reason"]
        # Multiple issues should reduce score further
        assert result["score"] < 0.5


class TestDateValidation:
    """Date-related validation checks."""

    def test_old_document_flagged(self) -> None:
        old_date = (datetime.now() - timedelta(days=400)).isoformat()
        doc = {"author": "hr_department", "source": "company_policy.txt", "date": old_date}
        result = document_validator.check(doc)
        assert result["trusted"] is False
        assert "days old" in result["reason"]

    def test_future_date_flagged(self) -> None:
        future_date = (datetime.now() + timedelta(days=30)).isoformat()
        doc = {"author": "hr_department", "source": "company_policy.txt", "date": future_date}
        result = document_validator.check(doc)
        assert result["trusted"] is False
        assert "future date" in result["reason"]

    def test_invalid_date_format(self) -> None:
        doc = {"author": "hr_department", "source": "company_policy.txt", "date": "not-a-date"}
        result = document_validator.check(doc)
        assert result["trusted"] is False
        assert "Invalid date format" in result["reason"]


class TestCustomAllowlists:
    """Custom trusted_authors/trusted_sources overrides."""

    def test_custom_trusted_authors(self) -> None:
        doc = {"author": "custom_author", "source": "company_policy.txt"}
        # Fails with defaults
        result_default = document_validator.check(doc)
        assert result_default["trusted"] is False
        # Passes with custom allowlist
        result_custom = document_validator.check(doc, trusted_authors=["custom_author"])
        assert result_custom["trusted"] is True

    def test_custom_trusted_sources(self) -> None:
        doc = {"author": "hr_department", "source": "custom_source.txt"}
        result_default = document_validator.check(doc)
        assert result_default["trusted"] is False
        result_custom = document_validator.check(doc, trusted_sources=["custom_source.txt"])
        assert result_custom["trusted"] is True


class TestScoring:
    """Score calculation based on number of issues."""

    def test_no_issues_full_score(self) -> None:
        doc = {
            "author": "admin",
            "source": "product_faq.txt",
            "date": datetime.now().isoformat(),
        }
        result = document_validator.check(doc)
        assert result["score"] == 1.0

    def test_score_decreases_with_issues(self) -> None:
        # One issue
        doc1 = {"author": "unknown", "source": "company_policy.txt"}
        r1 = document_validator.check(doc1)
        # Two issues
        doc2 = {"content": "bare content"}
        r2 = document_validator.check(doc2)
        assert r2["score"] < r1["score"]

    def test_score_never_negative(self) -> None:
        doc = {"author": "bad", "date": "invalid"}
        result = document_validator.check(doc)
        assert result["score"] >= 0.0


class TestEdgeCases:
    """Edge cases for document_validator."""

    def test_empty_dict_returns_untrusted(self) -> None:
        """Empty dict ({}) should be flagged as untrusted."""
        result = document_validator.check({})
        assert result["trusted"] is False
        assert result["score"] == 0.0
        assert "Empty document" in result["reason"]

    def test_only_content_field_present(self) -> None:
        """Document with only content (no author/source) should be untrusted."""
        doc = {"content": "Some policy text about refunds."}
        result = document_validator.check(doc)
        assert result["trusted"] is False
        assert "Missing author" in result["reason"]
        assert "Missing source" in result["reason"]


class TestEmptyInput:
    """Empty or None-like document input."""

    def test_empty_dict_untrusted(self) -> None:
        result = document_validator.check({})
        assert result["trusted"] is False
        assert result["score"] == 0.0
        assert "Empty document" in result["reason"]
