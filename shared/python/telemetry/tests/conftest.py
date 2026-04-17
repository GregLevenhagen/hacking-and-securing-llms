"""Reusable pytest fixtures for OTel telemetry tests.

Uses a custom InMemorySpanExporter (compatible with all OTel SDK versions)
and patches the global TracerProvider to work around OTel's restriction
on setting the provider more than once per process.
"""

import os
import sys
from pathlib import Path
from typing import Any, Generator

import pytest
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    SimpleSpanProcessor,
    SpanExporter,
    SpanExportResult,
)

# Ensure project root is on sys.path
_project_root = Path(__file__).resolve().parents[4]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


class InMemorySpanExporter(SpanExporter):
    """Simple in-memory span exporter for testing.

    Compatible with all opentelemetry-sdk versions (the built-in
    InMemorySpanExporter was moved/removed across versions).
    """

    def __init__(self) -> None:
        self._spans: list[Any] = []

    def export(self, spans: Any) -> SpanExportResult:
        self._spans.extend(spans)
        return SpanExportResult.SUCCESS

    def get_finished_spans(self) -> list[Any]:
        return list(self._spans)

    def clear(self) -> None:
        self._spans.clear()

    def shutdown(self) -> None:
        pass

    def force_flush(self, timeout_millis: int = 0) -> bool:
        return True


@pytest.fixture
def mock_otel_exporter() -> Generator[InMemorySpanExporter, None, None]:
    """Provide an InMemorySpanExporter that captures emitted spans.

    Bypasses OTel's one-set restriction on the global TracerProvider by
    resetting the internal _done flag, allowing each test to get a fresh provider.
    """
    exporter = InMemorySpanExporter()
    provider = TracerProvider(
        resource=Resource.create({"service.name": "test-service"})
    )
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    # Reset the one-shot guard so we can set a new provider
    trace._TRACER_PROVIDER_SET_ONCE._done = False
    trace.set_tracer_provider(provider)

    yield exporter

    provider.shutdown()


@pytest.fixture
def otel_env_otlp() -> Generator[dict[str, str], None, None]:
    """Set OTel env vars for OTLP mode and clean up after."""
    env_vars = {
        "OTEL_ENABLED": "true",
        "OTEL_SERVICE_NAME": "test-service",
        "OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4318",
        "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf",
    }
    original = {}
    for key, value in env_vars.items():
        original[key] = os.environ.get(key)
        os.environ[key] = value

    yield env_vars

    for key, orig_value in original.items():
        if orig_value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = orig_value


@pytest.fixture
def otel_env_console() -> Generator[dict[str, str], None, None]:
    """Set OTel env vars for console mode (no OTLP endpoint)."""
    env_vars = {
        "OTEL_ENABLED": "true",
        "OTEL_SERVICE_NAME": "test-console-service",
    }
    original = {}
    for key, value in env_vars.items():
        original[key] = os.environ.get(key)
        os.environ[key] = value

    otlp_orig = os.environ.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)

    yield env_vars

    for key, orig_value in original.items():
        if orig_value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = orig_value

    if otlp_orig is not None:
        os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = otlp_orig


@pytest.fixture
def otel_env_disabled() -> Generator[dict[str, str], None, None]:
    """Set OTel env vars with OTEL_ENABLED=false."""
    env_vars = {"OTEL_ENABLED": "false"}
    original = {}
    for key, value in env_vars.items():
        original[key] = os.environ.get(key)
        os.environ[key] = value

    yield env_vars

    for key, orig_value in original.items():
        if orig_value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = orig_value


@pytest.fixture
def traced_context(
    mock_otel_exporter: InMemorySpanExporter,
) -> Generator[tuple[Any, InMemorySpanExporter], None, None]:
    """Provide a fresh tracer and exporter pair for assertions.

    Usage:
        def test_something(traced_context):
            tracer, exporter = traced_context
            with tracer.start_as_current_span("test"):
                ...
            spans = exporter.get_finished_spans()
    """
    tracer = trace.get_tracer("test-helper")
    yield tracer, mock_otel_exporter


@pytest.fixture(autouse=True)
def reset_otel_init() -> Generator[None, None, None]:
    """Reset the init_telemetry() initialized flag and TracerProvider between tests."""
    from shared.python.telemetry.otel_setup import _reset_for_testing

    _reset_for_testing()
    # Also reset the OTel provider guard so the next test can set a fresh one
    trace._TRACER_PROVIDER_SET_ONCE._done = False
    yield
    _reset_for_testing()
    trace._TRACER_PROVIDER_SET_ONCE._done = False
