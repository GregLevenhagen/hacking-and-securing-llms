"""Interactive terminal demo for Azure OpenAI Content Filters."""

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
)

try:
    from shared.python.telemetry import init_telemetry, flush_telemetry, trace_demo
    init_telemetry()
except Exception:
    flush_telemetry = lambda: None  # noqa: E731
    trace_demo = lambda *a, **kw: (lambda fn: fn)  # noqa: E731

from filter_demo import FilterResultParser  # noqa: E402
from filter_config_compare import FilterConfigComparer, FILTER_CONFIGS  # noqa: E402


def load_prompts() -> list[dict[str, str]]:
    path = Path(__file__).resolve().parent.parent / "attacks" / "filter_test_prompts.json"
    with open(path) as f:
        return json.load(f)


@trace_demo("Azure OpenAI Content Filters", demo_id="demo-25", category="azure-defense")
def run_demo(azure_openai_client: Any = None) -> None:
    print_banner("Demo 25: Azure OpenAI Content Filters — Integrated Defense Pipeline")

    prompts = load_prompts()
    parser = FilterResultParser(azure_openai_client=azure_openai_client)
    comparer = FilterConfigComparer(azure_openai_client=azure_openai_client)

    # Phase 1: Filter analysis
    print_separator("Phase 1: Content Filter Analysis")
    for i, p in enumerate(prompts):
        result = parser.send_and_analyze(p["payload"])
        status = "[red]BLOCKED[/red]" if result["blocked"] else "[green]passed[/green]"
        filters = ", ".join(f["category"] for f in result["filters_triggered"]) or "none"
        console.print(f"  [{i+1}] {p['name']}: {status} | Filters: {filters}")

    # Phase 2: Config comparison
    if confirm_proceed("Continue to filter configuration comparison?"):
        print_separator("Phase 2: Filter Configuration Comparison")
        test_prompt = prompts[0]["payload"]  # Use first prompt
        console.print(f"  [dim]Testing: {test_prompt[:60]}...[/dim]\n")

        results = comparer.compare_prompt(test_prompt)
        for name, result in results.items():
            config = result["config"]
            status = "[red]BLOCKED[/red]" if result["blocked"] else "[green]passed[/green]"
            console.print(f"  {config['name']}: {status}")
            console.print(f"    [dim]{config['description']}[/dim]")

    console.print("\n[system]Demo complete.[/system]")


def main() -> None:
    azure_openai_client = None
    try:
        from shared.python.azure_openai_client import AzureOpenAIClient
        azure_openai_client = AzureOpenAIClient()
        console.print("[green]Azure OpenAI connected.[/green]")
    except Exception as e:
        console.print(f"[yellow]Azure OpenAI not available: {e}[/yellow]")
        console.print("[dim]Running with mock client.[/dim]")
        from shared.python.testing.mock_azure import MockAzureOpenAIClient
        azure_openai_client = MockAzureOpenAIClient(
            content_filter_results={
                "hate": {"filtered": False, "severity": "safe"},
                "violence": {"filtered": False, "severity": "safe"},
            },
        )

    run_demo(azure_openai_client=azure_openai_client)


if __name__ == "__main__":
    try:
        main()
    finally:
        flush_telemetry()
