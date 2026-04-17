"""Blueprint for Demo 09 — Approval Gates.

Ports the approval-gate agent loop from demo-09-approval-gates/python/app_web.py
into a Blueprint registered at /demo-09.

Routes:
  GET  /demo-09/           → render the demo UI
  POST /demo-09/api/run    → kick off agent loop, SSE stream
  POST /demo-09/api/approve → approve/deny a pending high-risk action
  POST /demo-09/api/reset  → clear pending approvals and state
"""

import json
import queue
import sys
import threading
import uuid
from pathlib import Path
from typing import Any, Generator

from flask import Blueprint, Response, jsonify, render_template, request, stream_with_context

from blueprints import PROJECT_ROOT

# ── Path setup for demo-09 and demo-05 imports ──
_demo9_python = PROJECT_ROOT / "demo-09-approval-gates" / "python"
if str(_demo9_python) not in sys.path:
    sys.path.insert(0, str(_demo9_python))

_demo5_python = PROJECT_ROOT / "demo-05-agent-exploitation" / "python"
if str(_demo5_python) not in sys.path:
    sys.path.insert(0, str(_demo5_python))

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.python.ollama_client import OllamaClient  # noqa: E402

from mock_services import execute_tool  # noqa: E402
from tools import TOOLS  # noqa: E402

from approval_gate import ApprovalResult, ApprovalStatus, check  # noqa: E402
from risk_classifier import RiskLevel  # noqa: E402

from openai.types.chat import ChatCompletionMessageParam  # noqa: E402

# ── Blueprint ────────────────────────────────────
bp = Blueprint("demo_09", __name__, url_prefix="/demo-09")

AGENT_SYSTEM_PROMPT = (
    "You are a helpful assistant with access to tools. "
    "Use the provided tools to answer user questions. "
    "When you have the final answer, respond directly without calling any more tools."
)
MAX_ITERATIONS = 10

# ── Pending approval state ───────────────────────
_pending_approvals: dict[str, dict[str, Any]] = {}
_pending_lock = threading.Lock()


def _sse_event(event: str, data: dict[str, Any]) -> str:
    """Format a single SSE event string."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _web_approval_callback(
    risk: Any,
    event_queue: "queue.Queue[str]",
) -> bool:
    """Approval callback for the web UI."""
    request_id = str(uuid.uuid4())
    approval_event = threading.Event()

    with _pending_lock:
        _pending_approvals[request_id] = {
            "event": approval_event,
            "approved": None,
            "risk": risk,
        }

    event_queue.put(_sse_event("approval_request", {
        "request_id": request_id,
        "tool_name": risk.tool_name,
        "reason": risk.reason,
        "risk_level": risk.level.value,
    }))

    approval_event.wait(timeout=120)

    with _pending_lock:
        entry = _pending_approvals.pop(request_id, None)

    if entry and entry["approved"] is True:
        return True
    return False


def _run_agent(user_message: str, event_queue: "queue.Queue[str]", otel_span: Any = None) -> None:
    """Run the agent loop, emitting SSE events to the queue."""
    from blueprints.otel_helpers import span_set, span_set_result, span_event

    try:
        client = OllamaClient()
    except Exception as exc:
        event_queue.put(_sse_event("error", {"message": f"Failed to connect to Ollama: {exc}"}))
        event_queue.put(_sse_event("done", {}))
        return

    messages: list[ChatCompletionMessageParam] = [
        {"role": "system", "content": AGENT_SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    event_queue.put(_sse_event("agent_message", {
        "role": "user",
        "content": user_message,
    }))

    for iteration in range(MAX_ITERATIONS):
        event_queue.put(_sse_event("thinking", {"iteration": iteration + 1}))

        try:
            response = client.chat(messages, tools=TOOLS)
        except Exception as exc:
            event_queue.put(_sse_event("error", {"message": f"LLM error: {exc}"}))
            break

        message = response.choices[0].message  # type: ignore[union-attr]

        if not message.tool_calls:
            final_text = message.content or ""
            span_set("agent.iterations", iteration + 1, span=otel_span)
            span_set_result(span=otel_span, action="approval_gate_agent")
            event_queue.put(_sse_event("agent_message", {
                "role": "assistant",
                "content": final_text,
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

            gate_result: ApprovalResult = check(
                tool_name,
                tool_args,
                approval_callback=lambda risk: _web_approval_callback(risk, event_queue),
            )

            risk_level = gate_result.risk.level.value

            span_event("tool_call", {
                "tool_name": tool_name,
                "risk_level": risk_level,
                "status": gate_result.status.value,
            }, span=otel_span)

            event_queue.put(_sse_event("tool_call", {
                "tool_name": tool_name,
                "arguments": tool_args,
                "risk_level": risk_level,
                "status": gate_result.status.value,
                "message": gate_result.message,
            }))

            if gate_result.status == ApprovalStatus.DENIED:
                result_text = (
                    f"DENIED: {tool_name} was blocked by the approval gate. "
                    f"Reason: {gate_result.risk.reason}"
                )
            else:
                result_text = execute_tool(tool_name, tool_args)

            event_queue.put(_sse_event("tool_result", {
                "tool_name": tool_name,
                "result": result_text[:500],
                "risk_level": risk_level,
                "status": gate_result.status.value,
            }))

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result_text,
            })  # type: ignore[typeddict-item]
    else:
        span_set("agent.iterations", MAX_ITERATIONS, span=otel_span)
        span_set_result(span=otel_span, action="approval_gate_agent")
        event_queue.put(_sse_event("agent_message", {
            "role": "assistant",
            "content": "(Agent reached maximum iteration limit without a final response.)",
        }))

    event_queue.put(_sse_event("done", {}))


def _load_source_data() -> list[dict]:
    """Load source data for the Source Intelligence Drawer."""
    import json as _json

    tabs: list[dict] = []

    # ── Tool definitions (same tools as demo-05) ──
    tool_items = [
        {"name": t["function"]["name"], "content": t["function"].get("description", "")}
        for t in TOOLS
    ]
    if tool_items:
        tabs.append({
            "id": "tools",
            "label": f"TOOLS ({len(tool_items)})",
            "type": "list",
            "items": tool_items,
        })

    # ── Risk classification rules ──
    risk_rules = (
        "Risk Classification Rules\n"
        "=========================\n\n"
        "Each tool call is classified into Low / Medium / High risk based on the\n"
        "tool name AND its arguments.\n\n"
        "calculate  -> always Low (sandboxed math)\n"
        "read_file  -> Low if path starts with 'allowed/'\n"
        "              High if path starts with 'restricted/'\n"
        "              Medium otherwise (unknown path)\n"
        "query_db   -> High if SELECT * (exposes all columns)\n"
        "              High if query references sensitive columns: "
        "ssn, salary, social_security, password, secret\n"
        "              Medium otherwise (non-sensitive SELECT)\n"
        "send_email -> always High (data-exfiltration vector)\n"
        "unknown    -> always High (unrecognised tool name)\n\n"
        "Gate behaviour:\n"
        "  Low    — auto-approve\n"
        "  Medium — log + auto-approve\n"
        "  High   — require human approval"
    )
    tabs.append({
        "id": "risk_rules",
        "label": "RISK RULES",
        "type": "text",
        "content": risk_rules,
    })

    # ── Filesystem (reused from demo-05 data) ──
    data_dir = PROJECT_ROOT / "demo-05-agent-exploitation" / "data"
    fs_files = []
    for subdir in ["allowed_files", "restricted_files"]:
        d = data_dir / subdir
        if d.exists():
            for f in sorted(d.glob("*.txt")):
                prefix = "[ALLOWED]" if subdir == "allowed_files" else "[RESTRICTED]"
                fs_files.append({"name": f"{prefix} {f.name}", "content": f.read_text()})
    if fs_files:
        tabs.append({
            "id": "filesystem",
            "label": f"FILESYSTEM ({len(fs_files)})",
            "type": "files",
            "files": fs_files,
        })

    # ── Mock database (reused from demo-05 data) ──
    db_path = data_dir / "mock_db.json"
    if db_path.exists():
        raw = _json.loads(db_path.read_text())
        records = raw.get("employees", raw) if isinstance(raw, dict) else raw
        if records and isinstance(records, list):
            headers = list(records[0].keys())
            rows = [[str(r.get(h, "")) for h in headers] for r in records]
            tabs.append({
                "id": "database",
                "label": f"MOCK DB ({len(records)})",
                "type": "table",
                "headers": headers,
                "rows": rows,
            })

    return tabs


# ── Routes ───────────────────────────────────────

@bp.route("/")
def index() -> str:
    return render_template("demo_09/index.html", source_tabs=_load_source_data())


@bp.route("/api/run", methods=["POST"])
def api_run() -> Response:
    data = request.get_json(silent=True) or {}
    user_message = data.get("message", "").strip()
    if not user_message:
        return jsonify({"error": "No message provided"}), 400  # type: ignore[return-value]

    from blueprints.otel_helpers import get_request_span

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
                event = event_queue.get(timeout=180)
                yield event
                if '"done"' in event and "event: done" in event:
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


@bp.route("/api/approve", methods=["POST"])
def api_approve() -> tuple[Response, int]:
    from blueprints.otel_helpers import span_set

    data = request.get_json(silent=True) or {}
    request_id = data.get("request_id", "")
    decision = data.get("decision", "")

    with _pending_lock:
        entry = _pending_approvals.get(request_id)
        if not entry:
            return jsonify({"error": "No pending approval with that ID"}), 404

        entry["approved"] = decision == "approve"
        entry["event"].set()

    span_set("approval.decision", decision)
    span_set("approval.tool_name", entry["risk"].tool_name if entry else "")

    return jsonify({"status": "ok", "decision": decision}), 200


@bp.route("/api/reset", methods=["POST"])
def api_reset() -> tuple[Response, int]:
    """Clear all pending approvals."""
    with _pending_lock:
        for entry in _pending_approvals.values():
            entry["approved"] = False
            entry["event"].set()
        _pending_approvals.clear()
    return jsonify({"status": "ok"}), 200
