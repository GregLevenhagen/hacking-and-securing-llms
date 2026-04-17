"""OpenTelemetry initialization using ONLY standard OTel APIs.

Reads standard OTel environment variables and configures a TracerProvider
with either OTLP export (when OTEL_EXPORTER_OTLP_ENDPOINT is set) or
ConsoleSpanExporter as a fallback for local debugging.

When no OTLP endpoint is configured, spans are written to a local file
(default: ``otel-traces.log`` in the project root) so they can be viewed
with ``tail -f otel-traces.log`` without Flask log noise.  Override the
path with ``OTEL_CONSOLE_FILE``.

Also registers opentelemetry-instrumentation-openai-v2 auto-instrumentation
so all OpenAI SDK calls (including Ollama and Azure OpenAI) are traced
automatically with gen_ai.* semantic convention attributes.

Dependencies (standard OTel only — NO vendor SDKs):
    - opentelemetry-api
    - opentelemetry-sdk
    - opentelemetry-exporter-otlp-proto-http
    - opentelemetry-instrumentation-openai-v2
    - opentelemetry-semantic-conventions
"""

import logging
import os
from pathlib import Path
from typing import Any
from urllib.parse import unquote

__all__ = [
    "init_telemetry",
    "get_tracer",
    "test_mode",
    "TraceContextFilter",
    "TRACE_LOG_FORMAT",
    "configure_log_correlation",
    "get_telemetry_status",
]

logger = logging.getLogger(__name__)

_initialized = False


def init_telemetry() -> bool:
    """Initialize the OpenTelemetry tracing pipeline.

    Reads configuration from standard OTel environment variables:
        - OTEL_ENABLED: "true" or "false" (default "false")
        - OTEL_EXPORTER_OTLP_ENDPOINT: OTLP endpoint URL
        - OTEL_EXPORTER_OTLP_HEADERS: Comma-separated key=value pairs
        - OTEL_EXPORTER_OTLP_PROTOCOL: "http/protobuf" (default) or "http/json"
        - OTEL_SERVICE_NAME: Service name (default "securing-llms")
        - OTEL_CONSOLE_FILE: Path for local span log when no endpoint is set
          (default "otel-traces.log" in project root)

    Returns:
        True if telemetry was initialized, False if skipped or already initialized.
    """
    global _initialized

    if _initialized:
        logger.debug("OTel already initialized, skipping")
        return False

    enabled = os.getenv("OTEL_ENABLED", "false").lower() == "true"
    if not enabled:
        logger.debug("OTEL_ENABLED is not true, skipping OTel initialization")
        return False

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        service_name = os.getenv("OTEL_SERVICE_NAME", "securing-llms")
        resource = Resource.create({"service.name": service_name})

        provider = TracerProvider(resource=resource)

        # Choose exporter based on whether an OTLP endpoint is configured
        endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
        if endpoint and _validate_endpoint(endpoint):
            exporter = _create_otlp_exporter(endpoint)
            logger.info(
                "OTel: using OTLP exporter → %s (service: %s)",
                endpoint,
                service_name,
            )
        else:
            from opentelemetry.sdk.trace.export import ConsoleSpanExporter

            # Write spans to a local file so they don't mix with Flask logs.
            # Default: otel-traces.log in the project root.
            # Override with OTEL_CONSOLE_FILE env var.
            _project_root = Path(__file__).resolve().parents[3]
            default_log = str(_project_root / "otel-traces.log")
            trace_file = os.getenv("OTEL_CONSOLE_FILE", default_log)
            _trace_fh = open(trace_file, "a", buffering=1)  # noqa: SIM115
            exporter = ConsoleSpanExporter(out=_trace_fh)
            logger.info(
                "OTel: no OTLP endpoint set, writing spans to %s (service: %s)",
                trace_file,
                service_name,
            )

        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        # Register OpenAI auto-instrumentation for gen_ai.* semantic conventions
        _register_openai_instrumentation()

        _initialized = True
        return True

    except ImportError as e:
        logger.warning(
            "OTel packages not installed, skipping telemetry: %s", e
        )
        return False
    except Exception as e:
        logger.warning("Failed to initialize OTel: %s", e)
        return False


def _parse_otlp_headers(raw: str) -> dict[str, str]:
    """Parse OTEL_EXPORTER_OTLP_HEADERS into a dict.

    Handles the standard format: "key1=value1,key2=value2"
    Also handles:
      - URL-encoded values (e.g., "Authorization=Basic%20dXNlcjpwYXNz")
      - Quoted values (e.g., 'key="value with spaces"')
      - Values containing '=' (e.g., "Authorization=Basic abc123==")
      - Empty values (e.g., "key=")
      - Whitespace around keys and values
    """
    headers: dict[str, str] = {}
    if not raw:
        return headers

    for pair in raw.split(","):
        pair = pair.strip()
        if not pair:
            continue
        if "=" not in pair:
            logger.warning("OTel: skipping malformed header (no '='): %r", pair)
            continue
        key, value = pair.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            logger.warning("OTel: skipping header with empty key")
            continue
        # Strip surrounding quotes if present
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        # URL-decode the value (handles %20, %3D, etc.)
        value = unquote(value)
        headers[key] = value

    return headers


def _validate_endpoint(endpoint: str) -> bool:
    """Validate that an OTLP endpoint URL is well-formed."""
    if not endpoint:
        return False
    if not endpoint.startswith(("http://", "https://")):
        logger.warning(
            "OTel: OTLP endpoint must start with http:// or https://, got: %r",
            endpoint,
        )
        return False
    return True


def _create_otlp_exporter(endpoint: str):  # type: ignore[no-untyped-def]
    """Create an OTLP span exporter with the configured protocol."""
    protocol = os.getenv("OTEL_EXPORTER_OTLP_PROTOCOL", "http/protobuf")
    headers = _parse_otlp_headers(os.getenv("OTEL_EXPORTER_OTLP_HEADERS", ""))

    # Ensure the endpoint has the traces path for HTTP exporters
    traces_endpoint = endpoint.rstrip("/")
    if not traces_endpoint.endswith("/v1/traces"):
        traces_endpoint += "/v1/traces"

    from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
        OTLPSpanExporter,
    )

    return OTLPSpanExporter(
        endpoint=traces_endpoint,
        headers=headers,
    )


def _register_openai_instrumentation() -> None:
    """Register OpenAI SDK auto-instrumentation for gen_ai.* attributes."""
    try:
        from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor

        OpenAIInstrumentor().instrument()
        logger.debug("OTel: OpenAI auto-instrumentation registered")
    except ImportError:
        logger.debug(
            "opentelemetry-instrumentation-openai-v2 not installed, "
            "skipping OpenAI auto-instrumentation"
        )
    except Exception as e:
        logger.warning("Failed to register OpenAI instrumentation: %s", e)


def get_tracer(name: str = "securing-llms") -> Any:
    """Get a named OTel tracer, or a no-op tracer if OTel is not installed.

    Args:
        name: Tracer name, typically the module or demo name.

    Returns:
        An OTel Tracer instance (or a no-op proxy).
    """
    try:
        from opentelemetry import trace

        return trace.get_tracer(name)
    except ImportError:
        # Return a no-op tracer-like object
        return _NoOpTracer()


class _NoOpTracer:
    """Minimal no-op tracer for when OTel is not installed."""

    def start_as_current_span(self, name: str, **kwargs: Any) -> Any:
        return _NoOpContextManager()


class _NoOpContextManager:
    """No-op context manager that acts as a dummy span."""

    def __enter__(self) -> "_NoOpContextManager":
        return self

    def __exit__(self, *args: Any) -> None:
        pass

    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def add_event(self, name: str, **kwargs: Any) -> None:
        pass

    def is_recording(self) -> bool:
        return False


def test_mode() -> Any:
    """Initialize OTel in test mode with an InMemorySpanExporter.

    Returns the exporter so tests can inspect captured spans.
    Call _reset_for_testing() first if OTel was already initialized.

    Returns:
        An InMemorySpanExporter instance, or None if OTel is not installed.
    """
    global _initialized

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult

        # Custom InMemorySpanExporter (built-in was removed in OTel SDK v1.40)
        class InMemorySpanExporter(SpanExporter):
            def __init__(self) -> None:
                self._spans: list[Any] = []
                self._stopped = False

            def export(self, spans: Any) -> SpanExportResult:
                if self._stopped:
                    return SpanExportResult.FAILURE
                self._spans.extend(spans)
                return SpanExportResult.SUCCESS

            def shutdown(self) -> None:
                self._stopped = True

            def force_flush(self, timeout_millis: int = 0) -> bool:
                return True

            def get_finished_spans(self) -> list[Any]:
                return list(self._spans)

            def clear(self) -> None:
                self._spans.clear()

        exporter = InMemorySpanExporter()
        resource = Resource.create({"service.name": "securing-llms-test"})
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(SimpleSpanProcessor(exporter))

        # Reset the global provider if already set
        trace._TRACER_PROVIDER_SET_ONCE._done = False  # type: ignore[attr-defined]
        trace.set_tracer_provider(provider)

        _initialized = True
        return exporter

    except ImportError:
        logger.warning("OTel packages not installed, test_mode() unavailable")
        return None


class TraceContextFilter(logging.Filter):
    """Logging filter that injects trace_id and span_id into log records.

    Adds ``otelTraceID`` and ``otelSpanID`` attributes so log formatters can
    include them (e.g., ``%(otelTraceID)s``).  When no active span exists the
    attributes are set to ``"0"`` for consistency.

    Usage::

        handler = logging.StreamHandler()
        handler.addFilter(TraceContextFilter())
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(otelTraceID)s/%(otelSpanID)s] %(message)s"
        ))
    """

    def filter(self, record: logging.LogRecord) -> bool:
        trace_id = "0"
        span_id = "0"
        try:
            from opentelemetry import trace as _trace

            span = _trace.get_current_span()
            ctx = span.get_span_context()
            if ctx and ctx.trace_id:
                trace_id = format(ctx.trace_id, "032x")
                span_id = format(ctx.span_id, "016x")
        except (ImportError, Exception):
            pass
        record.otelTraceID = trace_id  # type: ignore[attr-defined]
        record.otelSpanID = span_id  # type: ignore[attr-defined]
        return True


#: Default log format string that includes OTel trace context.
TRACE_LOG_FORMAT = (
    "%(asctime)s %(levelname)-8s [trace=%(otelTraceID)s span=%(otelSpanID)s] "
    "%(name)s - %(message)s"
)


def configure_log_correlation(
    logger_name: str | None = None,
    fmt: str | None = None,
    level: int = logging.INFO,
    log_file: str | None = None,
) -> None:
    """Add OTel trace context to a Python logger's output.

    Attaches a :class:`TraceContextFilter` and sets a formatter that includes
    ``trace_id`` and ``span_id`` fields.  Safe to call when OTel is not
    installed — the filter falls back to ``"0"`` for both IDs.

    Args:
        logger_name: Logger to configure.  ``None`` means the root logger.
        fmt: Custom format string (must use ``%(otelTraceID)s`` /
            ``%(otelSpanID)s``).  Defaults to :data:`TRACE_LOG_FORMAT`.
        level: Logging level for the handler.  Defaults to ``logging.INFO``.
        log_file: Path to a log file.  When set, logs are written to this
            file instead of stderr.  The file is opened in append mode
            with line buffering for ``tail -f`` compatibility.
    """
    target = logging.getLogger(logger_name)
    if log_file:
        handler: logging.Handler = logging.FileHandler(log_file, mode="a")
    else:
        handler = logging.StreamHandler()
    handler.addFilter(TraceContextFilter())
    handler.setFormatter(logging.Formatter(fmt or TRACE_LOG_FORMAT))
    handler.setLevel(level)
    target.addHandler(handler)


def get_telemetry_status() -> dict[str, Any]:
    """Return a JSON-friendly summary of the current OTel configuration.

    Useful for health-check endpoints and the Demo Hub telemetry panel.

    Returns:
        Dict with keys: ``enabled``, ``initialized``, ``service_name``,
        ``endpoint``, ``protocol``, ``headers_configured``.
    """
    enabled = os.getenv("OTEL_ENABLED", "false").lower() == "true"
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    headers_raw = os.getenv("OTEL_EXPORTER_OTLP_HEADERS", "")
    return {
        "enabled": enabled,
        "initialized": _initialized,
        "service_name": os.getenv("OTEL_SERVICE_NAME", "securing-llms"),
        "endpoint": endpoint or None,
        "protocol": os.getenv("OTEL_EXPORTER_OTLP_PROTOCOL", "http/protobuf"),
        "headers_configured": bool(headers_raw.strip()),
    }


def _reset_for_testing() -> None:
    """Reset initialization state for testing. NOT for production use."""
    global _initialized
    _initialized = False
