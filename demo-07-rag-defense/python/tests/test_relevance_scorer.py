"""Tests for relevance_scorer defense module.

Mocks sentence-transformers to avoid model download.
"""

import math
from unittest.mock import MagicMock

from retrieval_defenses import relevance_scorer


def _make_mock_encoder(raw_score: float) -> MagicMock:
    """Create a mock CrossEncoder that returns a fixed raw logit score."""
    mock = MagicMock()
    mock.predict.return_value = raw_score
    return mock


def _sigmoid(x: float) -> float:
    """Compute sigmoid — mirrors the normalization in relevance_scorer."""
    return 1.0 / (1.0 + math.exp(-x))


class TestScoringInterface:
    """Scorer returns a float score between 0 and 1."""

    def test_high_relevance_score(self) -> None:
        # Raw logit of 3.0 → sigmoid ≈ 0.953
        mock_encoder = _make_mock_encoder(3.0)
        result = relevance_scorer.check("What is PTO?", "PTO policy doc", model=mock_encoder)
        expected = _sigmoid(3.0)
        assert abs(result["score"] - expected) < 0.001
        assert 0.0 <= result["score"] <= 1.0
        assert result["trusted"] is True
        assert result["layer"] == "relevance_scorer"

    def test_low_relevance_score(self) -> None:
        # Raw logit of -3.0 → sigmoid ≈ 0.047
        mock_encoder = _make_mock_encoder(-3.0)
        result = relevance_scorer.check("What is PTO?", "Recipe for cake", model=mock_encoder)
        expected = _sigmoid(-3.0)
        assert abs(result["score"] - expected) < 0.001
        assert result["trusted"] is False
        assert "Low relevance" in result["reason"]

    def test_neutral_relevance_score(self) -> None:
        # Raw logit of 0.0 → sigmoid = 0.5
        mock_encoder = _make_mock_encoder(0.0)
        result = relevance_scorer.check("query", "document", model=mock_encoder)
        assert abs(result["score"] - 0.5) < 0.001
        assert result["trusted"] is True  # 0.5 meets default threshold of 0.5

    def test_score_always_between_0_and_1(self) -> None:
        for raw in [-10.0, -5.0, -1.0, 0.0, 1.0, 5.0, 10.0]:
            mock_encoder = _make_mock_encoder(raw)
            result = relevance_scorer.check("q", "d", model=mock_encoder)
            assert 0.0 <= result["score"] <= 1.0


class TestQueryDocumentPairs:
    """Scorer accepts query + document pairs correctly."""

    def test_predict_called_with_pair(self) -> None:
        mock_encoder = _make_mock_encoder(1.0)
        relevance_scorer.check("my query", "my document", model=mock_encoder)
        mock_encoder.predict.assert_called_once_with([("my query", "my document")])

    def test_different_pairs_hit_encoder(self) -> None:
        mock_encoder = _make_mock_encoder(2.0)
        relevance_scorer.check("first query", "first doc", model=mock_encoder)
        relevance_scorer.check("second query", "second doc", model=mock_encoder)
        assert mock_encoder.predict.call_count == 2


class TestThreshold:
    """Custom threshold parameter changes trust decision."""

    def test_custom_low_threshold(self) -> None:
        # sigmoid(-1.0) ≈ 0.269
        mock_encoder = _make_mock_encoder(-1.0)
        result = relevance_scorer.check("q", "d", threshold=0.2, model=mock_encoder)
        assert result["trusted"] is True  # 0.269 >= 0.2

    def test_custom_high_threshold(self) -> None:
        # sigmoid(1.0) ≈ 0.731
        mock_encoder = _make_mock_encoder(1.0)
        result = relevance_scorer.check("q", "d", threshold=0.9, model=mock_encoder)
        assert result["trusted"] is False  # 0.731 < 0.9


class TestFailOpen:
    """Scorer fails open when sentence-transformers is unavailable."""

    def test_import_error_fails_open(self) -> None:
        # When no model is provided and sentence-transformers isn't installed,
        # the function catches ImportError and fails open
        result = relevance_scorer.check(
            "query", "doc", model=None, model_name="nonexistent/model"
        )
        # Should fail open (either ImportError or other exception caught)
        assert result["trusted"] is True
        assert result["score"] == 0.5

    def test_model_error_fails_open(self) -> None:
        mock_encoder = MagicMock()
        mock_encoder.predict.side_effect = RuntimeError("Model crashed")
        result = relevance_scorer.check("q", "d", model=mock_encoder)
        assert result["trusted"] is True
        assert result["score"] == 0.5
        assert "error" in result["reason"].lower()


class TestEmptyInput:
    """Empty or whitespace query/document inputs."""

    def test_empty_query_untrusted(self) -> None:
        result = relevance_scorer.check("", "some document text")
        assert result["trusted"] is False
        assert result["score"] == 0.0
        assert "Empty query" in result["reason"]

    def test_empty_document_untrusted(self) -> None:
        result = relevance_scorer.check("some query", "")
        assert result["trusted"] is False
        assert result["score"] == 0.0

    def test_whitespace_query_untrusted(self) -> None:
        result = relevance_scorer.check("   ", "doc text")
        assert result["trusted"] is False
        assert result["score"] == 0.0

    def test_both_empty_untrusted(self) -> None:
        result = relevance_scorer.check("", "")
        assert result["trusted"] is False
        assert result["score"] == 0.0
