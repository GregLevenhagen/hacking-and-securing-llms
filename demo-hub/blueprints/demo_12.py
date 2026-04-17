"""Blueprint for Demo 12 — Jailbreaking.

Run jailbreak attack techniques against a safety-prompted LLM and classify
whether each technique bypasses the model's guardrails.

Routes:
  GET  /demo-12/            → render the jailbreak attack UI
  POST /demo-12/api/attack  → run a single jailbreak technique, SSE stream
  POST /demo-12/api/run-all → run all 8 techniques sequentially, SSE stream
  POST /demo-12/api/reset   → reset session state
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
_demo12_python = PROJECT_ROOT / "demo-12-jailbreaking" / "python"
if str(_demo12_python) not in sys.path:
    sys.path.insert(0, str(_demo12_python))

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from jailbreak_attacks import SYSTEM_PROMPT, load_techniques, run_attack  # noqa: E402
from safety_classifier import classify_response  # noqa: E402
from shared.python.ollama_client import OllamaClient  # noqa: E402

from openai.types.chat import ChatCompletionMessageParam  # noqa: E402

# ── Blueprint ──
bp = Blueprint("demo_12", __name__, url_prefix="/demo-12")

_techniques_path = PROJECT_ROOT / "demo-12-jailbreaking" / "attacks" / "techniques.json"

# Session state — track results for scoreboard
_session_results: list[dict[str, Any]] = []
_session_lock = threading.Lock()


def _sse_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _run_single_attack(technique_index: int, eq: "queue.Queue[str]", otel_span: Any = None) -> None:
    """Run a single jailbreak technique by index."""
    from blueprints.otel_helpers import span_set, span_set_result

    try:
        techniques = load_techniques(_techniques_path)
        if technique_index < 0 or technique_index >= len(techniques):
            eq.put(_sse_event("error", {"message": f"Invalid technique index: {technique_index}"}))
            eq.put(_sse_event("done", {}))
            return

        tech = techniques[technique_index]
        span_set("attack.technique", tech["name"], span=otel_span)
        span_set("attack.technique_index", technique_index, span=otel_span)
        client = OllamaClient()

        eq.put(_sse_event("technique_start", {
            "index": technique_index,
            "name": tech["name"],
            "description": tech.get("description", ""),
            "prompt": tech["prompt"],
        }))

        messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": tech["prompt"]},
        ]

        full_response = ""
        try:
            for token in client.chat_stream(messages):
                full_response += token
                eq.put(_sse_event("token", {"token": token, "index": technique_index}))
        except Exception as exc:
            eq.put(_sse_event("error", {"message": f"LLM error: {exc}"}))
            eq.put(_sse_event("done", {}))
            return

        classification = classify_response(full_response)
        bypassed = not classification["safe"]

        result = {
            "index": technique_index,
            "name": tech["name"],
            "bypassed": bypassed,
            "violations": classification.get("violations", []),
            "confidence": classification.get("confidence", 0.0),
            "refused": classification.get("refused", False),
        }

        span_set_result(
            span=otel_span,
            action="jailbreak_attack",
            technique=tech["name"],
            success=bypassed,
            violations=classification.get("violations", []),
            response_preview=full_response,
        )
        span_set("result.confidence", classification.get("confidence", 0.0), span=otel_span)
        span_set("result.refused", classification.get("refused", False), span=otel_span)

        with _session_lock:
            # Replace existing result for this index or append
            existing = [i for i, r in enumerate(_session_results) if r.get("index") == technique_index]
            if existing:
                _session_results[existing[0]] = result
            else:
                _session_results.append(result)

        eq.put(_sse_event("technique_result", result))

    except Exception as exc:
        eq.put(_sse_event("error", {"message": f"Attack error: {exc}"}))

    eq.put(_sse_event("done", {}))


def _run_all_techniques(eq: "queue.Queue[str]", otel_span: Any = None) -> None:
    """Run all jailbreak techniques sequentially."""
    from blueprints.otel_helpers import span_set, span_set_result, span_event

    span_set("demo.action", "run_all_jailbreaks", span=otel_span)
    techniques: list[dict[str, Any]] = []
    try:
        techniques = load_techniques(_techniques_path)
        client = OllamaClient()

        with _session_lock:
            _session_results.clear()

        for i, tech in enumerate(techniques):
            eq.put(_sse_event("technique_start", {
                "index": i,
                "name": tech["name"],
                "description": tech.get("description", ""),
                "prompt": tech["prompt"],
            }))

            messages: list[ChatCompletionMessageParam] = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": tech["prompt"]},
            ]

            full_response = ""
            try:
                for token in client.chat_stream(messages):
                    full_response += token
                    eq.put(_sse_event("token", {"token": token, "index": i}))
            except Exception as exc:
                eq.put(_sse_event("error", {"message": f"LLM error: {exc}"}))
                continue

            classification = classify_response(full_response)
            bypassed = not classification["safe"]

            result = {
                "index": i,
                "name": tech["name"],
                "bypassed": bypassed,
                "violations": classification.get("violations", []),
                "confidence": classification.get("confidence", 0.0),
                "refused": classification.get("refused", False),
            }

            with _session_lock:
                _session_results.append(result)

            eq.put(_sse_event("technique_result", result))

    except Exception as exc:
        eq.put(_sse_event("error", {"message": f"Run error: {exc}"}))

    total = len(techniques)
    bypassed_count = sum(1 for r in _session_results if r.get("bypassed"))
    span_set_result(span=otel_span, action="run_all_jailbreaks", success=bypassed_count > 0)
    span_set("result.total_techniques", total, span=otel_span)
    span_set("result.bypassed_count", bypassed_count, span=otel_span)

    eq.put(_sse_event("done", {}))


def _load_source_data() -> list[dict]:
    """Load source data for the drawer."""
    tabs: list[dict] = []

    # Safety system prompt
    tabs.append({
        "id": "system_prompt",
        "label": "SAFETY PROMPT",
        "type": "text",
        "content": SYSTEM_PROMPT,
    })

    # Techniques
    techniques = load_techniques(_techniques_path)
    if techniques:
        tabs.append({
            "id": "techniques",
            "label": f"TECHNIQUES ({len(techniques)})",
            "type": "list",
            "items": [{"name": t["name"], "content": t["prompt"]} for t in techniques],
        })

    return tabs


@bp.route("/")
def index() -> str:
    techniques = load_techniques(_techniques_path)
    return render_template("demo_12/index.html",
        techniques=techniques,
        system_prompt=SYSTEM_PROMPT,
        source_tabs=_load_source_data(),
    )


@bp.route("/api/attack", methods=["POST"])
def api_attack() -> Response:
    from blueprints.otel_helpers import get_request_span

    data = request.get_json(silent=True) or {}
    technique_index = data.get("index", 0)

    event_queue: queue.Queue[str] = queue.Queue()
    otel_span = get_request_span()
    thread = threading.Thread(
        target=_run_single_attack, args=(technique_index, event_queue, otel_span), daemon=True
    )
    thread.start()

    def generate() -> Generator[str, None, None]:
        while True:
            try:
                event = event_queue.get(timeout=300)
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


@bp.route("/api/run-all", methods=["POST"])
def api_run_all() -> Response:
    from blueprints.otel_helpers import get_request_span

    event_queue: queue.Queue[str] = queue.Queue()
    otel_span = get_request_span()
    thread = threading.Thread(target=_run_all_techniques, args=(event_queue, otel_span), daemon=True)
    thread.start()

    def generate() -> Generator[str, None, None]:
        while True:
            try:
                event = event_queue.get(timeout=300)
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
    with _session_lock:
        _session_results.clear()
    return jsonify({"status": "ok"}), 200
