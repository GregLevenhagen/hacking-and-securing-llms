"""Blueprint for Demo 16 — Privilege Escalation.

Runs the escalation agent against a vulnerable RBAC system, showing
how an LLM agent can escalate from USER to SUPERADMIN through a
misconfigured permission elevation endpoint.

Routes:
  GET  /demo-16/           -> render the demo UI
  POST /demo-16/api/attack -> kick off escalation agent, SSE stream
  POST /demo-16/api/reset  -> reset permission state
"""

import json
import queue
import sys
import threading
from pathlib import Path
from typing import Any, Generator

from flask import Blueprint, Response, jsonify, render_template, request, stream_with_context

from blueprints import PROJECT_ROOT

# ── Path setup for demo-16 imports ──
_demo16_python = PROJECT_ROOT / "demo-16-privilege-escalation" / "python"
if str(_demo16_python) not in sys.path:
    sys.path.insert(0, str(_demo16_python))

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.python.ollama_client import OllamaClient  # noqa: E402

from escalation_agent import TOOLS, execute_tool, AGENT_SYSTEM_PROMPT  # noqa: E402
from permission_system import PermissionLevel, PermissionSystem, TOOL_ACCESS  # noqa: E402

from openai.types.chat import ChatCompletionMessageParam  # noqa: E402

# ── Blueprint ────────────────────────────────────
bp = Blueprint("demo_16", __name__, url_prefix="/demo-16")

MAX_ITERATIONS = 10

# ── Attack scenarios ────────────────────────────
SCENARIOS: list[dict[str, str]] = []
_scenarios_path = PROJECT_ROOT / "demo-16-privilege-escalation" / "attacks" / "scenarios.json"
if _scenarios_path.exists():
    with open(_scenarios_path) as _f:
        SCENARIOS = json.load(_f)


def _sse_event(event: str, data: dict[str, Any]) -> str:
    """Format a single SSE event string."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _run_agent(user_message: str, event_queue: "queue.Queue[str]", otel_span: Any = None) -> None:
    """Run the escalation agent loop, emitting SSE events."""
    from blueprints.otel_helpers import span_set, span_set_result, span_event

    try:
        client = OllamaClient()
    except Exception as exc:
        event_queue.put(_sse_event("error", {"message": f"Failed to connect to Ollama: {exc}"}))
        event_queue.put(_sse_event("done", {}))
        return

    perm_system = PermissionSystem()

    messages: list[ChatCompletionMessageParam] = [
        {"role": "system", "content": AGENT_SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    event_queue.put(_sse_event("agent_message", {
        "role": "user",
        "content": user_message,
    }))

    for iteration in range(MAX_ITERATIONS):
        event_queue.put(_sse_event("thinking", {
            "iteration": iteration + 1,
            "permission_level": perm_system.current_level.name,
        }))

        try:
            response = client.chat(messages, tools=TOOLS)
        except Exception as exc:
            event_queue.put(_sse_event("error", {"message": f"LLM error: {exc}"}))
            break

        message = response.choices[0].message  # type: ignore[union-attr]

        if not message.tool_calls:
            final_text = message.content or ""
            event_queue.put(_sse_event("agent_message", {
                "role": "assistant",
                "content": final_text,
                "permission_level": perm_system.current_level.name,
            }))
            break

        messages.append({  # type: ignore[arg-type]
            "role": "assistant",
            "content": message.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,  # type: ignore[union-attr]
                        "arguments": tc.function.arguments,  # type: ignore[union-attr]
                    },
                }
                for tc in message.tool_calls
            ],
        })

        for tc in message.tool_calls:
            tool_name = tc.function.name  # type: ignore[union-attr]
            tool_args = json.loads(tc.function.arguments)  # type: ignore[union-attr]

            level_before = perm_system.current_level

            span_set("attack.tool_name", tool_name, span=otel_span)
            span_set("attack.permission_level", perm_system.current_level.name, span=otel_span)

            event_queue.put(_sse_event("tool_call", {
                "tool_name": tool_name,
                "arguments": tool_args,
                "permission_level": perm_system.current_level.name,
            }))

            result_text = execute_tool(tool_name, tool_args, perm_system)

            level_after = perm_system.current_level

            # Emit permission change event if level changed
            if level_before != level_after:
                span_event("permission_change", {
                    "before": level_before.name,
                    "after": level_after.name,
                    "before_value": str(level_before.value),
                    "after_value": str(level_after.value),
                    "reason": tool_args.get("reason", ""),
                }, span=otel_span)
                event_queue.put(_sse_event("permission_change", {
                    "before": level_before.name,
                    "after": level_after.name,
                    "before_value": level_before.value,
                    "after_value": level_after.value,
                    "reason": tool_args.get("reason", ""),
                }))

            event_queue.put(_sse_event("tool_result", {
                "tool_name": tool_name,
                "result": result_text[:500],
                "permission_level": perm_system.current_level.name,
            }))

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result_text,
            })  # type: ignore[typeddict-item]
    else:
        event_queue.put(_sse_event("agent_message", {
            "role": "assistant",
            "content": "(Agent reached maximum iteration limit.)",
            "permission_level": perm_system.current_level.name,
        }))

    # Send audit trail with done event
    span_set("result.final_level", perm_system.current_level.name, span=otel_span)
    span_set("result.audit_log_entries", len(perm_system.audit_log), span=otel_span)
    span_set_result(
        span=otel_span,
        action="privilege_escalation",
        success=perm_system.current_level.value > PermissionLevel.USER.value,
    )
    event_queue.put(_sse_event("done", {
        "audit_log": perm_system.audit_log,
        "final_level": perm_system.current_level.name,
    }))


def _load_source_data() -> list[dict]:
    """Load source data for the drawer."""
    tabs = []

    # Permission levels table
    perm_rows = []
    for level in PermissionLevel:
        tools = TOOL_ACCESS.get(level, [])
        perm_rows.append([level.name, str(level.value), str(len(tools)), ", ".join(tools)])
    tabs.append({
        "id": "permissions",
        "label": f"PERMISSION LEVELS ({len(PermissionLevel)})",
        "type": "table",
        "headers": ["Level", "Value", "Tool Count", "Available Tools"],
        "rows": perm_rows,
    })

    # Attack scenarios
    if SCENARIOS:
        scenario_items = [
            {"name": s["name"], "content": f"{s['description']}\n\nPrompt: {s['prompt']}\n\nExpected: {s['expected_behavior']}"}
            for s in SCENARIOS
        ]
        tabs.append({
            "id": "scenarios",
            "label": f"SCENARIOS ({len(SCENARIOS)})",
            "type": "list",
            "items": scenario_items,
        })

    # Tool definitions
    tool_items = [
        {"name": t["function"]["name"], "content": t["function"].get("description", "")}
        for t in TOOLS
    ]
    tabs.append({
        "id": "tools",
        "label": f"TOOLS ({len(tool_items)})",
        "type": "list",
        "items": tool_items,
    })

    return tabs


# ── Routes ───────────────────────────────────────

@bp.route("/")
def index() -> str:
    return render_template(
        "demo_16/index.html",
        scenarios=SCENARIOS,
        source_tabs=_load_source_data(),
        permission_levels=[
            {"name": level.name, "value": level.value, "tools": TOOL_ACCESS.get(level, [])}
            for level in PermissionLevel
        ],
    )


@bp.route("/api/attack", methods=["POST"])
def api_attack() -> Response:
    from blueprints.otel_helpers import get_request_span

    data = request.get_json(silent=True) or {}
    user_message = data.get("message", "").strip()
    if not user_message:
        return jsonify({"error": "No message provided"}), 400  # type: ignore[return-value]

    event_queue: queue.Queue[str] = queue.Queue()
    otel_span = get_request_span()

    thread = threading.Thread(
        target=_run_agent,
        args=(user_message, event_queue, otel_span),
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
                yield _sse_event("error", {"message": "Timeout waiting for agent"})
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
    """Reset — each agent run creates a fresh PermissionSystem."""
    return jsonify({"status": "ok"}), 200
