"""Blueprint for Demo 28 — APIM AI Gateway (Rate Limiting).

Side-by-side comparison: direct LLM calls with no rate limiting (vulnerable)
vs LLM calls through a simulated APIM AI Gateway with rate limiting,
semantic caching, and token governance (defended).

Routes:
  GET  /demo-28/            -> render the comparison UI
  POST /demo-28/api/compare -> run both sides, SSE stream results
  POST /demo-28/api/reset   -> reset APIM client state
"""

import json
import os
import queue
import sys
import threading
import time
from typing import Any, Generator

from flask import Blueprint, Response, jsonify, render_template, request, stream_with_context

from blueprints import PROJECT_ROOT

# -- Path setup ---------------------------------------------------------------
_demo28_python = PROJECT_ROOT / "demo-28-apim-ai-gateway" / "python"
if str(_demo28_python) not in sys.path:
    sys.path.insert(0, str(_demo28_python))

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from without_apim import DirectClient  # noqa: E402
from with_apim import APIMClient  # noqa: E402
from burst_test import run_burst  # noqa: E402

# -- Blueprint ----------------------------------------------------------------
bp = Blueprint("demo_28", __name__, url_prefix="/demo-28")

# Shared APIM client instance (persists across requests to show rate limiting)
_apim_client: APIMClient | None = None


def _get_apim_client() -> APIMClient:
    global _apim_client
    if _apim_client is None:
        _apim_client = APIMClient(client=None, token_budget=1000, tokens_per_call=150)
    return _apim_client


def _sse_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


# -- Source data for drawer ---------------------------------------------------

def _load_source_data() -> list[dict]:
    tabs: list[dict] = []

    # Burst test prompts
    burst_prompts = [
        {"name": "Prompt 1", "content": "What is the capital of France?"},
        {"name": "Prompt 2", "content": "Explain quantum computing briefly."},
        {"name": "Prompt 3 (repeat)", "content": "What is the capital of France?"},
        {"name": "Prompt 4", "content": "Summarize the history of AI."},
        {"name": "Prompt 5 (repeat)", "content": "Explain quantum computing briefly."},
    ]
    tabs.append({
        "id": "burst_prompts",
        "label": f"BURST PROMPTS ({len(burst_prompts)})",
        "type": "list",
        "items": burst_prompts,
    })

    # Defense layers
    defense_layers = [
        {
            "name": "rate_limiter",
            "content": (
                "Token-based rate limiter (llm-token-limit policy). Tracks estimated "
                "token consumption per request. When the budget is exhausted, "
                "subsequent requests receive HTTP 429 (throttled). Prevents "
                "denial-of-wallet attacks and runaway batch jobs."
            ),
        },
        {
            "name": "semantic_cache",
            "content": (
                "Semantic cache (llm-semantic-cache-lookup/store). Caches LLM responses "
                "keyed by normalized prompt text. Repeated identical prompts return "
                "cached responses without calling the backend, reducing latency and cost."
            ),
        },
        {
            "name": "token_governance",
            "content": (
                "Token governance and tracking. Monitors total token consumption, "
                "budget utilization percentage, and cache hit rates. Provides "
                "metrics for dashboards and cost management."
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


# -- Vulnerable side: direct LLM calls with no governance ---------------------

def _run_vulnerable(payload: str, eq: "queue.Queue[str]", otel_span: Any = None) -> None:
    from blueprints.otel_helpers import span_set, span_set_result

    try:
        # Simulate burst of direct LLM calls with no rate limiting
        n_requests = 10
        prompts = [payload]

        # Simulate: all requests go through, no throttling, no caching
        accepted = n_requests
        throttled = 0
        cached = 0
        total_tokens = n_requests * 150  # estimated tokens per call

        time.sleep(0.1)  # Simulate network latency

        response_text = (
            f"DIRECT LLM ACCESS (NO GATEWAY)\n"
            f"{'=' * 40}\n"
            f"Burst test: {n_requests} rapid requests\n"
            f"  Accepted: {accepted} (100%)\n"
            f"  Throttled: {throttled} (0%)\n"
            f"  Cached: {cached} (0%)\n"
            f"  Estimated tokens consumed: {total_tokens}\n"
            f"  Cost controls: NONE\n\n"
            f"All {n_requests} requests processed without limits. "
            f"No rate limiting, no caching, no token tracking. "
            f"A burst of requests can exhaust API quota and rack up costs."
        )

        span_set("vuln.requests_accepted", accepted, span=otel_span)
        span_set("vuln.tokens_consumed", total_tokens, span=otel_span)
        span_set("vuln.blocked", False, span=otel_span)
        span_set_result(
            span=otel_span,
            action="apim_vulnerable",
            blocked=False,
            response_preview=response_text[:300],
        )
        eq.put(_sse_event("vuln_result", {
            "response": response_text[:1000],
            "blocked": False,
        }))
    except Exception as exc:
        eq.put(_sse_event("vuln_result", {
            "response": f"Error: {exc}",
            "blocked": False,
        }))


# -- Defended side: APIM gateway with rate limiting + caching -----------------

def _run_defended(payload: str, eq: "queue.Queue[str]", otel_span: Any = None) -> None:
    from blueprints.otel_helpers import span_set, span_set_result, span_event

    try:
        apim = _get_apim_client()
        n_requests = 10
        prompts = [
            payload,
            "What is the capital of France?",
            payload,  # repeat to trigger cache
            "Explain quantum computing briefly.",
            payload,  # repeat again
        ]

        layers: list[dict[str, Any]] = []
        accepted = 0
        throttled = 0
        cached = 0

        for i in range(n_requests):
            prompt = prompts[i % len(prompts)]
            t0 = time.time()

            # Simulate the APIM call
            result = _simulate_apim_call(apim, prompt, i)
            elapsed_ms = (time.time() - t0) * 1000 + 5.0

            if result["throttled"]:
                throttled += 1
            elif result["cached"]:
                cached += 1
            else:
                accepted += 1

        # Build layer results
        t0 = time.time()

        # Rate limiter layer
        budget_exceeded = apim.is_budget_exceeded
        rate_limit_elapsed = (time.time() - t0) * 1000 + 8.0
        layers.append({
            "name": "rate_limiter",
            "blocked": budget_exceeded,
            "reason": (
                f"Token budget {'EXHAUSTED' if budget_exceeded else 'OK'} "
                f"({apim.tokens_consumed}/{apim.token_budget} tokens consumed, "
                f"{throttled} requests throttled)"
            ),
            "latency_ms": round(rate_limit_elapsed, 1),
        })

        # Semantic cache layer
        cache_active = cached > 0
        layers.append({
            "name": "semantic_cache",
            "blocked": False,
            "reason": (
                f"{cached} cache hits out of {n_requests} requests "
                f"({apim._cache.__len__()} entries in cache)"
            ),
            "latency_ms": round(3.2, 1),
        })

        # Token governance layer
        metrics = apim.get_metrics()
        layers.append({
            "name": "token_governance",
            "blocked": False,
            "reason": (
                f"Budget utilization: {metrics['budget_utilization']:.1%}, "
                f"Tokens: {metrics['tokens_consumed']}/{metrics['token_budget']}, "
                f"Total calls: {metrics['call_count']}"
            ),
            "latency_ms": round(1.5, 1),
        })

        overall_blocked = throttled > 0

        response_text = (
            f"APIM AI GATEWAY RESULTS\n"
            f"{'=' * 40}\n"
            f"Burst test: {n_requests} rapid requests\n"
            f"  Accepted: {accepted}\n"
            f"  Throttled: {throttled} (rate limited)\n"
            f"  Cached: {cached} (served from cache)\n"
            f"  Tokens consumed: {apim.tokens_consumed}/{apim.token_budget}\n"
            f"  Budget utilization: {metrics['budget_utilization']:.1%}\n"
            f"  Cache entries: {len(apim._cache)}\n\n"
        )
        if throttled > 0:
            response_text += (
                f"Rate limiting triggered! {throttled} requests throttled after "
                f"token budget was exceeded. This prevents denial-of-wallet attacks."
            )
        else:
            response_text += (
                "All requests within budget. Semantic caching reduced backend calls."
            )

        span_set("apim.accepted", accepted, span=otel_span)
        span_set("apim.throttled", throttled, span=otel_span)
        span_set("apim.cached", cached, span=otel_span)
        span_set("apim.tokens_consumed", apim.tokens_consumed, span=otel_span)
        span_set_result(
            span=otel_span,
            action="apim_gateway",
            blocked=overall_blocked,
            response_preview=response_text[:300],
        )

        eq.put(_sse_event("defended_result", {
            "response": response_text[:1000],
            "blocked": overall_blocked,
            "blocked_by": "rate_limiter" if overall_blocked else "",
            "layers": layers,
        }))
    except Exception as exc:
        eq.put(_sse_event("defended_result", {
            "response": f"Error: {exc}",
            "blocked": False,
            "blocked_by": "",
            "layers": [],
        }))


def _simulate_apim_call(apim: APIMClient, prompt: str, call_index: int) -> dict[str, Any]:
    """Simulate an APIM gateway call without requiring a real LLM backend."""
    apim.call_count += 1

    # Rate limit check
    if apim.is_budget_exceeded:
        return {
            "response": "[429] Token budget exceeded. Request throttled.",
            "cached": False,
            "throttled": True,
            "tokens_remaining": 0,
            "call_number": apim.call_count,
        }

    # Semantic cache lookup
    cache_key = prompt.strip().lower()
    if cache_key in apim._cache:
        return {
            "response": apim._cache[cache_key],
            "cached": True,
            "throttled": False,
            "tokens_remaining": apim.remaining_tokens,
            "call_number": apim.call_count,
        }

    # Consume tokens
    apim.tokens_consumed += apim.tokens_per_call

    # Simulated response
    simulated_response = f"[Simulated LLM response for: {prompt[:60]}...]"
    apim._cache[cache_key] = simulated_response

    return {
        "response": simulated_response,
        "cached": False,
        "throttled": False,
        "tokens_remaining": apim.remaining_tokens,
        "call_number": apim.call_count,
    }


# -- Routes -------------------------------------------------------------------

@bp.route("/")
def index() -> str:
    return render_template(
        "demo_28/index.html",
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
    global _apim_client
    if _apim_client is not None:
        _apim_client.reset()
    _apim_client = None
    return jsonify({"status": "ok"}), 200
