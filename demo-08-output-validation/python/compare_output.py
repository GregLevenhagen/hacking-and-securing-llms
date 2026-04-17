"""Side-by-side comparison: vulnerable vs defended output validation.

Runs each test scenario from scenarios.json against both the undefended
app (raw LLM output) and the defended app (validated output), displaying
results side by side to show which validator caught each violation.

Usage:
    python compare_output.py                # interactive mode
    python compare_output.py --auto         # automated (no pauses)
    python compare_output.py --auto --csv results.csv
    python compare_output.py --auto --scenario "List all SSNs"
"""

import csv
import json
import sys
import time
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

from demo08_vulnerable_app import VulnerableApp  # noqa: E402
from demo08_defended_app import DefendedApp  # noqa: E402

# OTel telemetry (no-op when OTEL_ENABLED=false or packages missing)
try:
    from shared.python.telemetry import init_telemetry, flush_telemetry, trace_demo
    init_telemetry()
except Exception:
    flush_telemetry = lambda: None  # noqa: E731
    trace_demo = lambda *a, **kw: (lambda fn: fn)  # noqa: E731


def load_scenarios() -> list[dict[str, Any]]:
    """Load test scenarios from scenarios.json.

    Raises:
        FileNotFoundError: If scenarios.json is not found.
    """
    scenarios_path = (
        Path(__file__).resolve().parents[1] / "test_cases" / "scenarios.json"
    )
    if not scenarios_path.exists():
        raise FileNotFoundError(f"Scenarios file not found: {scenarios_path}")
    with open(scenarios_path) as f:
        data: list[dict[str, Any]] = json.load(f)
    return data


def format_vulnerable_result(result: dict[str, Any]) -> str:
    """Format the vulnerable app's result for display."""
    response = result["response"] or "(no response)"
    latency_ms = result.get("latency_ms", 0.0)
    # Truncate long responses for display
    if len(response) > 300:
        response = response[:300] + "..."
    return (
        f"[bold red]NO VALIDATION[/bold red] [dim]({latency_ms:.0f}ms)[/dim]\n\n"
        f"{response}"
    )


def format_defended_result(result: dict[str, Any]) -> str:
    """Format the defended app's result for display."""
    lines: list[str] = []

    latency_ms = result.get("latency_ms", 0.0)
    lines.append(f"[dim]Total: {latency_ms:.0f}ms[/dim]\n")

    # Show each validator's verdict with per-validator timing
    for vr in result["validator_results"]:
        validator = vr.get("validator", "unknown")
        is_valid = vr.get("valid", True)
        violations = vr.get("violations", [])
        vr_ms = vr.get("latency_ms", 0.0)

        timing = f"[dim]({vr_ms:.0f}ms)[/dim]" if vr_ms > 0 else ""

        if not is_valid:
            lines.append(f"[bold red]\u2717 {validator}[/bold red] {timing}: VIOLATIONS FOUND")
            for v in violations:
                lines.append(f"  [red]\u2022 {v}[/red]")
        else:
            lines.append(f"[bold green]\u2713 {validator}[/bold green] {timing}: CLEAN")

    lines.append("")

    if not result["valid"]:
        # Summarize which validators caught issues
        blockers = [
            vr["validator"]
            for vr in result["validator_results"]
            if not vr.get("valid", True)
        ]
        lines.append(
            f"[bold cyan]>> BLOCKED BY: {', '.join(blockers)} <<[/bold cyan]"
        )
        lines.append(
            f"[dim]Total violations: {len(result['violations'])}[/dim]"
        )
    else:
        response = result["response"] or "(no response)"
        if len(response) > 200:
            response = response[:200] + "..."
        lines.append(f"[dim]Response:[/dim] {response}")

    return "\n".join(lines)


def run_comparison(
    vulnerable: VulnerableApp | None = None,
    defended: DefendedApp | None = None,
    scenario_filter: str | None = None,
) -> list[dict[str, Any]]:
    """Run all scenarios against both apps and display side-by-side results.

    Args:
        vulnerable: Optional pre-configured vulnerable app.
        defended: Optional pre-configured defended app.
        scenario_filter: If set, only run scenarios whose name contains this string.

    Returns:
        List of result dicts for each scenario with vulnerable/defended outcomes.
    """
    scenarios = load_scenarios()

    if scenario_filter:
        matching = [s for s in scenarios if scenario_filter.lower() in s["name"].lower()]
        if not matching:
            console.print(f"[bold red]No scenario matching '{scenario_filter}'.[/bold red]")
            console.print("[dim]Available scenarios:[/dim]")
            for s in scenarios:
                console.print(f"  [dim]- {s['name']}[/dim]")
            return []
        scenarios = matching

    if vulnerable is None:
        vulnerable = VulnerableApp()
    if defended is None:
        defended = DefendedApp()

    print_banner("Output Validation \u2014 Vulnerable vs Defended")

    console.print(
        "[system]Running scenarios against VULNERABLE (raw output) "
        "and DEFENDED (4 validators) apps[/system]"
    )
    console.print(
        f"[info]Scenarios loaded: {len(scenarios)} from test_cases/scenarios.json[/info]\n"
    )

    results: list[dict[str, Any]] = []
    blocked_count = 0

    for i, scenario in enumerate(scenarios, 1):
        name = scenario["name"]
        user_input = scenario["input"]
        description = scenario.get("description", "")

        console.print(f"[heading]Scenario {i}/{len(scenarios)}[/heading]")
        print_attack(f"{name}: {user_input[:80]}...")
        if description:
            console.print(f"[info]{description}[/info]")

        # Run against both apps with timing
        try:
            start = time.perf_counter()
            vuln_result = vulnerable.send(user_input)
            vuln_result["latency_ms"] = (time.perf_counter() - start) * 1000
        except (OllamaClientError, Exception) as e:
            vuln_result = {
                "response": f"Error: {e}",
                "valid": True,
                "violations": [],
                "validator_results": [],
                "latency_ms": 0.0,
            }

        try:
            start = time.perf_counter()
            def_result = defended.send(user_input)
            def_result["latency_ms"] = (time.perf_counter() - start) * 1000
        except (OllamaClientError, Exception) as e:
            def_result = {
                "response": f"Error: {e}",
                "valid": True,
                "violations": [],
                "validator_results": [],
                "latency_ms": 0.0,
            }

        # Format and display side by side
        vuln_display = format_vulnerable_result(vuln_result)
        def_display = format_defended_result(def_result)

        side_by_side(
            vuln_display,
            def_display,
            left_title="VULNERABLE",
            right_title="DEFENDED",
        )

        if not def_result["valid"]:
            blocked_count += 1

        results.append({
            "scenario_id": scenario["id"],
            "scenario_name": name,
            "input": user_input,
            "vulnerable": vuln_result,
            "defended": def_result,
        })

        if "--auto" not in sys.argv and i < len(scenarios):
            if not confirm_proceed("Continue to next scenario?"):
                break

    # Summary
    console.print("\n[heading]SUMMARY[/heading]")
    console.print(f"[system]Total scenarios: {len(scenarios)}[/system]")
    console.print(
        f"[defense]Violations caught: {blocked_count}/{len(scenarios)}[/defense]"
    )
    console.print(
        f"[attack]Passed all validators: "
        f"{len(scenarios) - blocked_count}/{len(scenarios)}[/attack]"
    )

    # Per-validator stats
    validator_catches: dict[str, int] = {}
    for r in results:
        for vr in r["defended"]["validator_results"]:
            if not vr.get("valid", True):
                name = vr["validator"]
                validator_catches[name] = validator_catches.get(name, 0) + 1

    if validator_catches:
        console.print("\n[system]Catches per validator:[/system]")
        for validator, count in sorted(validator_catches.items()):
            console.print(
                f"  [cyan]{validator}[/cyan]: caught violations in {count} scenarios"
            )

    # Print timing summary table
    print_timing_summary(results)

    return results


def build_timing_summary(results: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """Build per-validator timing stats (avg/min/max) from results.

    Returns:
        Dict of validator name → {"avg_ms": float, "min_ms": float, "max_ms": float, "count": int}
    """
    validator_timings: dict[str, list[float]] = {}

    for r in results:
        for vr in r["defended"].get("validator_results", []):
            validator = vr.get("validator", "unknown")
            ms = vr.get("latency_ms", 0.0)
            validator_timings.setdefault(validator, []).append(ms)

    summary: dict[str, dict[str, float]] = {}
    for validator, timings in validator_timings.items():
        summary[validator] = {
            "avg_ms": round(sum(timings) / len(timings), 2) if timings else 0.0,
            "min_ms": round(min(timings), 2) if timings else 0.0,
            "max_ms": round(max(timings), 2) if timings else 0.0,
            "count": float(len(timings)),
        }

    return summary


def print_timing_summary(results: list[dict[str, Any]]) -> None:
    """Print a colored timing summary table showing avg/min/max per validator."""
    summary = build_timing_summary(results)

    if not summary:
        return

    from shared.python.ui_helpers import print_table  # noqa: E402

    headers = ["Validator", "Count", "Avg (ms)", "Min (ms)", "Max (ms)"]
    rows: list[list[str]] = []
    for validator, stats in summary.items():
        rows.append([
            validator,
            str(int(stats["count"])),
            f"{stats['avg_ms']:.1f}",
            f"{stats['min_ms']:.1f}",
            f"{stats['max_ms']:.1f}",
        ])

    print_table(headers, rows, title="Validator Timing Summary")


def export_csv(results: list[dict[str, Any]], csv_path: str) -> None:
    """Export comparison results to a CSV file."""
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "scenario_id", "scenario_name", "input",
            "vuln_latency_ms",
            "def_valid", "def_violations", "def_latency_ms",
            "validator_timings",
        ])
        for r in results:
            defended = r["defended"]
            validator_timings = ";".join(
                f"{vr.get('validator', '?')}:{vr.get('latency_ms', 0):.0f}ms"
                for vr in defended.get("validator_results", [])
            )
            writer.writerow([
                r["scenario_id"],
                r["scenario_name"],
                r["input"],
                f"{r['vulnerable'].get('latency_ms', 0):.1f}",
                defended.get("valid", True),
                len(defended.get("violations", [])),
                f"{defended.get('latency_ms', 0):.1f}",
                validator_timings,
            ])

    console.print(f"\n[system]Results exported to: {csv_path}[/system]")


def _parse_csv_flag() -> str | None:
    """Parse --csv flag from sys.argv. Returns the CSV path or None."""
    for i, arg in enumerate(sys.argv):
        if arg == "--csv" and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return None


def _parse_scenario_flag() -> str | None:
    """Parse --scenario flag from sys.argv. Returns the scenario filter or None."""
    for i, arg in enumerate(sys.argv):
        if arg == "--scenario" and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return None


@trace_demo("Output Validation", demo_id="demo-08", category="defense")
def main() -> None:
    """Entry point for the comparison demo."""
    # Connectivity check before starting the demo
    client = OllamaClient()
    if not client.health_check():
        console.print(
            "[bold red]ERROR:[/bold red] Cannot connect to Ollama. "
            "Ensure Ollama is running and the model is pulled.\n"
            "See SETUP.md for instructions."
        )
        sys.exit(1)

    scenario_filter = _parse_scenario_flag()
    results = run_comparison(scenario_filter=scenario_filter)

    csv_path = _parse_csv_flag()
    if csv_path is not None:
        export_csv(results, csv_path)


if __name__ == "__main__":
    try:
        main()
    finally:
        flush_telemetry()
