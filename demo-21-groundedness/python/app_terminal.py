"""Interactive terminal demo for Azure Groundedness Detection.

Shows side-by-side: vulnerable RAG producing hallucinated facts vs
defended RAG catching and flagging ungrounded claims.
"""

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

# OTel telemetry
try:
    from shared.python.telemetry import init_telemetry, flush_telemetry, trace_demo
    init_telemetry()
except Exception:
    flush_telemetry = lambda: None  # noqa: E731
    trace_demo = lambda *a, **kw: (lambda fn: fn)  # noqa: E731

from demo21_vulnerable_rag import VulnerableRAG  # noqa: E402
from demo21_defended_rag import DefendedRAG  # noqa: E402


def load_sources() -> dict[str, dict[str, str]]:
    """Load source articles indexed by ID."""
    path = Path(__file__).resolve().parent.parent / "documents" / "source_articles.json"
    with open(path) as f:
        articles = json.load(f)
    return {a["id"]: a for a in articles}


def load_prompts() -> list[dict[str, str]]:
    """Load hallucination prompts."""
    path = Path(__file__).resolve().parent.parent / "attacks" / "hallucination_prompts.json"
    with open(path) as f:
        return json.load(f)


@trace_demo("Groundedness Detection", demo_id="demo-21", category="azure-defense")
def run_demo(client: Any = None, safety_client: Any = None) -> None:
    """Run the groundedness detection demo."""
    print_banner("Demo 21: Groundedness Detection — Hallucination Defense")

    sources = load_sources()
    prompts = load_prompts()
    vuln = VulnerableRAG(client=client)
    defended = DefendedRAG(client=client, safety_client=safety_client)

    console.print(f"\n[info]Loaded {len(sources)} source articles and {len(prompts)} hallucination prompts[/info]\n")

    for i, prompt_info in enumerate(prompts):
        source = sources.get(prompt_info["source_id"], {})
        source_text = source.get("content", "")
        source_title = source.get("title", "Unknown")

        print_separator(f"[{i+1}/{len(prompts)}] {prompt_info['name']}")
        console.print(f"  [dim]Source: {source_title}[/dim]")
        console.print(f"  [dim]Expected hallucination: {prompt_info['expected_hallucination']}[/dim]\n")

        vuln_result = vuln.answer(prompt_info["prompt"], source_text)
        defended_result = defended.answer(
            prompt_info["prompt"], source_text, reasoning=True
        )

        vuln_text = vuln_result["response"][:300]
        defended_text = defended_result["response"][:300]

        if defended_result.get("grounded") is False:
            defended_text = f"[red]{defended_text}[/red]"
        elif defended_result.get("grounded") is True:
            defended_text = f"[green]{defended_text}[/green]"

        side_by_side(
            vuln_text,
            defended_text,
            left_title="Vulnerable RAG (No Check)",
            right_title="Defended RAG (Groundedness)",
        )

        if i < len(prompts) - 1 and not confirm_proceed():
            break

    console.print("\n[system]Demo complete.[/system]")


def main() -> None:
    """Entry point."""
    safety_client = None
    try:
        from shared.python.azure_client import AzureContentSafetyClient
        safety_client = AzureContentSafetyClient()
        console.print("[green]Azure Groundedness Detection connected.[/green]")
    except Exception as e:
        console.print(f"[yellow]Azure not available: {e}[/yellow]")
        console.print("[dim]Running with mock groundedness client.[/dim]")
        from shared.python.testing.mock_azure import MockContentSafetyClient
        safety_client = MockContentSafetyClient(
            groundedness_responses={
                r"speed improvement|directly cause|alien life|president.*ordered|scientist.*designed": {
                    "grounded": False,
                    "ungroundedPercentage": 45.0,
                    "reasoning": ["Response contains claims not supported by source material"],
                },
            },
        )

    run_demo(safety_client=safety_client)


if __name__ == "__main__":
    try:
        main()
    finally:
        flush_telemetry()
