"""Tests for OTel shutdown and flush (shutdown.py)."""

from typing import Any
from unittest.mock import MagicMock, patch

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SimpleSpanProcessor,
    SpanExporter,
    SpanExportResult,
)

from shared.python.telemetry.shutdown import flush_telemetry


class _TestExporter(SpanExporter):
    """In-memory exporter for flush tests."""

    def __init__(self) -> None:
        self.spans: list[Any] = []
        self.flush_count = 0

    def export(self, spans: Any) -> SpanExportResult:
        self.spans.extend(spans)
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        pass

    def force_flush(self, timeout_millis: int = 0) -> bool:
        self.flush_count += 1
        return True


class TestFlushTelemetry:
    """Tests for flush_telemetry()."""

    def test_flushes_when_provider_has_force_flush(self) -> None:
        """Should call force_flush on TracerProvider."""
        mock_provider = MagicMock()
        mock_provider.force_flush.return_value = True

        with patch("opentelemetry.trace.get_tracer_provider", return_value=mock_provider):
            result = flush_telemetry()

        assert result is True
        mock_provider.force_flush.assert_called_once_with(timeout_millis=5000)

    def test_custom_timeout(self) -> None:
        """Should pass custom timeout to force_flush."""
        mock_provider = MagicMock()
        mock_provider.force_flush.return_value = True

        with patch("opentelemetry.trace.get_tracer_provider", return_value=mock_provider):
            flush_telemetry(timeout_millis=10000)

        mock_provider.force_flush.assert_called_once_with(timeout_millis=10000)

    def test_returns_false_when_no_force_flush(self) -> None:
        """Should return False when provider has no force_flush method."""
        mock_provider = MagicMock(spec=[])  # No force_flush

        with patch("opentelemetry.trace.get_tracer_provider", return_value=mock_provider):
            result = flush_telemetry()

        assert result is False

    def test_returns_false_on_exception(self) -> None:
        """Should handle exceptions gracefully."""
        mock_provider = MagicMock()
        mock_provider.force_flush.side_effect = RuntimeError("flush failed")

        with patch("opentelemetry.trace.get_tracer_provider", return_value=mock_provider):
            result = flush_telemetry()

        assert result is False

    def test_returns_false_when_otel_not_installed(self) -> None:
        """Should return False when OTel packages are not installed."""
        with patch.dict("sys.modules", {"opentelemetry": None}):
            result = flush_telemetry()
            assert result is False


class TestFlushWithRealProcessor:
    """Tests for flush_telemetry() with real OTel processors."""

    def test_batch_processor_flush_exports_buffered_spans(self) -> None:
        """force_flush on a BatchSpanProcessor should export buffered spans."""
        exporter = _TestExporter()
        provider = TracerProvider(
            resource=Resource.create({"service.name": "flush-test"})
        )
        provider.add_span_processor(BatchSpanProcessor(exporter))

        trace._TRACER_PROVIDER_SET_ONCE._done = False
        trace.set_tracer_provider(provider)

        tracer = trace.get_tracer("flush-test")
        with tracer.start_as_current_span("buffered-span"):
            pass

        # Spans may be buffered — flush forces export
        result = flush_telemetry()
        assert result is True
        assert len(exporter.spans) >= 1
        assert exporter.spans[0].name == "buffered-span"

        provider.shutdown()

    def test_simple_processor_flush_is_immediate(self) -> None:
        """SimpleSpanProcessor exports immediately — flush is still safe to call."""
        exporter = _TestExporter()
        provider = TracerProvider(
            resource=Resource.create({"service.name": "simple-test"})
        )
        provider.add_span_processor(SimpleSpanProcessor(exporter))

        trace._TRACER_PROVIDER_SET_ONCE._done = False
        trace.set_tracer_provider(provider)

        tracer = trace.get_tracer("simple-test")
        with tracer.start_as_current_span("immediate-span"):
            pass

        # Already exported, but flush should still succeed
        assert len(exporter.spans) == 1
        result = flush_telemetry()
        assert result is True

        provider.shutdown()
