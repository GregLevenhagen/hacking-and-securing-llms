"""Terminal demo for Demo 11 — Model Denial of Service.

Runs all four DoS attack types with Rich spinners, timing display,
and a summary comparison table at the end.

Usage:
    python app_terminal.py               # interactive mode
    python app_terminal.py --auto        # non-interactive (skip pauses)
    python app_terminal.py --scenario "Token Explosion"  # single attack
"""

import sys
import time
from pathlib import Path

# Add project root to path for shared imports
_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root))

# Add demo python dir for local imports
_demo_python = Path(__file__).resolve().parent
if str(_demo_python) not in sys.path:
    sys.path.insert(0, str(_demo_python))

from shared.python.ollama_client import OllamaClient  # noqa: E402
from shared.python.ui_helpers import (  # noqa: E402
    console,
    confirm_proceed,
    print_attack,
    print_banner,
    print_message,
    print_separator,
    print_step,
    print_table,
    progress_spinner,
)

from dos_attacks import ATTACK_FUNCTIONS  # noqa: E402

# OTel telemetry (no-op when OTEL_ENABLED=false or packages missing)
try:
    from shared.python.telemetry import init_telemetry, flush_telemetry, trace_demo
    init_telemetry()
except Exception:
    flush_telemetry = lambda: None  # noqa: E731
    trace_demo = lambda *a, **kw: (lambda fn: fn)  # noqa: E731

# Scenario metadata for terminal display
SCENARIOS = [
    {
        "name": "Token Explosion",
        "description": (
            "Sends a prompt designed to trigger extremely verbose output, "
            "consuming maximum tokens and processing time."
        ),
    },
    {
        "name": "Infinite Loop",
        "description": (
            "Creates a tool-calling agent loop where each file references "
            "the next in a circular chain, trapping the agent indefinitely."
        ),
    },
    {
        "name": "Recursive Reasoning",
        "description": (
            "Sends a self-referential paradox that forces the model to spend "
            "excessive time reasoning through multiple layers of contradiction."
        ),
    },
    {
        "name": "Context Overflow",
        "description": (
            "Sends an extremely long prompt that fills the context window, "
            "forcing the model to process maximum input tokens."
        ),
    },
]


def run_dos_demo(auto: bool = False, scenario: str | None = None) -> None:
    """Run the DoS attack demonstration scenarios.

    Args:
        auto: If True, skip interactive pauses.
        scenario: If provided, run only the attack matching this name (case-insensitive).
    """
    print_banner("Model Denial of Service — Attack Scenarios")

    console.print(
        "[attack]WARNING: Demonstrating model denial-of-service vectors.[/attack]\n"
        "[dim]These attacks exploit model compute resources to cause slowdowns,[/dim]\n"
        "[dim]excessive token usage, and service degradation.[/dim]\n"
    )

    # Filter to a single scenario if requested
    if scenario:
        matching = [s for s in SCENARIOS if scenario.lower() in s["name"].lower()]
        if not matching:
            console.print(f"[bold red]No scenario matching '{scenario}'.[/bold red]")
            console.print("[dim]Available scenarios:[/dim]")
            for s in SCENARIOS:
                console.print(f"  [dim]- {s['name']}[/dim]")
            return
        scenarios_to_run = matching
    else:
        scenarios_to_run = SCENARIOS

    # Initialize the Ollama client
    try:
        client = OllamaClient()
    except Exception as e:
        console.print(f"[bold red]Error connecting to Ollama: {e}[/bold red]")
        console.print("[dim]Is Ollama running? Try: ollama serve[/dim]")
        return

    results: list[dict] = []

    for i, scenario_info in enumerate(scenarios_to_run, 1):
        name = scenario_info["name"]
        attack_fn = ATTACK_FUNCTIONS.get(name)

        if attack_fn is None:
            console.print(f"[bold red]Unknown attack: {name}[/bold red]")
            continue

        print_separator(f"Attack {i}/{len(scenarios_to_run)}")
        print_step(i, len(scenarios_to_run), name)
        print_attack(scenario_info["description"])

        # Show the prompt that will be sent
        console.print("[info]Executing attack...[/info]")

        with progress_spinner(f"Running {name}..."):
            result = attack_fn(client)

        results.append(result)

        # Display results
        print_message("system", f"Attack: {result['attack_name']}")

        # Show metrics
        console.print(f"  [info]Status        : [/info][bold]{result['status']}[/bold]")
        console.print(f"  [info]Tokens used   : [/info][bold]{result['token_count']:,}[/bold]")
        console.print(f"  [info]Iterations    : [/info][bold]{result['iterations']}[/bold]")
        console.print(f"  [info]Elapsed time  : [/info][bold]{result['elapsed_seconds']:.3f}s[/bold]")

        # Status-based coloring
        if result["status"] == "max_iterations_reached":
            console.print(
                "[attack]DoS DEMONSTRATED: Agent trapped in infinite loop "
                "until safety limit was reached.[/attack]"
            )
        elif result["status"] == "completed":
            console.print("[info]Attack completed — resources consumed as expected.[/info]")
        else:
            console.print(f"[warning]{result['status']}[/warning]")

        console.print()

        if not auto and i < len(scenarios_to_run):
            if not confirm_proceed("Continue to next attack?"):
                break

    # Summary table
    if results:
        print_separator("Summary")
        headers = ["Attack", "Status", "Tokens", "Iterations", "Time (s)"]
        rows = []
        for r in results:
            status_str = r["status"]
            if status_str == "max_iterations_reached":
                status_str = "DoS (loop limit)"
            rows.append([
                r["attack_name"],
                status_str,
                f"{r['token_count']:,}",
                str(r["iterations"]),
                f"{r['elapsed_seconds']:.3f}",
            ])
        print_table(headers, rows, title="DoS Attack Results")

        total_tokens = sum(r["token_count"] for r in results)
        total_time = sum(r["elapsed_seconds"] for r in results)
        console.print(f"[info]Total tokens consumed: {total_tokens:,}[/info]")
        console.print(f"[info]Total wall-clock time: {total_time:.3f}s[/info]")

    console.print("\n[attack]All DoS attacks demonstrated resource exhaustion.[/attack]")
    console.print("[defense]Mitigations include:[/defense]")
    console.print("[dim]  - Token budget limits per request[/dim]")
    console.print("[dim]  - Iteration caps on agent loops[/dim]")
    console.print("[dim]  - Input length validation[/dim]")
    console.print("[dim]  - Rate limiting and timeout enforcement[/dim]\n")


@trace_demo("Model Denial of Service", demo_id="demo-11", category="attack")
def main() -> None:
    """Entry point — run with --auto for non-interactive, --scenario NAME for a single attack."""
    auto = "--auto" in sys.argv
    scenario: str | None = None
    for i, arg in enumerate(sys.argv):
        if arg == "--scenario" and i + 1 < len(sys.argv):
            scenario = sys.argv[i + 1]
    run_dos_demo(auto=auto, scenario=scenario)


if __name__ == "__main__":
    try:
        main()
    finally:
        flush_telemetry()
