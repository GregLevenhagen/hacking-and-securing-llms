"""Tests for defense layer metrics module."""

from input_defenses.metrics import (
    get_metrics,
    get_total_blocked,
    get_total_passed,
    record,
    reset,
)


class TestRecord:
    """Test recording defense layer results."""

    def setup_method(self) -> None:
        reset()

    def test_record_blocked(self) -> None:
        record("regex_filter", blocked=True)
        m = get_metrics("regex_filter")
        assert m["regex_filter"]["blocked"] == 1
        assert m["regex_filter"]["passed"] == 0

    def test_record_passed(self) -> None:
        record("regex_filter", blocked=False)
        m = get_metrics("regex_filter")
        assert m["regex_filter"]["passed"] == 1
        assert m["regex_filter"]["blocked"] == 0

    def test_record_error(self) -> None:
        record("llm_judge", blocked=False, error=True)
        m = get_metrics("llm_judge")
        assert m["llm_judge"]["errors"] == 1
        assert m["llm_judge"]["passed"] == 0
        assert m["llm_judge"]["blocked"] == 0

    def test_multiple_records_accumulate(self) -> None:
        record("regex_filter", blocked=True)
        record("regex_filter", blocked=True)
        record("regex_filter", blocked=False)
        m = get_metrics("regex_filter")
        assert m["regex_filter"]["blocked"] == 2
        assert m["regex_filter"]["passed"] == 1

    def test_record_multiple_layers(self) -> None:
        record("regex_filter", blocked=True)
        record("llm_judge", blocked=False)
        record("input_sanitizer", blocked=False)
        all_m = get_metrics()
        assert len(all_m) == 3
        assert all_m["regex_filter"]["blocked"] == 1
        assert all_m["llm_judge"]["passed"] == 1


class TestGetMetrics:
    """Test retrieving metrics."""

    def setup_method(self) -> None:
        reset()

    def test_unknown_layer_returns_zeros(self) -> None:
        m = get_metrics("nonexistent_layer")
        assert m["nonexistent_layer"]["blocked"] == 0
        assert m["nonexistent_layer"]["passed"] == 0
        assert m["nonexistent_layer"]["errors"] == 0

    def test_get_all_metrics_empty(self) -> None:
        assert get_metrics() == {}

    def test_get_metrics_returns_copy(self) -> None:
        """Modifying returned metrics doesn't affect internal state."""
        record("regex_filter", blocked=True)
        m = get_metrics("regex_filter")
        m["regex_filter"]["blocked"] = 999
        actual = get_metrics("regex_filter")
        assert actual["regex_filter"]["blocked"] == 1


class TestTotals:
    """Test aggregate total functions."""

    def setup_method(self) -> None:
        reset()

    def test_total_blocked(self) -> None:
        record("regex_filter", blocked=True)
        record("llm_judge", blocked=True)
        record("input_sanitizer", blocked=False)
        assert get_total_blocked() == 2

    def test_total_passed(self) -> None:
        record("regex_filter", blocked=False)
        record("llm_judge", blocked=False)
        record("input_sanitizer", blocked=True)
        assert get_total_passed() == 2

    def test_totals_empty(self) -> None:
        assert get_total_blocked() == 0
        assert get_total_passed() == 0


class TestReset:
    """Test resetting metrics."""

    def setup_method(self) -> None:
        reset()

    def test_reset_all(self) -> None:
        record("regex_filter", blocked=True)
        record("llm_judge", blocked=False)
        reset()
        assert get_metrics() == {}

    def test_reset_single_layer(self) -> None:
        record("regex_filter", blocked=True)
        record("llm_judge", blocked=True)
        reset("regex_filter")
        m = get_metrics()
        assert m["regex_filter"]["blocked"] == 0
        assert m["llm_judge"]["blocked"] == 1

    def test_reset_nonexistent_layer(self) -> None:
        """Resetting a layer that was never recorded is a no-op."""
        reset("nonexistent")
        assert get_metrics() == {}
