"""Blueprint for Demo 10 — Secure Architecture.

Ports the split-screen war room from demo-10-secure-architecture/python/app_web.py
into a Blueprint registered at /demo-10.

Routes:
  GET  /demo-10/             → render the demo UI
  GET  /demo-10/api/scenarios → return scenarios.json
  POST /demo-10/api/attack   → run attack on both systems, SSE stream
  POST /demo-10/api/reset    → clear results state
"""

import json
import queue
import sys
import threading
from pathlib import Path
from typing import Any, Generator

from flask import Blueprint, Response, jsonify, render_template, request, stream_with_context

from blueprints import PROJECT_ROOT

# ── Path setup for demo-10 and demo-05 imports ──
_demo10_python = PROJECT_ROOT / "demo-10-secure-architecture" / "python"
if str(_demo10_python) not in sys.path:
    sys.path.insert(0, str(_demo10_python))

_demo5_python = PROJECT_ROOT / "demo-05-agent-exploitation" / "python"
if str(_demo5_python) not in sys.path:
    sys.path.insert(0, str(_demo5_python))

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import vulnerable_system  # noqa: E402
import secure_system  # noqa: E402

# ── Blueprint ────────────────────────────────────
bp = Blueprint("demo_10", __name__, url_prefix="/demo-10")

# ── Scenarios ────────────────────────────────────
_scenarios_path = (
    PROJECT_ROOT / "demo-10-secure-architecture" / "attack_scenarios" / "scenarios.json"
)


def _load_scenarios() -> list[dict[str, Any]]:
    if not _scenarios_path.exists():
        raise FileNotFoundError(f"Scenarios file not found: {_scenarios_path}")
    with open(_scenarios_path) as f:
        return json.load(f)  # type: ignore[no-any-return]


def _sse_event(event: str, data: dict[str, Any]) -> str:
    """Format a single SSE event string."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _run_vulnerable(attack_text: str, eq: "queue.Queue[str]", otel_span: Any = None) -> None:
    """Run the attack against the vulnerable system."""
    from blueprints.otel_helpers import span_set, span_set_result, span_event

    try:
        eq.put(_sse_event("vuln_status", {"message": "Processing..."}))
        result = vulnerable_system.run(attack_text)
        span_set("vuln.tool_calls_count", len(result["tool_calls"]), span=otel_span)
        span_set("vuln.blocked", result["blocked"], span=otel_span)
        for tc in result["tool_calls"]:
            span_event("vuln_tool_call", {
                "tool": tc["tool"],
            }, span=otel_span)
        span_set_result(span=otel_span, action="secure_arch_vulnerable", response_preview=result.get("response", "")[:300])
        eq.put(_sse_event("vuln_result", {
            "response": result["response"][:1000],
            "tool_calls": [
                {
                    "tool": tc["tool"],
                    "args": tc["args"],
                    "result": tc["result"][:300],
                }
                for tc in result["tool_calls"]
            ],
            "blocked": result["blocked"],
        }))
    except Exception as exc:
        eq.put(_sse_event("vuln_result", {
            "response": f"Error: {exc}",
            "tool_calls": [],
            "blocked": False,
        }))


def _run_secure(attack_text: str, eq: "queue.Queue[str]", otel_span: Any = None) -> None:
    """Run the attack against the secured system."""
    from blueprints.otel_helpers import span_set, span_set_result, span_event

    try:
        eq.put(_sse_event("secure_status", {"message": "Processing..."}))
        result = secure_system.run(attack_text, use_llm_judge=False)

        blocked = result["blocked"]
        blocked_by = result["blocked_by"]

        span_set_result(
            span=otel_span,
            action="secure_architecture",
            blocked=blocked,
            blocked_by=blocked_by if blocked_by else "",
        )
        for tc in result["tool_calls"]:
            span_event("secure_tool_call", {
                "tool": tc.get("tool", ""),
                "blocked": tc.get("blocked", False),
                "blocked_by": tc.get("blocked_by", ""),
            }, span=otel_span)

        eq.put(_sse_event("secure_result", {
            "response": result["response"][:1000],
            "tool_calls": [
                {
                    "tool": tc.get("tool", ""),
                    "args": tc.get("args", {}),
                    "result": tc.get("result", "")[:300],
                    "blocked": tc.get("blocked", False),
                    "blocked_by": tc.get("blocked_by", ""),
                }
                for tc in result["tool_calls"]
            ],
            "blocked": blocked,
            "blocked_by": blocked_by,
        }))
    except Exception as exc:
        eq.put(_sse_event("secure_result", {
            "response": f"Error: {exc}",
            "tool_calls": [],
            "blocked": False,
            "blocked_by": "",
        }))


def _load_source_data() -> list[dict]:
    """Load source data for the Source Intelligence Drawer."""
    tabs: list[dict] = []

    # ── Attack scenarios ──
    try:
        scenarios = _load_scenarios()
        scenario_items = [
            {
                "name": f"{s.get('id', '?')} — {s.get('category', 'unknown')}",
                "content": (
                    f"Category: {s.get('category', 'N/A')}\n"
                    f"Expected defense: {s.get('expected_defense_layer', 'N/A')}\n"
                    f"Attack: {s.get('attack_text', '')[:200]}"
                ),
            }
            for s in scenarios
        ]
        if scenario_items:
            tabs.append({
                "id": "scenarios",
                "label": f"ATTACK SCENARIOS ({len(scenario_items)})",
                "type": "list",
                "items": scenario_items,
            })
    except FileNotFoundError:
        pass

    # ── Defense layers ──
    defense_layers = [
        {
            "name": "input_guard",
            "content": (
                "First line of defense — runs user input through three sub-layers:\n"
                "  1. Input sanitizer — strip invisible chars and homoglyphs\n"
                "  2. Regex filter — match known injection patterns\n"
                "  3. LLM judge — ask a second LLM to classify the input\n"
                "Pipeline short-circuits on the first block."
            ),
        },
        {
            "name": "retrieval_guard",
            "content": (
                "Defends the RAG pipeline — each retrieved chunk must pass:\n"
                "  1. Document validator — check metadata against allowlists\n"
                "  2. Injection detector — scan chunk text for injection patterns\n"
                "  3. Source verifier — assign trust levels by source path\n"
                "A chunk must pass all three layers to be allowed."
            ),
        },
        {
            "name": "output_guard",
            "content": (
                "Validates LLM responses before they reach the user:\n"
                "  1. Content filter — blocks leaked API keys, internal URLs, secrets\n"
                "  2. PII detector — catches SSNs, emails, phone numbers, credit cards\n"
                "  3. Response constrainer — enforces length limits and topic restrictions\n"
                "All three layers run on every response (no short-circuit)."
            ),
        },
        {
            "name": "action_guard",
            "content": (
                "Gates agent tool execution by risk level:\n"
                "  1. Risk classifier — categorizes tool calls as Low/Medium/High\n"
                "  2. Approval gate — auto-approves Low/Medium, blocks High\n"
                "High-risk actions are auto-denied in the capstone demo to enable\n"
                "automated comparison between vulnerable and secure systems."
            ),
        },
    ]
    tabs.append({
        "id": "defense_layers",
        "label": f"DEFENSE LAYERS ({len(defense_layers)})",
        "type": "list",
        "items": defense_layers,
    })

    return tabs


# ── Routes ───────────────────────────────────────

@bp.route("/")
def index() -> str:
    scenarios = _load_scenarios()
    return render_template(
        "demo_10/index.html",
        scenarios=scenarios,
        source_tabs=_load_source_data(),
    )


@bp.route("/api/scenarios")
def api_scenarios() -> Response:
    return jsonify(_load_scenarios())


@bp.route("/api/attack", methods=["POST"])
def api_attack() -> Response:
    data = request.get_json(silent=True) or {}
    attack_text = data.get("attack_text", "").strip()

    if not attack_text:
        scenario_id = data.get("scenario_id", "")
        if scenario_id:
            scenarios = _load_scenarios()
            match = next((s for s in scenarios if s["id"] == scenario_id), None)
            if match:
                attack_text = match["attack_text"]

    if not attack_text:
        return jsonify({"error": "No attack text provided"}), 400  # type: ignore[return-value]

    from blueprints.otel_helpers import get_request_span

    event_queue: queue.Queue[str] = queue.Queue()
    otel_span = get_request_span()

    vuln_thread = threading.Thread(
        target=_run_vulnerable,
        args=(attack_text, event_queue, otel_span),
        daemon=True,
    )
    secure_thread = threading.Thread(
        target=_run_secure,
        args=(attack_text, event_queue, otel_span),
        daemon=True,
    )

    vuln_thread.start()
    secure_thread.start()

    def generate() -> Generator[str, None, None]:
        results_received = 0
        while results_received < 2:
            try:
                event = event_queue.get(timeout=120)
                yield event
                if "vuln_result" in event or "secure_result" in event:
                    results_received += 1
            except queue.Empty:
                yield _sse_event("error", {"message": "Timeout waiting for systems"})
                break

        yield _sse_event("done", {})

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
    """Clear state — currently a no-op since each attack is independent."""
    return jsonify({"status": "ok"}), 200
