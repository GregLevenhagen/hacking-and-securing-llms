"""Interactive terminal demo for APIM AI Gateway governance.

Compares unprotected direct LLM access with APIM-governed access under
burst traffic, showing how rate limiting and semantic caching prevent
abuse and reduce costs.
"""

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root))

# Add demo python dir for local imports
_demo_python = Path(__file__).resolve().parent
if str(_demo_python) not in sys.path:
    sys.path.insert(0, str(_demo_python))

from shared.python.ui_helpers import (  # noqa: E402
    console,
    confirm_proceed,
    print_banner,
    print_separator,
    side_by_side,
)

# OTel telemetry (no-op when OTEL_ENABLED=false or packages missing)
try:
    from shared.python.telemetry import init_telemetry, flush_telemetry, trace_demo
    init_telemetry()
except Exception:
    flush_telemetry = lambda: None  # noqa: E731
    trace_demo = lambda *a, **kw: (lambda fn: fn)  # noqa: E731

from without_apim import DirectClient  # noqa: E402
from with_apim import APIMClient  # noqa: E402
from burst_test import run_burst  # noqa: E402


BURST_SIZE = 20
TOKEN_BUDGET = 1000
TOKENS_PER_CALL = 150


def _format_burst_results(counters: dict[str, int], label: str) -> str:
    """Format burst test results for panel display."""
    lines = [f"[bold]{label}[/bold]\n"]
    lines.append(f"Total requests: {counters['total']}")

    accepted = counters["accepted"]
    throttled = counters["throttled"]
    cached = counters["cached"]

    lines.append(f"[green]Accepted (new):[/green] {accepted}")
    lines.append(f"[yellow]Cached:[/yellow] {cached}")
    lines.append(f"[red]Throttled (429):[/red] {throttled}")

    # Cost estimate (simplified: each new call = $0.002)
    cost_per_call = 0.002
    actual_llm_calls = accepted  # cached and throttled don't call the LLM
    estimated_cost = actual_llm_calls * cost_per_call
    lines.append(f"\n[bold]Backend LLM calls:[/bold] {actual_llm_calls}")
    lines.append(f"[bold]Estimated cost:[/bold] ${estimated_cost:.4f}")

    return "\n".join(lines)


@trace_demo("APIM AI Gateway", demo_id="demo-28", category="azure-defense")
def run_demo() -> None:
    """Run the side-by-side comparison demo."""
    print_banner("Demo 28: APIM AI Gateway — Rate Limiting & Semantic Caching")

    console.print(
        "\n[attack]Without APIM: No rate limits, no caching — every request hits the LLM backend.[/attack]\n"
        "[dim]This demo sends a burst of {n} requests and compares unprotected vs APIM-governed access.[/dim]\n".format(
            n=BURST_SIZE
        )
    )

    from shared.python.testing.mock_ollama import MockOllamaClient
    client = MockOllamaClient(
        default_response="Paris is the capital of France."
    )

    # ── Phase 1: Unprotected burst ───────────────────────────────────
    print_separator(f"Burst Test: {BURST_SIZE} Rapid Requests")

    direct = DirectClient(client=client)
    direct_results = run_burst(direct, n_requests=BURST_SIZE)

    # ── Phase 2: APIM-protected burst ────────────────────────────────
    apim = APIMClient(
        client=client,
        token_budget=TOKEN_BUDGET,
        tokens_per_call=TOKENS_PER_CALL,
    )
    apim_results = run_burst(apim, n_requests=BURST_SIZE)

    # ── Side-by-side comparison ──────────────────────────────────────
    direct_text = _format_burst_results(direct_results, "Direct LLM Access (No APIM)")
    apim_text = _format_burst_results(apim_results, "APIM AI Gateway Protected")

    side_by_side(
        direct_text,
        apim_text,
        left_title="Unprotected",
        right_title="APIM Gateway",
    )

    # ── Explanation ──────────────────────────────────────────────────
    print_separator("Key Takeaways")
    console.print("[attack]Without APIM:[/attack]")
    console.print("  - All {n} requests hit the backend LLM".format(n=BURST_SIZE))
    console.print("  - No cost controls, no abuse prevention")
    console.print("  - Denial-of-wallet risk from burst traffic\n")

    console.print("[defense]With APIM AI Gateway:[/defense]")
    console.print("  - [bold]Rate limiting[/bold]: Token budget of {b} prevents runaway costs".format(b=TOKEN_BUDGET))
    console.print("  - [bold]Semantic caching[/bold]: Repeated/similar queries served from cache")
    console.print("  - [bold]Content safety[/bold]: APIM policies can screen prompts before they reach the LLM")
    console.print(f"  - Backend LLM calls reduced from {direct_results['accepted']} to {apim_results['accepted']}")

    console.print("\n[system]Demo complete.[/system]")


def main() -> None:
    """Entry point."""
    run_demo()


if __name__ == "__main__":
    try:
        main()
    finally:
        flush_telemetry()
