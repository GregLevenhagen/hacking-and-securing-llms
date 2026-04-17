"""Flask boilerplate and SSE streaming helpers for web-based demos.

Provides a create_app() factory with common error handlers and
SSE streaming helpers for real-time LLM output.
"""

import json
import logging
from typing import Any, Generator, Iterator, Union

from flask import Flask, Response, jsonify, stream_with_context

__all__ = ["create_app", "sse_stream", "sse_event", "SSE_HEADERS"]

logger = logging.getLogger(__name__)

# Standard headers for SSE responses — prevents proxy buffering
SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}


def create_app(name: str, **kwargs: Any) -> Flask:
    """Create a Flask app with common error handlers and configuration.

    Args:
        name: The Flask application name (typically __name__).
        **kwargs: Additional keyword arguments passed to Flask().

    Returns:
        Configured Flask application instance.
    """
    app = Flask(name, **kwargs)

    @app.errorhandler(404)
    def not_found(error: Any) -> tuple[Response, int]:
        return jsonify({"error": "Not found", "status": 404}), 404

    @app.errorhandler(500)
    def internal_error(error: Any) -> tuple[Response, int]:
        logger.error("Internal server error: %s", error)
        return jsonify({"error": "Internal server error", "status": 500}), 500

    @app.errorhandler(400)
    def bad_request(error: Any) -> tuple[Response, int]:
        return jsonify({"error": "Bad request", "status": 400}), 400

    return app


def sse_event(event: str, data: Union[dict[str, Any], str]) -> str:
    """Format a single SSE event string.

    Use this when building custom SSE generators that need to emit
    structured events (e.g., approval_request, status updates).

    Args:
        event: The SSE event name (e.g., "message", "approval_request").
        data: The event payload — dict is JSON-serialized, str is sent as-is.

    Returns:
        Formatted SSE event string ready to be yielded in a response.
    """
    if isinstance(data, dict):
        payload = json.dumps(data)
    else:
        payload = data
    return f"event: {event}\ndata: {payload}\n\n"


def sse_stream(
    generator: Union[Generator[str, None, None], Iterator[str]],
    event: str = "message",
) -> Response:
    """Wrap a string generator as a Server-Sent Events response.

    Each yielded string becomes an SSE data line. Use this to stream
    LLM tokens to the browser in real time. Emits a final "done" event
    when the generator is exhausted.

    Args:
        generator: A generator/iterator that yields string tokens.
        event: The SSE event name (default: "message").

    Returns:
        Flask Response with text/event-stream content type.
    """

    def format_sse() -> Generator[str, None, None]:
        try:
            for token in generator:
                yield sse_event(event, {"token": token})
        except Exception as e:
            logger.error("SSE stream error: %s", e)
            yield sse_event("error", {"error": str(e)})
        yield sse_event("done", {})

    return Response(
        stream_with_context(format_sse()),
        mimetype="text/event-stream",
        headers=SSE_HEADERS,
    )
