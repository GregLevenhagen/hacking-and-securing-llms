"""Blueprint for Demo 26 — Secure RAG (Access Control).

Side-by-side comparison: vulnerable RAG (returns all matching documents
regardless of user role) vs defended RAG (filters documents by user
role/access level before RAG query — Azure AI Search security trimming).

Routes:
  GET  /demo-26/            → render the comparison UI
  POST /demo-26/api/compare → run both RAG systems, SSE stream results
  POST /demo-26/api/reset   → no-op (stateless)
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

# ── Path setup ──
_demo26_python = PROJECT_ROOT / "demo-26-secure-rag" / "python"
if str(_demo26_python) not in sys.path:
    sys.path.insert(0, str(_demo26_python))

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from demo26_vulnerable_rag import VulnerableRAG  # noqa: E402
from demo26_defended_rag import DefendedRAG, ROLE_ACCESS_MAP  # noqa: E402

# ── Documents ──
_documents_path = (
    PROJECT_ROOT / "demo-26-secure-rag" / "documents" / "sample_documents.json"
)


def _load_documents() -> list[dict[str, Any]]:
    if not _documents_path.exists():
        return []
    with open(_documents_path) as f:
        return json.load(f)


def _load_source_data() -> list[dict]:
    """Load source data for the Source Intelligence Drawer."""
    tabs: list[dict] = []

    # Document corpus
    docs = _load_documents()
    if docs:
        doc_items = [
            {
                "name": f"{d['id']} — {d['title']}",
                "content": (
                    f"Access level: {d['access_level']}\n"
                    f"Department: {d['department']}\n"
                    f"Content: {d['content'][:200]}..."
                ),
            }
            for d in docs
        ]
        tabs.append({
            "id": "documents",
            "label": f"DOCUMENT CORPUS ({len(doc_items)})",
            "type": "list",
            "items": doc_items,
        })

    # Role access map
    role_items = [
        {
            "name": role,
            "content": f"Can access: {', '.join(levels)}",
        }
        for role, levels in ROLE_ACCESS_MAP.items()
    ]
    tabs.append({
        "id": "roles",
        "label": f"ROLE ACCESS MAP ({len(role_items)})",
        "type": "list",
        "items": role_items,
    })

    # Defense layers
    defense_layers = [
        {
            "name": "access_control",
            "content": (
                "Azure AI Search security trimming. Filters search results based on "
                "the querying user's role, ensuring each user only sees documents "
                "their access level permits. Maps user roles to access-level lists "
                "using the ROLE_ACCESS_MAP."
            ),
        },
        {
            "name": "document_filter",
            "content": (
                "Document-level security filter. Applied at query time via Azure AI "
                "Search security filters ($filter=allowed_groups/any(...)). Documents "
                "with access_level outside the user's permitted set are excluded "
                "from search results before RAG context assembly."
            ),
        },
        {
            "name": "role_validator",
            "content": (
                "Role validation layer. Validates the user's role against the known "
                "role hierarchy (intern < employee < manager < executive). Unrecognized "
                "roles default to public-only access (principle of least privilege)."
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
bp = Blueprint("demo_26", __name__, url_prefix="/demo-26")


def _sse_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _format_results(results: list[dict[str, Any]]) -> str:
    """Format search results for display."""
    if not results:
        return "No matching documents found."
    lines = []
    for r in results:
        lines.append(
            f"[{r['access_level'].upper()}] {r['title']}\n"
            f"  Dept: {r['department']} | ID: {r['id']}\n"
            f"  {r['content'][:150]}..."
        )
    return "\n\n".join(lines)


def _run_vulnerable(
    query: str, user_role: str, eq: "queue.Queue[str]", otel_span: Any = None
) -> None:
    """Vulnerable path — returns all matching docs regardless of user role."""
    from blueprints.otel_helpers import span_set, span_set_result

    try:
        t0 = time.time()
        rag = VulnerableRAG()
        results = rag.search(query, user_role=user_role)
        latency = round((time.time() - t0) * 1000, 1)

        # Count documents by access level for the response
        level_counts: dict[str, int] = {}
        for r in results:
            lvl = r.get("access_level", "unknown")
            level_counts[lvl] = level_counts.get(lvl, 0) + 1

        response = (
            f"Vulnerable RAG returned {len(results)} documents (NO access control).\n"
            f"User role '{user_role}' was IGNORED.\n"
            f"Access levels returned: {json.dumps(level_counts)}\n\n"
            f"{_format_results(results)}"
        )

        span_set("vuln.blocked", False, span=otel_span)
        span_set("vuln.doc_count", len(results), span=otel_span)
        span_set_result(
            span=otel_span,
            action="secure_rag_vulnerable",
            blocked=False,
            response_preview=response[:300],
        )
        eq.put(_sse_event("vuln_result", {
            "response": response[:2000],
            "blocked": False,
            "doc_count": len(results),
            "latency_ms": latency,
        }))
    except Exception as exc:
        eq.put(_sse_event("vuln_result", {
            "response": f"Error: {exc}",
            "blocked": False,
            "doc_count": 0,
        }))


def _run_defended(
    query: str, user_role: str, eq: "queue.Queue[str]", otel_span: Any = None
) -> None:
    """Defended path — filter documents by user role/access level."""
    from blueprints.otel_helpers import span_set, span_set_result

    try:
        t0 = time.time()
        layers: list[dict[str, Any]] = []

        # Try Azure AI Search, fall back to local simulation
        azure_search_endpoint = os.getenv("AZURE_SEARCH_ENDPOINT", "")
        azure_search_key = os.getenv("AZURE_SEARCH_KEY", "")

        # Layer 1: Role validation
        layer1_t0 = time.time()
        valid_roles = list(ROLE_ACCESS_MAP.keys())
        role_valid = user_role.lower() in valid_roles if user_role else False
        effective_role = user_role.lower() if role_valid else "(none)"
        layer1_latency = round((time.time() - layer1_t0) * 1000, 1)

        layers.append({
            "name": "role_validator",
            "blocked": False,
            "reason": (
                f"Role '{user_role}' validated — maps to: "
                f"{', '.join(ROLE_ACCESS_MAP.get(effective_role, ['public']))}"
                if role_valid
                else f"Role '{user_role}' unknown — defaulting to public-only access"
            ),
            "latency_ms": layer1_latency,
        })

        # Layer 2: Access control / document filter
        layer2_t0 = time.time()

        if azure_search_endpoint and azure_search_key:
            try:
                # Attempt real Azure AI Search with security trimming
                from azure.search.documents import SearchClient
                from azure.core.credentials import AzureKeyCredential

                _search_client = SearchClient(
                    endpoint=azure_search_endpoint,
                    index_name=os.getenv("AZURE_SEARCH_INDEX", "demo-rag-index"),
                    credential=AzureKeyCredential(azure_search_key),
                )
                allowed_levels = ROLE_ACCESS_MAP.get(effective_role, ["public"])
                filter_expr = " or ".join(
                    f"access_level eq '{lvl}'" for lvl in allowed_levels
                )
                search_results = _search_client.search(
                    search_text=query,
                    filter=filter_expr,
                    top=10,
                )
                results = [dict(r) for r in search_results]
            except Exception:
                # Fall back to local DefendedRAG
                rag = DefendedRAG()
                results = rag.search(query, user_role=effective_role)
        else:
            rag = DefendedRAG()
            results = rag.search(query, user_role=effective_role)

        layer2_latency = round((time.time() - layer2_t0) * 1000, 1)

        # Count what was filtered out vs returned
        all_rag = VulnerableRAG()
        all_results = all_rag.search(query)
        filtered_count = len(all_results) - len(results)

        layers.append({
            "name": "access_control",
            "blocked": filtered_count > 0,
            "reason": (
                f"Filtered {filtered_count} documents above user's access level"
                if filtered_count > 0
                else "No documents filtered — all results within access level"
            ),
            "latency_ms": layer2_latency,
        })

        # Layer 3: Document filter (detail layer showing what was excluded)
        layer3_t0 = time.time()
        excluded_levels: set[str] = set()
        for r in all_results:
            if r["id"] not in {dr["id"] for dr in results}:
                excluded_levels.add(r.get("access_level", "unknown"))
        layer3_latency = round((time.time() - layer3_t0) * 1000, 1)

        layers.append({
            "name": "document_filter",
            "blocked": len(excluded_levels) > 0,
            "reason": (
                f"Excluded documents at levels: {', '.join(sorted(excluded_levels))}"
                if excluded_levels
                else "All matching documents within permitted access levels"
            ),
            "latency_ms": layer3_latency,
        })

        total_latency = round((time.time() - t0) * 1000, 1)

        blocked = filtered_count > 0
        blocked_by = "access_control" if blocked else ""

        response = (
            f"Defended RAG returned {len(results)} documents "
            f"(filtered {filtered_count} by access control).\n"
            f"User role: {effective_role}\n"
            f"Allowed levels: {', '.join(ROLE_ACCESS_MAP.get(effective_role, ['public']))}\n\n"
            f"{_format_results(results)}"
        )

        span_set("defended.blocked", blocked, span=otel_span)
        span_set("defended.doc_count", len(results), span=otel_span)
        span_set("defended.filtered_count", filtered_count, span=otel_span)
        span_set_result(
            span=otel_span,
            action="secure_rag_defended",
            blocked=blocked,
            blocked_by=blocked_by,
            response_preview=response[:300],
        )
        eq.put(_sse_event("defended_result", {
            "response": response[:2000],
            "blocked": blocked,
            "blocked_by": blocked_by,
            "layers": layers,
            "doc_count": len(results),
            "filtered_count": filtered_count,
            "latency_ms": total_latency,
        }))
    except Exception as exc:
        eq.put(_sse_event("defended_result", {
            "response": f"Error: {exc}",
            "blocked": False,
            "blocked_by": "",
            "layers": [],
            "doc_count": 0,
        }))


# ── Routes ──

@bp.route("/")
def index() -> str:
    documents = _load_documents()
    roles = list(ROLE_ACCESS_MAP.keys())
    return render_template(
        "demo_26/index.html",
        documents=documents,
        roles=roles,
        source_tabs=_load_source_data(),
    )


@bp.route("/api/compare", methods=["POST"])
def api_compare() -> Response:
    data = request.get_json(silent=True) or {}
    payload = data.get("payload", "").strip()
    user_role = data.get("user_role", "intern").strip()
    if not payload:
        return jsonify({"error": "No payload provided"}), 400  # type: ignore[return-value]

    from blueprints.otel_helpers import get_request_span

    event_queue: queue.Queue[str] = queue.Queue()
    otel_span = get_request_span()

    t1 = threading.Thread(
        target=_run_vulnerable,
        args=(payload, user_role, event_queue, otel_span),
        daemon=True,
    )
    t2 = threading.Thread(
        target=_run_defended,
        args=(payload, user_role, event_queue, otel_span),
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
