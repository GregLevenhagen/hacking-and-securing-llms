"""Query the RAG system and return answers with source citations.

Retrieves relevant chunks from ChromaDB, constructs a context-augmented
prompt, and sends it to the LLM for an answer grounded in the documents.
"""

import re
import sys
from pathlib import Path
from typing import Any

# Add project root to path for shared imports
_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root))

import chromadb  # noqa: E402
from openai.types.chat import ChatCompletionMessageParam  # noqa: E402

from shared.python.config import get_config  # noqa: E402
from shared.python.ollama_client import OllamaClient  # noqa: E402
from shared.python.ui_helpers import (  # noqa: E402
    console,
    print_banner,
    print_message,
)

from build_index import (  # noqa: E402
    CHROMA_DIR,
    COLLECTION_NAME,
    OllamaEmbeddingFunction,
)

# Number of chunks to retrieve per query
DEFAULT_TOP_K = 3

# Distance threshold — chunks with distance above this are filtered out
# (lower distance = more relevant; set to None to disable filtering)
DEFAULT_DISTANCE_THRESHOLD: float | None = None

# System prompt for RAG-augmented answering
RAG_SYSTEM_PROMPT = """You are a helpful customer service assistant for AcmeTech Corporation.
Answer questions based ONLY on the provided context documents.
If the answer is not found in the context, say "I don't have information about that in our documents."
Always cite which document(s) your answer comes from.

Context documents:
{context}"""


def get_collection(
    chroma_dir: Path | None = None,
    collection_name: str = COLLECTION_NAME,
    embedding_fn: Any = None,
) -> chromadb.Collection:
    """Get an existing ChromaDB collection."""
    storage = chroma_dir or CHROMA_DIR
    ef = embedding_fn or OllamaEmbeddingFunction()

    client = chromadb.PersistentClient(path=str(storage))
    return client.get_collection(
        name=collection_name,
        embedding_function=ef,  # type: ignore[arg-type]
    )


def retrieve_chunks(
    query: str,
    collection: chromadb.Collection,
    top_k: int = DEFAULT_TOP_K,
    distance_threshold: float | None = DEFAULT_DISTANCE_THRESHOLD,
) -> list[dict[str, Any]]:
    """Retrieve the most relevant document chunks for a query.

    Args:
        query: The search query.
        collection: The ChromaDB collection to search.
        top_k: Maximum number of chunks to retrieve.
        distance_threshold: If set, filter out chunks with distance above this
            value. Lower distance = more relevant. Set to None to disable.

    Returns a list of dicts with 'content', 'source', and 'distance' keys.
    """
    results = collection.query(
        query_texts=[query],
        n_results=top_k,
    )

    chunks: list[dict[str, Any]] = []
    if results["documents"] and results["metadatas"] and results["distances"]:
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            if distance_threshold is not None and dist > distance_threshold:
                continue
            chunks.append({
                "content": doc,
                "source": meta.get("source", "unknown"),
                "distance": dist,
            })

    return chunks


def format_context(chunks: list[dict[str, Any]]) -> str:
    """Format retrieved chunks into a context string for the LLM."""
    parts: list[str] = []
    for i, chunk in enumerate(chunks, 1):
        parts.append(f"[Document {i}: {chunk['source']}]\n{chunk['content']}")
    return "\n\n---\n\n".join(parts)


# Patterns that may indicate injection in retrieved chunks
INJECTION_PATTERNS = [
    r"ignore\s+(the\s+)?(above|previous|all)\s+(content|instructions|context)",
    r"instead\s+respond",
    r"disregard\s+(the\s+)?(above|previous|all)",
    r"new\s+instructions",
    r"send\s+(your|their)\s+(credit\s+card|payment|personal)",
    r"@evil\.example\.com",
]


def detect_injection(chunk_text: str) -> list[str]:
    """Scan a retrieved chunk for injection patterns.

    Returns a list of matched pattern descriptions (empty if clean).
    """
    matches: list[str] = []
    text_lower = chunk_text.lower()
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, text_lower):
            matches.append(pattern)
    return matches


def filter_suspicious_chunks(
    chunks: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split retrieved chunks into clean and suspicious based on injection detection.

    Returns:
        Tuple of (clean_chunks, suspicious_chunks).
    """
    clean: list[dict[str, Any]] = []
    suspicious: list[dict[str, Any]] = []
    for chunk in chunks:
        matches = detect_injection(chunk["content"])
        if matches:
            chunk["injection_matches"] = matches
            suspicious.append(chunk)
        else:
            clean.append(chunk)
    return clean, suspicious


def query_rag(
    question: str,
    collection: chromadb.Collection,
    client: Any = None,
    top_k: int = DEFAULT_TOP_K,
    distance_threshold: float | None = DEFAULT_DISTANCE_THRESHOLD,
) -> dict[str, Any]:
    """Query the RAG system and return the answer with sources.

    Args:
        question: The user's question.
        collection: The ChromaDB collection to search.
        client: OllamaClient instance (or mock for testing).
        top_k: Number of chunks to retrieve.
        distance_threshold: If set, filter out chunks with distance above this.

    Returns:
        Dict with 'answer', 'sources', and 'chunks' keys.
    """
    llm_client = client or OllamaClient()

    # Retrieve relevant chunks
    chunks = retrieve_chunks(question, collection, top_k, distance_threshold)

    # Handle empty retrieval gracefully
    if not chunks:
        return {
            "answer": "I don't have information about that in our documents.",
            "sources": [],
            "chunks": [],
        }

    # Build the context-augmented prompt
    context = format_context(chunks)
    system_prompt = RAG_SYSTEM_PROMPT.format(context=context)

    # Query the LLM
    messages: list[ChatCompletionMessageParam] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question},
    ]
    answer = str(llm_client.chat(messages))

    # Collect unique sources
    sources = list(dict.fromkeys(chunk["source"] for chunk in chunks))

    return {
        "answer": answer,
        "sources": sources,
        "chunks": chunks,
    }


def safe_query_rag(
    question: str,
    collection: chromadb.Collection,
    client: Any = None,
    top_k: int = DEFAULT_TOP_K,
    distance_threshold: float | None = DEFAULT_DISTANCE_THRESHOLD,
) -> dict[str, Any]:
    """Query the RAG system with injection filtering applied before LLM call.

    Retrieves chunks, filters out suspicious ones via detect_injection(),
    then sends only clean chunks to the LLM.

    Returns:
        Dict with 'answer', 'sources', 'chunks', 'filtered_chunks' keys.
        'filtered_chunks' contains chunks that were removed due to injection detection.
    """
    llm_client = client or OllamaClient()

    # Retrieve relevant chunks
    chunks = retrieve_chunks(question, collection, top_k, distance_threshold)

    # Filter out suspicious chunks before sending to LLM
    clean_chunks, suspicious_chunks = filter_suspicious_chunks(chunks)

    # Handle empty retrieval gracefully
    if not clean_chunks:
        return {
            "answer": "I don't have information about that in our documents.",
            "sources": [],
            "chunks": [],
            "filtered_chunks": suspicious_chunks,
        }

    # Build the context-augmented prompt from clean chunks only
    context = format_context(clean_chunks)
    system_prompt = RAG_SYSTEM_PROMPT.format(context=context)

    messages: list[ChatCompletionMessageParam] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question},
    ]
    answer = str(llm_client.chat(messages))

    sources = list(dict.fromkeys(chunk["source"] for chunk in clean_chunks))

    return {
        "answer": answer,
        "sources": sources,
        "chunks": clean_chunks,
        "filtered_chunks": suspicious_chunks,
    }


def run_interactive() -> None:
    """Run the RAG query system in interactive mode."""
    print_banner("RAG Poisoning — Query System")

    console.print("[info]Loading ChromaDB index...[/info]")
    try:
        collection = get_collection()
    except (ValueError, Exception) as e:
        console.print(f"[bold red]Error: Index not found. Run build_index.py first.[/bold red]")
        console.print(f"  [dim]{e}[/dim]")
        return

    console.print(f"  Collection: [system]{COLLECTION_NAME}[/system]")
    console.print(f"  Documents: [system]{collection.count()}[/system] chunks indexed")
    console.print("[dim]Type 'quit' to exit.\n[/dim]")

    while True:
        try:
            question = console.input("[bold #ffb000]query > [/bold #ffb000]")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[info]Goodbye.[/info]")
            break

        if not question.strip():
            continue

        if question.strip().lower() == "quit":
            break

        console.print()
        print_message("user", question)

        try:
            result = query_rag(question, collection)
        except Exception as e:
            console.print(f"[bold red]Error querying RAG: {e}[/bold red]")
            console.print("[dim]Is Ollama running? Try: ollama serve[/dim]")
            continue

        # Display the answer
        print_message("assistant", result["answer"])

        # Display source citations
        if result["sources"]:
            console.print("[dim]Sources:[/dim]")
            for source in result["sources"]:
                console.print(f"  [dim]- {source}[/dim]")
        else:
            console.print("[dim]No relevant documents found.[/dim]")

        # Display retrieval details
        if result["chunks"]:
            console.print("\n[dim]Retrieved chunks (by relevance):[/dim]")
            for chunk in result["chunks"]:
                console.print(
                    f"  [dim]{chunk['source']} "
                    f"(distance: {chunk['distance']:.4f})[/dim]"
                )
        console.print()


if __name__ == "__main__":
    run_interactive()
