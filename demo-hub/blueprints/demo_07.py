"""Blueprint for Demo 07 — RAG Defense.

Side-by-side comparison: undefended RAG (poisoned results) vs defended RAG
(filtered by document_validator, injection_detector, source_verifier, relevance_scorer).

Routes:
  GET  /demo-07/            → render the comparison UI
  POST /demo-07/api/setup   → build and poison the ChromaDB index (SSE progress)
  POST /demo-07/api/compare → query both RAG systems, SSE stream results
  POST /demo-07/api/reset   → clear ChromaDB state
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
_demo7_python = PROJECT_ROOT / "demo-07-rag-defense" / "python"
if str(_demo7_python) not in sys.path:
    sys.path.insert(0, str(_demo7_python))

_demo3_python = PROJECT_ROOT / "demo-03-rag-poisoning" / "python"
if str(_demo3_python) not in sys.path:
    sys.path.insert(0, str(_demo3_python))

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ── Blueprint ──
bp = Blueprint("demo_07", __name__, url_prefix="/demo-07")

# Hub-specific ChromaDB directory to avoid state bleed
_hub_chroma_dir = PROJECT_ROOT / "demo-hub" / ".chroma_demo07"

# Setup state
_setup_done = False
_setup_lock = threading.Lock()

DEFAULT_QUERIES = [
    "What is the company refund policy?",
    "How do I return a defective product?",
    "What are the employee vacation policies?",
]


def _load_source_data() -> list[dict]:
    """Load source data for the Source Intelligence Drawer."""
    tabs: list[dict] = []

    # Clean documents (reused from Demo 03)
    legit_dir = PROJECT_ROOT / "demo-03-rag-poisoning" / "documents" / "legitimate"
    legit_files = []
    if legit_dir.exists():
        for f in sorted(legit_dir.glob("*.txt")):
            legit_files.append({"name": f.stem.replace("_", " ").title(), "content": f.read_text()})
    if legit_files:
        tabs.append({
            "id": "clean_docs",
            "label": f"CLEAN DOCS ({len(legit_files)})",
            "type": "files",
            "files": legit_files,
        })

    # Poisoned documents (reused from Demo 03)
    poisoned_dir = PROJECT_ROOT / "demo-03-rag-poisoning" / "documents" / "poisoned"
    poisoned_files = []
    if poisoned_dir.exists():
        for f in sorted(poisoned_dir.glob("*.txt")):
            poisoned_files.append({
                "name": f"[POISONED] {f.stem.replace('_', ' ').title()}",
                "content": f.read_text(),
            })
    if poisoned_files:
        tabs.append({
            "id": "poisoned_docs",
            "label": f"POISONED DOCS ({len(poisoned_files)})",
            "type": "files",
            "files": poisoned_files,
        })

    # Defense layers
    defense_layers = [
        {
            "name": "source_verifier",
            "content": (
                "Source trust verifier for RAG documents. Assigns trust levels "
                "(high/medium/low/untrusted) to documents based on their source "
                "path. Documents from known-good directories get high trust; "
                "unknown or suspicious paths get lower trust."
            ),
        },
        {
            "name": "document_validator",
            "content": (
                "Document metadata validator for RAG defense. Checks document "
                "metadata (author, date, source) against an allowlist of trusted "
                "values. Documents with missing or untrusted metadata are flagged "
                "as potentially poisoned."
            ),
        },
        {
            "name": "injection_detector",
            "content": (
                "Injection pattern detector for retrieved RAG document chunks. "
                "Scans retrieved text chunks for prompt injection patterns "
                "including RAG-specific patterns like 'when asked about' and "
                "'instead respond'."
            ),
        },
        {
            "name": "relevance_scorer",
            "content": (
                "Relevance scorer using sentence-transformers cross-encoder. "
                "Reranks retrieved chunks by semantic relevance to the query. "
                "Poisoned documents that are off-topic or contain injected "
                "instructions typically score lower on genuine relevance."
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


def _sse_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _do_setup(eq: "queue.Queue[str]", otel_span: Any = None) -> None:
    """Build the clean index, then poison it."""
    global _setup_done
    try:
        from build_index import build_index, COLLECTION_NAME, OllamaEmbeddingFunction  # noqa: E402
        from poison_index import poison_index  # noqa: E402

        eq.put(_sse_event("progress", {"phase": "Building clean index..."}))
        build_index(chroma_dir=_hub_chroma_dir)

        eq.put(_sse_event("progress", {"phase": "Injecting poisoned document..."}))
        poison_index(chroma_dir=_hub_chroma_dir)

        with _setup_lock:
            _setup_done = True

        from blueprints.otel_helpers import span_set_result
        span_set_result(span=otel_span, action="rag_setup")
        eq.put(_sse_event("setup_complete", {"message": "Index ready with clean + poisoned documents."}))
    except Exception as exc:
        eq.put(_sse_event("error", {"message": f"Setup failed: {exc}"}))
    eq.put(_sse_event("done", {}))


def _get_collection() -> Any:
    """Get the ChromaDB collection with the correct embedding function."""
    import chromadb as _chromadb  # noqa: E402
    from build_index import COLLECTION_NAME, OllamaEmbeddingFunction  # noqa: E402
    chroma_client = _chromadb.PersistentClient(path=str(_hub_chroma_dir))
    return chroma_client.get_collection(
        COLLECTION_NAME,
        embedding_function=OllamaEmbeddingFunction(),  # type: ignore[arg-type]
    )


def _query_undefended(query: str, eq: "queue.Queue[str]", otel_span: Any = None) -> None:
    """Query the RAG system without defenses."""
    from blueprints.otel_helpers import span_set, span_set_result, span_event

    try:
        from query_rag import query_rag  # noqa: E402

        collection = _get_collection()
        result = query_rag(query, collection=collection)
        span_event("vuln_query_complete", {
            "sources_count": len(result.get("sources", [])),
            "response_length": len(result["answer"]),
        }, span=otel_span)
        span_set("vuln.response_preview", result["answer"][:200], span=otel_span)
        span_set_result(span=otel_span, action="rag_query_undefended", response_preview=result["answer"])
        eq.put(_sse_event("vuln_result", {
            "response": result["answer"][:1000],
            "sources": result.get("sources", []),
            "blocked": False,
        }))
    except Exception as exc:
        eq.put(_sse_event("vuln_result", {
            "response": f"Error: {exc}",
            "sources": [],
            "blocked": False,
        }))


def _query_defended(query: str, eq: "queue.Queue[str]", otel_span: Any = None) -> None:
    """Query the RAG system with defense layers."""
    from blueprints.otel_helpers import span_set, span_set_result, span_event

    try:
        from demo07_defended_rag import query_defended_rag  # noqa: E402

        collection = _get_collection()
        result = query_defended_rag(query, collection=collection)

        layers: list[dict[str, Any]] = []
        for chunk_result in result.get("chunk_verdicts", []):
            for verdict in chunk_result.get("verdicts", []):
                layers.append({
                    "name": verdict.get("layer", "unknown"),
                    "blocked": not verdict.get("trusted", True),
                    "reason": verdict.get("reason", ""),
                })

        was_blocked = result.get("filtered_count", 0) > 0
        blocking_layers = [l["name"] for l in layers if l["blocked"]]

        span_set_result(
            span=otel_span,
            action="rag_compare",
            blocked=was_blocked,
            blocked_by=", ".join(blocking_layers) if blocking_layers else "",
            response_preview=result["answer"],
        )
        span_set("defense.filtered_count", result.get("filtered_count", 0), span=otel_span)
        span_set("defense.layers_checked", len(layers), span=otel_span)
        for i, layer in enumerate(layers):
            span_event(f"defense_layer_{layer['name']}", {
                "blocked": layer["blocked"],
                "reason": layer.get("reason", ""),
            }, span=otel_span)

        eq.put(_sse_event("defended_result", {
            "response": result["answer"][:1000],
            "blocked": was_blocked,
            "blocked_by": "retrieval_defenses",
            "layers": layers,
            "filtered_count": result.get("filtered_count", 0),
        }))
    except Exception as exc:
        eq.put(_sse_event("defended_result", {
            "response": f"Error: {exc}",
            "blocked": False,
            "blocked_by": "",
            "layers": [],
            "filtered_count": 0,
        }))


@bp.route("/")
def index() -> str:
    return render_template(
        "demo_07/index.html",
        queries=DEFAULT_QUERIES,
        setup_done=_setup_done,
        source_tabs=_load_source_data(),
    )


@bp.route("/api/setup", methods=["POST"])
def api_setup() -> Response:
    from blueprints.otel_helpers import get_request_span
    otel_span = get_request_span()
    event_queue: queue.Queue[str] = queue.Queue()
    thread = threading.Thread(target=_do_setup, args=(event_queue, otel_span), daemon=True)
    thread.start()

    def generate() -> Generator[str, None, None]:
        while True:
            try:
                event = event_queue.get(timeout=300)
                yield event
                if "event: done" in event:
                    break
            except queue.Empty:
                yield _sse_event("error", {"message": "Setup timeout"})
                break

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@bp.route("/api/compare", methods=["POST"])
def api_compare() -> Response:
    data = request.get_json(silent=True) or {}
    payload = data.get("payload", "").strip() or data.get("query", "").strip()
    if not payload:
        return jsonify({"error": "No query provided"}), 400  # type: ignore[return-value]

    if not _setup_done:
        return jsonify({"error": "Run setup first"}), 400  # type: ignore[return-value]

    from blueprints.otel_helpers import get_request_span

    event_queue: queue.Queue[str] = queue.Queue()
    otel_span = get_request_span()

    t1 = threading.Thread(target=_query_undefended, args=(payload, event_queue, otel_span), daemon=True)
    t2 = threading.Thread(target=_query_defended, args=(payload, event_queue, otel_span), daemon=True)
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
    global _setup_done
    import shutil
    if _hub_chroma_dir.exists():
        shutil.rmtree(_hub_chroma_dir, ignore_errors=True)
    with _setup_lock:
        _setup_done = False
    return jsonify({"status": "ok"}), 200
