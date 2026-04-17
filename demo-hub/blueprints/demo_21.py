"""Blueprint for Demo 21 — Groundedness Detection (Hallucination Defense).

Side-by-side comparison: vulnerable RAG chatbot (no groundedness verification) vs
defended RAG chatbot (Azure Groundedness Detection verifying answers against source).

Routes:
  GET  /demo-21/            → render the comparison UI
  POST /demo-21/api/compare → run both chatbots, SSE stream results
  POST /demo-21/api/reset   → no-op (stateless)
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
_demo21_python = PROJECT_ROOT / "demo-21-groundedness" / "python"
if str(_demo21_python) not in sys.path:
    sys.path.insert(0, str(_demo21_python))

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.python.ollama_client import OllamaClient  # noqa: E402

# ── Payloads and source documents ──
_payloads_path = PROJECT_ROOT / "demo-21-groundedness" / "attacks" / "hallucination_prompts.json"
_articles_path = PROJECT_ROOT / "demo-21-groundedness" / "documents" / "source_articles.json"

VULN_SYSTEM_PROMPT = (
    "You are a helpful research assistant. Answer questions based on the "
    "provided source material. If the source material doesn't contain enough "
    "information, supplement with your general knowledge."
)

DEFENDED_SYSTEM_PROMPT = (
    "You are a helpful research assistant. Answer questions based ONLY on the "
    "provided source material. If the information is not in the source, say "
    "'The source material does not contain this information.' Do not speculate."
)

# ── Keywords that hint the response adds info not in the source ──
_HALLUCINATION_INDICATORS: list[str] = [
    r"first\s+person\s+to\s+receive",
    r"directly\s+caus",
    r"evidence\s+of\s+alien",
    r"professor\s+at",
    r"scientist.*designed",
    r"available\s+to\s+the\s+general\s+public",
    r"unemployment\s+rate\s+was\s+\d",
    r"hubble\s+miss",
    r"(?:he|she)\s+said",
    r"de\s+lesseps\s+said",
]


def _load_payloads() -> list[dict[str, str]]:
    if not _payloads_path.exists():
        return []
    with open(_payloads_path) as f:
        return json.load(f)  # type: ignore[no-any-return]


def _load_articles() -> list[dict[str, str]]:
    if not _articles_path.exists():
        return []
    with open(_articles_path) as f:
        return json.load(f)  # type: ignore[no-any-return]


_ARTICLES: list[dict[str, str]] = _load_articles()
_ARTICLE_MAP: dict[str, dict[str, str]] = {a["id"]: a for a in _ARTICLES}


def _get_source_text(source_id: str) -> str:
    """Get source article text by id; fall back to all articles if not found."""
    article = _ARTICLE_MAP.get(source_id)
    if article:
        return f"{article['title']}\n{article['content']}"
    # Return all articles concatenated as fallback
    return "\n\n".join(
        f"{a['title']}\n{a['content']}" for a in _ARTICLES
    )


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
                {"name": p["name"], "content": p["prompt"]}
                for p in payloads
            ],
        })

    if _ARTICLES:
        tabs.append({
            "id": "documents",
            "label": f"SOURCE DOCUMENTS ({len(_ARTICLES)})",
            "type": "list",
            "items": [
                {"name": a["title"], "content": a["content"]}
                for a in _ARTICLES
            ],
        })

    defense_layers = [
        {
            "name": "groundedness_check",
            "content": (
                "Azure Groundedness Detection post-scan. After the LLM generates "
                "a response, verifies that the claims in the response are grounded "
                "in the provided source material. Detects hallucinated facts, "
                "fabricated statistics, and unsupported claims."
            ),
        },
        {
            "name": "reasoning_check",
            "content": (
                "Detailed reasoning analysis for ungrounded segments. When the "
                "groundedness check finds issues, this layer identifies the specific "
                "segments that are not supported by the source material and explains "
                "why they are considered ungrounded."
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


def _simulate_groundedness(response: str, source_text: str) -> dict[str, Any]:
    """Simulate Azure Groundedness Detection when credentials are absent.

    Uses heuristic checks: if the response contains details not present in
    the source text, flag as ungrounded.
    """
    response_lower = response.lower()
    source_lower = source_text.lower()

    ungrounded_reasons: list[str] = []

    # Check for hallucination indicator patterns
    for pattern in _HALLUCINATION_INDICATORS:
        if re.search(pattern, response_lower):
            ungrounded_reasons.append(f"Pattern match: '{pattern}' found in response but not verifiable in source")

    # Check for specific names/numbers in response that aren't in source
    # Simple heuristic: look for quoted names or specific numbers
    response_sentences = response.split(".")
    for sentence in response_sentences:
        sentence_stripped = sentence.strip()
        if len(sentence_stripped) < 10:
            continue
        # If sentence has specific claims with names/dates not in source
        name_matches = re.findall(r"[A-Z][a-z]+\s+[A-Z][a-z]+", sentence_stripped)
        for name in name_matches:
            if name.lower() not in source_lower and len(name) > 5:
                ungrounded_reasons.append(f"Name '{name}' not found in source material")
                break

    if ungrounded_reasons:
        pct = min(len(ungrounded_reasons) * 20, 80)
        return {
            "grounded": False,
            "ungroundedPercentage": float(pct),
            "reasoning": ungrounded_reasons[:5],
        }

    return {
        "grounded": True,
        "ungroundedPercentage": 0.0,
        "reasoning": [],
    }


def _azure_groundedness_check(
    response: str,
    source_text: str,
    reasoning: bool = True,
) -> tuple[dict[str, Any], bool]:
    """Try Azure Groundedness Detection; fall back to simulation.

    Returns (groundedness_result, used_azure).
    """
    endpoint = os.getenv("AZURE_CONTENT_SAFETY_ENDPOINT", "")
    key = os.getenv("AZURE_CONTENT_SAFETY_KEY", "")

    if endpoint and key:
        try:
            from azure.ai.contentsafety import ContentSafetyClient
            from azure.core.credentials import AzureKeyCredential

            client = ContentSafetyClient(endpoint, AzureKeyCredential(key))
            # Use the groundedness detection API
            body = {
                "domain": "Generic",
                "task": "QnA",
                "text": response,
                "groundingSources": [source_text],
                "reasoning": reasoning,
            }
            resp = client.detect_groundedness(body)
            grounded = not getattr(resp, "ungrounded_detected", True)
            pct = getattr(resp, "ungrounded_percentage", 0.0) or 0.0
            reason_list: list[str] = []
            for seg in getattr(resp, "ungrounded_segments", []) or []:
                reason_list.append(getattr(seg, "text", str(seg)))
            return {
                "grounded": grounded,
                "ungroundedPercentage": pct,
                "reasoning": reason_list,
            }, True
        except Exception:
            pass

    return _simulate_groundedness(response, source_text), False


# ── Blueprint ──
bp = Blueprint("demo_21", __name__, url_prefix="/demo-21")


def _sse_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _run_vulnerable(
    payload: str,
    source_text: str,
    eq: "queue.Queue[str]",
    otel_span: Any = None,
) -> None:
    from blueprints.otel_helpers import span_set, span_set_result

    try:
        client = OllamaClient()
        messages = [
            {"role": "system", "content": VULN_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Source Material:\n{source_text}\n\n"
                    f"Question: {payload}\n\n"
                    f"Answer the question using the source material."
                ),
            },
        ]
        response = str(client.chat(messages))

        span_set("vuln.blocked", False, span=otel_span)
        span_set_result(
            span=otel_span,
            action="vulnerable_groundedness",
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


def _run_defended(
    payload: str,
    source_text: str,
    eq: "queue.Queue[str]",
    otel_span: Any = None,
) -> None:
    from blueprints.otel_helpers import span_set_result

    layers: list[dict[str, Any]] = []

    try:
        # ── Generate response with stricter system prompt ──
        client = OllamaClient()
        messages = [
            {"role": "system", "content": DEFENDED_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Source Material:\n{source_text}\n\n"
                    f"Question: {payload}\n\n"
                    f"Answer the question using ONLY the source material."
                ),
            },
        ]
        response = str(client.chat(messages))

        # ── Layer 1: Groundedness check ──
        t0 = time.time()
        gcheck, _used_azure = _azure_groundedness_check(response, source_text, reasoning=True)
        ground_ms = round((time.time() - t0) * 1000)

        grounded = gcheck.get("grounded", True)
        ungrounded_pct = gcheck.get("ungroundedPercentage", 0.0)

        layers.append({
            "name": "groundedness_check",
            "blocked": not grounded,
            "reason": (
                f"{ungrounded_pct:.0f}% ungrounded content detected"
                if not grounded
                else "Response is grounded in source material"
            ),
            "latency_ms": ground_ms,
        })

        # ── Layer 2: Reasoning analysis ──
        reasoning_items = gcheck.get("reasoning", [])
        layers.append({
            "name": "reasoning_check",
            "blocked": len(reasoning_items) > 0,
            "reason": (
                f"{len(reasoning_items)} ungrounded segment(s) identified"
                if reasoning_items
                else "No ungrounded segments"
            ),
            "latency_ms": 0,  # included in the groundedness check
        })

        if not grounded:
            warning_text = (
                f"[GROUNDEDNESS WARNING] The response contains "
                f"{ungrounded_pct:.0f}% ungrounded content.\n\n"
                f"Original response: {response}"
            )
            if reasoning_items:
                warning_text += "\n\nUngrounded segments:\n" + "\n".join(
                    f"  - {r}" for r in reasoning_items
                )
            span_set_result(
                span=otel_span,
                action="groundedness",
                blocked=True,
                blocked_by="groundedness_check",
                response_preview=warning_text[:300],
            )
            eq.put(_sse_event("defended_result", {
                "response": warning_text[:2000],
                "blocked": True,
                "blocked_by": "groundedness_check",
                "layers": layers,
            }))
            return

        # ── All clear ──
        span_set_result(
            span=otel_span,
            action="groundedness",
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
    return render_template(
        "demo_21/index.html",
        payloads=payloads,
        articles=_ARTICLES,
        source_tabs=_load_source_data(),
    )


@bp.route("/api/compare", methods=["POST"])
def api_compare() -> Response:
    data = request.get_json(silent=True) or {}
    payload = data.get("payload", "").strip()
    source_id = data.get("source_id", "").strip()
    if not payload:
        return jsonify({"error": "No payload provided"}), 400  # type: ignore[return-value]

    source_text = _get_source_text(source_id)

    from blueprints.otel_helpers import get_request_span

    event_queue: queue.Queue[str] = queue.Queue()
    otel_span = get_request_span()

    t1 = threading.Thread(
        target=_run_vulnerable,
        args=(payload, source_text, event_queue, otel_span),
        daemon=True,
    )
    t2 = threading.Thread(
        target=_run_defended,
        args=(payload, source_text, event_queue, otel_span),
        daemon=True,
    )
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
