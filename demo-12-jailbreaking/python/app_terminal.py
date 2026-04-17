"""Interactive terminal demo for jailbreak attack techniques.

Shows each jailbreak technique, the LLM response, and the safety
classification result revealing whether guardrails were bypassed.
"""

import sys
from pathlib import Path
from typing import Any

# Add project root to path for shared imports
_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root))

from shared.python.ollama_client import OllamaClient, OllamaClientError  # noqa: E402
from shared.python.ui_helpers import (  # noqa: E402
    console,
    confirm_proceed,
    print_attack,
    print_banner,
    print_message,
    print_separator,
)

from jailbreak_attacks import (  # noqa: E402
    JAILBREAK_TECHNIQUES,
    SYSTEM_PROMPT,
    load_techniques,
    run_attack,
)

# OTel telemetry (no-op when OTEL_ENABLED=false or packages missing)
try:
    from shared.python.telemetry import init_telemetry, flush_telemetry, trace_demo
    init_telemetry()
except Exception:
    flush_telemetry = lambda: None  # noqa: E731
    trace_demo = lambda *a, **kw: (lambda fn: fn)  # noqa: E731


def _display_classification(result: dict[str, Any]) -> None:
    """Display formatted safety classification for a single attack."""
    classification = result.get("classification", {})
    bypassed = result.get("bypassed", False)

    if bypassed:
        status = "[bold red]BYPASSED[/bold red]"
        violations = classification.get("violations", [])
        console.print(f"\n  [bold red]VERDICT: {status}[/bold red]")
        console.print(f"  [bold red]VIOLATIONS: {', '.join(violations)}[/bold red]")
    else:
        status = "[bold green]BLOCKED[/bold green]"
        console.print(f"\n  [bold green]VERDICT: {status}[/bold green]")

    confidence = classification.get("confidence", 0.0)
    refused = classification.get("refused", False)
    console.print(f"  Confidence: {confidence:.0%}")
    console.print(f"  Refused: {'Yes' if refused else 'No'}")


def run_automated() -> None:
    """Run all jailbreak techniques and show classification results."""
    print_banner("Jailbreaking \u2014 Automated Attack Suite")

    console.print(f"\n[bold cyan]SAFETY SYSTEM PROMPT:[/bold cyan]")
    console.print(f"[dim]{SYSTEM_PROMPT[:300]}...[/dim]\n")

    try:
        client = OllamaClient()
    except Exception as e:
        console.print(f"[bold red]Failed to create client: {e}[/bold red]")
        return

    techniques = load_techniques()
    total_bypassed = 0

    for i, technique in enumerate(techniques, 1):
        print_separator(
            f"Attack {i}/{len(techniques)}: {technique['name']}"
        )
        console.print(f"[dim]{technique['description']}[/dim]\n")
        print_attack(technique["prompt"])

        try:
            result = run_attack(client, technique)
        except OllamaClientError as e:
            console.print(f"[bold red]LLM Error: {e}[/bold red]")
            if not confirm_proceed("Continue to next attack?"):
                break
            continue

        # Show the LLM response (truncated for readability)
        print_message("assistant", result["response"][:1000])

        # Show classification
        _display_classification(result)

        if result["bypassed"]:
            total_bypassed += 1

        if i < len(techniques):
            if not confirm_proceed("Continue to next attack?"):
                break

    console.print(
        f"\n[system]All attacks complete: {total_bypassed}/{len(techniques)} "
        f"techniques bypassed safety guardrails[/system]"
    )


def run_single(technique_name: str) -> None:
    """Run a single jailbreak technique by name."""
    techniques = load_techniques()
    technique = next(
        (t for t in techniques if t["name"].lower() == technique_name.lower()),
        None,
    )
    if not technique:
        console.print(f"[bold red]Unknown technique: {technique_name}[/bold red]")
        console.print("[dim]Available techniques:[/dim]")
        for t in techniques:
            console.print(f"  - {t['name']}")
        return

    print_banner(f"Jailbreaking \u2014 {technique['name']}")

    console.print(f"\n[bold cyan]SAFETY SYSTEM PROMPT:[/bold cyan]")
    console.print(f"[dim]{SYSTEM_PROMPT[:300]}...[/dim]\n")

    try:
        client = OllamaClient()
    except Exception as e:
        console.print(f"[bold red]Failed to create client: {e}[/bold red]")
        return

    print_attack(technique["prompt"])

    try:
        result = run_attack(client, technique)
    except OllamaClientError as e:
        console.print(f"[bold red]LLM Error: {e}[/bold red]")
        return

    print_message("assistant", result["response"])
    _display_classification(result)


@trace_demo("Jailbreaking", demo_id="demo-12", category="attack")
def main() -> None:
    """Entry point \u2014 run automated by default, or specify a technique name."""
    if len(sys.argv) > 1 and sys.argv[1] != "--auto":
        run_single(sys.argv[1])
    else:
        run_automated()


if __name__ == "__main__":
    try:
        main()
    finally:
        flush_telemetry()
