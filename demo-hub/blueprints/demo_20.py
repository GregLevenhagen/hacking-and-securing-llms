"""Blueprint for Demo 20 — Prompt Shields (Jailbreak Detection).

Side-by-side comparison: vulnerable chatbot (no jailbreak detection) vs defended
chatbot (Azure Prompt Shields scanning for jailbreak and indirect injection).

Routes:
  GET  /demo-20/            → render the comparison UI
  POST /demo-20/api/compare → run both chatbots, SSE stream results
  POST /demo-20/api/reset   → no-op (stateless)
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
_demo20_python = PROJECT_ROOT / "demo-20-prompt-shields" / "python"
if str(_demo20_python) not in sys.path:
    sys.path.insert(0, str(_demo20_python))

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.python.ollama_client import OllamaClient  # noqa: E402

# ── Payloads ──
_payloads_path = PROJECT_ROOT / "demo-20-prompt-shields" / "attacks" / "jailbreak_payloads.json"

# ── Jailbreak simulation patterns ──
_JAILBREAK_PATTERNS: list[tuple[str, str]] = [
    (r"ignore\s+(all\s+)?previous\s+instructions", "system_override"),
    (r"you\s+are\s+now\s+DAN", "role_switching"),
    (r"do\s+anything\s+now", "role_switching"),
    (r"developer\s+mode", "role_switching"),
    (r"ignore\s+(your\s+)?safety", "system_override"),
    (r"bypass\s+.*restrictions", "system_override"),
    (r"disable\s+.*safety", "system_override"),
    (r"```system", "system_override"),
    (r"unrestricted\s+assistant", "system_override"),
    (r"base64.*decode.*follow", "encoding"),
    (r"ROT13.*translate.*execute", "encoding"),
    (r"1gn0r3|4ll\s+s4f3ty", "encoding"),
    (r"for\s+research\s+purposes\s+only", "multi_turn"),
    (r"fictional\s+novel.*villain", "hypothetical"),
    (r"combine\s+them\s+and\s+explain", "splitting"),
    (r"prefix.*Step\s+1:", "prefix_injection"),
    (r"re-spond|pro-mpt", "token_manipulation"),
    (r"cybersecurity\s+training\s+manual", "obfuscation"),
]

_INDIRECT_INJECTION_PATTERNS: list[str] = [
    r"ignore\s+.*instructions.*and",
    r"new\s+instruction",
    r"system\s+prompt",
    r"reveal\s+.*prompt",
    r"PWNED",
]

VULN_SYSTEM_PROMPT = (
    "You are a helpful assistant. Answer questions accurately. "
    "Be concise and informative."
)

DEFENDED_SYSTEM_PROMPT = (
    "You are a helpful assistant. Answer questions accurately. "
    "Be concise and informative."
)


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
            "name": "jailbreak_detector",
            "content": (
                "Azure Prompt Shields jailbreak detector. Scans user prompts "
                "for jailbreak attempts including role-switching, system overrides, "
                "encoding tricks, and multi-turn escalation. Returns BLOCKED with "
                "the detected attack type if a jailbreak is identified."
            ),
        },
        {
            "name": "indirect_injection_detector",
            "content": (
                "Azure Prompt Shields indirect injection detector. Scans any "
                "documents or external content provided alongside the prompt for "
                "hidden instructions that attempt to manipulate the LLM's behavior. "
                "Detects embedded instructions in retrieved documents, web pages, etc."
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


def _simulate_jailbreak_scan(user_prompt: str) -> dict[str, Any]:
    """Simulate Azure Prompt Shields when credentials are absent."""
    text_lower = user_prompt.lower()
    detected = False
    attack_type = "none"

    for pattern, atype in _JAILBREAK_PATTERNS:
        if re.search(pattern, text_lower):
            detected = True
            attack_type = atype
            break

    return {
        "userPromptAttack": {
            "detected": detected,
            "attackType": attack_type,
            "confidence": 0.95 if detected else 0.0,
        },
        "documentAttack": {
            "detected": False,
            "attackType": "none",
            "confidence": 0.0,
        },
    }


def _simulate_indirect_scan(user_prompt: str) -> dict[str, Any]:
    """Simulate indirect injection scanning."""
    text_lower = user_prompt.lower()
    detected = False
    for pattern in _INDIRECT_INJECTION_PATTERNS:
        if re.search(pattern, text_lower):
            detected = True
            break

    return {
        "detected": detected,
        "attackType": "indirect_injection" if detected else "none",
        "confidence": 0.90 if detected else 0.0,
    }


def _azure_prompt_shield(user_prompt: str) -> tuple[dict[str, Any], bool]:
    """Try Azure Prompt Shields; fall back to simulation.

    Returns (shield_result, used_azure).
    """
    endpoint = os.getenv("AZURE_CONTENT_SAFETY_ENDPOINT", "")
    key = os.getenv("AZURE_CONTENT_SAFETY_KEY", "")

    if endpoint and key:
        try:
            from azure.ai.contentsafety import ContentSafetyClient
            from azure.ai.contentsafety.models import ShieldPromptOptions
            from azure.core.credentials import AzureKeyCredential

            client = ContentSafetyClient(endpoint, AzureKeyCredential(key))
            resp = client.shield_prompt(ShieldPromptOptions(
                user_prompt=user_prompt,
                documents=[],
            ))
            result: dict[str, Any] = {
                "userPromptAttack": {
                    "detected": getattr(resp, "user_prompt_analysis", None) is not None
                    and getattr(resp.user_prompt_analysis, "attack_detected", False),
                    "attackType": "jailbreak",
                    "confidence": 0.95,
                },
                "documentAttack": {
                    "detected": False,
                    "attackType": "none",
                    "confidence": 0.0,
                },
            }
            return result, True
        except Exception:
            pass

    return _simulate_jailbreak_scan(user_prompt), False


# ── Blueprint ──
bp = Blueprint("demo_20", __name__, url_prefix="/demo-20")


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
            action="vulnerable_prompt_shields",
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
        # ── Layer 1: Jailbreak detection ──
        t0 = time.time()
        shield_result, _used_azure = _azure_prompt_shield(payload)
        jailbreak_ms = round((time.time() - t0) * 1000)

        user_attack = shield_result.get("userPromptAttack", {})
        jailbreak_detected = user_attack.get("detected", False)
        attack_type = user_attack.get("attackType", "none")

        layers.append({
            "name": "jailbreak_detector",
            "blocked": jailbreak_detected,
            "reason": (
                f"Jailbreak detected (type: {attack_type})"
                if jailbreak_detected
                else "No jailbreak detected"
            ),
            "latency_ms": jailbreak_ms,
        })

        if jailbreak_detected:
            response_text = (
                f"[BLOCKED] Jailbreak attempt detected "
                f"(type: {attack_type})"
            )
            span_set_result(
                span=otel_span,
                action="prompt_shields",
                blocked=True,
                blocked_by="jailbreak_detector",
                response_preview=response_text[:300],
            )
            eq.put(_sse_event("defended_result", {
                "response": response_text,
                "blocked": True,
                "blocked_by": "jailbreak_detector",
                "layers": layers,
            }))
            return

        # ── Layer 2: Indirect injection detection ──
        t0 = time.time()
        indirect_result = _simulate_indirect_scan(payload)
        indirect_ms = round((time.time() - t0) * 1000)

        indirect_detected = indirect_result.get("detected", False)

        layers.append({
            "name": "indirect_injection_detector",
            "blocked": indirect_detected,
            "reason": (
                "Indirect injection pattern detected"
                if indirect_detected
                else "No indirect injection detected"
            ),
            "latency_ms": indirect_ms,
        })

        if indirect_detected:
            response_text = (
                "[BLOCKED] Indirect injection attempt detected in the prompt."
            )
            span_set_result(
                span=otel_span,
                action="prompt_shields",
                blocked=True,
                blocked_by="indirect_injection_detector",
                response_preview=response_text[:300],
            )
            eq.put(_sse_event("defended_result", {
                "response": response_text,
                "blocked": True,
                "blocked_by": "indirect_injection_detector",
                "layers": layers,
            }))
            return

        # ── All clear — send to LLM ──
        client = OllamaClient()
        messages = [
            {"role": "system", "content": DEFENDED_SYSTEM_PROMPT},
            {"role": "user", "content": payload},
        ]
        response = str(client.chat(messages))

        span_set_result(
            span=otel_span,
            action="prompt_shields",
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
    return render_template("demo_20/index.html", payloads=payloads, source_tabs=_load_source_data())


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
