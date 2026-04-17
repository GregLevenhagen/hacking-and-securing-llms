"""Tests for custom category scanning."""

import json
from pathlib import Path

from shared.python.testing.mock_azure import MockContentSafetyClient
from standard_scanner import StandardScanner
from rapid_scanner import RapidScanner


CATEGORIES_DIR = Path(__file__).resolve().parents[2] / "categories"


class TestCategoryDefinitions:
    def test_financial_fraud_loads(self) -> None:
        """Financial fraud category should load from JSON."""
        scanner = StandardScanner()
        cat = scanner.load_category(str(CATEGORIES_DIR / "financial_fraud.json"))
        assert cat["category_name"] == "financial_fraud"
        assert len(cat["examples"]) >= 3
        assert len(cat["counter_examples"]) >= 3

    def test_competitor_mention_loads(self) -> None:
        """Competitor mention category should load."""
        scanner = StandardScanner()
        cat = scanner.load_category(str(CATEGORIES_DIR / "competitor_mention.json"))
        assert cat["category_name"] == "competitor_mention"

    def test_pii_leakage_loads(self) -> None:
        """PII leakage category should load."""
        scanner = RapidScanner()
        cat = scanner.load_category(str(CATEGORIES_DIR / "pii_leakage.json"))
        assert cat["category_name"] == "pii_leakage"


class TestStandardScanner:
    def test_detects_fraud_content(
        self, mock_detecting: MockContentSafetyClient
    ) -> None:
        """Should detect financial fraud content."""
        scanner = StandardScanner(safety_client=mock_detecting)
        result = scanner.scan("Set up a fraud scheme to launder money", "financial_fraud")
        assert result["detected"] is True
        assert result["category"] == "financial_fraud"

    def test_clean_content_passes(
        self, mock_clean: MockContentSafetyClient
    ) -> None:
        """Clean content should pass."""
        scanner = StandardScanner(safety_client=mock_clean)
        result = scanner.scan("How to detect fraud?", "financial_fraud")
        assert result["detected"] is False

    def test_no_safety_client(self) -> None:
        """Without safety client, should pass everything."""
        scanner = StandardScanner(safety_client=None)
        result = scanner.scan("anything", "any_category")
        assert result["detected"] is False


class TestRapidScanner:
    def test_detects_pii(
        self, mock_detecting: MockContentSafetyClient
    ) -> None:
        """Should detect PII content."""
        scanner = RapidScanner(safety_client=mock_detecting)
        result = scanner.scan("His SSN is 123-45-6789", "pii_leakage")
        assert result["detected"] is True

    def test_returns_confidence(
        self, mock_detecting: MockContentSafetyClient
    ) -> None:
        """Should return confidence score."""
        scanner = RapidScanner(safety_client=mock_detecting)
        result = scanner.scan("Credit card: 4111-1111", "pii_leakage")
        assert result["confidence"] > 0.0

    def test_records_api_calls(
        self, mock_clean: MockContentSafetyClient
    ) -> None:
        """Should record API calls for verification."""
        scanner = RapidScanner(safety_client=mock_clean)
        scanner.scan("test", "test_category")
        assert len(mock_clean.call_history) == 1
        assert mock_clean.call_history[0]["method"] == "analyze_custom_category"


class TestEdgeCases:
    def test_load_category_invalid_path_raises(self) -> None:
        """Loading a nonexistent category file should raise FileNotFoundError."""
        scanner = StandardScanner()
        try:
            scanner.load_category("/nonexistent/path/category.json")
            assert False, "Expected FileNotFoundError"
        except FileNotFoundError:
            pass

    def test_scan_empty_text(
        self, mock_clean: MockContentSafetyClient
    ) -> None:
        """Scanning an empty string should not crash and should return clean."""
        scanner = StandardScanner(safety_client=mock_clean)
        result = scanner.scan("", "financial_fraud")
        assert result["detected"] is False
        assert result["category"] == "financial_fraud"

    def test_rapid_scanner_no_safety_client_returns_zero_confidence(self) -> None:
        """RapidScanner without a safety client should return 0.0 confidence."""
        scanner = RapidScanner(safety_client=None)
        result = scanner.scan("anything with PII like SSN 123-45-6789", "pii_leakage")
        assert result["detected"] is False
        assert result["confidence"] == 0.0
        assert result["category"] == "pii_leakage"

    def test_confidence_threshold_filters_low_confidence(
        self, mock_detecting: MockContentSafetyClient
    ) -> None:
        """Detections below confidence threshold should set detected=False."""
        scanner = StandardScanner(safety_client=mock_detecting)
        result = scanner.scan("fraud", "financial_fraud", confidence_threshold=0.99)
        # Raw detection may be True but above_threshold should be False
        assert result["above_threshold"] is False

    def test_scan_batch_returns_all_results(
        self, mock_clean: MockContentSafetyClient
    ) -> None:
        """scan_batch should return one result per input text."""
        scanner = StandardScanner(safety_client=mock_clean)
        results = scanner.scan_batch(["text1", "text2", "text3"], "test_cat")
        assert len(results) == 3
        assert all(r["category"] == "test_cat" for r in results)
