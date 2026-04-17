"""RAG Defense comparison demo: undefended vs defended RAG.

Shows the same poisoned RAG system queried with and without defense
layers active. The undefended system returns corrupted answers from
the poisoned document; the defended system filters it out.
"""

import sys
from pathlib import Path

# Add project root to path for shared imports
_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root))

# Add Demo 3's python directory for RAG imports
_demo3_python = _project_root / "demo-03-rag-poisoning" / "python"
sys.path.insert(0, str(_demo3_python))

from shared.python.ui_helpers import (  # noqa: E402
    confirm_proceed,
    console,
    print_attack,
    print_banner,
    print_defense,
    side_by_side,
)

from build_index import build_index  # noqa: E402  (Demo 3)
from poison_index import poison_index  # noqa: E402  (Demo 3)
from query_rag import query_rag  # noqa: E402  (Demo 3)

from demo07_defended_rag import query_defended_rag  # noqa: E402  (Demo 7)

# OTel telemetry (no-op when OTEL_ENABLED=false or packages missing)
try:
    from shared.python.telemetry import init_telemetry, flush_telemetry, trace_demo
    init_telemetry()
except Exception:
    flush_telemetry = lambda: None  # noqa: E731
    trace_demo = lambda *a, **kw: (lambda fn: fn)  # noqa: E731

# Queries that target the poisoned refund policy content
DEFAULT_QUERIES = [
    "What is the refund policy?",
    "How do I get a refund for my product?",
    "Can I return a custom-configured product?",
]


def format_undefended_result(result: dict) -> str:
    """Format an undefended RAG query result for display."""
    lines: list[str] = []
    lines.append(result["answer"])
    lines.append("")
    lines.append("Sources:")
    for source in result["sources"]:
        lines.append(f"  - {source}")
    return "\n".join(lines)


def format_defended_result(result: dict) -> str:
    """Format a defended RAG query result for display."""
    lines: list[str] = []
    lines.append(result["answer"])
    lines.append("")
    lines.append("Sources:")
    for source in result["sources"]:
        lines.append(f"  - {source}")
    lines.append("")
    lines.append(f"Filtered: {result['filtered_count']} untrusted chunk(s)")
    return "\n".join(lines)


def format_defense_verdicts(defense_results: list[dict]) -> str:
    """Format defense layer verdicts for each chunk with timing."""
    lines: list[str] = []
    for dr in defense_results:
        chunk = dr["chunk"]
        source = chunk["source"]
        passed = dr["passed"]
        status = "TRUSTED" if passed else "FILTERED"
        total_ms = dr.get("total_latency_ms", 0.0)

        lines.append(f"  [{status}] {source} ({total_ms:.1f}ms total)")
        for verdict in dr["verdicts"]:
            icon = "+" if verdict["trusted"] else "X"
            v_ms = verdict.get("latency_ms", 0.0)
            timing = f"({v_ms:.1f}ms)" if v_ms > 0 else ""
            lines.append(
                f"    [{icon}] {verdict['layer']} {timing}: {verdict['reason']} "
                f"(score: {verdict['score']:.2f})"
            )
    return "\n".join(lines)


@trace_demo("RAG Defense", demo_id="demo-07", category="defense")
def run_demo(auto: bool = False) -> None:
    """Run the RAG Defense comparison demo."""
    print_banner("RAG Defense -- Defense in Depth")

    # Phase 1: Build clean index then poison it
    console.print("[heading]PHASE 1: Building Poisoned RAG Index[/heading]\n")
    console.print("[info]Building clean index from legitimate documents...[/info]")
    build_index()
    console.print("[info]Injecting poisoned document...[/info]")
    poisoned_collection = poison_index()
    console.print(
        f"  [attack]Poisoned index ready:[/attack] "
        f"{poisoned_collection.count()} chunks (including poison)\n"
    )

    if not auto:
        confirm_proceed("Ready to compare undefended vs defended RAG?")

    # Phase 2: Query both systems
    for i, query in enumerate(DEFAULT_QUERIES):
        console.print(
            f"[heading]QUERY {i + 1}: {query}[/heading]\n"
        )

        # Undefended query (Demo 3 style — no filtering)
        console.print("[attack]Querying UNDEFENDED RAG...[/attack]")
        undefended_result = query_rag(query, poisoned_collection)

        # Defended query (with all four defense layers)
        console.print("[defense]Querying DEFENDED RAG...[/defense]")
        defended_result = query_defended_rag(
            query, poisoned_collection
        )

        # Show defense verdicts for each chunk
        console.print("\n[heading]Defense Layer Verdicts:[/heading]")
        console.print(format_defense_verdicts(defended_result["defense_results"]))
        console.print()

        # Side-by-side comparison
        side_by_side(
            format_undefended_result(undefended_result),
            format_defended_result(defended_result),
            left_title="UNDEFENDED (POISONED)",
            right_title="DEFENDED (FILTERED)",
        )

        if not auto and i < len(DEFAULT_QUERIES) - 1:
            confirm_proceed("Next query?")

    # Summary
    console.print("[heading]KEY TAKEAWAYS[/heading]\n")
    print_defense(
        "Defense in depth: four layers work together to filter poison.\n\n"
        "1. SOURCE VERIFIER — flags documents from untrusted paths\n"
        "2. DOCUMENT VALIDATOR — checks metadata (author, date, source)\n"
        "3. INJECTION DETECTOR — scans for prompt injection patterns\n"
        "4. RELEVANCE SCORER — dowranks off-topic / suspicious chunks\n\n"
        "No single layer is perfect, but the combination catches\n"
        "poisoned documents that any individual layer might miss."
    )

    print_attack(
        "Without defenses, a single poisoned document overrides\n"
        "correct answers and can exfiltrate data to attacker URLs."
    )


if __name__ == "__main__":
    try:
        from shared.python.ollama_client import OllamaClient  # noqa: E402

        client = OllamaClient()
        if not client.health_check():
            console.print(
                "[bold red]ERROR:[/bold red] Cannot connect to Ollama. "
                "Ensure Ollama is running and the model is pulled.\n"
                "See SETUP.md for instructions."
            )
            sys.exit(1)

        auto_mode = "--auto" in sys.argv
        run_demo(auto=auto_mode)
    finally:
        flush_telemetry()
