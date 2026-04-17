"""Terminal demo for Insecure Output Handling (XSS via LLM).

Runs all 6 XSS prompts against the LLM and displays detection results
side by side: raw (unsafe) output vs sanitized (safe) output.

Usage:
    python app_terminal.py              # interactive mode
    python app_terminal.py --auto       # automated (no pauses)
"""

import sys
from pathlib import Path
from typing import Any

# Add project root to path for shared imports
_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root))

from shared.python.ui_helpers import (  # noqa: E402
    console,
    confirm_proceed,
    print_attack,
    print_banner,
    side_by_side,
)
from shared.python.ollama_client import OllamaClient, OllamaClientError  # noqa: E402

from xss_attacks import XSS_PROMPTS, load_prompts, run_xss_attack  # noqa: E402
from output_renderer import detect_xss_patterns, sanitize_html  # noqa: E402

# OTel telemetry (no-op when OTEL_ENABLED=false or packages missing)
try:
    from shared.python.telemetry import init_telemetry, flush_telemetry, trace_demo
    init_telemetry()
except Exception:
    flush_telemetry = lambda: None  # noqa: E731
    trace_demo = lambda *a, **kw: (lambda fn: fn)  # noqa: E731


def format_unsafe_result(response: str, findings: list[dict[str, Any]]) -> str:
    """Format the unsafe (raw) result for Rich display."""
    lines: list[str] = []
    lines.append("[bold red]RAW OUTPUT — NO SANITIZATION[/bold red]\n")

    # Truncate for terminal display
    display = response[:500] if len(response) > 500 else response
    lines.append(display)

    if findings:
        lines.append(f"\n\n[bold red]⚠ {len(findings)} XSS PATTERNS DETECTED:[/bold red]")
        for f in findings:
            match_preview = f["match"][:60] + "..." if len(f["match"]) > 60 else f["match"]
            lines.append(f"  [red]• {f['name']}[/red]: {match_preview}")

    return "\n".join(lines)


def format_safe_result(sanitized: str, findings: list[dict[str, Any]]) -> str:
    """Format the safe (sanitized) result for Rich display."""
    lines: list[str] = []
    lines.append("[bold green]SANITIZED OUTPUT[/bold green]\n")

    # Truncate for terminal display
    display = sanitized[:500] if len(sanitized) > 500 else sanitized
    lines.append(display)

    if findings:
        lines.append(f"\n\n[bold green]✓ {len(findings)} PATTERNS REMOVED[/bold green]")
    else:
        lines.append("\n\n[dim]No dangerous patterns found.[/dim]")

    return "\n".join(lines)


def run_demo(client: Any = None) -> list[dict[str, Any]]:
    """Run all XSS prompts and show detection results.

    Args:
        client: Optional pre-configured OllamaClient.

    Returns:
        List of result dicts for each prompt.
    """
    if client is None:
        client = OllamaClient()

    prompts = load_prompts()
    results: list[dict[str, Any]] = []

    print_banner("Insecure Output Handling — XSS via LLM")

    console.print(
        "[info]Demonstrating how LLM-generated HTML/JS can be dangerous "
        "when rendered without sanitization.[/info]"
    )
    console.print(f"[info]Running {len(prompts)} XSS attack prompts...[/info]\n")

    for i, prompt_config in enumerate(prompts, 1):
        console.print(f"[heading]Attack {i}/{len(prompts)}[/heading]")
        print_attack(f"{prompt_config['name']}: {prompt_config['prompt'][:80]}...")

        result = run_xss_attack(client, prompt_config)
        response = result["response"]

        # Detect patterns
        findings = detect_xss_patterns(response)

        # Sanitize
        sanitized = sanitize_html(response)

        # Display side by side
        unsafe_display = format_unsafe_result(response, findings)
        safe_display = format_safe_result(sanitized, findings)

        side_by_side(
            unsafe_display,
            safe_display,
            left_title="UNSAFE",
            right_title="SAFE",
        )

        result["findings"] = findings
        result["sanitized"] = sanitized
        results.append(result)

        if "--auto" not in sys.argv and i < len(prompts):
            if not confirm_proceed("Continue to next attack?"):
                break

    # Summary
    console.print("\n[heading]SUMMARY[/heading]")
    total_findings = sum(len(r.get("findings", [])) for r in results)
    attacks_with_xss = sum(1 for r in results if r.get("findings"))
    console.print(f"[system]Total attacks: {len(results)}[/system]")
    console.print(f"[attack]Attacks producing XSS: {attacks_with_xss}/{len(results)}[/attack]")
    console.print(f"[attack]Total XSS patterns found: {total_findings}[/attack]")

    return results


@trace_demo("Insecure Output Handling", demo_id="demo-15", category="attack")
def main() -> None:
    """Entry point for the terminal demo."""
    client = OllamaClient()
    if not client.health_check():
        console.print(
            "[bold red]ERROR:[/bold red] Cannot connect to Ollama. "
            "Ensure Ollama is running and the model is pulled.\n"
            "See SETUP.md for instructions."
        )
        sys.exit(1)

    run_demo(client)


if __name__ == "__main__":
    try:
        main()
    finally:
        flush_telemetry()
