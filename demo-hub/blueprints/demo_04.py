"""Blueprint for Demo 04 — System Prompt Extraction.

Auto-runner + interactive chat for extracting secrets from a system prompt.

Routes:
  GET  /demo-04/            → render the auto-runner + chat UI
  POST /demo-04/api/run-all → run all techniques sequentially, SSE stream
  POST /demo-04/api/chat    → interactive chat, SSE stream
  POST /demo-04/api/reset   → reset chatbot state
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
_demo4_python = PROJECT_ROOT / "demo-04-system-prompt-extraction" / "python"
if str(_demo4_python) not in sys.path:
    sys.path.insert(0, str(_demo4_python))

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from chatbot import KNOWN_SECRETS, check_extraction  # noqa: E402
from extraction_attacks import load_techniques  # noqa: E402
from shared.python.ollama_client import OllamaClient  # noqa: E402

from openai.types.chat import ChatCompletionMessageParam  # noqa: E402

# ── Blueprint ──
bp = Blueprint("demo_04", __name__, url_prefix="/demo-04")

_techniques_path = PROJECT_ROOT / "demo-04-system-prompt-extraction" / "attacks" / "techniques.json"
_secret_prompt_path = PROJECT_ROOT / "demo-04-system-prompt-extraction" / "system_prompts" / "secret_prompt.txt"

# Chat state
_chat_messages: list[ChatCompletionMessageParam] = []
_chat_lock = threading.Lock()


def _load_secret_prompt() -> str:
    if _secret_prompt_path.exists():
        return _secret_prompt_path.read_text().strip()
    return ""


def _init_chat() -> None:
    global _chat_messages
    with _chat_lock:
        _chat_messages = [{"role": "system", "content": _load_secret_prompt()}]


def _sse_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _run_all_techniques(eq: "queue.Queue[str]", otel_span: Any = None) -> None:
    """Run all extraction techniques sequentially."""
    from blueprints.otel_helpers import span_set, span_set_result, span_event

    span_set("demo.action", "run_all_techniques", span=otel_span)
    _total_successes = 0

    try:
        techniques = load_techniques(_techniques_path)
        client = OllamaClient()
        secret_prompt = _load_secret_prompt()
        span_set("attack.technique_count", len(techniques), span=otel_span)

        for i, tech in enumerate(techniques):
            eq.put(_sse_event("technique_start", {
                "index": i,
                "name": tech["name"],
                "prompt": tech["prompt"],
            }))

            messages: list[ChatCompletionMessageParam] = [
                {"role": "system", "content": secret_prompt},
                {"role": "user", "content": tech["prompt"]},
            ]

            full_response = ""
            try:
                for token in client.chat_stream(messages):
                    full_response += token
                    eq.put(_sse_event("token", {"token": token, "index": i}))
            except Exception as exc:
                eq.put(_sse_event("error", {"message": f"LLM error: {exc}"}))
                continue

            found = check_extraction(full_response)
            _success = len(found) > 0
            if _success:
                _total_successes += 1
            span_event("technique_complete", {
                "name": tech["name"],
                "success": _success,
                "secrets_found": ", ".join(found) if found else "",
            }, span=otel_span)
            eq.put(_sse_event("technique_result", {
                "index": i,
                "name": tech["name"],
                "secrets_found": found,
                "success": _success,
            }))

    except Exception as exc:
        eq.put(_sse_event("error", {"message": f"Run error: {exc}"}))

    span_set("result.total_successes", _total_successes, span=otel_span)
    span_set_result(span=otel_span, action="run_all_techniques", success=_total_successes > 0)
    eq.put(_sse_event("done", {}))


MAX_AGENT_RETRIES = 10


def _run_agent_technique(
    tech_index: int,
    tech: dict[str, str],
    secret_prompt: str,
    results_out: "queue.Queue[str]",
) -> None:
    """Run a single extraction technique with retry loop (agent).

    Retries up to MAX_AGENT_RETRIES times with fresh conversations.
    Short-circuits as soon as any secret is found.
    Emits a single agent_result event when done (success or exhausted).
    """
    client = OllamaClient()
    all_found: list[str] = []
    best_response = ""
    attempts = 0

    for attempt in range(1, MAX_AGENT_RETRIES + 1):
        attempts = attempt
        messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": secret_prompt},
            {"role": "user", "content": tech["prompt"]},
        ]

        full_response = ""
        try:
            for token in client.chat_stream(messages):
                full_response += token
        except Exception:
            continue  # retry on error

        found = check_extraction(full_response)
        if found:
            all_found = found
            best_response = full_response
            break  # short-circuit on success

        # On last attempt, keep the response even if no secrets found
        if attempt == MAX_AGENT_RETRIES:
            best_response = full_response

    results_out.put(_sse_event("agent_result", {
        "index": tech_index,
        "name": tech["name"],
        "prompt": tech["prompt"],
        "attempts": attempts,
        "max_attempts": MAX_AGENT_RETRIES,
        "secrets_found": all_found,
        "success": len(all_found) > 0,
        "response_preview": best_response[:500],
    }))


def _run_agentic_retries(eq: "queue.Queue[str]", otel_span: Any = None) -> None:
    """Run all techniques in parallel with retry loops."""
    from blueprints.otel_helpers import span_set, span_set_result

    span_set("demo.action", "agentic_retries", span=otel_span)
    completed = 0

    try:
        techniques = load_techniques(_techniques_path)
        secret_prompt = _load_secret_prompt()

        span_set("attack.technique_count", len(techniques), span=otel_span)

        eq.put(_sse_event("agentic_start", {
            "count": len(techniques),
            "max_retries": MAX_AGENT_RETRIES,
        }))

        # Shared queue for agent results
        agent_results: queue.Queue[str] = queue.Queue()
        threads: list[threading.Thread] = []

        for i, tech in enumerate(techniques):
            t = threading.Thread(
                target=_run_agent_technique,
                args=(i, tech, secret_prompt, agent_results),
                daemon=True,
            )
            threads.append(t)
            t.start()

        # Collect results as agents finish (in completion order)
        completed = 0
        while completed < len(techniques):
            try:
                event = agent_results.get(timeout=600)
                eq.put(event)
                completed += 1
                eq.put(_sse_event("agentic_progress", {
                    "completed": completed,
                    "total": len(techniques),
                }))
            except queue.Empty:
                eq.put(_sse_event("error", {"message": "Agentic retries timeout"}))
                break

        # Wait for all threads to finish
        for t in threads:
            t.join(timeout=5)

    except Exception as exc:
        eq.put(_sse_event("error", {"message": f"Agentic error: {exc}"}))

    span_set("result.total_completed", completed, span=otel_span)
    span_set_result(span=otel_span, action="agentic_retries")
    eq.put(_sse_event("agentic_done", {}))


def _stream_chat(message: str, eq: "queue.Queue[str]", otel_span: Any = None) -> None:
    """Interactive chat with the secret-holding chatbot."""
    from blueprints.otel_helpers import span_set, span_set_result

    span_set("demo.action", "chat", span=otel_span)

    try:
        client = OllamaClient()
        with _chat_lock:
            _chat_messages.append({"role": "user", "content": message})
            msgs = list(_chat_messages)

        full_response = ""
        for token in client.chat_stream(msgs):
            full_response += token
            eq.put(_sse_event("token", {"token": token}))

        with _chat_lock:
            _chat_messages.append({"role": "assistant", "content": full_response})

        found = check_extraction(full_response)
        eq.put(_sse_event("chat_result", {
            "secrets_found": found,
            "success": len(found) > 0,
        }))
        span_set("result.secrets_found", ", ".join(found) if found else "", span=otel_span)
        span_set_result(
            span=otel_span,
            action="chat",
            success=len(found) > 0,
            response_preview=full_response,
        )
    except Exception as exc:
        eq.put(_sse_event("error", {"message": f"Chat error: {exc}"}))

    eq.put(_sse_event("done", {}))


def _load_source_data() -> list[dict]:
    """Load source data for the drawer."""
    tabs: list[dict] = []
    # Secret system prompt
    prompt_path = PROJECT_ROOT / "demo-04-system-prompt-extraction" / "system_prompts" / "secret_prompt.txt"
    if prompt_path.exists():
        tabs.append({"id": "secret_prompt", "label": "SECRET PROMPT", "type": "text", "content": prompt_path.read_text()})
    # Techniques
    techniques = load_techniques(_techniques_path)
    if techniques:
        tabs.append({
            "id": "techniques",
            "label": f"TECHNIQUES ({len(techniques)})",
            "type": "list",
            "items": [{"name": t["name"], "content": t["prompt"]} for t in techniques],
        })
    return tabs


@bp.route("/")
def index() -> str:
    techniques = load_techniques(_techniques_path)
    return render_template("demo_04/index.html",
        techniques=techniques,
        known_secrets=KNOWN_SECRETS,
        source_tabs=_load_source_data(),
    )


@bp.route("/api/run-all", methods=["POST"])
def api_run_all() -> Response:
    from blueprints.otel_helpers import get_request_span

    event_queue: queue.Queue[str] = queue.Queue()
    otel_span = get_request_span()
    thread = threading.Thread(target=_run_all_techniques, args=(event_queue, otel_span), daemon=True)
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


@bp.route("/api/agentic-retries", methods=["POST"])
def api_agentic_retries() -> Response:
    from blueprints.otel_helpers import get_request_span

    event_queue: queue.Queue[str] = queue.Queue()
    otel_span = get_request_span()
    thread = threading.Thread(target=_run_agentic_retries, args=(event_queue, otel_span), daemon=True)
    thread.start()

    def generate() -> Generator[str, None, None]:
        while True:
            try:
                event = event_queue.get(timeout=600)
                yield event
                if "event: agentic_done" in event:
                    break
            except queue.Empty:
                yield _sse_event("error", {"message": "Timeout"})
                break

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@bp.route("/api/chat", methods=["POST"])
def api_chat() -> Response:
    data = request.get_json(silent=True) or {}
    message = data.get("message", "").strip()
    if not message:
        return jsonify({"error": "No message provided"}), 400  # type: ignore[return-value]

    if not _chat_messages:
        _init_chat()

    from blueprints.otel_helpers import get_request_span

    event_queue: queue.Queue[str] = queue.Queue()
    otel_span = get_request_span()
    thread = threading.Thread(target=_stream_chat, args=(message, event_queue, otel_span), daemon=True)
    thread.start()

    def generate() -> Generator[str, None, None]:
        while True:
            try:
                event = event_queue.get(timeout=120)
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
    _init_chat()
    return jsonify({"status": "ok"}), 200


# Init chat on import
_init_chat()
