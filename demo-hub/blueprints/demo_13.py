"""Blueprint for Demo 13 — Hallucination Exploitation.

Auto-runner for hallucination attack prompts with real-time fact verification.

Routes:
  GET  /demo-13/            -> render the attack UI
  POST /demo-13/api/attack  -> run a single hallucination attack, SSE stream
  POST /demo-13/api/run-all -> run all attacks sequentially, SSE stream
  POST /demo-13/api/reset   -> reset state (no-op placeholder for consistency)
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
_demo13_python = PROJECT_ROOT / "demo-13-hallucination-exploitation" / "python"
if str(_demo13_python) not in sys.path:
    sys.path.insert(0, str(_demo13_python))

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from hallucination_attacks import (  # noqa: E402
    HALLUCINATION_PROMPTS,
    extract_api_references,
    extract_citations,
    extract_urls,
    load_prompts_from_json,
)
from fact_checker import (  # noqa: E402
    verify_api,
    verify_citation,
    verify_fact,
    verify_url,
    GROUND_TRUTH_FACTS,
)
from shared.python.ollama_client import OllamaClient  # noqa: E402

# ── Blueprint ──
bp = Blueprint("demo_13", __name__, url_prefix="/demo-13")

_prompts_path = PROJECT_ROOT / "demo-13-hallucination-exploitation" / "attacks" / "prompts.json"


def _sse_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _verify_claims(
    response_text: str,
    verification_type: str,
    prompt_config: dict[str, Any],
) -> list[dict[str, Any]]:
    """Extract and verify claims from a response based on verification type."""
    claims: list[dict[str, Any]] = []

    if verification_type == "citation":
        for cite in extract_citations(response_text):
            result = verify_citation(cite)
            claims.append({
                "type": "citation",
                "text": cite[:200],
                "valid": result["valid"],
                "reason": result["reason"],
            })

    elif verification_type == "url":
        for url in extract_urls(response_text):
            result = verify_url(url)
            claims.append({
                "type": "url",
                "text": url,
                "valid": result["valid"],
                "reason": result["reason"],
            })

    elif verification_type == "api":
        for api_ref in extract_api_references(response_text):
            result = verify_api(api_ref)
            claims.append({
                "type": "api",
                "text": api_ref,
                "valid": result["valid"],
                "reason": result["reason"],
            })

    elif verification_type == "fact":
        gt_key = prompt_config.get("ground_truth_key", "")
        if gt_key and gt_key in GROUND_TRUTH_FACTS:
            gt = GROUND_TRUTH_FACTS[gt_key]
            result = verify_fact(prompt_config["prompt"], gt)
            claims.append({
                "type": "fact",
                "text": gt["claim"],
                "valid": result["valid"],
                "reason": result["reason"],
            })

    # Fallback for empty extraction
    if not claims and verification_type in ("citation", "url", "api"):
        claims.append({
            "type": verification_type,
            "text": "(No structured claims could be extracted from response)",
            "valid": None,
            "reason": "Could not extract individual claims for verification",
        })

    return claims


def _run_single_attack(attack_id: str, eq: "queue.Queue[str]", otel_span: Any = None) -> None:
    """Run a single hallucination attack and stream results."""
    from blueprints.otel_helpers import span_set, span_set_result, span_event

    try:
        prompts = load_prompts_from_json()
        prompt_config = next((p for p in prompts if p["id"] == attack_id), None)
        if not prompt_config:
            eq.put(_sse_event("error", {"message": f"Unknown attack ID: {attack_id}"}))
            eq.put(_sse_event("done", {}))
            return

        span_set("attack.id", attack_id, span=otel_span)
        span_set("attack.name", prompt_config["name"], span=otel_span)
        span_set("attack.verification_type", prompt_config["verification_type"], span=otel_span)

        client = OllamaClient()

        eq.put(_sse_event("attack_start", {
            "id": prompt_config["id"],
            "name": prompt_config["name"],
            "category": prompt_config.get("category", ""),
            "prompt": prompt_config["prompt"],
            "description": prompt_config.get("description", ""),
            "verification_type": prompt_config["verification_type"],
        }))

        messages = [
            {"role": "system", "content": "You are a helpful research assistant."},
            {"role": "user", "content": prompt_config["prompt"]},
        ]

        full_response = ""
        try:
            for token in client.chat_stream(messages):
                full_response += token
                eq.put(_sse_event("token", {"token": token, "id": prompt_config["id"]}))
        except Exception as exc:
            eq.put(_sse_event("error", {"message": f"LLM error: {exc}"}))
            eq.put(_sse_event("done", {}))
            return

        # Verify claims
        claims = _verify_claims(full_response, prompt_config["verification_type"], prompt_config)

        for claim in claims:
            eq.put(_sse_event("verification_result", {
                "id": prompt_config["id"],
                **claim,
            }))

        fabricated = sum(1 for c in claims if c["valid"] is False)
        real = sum(1 for c in claims if c["valid"] is True)
        unverified = sum(1 for c in claims if c["valid"] is None)

        span_set("result.fabricated_count", fabricated, span=otel_span)
        span_set("result.real_count", real, span=otel_span)
        span_set("result.unverified_count", unverified, span=otel_span)
        span_set_result(
            span=otel_span,
            action="hallucination_attack",
            technique=prompt_config["name"],
            success=fabricated > 0,
            response_preview=full_response,
        )

        eq.put(_sse_event("attack_result", {
            "id": prompt_config["id"],
            "name": prompt_config["name"],
            "summary": {
                "total": len(claims),
                "fabricated": fabricated,
                "real": real,
                "unverified": unverified,
            },
        }))

    except Exception as exc:
        eq.put(_sse_event("error", {"message": f"Attack error: {exc}"}))

    eq.put(_sse_event("done", {}))


def _run_all_attacks(eq: "queue.Queue[str]", otel_span: Any = None) -> None:
    """Run all hallucination attacks sequentially."""
    from blueprints.otel_helpers import span_set, span_set_result, span_event

    try:
        prompts = load_prompts_from_json()
        client = OllamaClient()

        for i, prompt_config in enumerate(prompts):
            eq.put(_sse_event("attack_start", {
                "index": i,
                "id": prompt_config["id"],
                "name": prompt_config["name"],
                "category": prompt_config.get("category", ""),
                "prompt": prompt_config["prompt"],
                "description": prompt_config.get("description", ""),
                "verification_type": prompt_config["verification_type"],
            }))

            messages = [
                {"role": "system", "content": "You are a helpful research assistant."},
                {"role": "user", "content": prompt_config["prompt"]},
            ]

            full_response = ""
            try:
                for token in client.chat_stream(messages):
                    full_response += token
                    eq.put(_sse_event("token", {"token": token, "index": i}))
            except Exception as exc:
                eq.put(_sse_event("error", {"message": f"LLM error on attack {i}: {exc}"}))
                continue

            # Verify claims
            claims = _verify_claims(full_response, prompt_config["verification_type"], prompt_config)

            for claim in claims:
                eq.put(_sse_event("verification_result", {
                    "index": i,
                    "id": prompt_config["id"],
                    **claim,
                }))

            fabricated = sum(1 for c in claims if c["valid"] is False)
            real = sum(1 for c in claims if c["valid"] is True)
            unverified = sum(1 for c in claims if c["valid"] is None)

            span_event("hallucination_attack", {
                "attack_id": prompt_config["id"],
                "attack_name": prompt_config["name"],
                "verification_type": prompt_config["verification_type"],
                "fabricated_count": fabricated,
                "real_count": real,
                "unverified_count": unverified,
            }, span=otel_span)

            eq.put(_sse_event("attack_result", {
                "index": i,
                "id": prompt_config["id"],
                "name": prompt_config["name"],
                "summary": {
                    "total": len(claims),
                    "fabricated": fabricated,
                    "real": real,
                    "unverified": unverified,
                },
            }))

    except Exception as exc:
        eq.put(_sse_event("error", {"message": f"Run error: {exc}"}))

    span_set_result(span=otel_span, action="run_all_hallucination_attacks")

    eq.put(_sse_event("done", {}))


def _load_source_data() -> list[dict]:
    """Load source data for the source drawer."""
    tabs: list[dict] = []

    # Prompts config
    prompts = load_prompts_from_json()
    if prompts:
        tabs.append({
            "id": "prompts",
            "label": f"ATTACK PROMPTS ({len(prompts)})",
            "type": "list",
            "items": [{"name": p["name"], "content": p["prompt"]} for p in prompts],
        })

    # Fact checker source
    fact_checker_path = _demo13_python / "fact_checker.py"
    if fact_checker_path.exists():
        tabs.append({
            "id": "fact_checker",
            "label": "FACT CHECKER",
            "type": "code",
            "language": "python",
            "content": fact_checker_path.read_text(),
        })

    # Attack runner source
    attacks_path = _demo13_python / "hallucination_attacks.py"
    if attacks_path.exists():
        tabs.append({
            "id": "hallucination_attacks",
            "label": "ATTACK RUNNER",
            "type": "code",
            "language": "python",
            "content": attacks_path.read_text(),
        })

    return tabs


@bp.route("/")
def index() -> str:
    prompts = load_prompts_from_json()
    return render_template("demo_13/index.html",
        prompts=prompts,
        source_tabs=_load_source_data(),
    )


@bp.route("/api/attack", methods=["POST"])
def api_attack() -> Response:
    from blueprints.otel_helpers import get_request_span

    data = request.get_json(silent=True) or {}
    attack_id = data.get("attack_id", "").strip()
    if not attack_id:
        return jsonify({"error": "No attack_id provided"}), 400  # type: ignore[return-value]

    event_queue: queue.Queue[str] = queue.Queue()
    otel_span = get_request_span()
    thread = threading.Thread(target=_run_single_attack, args=(attack_id, event_queue, otel_span), daemon=True)
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


@bp.route("/api/run-all", methods=["POST"])
def api_run_all() -> Response:
    from blueprints.otel_helpers import get_request_span

    event_queue: queue.Queue[str] = queue.Queue()
    otel_span = get_request_span()
    thread = threading.Thread(target=_run_all_attacks, args=(event_queue, otel_span), daemon=True)
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


@bp.route("/api/reset", methods=["POST"])
def api_reset() -> tuple[Response, int]:
    return jsonify({"status": "ok"}), 200
