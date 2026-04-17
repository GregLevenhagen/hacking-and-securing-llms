"""Interactive terminal demo for Azure Custom Content Categories."""

import json
import sys
from pathlib import Path
from typing import Any

_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root))

from shared.python.ui_helpers import (  # noqa: E402
    console,
    confirm_proceed,
    print_banner,
    print_separator,
    side_by_side,
)

try:
    from shared.python.telemetry import init_telemetry, flush_telemetry, trace_demo
    init_telemetry()
except Exception:
    flush_telemetry = lambda: None  # noqa: E731
    trace_demo = lambda *a, **kw: (lambda fn: fn)  # noqa: E731

from standard_scanner import StandardScanner  # noqa: E402
from rapid_scanner import RapidScanner  # noqa: E402


def load_categories() -> list[dict[str, Any]]:
    """Load all category definitions."""
    cat_dir = Path(__file__).resolve().parent.parent / "categories"
    categories = []
    for cat_file in sorted(cat_dir.glob("*.json")):
        with open(cat_file) as f:
            categories.append(json.load(f))
    return categories


@trace_demo("Custom Content Categories", demo_id="demo-23", category="azure-defense")
def run_demo(safety_client: Any = None) -> None:
    print_banner("Demo 23: Custom Content Categories — Domain-Specific Moderation")

    categories = load_categories()
    standard = StandardScanner(safety_client=safety_client)
    rapid = RapidScanner(safety_client=safety_client)

    console.print(f"\n[info]Loaded {len(categories)} custom categories[/info]\n")

    for cat in categories:
        print_separator(f"Category: {cat['display_name']}")
        console.print(f"[dim]{cat['description'][:100]}...[/dim]\n")

        # Test positive examples
        console.print("[bold]Testing positive examples (should detect):[/bold]")
        for example in cat["examples"][:3]:
            std_result = standard.scan(example, cat["category_name"])
            rapid_result = rapid.scan(example, cat["category_name"])

            std_status = "[red]DETECTED[/red]" if std_result["detected"] else "[green]clean[/green]"
            rapid_status = "[red]DETECTED[/red]" if rapid_result["detected"] else "[green]clean[/green]"

            console.print(f"  Standard: {std_status} | Rapid: {rapid_status}")
            console.print(f"  [dim]{example[:60]}...[/dim]")

        # Test negative examples
        console.print("\n[bold]Testing counter-examples (should pass):[/bold]")
        for example in cat["counter_examples"][:3]:
            std_result = standard.scan(example, cat["category_name"])
            rapid_result = rapid.scan(example, cat["category_name"])

            std_status = "[red]DETECTED[/red]" if std_result["detected"] else "[green]clean[/green]"
            rapid_status = "[red]DETECTED[/red]" if rapid_result["detected"] else "[green]clean[/green]"

            console.print(f"  Standard: {std_status} | Rapid: {rapid_status}")
            console.print(f"  [dim]{example[:60]}...[/dim]")

        if not confirm_proceed():
            break

    console.print("\n[system]Demo complete.[/system]")


def main() -> None:
    safety_client = None
    try:
        from shared.python.azure_client import AzureContentSafetyClient
        safety_client = AzureContentSafetyClient()
        console.print("[green]Azure Custom Categories connected.[/green]")
    except Exception as e:
        console.print(f"[yellow]Azure not available: {e}[/yellow]")
        from shared.python.testing.mock_azure import MockContentSafetyClient
        safety_client = MockContentSafetyClient(
            custom_category_responses={
                r"pump.and.dump|fake invoices|shell companies|Ponzi|bank credentials": {
                    "detected": True, "confidence": 0.91,
                },
                r"Google Cloud|AWS|Azure|Competitor|switch to": {
                    "detected": True, "confidence": 0.85,
                },
                r"SSN|credit card|medical record|123-45|4111": {
                    "detected": True, "confidence": 0.95,
                },
            },
        )

    run_demo(safety_client=safety_client)


if __name__ == "__main__":
    try:
        main()
    finally:
        flush_telemetry()
