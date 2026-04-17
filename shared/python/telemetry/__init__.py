"""OpenTelemetry instrumentation pipeline for the demo suite.

Provides vendor-neutral tracing using standard OTel APIs and OTLP export.
Works with any OTel-compliant backend: LangFuse, Jaeger, Grafana Tempo,
Datadog, Arize Phoenix, or a generic OTel Collector.

Usage:
    from shared.python.telemetry import init_telemetry, flush_telemetry, trace_demo

    init_telemetry()  # Call once at startup

    @trace_demo("demo-01")
    def run_demo():
        ...

    flush_telemetry()  # Call before process exit
"""

from .otel_setup import (
    TRACE_LOG_FORMAT,
    TraceContextFilter,
    configure_log_correlation,
    get_telemetry_status,
    get_tracer,
    init_telemetry,
    test_mode,
)
from .shutdown import flush_telemetry
from .trace_helpers import add_demo_event, set_session_id, set_user_id, trace_demo

__all__ = [
    "init_telemetry",
    "flush_telemetry",
    "trace_demo",
    "set_user_id",
    "set_session_id",
    "add_demo_event",
    "get_tracer",
    "test_mode",
    "TraceContextFilter",
    "TRACE_LOG_FORMAT",
    "configure_log_correlation",
    "get_telemetry_status",
]
