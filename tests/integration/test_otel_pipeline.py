"""Integration tests for OTel pipeline.

Verifies init_telemetry, ConsoleSpanExporter fallback, and
auto-instrumentation registration.
"""

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_project_root = Path(__file__).resolve().parents[2]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from shared.python.telemetry.otel_setup import init_telemetry, _reset_for_testing
from shared.python.telemetry.shutdown import flush_telemetry
from shared.python.telemetry.trace_helpers import trace_demo


@pytest.fixture(autouse=True)
def reset_otel():
    _reset_for_testing()
    yield
    _reset_for_testing()


class TestOtelPipelineIntegration:
    def test_disabled_by_default(self) -> None:
        """OTel should be disabled when OTEL_ENABLED is not set."""
        os.environ.pop("OTEL_ENABLED", None)
        assert init_telemetry() is False

    def test_console_fallback_when_enabled(self) -> None:
        """Should fall back to ConsoleSpanExporter when no endpoint."""
        os.environ["OTEL_ENABLED"] = "true"
        os.environ.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)
        try:
            result = init_telemetry()
            assert result is True
        finally:
            os.environ.pop("OTEL_ENABLED", None)

    def test_flush_after_init(self) -> None:
        """flush_telemetry should work after initialization."""
        os.environ["OTEL_ENABLED"] = "true"
        os.environ.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)
        try:
            init_telemetry()
            result = flush_telemetry()
            # Should return True (provider has force_flush)
            assert result is True
        finally:
            os.environ.pop("OTEL_ENABLED", None)

    def test_trace_demo_works_without_init(self) -> None:
        """@trace_demo should work as a no-op without initialization."""
        @trace_demo("test-demo")
        def my_func() -> int:
            return 42

        assert my_func() == 42

    def test_idempotent_init(self) -> None:
        """Multiple init calls should not fail."""
        os.environ["OTEL_ENABLED"] = "true"
        os.environ.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)
        try:
            assert init_telemetry() is True
            assert init_telemetry() is False  # Already initialized
        finally:
            os.environ.pop("OTEL_ENABLED", None)
