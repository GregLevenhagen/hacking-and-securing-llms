"""OTel tracing helpers for demo-specific span creation.

Provides a @trace_demo decorator and utility functions for adding
demo metadata to OTel spans.
"""

import functools
import logging
from typing import Any, Callable, TypeVar

__all__ = ["trace_demo", "set_user_id", "set_session_id", "add_demo_event"]

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def trace_demo(
    demo_name: str,
    demo_id: str | None = None,
    category: str = "attack",
) -> Callable[[F], F]:
    """Decorator that wraps a function in an OTel span with demo attributes.

    Args:
        demo_name: Human-readable demo name (e.g., "Direct Prompt Injection").
        demo_id: Demo identifier (e.g., "demo-01"). Auto-derived from demo_name
            if not provided.
        category: One of "attack", "defense", or "azure-defense".

    Usage:
        @trace_demo("Direct Prompt Injection", demo_id="demo-01", category="attack")
        def run_demo():
            ...
    """
    resolved_id = demo_id or demo_name.lower().replace(" ", "-")

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                from opentelemetry import trace

                tracer = trace.get_tracer("securing-llms.demos")
                with tracer.start_as_current_span(
                    f"demo.{resolved_id}",
                    attributes={
                        "demo.name": demo_name,
                        "demo.id": resolved_id,
                        "demo.category": category,
                    },
                ) as span:
                    return fn(*args, **kwargs)
            except ImportError:
                return fn(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


def set_user_id(user_id: str) -> None:
    """Add a user ID attribute to the current active span."""
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        if span.is_recording():
            span.set_attribute("user.id", user_id)
    except ImportError:
        pass


def set_session_id(session_id: str) -> None:
    """Add a session ID attribute to the current active span."""
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        if span.is_recording():
            span.set_attribute("session.id", session_id)
    except ImportError:
        pass


def add_demo_event(name: str, attributes: dict[str, Any] | None = None) -> None:
    """Add a named event to the current active span.

    Args:
        name: Event name (e.g., "attack.attempted", "defense.blocked").
        attributes: Optional dict of event attributes.
    """
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        if span.is_recording():
            span.add_event(name, attributes=attributes or {})
    except ImportError:
        pass
