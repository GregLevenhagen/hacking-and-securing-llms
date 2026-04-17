"""Blueprint for Demo 01 — Direct Prompt Injection.

Provides a chat interface where users can test prompt injection attacks
against a French translator chatbot with 4 system prompt strictness levels.

Routes:
  GET  /demo-01/           → render the chat UI
  POST /demo-01/api/chat   → send message, SSE stream response tokens
  POST /demo-01/api/reset  → clear conversation history
  GET  /demo-01/api/payloads → return attack payloads
"""

import json
import queue
import sys
import threading
from pathlib import Path
from typing import Any, Generator

from flask import Blueprint, Response, jsonify, render_template, request, stream_with_context

from blueprints import PROJECT_ROOT

# ── Path setup for demo-01 imports ──
_demo1_python = PROJECT_ROOT / "demo-01-direct-prompt-injection" / "python"
if str(_demo1_python) not in sys.path:
    sys.path.insert(0, str(_demo1_python))

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.python.ollama_client import OllamaClient  # noqa: E402
from system_prompts import get_all_prompts  # noqa: E402

from openai.types.chat import ChatCompletionMessageParam  # noqa: E402

# ── Blueprint ────────────────────────────────────
bp = Blueprint("demo_01", __name__, url_prefix="/demo-01")

# ── Payloads ─────────────────────────────────────
_payloads_path = (
    PROJECT_ROOT / "demo-01-direct-prompt-injection" / "attacks" / "payloads.json"
)


def _load_payloads() -> list[dict[str, str]]:
    if not _payloads_path.exists():
        return []
    with open(_payloads_path) as f:
        return json.load(f)  # type: ignore[no-any-return]


# ── Conversation state (per prompt level) ────────
# Key = prompt level index (0-3), value = messages list
_conversations: dict[int, list[ChatCompletionMessageParam]] = {}
_conv_lock = threading.Lock()

_prompts = get_all_prompts()


def _get_conversation(level: int) -> list[ChatCompletionMessageParam]:
    """Get or create conversation history for a given prompt level."""
    with _conv_lock:
        if level not in _conversations:
            _conversations[level] = [
                {"role": "system", "content": _prompts[level]["prompt"]}
            ]
        return _conversations[level]


def _reset_conversation(level: int) -> None:
    """Reset conversation for a given prompt level."""
    with _conv_lock:
        _conversations[level] = [
            {"role": "system", "content": _prompts[level]["prompt"]}
        ]


def _sse_event(event: str, data: dict[str, Any]) -> str:
    """Format a single SSE event string."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _stream_chat(
    user_message: str,
    level: int,
    event_queue: "queue.Queue[str]",
    otel_span: Any = None,
) -> None:
    """Run chat_stream in a thread, emitting SSE token events."""
    from blueprints.otel_helpers import span_set, span_set_result

    span_set("demo.action", "chat", span=otel_span)
    span_set("input.prompt_level", level, span=otel_span)
    span_set("input.prompt_level_name", _prompts[level]["name"], span=otel_span)

    try:
        client = OllamaClient()
    except Exception as exc:
        event_queue.put(_sse_event("error", {"message": f"Failed to connect to Ollama: {exc}"}))
        event_queue.put(_sse_event("done", {}))
        return

    messages = _get_conversation(level)
    messages.append({"role": "user", "content": user_message})

    full_response = ""
    try:
        for token in client.chat_stream(messages):
            full_response += token
            event_queue.put(_sse_event("token", {"token": token}))
    except Exception as exc:
        # Remove the user message we just appended
        messages.pop()
        event_queue.put(_sse_event("error", {"message": f"LLM error: {exc}"}))
        event_queue.put(_sse_event("done", {}))
        return

    messages.append({"role": "assistant", "content": full_response})

    span_set_result(
        span=otel_span,
        action="chat",
        response_preview=full_response,
    )

    event_queue.put(_sse_event("done", {"full_response": full_response}))


# ── Routes ───────────────────────────────────────

@bp.route("/")
def index() -> str:
    payloads = _load_payloads()
    return render_template(
        "demo_01/index.html",
        prompts=_prompts,
        payloads=payloads,
        source_tabs=[
            {
                "id": "prompts",
                "label": "SYSTEM PROMPTS",
                "type": "files",
                "files": [
                    {"name": f"Level {i}: {p['name']}", "content": p["prompt"]}
                    for i, p in enumerate(_prompts)
                ],
            },
            {
                "id": "payloads",
                "label": "ATTACK PAYLOADS",
                "type": "list",
                "items": [
                    {"name": p["name"], "content": p["payload"]}
                    for p in payloads
                ],
            },
        ],
    )


@bp.route("/api/chat", methods=["POST"])
def api_chat() -> Response:
    data = request.get_json(silent=True) or {}
    user_message = data.get("message", "").strip()
    level = data.get("level", 0)

    if not user_message:
        return jsonify({"error": "No message provided"}), 400  # type: ignore[return-value]

    if not isinstance(level, int) or level < 0 or level >= len(_prompts):
        level = 0

    from blueprints.otel_helpers import get_request_span

    event_queue: queue.Queue[str] = queue.Queue()
    otel_span = get_request_span()

    thread = threading.Thread(
        target=_stream_chat,
        args=(user_message, level, event_queue, otel_span),
        daemon=True,
    )
    thread.start()

    def generate() -> Generator[str, None, None]:
        while True:
            try:
                event = event_queue.get(timeout=120)
                yield event
                if "event: done" in event:
                    break
            except queue.Empty:
                yield _sse_event("error", {"message": "Timeout waiting for response"})
                break

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@bp.route("/api/reset", methods=["POST"])
def api_reset() -> tuple[Response, int]:
    data = request.get_json(silent=True) or {}
    level = data.get("level", -1)

    if isinstance(level, int) and 0 <= level < len(_prompts):
        _reset_conversation(level)
    else:
        # Reset all
        with _conv_lock:
            _conversations.clear()

    return jsonify({"status": "ok"}), 200


@bp.route("/api/payloads")
def api_payloads() -> Response:
    return jsonify(_load_payloads())
