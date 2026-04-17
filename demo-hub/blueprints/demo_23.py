"""Blueprint for Demo 23 — Custom Categories (Domain Moderation).

Side-by-side comparison: vulnerable (no custom-category scanning) vs defended
(Azure Custom Categories / Rapid API scanning for financial_fraud,
competitor_mention, pii_leakage).

Routes:
  GET  /demo-23/            → render the comparison UI
  POST /demo-23/api/compare → run both paths, SSE stream results
  POST /demo-23/api/reset   → no-op (stateless)
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
_demo23_python = PROJECT_ROOT / "demo-23-custom-categories" / "python"
if str(_demo23_python) not in sys.path:
    sys.path.insert(0, str(_demo23_python))

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from rapid_scanner import RapidScanner  # noqa: E402

# ── Category definitions ──
_categories_dir = PROJECT_ROOT / "demo-23-custom-categories" / "categories"

CATEGORY_FILES = ["financial_fraud.json", "competitor_mention.json", "pii_leakage.json"]


def _load_categories() -> list[dict[str, Any]]:
    """Load all custom category JSON definitions."""
    cats: list[dict[str, Any]] = []
    for fname in CATEGORY_FILES:
        path = _categories_dir / fname
        if path.exists():
            with open(path) as f:
                cats.append(json.load(f))
    return cats


# ── Simulation patterns (used when Azure is not configured) ──
_SIM_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "financial_fraud": [
        re.compile(r"(?i)(pump.and.dump|ponzi|launder|shell.compan|tax.fraud|fake.invoice|scam|insider.trad)"),
        re.compile(r"(?i)(bank.credential|wire.the.money|crypto.*scheme|deceptive.*invest)"),
    ],
    "competitor_mention": [
        re.compile(r"(?i)(google\s*cloud|aws|azure|lambda|competitor|switch.*to|better.*than.*our)"),
        re.compile(r"(?i)(competing\s+product|recommend.*switch|their\s+pricing)"),
    ],
    "pii_leakage": [
        re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),  # SSN
        re.compile(r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b"),  # credit card
        re.compile(r"(?i)(ssn\s+is|medical\s+record\s*#|born\s+\d{2}/\d{2}/\d{4})"),
        re.compile(r"(?i)(\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b.*born)"),
    ],
}


def _simulate_scan(text: str, category_name: str) -> dict[str, Any]:
    """Pattern-match simulation when Azure Content Safety is unavailable."""
    patterns = _SIM_PATTERNS.get(category_name, [])
    for pat in patterns:
        m = pat.search(text)
        if m:
            return {
                "detected": True,
                "confidence": 0.85,
                "category": category_name,
                "simulated": True,
                "matched_snippet": m.group(0)[:60],
            }
    return {
        "detected": False,
        "confidence": 0.05,
        "category": category_name,
        "simulated": True,
    }


def _load_source_data() -> list[dict]:
    """Load source data for the Source Intelligence Drawer."""
    tabs: list[dict] = []

    # Custom category definitions
    categories = _load_categories()
    if categories:
        cat_items = []
        for cat in categories:
            examples_str = "\n".join(f"  + {e}" for e in cat.get("examples", [])[:3])
            cat_items.append({
                "name": cat.get("display_name", cat.get("category_name", "unknown")),
                "content": (
                    f"{cat.get('description', '')}\n\nExamples:\n{examples_str}"
                ),
            })
        tabs.append({
            "id": "categories",
            "label": f"CUSTOM CATEGORIES ({len(cat_items)})",
            "type": "list",
            "items": cat_items,
        })

    # Defense layers
    defense_layers = [
        {
            "name": "financial_fraud_detector",
            "content": (
                "Azure Custom Category scanner for financial fraud. Detects "
                "content promoting scams, money laundering, insider trading, "
                "identity theft for financial gain, or deceptive investment schemes."
            ),
        },
        {
            "name": "competitor_mention_detector",
            "content": (
                "Azure Custom Category scanner for competitor mentions. Detects "
                "content that names, recommends, or favorably compares competitor "
                "products or services."
            ),
        },
        {
            "name": "pii_leakage_detector",
            "content": (
                "Azure Custom Category scanner for PII leakage. Detects content "
                "containing SSNs, credit card numbers, medical records, addresses, "
                "and other personally identifiable information."
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
bp = Blueprint("demo_23", __name__, url_prefix="/demo-23")


def _sse_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _run_vulnerable(payload: str, eq: "queue.Queue[str]", otel_span: Any = None) -> None:
    """Vulnerable path — no custom category scanning at all."""
    from blueprints.otel_helpers import span_set, span_set_result

    try:
        t0 = time.time()
        # Just pass text through with zero scanning
        response = (
            f"Content accepted without scanning:\n\n{payload[:500]}"
        )
        latency = round((time.time() - t0) * 1000, 1)

        span_set("vuln.blocked", False, span=otel_span)
        span_set_result(
            span=otel_span,
            action="custom_categories_vulnerable",
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
    """Defended path — scan text against all custom categories."""
    from blueprints.otel_helpers import span_set, span_set_result

    try:
        t0 = time.time()
        layers: list[dict[str, Any]] = []
        blocked = False
        blocked_by = ""

        category_names = ["financial_fraud", "competitor_mention", "pii_leakage"]

        # Try Azure Content Safety first, fall back to simulation
        azure_endpoint = os.getenv("AZURE_CONTENT_SAFETY_ENDPOINT", "")
        azure_key = os.getenv("AZURE_CONTENT_SAFETY_KEY", "")

        for cat_name in category_names:
            layer_t0 = time.time()
            scan_result: dict[str, Any]

            if azure_endpoint and azure_key:
                try:
                    # Attempt real Azure Custom Categories (Rapid API)
                    from azure.ai.contentsafety import ContentSafetyClient
                    from azure.core.credentials import AzureKeyCredential

                    client = ContentSafetyClient(
                        azure_endpoint,
                        AzureKeyCredential(azure_key),
                    )
                    scanner = RapidScanner(safety_client=client)
                    scan_result = scanner.scan(payload, cat_name)
                except Exception:
                    scan_result = _simulate_scan(payload, cat_name)
            else:
                scan_result = _simulate_scan(payload, cat_name)

            layer_latency = round((time.time() - layer_t0) * 1000, 1)
            detected = scan_result.get("detected", False)

            layer_name = f"{cat_name}_detector"
            layers.append({
                "name": layer_name,
                "blocked": detected,
                "reason": (
                    f"Detected {cat_name} (confidence: {scan_result.get('confidence', 0):.0%})"
                    if detected
                    else f"No {cat_name} detected"
                ),
                "latency_ms": layer_latency,
            })

            if detected and not blocked:
                blocked = True
                blocked_by = layer_name

        total_latency = round((time.time() - t0) * 1000, 1)

        if blocked:
            response = (
                f"Content BLOCKED by custom category scanning.\n"
                f"Triggered category: {blocked_by}"
            )
        else:
            response = (
                f"Content passed all custom category scans.\n\n{payload[:300]}"
            )

        span_set("defended.blocked", blocked, span=otel_span)
        span_set_result(
            span=otel_span,
            action="custom_categories_defended",
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
    categories = _load_categories()
    return render_template(
        "demo_23/index.html",
        categories=categories,
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
