"""Interactive terminal demo for Azure Task Adherence — Agent Tool Safety."""

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

from vulnerable_agent import VulnerableAgent  # noqa: E402
from defended_agent import DefendedAgent, TaskAdherenceChecker  # noqa: E402


def load_scenarios() -> list[dict[str, Any]]:
    path = Path(__file__).resolve().parent.parent / "scenarios" / "misaligned_actions.json"
    with open(path) as f:
        return json.load(f)


@trace_demo("Task Adherence", demo_id="demo-24", category="azure-defense")
def run_demo(safety_client: Any = None) -> None:
    print_banner("Demo 24: Task Adherence — Agent Tool Safety")

    scenarios = load_scenarios()
    vuln = VulnerableAgent()
    checker = TaskAdherenceChecker(safety_client=safety_client)
    defended = DefendedAgent(checker=checker)

    console.print(f"\n[info]Testing {len(scenarios)} misaligned action scenarios[/info]\n")

    for i, scenario in enumerate(scenarios):
        print_separator(f"[{i+1}/{len(scenarios)}] {scenario['name']}")
        console.print(f"  [bold]User asked:[/bold] {scenario['user_intent']}")
        console.print(f"  [bold]Agent tried:[/bold] {scenario['tool_name']}({json.dumps(scenario['tool_input'])})")
        console.print(f"  [dim]Expected: {scenario['expected_misalignment']}[/dim]\n")

        vuln_result = vuln.execute_scenario(scenario)
        defended_result = defended.execute_scenario(scenario)

        vuln_text = f"✅ Executed: {vuln_result['tool_output']}"
        if defended_result["blocked"]:
            check = defended_result["adherence_check"]
            defended_text = (
                f"[green]🛡️ BLOCKED — Misalignment detected[/green]\n"
                f"Risk: {check.get('risk_type', 'unknown')}\n"
                f"Reasoning: {check.get('reasoning', '')}"
            )
        else:
            defended_text = f"✅ Allowed: {defended_result['tool_output']}"

        side_by_side(vuln_text, defended_text, left_title="Vulnerable Agent", right_title="Defended Agent")

        if i < len(scenarios) - 1 and not confirm_proceed():
            break

    console.print("\n[system]Demo complete.[/system]")


def main() -> None:
    safety_client = None
    try:
        from shared.python.azure_client import AzureContentSafetyClient
        safety_client = AzureContentSafetyClient()
        console.print("[green]Azure Task Adherence connected.[/green]")
    except Exception as e:
        console.print(f"[yellow]Azure not available: {e}[/yellow]")
        console.print("[dim]Using heuristic adherence checker.[/dim]")

    run_demo(safety_client=safety_client)


if __name__ == "__main__":
    try:
        main()
    finally:
        flush_telemetry()
