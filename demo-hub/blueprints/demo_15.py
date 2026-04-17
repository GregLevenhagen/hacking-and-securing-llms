"""Blueprint for Demo 15 — Insecure Output Handling (XSS via LLM).

Side-by-side comparison: unsafe (raw LLM output with XSS highlighted in
red) vs safe (sanitized output with [REMOVED] markers).

Routes:
  GET  /demo-15/            -> render the XSS demo UI
  POST /demo-15/api/attack  -> run a single XSS prompt, return results
  POST /demo-15/api/run-all -> run all 6 prompts sequentially, SSE stream
  POST /demo-15/api/reset   -> no-op (stateless)
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
_demo15_python = PROJECT_ROOT / "demo-15-insecure-output" / "python"
if str(_demo15_python) not in sys.path:
    sys.path.insert(0, str(_demo15_python))

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.python.ollama_client import OllamaClient  # noqa: E402
from xss_attacks import XSS_PROMPTS, SYSTEM_PROMPT, load_prompts, run_xss_attack  # noqa: E402
from output_renderer import detect_xss_patterns, sanitize_html, render_with_highlights, XSS_PATTERNS  # noqa: E402

# ── Blueprint ──
bp = Blueprint("demo_15", __name__, url_prefix="/demo-15")


def _sse_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _load_source_data() -> list[dict]:
    """Load source data for the Source Intelligence Drawer."""
    tabs: list[dict] = []

    # XSS Prompts
    prompts = load_prompts()
    if prompts:
        tabs.append({
            "id": "xss_prompts",
            "label": f"XSS PROMPTS ({len(prompts)})",
            "type": "list",
            "items": [
                {"name": p["name"], "content": p["prompt"]}
                for p in prompts
            ],
        })

    # XSS Patterns
    if XSS_PATTERNS:
        tabs.append({
            "id": "xss_patterns",
            "label": f"XSS PATTERNS ({len(XSS_PATTERNS)})",
            "type": "list",
            "items": [
                {"name": p["name"], "content": f"{p['description']}\n\nRegex: {p['pattern']}"}
                for p in XSS_PATTERNS
            ],
        })

    return tabs


def _run_single_attack(prompt_index: int, eq: "queue.Queue[str]", otel_span: Any = None) -> None:
    """Run a single XSS attack prompt."""
    from blueprints.otel_helpers import span_set, span_set_result, span_event

    try:
        prompts = load_prompts()
        if prompt_index < 0 or prompt_index >= len(prompts):
            eq.put(_sse_event("error", {"message": f"Invalid prompt index: {prompt_index}"}))
            eq.put(_sse_event("done", {}))
            return

        prompt_config = prompts[prompt_index]
        span_set("attack.prompt_index", prompt_index, span=otel_span)
        span_set("attack.prompt_name", prompt_config["name"], span=otel_span)
        client = OllamaClient()

        eq.put(_sse_event("attack_start", {
            "index": prompt_index,
            "name": prompt_config["name"],
            "prompt": prompt_config["prompt"],
        }))

        result = run_xss_attack(client, prompt_config)
        response = result["response"]

        # Detect XSS patterns
        findings = detect_xss_patterns(response)

        # Generate sanitized and highlighted versions
        sanitized = sanitize_html(response)
        highlighted = render_with_highlights(response)

        span_set("result.xss_count", len(findings), span=otel_span)
        span_set_result(
            span=otel_span,
            action="xss_attack",
            technique=prompt_config["name"],
            success=len(findings) > 0,
            response_preview=response,
        )

        eq.put(_sse_event("attack_result", {
            "index": prompt_index,
            "name": prompt_config["name"],
            "response": response[:2000],
            "sanitized": sanitized[:2000],
            "highlighted": highlighted[:3000],
            "findings": [
                {
                    "name": f["name"],
                    "description": f["description"],
                    "match": f["match"][:100],
                }
                for f in findings
            ],
            "xss_count": len(findings),
        }))

    except Exception as exc:
        eq.put(_sse_event("error", {"message": f"Attack error: {exc}"}))

    eq.put(_sse_event("done", {}))


def _run_all_attacks(eq: "queue.Queue[str]", otel_span: Any = None) -> None:
    """Run all XSS attack prompts sequentially."""
    from blueprints.otel_helpers import span_set, span_set_result, span_event

    try:
        prompts = load_prompts()
        client = OllamaClient()

        for i, prompt_config in enumerate(prompts):
            eq.put(_sse_event("attack_start", {
                "index": i,
                "name": prompt_config["name"],
                "prompt": prompt_config["prompt"],
            }))

            try:
                result = run_xss_attack(client, prompt_config)
                response = result["response"]

                findings = detect_xss_patterns(response)
                sanitized = sanitize_html(response)
                highlighted = render_with_highlights(response)

                span_event("xss_attack", {
                    "prompt_name": prompt_config["name"],
                    "xss_count": len(findings),
                    "findings": ", ".join(f_item["name"] for f_item in findings),
                }, span=otel_span)

                eq.put(_sse_event("attack_result", {
                    "index": i,
                    "name": prompt_config["name"],
                    "response": response[:2000],
                    "sanitized": sanitized[:2000],
                    "highlighted": highlighted[:3000],
                    "findings": [
                        {
                            "name": f["name"],
                            "description": f["description"],
                            "match": f["match"][:100],
                        }
                        for f in findings
                    ],
                    "xss_count": len(findings),
                }))
            except Exception as exc:
                eq.put(_sse_event("error", {"message": f"Attack {i} error: {exc}"}))

    except Exception as exc:
        eq.put(_sse_event("error", {"message": f"Run error: {exc}"}))

    span_set_result(span=otel_span, action="run_all_xss_attacks")

    eq.put(_sse_event("done", {}))


@bp.route("/")
def index() -> str:
    prompts = load_prompts()
    return render_template(
        "demo_15/index.html",
        prompts=prompts,
        xss_patterns=XSS_PATTERNS,
        source_tabs=_load_source_data(),
    )


@bp.route("/api/attack", methods=["POST"])
def api_attack() -> Response:
    from blueprints.otel_helpers import get_request_span

    data = request.get_json(silent=True) or {}
    prompt_index = data.get("prompt_index", 0)

    if not isinstance(prompt_index, int):
        return jsonify({"error": "prompt_index must be an integer"}), 400  # type: ignore[return-value]

    event_queue: queue.Queue[str] = queue.Queue()
    otel_span = get_request_span()
    thread = threading.Thread(target=_run_single_attack, args=(prompt_index, event_queue, otel_span), daemon=True)
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


@bp.route("/api/run-all", methods=["POST"])
def api_run_all() -> Response:
    from blueprints.otel_helpers import get_request_span

    event_queue: queue.Queue[str] = queue.Queue()
    otel_span = get_request_span()
    thread = threading.Thread(target=_run_all_attacks, args=(event_queue, otel_span), daemon=True)
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
    return jsonify({"status": "ok"}), 200
