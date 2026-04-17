"""Interactive terminal demo for Foundry Agents with guardrails.

Shows each agent attack scenario against a local agent (no guardrails —
all attacks succeed) vs a Foundry agent (with content safety, tool
governance, and session isolation — attacks are blocked).
"""

import json
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

from local_agent import LocalAgent  # noqa: E402
from foundry_agent import FoundryAgent  # noqa: E402


def load_attacks() -> list[dict]:
    """Load agent attack scenarios from JSON."""
    path = Path(__file__).resolve().parent.parent / "attacks" / "agent_attacks.json"
    with open(path) as f:
        return json.load(f)


def _format_result(result: dict, label: str) -> str:
    """Format agent execution result for display."""
    lines = [f"[bold]{label}[/bold]\n"]
    lines.append(f"Total tool calls: {result['total']}")
    lines.append(f"[green]Executed:[/green] {result['executed_count']}")
    lines.append(f"[red]Blocked:[/red] {result['blocked_count']}\n")

    if result["executed"]:
        lines.append("[bold]Executed:[/bold]")
        for ex in result["executed"]:
            tool = ex.get("tool", "?")
            status = ex.get("status", "?")
            lines.append(f"  {tool}: {status}")

    if result["blocked"]:
        lines.append("[bold]Blocked:[/bold]")
        for bl in result["blocked"]:
            tool = bl.get("tool", bl.get("stage", "?"))
            reason = bl.get("reason", "unknown")
            lines.append(f"  {tool}: [red]{reason[:80]}[/red]")

    return "\n".join(lines)


@trace_demo("Foundry Agents", demo_id="demo-30", category="azure-defense")
def run_demo() -> None:
    """Run the side-by-side agent comparison demo."""
    print_banner("Demo 30: Foundry Agents — Guardrails & Tool Governance")

    attacks = load_attacks()
    console.print(f"\n[info]Loaded {len(attacks)} agent attack scenarios[/info]")
    console.print(
        "[attack]VULNERABILITY: Unguarded agents execute all tool calls without validation.[/attack]\n"
        "[dim]This demo shows how Foundry Agents enforce content safety, tool governance,[/dim]\n"
        "[dim]and session isolation to block malicious tool calls.[/dim]\n"
    )

    local = LocalAgent()
    foundry = FoundryAgent(session_id="demo-session-001")

    for i, attack in enumerate(attacks):
        print_separator(
            f"[{i+1}/{len(attacks)}] {attack['name']} ({attack['category']})"
        )
        console.print(f"[dim]{attack['description']}[/dim]")
        console.print(f"[user]Request:[/user] {attack['user_request'][:80]}\n")

        tool_calls = attack["tool_calls"]
        local_result = local.execute(attack["user_request"], tool_calls)
        foundry_result = foundry.execute(attack["user_request"], tool_calls)

        local_text = _format_result(local_result, "Local Agent (No Guardrails)")
        foundry_text = _format_result(foundry_result, "Foundry Agent (Protected)")

        side_by_side(
            local_text,
            foundry_text,
            left_title="Local — All Executed",
            right_title="Foundry — Blocked",
        )

        if i < len(attacks) - 1 and not confirm_proceed():
            break

    # Summary
    print_separator("Summary")
    local_total = sum(1 for _ in local.execution_log)
    foundry_info = foundry.get_session_info()

    console.print(f"[attack]Local Agent:[/attack] Executed {local_total} tool calls with no validation")
    console.print(
        f"[defense]Foundry Agent:[/defense] "
        f"Executed {foundry_info['total_executions']}, "
        f"Blocked {foundry_info['total_blocks']}"
    )

    console.print("\n[system]Demo complete.[/system]")


def main() -> None:
    """Entry point."""
    run_demo()


if __name__ == "__main__":
    try:
        main()
    finally:
        flush_telemetry()
