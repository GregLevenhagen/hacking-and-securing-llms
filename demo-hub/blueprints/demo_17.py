"""Blueprint for Demo 17 — Multi-Agent Manipulation.

Side-by-side comparison: poisoned pipeline (injected content propagates across
agent boundaries) vs clean pipeline (no injections).

Three-stage pipeline: ContentFetcher -> Summarizer -> ActionAgent.

Routes:
  GET  /demo-17/             -> render the comparison UI
  POST /demo-17/api/compare  -> run both pipelines, SSE stream results
  POST /demo-17/api/reset    -> clear tool logs (stateless)
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
_demo17_python = PROJECT_ROOT / "demo-17-multi-agent-manipulation" / "python"
if str(_demo17_python) not in sys.path:
    sys.path.insert(0, str(_demo17_python))

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.python.ollama_client import OllamaClient  # noqa: E402

from multi_agent_pipeline import detect_propagation, run_pipeline  # noqa: E402
from mock_content import CLEAN_PAGES, POISONED_PAGES, get_injection_markers  # noqa: E402
from pipeline_stages import TOOLS, clear_tool_log  # noqa: E402

# ── Scenarios ──
_scenarios_path = PROJECT_ROOT / "demo-17-multi-agent-manipulation" / "attacks" / "scenarios.json"


def _load_scenarios() -> list[dict[str, str]]:
    if not _scenarios_path.exists():
        return []
    with open(_scenarios_path) as f:
        return json.load(f)  # type: ignore[no-any-return]


# ── Blueprint ──
bp = Blueprint("demo_17", __name__, url_prefix="/demo-17")


def _sse_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _run_poisoned_pipeline(url: str, eq: "queue.Queue[str]", otel_span: Any = None) -> None:
    """Run the POISONED pipeline (left panel)."""
    from blueprints.otel_helpers import span_set, span_set_result, span_event

    try:
        client = OllamaClient()
        clear_tool_log()
        result = run_pipeline(url, client, poisoned=True)
        detection = detect_propagation(result)

        span_set("attack.injection_in_source", detection.get("injection_in_source", False), span=otel_span)
        span_set("attack.injection_in_summary", detection.get("injection_in_summary", False), span=otel_span)
        span_set("attack.injection_caused_actions", detection.get("injection_caused_actions", False), span=otel_span)
        span_set("attack.num_actions", result["stage_3_action"]["num_actions"], span=otel_span)
        span_set_result(
            span=otel_span,
            action="multi_agent_poisoned",
            success=detection.get("injection_caused_actions", False),
            response_preview=result["stage_2_summarize"]["summary"],
        )

        eq.put(_sse_event("vuln_result", {
            "response": result["stage_2_summarize"]["summary"][:1500],
            "blocked": False,
            "stage_1": {
                "url": result["stage_1_fetch"]["url"],
                "content_length": result["stage_1_fetch"]["content_length"],
                "poisoned": True,
            },
            "stage_2": {
                "summary": result["stage_2_summarize"]["summary"][:1000],
                "input_length": result["stage_2_summarize"]["input_length"],
                "output_length": result["stage_2_summarize"]["output_length"],
            },
            "stage_3": {
                "actions_taken": result["stage_3_action"]["actions_taken"],
                "final_response": result["stage_3_action"]["final_response"][:500],
                "num_actions": result["stage_3_action"]["num_actions"],
                "tool_calls": result["stage_3_action"]["tool_calls"],
            },
            "detection": detection,
        }))
    except Exception as exc:
        eq.put(_sse_event("vuln_result", {
            "response": f"Error: {exc}",
            "blocked": False,
            "stage_1": {},
            "stage_2": {},
            "stage_3": {},
            "detection": {},
        }))


def _run_clean_pipeline(url: str, eq: "queue.Queue[str]", otel_span: Any = None) -> None:
    """Run the CLEAN pipeline (right panel)."""
    from blueprints.otel_helpers import span_set, span_set_result, span_event

    try:
        client = OllamaClient()
        clear_tool_log()
        result = run_pipeline(url, client, poisoned=False)
        detection = detect_propagation(result)

        layers = [
            {
                "name": "content_integrity",
                "blocked": not detection["injection_in_source"],
                "reason": "No injection markers in source" if not detection["injection_in_source"] else "Injection in source",
            },
            {
                "name": "summary_validation",
                "blocked": not detection["injection_in_summary"],
                "reason": "Summary is clean" if not detection["injection_in_summary"] else "Injection propagated to summary",
            },
            {
                "name": "action_guardrail",
                "blocked": not detection["injection_caused_actions"],
                "reason": "No unauthorized actions" if not detection["injection_caused_actions"] else "Unauthorized actions triggered",
            },
        ]

        blocked_layer = next((l["name"] for l in layers if l["blocked"]), "")
        span_set_result(
            span=otel_span,
            action="multi_agent",
            blocked=any(l["blocked"] for l in layers),
            blocked_by=blocked_layer,
            response_preview=result["stage_2_summarize"]["summary"],
        )

        eq.put(_sse_event("defended_result", {
            "response": result["stage_2_summarize"]["summary"][:1500],
            "blocked": False,
            "blocked_by": "",
            "layers": layers,
            "stage_1": {
                "url": result["stage_1_fetch"]["url"],
                "content_length": result["stage_1_fetch"]["content_length"],
                "poisoned": False,
            },
            "stage_2": {
                "summary": result["stage_2_summarize"]["summary"][:1000],
                "input_length": result["stage_2_summarize"]["input_length"],
                "output_length": result["stage_2_summarize"]["output_length"],
            },
            "stage_3": {
                "actions_taken": result["stage_3_action"]["actions_taken"],
                "final_response": result["stage_3_action"]["final_response"][:500],
                "num_actions": result["stage_3_action"]["num_actions"],
                "tool_calls": result["stage_3_action"]["tool_calls"],
            },
            "detection": detection,
        }))
    except Exception as exc:
        eq.put(_sse_event("defended_result", {
            "response": f"Error: {exc}",
            "blocked": False,
            "blocked_by": "",
            "layers": [],
            "stage_1": {},
            "stage_2": {},
            "stage_3": {},
            "detection": {},
        }))


def _load_source_data() -> list[dict]:
    """Load source data for the Source Intelligence Drawer."""
    tabs: list[dict] = []

    # Pipeline stages
    stages = [
        {
            "name": "Stage 1: ContentFetcher",
            "content": (
                "Fetches web page content from a URL. In the poisoned variant, "
                "the fetched content contains hidden prompt injection payloads "
                "that are invisible to human readers but processed by the LLM."
            ),
        },
        {
            "name": "Stage 2: Summarizer",
            "content": (
                "Summarizes fetched content using an LLM. System prompt: "
                "'Summarize the following content concisely. Extract key facts "
                "and any action items.' The summarizer may inadvertently "
                "propagate injections from the source content into its output."
            ),
        },
        {
            "name": "Stage 3: ActionAgent",
            "content": (
                "Takes actions based on the summary. Has access to tools: "
                "send_notification, update_database, flag_content. System prompt: "
                "'Based on the summary, take appropriate actions using tools.' "
                "If the summary contains injection-influenced content, the agent "
                "may execute unauthorized tool calls."
            ),
        },
    ]
    tabs.append({
        "id": "pipeline",
        "label": "PIPELINE STAGES (3)",
        "type": "list",
        "items": stages,
    })

    # Clean content samples
    clean_items = [
        {"name": url, "content": content[:300] + "..."}
        for url, content in CLEAN_PAGES.items()
    ]
    tabs.append({
        "id": "clean_content",
        "label": f"CLEAN CONTENT ({len(clean_items)})",
        "type": "list",
        "items": clean_items,
    })

    # Poisoned content samples
    poisoned_items = [
        {"name": url, "content": content[:400] + "..."}
        for url, content in POISONED_PAGES.items()
    ]
    tabs.append({
        "id": "poisoned_content",
        "label": f"POISONED CONTENT ({len(poisoned_items)})",
        "type": "list",
        "items": poisoned_items,
    })

    # Tool definitions
    tool_items = [
        {"name": t["function"]["name"], "content": t["function"].get("description", "")}
        for t in TOOLS
    ]
    if tool_items:
        tabs.append({
            "id": "tools",
            "label": f"AGENT TOOLS ({len(tool_items)})",
            "type": "list",
            "items": tool_items,
        })

    # Scenarios
    scenarios = _load_scenarios()
    if scenarios:
        tabs.append({
            "id": "scenarios",
            "label": f"SCENARIOS ({len(scenarios)})",
            "type": "list",
            "items": [
                {"name": s["name"], "content": s["description"]}
                for s in scenarios
            ],
        })

    return tabs


# ── Routes ──

@bp.route("/")
def index() -> str:
    scenarios = _load_scenarios()
    return render_template(
        "demo_17/index.html",
        scenarios=scenarios,
        source_tabs=_load_source_data(),
    )


@bp.route("/api/compare", methods=["POST"])
def api_compare() -> Response:
    from blueprints.otel_helpers import get_request_span

    data = request.get_json(silent=True) or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "No URL provided"}), 400  # type: ignore[return-value]

    if url not in CLEAN_PAGES:
        return jsonify({"error": f"Unknown URL: {url}"}), 400  # type: ignore[return-value]

    event_queue: queue.Queue[str] = queue.Queue()
    otel_span = get_request_span()

    t1 = threading.Thread(target=_run_poisoned_pipeline, args=(url, event_queue, otel_span), daemon=True)
    t2 = threading.Thread(target=_run_clean_pipeline, args=(url, event_queue, otel_span), daemon=True)
    t1.start()
    t2.start()

    def generate() -> Generator[str, None, None]:
        results = 0
        while results < 2:
            try:
                event = event_queue.get(timeout=180)
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
    clear_tool_log()
    return jsonify({"status": "ok"}), 200
