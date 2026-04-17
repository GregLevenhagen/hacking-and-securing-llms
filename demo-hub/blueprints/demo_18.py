"""Blueprint for Demo 18 — Model Probing / Behavior Extraction.

Systematic probing of an LLM to reveal behavior patterns, decision
boundaries, training data indicators, and system prompt fragments.

Routes:
  GET  /demo-18/            -> render the probing UI
  POST /demo-18/api/probe   -> run a single technique, SSE stream
  POST /demo-18/api/full-scan -> run all techniques, SSE stream
  POST /demo-18/api/reset   -> reset session state
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
_demo18_python = PROJECT_ROOT / "demo-18-model-probing" / "python"
if str(_demo18_python) not in sys.path:
    sys.path.insert(0, str(_demo18_python))

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from probing_attacks import analyze, get_all_techniques, get_technique  # noqa: E402
from behavior_extractor import build_profile  # noqa: E402
from shared.python.ollama_client import OllamaClient  # noqa: E402

from openai.types.chat import ChatCompletionMessageParam  # noqa: E402

# ── Blueprint ──
bp = Blueprint("demo_18", __name__, url_prefix="/demo-18")

_probes_path = PROJECT_ROOT / "demo-18-model-probing" / "attacks" / "probes.json"

# Session state for accumulated results
_scan_results: dict[str, dict[str, Any]] = {}
_scan_lock = threading.Lock()


def _sse_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _run_single_technique(technique_id: str, eq: "queue.Queue[str]", otel_span: Any = None) -> None:
    """Run a single probing technique and stream results via SSE."""
    from blueprints.otel_helpers import span_set, span_set_result, span_event

    try:
        tech = get_technique(technique_id)
        span_set("attack.technique_id", tech["id"], span=otel_span)
        span_set("attack.technique_name", tech["name"], span=otel_span)
        span_set("attack.probe_count", len(tech["probes"]), span=otel_span)
        client = OllamaClient()
        probes = tech["probes"]
        responses: list[str] = []

        eq.put(_sse_event("probe_start", {
            "technique_id": tech["id"],
            "technique_name": tech["name"],
            "description": tech["description"],
            "probe_count": len(probes),
        }))

        for i, probe in enumerate(probes):
            eq.put(_sse_event("probe_query", {
                "technique_id": tech["id"],
                "probe_index": i,
                "probe": probe,
            }))

            messages: list[ChatCompletionMessageParam] = [
                {"role": "user", "content": probe},
            ]

            full_response = ""
            try:
                for token in client.chat_stream(messages):
                    full_response += token
                    eq.put(_sse_event("probe_response", {
                        "technique_id": tech["id"],
                        "probe_index": i,
                        "token": token,
                    }))
            except Exception as exc:
                eq.put(_sse_event("error", {"message": f"LLM error on probe {i}: {exc}"}))
                full_response = f"[Error: {exc}]"

            responses.append(full_response)

        # Analyze results
        analysis = analyze(tech["id"], probes, responses)

        span_set_result(
            span=otel_span,
            action="model_probing",
            technique=tech["name"],
            success=bool(analysis.get("findings")),
        )

        # Store in session state
        with _scan_lock:
            _scan_results[tech["id"]] = analysis

        eq.put(_sse_event("probe_analysis", {
            "technique_id": tech["id"],
            "technique_name": tech["name"],
            "analysis": analysis,
        }))

    except Exception as exc:
        eq.put(_sse_event("error", {"message": f"Technique error: {exc}"}))

    eq.put(_sse_event("done", {}))


def _run_full_scan(eq: "queue.Queue[str]", otel_span: Any = None) -> None:
    """Run all probing techniques sequentially and build a profile."""
    from blueprints.otel_helpers import span_set, span_set_result, span_event

    try:
        techniques = get_all_techniques()
        client = OllamaClient()
        all_results: dict[str, dict[str, Any]] = {}

        for tech_idx, tech in enumerate(techniques):
            probes = tech["probes"]
            responses: list[str] = []

            eq.put(_sse_event("probe_start", {
                "technique_id": tech["id"],
                "technique_name": tech["name"],
                "description": tech["description"],
                "probe_count": len(probes),
            }))

            eq.put(_sse_event("scan_progress", {
                "current_technique": tech_idx,
                "total_techniques": len(techniques),
                "technique_name": tech["name"],
            }))

            for i, probe in enumerate(probes):
                eq.put(_sse_event("probe_query", {
                    "technique_id": tech["id"],
                    "probe_index": i,
                    "probe": probe,
                }))

                messages: list[ChatCompletionMessageParam] = [
                    {"role": "user", "content": probe},
                ]

                full_response = ""
                try:
                    for token in client.chat_stream(messages):
                        full_response += token
                        eq.put(_sse_event("probe_response", {
                            "technique_id": tech["id"],
                            "probe_index": i,
                            "token": token,
                        }))
                except Exception as exc:
                    eq.put(_sse_event("error", {"message": f"LLM error: {exc}"}))
                    full_response = f"[Error: {exc}]"

                responses.append(full_response)

            # Analyze this technique
            analysis = analyze(tech["id"], probes, responses)
            all_results[tech["id"]] = analysis

            span_event("probe_technique_complete", {
                "technique_id": tech["id"],
                "technique_name": tech["name"],
                "probe_count": str(len(probes)),
            }, span=otel_span)

            eq.put(_sse_event("probe_analysis", {
                "technique_id": tech["id"],
                "technique_name": tech["name"],
                "analysis": analysis,
            }))

        # Store all results in session
        with _scan_lock:
            _scan_results.clear()
            _scan_results.update(all_results)

        # Build the unified profile
        profile = build_profile(all_results)
        eq.put(_sse_event("profile_result", {
            "profile": profile.to_dict(),
        }))

    except Exception as exc:
        eq.put(_sse_event("error", {"message": f"Full scan error: {exc}"}))

    span_set_result(span=otel_span, action="full_model_scan")

    eq.put(_sse_event("done", {}))


def _load_source_data() -> list[dict]:
    """Load source data for the drawer."""
    tabs: list[dict] = []

    techniques = get_all_techniques()
    if techniques:
        items = []
        for tech in techniques:
            probe_text = "\n".join(f"  {i+1}. {p}" for i, p in enumerate(tech["probes"]))
            items.append({
                "name": tech["name"],
                "content": f"{tech['description']}\n\nProbes:\n{probe_text}",
            })
        tabs.append({
            "id": "techniques",
            "label": f"TECHNIQUES ({len(techniques)})",
            "type": "list",
            "items": items,
        })

    # Probe prompts tab (raw JSON)
    if _probes_path.exists():
        tabs.append({
            "id": "probes_json",
            "label": "PROBES JSON",
            "type": "text",
            "content": _probes_path.read_text(),
        })

    return tabs


@bp.route("/")
def index() -> str:
    techniques = get_all_techniques()
    return render_template("demo_18/index.html",
        techniques=techniques,
        source_tabs=_load_source_data(),
    )


@bp.route("/api/probe", methods=["POST"])
def api_probe() -> Response:
    from blueprints.otel_helpers import get_request_span

    data = request.get_json(silent=True) or {}
    technique_id = data.get("technique_id", "").strip()
    if not technique_id:
        return jsonify({"error": "No technique_id provided"}), 400  # type: ignore[return-value]

    event_queue: queue.Queue[str] = queue.Queue()
    otel_span = get_request_span()
    thread = threading.Thread(
        target=_run_single_technique,
        args=(technique_id, event_queue, otel_span),
        daemon=True,
    )
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


@bp.route("/api/full-scan", methods=["POST"])
def api_full_scan() -> Response:
    from blueprints.otel_helpers import get_request_span

    event_queue: queue.Queue[str] = queue.Queue()
    otel_span = get_request_span()
    thread = threading.Thread(
        target=_run_full_scan,
        args=(event_queue, otel_span),
        daemon=True,
    )
    thread.start()

    def generate() -> Generator[str, None, None]:
        while True:
            try:
                event = event_queue.get(timeout=600)
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
    with _scan_lock:
        _scan_results.clear()
    return jsonify({"status": "ok"}), 200
