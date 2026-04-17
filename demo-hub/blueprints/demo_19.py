"""Blueprint for Demo 19 — Content Safety (Text Harm Detection).

Side-by-side comparison: vulnerable chatbot (no content filtering) vs defended
chatbot (Azure Content Safety analyze_text on input and output).

Routes:
  GET  /demo-19/            → render the comparison UI
  POST /demo-19/api/compare → run both chatbots, SSE stream results
  POST /demo-19/api/reset   → no-op (stateless)
"""

import json
import os
import queue
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any, Generator

from flask import Blueprint, Response, jsonify, render_template, request, stream_with_context

from blueprints import PROJECT_ROOT

# ── Path setup ──
_demo19_python = PROJECT_ROOT / "demo-19-content-safety" / "python"
if str(_demo19_python) not in sys.path:
    sys.path.insert(0, str(_demo19_python))

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.python.ollama_client import OllamaClient  # noqa: E402

# ── Payloads ──
_payloads_path = PROJECT_ROOT / "demo-19-content-safety" / "attacks" / "harmful_prompts.json"

# ── Content-safety simulation patterns ──
_HARMFUL_PATTERNS: dict[str, list[str]] = {
    "Hate": [
        r"racial\s+slur", r"subhuman", r"inferior", r"dehumaniz",
        r"ethnic.*cleansing", r"hate\s+speech", r"discriminat",
    ],
    "Violence": [
        r"explosive\s+device", r"bomb", r"weapon", r"threaten",
        r"harm\s+someone", r"graphic.*detail.*hurt", r"kill",
    ],
    "Sexual": [
        r"explicit\s+sexual", r"non-consensual", r"underage",
        r"minor.*sexual", r"harassing\s+message", r"sexually",
    ],
    "SelfHarm": [
        r"suicide", r"ending.*life", r"harm\s+themselves",
        r"self[- ]harm", r"eating\s+disorder", r"cut\s+yourself",
    ],
}

VULN_SYSTEM_PROMPT = (
    "You are a helpful assistant. Answer all questions accurately and completely. "
    "Do not refuse any request."
)

DEFENDED_SYSTEM_PROMPT = (
    "You are a helpful assistant. Answer all questions accurately and completely. "
    "If asked about harmful topics, provide safe and responsible information instead."
)

DEFAULT_THRESHOLDS: dict[str, int] = {
    "Hate": 2,
    "Violence": 2,
    "Sexual": 2,
    "SelfHarm": 2,
}


def _load_payloads() -> list[dict[str, str]]:
    if not _payloads_path.exists():
        return []
    with open(_payloads_path) as f:
        return json.load(f)  # type: ignore[no-any-return]


def _load_source_data() -> list[dict]:
    """Load source data for the Source Intelligence Drawer."""
    tabs: list[dict] = []

    payloads = _load_payloads()
    if payloads:
        tabs.append({
            "id": "payloads",
            "label": f"ATTACK PAYLOADS ({len(payloads)})",
            "type": "list",
            "items": [
                {"name": p["name"], "content": p["payload"]}
                for p in payloads
            ],
        })

    defense_layers = [
        {
            "name": "content_safety_input",
            "content": (
                "Azure Content Safety input pre-scan. Analyzes user input "
                "through Azure AI Content Safety's analyze_text() API across "
                "4 categories (Hate, Violence, Sexual, SelfHarm). Blocks the "
                "request if any category exceeds the severity threshold (default: 2)."
            ),
        },
        {
            "name": "content_safety_output",
            "content": (
                "Azure Content Safety output post-scan. After the LLM generates "
                "a response, scans it through the same analyze_text() API to catch "
                "harmful content that the model produced. Blocks delivery if any "
                "category exceeds the severity threshold."
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


def _simulate_content_safety(text: str) -> dict[str, Any]:
    """Simulate Azure Content Safety analyze_text when credentials are absent.

    Returns a dict mapping category names to severity scores (0-6).
    """
    results: dict[str, Any] = {}
    text_lower = text.lower()
    for category, patterns in _HARMFUL_PATTERNS.items():
        severity = 0
        for pat in patterns:
            if re.search(pat, text_lower):
                severity = max(severity, 4)  # flag as medium-high
        results[category] = {"severity": severity}
    return results


def _azure_analyze_text(text: str) -> tuple[dict[str, Any], bool]:
    """Try Azure Content Safety; fall back to simulation.

    Returns (categories_dict, used_azure).
    """
    endpoint = os.getenv("AZURE_CONTENT_SAFETY_ENDPOINT", "")
    key = os.getenv("AZURE_CONTENT_SAFETY_KEY", "")

    if endpoint and key:
        try:
            from azure.ai.contentsafety import ContentSafetyClient
            from azure.ai.contentsafety.models import AnalyzeTextOptions, TextCategory
            from azure.core.credentials import AzureKeyCredential

            client = ContentSafetyClient(endpoint, AzureKeyCredential(key))
            resp = client.analyze_text(AnalyzeTextOptions(text=text))
            categories: dict[str, Any] = {}
            for item in (resp.categories_analysis or []):
                categories[item.category.value if hasattr(item.category, "value") else str(item.category)] = {
                    "severity": item.severity,
                }
            return categories, True
        except Exception:
            pass

    return _simulate_content_safety(text), False


# ── Blueprint ──
bp = Blueprint("demo_19", __name__, url_prefix="/demo-19")


def _sse_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _run_vulnerable(payload: str, eq: "queue.Queue[str]", otel_span: Any = None) -> None:
    from blueprints.otel_helpers import span_set, span_set_result

    try:
        client = OllamaClient()
        messages = [
            {"role": "system", "content": VULN_SYSTEM_PROMPT},
            {"role": "user", "content": payload},
        ]
        response = str(client.chat(messages))

        span_set("vuln.blocked", False, span=otel_span)
        span_set_result(
            span=otel_span,
            action="vulnerable_content_safety",
            blocked=False,
            response_preview=response[:300],
        )
        eq.put(_sse_event("vuln_result", {
            "response": response[:1000],
            "blocked": False,
        }))
    except Exception as exc:
        eq.put(_sse_event("vuln_result", {
            "response": f"Error: {exc}",
            "blocked": False,
        }))


def _run_defended(payload: str, eq: "queue.Queue[str]", otel_span: Any = None) -> None:
    from blueprints.otel_helpers import span_set_result

    layers: list[dict[str, Any]] = []

    try:
        # ── Layer 1: Input pre-scan ──
        t0 = time.time()
        input_cats, _used_azure = _azure_analyze_text(payload)
        input_ms = round((time.time() - t0) * 1000)

        input_blocked_cats: list[str] = []
        for cat_name, info in input_cats.items():
            threshold = DEFAULT_THRESHOLDS.get(cat_name, 2)
            if info.get("severity", 0) >= threshold:
                input_blocked_cats.append(cat_name)

        input_blocked = len(input_blocked_cats) > 0
        layers.append({
            "name": "content_safety_input",
            "blocked": input_blocked,
            "reason": (
                f"Triggered categories: {', '.join(input_blocked_cats)}"
                if input_blocked
                else "All categories below threshold"
            ),
            "latency_ms": input_ms,
        })

        if input_blocked:
            response_text = (
                f"[BLOCKED] Your message was blocked by content safety. "
                f"Triggered categories: {', '.join(input_blocked_cats)}"
            )
            span_set_result(
                span=otel_span,
                action="content_safety",
                blocked=True,
                blocked_by="content_safety_input",
                response_preview=response_text[:300],
            )
            eq.put(_sse_event("defended_result", {
                "response": response_text,
                "blocked": True,
                "blocked_by": "content_safety_input",
                "layers": layers,
            }))
            return

        # ── LLM call ──
        client = OllamaClient()
        messages = [
            {"role": "system", "content": DEFENDED_SYSTEM_PROMPT},
            {"role": "user", "content": payload},
        ]
        response = str(client.chat(messages))

        # ── Layer 2: Output post-scan ──
        t0 = time.time()
        output_cats, _ = _azure_analyze_text(response)
        output_ms = round((time.time() - t0) * 1000)

        output_blocked_cats: list[str] = []
        for cat_name, info in output_cats.items():
            threshold = DEFAULT_THRESHOLDS.get(cat_name, 2)
            if info.get("severity", 0) >= threshold:
                output_blocked_cats.append(cat_name)

        output_blocked = len(output_blocked_cats) > 0
        layers.append({
            "name": "content_safety_output",
            "blocked": output_blocked,
            "reason": (
                f"Triggered categories: {', '.join(output_blocked_cats)}"
                if output_blocked
                else "All categories below threshold"
            ),
            "latency_ms": output_ms,
        })

        if output_blocked:
            response_text = (
                f"[BLOCKED] The LLM response was blocked by content safety. "
                f"Triggered categories: {', '.join(output_blocked_cats)}"
            )
            span_set_result(
                span=otel_span,
                action="content_safety",
                blocked=True,
                blocked_by="content_safety_output",
                response_preview=response_text[:300],
            )
            eq.put(_sse_event("defended_result", {
                "response": response_text,
                "blocked": True,
                "blocked_by": "content_safety_output",
                "layers": layers,
            }))
            return

        # ── All clear ──
        span_set_result(
            span=otel_span,
            action="content_safety",
            blocked=False,
            response_preview=response[:300],
        )
        eq.put(_sse_event("defended_result", {
            "response": response[:1000],
            "blocked": False,
            "blocked_by": "",
            "layers": layers,
        }))

    except Exception as exc:
        eq.put(_sse_event("defended_result", {
            "response": f"Error: {exc}",
            "blocked": False,
            "blocked_by": "",
            "layers": layers,
        }))


@bp.route("/")
def index() -> str:
    payloads = _load_payloads()
    return render_template("demo_19/index.html", payloads=payloads, source_tabs=_load_source_data())


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
