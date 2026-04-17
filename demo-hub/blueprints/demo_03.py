"""Blueprint for Demo 03 — RAG Poisoning.

5-phase runner: Build Index → Query Clean → Poison → Query Poisoned → Compare.

Routes:
  GET  /demo-03/          → render the phase runner UI
  POST /demo-03/api/phase → run a phase (1-5), SSE stream results
  POST /demo-03/api/reset → clear ChromaDB state
"""

import json
import queue
import shutil
import sys
import threading
from pathlib import Path
from typing import Any, Generator

from flask import Blueprint, Response, jsonify, render_template, request, stream_with_context

from blueprints import PROJECT_ROOT

# ── Path setup ──
_demo3_python = PROJECT_ROOT / "demo-03-rag-poisoning" / "python"
if str(_demo3_python) not in sys.path:
    sys.path.insert(0, str(_demo3_python))

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ── Blueprint ──
bp = Blueprint("demo_03", __name__, url_prefix="/demo-03")

_hub_chroma_dir = PROJECT_ROOT / "demo-hub" / ".chroma_demo03"

# State tracking
_phase_state = {"current": 0, "clean_result": "", "poisoned_result": ""}
_state_lock = threading.Lock()

DEFAULT_QUERY = "What is the company refund policy?"


def _sse_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _run_phase(phase: int, eq: "queue.Queue[str]", otel_span: Any = None) -> None:
    """Execute a single demo phase."""
    from blueprints.otel_helpers import span_set, span_set_result

    span_set("demo.action", "rag_phase", span=otel_span)
    span_set("attack.phase", phase, span=otel_span)

    try:
        import chromadb as _chromadb  # noqa: E402
        from build_index import COLLECTION_NAME, OllamaEmbeddingFunction, build_index  # noqa: E402
        from poison_index import poison_index  # noqa: E402
        from query_rag import query_rag  # noqa: E402

        def _get_collection() -> "_chromadb.Collection":
            """Get the ChromaDB collection with the correct embedding function."""
            chroma_client = _chromadb.PersistentClient(path=str(_hub_chroma_dir))
            return chroma_client.get_collection(
                COLLECTION_NAME,
                embedding_function=OllamaEmbeddingFunction(),  # type: ignore[arg-type]
            )

        if phase == 1:
            eq.put(_sse_event("progress", {"message": "Building clean document index..."}))
            build_index(chroma_dir=_hub_chroma_dir)
            with _state_lock:
                _phase_state["current"] = 1
            eq.put(_sse_event("phase_result", {"phase": 1, "message": "Clean index built successfully."}))
            span_set_result(span=otel_span, action="rag_phase", response_preview="Clean index built successfully.")

        elif phase == 2:
            eq.put(_sse_event("progress", {"message": "Querying clean RAG system..."}))
            collection = _get_collection()
            result = query_rag(DEFAULT_QUERY, collection=collection)
            answer = result["answer"]
            with _state_lock:
                _phase_state["current"] = 2
                _phase_state["clean_result"] = answer
            eq.put(_sse_event("phase_result", {"phase": 2, "message": answer[:1000]}))
            span_set_result(span=otel_span, action="rag_phase", response_preview=answer)

        elif phase == 3:
            eq.put(_sse_event("progress", {"message": "Injecting poisoned document..."}))
            poison_index(chroma_dir=_hub_chroma_dir)
            with _state_lock:
                _phase_state["current"] = 3
            eq.put(_sse_event("phase_result", {"phase": 3, "message": "Poisoned document injected into index."}))
            span_set_result(span=otel_span, action="rag_phase", response_preview="Poisoned document injected into index.")

        elif phase == 4:
            eq.put(_sse_event("progress", {"message": "Querying poisoned RAG system..."}))
            collection = _get_collection()
            result = query_rag(DEFAULT_QUERY, collection=collection)
            answer = result["answer"]
            with _state_lock:
                _phase_state["current"] = 4
                _phase_state["poisoned_result"] = answer
            eq.put(_sse_event("phase_result", {"phase": 4, "message": answer[:1000]}))
            span_set_result(span=otel_span, action="rag_phase", response_preview=answer)

        elif phase == 5:
            with _state_lock:
                clean = str(_phase_state["clean_result"])
                poisoned = str(_phase_state["poisoned_result"])
                _phase_state["current"] = 5
            eq.put(_sse_event("phase_result", {
                "phase": 5,
                "clean": clean[:1000],
                "poisoned": poisoned[:1000],
            }))
            span_set_result(span=otel_span, action="rag_phase", response_preview=f"clean={clean[:150]} | poisoned={poisoned[:150]}")

    except Exception as exc:
        eq.put(_sse_event("error", {"message": f"Phase {phase} error: {exc}"}))

    eq.put(_sse_event("done", {}))


def _load_source_docs() -> list[dict]:
    """Load document corpus for the source drawer."""
    tabs: list[dict] = []
    legit_dir = PROJECT_ROOT / "demo-03-rag-poisoning" / "documents" / "legitimate"
    poisoned_dir = PROJECT_ROOT / "demo-03-rag-poisoning" / "documents" / "poisoned"

    legit_files = []
    if legit_dir.exists():
        for f in sorted(legit_dir.glob("*.txt")):
            legit_files.append({"name": f.stem.replace("_", " ").title(), "content": f.read_text()})

    poisoned_files = []
    if poisoned_dir.exists():
        for f in sorted(poisoned_dir.glob("*.txt")):
            poisoned_files.append({"name": f"[POISONED] {f.stem.replace('_', ' ').title()}", "content": f.read_text()})

    if legit_files:
        tabs.append({"id": "clean_docs", "label": f"CLEAN DOCS ({len(legit_files)})", "type": "files", "files": legit_files})
    if poisoned_files:
        tabs.append({"id": "poisoned_docs", "label": f"POISONED DOCS ({len(poisoned_files)})", "type": "files", "files": poisoned_files})
    return tabs


@bp.route("/")
def index() -> str:
    return render_template("demo_03/index.html", current_phase=_phase_state["current"], source_tabs=_load_source_docs())


@bp.route("/api/phase", methods=["POST"])
def api_phase() -> Response:
    data = request.get_json(silent=True) or {}
    phase = data.get("phase", 0)
    if not isinstance(phase, int) or phase < 1 or phase > 5:
        return jsonify({"error": "Invalid phase (1-5)"}), 400  # type: ignore[return-value]

    from blueprints.otel_helpers import get_request_span

    event_queue: queue.Queue[str] = queue.Queue()
    otel_span = get_request_span()
    thread = threading.Thread(target=_run_phase, args=(phase, event_queue, otel_span), daemon=True)
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
    if _hub_chroma_dir.exists():
        shutil.rmtree(_hub_chroma_dir, ignore_errors=True)
    with _state_lock:
        _phase_state["current"] = 0
        _phase_state["clean_result"] = ""
        _phase_state["poisoned_result"] = ""
    return jsonify({"status": "ok"}), 200
