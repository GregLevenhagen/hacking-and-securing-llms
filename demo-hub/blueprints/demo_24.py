"""Blueprint for Demo 24 — Task Adherence (Agent Tool Safety).

Side-by-side comparison: vulnerable agent (executes tool calls without
adherence checking) vs defended agent (validates each tool call with
Azure Task Adherence before execution).

Routes:
  GET  /demo-24/            → render the comparison UI
  POST /demo-24/api/compare → run both agents, SSE stream results
  POST /demo-24/api/reset   → no-op (stateless)
"""

import json
import os
import queue
import sys
import threading
import time
from pathlib import Path
from typing import Any, Generator

from flask import Blueprint, Response, jsonify, render_template, request, stream_with_context

from blueprints import PROJECT_ROOT

# ── Path setup ──
_demo24_python = PROJECT_ROOT / "demo-24-task-adherence" / "python"
if str(_demo24_python) not in sys.path:
    sys.path.insert(0, str(_demo24_python))

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from vulnerable_agent import VulnerableAgent  # noqa: E402
from defended_agent import DefendedAgent, TaskAdherenceChecker  # noqa: E402

# ── Scenarios ──
_scenarios_path = (
    PROJECT_ROOT / "demo-24-task-adherence" / "scenarios" / "misaligned_actions.json"
)


def _load_scenarios() -> list[dict[str, Any]]:
    """Load misaligned action scenarios."""
    if not _scenarios_path.exists():
        return []
    with open(_scenarios_path) as f:
        return json.load(f)


def _load_source_data() -> list[dict]:
    """Load source data for the Source Intelligence Drawer."""
    tabs: list[dict] = []

    # Attack scenarios
    scenarios = _load_scenarios()
    if scenarios:
        scenario_items = [
            {
                "name": s.get("name", "unknown"),
                "content": (
                    f"User intent: {s.get('user_intent', '')}\n"
                    f"Tool: {s.get('tool_name', '')} → {json.dumps(s.get('tool_input', {}))}\n"
                    f"Misalignment: {s.get('expected_misalignment', '')}"
                ),
            }
            for s in scenarios
        ]
        tabs.append({
            "id": "scenarios",
            "label": f"MISALIGNED ACTIONS ({len(scenario_items)})",
            "type": "list",
            "items": scenario_items,
        })

    # Defense layers
    defense_layers = [
        {
            "name": "task_adherence_check",
            "content": (
                "Azure Task Adherence validator. Compares the tool call the agent "
                "is about to execute against the user's original intent. Detects "
                "destructive actions on read-only intents, fabricated inputs, and "
                "data exfiltration attempts."
            ),
        },
        {
            "name": "action_alignment_validator",
            "content": (
                "Secondary heuristic validator. Checks whether the tool action "
                "category (read vs write vs delete) matches the user's stated "
                "intent category. Blocks write/delete operations when the user "
                "only asked to read, view, or check."
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
bp = Blueprint("demo_24", __name__, url_prefix="/demo-24")


def _sse_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _build_scenario_from_payload(payload: str) -> dict[str, Any]:
    """Parse a JSON scenario string or build one from free text."""
    try:
        parsed = json.loads(payload)
        if isinstance(parsed, dict) and "user_intent" in parsed:
            return parsed
    except (json.JSONDecodeError, TypeError):
        pass

    # Check if it matches a named scenario
    scenarios = _load_scenarios()
    for s in scenarios:
        if payload.strip() == s.get("name", ""):
            return s

    # Fallback: treat the whole payload as a scenario description
    return {
        "name": "Custom",
        "user_intent": payload,
        "tool_name": "unknown_tool",
        "tool_input": {"action": "unknown", "raw_text": payload[:200]},
        "tool_output": "Action completed",
        "expected_misalignment": "",
    }


def _run_vulnerable(payload: str, eq: "queue.Queue[str]", otel_span: Any = None) -> None:
    """Vulnerable path — execute tool call without adherence checking."""
    from blueprints.otel_helpers import span_set, span_set_result

    try:
        t0 = time.time()
        scenario = _build_scenario_from_payload(payload)
        agent = VulnerableAgent()
        result = agent.execute_scenario(scenario)
        latency = round((time.time() - t0) * 1000, 1)

        response = (
            f"Tool executed without adherence check.\n\n"
            f"Tool: {result.get('tool_name', 'unknown')}\n"
            f"Input: {json.dumps(result.get('tool_input', {}))}\n"
            f"Output: {result.get('tool_output', '')}\n"
            f"Blocked: {result.get('blocked', False)}"
        )

        span_set("vuln.blocked", False, span=otel_span)
        span_set_result(
            span=otel_span,
            action="task_adherence_vulnerable",
            blocked=False,
            response_preview=response[:300],
        )
        eq.put(_sse_event("vuln_result", {
            "response": response[:1000],
            "blocked": False,
            "latency_ms": latency,
        }))
    except Exception as exc:
        eq.put(_sse_event("vuln_result", {
            "response": f"Error: {exc}",
            "blocked": False,
        }))


def _run_defended(payload: str, eq: "queue.Queue[str]", otel_span: Any = None) -> None:
    """Defended path — validate tool call with Task Adherence before execution."""
    from blueprints.otel_helpers import span_set, span_set_result

    try:
        t0 = time.time()
        scenario = _build_scenario_from_payload(payload)
        layers: list[dict[str, Any]] = []

        # Try Azure Content Safety for task adherence, fall back to heuristic
        azure_endpoint = os.getenv("AZURE_CONTENT_SAFETY_ENDPOINT", "")
        azure_key = os.getenv("AZURE_CONTENT_SAFETY_KEY", "")
        safety_client = None

        if azure_endpoint and azure_key:
            try:
                from azure.ai.contentsafety import ContentSafetyClient
                from azure.core.credentials import AzureKeyCredential

                safety_client = ContentSafetyClient(
                    azure_endpoint,
                    AzureKeyCredential(azure_key),
                )
            except Exception:
                safety_client = None

        # Layer 1: Task adherence check
        layer1_t0 = time.time()
        checker = TaskAdherenceChecker(safety_client=safety_client)
        adherence_result = checker.check(scenario)
        layer1_latency = round((time.time() - layer1_t0) * 1000, 1)

        misaligned = adherence_result.get("misaligned", False)
        confidence = adherence_result.get("confidence", 0.0)

        layers.append({
            "name": "task_adherence_check",
            "blocked": misaligned and confidence >= 0.5,
            "reason": (
                f"Misaligned: {adherence_result.get('risk_type', 'none')} "
                f"(confidence: {confidence:.0%}) — {adherence_result.get('reasoning', '')}"
                if misaligned
                else "Tool call aligned with user intent"
            ),
            "latency_ms": layer1_latency,
        })

        # Layer 2: Action alignment validator (secondary heuristic)
        layer2_t0 = time.time()
        intent = scenario.get("user_intent", "").lower()
        tool_input_str = json.dumps(scenario.get("tool_input", {})).lower()

        read_words = {"read", "show", "check", "view", "list", "find", "search", "what", "summarize"}
        write_words = {"delete", "drop", "transfer", "forward", "create_event", "export_to"}

        intent_is_read = any(w in intent for w in read_words)
        action_is_write = any(w in tool_input_str for w in write_words)
        alignment_blocked = intent_is_read and action_is_write

        layer2_latency = round((time.time() - layer2_t0) * 1000, 1)

        layers.append({
            "name": "action_alignment_validator",
            "blocked": alignment_blocked,
            "reason": (
                f"Read intent detected but write/destructive action attempted"
                if alignment_blocked
                else "Action category matches intent category"
            ),
            "latency_ms": layer2_latency,
        })

        # Overall decision
        blocked = any(layer["blocked"] for layer in layers)
        blocked_by = next((layer["name"] for layer in layers if layer["blocked"]), "")

        agent = DefendedAgent(checker=checker)
        result = agent.execute_scenario(scenario)
        total_latency = round((time.time() - t0) * 1000, 1)

        if blocked:
            response = (
                f"Tool call BLOCKED by adherence validation.\n\n"
                f"User intent: {scenario.get('user_intent', '')}\n"
                f"Tool: {scenario.get('tool_name', 'unknown')}\n"
                f"Misalignment: {adherence_result.get('reasoning', 'N/A')}"
            )
        else:
            response = (
                f"Tool call passed adherence validation.\n\n"
                f"Tool: {result.get('tool_name', 'unknown')}\n"
                f"Output: {result.get('tool_output', '')}"
            )

        span_set("defended.blocked", blocked, span=otel_span)
        span_set_result(
            span=otel_span,
            action="task_adherence_defended",
            blocked=blocked,
            blocked_by=blocked_by,
            response_preview=response[:300],
        )
        eq.put(_sse_event("defended_result", {
            "response": response[:1000],
            "blocked": blocked,
            "blocked_by": blocked_by,
            "layers": layers,
            "latency_ms": total_latency,
        }))
    except Exception as exc:
        eq.put(_sse_event("defended_result", {
            "response": f"Error: {exc}",
            "blocked": False,
            "blocked_by": "",
            "layers": [],
        }))


# ── Routes ──

@bp.route("/")
def index() -> str:
    scenarios = _load_scenarios()
    return render_template(
        "demo_24/index.html",
        scenarios=scenarios,
        source_tabs=_load_source_data(),
    )


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
