"""Blueprint for Demo 06 — Input Sanitization.

Side-by-side comparison: vulnerable chatbot (no defenses) vs defended chatbot
(regex filter + input sanitizer + LLM judge + LLM Guard scanner).

Routes:
  GET  /demo-06/            → render the comparison UI
  POST /demo-06/api/compare → run both chatbots, SSE stream results
  POST /demo-06/api/reset   → no-op (stateless)
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
_demo6_python = PROJECT_ROOT / "demo-06-input-sanitization" / "python"
if str(_demo6_python) not in sys.path:
    sys.path.insert(0, str(_demo6_python))

_demo1_python = PROJECT_ROOT / "demo-01-direct-prompt-injection" / "python"
if str(_demo1_python) not in sys.path:
    sys.path.insert(0, str(_demo1_python))

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.python.ollama_client import OllamaClient  # noqa: E402
from vulnerable_chatbot import VulnerableChatbot  # noqa: E402
from defended_chatbot import DefendedChatbot  # noqa: E402

# ── Payloads from Demo 01 ──
_payloads_path = PROJECT_ROOT / "demo-01-direct-prompt-injection" / "attacks" / "payloads.json"


def _load_payloads() -> list[dict[str, str]]:
    if not _payloads_path.exists():
        return []
    with open(_payloads_path) as f:
        return json.load(f)  # type: ignore[no-any-return]


def _load_source_data() -> list[dict]:
    """Load source data for the Source Intelligence Drawer."""
    tabs: list[dict] = []

    # Attack payloads (reused from Demo 01)
    payloads = _load_payloads()
    if payloads:
        tabs.append({
            "id": "payloads",
            "label": f"ATTACK PAYLOADS ({len(payloads)})",
            "type": "list",
            "items": [
                {"name": p["name"], "content": p["payload"]}
                for p in payloads
            ],
        })

    # Defense layers
    defense_layers = [
        {
            "name": "regex_filter",
            "content": (
                "Regex-based injection pattern filter. Scans user input for "
                "known prompt injection patterns using case-insensitive regex "
                "matching. Returns BLOCKED if any pattern matches, PASS otherwise."
            ),
        },
        {
            "name": "input_sanitizer",
            "content": (
                "Input sanitizer that strips special tokens and invisible "
                "characters. Removes zero-width characters, unicode homoglyphs, "
                "invisible formatting, and other obfuscation techniques that "
                "attackers use to sneak injections past simple pattern matchers."
            ),
        },
        {
            "name": "llm_judge",
            "content": (
                "LLM-based prompt injection judge. Sends user input to a second "
                "LLM call asking it to classify whether the input is a prompt "
                "injection attempt. Uses a separate model call to avoid the "
                "primary model being manipulated."
            ),
        },
        {
            "name": "llm_guard_scanner",
            "content": (
                "LLM Guard prompt injection scanner. Integrates the llm-guard "
                "library's PromptInjection scanner, which uses a fine-tuned "
                "classifier model to detect injection attempts."
            ),
        },
    ]
    tabs.append({
        "id": "defenses",
        "label": f"DEFENSE LAYERS ({len(defense_layers)})",
        "type": "list",
        "items": defense_layers,
    })

    return tabs


# ── Blueprint ──
bp = Blueprint("demo_06", __name__, url_prefix="/demo-06")


def _sse_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _run_vulnerable(payload: str, eq: "queue.Queue[str]", otel_span: Any = None) -> None:
    from blueprints.otel_helpers import span_set, span_set_result

    try:
        client = OllamaClient()
        bot = VulnerableChatbot(client=client)
        result = bot.send(payload)
        span_set("vuln.blocked", False, span=otel_span)
        span_set_result(
            span=otel_span,
            action="vulnerable_chatbot",
            blocked=False,
            response_preview=result["response"][:300] if result["response"] else "",
        )
        eq.put(_sse_event("vuln_result", {
            "response": result["response"][:1000] if result["response"] else "",
            "blocked": result["blocked"],
        }))
    except Exception as exc:
        eq.put(_sse_event("vuln_result", {
            "response": f"Error: {exc}",
            "blocked": False,
        }))


def _run_defended(payload: str, eq: "queue.Queue[str]", otel_span: Any = None) -> None:
    from blueprints.otel_helpers import span_set_result

    try:
        client = OllamaClient()
        bot = DefendedChatbot(client=client)
        result = bot.send(payload)

        layers = []
        for dr in result.get("defense_results", []):
            layers.append({
                "name": dr.get("layer", "unknown"),
                "blocked": dr.get("blocked", False),
                "reason": dr.get("reason", ""),
            })

        span_set_result(
            span=otel_span,
            action="input_sanitization",
            blocked=result["blocked"],
            blocked_by=result.get("blocked_by", ""),
            response_preview=result["response"][:300] if result["response"] else "",
        )
        eq.put(_sse_event("defended_result", {
            "response": result["response"][:1000] if result["response"] else "Blocked by defense layers.",
            "blocked": result["blocked"],
            "blocked_by": result.get("blocked_by", ""),
            "layers": layers,
        }))
    except Exception as exc:
        eq.put(_sse_event("defended_result", {
            "response": f"Error: {exc}",
            "blocked": False,
            "blocked_by": "",
            "layers": [],
        }))


@bp.route("/")
def index() -> str:
    payloads = _load_payloads()
    return render_template("demo_06/index.html", payloads=payloads, source_tabs=_load_source_data())


@bp.route("/api/compare", methods=["POST"])
def api_compare() -> Response:
    data = request.get_json(silent=True) or {}
    payload = data.get("payload", "").strip()
    if not payload:
        return jsonify({"error": "No payload provided"}), 400  # type: ignore[return-value]

    from blueprints.otel_helpers import get_request_span

    event_queue: queue.Queue[str] = queue.Queue()
    otel_span = get_request_span()

    t1 = threading.Thread(target=_run_vulnerable, args=(payload, event_queue, otel_span), daemon=True)
    t2 = threading.Thread(target=_run_defended, args=(payload, event_queue, otel_span), daemon=True)
    t1.start()
    t2.start()

    def generate() -> Generator[str, None, None]:
        results = 0
        while results < 2:
            try:
                event = event_queue.get(timeout=120)
                yield event
                if "vuln_result" in event or "defended_result" in event:
                    results += 1
            except queue.Empty:
                yield _sse_event("error", {"message": "Timeout"})
                break
        yield _sse_event("done", {})

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@bp.route("/api/reset", methods=["POST"])
def api_reset() -> tuple[Response, int]:
    return jsonify({"status": "ok"}), 200
