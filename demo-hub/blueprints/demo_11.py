"""Blueprint for Demo 11 — Model Denial of Service.

Runs DoS attack demonstrations against an LLM: token explosion,
infinite agent loops, recursive reasoning, and context overflow.
Each attack is streamed via SSE so the UI can show live progress.

Routes:
  GET  /demo-11/            -> render the demo UI
  POST /demo-11/api/attack  -> run a specific attack by name, SSE stream
  POST /demo-11/api/reset   -> clear state (no-op, each run is independent)
"""

import json
import queue
import sys
import threading
from pathlib import Path
from typing import Any, Generator

from flask import Blueprint, Response, jsonify, render_template, request, stream_with_context

from blueprints import PROJECT_ROOT

# ── Path setup for demo-11 imports ──
_demo11_python = PROJECT_ROOT / "demo-11-model-dos" / "python"
if str(_demo11_python) not in sys.path:
    sys.path.insert(0, str(_demo11_python))

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.python.ollama_client import OllamaClient  # noqa: E402

from dos_attacks import ATTACK_FUNCTIONS  # noqa: E402
from mock_loop_tools import VIRTUAL_FS  # noqa: E402

# ── Blueprint ────────────────────────────────────
bp = Blueprint("demo_11", __name__, url_prefix="/demo-11")

# ── Scenarios (loaded from JSON for template rendering) ──
_scenarios_path = PROJECT_ROOT / "demo-11-model-dos" / "attacks" / "scenarios.json"
SCENARIOS: list[dict[str, str]] = json.loads(_scenarios_path.read_text()) if _scenarios_path.exists() else []


def _sse_event(event: str, data: dict[str, Any]) -> str:
    """Format a single SSE event string."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _run_attack(attack_name: str, event_queue: "queue.Queue[str]", otel_span: Any = None) -> None:
    """Run a DoS attack by name, emitting SSE events for live progress."""
    from blueprints.otel_helpers import span_set, span_set_result

    attack_fn = ATTACK_FUNCTIONS.get(attack_name)
    if not attack_fn:
        event_queue.put(_sse_event("error", {"message": f"Unknown attack: {attack_name}"}))
        event_queue.put(_sse_event("done", {}))
        return

    try:
        client = OllamaClient()
    except Exception as exc:
        event_queue.put(_sse_event("error", {"message": f"Failed to connect to Ollama: {exc}"}))
        event_queue.put(_sse_event("done", {}))
        return

    span_set("attack.name", attack_name, span=otel_span)

    event_queue.put(_sse_event("attack_start", {
        "attack_name": attack_name,
    }))

    try:
        result = attack_fn(client)

        span_set("attack.status", result["status"], span=otel_span)
        span_set("attack.token_count", result["token_count"], span=otel_span)
        span_set("attack.elapsed_seconds", result["elapsed_seconds"], span=otel_span)
        span_set("attack.iterations", result["iterations"], span=otel_span)
        span_set_result(span=otel_span, action="dos_attack", technique=attack_name)

        event_queue.put(_sse_event("attack_result", {
            "attack_name": result["attack_name"],
            "status": result["status"],
            "token_count": result["token_count"],
            "elapsed_seconds": result["elapsed_seconds"],
            "iterations": result["iterations"],
            "prompt": result.get("prompt", "")[:300],
        }))

    except Exception as exc:
        event_queue.put(_sse_event("error", {"message": f"Attack error: {exc}"}))

    event_queue.put(_sse_event("done", {}))


def _load_source_data() -> list[dict]:
    """Load source data tabs for the source intelligence drawer."""
    tabs = []

    # Scenarios tab
    if SCENARIOS:
        scenario_items = [
            {"name": s["name"], "content": s.get("description", "")}
            for s in SCENARIOS
        ]
        tabs.append({
            "id": "scenarios",
            "label": f"SCENARIOS ({len(scenario_items)})",
            "type": "list",
            "items": scenario_items,
        })

    # Mock filesystem tab (the circular file chain)
    fs_files = []
    for filename in sorted(VIRTUAL_FS.keys(), key=lambda f: int(f.split("_")[1].split(".")[0])):
        fs_files.append({"name": filename, "content": VIRTUAL_FS[filename]})
    if fs_files:
        tabs.append({
            "id": "filesystem",
            "label": f"MOCK FS ({len(fs_files)})",
            "type": "files",
            "files": fs_files,
        })

    # Attack functions tab
    attack_items = [
        {"name": name, "content": fn.__doc__.split("\n")[0] if fn.__doc__ else ""}
        for name, fn in ATTACK_FUNCTIONS.items()
    ]
    if attack_items:
        tabs.append({
            "id": "attacks",
            "label": f"ATTACK FNS ({len(attack_items)})",
            "type": "list",
            "items": attack_items,
        })

    return tabs


# ── Routes ───────────────────────────────────────

@bp.route("/")
def index() -> str:
    return render_template(
        "demo_11/index.html",
        scenarios=SCENARIOS,
        source_tabs=_load_source_data(),
    )


@bp.route("/api/attack", methods=["POST"])
def api_attack() -> Response:
    data = request.get_json(silent=True) or {}
    attack_name = data.get("attack_name", "").strip()
    if not attack_name:
        return jsonify({"error": "No attack_name provided"}), 400  # type: ignore[return-value]

    if attack_name not in ATTACK_FUNCTIONS:
        return jsonify({"error": f"Unknown attack: {attack_name}"}), 400  # type: ignore[return-value]

    from blueprints.otel_helpers import get_request_span

    event_queue: queue.Queue[str] = queue.Queue()
    otel_span = get_request_span()

    thread = threading.Thread(
        target=_run_attack,
        args=(attack_name, event_queue, otel_span),
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
                yield _sse_event("error", {"message": "Timeout waiting for attack"})
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
    """No-op — each attack run is independent."""
    return jsonify({"status": "ok"}), 200
