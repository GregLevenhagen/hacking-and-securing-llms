"""Interactive terminal demo for multi-agent manipulation.

Shows how prompt injection propagates across agent boundaries in a
3-stage pipeline: ContentFetcher -> Summarizer -> ActionAgent.

Runs each URL through both clean and poisoned pipelines, displaying
side-by-side results and propagation analysis.
"""

import json
import sys
from pathlib import Path

# Add project root to path for shared imports
_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from shared.python.ollama_client import OllamaClient  # noqa: E402
from shared.python.ui_helpers import (  # noqa: E402
    console,
    confirm_proceed,
    print_attack,
    print_banner,
    print_defense,
    print_message,
    print_separator,
    print_step,
    side_by_side,
)

from multi_agent_pipeline import detect_propagation, run_pipeline  # noqa: E402
from mock_content import CLEAN_PAGES, POISONED_PAGES  # noqa: E402
from pipeline_stages import clear_tool_log, get_tool_log  # noqa: E402

# OTel telemetry (no-op when OTEL_ENABLED=false or packages missing)
try:
    from shared.python.telemetry import init_telemetry, flush_telemetry, trace_demo
    init_telemetry()
except Exception:
    flush_telemetry = lambda: None  # noqa: E731
    trace_demo = lambda *a, **kw: (lambda fn: fn)  # noqa: E731

# Load scenarios
_scenarios_path = Path(__file__).resolve().parent.parent / "attacks" / "scenarios.json"


def _load_scenarios() -> list[dict]:
    if _scenarios_path.exists():
        with open(_scenarios_path) as f:
            return json.load(f)
    return []


def run_demo(client: OllamaClient | None = None) -> None:
    """Run the full multi-agent manipulation demo interactively."""
    if client is None:
        client = OllamaClient()

    print_banner("Multi-Agent Manipulation")
    console.print("[system]This demo shows how prompt injection propagates across")
    console.print("agent boundaries in a 3-stage pipeline:[/system]")
    console.print("[system]  ContentFetcher -> Summarizer -> ActionAgent[/system]\n")

    scenarios = _load_scenarios()
    urls = list(CLEAN_PAGES.keys())

    for i, url in enumerate(urls):
        scenario = scenarios[i] if i < len(scenarios) else {}
        name = scenario.get("name", f"Scenario {i + 1}")

        print_separator()
        console.print(f"\n[heading]SCENARIO: {name}[/heading]")
        console.print(f"[dim]URL: {url}[/dim]\n")

        # ── Clean pipeline ──
        print_defense("Running CLEAN pipeline (no injections)")
        clear_tool_log()

        try:
            clean_result = run_pipeline(url, client, poisoned=False)
            clean_detection = detect_propagation(clean_result)
        except Exception as e:
            console.print(f"[warning]Clean pipeline error: {e}[/warning]")
            continue

        print_step(1, "FETCH", f"{len(clean_result['stage_1_fetch']['content'])} chars fetched")
        print_step(2, "SUMMARIZE", "Summary generated")
        print_message("assistant", clean_result["stage_2_summarize"]["summary"][:400])
        print_step(3, "ACTION", f"{clean_result['stage_3_action']['num_actions']} actions taken")
        if clean_result["stage_3_action"]["final_response"]:
            console.print(f"[dim]{clean_result['stage_3_action']['final_response'][:200]}[/dim]")
        console.print()

        # ── Poisoned pipeline ──
        print_attack("Running POISONED pipeline (hidden injections)")
        clear_tool_log()

        try:
            poisoned_result = run_pipeline(url, client, poisoned=True)
            poisoned_detection = detect_propagation(poisoned_result)
        except Exception as e:
            console.print(f"[warning]Poisoned pipeline error: {e}[/warning]")
            continue

        print_step(1, "FETCH", f"{len(poisoned_result['stage_1_fetch']['content'])} chars fetched (POISONED)")
        print_step(2, "SUMMARIZE", "Summary generated")
        print_message("assistant", poisoned_result["stage_2_summarize"]["summary"][:400])
        print_step(3, "ACTION", f"{poisoned_result['stage_3_action']['num_actions']} actions taken")
        if poisoned_result["stage_3_action"]["actions_taken"]:
            for action in poisoned_result["stage_3_action"]["actions_taken"]:
                console.print(f"  [attack]TOOL: {action['tool']}({json.dumps(action['arguments'])})[/attack]")
        console.print()

        # ── Propagation analysis ──
        console.print("[system]PROPAGATION ANALYSIS:[/system]")
        chain = poisoned_detection["propagation_chain"]
        if chain:
            console.print(f"  [attack]Injection propagated through: {' -> '.join(chain)}[/attack]")
        else:
            console.print("  [defense]No injection propagation detected[/defense]")

        side_by_side(
            f"Actions: {clean_detection['num_actions']}\nTool calls: {clean_detection['num_tool_calls']}",
            f"Actions: {poisoned_detection['num_actions']}\nTool calls: {poisoned_detection['num_tool_calls']}",
            left_title="CLEAN",
            right_title="POISONED",
        )

        if i < len(urls) - 1:
            if not confirm_proceed("Continue to next scenario?"):
                return

    console.print("\n[system]Demo complete. Notice how injections hidden in web content")
    console.print("propagated through the summarizer and caused the action agent")
    console.print("to execute unauthorized tool calls.[/system]")


def run_automated(client: OllamaClient | None = None) -> None:
    """Run the demo without interactive pauses."""
    if client is None:
        client = OllamaClient()

    print_banner("Multi-Agent Manipulation -- Automated")

    for url in CLEAN_PAGES:
        console.print(f"\n[heading]{url}[/heading]")

        for poisoned in [False, True]:
            label = "POISONED" if poisoned else "CLEAN"
            console.print(f"\n[dim]{label} pipeline:[/dim]")
            clear_tool_log()

            try:
                result = run_pipeline(url, client, poisoned=poisoned)
                detection = detect_propagation(result)
            except Exception as e:
                console.print(f"[warning]Error: {e}[/warning]")
                continue

            console.print(f"  Summary: {result['stage_2_summarize']['summary'][:200]}...")
            console.print(f"  Actions: {result['stage_3_action']['num_actions']}")
            if detection["propagation_chain"]:
                console.print(f"  [attack]Propagation: {' -> '.join(detection['propagation_chain'])}[/attack]")

    console.print("\n[system]All scenarios processed.[/system]")


@trace_demo("Multi-Agent Manipulation", demo_id="demo-17", category="attack")
def main() -> None:
    """Entry point."""
    if "--auto" in sys.argv:
        run_automated()
    else:
        run_demo()


if __name__ == "__main__":
    try:
        main()
    finally:
        flush_telemetry()
