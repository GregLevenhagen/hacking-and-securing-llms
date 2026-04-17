"""Terminal demo for Demo 16 — Privilege Escalation.

Runs escalation scenarios showing how an LLM agent can exploit a
misconfigured RBAC system to gain admin/superadmin capabilities.

Usage:
    python app_terminal.py               # interactive mode
    python app_terminal.py --auto        # non-interactive (skip pauses)
    python app_terminal.py --scenario "Direct Escalation"  # single scenario
"""

import json
import sys
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

from escalation_agent import run_escalation  # noqa: E402
from permission_system import PermissionSystem  # noqa: E402

# OTel telemetry (no-op when OTEL_ENABLED=false or packages missing)
try:
    from shared.python.telemetry import init_telemetry, flush_telemetry, trace_demo
    init_telemetry()
except Exception:
    flush_telemetry = lambda: None  # noqa: E731
    trace_demo = lambda *a, **kw: (lambda fn: fn)  # noqa: E731

# Load scenarios from JSON
_SCENARIOS_PATH = Path(__file__).resolve().parent.parent / "attacks" / "scenarios.json"


def _load_scenarios() -> list[dict[str, str]]:
    """Load attack scenarios from the JSON file."""
    if _SCENARIOS_PATH.exists():
        with open(_SCENARIOS_PATH) as f:
            return json.load(f)
    return []


SCENARIOS = _load_scenarios()


def run_escalation_demo(auto: bool = False, scenario: str | None = None) -> None:
    """Run the privilege escalation demonstration scenarios.

    Args:
        auto: If True, skip interactive pauses.
        scenario: If provided, run only the scenario matching this name (case-insensitive).
    """
    print_banner("Privilege Escalation — Attack Scenarios")

    console.print(
        "[attack]WARNING: Demonstrating privilege escalation via RBAC misconfiguration.[/attack]\n"
        "[dim]An LLM agent starts as a basic USER and exploits a vulnerable[/dim]\n"
        "[dim]permission system to escalate to SUPERADMIN.[/dim]\n"
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
        prompt = scenario_info["prompt"]

        print_separator(f"Scenario {i}/{len(scenarios_to_run)}")
        print_step(i, len(scenarios_to_run), name)
        print_attack(scenario_info["description"])

        console.print(f"[info]Prompt:[/info] {prompt[:200]}...")
        console.print("[info]Running escalation agent...[/info]")

        perm_system = PermissionSystem()

        with progress_spinner(f"Running {name}..."):
            trace = run_escalation(
                prompt,
                client=client,
                perm_system=perm_system,
                verbose=False,
            )

        results.append({"name": name, **trace})

        # Display results
        print_message("assistant", trace["final_response"])

        # Show permission changes
        if trace["permission_changes"]:
            console.print(f"[attack]Permission escalations: {len(trace['permission_changes'])}[/attack]")
            for change in trace["permission_changes"]:
                console.print(
                    f"  [attack]{change['from']} -> {change['to']}[/attack]  "
                    f"[dim]Reason: {change['reason']}[/dim]"
                )

        # Show tool calls
        console.print(f"[info]Tool calls made: {len(trace['tool_calls'])}[/info]")
        for call in trace["tool_calls"]:
            level = call.get("permission_level", "?")
            console.print(f"  [{level}] {call['tool']}({json.dumps(call['args'])})")

        console.print()

        if not auto and i < len(scenarios_to_run):
            if not confirm_proceed("Continue to next scenario?"):
                break

    # Summary table
    if results:
        print_separator("Summary")
        headers = ["Scenario", "Escalations", "Tool Calls", "Final Level"]
        rows = []
        for r in results:
            escalations = len(r.get("permission_changes", []))
            tool_calls = len(r.get("tool_calls", []))
            final_level = "USER"
            if r.get("permission_changes"):
                final_level = r["permission_changes"][-1]["to"]
            rows.append([r["name"], str(escalations), str(tool_calls), final_level])
        print_table(headers, rows, title="Privilege Escalation Results")

    console.print("\n[attack]All scenarios demonstrated RBAC exploitation.[/attack]")
    console.print("[defense]Mitigations include:[/defense]")
    console.print("[dim]  - Proper authorization checks on elevation endpoints[/dim]")
    console.print("[dim]  - Multi-factor approval for privilege changes[/dim]")
    console.print("[dim]  - Time-limited elevation tokens[/dim]")
    console.print("[dim]  - Audit logging with anomaly detection[/dim]\n")


@trace_demo("Privilege Escalation", demo_id="demo-16", category="attack")
def main() -> None:
    """Entry point — run with --auto for non-interactive, --scenario NAME for a single scenario."""
    auto = "--auto" in sys.argv
    scenario: str | None = None
    for i, arg in enumerate(sys.argv):
        if arg == "--scenario" and i + 1 < len(sys.argv):
            scenario = sys.argv[i + 1]
    run_escalation_demo(auto=auto, scenario=scenario)


if __name__ == "__main__":
    try:
        main()
    finally:
        flush_telemetry()
