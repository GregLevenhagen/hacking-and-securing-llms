"""Full RAG Poisoning demo: clean baseline vs poisoned comparison.

Orchestrates the complete demo flow:
1. Build a clean ChromaDB index from legitimate documents
2. Query the RAG system (clean results)
3. Inject the poisoned document into the index
4. Re-run the same query (poisoned results)
5. Display side-by-side comparison with retrieval analysis
"""

import re
import sys
from pathlib import Path
from typing import Any

# Add project root to path for shared imports
_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root))

from rich.text import Text  # noqa: E402

from shared.python.ui_helpers import (  # noqa: E402
    confirm_proceed,
    console,
    print_attack,
    print_banner,
    print_defense,
    side_by_side,
)

from build_index import build_index  # noqa: E402
from poison_index import poison_index  # noqa: E402
from query_rag import (  # noqa: E402
    INJECTION_PATTERNS,
    detect_injection,
    query_rag,
)

# OTel telemetry (no-op when OTEL_ENABLED=false or packages missing)
try:
    from shared.python.telemetry import init_telemetry, flush_telemetry, trace_demo
    init_telemetry()
except Exception:
    flush_telemetry = lambda: None  # noqa: E731
    trace_demo = lambda *a, **kw: (lambda fn: fn)  # noqa: E731

# Default queries that demonstrate the poisoning effect
DEFAULT_QUERIES = [
    "What is the refund policy?",
    "How do I get a refund for my product?",
    "Can I return a custom-configured product?",
]

# Marker for detecting poisoned sources in retrieval results
POISONED_SOURCE = "poisoned_policy.txt"


def format_result(result: dict[str, Any]) -> str:
    """Format a RAG query result for display."""
    lines: list[str] = []
    lines.append(result["answer"])
    lines.append("")
    lines.append("Sources:")
    for source in result["sources"]:
        lines.append(f"  - {source}")
    return "\n".join(lines)


def highlight_injection(chunk_text: str) -> Text:
    """Return a Rich Text with injection-matched spans highlighted in red.

    Non-matching text is rendered dim, matched spans are bold red.
    """
    text = Text(chunk_text)
    text.stylize("dim")
    text_lower = chunk_text.lower()
    for pattern in INJECTION_PATTERNS:
        for match in re.finditer(pattern, text_lower):
            text.stylize("bold red", match.start(), match.end())
    return text


def format_retrieval_detail(chunks: list[dict[str, Any]]) -> str:
    """Format retrieval chunk details showing distances and poisoned flags."""
    lines: list[str] = []
    for i, chunk in enumerate(chunks, 1):
        source = chunk["source"]
        distance = chunk["distance"]
        is_poisoned = POISONED_SOURCE in source
        flag = " [POISONED]" if is_poisoned else ""
        lines.append(f"  {i}. {source} (distance: {distance:.4f}){flag}")
    return "\n".join(lines)


@trace_demo("RAG Poisoning", demo_id="demo-03", category="attack")
def run_demo(auto: bool = False) -> None:
    """Run the full RAG poisoning demo."""
    print_banner("RAG Poisoning -- Full Demo")

    # Step 1: Build clean index
    console.print("[heading]PHASE 1: Building Clean Index[/heading]\n")
    console.print("[info]Indexing legitimate company documents...[/info]")
    try:
        clean_collection = build_index()
    except Exception as e:
        console.print(f"[bold red]Error building index: {e}[/bold red]")
        console.print("[dim]Is Ollama running? Try: ollama serve[/dim]")
        return

    clean_count = clean_collection.count()
    console.print(
        f"  [system]Clean index built:[/system] "
        f"{clean_count} chunks indexed\n"
    )

    if not auto:
        confirm_proceed("Ready to query the clean RAG system?")

    # Step 2: Query clean index
    console.print("[heading]PHASE 2: Querying Clean RAG System[/heading]\n")

    clean_results: list[dict[str, Any]] = []
    for query in DEFAULT_QUERIES:
        console.print(f"[user]Query:[/user] {query}")
        try:
            result = query_rag(query, clean_collection)
        except Exception as e:
            console.print(f"[bold red]Error querying: {e}[/bold red]")
            return
        clean_results.append(result)
        console.print(f"[assistant]{result['answer']}[/assistant]")
        console.print(
            f"  [dim]Sources: {', '.join(result['sources'])}[/dim]"
        )
        console.print(f"[dim]{format_retrieval_detail(result['chunks'])}[/dim]\n")

    if not auto:
        confirm_proceed("Ready to inject the poisoned document?")

    # Step 3: Poison the index
    console.print("[heading]PHASE 3: Injecting Poisoned Document[/heading]\n")
    print_attack(
        "Injecting poisoned_policy.txt into the document index.\n"
        "This document mimics the legitimate refund policy but contains\n"
        "hidden instructions to redirect users to a malicious URL."
    )
    console.print()

    try:
        poisoned_collection = poison_index()
    except Exception as e:
        console.print(f"[bold red]Error poisoning index: {e}[/bold red]")
        return

    poisoned_count = poisoned_collection.count()
    console.print(
        f"  [attack]Index poisoned:[/attack] "
        f"{poisoned_count} chunks total "
        f"({poisoned_count - clean_count} poisoned chunks injected)\n"
    )

    if not auto:
        confirm_proceed("Ready to see the poisoned results?")

    # Step 4: Query poisoned index with the same questions
    console.print("[heading]PHASE 4: Querying Poisoned RAG System[/heading]\n")

    poisoned_results: list[dict[str, Any]] = []
    for query in DEFAULT_QUERIES:
        console.print(f"[user]Query:[/user] {query}")
        try:
            result = query_rag(query, poisoned_collection)
        except Exception as e:
            console.print(f"[bold red]Error querying: {e}[/bold red]")
            return
        poisoned_results.append(result)
        console.print(f"[attack]{result['answer']}[/attack]")
        console.print(
            f"  [dim]Sources: {', '.join(result['sources'])}[/dim]"
        )
        # Show retrieval detail with poisoned source flagging
        console.print(f"[dim]{format_retrieval_detail(result['chunks'])}[/dim]\n")

    if not auto:
        confirm_proceed("Ready to see the side-by-side comparison?")

    # Step 5: Side-by-side comparison
    console.print("[heading]PHASE 5: Side-by-Side Comparison[/heading]\n")

    for i, query in enumerate(DEFAULT_QUERIES):
        console.print(f"[bold #ffb000]Query: {query}[/bold #ffb000]")
        side_by_side(
            format_result(clean_results[i]),
            format_result(poisoned_results[i]),
            left_title="CLEAN RAG",
            right_title="POISONED RAG",
        )

    # Retrieval analysis summary
    console.print("[heading]RETRIEVAL ANALYSIS[/heading]\n")
    for i, query in enumerate(DEFAULT_QUERIES):
        console.print(f"[bold #ffb000]Query: {query}[/bold #ffb000]")
        poisoned_chunks = poisoned_results[i]["chunks"]
        poisoned_in_top_k = sum(
            1 for c in poisoned_chunks if POISONED_SOURCE in c["source"]
        )
        total_chunks = len(poisoned_chunks)
        if poisoned_in_top_k > 0:
            console.print(
                f"  [attack]Poisoned document appeared in {poisoned_in_top_k}/{total_chunks} "
                f"retrieved chunks[/attack]"
            )
            for c in poisoned_chunks:
                if POISONED_SOURCE in c["source"]:
                    console.print(
                        f"    [attack]> {c['source']} at distance {c['distance']:.4f}[/attack]"
                    )
        else:
            console.print(
                f"  [defense]Poisoned document NOT in top-{total_chunks} results[/defense]"
            )

        # Injection pattern detection on retrieved chunks with text highlighting
        for c in poisoned_chunks:
            matches = detect_injection(c["content"])
            if matches:
                console.print(
                    f"  [attack]INJECTION DETECTED in chunk from {c['source']}:[/attack]"
                )
                for m in matches:
                    console.print(f"    [dim]matched pattern: {m}[/dim]")
                # Show the chunk text with matched spans highlighted
                highlighted = highlight_injection(c["content"])
                console.print("    ", end="")
                console.print(highlighted)
        console.print()

    # Summary
    console.print("[heading]KEY TAKEAWAYS[/heading]\n")
    print_defense(
        "RAG systems implicitly trust retrieved documents.\n"
        "A single poisoned document can override correct answers.\n"
        "The LLM follows injected instructions because they appear\n"
        "in the 'trusted' context window alongside legitimate content.\n\n"
        "Defenses: document validation, source verification,\n"
        "injection detection, relevance scoring (see Demo 7)."
    )


if __name__ == "__main__":
    try:
        auto_mode = "--auto" in sys.argv
        run_demo(auto=auto_mode)
    finally:
        flush_telemetry()
