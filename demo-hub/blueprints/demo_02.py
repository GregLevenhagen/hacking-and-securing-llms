"""Blueprint for Demo 02 — Indirect Prompt Injection.

Shows how hidden payloads in web pages trick a summarizer LLM.
Two-panel layout: left shows "What humans see" (visible text),
right shows "What the LLM sees" (full extracted text including hidden payloads).

Routes:
  GET  /demo-02/             → render the page picker UI
  POST /demo-02/api/analyze  → analyze a page, SSE stream results
  POST /demo-02/api/reset    → no-op
"""

import json
import queue
import sys
import threading
from pathlib import Path
from typing import Any, Generator

from flask import Blueprint, Response, jsonify, render_template, request, stream_with_context

from blueprints import PROJECT_ROOT

# ── Path setup ──
_demo2_python = PROJECT_ROOT / "demo-02-indirect-prompt-injection" / "python"
if str(_demo2_python) not in sys.path:
    sys.path.insert(0, str(_demo2_python))

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from summarizer import extract_text, extract_visible_text, INJECTION_PAYLOAD  # noqa: E402
from shared.python.ollama_client import OllamaClient  # noqa: E402

from openai.types.chat import ChatCompletionMessageParam  # noqa: E402

# ── Blueprint ──
bp = Blueprint("demo_02", __name__, url_prefix="/demo-02")

# Pages available for analysis
_pages_dir = PROJECT_ROOT / "demo-02-indirect-prompt-injection" / "pages"
PAGES = [
    {"name": "legitimate.html", "label": "Legitimate Page", "poisoned": False},
    {"name": "poisoned_whitefont.html", "label": "White Font Injection", "poisoned": True},
    {"name": "poisoned_zerosize.html", "label": "Zero-Size Font", "poisoned": True},
    {"name": "poisoned_comment.html", "label": "HTML Comment", "poisoned": True},
    {"name": "poisoned_data_attr.html", "label": "Data Attribute", "poisoned": True},
    {"name": "poisoned_aria.html", "label": "ARIA Label", "poisoned": True},
    {"name": "poisoned_css_content.html", "label": "CSS Content", "poisoned": True},
]


def _sse_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _analyze_page(page_name: str, eq: "queue.Queue[str]", otel_span: Any = None) -> None:
    """Analyze a page: extract visible text, full text, and summarize."""
    from blueprints.otel_helpers import span_set, span_set_result

    span_set("demo.action", "analyze_page", span=otel_span)
    span_set("attack.page_name", page_name, span=otel_span)

    _response_preview = ""
    try:
        page_path = _pages_dir / page_name
        if not page_path.exists():
            eq.put(_sse_event("error", {"message": f"Page not found: {page_name}"}))
            eq.put(_sse_event("done", {}))
            return

        html = page_path.read_text()

        # What humans see (visible text only)
        visible = extract_visible_text(html)
        eq.put(_sse_event("human_view", {"text": visible[:2000]}))

        # What the LLM sees (full extraction including hidden content)
        full_text = extract_text(html)
        has_injection = INJECTION_PAYLOAD[:30] in full_text
        span_set("attack.has_injection", has_injection, span=otel_span)
        _response_preview = full_text[:300]
        eq.put(_sse_event("llm_view", {
            "text": full_text[:2000],
            "has_injection": has_injection,
        }))

        # Summarize via LLM (streaming)
        try:
            client = OllamaClient()
            messages: list[ChatCompletionMessageParam] = [
                {"role": "system", "content": "Summarize this web page content concisely."},
                {"role": "user", "content": f"Page content:\n{full_text[:3000]}"},
            ]
            for token in client.chat_stream(messages):
                eq.put(_sse_event("summary_token", {"token": token}))
            eq.put(_sse_event("summary_done", {}))
        except Exception as exc:
            eq.put(_sse_event("error", {"message": f"LLM error: {exc}"}))

    except Exception as exc:
        eq.put(_sse_event("error", {"message": f"Analysis error: {exc}"}))

    span_set_result(
        span=otel_span,
        action="analyze_page",
        response_preview=_response_preview,
    )
    eq.put(_sse_event("done", {}))


@bp.route("/")
def index() -> str:
    return render_template(
        "demo_02/index.html",
        pages=PAGES,
        source_tabs=[
            {
                "id": "pages",
                "label": "HTML PAGES",
                "type": "list",
                "items": [
                    {"name": p["label"], "content": f"{'[POISONED] ' if p.get('poisoned') else '[CLEAN] '}{p['name']}"}
                    for p in PAGES
                ],
            },
            {
                "id": "injection",
                "label": "INJECTION PAYLOAD",
                "type": "text",
                "content": INJECTION_PAYLOAD,
            },
        ],
    )


@bp.route("/api/analyze", methods=["POST"])
def api_analyze() -> Response:
    data = request.get_json(silent=True) or {}
    page_name = data.get("page_name", "").strip()
    if not page_name:
        return jsonify({"error": "No page specified"}), 400  # type: ignore[return-value]

    from blueprints.otel_helpers import get_request_span

    event_queue: queue.Queue[str] = queue.Queue()
    otel_span = get_request_span()
    thread = threading.Thread(target=_analyze_page, args=(page_name, event_queue, otel_span), daemon=True)
    thread.start()

    def generate() -> Generator[str, None, None]:
        while True:
            try:
                event = event_queue.get(timeout=120)
                yield event
                if "event: done" in event:
                    break
            except queue.Empty:
                yield _sse_event("error", {"message": "Timeout"})
                break

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@bp.route("/api/reset", methods=["POST"])
def api_reset() -> tuple[Response, int]:
    return jsonify({"status": "ok"}), 200
