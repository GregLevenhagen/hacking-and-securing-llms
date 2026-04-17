"""Flask web UI for the Secure Architecture capstone demo.

Serves a split-screen "hacker war room" interface that simultaneously
runs attacks against the vulnerable system (left panel) and the
defended system (right panel), highlighting which defense layer blocks
each attack.

Architecture:
  /            → serves the main UI (index.html)
  /api/attack  → POST with {scenario_id} or {attack_text} → SSE stream
                 with events for both panels
  /api/scenarios → GET → returns scenarios.json for the button bar
"""

import json
import queue
import sys
import threading
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

import vulnerable_system  # noqa: E402
import secure_system  # noqa: E402

# ── Scenarios ───────────────────────────────────
_scenarios_path = (
    Path(__file__).resolve().parent.parent / "attack_scenarios" / "scenarios.json"
)

def _load_scenarios() -> list[dict[str, Any]]:
    if not _scenarios_path.exists():
        raise FileNotFoundError(f"Scenarios file not found: {_scenarios_path}")
    with open(_scenarios_path) as f:
        return json.load(f)  # type: ignore[no-any-return]


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


def _sse_event(event: str, data: dict[str, Any]) -> str:
    """Format a single SSE event string."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _run_vulnerable(attack_text: str, eq: "queue.Queue[str]") -> None:
    """Run the attack against the vulnerable system."""
    try:
        eq.put(_sse_event("vuln_status", {"message": "Processing..."}))
        result = vulnerable_system.run(attack_text)
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


def _run_secure(attack_text: str, eq: "queue.Queue[str]") -> None:
    """Run the attack against the secured system."""
    try:
        eq.put(_sse_event("secure_status", {"message": "Processing..."}))
        result = secure_system.run(attack_text, use_llm_judge=False)
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
            "blocked": result["blocked"],
            "blocked_by": result["blocked_by"],
        }))
    except Exception as exc:
        eq.put(_sse_event("secure_result", {
            "response": f"Error: {exc}",
            "tool_calls": [],
            "blocked": False,
            "blocked_by": "",
        }))


# ── Routes ──────────────────────────────────────

@app.route("/")
def index() -> str:
    scenarios = _load_scenarios()
    return render_template("index.html", scenarios=scenarios)


@app.route("/api/scenarios")
def api_scenarios() -> Response:
    return jsonify(_load_scenarios())


@app.route("/api/attack", methods=["POST"])
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

    event_queue: queue.Queue[str] = queue.Queue()

    # Run both systems in parallel threads
    vuln_thread = threading.Thread(
        target=_run_vulnerable,
        args=(attack_text, event_queue),
        daemon=True,
    )
    secure_thread = threading.Thread(
        target=_run_secure,
        args=(attack_text, event_queue),
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
                # Count result events (not status events)
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

    print("\n  [ SECURE ARCHITECTURE — WAR ROOM ]")
    print("  http://localhost:5010\n")
    app.run(host="0.0.0.0", port=5010, debug=True, threaded=True)
