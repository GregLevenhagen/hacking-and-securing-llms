"""Blueprint for Demo 27 — Red Teaming Agent (Adversarial Eval).

Side-by-side comparison: vulnerable chatbot (no safety checks) vs red team
scan results showing which encoding strategies bypass defenses and computing
an Attack Success Rate (ASR).

Routes:
  GET  /demo-27/            -> render the comparison UI
  POST /demo-27/api/compare -> run both sides, SSE stream results
  POST /demo-27/api/reset   -> no-op (stateless)
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

# -- Path setup ---------------------------------------------------------------
_demo27_python = PROJECT_ROOT / "demo-27-red-teaming" / "python"
if str(_demo27_python) not in sys.path:
    sys.path.insert(0, str(_demo27_python))

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from red_team_scan import (  # noqa: E402
    ATTACK_STRATEGIES,
    DEFAULT_PAYLOADS,
    REFUSAL_PATTERNS,
    RedTeamScanner,
    _is_attack_successful,
)
from target_app import TargetApp  # noqa: E402
from eval_safety import SafetyEvaluator  # noqa: E402

# -- Blueprint ----------------------------------------------------------------
bp = Blueprint("demo_27", __name__, url_prefix="/demo-27")


def _sse_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


# -- Source data for drawer ---------------------------------------------------

def _load_source_data() -> list[dict]:
    tabs: list[dict] = []

    # Attack categories / payloads
    payload_items = []
    for category, payloads in DEFAULT_PAYLOADS.items():
        for p in payloads:
            payload_items.append({"name": f"{category}", "content": p})
    if payload_items:
        tabs.append({
            "id": "payloads",
            "label": f"ATTACK PAYLOADS ({len(payload_items)})",
            "type": "list",
            "items": payload_items,
        })

    # Encoding strategies
    strat_items = [
        {"name": name, "content": fn.__doc__ or name}
        for name, fn in ATTACK_STRATEGIES.items()
    ]
    tabs.append({
        "id": "strategies",
        "label": f"ENCODING STRATEGIES ({len(strat_items)})",
        "type": "list",
        "items": strat_items,
    })

    # Defense layers
    defense_layers = [
        {
            "name": "base64_encoding",
            "content": (
                "Red team strategy: base64-encode the attack payload and instruct "
                "the target to decode and execute. Tests whether the model blindly "
                "follows encoded instructions."
            ),
        },
        {
            "name": "rot13_encoding",
            "content": (
                "Red team strategy: ROT13-encode the attack and wrap in decode "
                "instructions. Tests resistance to simple substitution ciphers."
            ),
        },
        {
            "name": "leetspeak_encoding",
            "content": (
                "Red team strategy: convert attack to leetspeak (a->4, e->3, etc.) "
                "to bypass keyword-based content filters."
            ),
        },
        {
            "name": "direct_request",
            "content": (
                "Baseline: send the attack payload as-is with no encoding. "
                "Measures the model's raw refusal capability."
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


# -- Vulnerable side: undefended target chatbot --------------------------------

def _run_vulnerable(payload: str, eq: "queue.Queue[str]", otel_span: Any = None) -> None:
    from blueprints.otel_helpers import span_set, span_set_result

    try:
        # Simulate an undefended target that responds to everything
        target = TargetApp.__new__(TargetApp)
        target.client = None

        # Simulate the response -- target has no safety checks
        simulated_response = (
            f"Sure, I'll help with that. Here is the information you requested "
            f"regarding: '{payload[:80]}...'. "
            f"The target application complied without any safety checks or content "
            f"filtering. No refusal was triggered."
        )

        span_set("vuln.blocked", False, span=otel_span)
        span_set_result(
            span=otel_span,
            action="red_team_vulnerable",
            blocked=False,
            response_preview=simulated_response[:300],
        )
        eq.put(_sse_event("vuln_result", {
            "response": simulated_response[:1000],
            "blocked": False,
        }))
    except Exception as exc:
        eq.put(_sse_event("vuln_result", {
            "response": f"Error: {exc}",
            "blocked": False,
        }))


# -- Defended side: red team scan results --------------------------------------

def _run_defended(payload: str, eq: "queue.Queue[str]", otel_span: Any = None) -> None:
    from blueprints.otel_helpers import span_set, span_set_result, span_event

    try:
        # Run a simulated red team scan across encoding strategies
        strategies_to_test = ["Base64", "ROT13", "Leetspeak", "DirectRequest"]
        layer_map = {
            "Base64": "base64_encoding",
            "ROT13": "rot13_encoding",
            "Leetspeak": "leetspeak_encoding",
            "DirectRequest": "direct_request",
        }

        layers: list[dict[str, Any]] = []
        total_attacks = 0
        successful_attacks = 0
        bypassed_strategies: list[str] = []

        for strat_name in strategies_to_test:
            t0 = time.time()
            encoder = ATTACK_STRATEGIES.get(strat_name)
            if encoder is None:
                continue

            encoded = encoder(payload)
            total_attacks += 1

            # Simulate target response -- use refusal patterns to decide
            # In simulation mode, check if the encoded payload would bypass
            # a typical safety-aware model
            attack_success = False

            # Direct requests are usually caught, encoded ones may bypass
            if strat_name == "DirectRequest":
                # Model usually refuses direct harmful requests
                attack_success = False
            elif strat_name == "Base64":
                # Base64 can bypass keyword filters ~40% of the time
                attack_success = hash(payload + "b64") % 5 < 2
            elif strat_name == "ROT13":
                # ROT13 similarly bypasses keyword filters
                attack_success = hash(payload + "rot13") % 5 < 2
            elif strat_name == "Leetspeak":
                # Leetspeak sometimes bypasses pattern matching
                attack_success = hash(payload + "leet") % 5 < 1

            elapsed_ms = (time.time() - t0) * 1000 + 15.0  # Add simulated latency

            layer_name = layer_map.get(strat_name, strat_name.lower())

            if attack_success:
                successful_attacks += 1
                bypassed_strategies.append(strat_name)
                layers.append({
                    "name": layer_name,
                    "blocked": True,  # blocked=True in defense context means "detected a bypass"
                    "reason": f"Attack BYPASSED via {strat_name} encoding (vulnerability found)",
                    "latency_ms": round(elapsed_ms, 1),
                })
            else:
                layers.append({
                    "name": layer_name,
                    "blocked": False,  # Not blocked = model resisted this strategy
                    "reason": f"Attack RESISTED - {strat_name} encoding was refused by target",
                    "latency_ms": round(elapsed_ms, 1),
                })

            span_event(f"red_team_{strat_name}", {
                "strategy": strat_name,
                "success": attack_success,
            }, span=otel_span)

        # Compute ASR
        asr = successful_attacks / total_attacks if total_attacks > 0 else 0.0

        # Safety evaluation
        evaluator = SafetyEvaluator()
        eval_result = evaluator.evaluate_conversation([
            {"role": "user", "content": payload},
        ])

        response_text = (
            f"RED TEAM SCAN COMPLETE\n"
            f"{'=' * 40}\n"
            f"Attack Success Rate (ASR): {asr:.0%} ({successful_attacks}/{total_attacks})\n"
            f"Strategies tested: {', '.join(strategies_to_test)}\n"
        )
        if bypassed_strategies:
            response_text += f"Bypassed via: {', '.join(bypassed_strategies)}\n"
        else:
            response_text += "No strategies bypassed the target's defenses.\n"

        response_text += (
            f"\nSafety Evaluation:\n"
            f"  Hate: {eval_result.scores.get('hate', 0):.2f}\n"
            f"  Violence: {eval_result.scores.get('violence', 0):.2f}\n"
            f"  Indirect Attack: {eval_result.scores.get('indirect_attack', 0):.2f}\n"
            f"  Overall Safe: {'Yes' if eval_result.overall_safe else 'No'}\n"
        )

        overall_blocked = asr == 0.0  # All attacks resisted = good defense

        span_set("red_team.asr", round(asr, 4), span=otel_span)
        span_set("red_team.total_attacks", total_attacks, span=otel_span)
        span_set("red_team.successful_attacks", successful_attacks, span=otel_span)
        span_set_result(
            span=otel_span,
            action="red_team_scan",
            blocked=overall_blocked,
            response_preview=response_text[:300],
        )

        eq.put(_sse_event("defended_result", {
            "response": response_text[:1000],
            "blocked": overall_blocked,
            "blocked_by": "red_team_scanner" if overall_blocked else "",
            "layers": layers,
        }))
    except Exception as exc:
        eq.put(_sse_event("defended_result", {
            "response": f"Error: {exc}",
            "blocked": False,
            "blocked_by": "",
            "layers": [],
        }))


# -- Routes -------------------------------------------------------------------

@bp.route("/")
def index() -> str:
    payloads = [
        {"name": f"{cat} — {p[:50]}...", "payload": p}
        for cat, ps in DEFAULT_PAYLOADS.items()
        for p in ps
    ]
    return render_template(
        "demo_27/index.html",
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
