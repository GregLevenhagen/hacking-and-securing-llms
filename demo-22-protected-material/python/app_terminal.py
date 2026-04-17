"""Interactive terminal demo for Azure Protected Material Detection."""

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

from vulnerable_generator import VulnerableGenerator  # noqa: E402
from defended_generator import DefendedGenerator  # noqa: E402


def load_prompts() -> list[dict[str, str]]:
    path = Path(__file__).resolve().parent.parent / "attacks" / "generation_prompts.json"
    with open(path) as f:
        return json.load(f)


@trace_demo("Protected Material Detection", demo_id="demo-22", category="azure-defense")
def run_demo(client: Any = None, safety_client: Any = None) -> None:
    print_banner("Demo 22: Protected Material Detection — IP & Copyright Shield")

    prompts = load_prompts()
    vuln = VulnerableGenerator(client=client)
    defended = DefendedGenerator(client=client, safety_client=safety_client)

    console.print(f"\n[info]Testing {len(prompts)} generation prompts for protected material[/info]\n")

    for i, prompt_info in enumerate(prompts):
        print_separator(
            f"[{i+1}/{len(prompts)}] {prompt_info['name']} ({prompt_info['category']})"
        )
        console.print(f"[dim]{prompt_info['payload'][:80]}...[/dim]\n")

        vuln_result = vuln.generate(prompt_info["payload"])
        defended_result = defended.generate(prompt_info["payload"])

        vuln_text = vuln_result["response"][:250]
        defended_text = defended_result["response"][:250]
        if defended_result.get("detected"):
            defended_text = f"[green]{defended_text}[/green]"

        side_by_side(
            vuln_text, defended_text,
            left_title="Vulnerable (No Check)",
            right_title="Defended (Protected Material)",
        )

        if i < len(prompts) - 1 and not confirm_proceed():
            break

    console.print("\n[system]Demo complete.[/system]")


def main() -> None:
    safety_client = None
    try:
        from shared.python.azure_client import AzureContentSafetyClient
        safety_client = AzureContentSafetyClient()
        console.print("[green]Azure Protected Material Detection connected.[/green]")
    except Exception as e:
        console.print(f"[yellow]Azure not available: {e}[/yellow]")
        from shared.python.testing.mock_azure import MockContentSafetyClient
        safety_client = MockContentSafetyClient(
            protected_material_responses={
                r"lyrics|Bohemian|Taylor|Shake It|Harry Potter|Empire Strikes": {
                    "detected": True,
                    "details": {"type": "copyrighted_text", "confidence": 0.95},
                },
                r"useState|stackoverflow|youtube.dl|GPL": {
                    "detected": True,
                    "details": {"type": "source_code", "license": "Various", "confidence": 0.88},
                },
            },
        )

    run_demo(safety_client=safety_client)


if __name__ == "__main__":
    try:
        main()
    finally:
        flush_telemetry()
