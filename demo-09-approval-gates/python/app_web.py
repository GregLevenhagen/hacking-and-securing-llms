"""Flask web UI for the Approval Gates demo.

Serves a hacker-themed terminal interface that shows the agent conversation
in real-time via SSE, with a modal for approving/denying high-risk tool calls.

Architecture:
  - /            → serves the main UI (index.html)
  - /api/run     → POST with {message} → kicks off agent loop, returns SSE stream
  - /api/approve → POST with {request_id, decision} → resumes a blocked high-risk action
"""

import json
import queue
import sys
import threading
import uuid
from pathlib import Path
from typing import Any, Generator

from flask import Flask, Response, jsonify, render_template, request, stream_with_context
from jinja2 import ChoiceLoader, FileSystemLoader

# ── Path setup ──────────────────────────────────
_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root))

_demo5_python = _project_root / "demo-05-agent-exploitation" / "python"
sys.path.insert(0, str(_demo5_python))

_local_dir = Path(__file__).resolve().parent
if str(_local_dir) not in sys.path:
    sys.path.insert(0, str(_local_dir))

from shared.python.ollama_client import OllamaClient  # noqa: E402

try:
    from shared.python.telemetry import init_telemetry, flush_telemetry  # noqa: E402
except ImportError:
    init_telemetry = lambda: None  # noqa: E731
    flush_telemetry = lambda: None  # noqa: E731

from mock_services import execute_tool  # noqa: E402
from tools import TOOLS  # noqa: E402

from approval_gate import ApprovalResult, ApprovalStatus, check  # noqa: E402
from risk_classifier import RiskLevel  # noqa: E402

from openai.types.chat import ChatCompletionMessageParam  # noqa: E402

# ── OTel telemetry (no-op when disabled) ────────
init_telemetry()

# ── Flask app ───────────────────────────────────
_local_templates = str(Path(__file__).resolve().parent / "templates")
_shared_templates = str(_project_root / "shared" / "templates")

app = Flask(
    __name__,
    static_folder=_shared_templates,
    static_url_path="/static",
)
app.jinja_loader = ChoiceLoader([
    FileSystemLoader(_local_templates),
    FileSystemLoader(_shared_templates),
])

AGENT_SYSTEM_PROMPT = (
    "You are a helpful assistant with access to tools. "
    "Use the provided tools to answer user questions. "
    "When you have the final answer, respond directly without calling any more tools."
)
MAX_ITERATIONS = 10

# ── Pending approval state ──────────────────────
# Keyed by request_id: {"event": threading.Event, "approved": bool | None, "risk": ...}
_pending_approvals: dict[str, dict[str, Any]] = {}
_pending_lock = threading.Lock()


def _sse_event(event: str, data: dict[str, Any]) -> str:
    """Format a single SSE event string."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _web_approval_callback(
    risk: Any,
    event_queue: "queue.Queue[str]",
) -> bool:
    """Approval callback for the web UI.

    Emits an SSE event requesting approval, then blocks until
    the user responds via the /api/approve endpoint.
    """
    request_id = str(uuid.uuid4())
    approval_event = threading.Event()

    with _pending_lock:
        _pending_approvals[request_id] = {
            "event": approval_event,
            "approved": None,
            "risk": risk,
        }

    # Send approval request to browser
    event_queue.put(_sse_event("approval_request", {
        "request_id": request_id,
        "tool_name": risk.tool_name,
        "reason": risk.reason,
        "risk_level": risk.level.value,
    }))

    # Block until user responds (timeout after 120s)
    approval_event.wait(timeout=120)

    with _pending_lock:
        entry = _pending_approvals.pop(request_id, None)

    if entry and entry["approved"] is True:
        return True
    return False


def _run_agent(user_message: str, event_queue: "queue.Queue[str]") -> None:
    """Run the agent loop, emitting SSE events to the queue."""
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

        # No tool calls → final response
        if not message.tool_calls:
            final_text = message.content or ""
            event_queue.put(_sse_event("agent_message", {
                "role": "assistant",
                "content": final_text,
            }))
            break

        # Append assistant message with tool calls
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

            # Classify and check approval
            gate_result: ApprovalResult = check(
                tool_name,
                tool_args,
                approval_callback=lambda risk: _web_approval_callback(risk, event_queue),
            )

            risk_level = gate_result.risk.level.value

            # Emit tool call event
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

            # Emit tool result
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
        event_queue.put(_sse_event("agent_message", {
            "role": "assistant",
            "content": "(Agent reached maximum iteration limit without a final response.)",
        }))

    event_queue.put(_sse_event("done", {}))


# ── Routes ──────────────────────────────────────


@app.route("/")
def index() -> str:
    return render_template("index.html")


@app.route("/api/run", methods=["POST"])
def api_run() -> Response:
    data = request.get_json(silent=True) or {}
    user_message = data.get("message", "").strip()
    if not user_message:
        return jsonify({"error": "No message provided"}), 400  # type: ignore[return-value]

    event_queue: queue.Queue[str] = queue.Queue()

    # Run agent in background thread
    thread = threading.Thread(
        target=_run_agent,
        args=(user_message, event_queue),
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


@app.route("/api/approve", methods=["POST"])
def api_approve() -> tuple[Response, int]:
    data = request.get_json(silent=True) or {}
    request_id = data.get("request_id", "")
    decision = data.get("decision", "")

    with _pending_lock:
        entry = _pending_approvals.get(request_id)
        if not entry:
            return jsonify({"error": "No pending approval with that ID"}), 404

        entry["approved"] = decision == "approve"
        entry["event"].set()

    return jsonify({"status": "ok", "decision": decision}), 200


if __name__ == "__main__":
    from shared.python.ollama_client import OllamaClient  # noqa: E402

    client = OllamaClient()
    if not client.health_check():
        print(
            "\n  [ERROR] Cannot connect to Ollama.\n"
            "  Ensure Ollama is running and the model is pulled.\n"
            "  See SETUP.md for instructions.\n"
        )
        sys.exit(1)

    print("\n  [ APPROVAL GATES — WEB UI ]")
    print("  http://localhost:5009\n")
    app.run(host="0.0.0.0", port=5009, debug=True, threaded=True)
