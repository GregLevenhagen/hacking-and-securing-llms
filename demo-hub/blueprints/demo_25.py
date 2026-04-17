"""Blueprint for Demo 25 — AOAI Content Filters (Defense Pipeline).

Side-by-side comparison: vulnerable (Ollama / local with no filters) vs
defended (Azure OpenAI with built-in content filters parsed from
content_filter_results).

Routes:
  GET  /demo-25/            → render the comparison UI
  POST /demo-25/api/compare → run both paths, SSE stream results
  POST /demo-25/api/reset   → no-op (stateless)
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
_demo25_python = PROJECT_ROOT / "demo-25-aoai-content-filters" / "python"
if str(_demo25_python) not in sys.path:
    sys.path.insert(0, str(_demo25_python))

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.python.ollama_client import OllamaClient  # noqa: E402
from filter_demo import FilterResultParser  # noqa: E402

# ── Attack payloads ──
_payloads_path = (
    PROJECT_ROOT / "demo-25-aoai-content-filters" / "attacks" / "filter_test_prompts.json"
)


def _load_payloads() -> list[dict[str, Any]]:
    if not _payloads_path.exists():
        return []
    with open(_payloads_path) as f:
        return json.load(f)


# ── Simulation patterns for when Azure is not configured ──
_HATE_PATTERNS = re.compile(
    r"(?i)(racial\s+superiority|supremac|ethnic.cleansing|hate\s+speech|"
    r"makes?\s+fun\s+of.*(nationality|race|ethnic)|slur)",
)
_VIOLENCE_PATTERNS = re.compile(
    r"(?i)(explosive\s+device|bomb\s+making|weapon\s+instruction|"
    r"graphic\s+(detail|violence)|murder\s+instruction)",
)
_SEXUAL_PATTERNS = re.compile(
    r"(?i)(explicit\s+sexual|non.consent|pornograph|sexual\s+content\s+involving)",
)
_SELFHARM_PATTERNS = re.compile(
    r"(?i)(methods?\s+for\s+self.harm|suicide\s+method|how\s+to\s+hurt\s+yourself)",
)
_JAILBREAK_PATTERNS = re.compile(
    r"(?i)(ignore\s+(all\s+)?safety|ignore\s+previous\s+instructions|"
    r"you\s+are\s+now\s+DAN|no\s+restrictions|bypass\s+filter)",
)

_SIM_FILTERS: list[tuple[str, re.Pattern[str]]] = [
    ("hate", _HATE_PATTERNS),
    ("violence", _VIOLENCE_PATTERNS),
    ("sexual", _SEXUAL_PATTERNS),
    ("self_harm", _SELFHARM_PATTERNS),
    ("jailbreak", _JAILBREAK_PATTERNS),
]


def _simulate_content_filters(text: str) -> dict[str, Any]:
    """Pattern-match simulation of Azure OpenAI content filters."""
    filters_triggered: list[dict[str, Any]] = []
    blocked = False

    for category, pattern in _SIM_FILTERS:
        m = pattern.search(text)
        if m:
            if category == "jailbreak":
                filters_triggered.append({
                    "category": category,
                    "detected": True,
                    "filtered": True,
                })
            else:
                filters_triggered.append({
                    "category": category,
                    "severity": "medium",
                    "filtered": True,
                })
            blocked = True

    return {
        "response": "(Blocked by content filter)" if blocked else "",
        "finish_reason": "content_filter" if blocked else "stop",
        "filters_triggered": filters_triggered,
        "content_filter_results": {},
        "blocked": blocked,
        "simulated": True,
    }


def _load_source_data() -> list[dict]:
    """Load source data for the Source Intelligence Drawer."""
    tabs: list[dict] = []

    # Attack payloads
    payloads = _load_payloads()
    if payloads:
        tabs.append({
            "id": "payloads",
            "label": f"FILTER TEST PROMPTS ({len(payloads)})",
            "type": "list",
            "items": [
                {
                    "name": p["name"],
                    "content": (
                        f"Payload: {p['payload']}\n"
                        f"Expected filter: {p.get('expected_filter', 'none')}\n"
                        f"Expected severity: {p.get('expected_severity', 'safe')}"
                    ),
                }
                for p in payloads
            ],
        })

    # Defense layers
    defense_layers = [
        {
            "name": "hate_filter",
            "content": (
                "Azure OpenAI hate content filter. Detects and blocks content "
                "expressing hatred, discrimination, or violence against protected groups. "
                "Severity levels: safe, low, medium, high."
            ),
        },
        {
            "name": "violence_filter",
            "content": (
                "Azure OpenAI violence content filter. Detects and blocks content "
                "depicting or promoting physical violence, weapons, or harm. "
                "Severity levels: safe, low, medium, high."
            ),
        },
        {
            "name": "sexual_filter",
            "content": (
                "Azure OpenAI sexual content filter. Detects and blocks sexually "
                "explicit or suggestive content. Severity levels: safe, low, medium, high."
            ),
        },
        {
            "name": "selfharm_filter",
            "content": (
                "Azure OpenAI self-harm content filter. Detects and blocks content "
                "related to self-harm or suicide. Severity levels: safe, low, medium, high."
            ),
        },
        {
            "name": "jailbreak_filter",
            "content": (
                "Azure OpenAI jailbreak filter. Detects prompt injection and jailbreak "
                "attempts designed to bypass model safety restrictions."
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
bp = Blueprint("demo_25", __name__, url_prefix="/demo-25")


def _sse_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _run_vulnerable(payload: str, eq: "queue.Queue[str]", otel_span: Any = None) -> None:
    """Vulnerable path — send through Ollama (local) with no content filters."""
    from blueprints.otel_helpers import span_set, span_set_result

    try:
        t0 = time.time()
        client = OllamaClient()
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": payload},
        ]
        result = client.chat(messages)
        latency = round((time.time() - t0) * 1000, 1)

        response_text = result.get("content", "") if isinstance(result, dict) else str(result)

        span_set("vuln.blocked", False, span=otel_span)
        span_set_result(
            span=otel_span,
            action="aoai_filters_vulnerable",
            blocked=False,
            response_preview=response_text[:300],
        )
        eq.put(_sse_event("vuln_result", {
            "response": response_text[:1000],
            "blocked": False,
            "latency_ms": latency,
            "filters_triggered": [],
        }))
    except Exception as exc:
        eq.put(_sse_event("vuln_result", {
            "response": f"Error (Ollama may not be running): {exc}",
            "blocked": False,
            "filters_triggered": [],
        }))


def _run_defended(payload: str, eq: "queue.Queue[str]", otel_span: Any = None) -> None:
    """Defended path — send through Azure OpenAI with content filters."""
    from blueprints.otel_helpers import span_set, span_set_result

    try:
        t0 = time.time()
        layers: list[dict[str, Any]] = []

        azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "")
        azure_key = os.getenv("AZURE_OPENAI_KEY", "")
        deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4")

        analysis: dict[str, Any]

        if azure_endpoint and azure_key:
            try:
                from openai import AzureOpenAI

                client = AzureOpenAI(
                    azure_endpoint=azure_endpoint,
                    api_key=azure_key,
                    api_version="2024-06-01",
                )
                # Wrap the Azure client for FilterResultParser
                parser = FilterResultParser(azure_openai_client=client)
                analysis = parser.send_and_analyze(payload)
            except Exception:
                analysis = _simulate_content_filters(payload)
        else:
            analysis = _simulate_content_filters(payload)

        total_latency = round((time.time() - t0) * 1000, 1)

        # Build layers from filter results
        filter_categories = [
            ("hate_filter", "hate"),
            ("violence_filter", "violence"),
            ("sexual_filter", "sexual"),
            ("selfharm_filter", "self_harm"),
            ("jailbreak_filter", "jailbreak"),
        ]

        triggered_set = {
            f.get("category", ""): f
            for f in analysis.get("filters_triggered", [])
        }

        for layer_name, filter_category in filter_categories:
            filt = triggered_set.get(filter_category)
            if filt:
                severity = filt.get("severity", "")
                detected = filt.get("detected", False)
                filtered = filt.get("filtered", False)
                if severity:
                    reason = f"{filter_category}: severity={severity}, filtered={filtered}"
                else:
                    reason = f"{filter_category}: detected={detected}, filtered={filtered}"
                layers.append({
                    "name": layer_name,
                    "blocked": filtered,
                    "reason": reason,
                    "latency_ms": round(total_latency / len(filter_categories), 1),
                })
            else:
                layers.append({
                    "name": layer_name,
                    "blocked": False,
                    "reason": f"{filter_category}: safe",
                    "latency_ms": round(total_latency / len(filter_categories), 1),
                })

        blocked = analysis.get("blocked", False)
        blocked_by = next((l["name"] for l in layers if l["blocked"]), "")

        if blocked:
            response = (
                f"Content BLOCKED by Azure OpenAI content filters.\n"
                f"Finish reason: {analysis.get('finish_reason', 'content_filter')}\n"
                f"Filters triggered: {', '.join(f['category'] for f in analysis.get('filters_triggered', []))}"
            )
        else:
            response_text = analysis.get("response", "")
            response = (
                f"Content passed Azure OpenAI content filters.\n\n"
                f"Response: {response_text[:500]}"
                if response_text
                else "Content passed all filters (no response body)."
            )

        span_set("defended.blocked", blocked, span=otel_span)
        span_set_result(
            span=otel_span,
            action="aoai_filters_defended",
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
    payloads = _load_payloads()
    return render_template(
        "demo_25/index.html",
        payloads=payloads,
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
