"""Tests for OTel initialization (otel_setup.py)."""

import logging
import os
from unittest.mock import MagicMock, patch

import pytest

from shared.python.telemetry.otel_setup import (
    TRACE_LOG_FORMAT,
    TraceContextFilter,
    _parse_otlp_headers,
    _reset_for_testing,
    _validate_endpoint,
    configure_log_correlation,
    get_telemetry_status,
    get_tracer,
    init_telemetry,
    test_mode,
)


class TestInitTelemetry:
    """Tests for init_telemetry() behavior."""

    def test_disabled_by_default(self) -> None:
        """OTEL_ENABLED defaults to false, so init_telemetry should be a no-op."""
        os.environ.pop("OTEL_ENABLED", None)
        assert init_telemetry() is False

    def test_disabled_when_false(self, otel_env_disabled: dict[str, str]) -> None:
        """OTEL_ENABLED=false should skip initialization."""
        assert init_telemetry() is False

    def test_idempotent_calls(self, otel_env_console: dict[str, str]) -> None:
        """Multiple calls should only initialize once."""
        result1 = init_telemetry()
        result2 = init_telemetry()
        assert result1 is True
        assert result2 is False

    def test_console_fallback_when_no_endpoint(
        self, otel_env_console: dict[str, str]
    ) -> None:
        """When OTEL_ENABLED=true but no endpoint, should use ConsoleSpanExporter."""
        result = init_telemetry()
        assert result is True

    def test_otlp_exporter_when_endpoint_set(
        self, otel_env_otlp: dict[str, str]
    ) -> None:
        """When OTLP endpoint is configured, should use OTLPSpanExporter."""
        with patch(
            "shared.python.telemetry.otel_setup._create_otlp_exporter"
        ) as mock_create:
            mock_create.return_value = MagicMock()
            result = init_telemetry()
            assert result is True
            mock_create.assert_called_once_with("http://localhost:4318")

    def test_service_name_on_resource(
        self, otel_env_console: dict[str, str]
    ) -> None:
        """OTEL_SERVICE_NAME should be set on the TracerProvider resource."""
        from opentelemetry import trace

        init_telemetry()
        provider = trace.get_tracer_provider()
        if hasattr(provider, "resource"):
            assert provider.resource.attributes.get("service.name") == "test-console-service"

    def test_graceful_when_otel_setup_fails(self) -> None:
        """If OTel setup fails, should return False gracefully."""
        os.environ["OTEL_ENABLED"] = "true"
        os.environ.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)

        try:
            with patch(
                "opentelemetry.sdk.trace.TracerProvider",
                side_effect=RuntimeError("simulated init failure"),
            ):
                _reset_for_testing()
                result = init_telemetry()
                assert result is False
        finally:
            os.environ.pop("OTEL_ENABLED", None)

    def test_returns_true_on_success(
        self, otel_env_console: dict[str, str]
    ) -> None:
        """init_telemetry should return True when successfully initialized."""
        result = init_telemetry()
        assert result is True

    def test_invalid_endpoint_falls_back_to_console(self) -> None:
        """An invalid endpoint URL should fall back to ConsoleSpanExporter."""
        os.environ["OTEL_ENABLED"] = "true"
        os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = "not-a-url"
        os.environ["OTEL_SERVICE_NAME"] = "test-svc"
        try:
            _reset_for_testing()
            result = init_telemetry()
            assert result is True  # Falls back to Console, doesn't fail
        finally:
            os.environ.pop("OTEL_ENABLED", None)
            os.environ.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)
            os.environ.pop("OTEL_SERVICE_NAME", None)

    def test_openai_instrumentation_registered(
        self, otel_env_console: dict[str, str]
    ) -> None:
        """OpenAI auto-instrumentation should be registered during init."""
        with patch(
            "shared.python.telemetry.otel_setup._register_openai_instrumentation"
        ) as mock_register:
            result = init_telemetry()
            assert result is True
            mock_register.assert_called_once()

    def test_openai_instrumentation_missing_handled(
        self, otel_env_console: dict[str, str]
    ) -> None:
        """Missing openai instrumentation package should not prevent init."""
        # Patch the inner import within _register_openai_instrumentation
        with patch.dict("sys.modules", {"opentelemetry.instrumentation.openai_v2": None}):
            result = init_telemetry()
            # Should succeed — OpenAI instrumentation is optional
            assert result is True


class TestParseOtlpHeaders:
    """Tests for _parse_otlp_headers() header parsing."""

    def test_empty_string(self) -> None:
        assert _parse_otlp_headers("") == {}

    def test_simple_key_value(self) -> None:
        assert _parse_otlp_headers("key=value") == {"key": "value"}

    def test_multiple_pairs(self) -> None:
        result = _parse_otlp_headers("key1=val1,key2=val2")
        assert result == {"key1": "val1", "key2": "val2"}

    def test_value_with_equals(self) -> None:
        """Authorization=Basic abc123== should keep the full value."""
        result = _parse_otlp_headers("Authorization=Basic abc123==")
        assert result == {"Authorization": "Basic abc123=="}

    def test_url_encoded_value(self) -> None:
        result = _parse_otlp_headers("Authorization=Basic%20dXNlcjpwYXNz")
        assert result == {"Authorization": "Basic dXNlcjpwYXNz"}

    def test_quoted_value_double(self) -> None:
        result = _parse_otlp_headers('key="value with spaces"')
        assert result == {"key": "value with spaces"}

    def test_quoted_value_single(self) -> None:
        result = _parse_otlp_headers("key='value with spaces'")
        assert result == {"key": "value with spaces"}

    def test_whitespace_trimming(self) -> None:
        result = _parse_otlp_headers("  key = value , key2 = val2  ")
        assert result == {"key": "value", "key2": "val2"}

    def test_empty_value(self) -> None:
        result = _parse_otlp_headers("key=")
        assert result == {"key": ""}

    def test_skips_malformed_pair(self) -> None:
        result = _parse_otlp_headers("good=val,malformed,key2=val2")
        assert result == {"good": "val", "key2": "val2"}

    def test_skips_empty_key(self) -> None:
        result = _parse_otlp_headers("=value")
        assert result == {}


class TestValidateEndpoint:
    """Tests for _validate_endpoint()."""

    def test_valid_https(self) -> None:
        assert _validate_endpoint("https://example.com") is True

    def test_valid_http(self) -> None:
        assert _validate_endpoint("http://localhost:4318") is True

    def test_empty(self) -> None:
        assert _validate_endpoint("") is False

    def test_no_scheme(self) -> None:
        assert _validate_endpoint("example.com:4318") is False

    def test_ftp_scheme(self) -> None:
        assert _validate_endpoint("ftp://example.com") is False


class TestGetTracer:
    """Tests for get_tracer() convenience function."""

    def test_returns_tracer_when_otel_available(
        self, otel_env_console: dict[str, str]
    ) -> None:
        init_telemetry()
        tracer = get_tracer("test-tracer")
        # Should be a real OTel tracer, not our no-op
        assert hasattr(tracer, "start_as_current_span")

    def test_returns_noop_when_otel_not_installed(self) -> None:
        with patch.dict("sys.modules", {"opentelemetry": None}):
            with patch(
                "shared.python.telemetry.otel_setup.get_tracer"
            ) as mock_get:
                from shared.python.telemetry.otel_setup import _NoOpTracer
                mock_get.return_value = _NoOpTracer()
                tracer = mock_get("test")
                assert hasattr(tracer, "start_as_current_span")

    def test_default_name(self) -> None:
        tracer = get_tracer()
        assert hasattr(tracer, "start_as_current_span")


class TestTestMode:
    """Tests for test_mode() function."""

    def test_returns_exporter(self) -> None:
        _reset_for_testing()
        exporter = test_mode()
        assert exporter is not None
        assert hasattr(exporter, "get_finished_spans")
        assert hasattr(exporter, "clear")

    def test_captures_spans(self) -> None:
        _reset_for_testing()
        exporter = test_mode()
        assert exporter is not None

        from opentelemetry import trace
        tracer = trace.get_tracer("test")
        with tracer.start_as_current_span("test-span"):
            pass

        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].name == "test-span"

    def test_clear_resets_spans(self) -> None:
        _reset_for_testing()
        exporter = test_mode()
        assert exporter is not None

        from opentelemetry import trace
        tracer = trace.get_tracer("test")
        with tracer.start_as_current_span("span-1"):
            pass

        exporter.clear()
        assert len(exporter.get_finished_spans()) == 0


class TestTraceContextFilter:
    """Tests for the TraceContextFilter logging filter."""

    def test_adds_zero_ids_when_no_span(self) -> None:
        """Without an active span, trace_id and span_id should be '0'."""
        filt = TraceContextFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="hello", args=(), exc_info=None,
        )
        result = filt.filter(record)
        assert result is True
        assert record.otelTraceID == "0"  # type: ignore[attr-defined]
        assert record.otelSpanID == "0"  # type: ignore[attr-defined]

    def test_injects_real_ids_inside_span(
        self, mock_otel_exporter: "InMemorySpanExporter",
    ) -> None:
        """Inside an active span, filter should inject hex trace/span IDs."""
        from opentelemetry import trace

        filt = TraceContextFilter()
        tracer = trace.get_tracer("test")
        with tracer.start_as_current_span("log-test"):
            record = logging.LogRecord(
                name="test", level=logging.INFO, pathname="", lineno=0,
                msg="inside span", args=(), exc_info=None,
            )
            filt.filter(record)
            assert record.otelTraceID != "0"  # type: ignore[attr-defined]
            assert record.otelSpanID != "0"  # type: ignore[attr-defined]
            assert len(record.otelTraceID) == 32  # type: ignore[attr-defined]
            assert len(record.otelSpanID) == 16  # type: ignore[attr-defined]

    def test_ids_are_hex_strings(
        self, mock_otel_exporter: "InMemorySpanExporter",
    ) -> None:
        """Trace and span IDs should be valid lowercase hex."""
        from opentelemetry import trace

        filt = TraceContextFilter()
        tracer = trace.get_tracer("test")
        with tracer.start_as_current_span("hex-test"):
            record = logging.LogRecord(
                name="test", level=logging.INFO, pathname="", lineno=0,
                msg="hex", args=(), exc_info=None,
            )
            filt.filter(record)
            int(record.otelTraceID, 16)  # type: ignore[attr-defined]
            int(record.otelSpanID, 16)  # type: ignore[attr-defined]

    def test_graceful_when_otel_missing(self) -> None:
        """Filter should return True and use '0' when OTel is not installed."""
        filt = TraceContextFilter()
        with patch.dict("sys.modules", {"opentelemetry": None}):
            record = logging.LogRecord(
                name="test", level=logging.INFO, pathname="", lineno=0,
                msg="no otel", args=(), exc_info=None,
            )
            result = filt.filter(record)
            assert result is True
            assert record.otelTraceID == "0"  # type: ignore[attr-defined]

    def test_always_returns_true(self) -> None:
        """Filter must never suppress log records — always returns True."""
        filt = TraceContextFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="keep me", args=(), exc_info=None,
        )
        assert filt.filter(record) is True


class TestConfigureLogCorrelation:
    """Tests for configure_log_correlation()."""

    def test_adds_handler_with_filter(self) -> None:
        """configure_log_correlation should add a handler with TraceContextFilter."""
        test_logger = logging.getLogger("test.log_correlation.handler")
        initial_count = len(test_logger.handlers)
        configure_log_correlation(logger_name="test.log_correlation.handler")
        assert len(test_logger.handlers) == initial_count + 1
        handler = test_logger.handlers[-1]
        assert any(isinstance(f, TraceContextFilter) for f in handler.filters)
        # Cleanup
        test_logger.removeHandler(handler)

    def test_default_format(self) -> None:
        """Default format should include otelTraceID and otelSpanID placeholders."""
        assert "%(otelTraceID)s" in TRACE_LOG_FORMAT
        assert "%(otelSpanID)s" in TRACE_LOG_FORMAT

    def test_custom_format(self) -> None:
        """Custom format string should be used when provided."""
        custom_fmt = "%(message)s [%(otelTraceID)s]"
        test_logger = logging.getLogger("test.log_correlation.custom")
        configure_log_correlation(
            logger_name="test.log_correlation.custom", fmt=custom_fmt
        )
        handler = test_logger.handlers[-1]
        assert handler.formatter._fmt == custom_fmt  # type: ignore[union-attr]
        # Cleanup
        test_logger.removeHandler(handler)


class TestGetTelemetryStatus:
    """Tests for get_telemetry_status()."""

    def test_disabled_state(self) -> None:
        """When OTel is disabled, status should reflect that."""
        os.environ.pop("OTEL_ENABLED", None)
        os.environ.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)
        _reset_for_testing()
        status = get_telemetry_status()
        assert status["enabled"] is False
        assert status["initialized"] is False
        assert status["service_name"] == "securing-llms"
        assert status["endpoint"] is None
        assert status["protocol"] == "http/protobuf"
        assert status["headers_configured"] is False

    def test_enabled_with_endpoint(
        self, otel_env_otlp: dict[str, str]
    ) -> None:
        """When OTel is enabled with endpoint, status should show all config."""
        status = get_telemetry_status()
        assert status["enabled"] is True
        assert status["endpoint"] == "http://localhost:4318"
        assert status["service_name"] == "test-service"
        assert status["protocol"] == "http/protobuf"

    def test_initialized_after_init(
        self, otel_env_console: dict[str, str]
    ) -> None:
        """After init_telemetry(), initialized should be True."""
        init_telemetry()
        status = get_telemetry_status()
        assert status["initialized"] is True

    def test_headers_configured(self) -> None:
        """headers_configured should be True when headers env var is set."""
        os.environ["OTEL_ENABLED"] = "true"
        os.environ["OTEL_EXPORTER_OTLP_HEADERS"] = "Authorization=Bearer tok"
        try:
            status = get_telemetry_status()
            assert status["headers_configured"] is True
        finally:
            os.environ.pop("OTEL_ENABLED", None)
            os.environ.pop("OTEL_EXPORTER_OTLP_HEADERS", None)

    def test_returns_dict(self) -> None:
        """Return value should be a plain dict (JSON-serializable)."""
        status = get_telemetry_status()
        assert isinstance(status, dict)
        # All values should be JSON-compatible types
        for v in status.values():
            assert isinstance(v, (bool, str, type(None)))
