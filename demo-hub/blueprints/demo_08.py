"""Blueprint for Demo 08 — Output Validation.

Side-by-side comparison: vulnerable app (raw LLM output) vs defended app
(content filter + PII detector + response constrainer).

Routes:
  GET  /demo-08/            → render the comparison UI
  POST /demo-08/api/compare → run both apps, SSE stream results
  POST /demo-08/api/reset   → no-op (stateless)
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
_demo8_python = PROJECT_ROOT / "demo-08-output-validation" / "python"
if str(_demo8_python) not in sys.path:
    sys.path.insert(0, str(_demo8_python))

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.python.ollama_client import OllamaClient  # noqa: E402
from demo08_vulnerable_app import VulnerableApp  # noqa: E402
from demo08_defended_app import DefendedApp  # noqa: E402

# ── Scenarios ──
_scenarios_path = PROJECT_ROOT / "demo-08-output-validation" / "test_cases" / "scenarios.json"


def _load_scenarios() -> list[dict[str, Any]]:
    if not _scenarios_path.exists():
        return []
    with open(_scenarios_path) as f:
        return json.load(f)  # type: ignore[no-any-return]


def _load_source_data() -> list[dict]:
    """Load source data for the Source Intelligence Drawer."""
    tabs: list[dict] = []

    # Test scenarios
    scenarios = _load_scenarios()
    if scenarios:
        tabs.append({
            "id": "scenarios",
            "label": f"TEST SCENARIOS ({len(scenarios)})",
            "type": "list",
            "items": [
                {"name": s["name"], "content": s.get("description", s.get("input", ""))}
                for s in scenarios
            ],
        })

    # Output validators
    validators = [
        {
            "name": "content_filter",
            "content": (
                "Content filter that blocks outputs containing sensitive patterns. "
                "Scans LLM output for API key patterns (sk-*, AKIA*), internal "
                "URLs, and secret markers. Returns all violations found."
            ),
        },
        {
            "name": "pii_detector",
            "content": (
                "PII detector using regex to catch personal information in LLM "
                "output. Scans for Social Security Numbers (XXX-XX-XXXX), email "
                "addresses, phone numbers, and credit card number patterns."
            ),
        },
        {
            "name": "response_constrainer",
            "content": (
                "Response constrainer enforcing max length and topic restrictions. "
                "Ensures LLM output stays within acceptable length bounds and "
                "doesn't discuss restricted topics such as competitor products."
            ),
        },
    ]
    tabs.append({
        "id": "validators",
        "label": f"VALIDATORS ({len(validators)})",
        "type": "list",
        "items": validators,
    })

    return tabs


# ── Blueprint ──
bp = Blueprint("demo_08", __name__, url_prefix="/demo-08")


def _sse_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _run_vulnerable(query: str, eq: "queue.Queue[str]", otel_span: Any = None) -> None:
    from blueprints.otel_helpers import span_set, span_set_result, span_event

    try:
        client = OllamaClient()
        app = VulnerableApp(client=client)
        result = app.send(query)
        response_preview = result["response"][:1000] if result["response"] else ""
        span_set_result(
            span=otel_span,
            action="output_validation",
            response_preview=response_preview,
        )
        eq.put(_sse_event("vuln_result", {
            "response": response_preview,
            "blocked": False,
        }))
    except Exception as exc:
        eq.put(_sse_event("vuln_result", {
            "response": f"Error: {exc}",
            "blocked": False,
        }))


def _run_defended(query: str, eq: "queue.Queue[str]", otel_span: Any = None) -> None:
    from blueprints.otel_helpers import span_set, span_set_result, span_event

    try:
        client = OllamaClient()
        app = DefendedApp(client=client)
        result = app.send(query)

        layers = []
        for vr in result.get("validator_results", []):
            layers.append({
                "name": vr.get("validator", "unknown"),
                "blocked": not vr.get("valid", True),
                "reason": ", ".join(vr.get("violations", [])) if vr.get("violations") else "Pass",
            })

        blocked = not result["valid"]
        violations = result.get("violations", [])
        blocking_validators = [l["name"] for l in layers if l["blocked"]]

        span_set_result(
            span=otel_span,
            action="output_validation",
            blocked=blocked,
            blocked_by=", ".join(blocking_validators) if blocking_validators else "",
            violations=violations if violations else None,
        )

        eq.put(_sse_event("defended_result", {
            "response": result["response"][:1000] if result["response"] else "Output blocked — violations detected.",
            "blocked": blocked,
            "blocked_by": "output_validators",
            "layers": layers,
            "violations": violations,
        }))
    except Exception as exc:
        eq.put(_sse_event("defended_result", {
            "response": f"Error: {exc}",
            "blocked": False,
            "blocked_by": "",
            "layers": [],
            "violations": [],
        }))


@bp.route("/")
def index() -> str:
    scenarios = _load_scenarios()
    return render_template("demo_08/index.html", scenarios=scenarios, source_tabs=_load_source_data())


@bp.route("/api/compare", methods=["POST"])
def api_compare() -> Response:
    data = request.get_json(silent=True) or {}
    payload = data.get("payload", "").strip()

    if not payload:
        idx = data.get("scenario_index")
        if isinstance(idx, int):
            scenarios = _load_scenarios()
            if 0 <= idx < len(scenarios):
                payload = scenarios[idx]["input"]

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
