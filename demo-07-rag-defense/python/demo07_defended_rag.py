"""Defended RAG system with four defense layers.

Applies all four RAG defense modules to retrieved documents before
sending them to the LLM. Poisoned documents are filtered out by
one or more layers: document_validator, injection_detector,
source_verifier, and relevance_scorer.
"""

import sys
import time
from pathlib import Path
from typing import Any

# Add project root to path for shared imports
_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root))

import chromadb  # noqa: E402
from openai.types.chat import ChatCompletionMessageParam  # noqa: E402

from shared.python.ollama_client import OllamaClient  # noqa: E402

from retrieval_defenses import document_validator, injection_detector, relevance_scorer, source_verifier  # noqa: E402

# Number of chunks to retrieve per query
DEFAULT_TOP_K = 5

# System prompt for RAG-augmented answering
RAG_SYSTEM_PROMPT = """You are a helpful customer service assistant for AcmeTech Corporation.
Answer questions based ONLY on the provided context documents.
If the answer is not found in the context, say "I don't have information about that in our documents."
Always cite which document(s) your answer comes from.

Context documents:
{context}"""


def apply_defenses(
    chunk: dict[str, Any],
    query: str,
    relevance_model: Any = None,
) -> dict[str, Any]:
    """Apply all four defense layers to a single retrieved chunk.

    Args:
        chunk: Dict with 'content', 'source', and 'distance' keys.
        query: The user's original query (for relevance scoring).
        relevance_model: Pre-loaded cross-encoder model (optional).

    Returns:
        Dict with 'chunk', 'verdicts' (list of DefenseResult), and 'passed' (bool).
    """
    verdicts: list[dict[str, Any]] = []
    chunk_start = time.perf_counter()

    # Layer 1: Source verification — check trust level by path
    t0 = time.perf_counter()
    source_result = source_verifier.check(chunk["source"])
    sr = dict(source_result)
    sr["latency_ms"] = (time.perf_counter() - t0) * 1000
    verdicts.append(sr)

    # Layer 2: Document metadata validation
    doc_meta = {
        "source": chunk["source"],
        "content": chunk["content"],
    }
    t0 = time.perf_counter()
    validator_result = document_validator.check(doc_meta)
    vr = dict(validator_result)
    vr["latency_ms"] = (time.perf_counter() - t0) * 1000
    verdicts.append(vr)

    # Layer 3: Injection pattern detection
    t0 = time.perf_counter()
    injection_result = injection_detector.check(chunk["content"])
    ir = dict(injection_result)
    ir["latency_ms"] = (time.perf_counter() - t0) * 1000
    verdicts.append(ir)

    # Layer 4: Relevance scoring
    t0 = time.perf_counter()
    relevance_result = relevance_scorer.check(
        query=query,
        document_text=chunk["content"],
        model=relevance_model,
    )
    rr = dict(relevance_result)
    rr["latency_ms"] = (time.perf_counter() - t0) * 1000
    verdicts.append(rr)

    # A chunk passes only if ALL layers trust it
    passed = all(v["trusted"] for v in verdicts)
    total_ms = (time.perf_counter() - chunk_start) * 1000

    return {
        "chunk": chunk,
        "verdicts": verdicts,
        "passed": passed,
        "total_latency_ms": total_ms,
    }


def retrieve_and_filter(
    query: str,
    collection: chromadb.Collection,
    top_k: int = DEFAULT_TOP_K,
    relevance_model: Any = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Retrieve chunks and filter through defense layers.

    Returns:
        Tuple of (trusted_chunks, all_defense_results).
        trusted_chunks: list of chunk dicts that passed all defenses.
        all_defense_results: list of defense result dicts for every chunk.
    """
    results = collection.query(
        query_texts=[query],
        n_results=top_k,
    )

    all_defense_results: list[dict[str, Any]] = []
    trusted_chunks: list[dict[str, Any]] = []

    if results["documents"] and results["metadatas"] and results["distances"]:
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            chunk = {
                "content": doc,
                "source": meta.get("source", "unknown"),
                "distance": dist,
            }

            defense_result = apply_defenses(chunk, query, relevance_model)
            all_defense_results.append(defense_result)

            if defense_result["passed"]:
                trusted_chunks.append(chunk)

    return trusted_chunks, all_defense_results


def format_context(chunks: list[dict[str, Any]]) -> str:
    """Format trusted chunks into a context string for the LLM."""
    parts: list[str] = []
    for i, chunk in enumerate(chunks, 1):
        parts.append(f"[Document {i}: {chunk['source']}]\n{chunk['content']}")
    return "\n\n---\n\n".join(parts)


def query_defended_rag(
    question: str,
    collection: chromadb.Collection,
    client: Any = None,
    top_k: int = DEFAULT_TOP_K,
    relevance_model: Any = None,
) -> dict[str, Any]:
    """Query the defended RAG system.

    Retrieves chunks, applies all defense layers, then sends only
    trusted chunks to the LLM.

    Args:
        question: The user's question.
        collection: The ChromaDB collection to search.
        client: OllamaClient instance (or mock for testing).
        top_k: Number of chunks to retrieve before filtering.
        relevance_model: Pre-loaded cross-encoder model (optional).

    Returns:
        Dict with 'answer', 'sources', 'trusted_chunks',
        'defense_results', and 'filtered_count' keys.
    """
    if not question or not question.strip():
        return {
            "answer": "No question provided.",
            "sources": [],
            "trusted_chunks": [],
            "defense_results": [],
            "filtered_count": 0,
        }

    llm_client = client or OllamaClient()

    # Retrieve and filter chunks
    trusted_chunks, defense_results = retrieve_and_filter(
        question, collection, top_k, relevance_model
    )

    total_retrieved = len(defense_results)
    filtered_count = total_retrieved - len(trusted_chunks)

    # Build context from trusted chunks only
    if trusted_chunks:
        context = format_context(trusted_chunks)
    else:
        context = "(No trusted documents found for this query.)"

    system_prompt = RAG_SYSTEM_PROMPT.format(context=context)

    # Query the LLM
    messages: list[ChatCompletionMessageParam] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question},
    ]
    answer = str(llm_client.chat(messages))

    # Collect unique sources from trusted chunks
    sources = list(dict.fromkeys(c["source"] for c in trusted_chunks))

    return {
        "answer": answer,
        "sources": sources,
        "trusted_chunks": trusted_chunks,
        "defense_results": defense_results,
        "filtered_count": filtered_count,
    }
