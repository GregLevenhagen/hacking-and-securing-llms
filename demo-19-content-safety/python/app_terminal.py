"""Interactive terminal demo for Azure Content Safety text harm detection.

Shows side-by-side comparison of a vulnerable chatbot (no filtering)
vs a defended chatbot (with Azure Content Safety analyze_text scanning).

Modes:
  (default)      Run all harmful prompts from attacks/harmful_prompts.json
  --interactive  Live prompt input: type your own messages for real-time analysis
  --bulk FILE    Process a JSON prompt file and write results to stdout as JSON
"""

import json
import sys
from pathlib import Path
from typing import Any

_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root))

from shared.python.ollama_client import OllamaClient, OllamaClientError  # noqa: E402
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

from demo19_vulnerable_app import VulnerableChatbot  # noqa: E402
from demo19_defended_app import DefendedChatbot  # noqa: E402


SEVERITY_COLORS = {
    0: "green",
    1: "green",
    2: "yellow",
    3: "yellow",
    4: "red",
    5: "red",
    6: "bold red",
    7: "bold red",
}


def load_prompts() -> list[dict[str, str]]:
    """Load harmful prompts from JSON file."""
    path = Path(__file__).resolve().parent.parent / "attacks" / "harmful_prompts.json"
    with open(path) as f:
        return json.load(f)


def severity_bar(severity: int, width: int = 10) -> str:
    """Render a colored bar for severity (0-7 scale).

    Example: ``[████░░░░░░] 4/7 (Medium)``
    """
    filled = round(severity / 7 * width)
    empty = width - filled
    color = SEVERITY_COLORS.get(severity, "white")
    labels = {0: "Safe", 1: "Low", 2: "Low", 3: "Medium", 4: "Medium", 5: "High", 6: "High", 7: "Critical"}
    label = labels.get(severity, "Unknown")
    bar = "█" * filled + "░" * empty
    return f"[{color}][{bar}] {severity}/7 ({label})[/{color}]"


def format_severity(severity: int) -> str:
    """Format severity score with color coding."""
    color = SEVERITY_COLORS.get(severity, "white")
    labels = {0: "Safe", 1: "Low", 2: "Low", 3: "Medium", 4: "Medium", 5: "High", 6: "High", 7: "Critical"}
    label = labels.get(severity, "Unknown")
    return f"[{color}]{severity}/7 ({label})[/{color}]"


def format_categories(categories: dict[str, Any]) -> str:
    """Format category results with severity bars."""
    parts = []
    for cat, result in categories.items():
        sev = result.get("severity", 0)
        parts.append(f"  {cat:10s} {severity_bar(sev)}")
    return "\n".join(parts) if parts else "  (no categories)"


@trace_demo("Content Safety", demo_id="demo-19", category="azure-defense")
def run_demo(client: Any = None, safety_client: Any = None) -> None:
    """Run the side-by-side comparison demo."""
    print_banner("Demo 19: Azure Content Safety — Text Harm Detection")

    prompts = load_prompts()
    vuln = VulnerableChatbot(client=client)
    defended = DefendedChatbot(client=client, safety_client=safety_client)

    console.print(f"\n[info]Loaded {len(prompts)} harmful prompts across 4 categories[/info]")
    console.print("[dim]Each prompt is sent to both vulnerable and defended chatbots[/dim]\n")

    for i, prompt_info in enumerate(prompts):
        print_separator(
            f"[{i+1}/{len(prompts)}] {prompt_info['name']} "
            f"(Expected: {prompt_info['expected_severity']})"
        )
        console.print(f"[dim]Payload: {prompt_info['payload'][:80]}...[/dim]\n")

        try:
            vuln_result = vuln.send(prompt_info["payload"])
            defended_result = defended.send(prompt_info["payload"])

            # Build display text
            vuln_text = vuln_result["response"][:200]
            if vuln_result.get("blocked"):
                vuln_text = f"[red]{vuln_text}[/red]"

            defended_text = defended_result["response"][:200]
            if defended_result.get("blocked"):
                defended_text = f"[green]{defended_text}[/green]"
                blocked_at = defended_result.get("blocked_at", "unknown")
                defended_text += f"\n\n[dim]Blocked at: {blocked_at}[/dim]"

            # Show category details for defended
            if defended_result.get("categories"):
                defended_text += "\n\n[bold]Category Scores:[/bold]\n"
                defended_text += format_categories(defended_result["categories"])

            side_by_side(
                vuln_text,
                defended_text,
                left_title="Vulnerable (No Filter)",
                right_title="Defended (Azure Content Safety)",
            )

        except OllamaClientError as e:
            console.print(f"[bold red]LLM Error: {e}[/bold red]")
        except Exception as e:
            console.print(f"[bold red]Error: {e}[/bold red]")

        if i < len(prompts) - 1 and not confirm_proceed():
            break

    console.print("\n[system]Demo complete.[/system]")


@trace_demo("Content Safety Interactive", demo_id="demo-19-interactive", category="azure-defense")
def run_interactive(client: Any = None, safety_client: Any = None) -> None:
    """Interactive mode: type your own prompts for real-time analysis."""
    print_banner("Demo 19: Azure Content Safety — Interactive Mode")
    console.print("[dim]Type a message and press Enter to analyze it. Type 'quit' to exit.[/dim]\n")

    defended = DefendedChatbot(client=client, safety_client=safety_client)

    while True:
        try:
            user_input = console.input("[bold cyan]>>> [/bold cyan]").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not user_input or user_input.lower() in ("quit", "exit", "q"):
            break

        result = defended.send(user_input)
        if result["blocked"]:
            console.print(f"[red]BLOCKED at {result.get('blocked_at', 'unknown')}[/red]")
        else:
            console.print(f"[green]ALLOWED[/green] — {result['response'][:200]}")

        if result.get("categories"):
            console.print("[bold]Category Scores:[/bold]")
            console.print(format_categories(result["categories"]))
        console.print()

    console.print("[system]Interactive mode ended.[/system]")


def run_bulk(file_path: str, client: Any = None, safety_client: Any = None) -> None:
    """Bulk mode: process a JSON prompt file and output results as JSON."""
    path = Path(file_path)
    if not path.exists():
        print(json.dumps({"error": f"File not found: {file_path}"}))
        sys.exit(1)

    with open(path) as f:
        prompts = json.load(f)

    defended = DefendedChatbot(client=client, safety_client=safety_client)
    results = []
    for prompt_info in prompts:
        payload = prompt_info.get("payload", prompt_info.get("text", ""))
        result = defended.send(payload)
        results.append({
            "name": prompt_info.get("name", "unnamed"),
            "payload": payload[:100],
            "blocked": result["blocked"],
            "blocked_at": result.get("blocked_at"),
            "categories": result.get("categories", {}),
        })

    print(json.dumps(results, indent=2))


def main() -> None:
    """Entry point."""
    # Try to create Azure Content Safety client
    safety_client = None
    try:
        from shared.python.azure_client import AzureContentSafetyClient
        safety_client = AzureContentSafetyClient()
        console.print("[green]Azure Content Safety connected.[/green]")
    except Exception as e:
        console.print(f"[yellow]Azure Content Safety not available: {e}[/yellow]")
        console.print("[dim]Running with mock safety client for demonstration.[/dim]")
        from shared.python.testing.mock_azure import MockContentSafetyClient
        safety_client = MockContentSafetyClient(
            analyze_text_responses={
                r"slur|racial|ethnic": {
                    "Hate": {"severity": 6, "flagged": True},
                    "Violence": {"severity": 0, "flagged": False},
                    "Sexual": {"severity": 0, "flagged": False},
                    "SelfHarm": {"severity": 0, "flagged": False},
                },
                r"weapon|explosive|bomb": {
                    "Hate": {"severity": 0, "flagged": False},
                    "Violence": {"severity": 6, "flagged": True},
                    "Sexual": {"severity": 0, "flagged": False},
                    "SelfHarm": {"severity": 0, "flagged": False},
                },
                r"explicit|sexual|harass": {
                    "Hate": {"severity": 0, "flagged": False},
                    "Violence": {"severity": 0, "flagged": False},
                    "Sexual": {"severity": 6, "flagged": True},
                    "SelfHarm": {"severity": 0, "flagged": False},
                },
                r"suicide|self.harm|eating disorder": {
                    "Hate": {"severity": 0, "flagged": False},
                    "Violence": {"severity": 0, "flagged": False},
                    "Sexual": {"severity": 0, "flagged": False},
                    "SelfHarm": {"severity": 6, "flagged": True},
                },
            },
        )

    # Parse CLI flags
    if "--interactive" in sys.argv:
        run_interactive(safety_client=safety_client)
    elif "--bulk" in sys.argv:
        idx = sys.argv.index("--bulk")
        if idx + 1 < len(sys.argv):
            run_bulk(sys.argv[idx + 1], safety_client=safety_client)
        else:
            print("Usage: python app_terminal.py --bulk <file.json>")
            sys.exit(1)
    else:
        run_demo(safety_client=safety_client)


if __name__ == "__main__":
    try:
        main()
    finally:
        flush_telemetry()
