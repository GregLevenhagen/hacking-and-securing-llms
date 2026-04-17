"""OTel span enrichment helpers for demo hub blueprints.

Call these from API route handlers to add demo-specific attributes
to the current request span.  All functions are safe no-ops when
OTel is not enabled or the span doesn't exist.

Usage in a blueprint::

    from blueprints.otel_helpers import span_set, span_event

    @bp.route("/api/attack", methods=["POST"])
    def api_attack():
        span_set("attack.technique", "role-play")
        span_set("attack.payload", payload_text)
        ...
        span_set("defense.result", "blocked")
        span_set("defense.blocked_by", "injection_detector")
        span_event("technique_complete", {"success": True})
"""

import logging

from flask import has_request_context, request

_log = logging.getLogger("demo-hub")


def _get_span():  # type: ignore[no-untyped-def]
    """Get the current request's OTel span, or None."""
    if has_request_context():
        return getattr(request, "_otel_span", None)
    return None


def get_request_span():  # type: ignore[no-untyped-def]
    """Get the span object so threads can enrich it after request context is gone."""
    return _get_span()


def _is_recording(span) -> bool:  # type: ignore[no-untyped-def]
    """Check if a span is still open and accepting attributes."""
    return span is not None and getattr(span, "is_recording", lambda: False)()


def span_set(key: str, value: str | int | float | bool, span=None) -> None:  # type: ignore[no-untyped-def]
    """Set an attribute on the current request's OTel span (or an explicit span)."""
    span = span or _get_span()
    if _is_recording(span):
        span.set_attribute(key, value)


def span_event(name: str, attributes: dict | None = None, span=None) -> None:  # type: ignore[no-untyped-def]
    """Add an event (log line) to the current request's OTel span (or an explicit span)."""
    span = span or _get_span()
    if _is_recording(span):
        span.add_event(name, attributes=attributes or {})


def span_set_result(
    *,
    span=None,  # type: ignore[no-untyped-def]
    action: str = "",
    success: bool | None = None,
    blocked: bool | None = None,
    blocked_by: str = "",
    technique: str = "",
    violations: list[str] | None = None,
    response_preview: str = "",
    tokens_in: int = 0,
    tokens_out: int = 0,
) -> None:
    """Set common result attributes on the current request's OTel span.

    Call this at the end of an attack/defense handler to record the outcome.
    """
    span = span or _get_span()
    if not _is_recording(span):
        return
    if action:
        span.set_attribute("demo.action", action)
    if success is not None:
        span.set_attribute("result.success", success)
    if blocked is not None:
        span.set_attribute("defense.blocked", blocked)
    if blocked_by:
        span.set_attribute("defense.blocked_by", blocked_by)
    if technique:
        span.set_attribute("attack.technique", technique)
    if violations:
        span.set_attribute("result.violations", ", ".join(violations))
    if response_preview:
        span.set_attribute("llm.response_preview", response_preview[:300])
    if tokens_in:
        span.set_attribute("llm.tokens_in", tokens_in)
    if tokens_out:
        span.set_attribute("llm.tokens_out", tokens_out)

    # Log a human-readable summary to otel-app.log.
    # Extract trace/span IDs directly from the span object since
    # this often runs in a background thread where OTel context
    # (contextvars) isn't propagated from the request thread.
    parts = []
    if action:
        parts.append(action)
    if technique:
        parts.append(f"technique={technique}")
    if success is not None:
        parts.append("SUCCESS" if success else "FAILED")
    if blocked is not None:
        parts.append("BLOCKED" if blocked else "ALLOWED")
    if blocked_by:
        parts.append(f"by={blocked_by}")
    if violations:
        parts.append(f"violations=[{', '.join(violations)}]")
    if parts:
        trace_id = "0"
        span_id = "0"
        ctx = span.get_span_context()
        if ctx and ctx.trace_id:
            trace_id = format(ctx.trace_id, "032x")
            span_id = format(ctx.span_id, "016x")
        _log.info(
            "[trace=%s span=%s]  %s",
            trace_id, span_id, "  ".join(parts),
        )
