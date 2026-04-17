"""Terminal demo for Demo 18 — Model Probing / Behavior Extraction.

Runs all 6 probing techniques against the model, displays per-probe
results with Rich formatting, then builds and shows a behavior profile.

Usage:
    python app_terminal.py               # interactive mode
    python app_terminal.py --auto        # non-interactive (skip pauses)
    python app_terminal.py --technique boundary_probing  # single technique
"""

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

from probing_attacks import analyze, get_all_techniques  # noqa: E402
from behavior_extractor import build_profile  # noqa: E402

# OTel telemetry (no-op when OTEL_ENABLED=false or packages missing)
try:
    from shared.python.telemetry import init_telemetry, flush_telemetry, trace_demo
    init_telemetry()
except Exception:
    flush_telemetry = lambda: None  # noqa: E731
    trace_demo = lambda *a, **kw: (lambda fn: fn)  # noqa: E731


def run_probing_demo(
    auto: bool = False,
    technique_filter: str | None = None,
    client: object | None = None,
) -> None:
    """Run the model probing demonstration.

    Args:
        auto: If True, skip interactive pauses.
        technique_filter: If provided, run only the matching technique id.
        client: Optional pre-configured client (for testing).
    """
    print_banner("Model Probing / Behavior Extraction — Demo 18")

    console.print(
        "[attack]PROBING: Systematically extracting model behavior patterns.[/attack]\n"
        "[dim]This demo sends structured probes to reveal safety boundaries,[/dim]\n"
        "[dim]training data indicators, system prompt fragments, temperature,[/dim]\n"
        "[dim]and capability scores.[/dim]\n"
    )

    techniques = get_all_techniques()

    # Filter to a single technique if requested
    if technique_filter:
        matching = [t for t in techniques if technique_filter.lower() in t["id"].lower()]
        if not matching:
            console.print(f"[bold red]No technique matching '{technique_filter}'.[/bold red]")
            console.print("[dim]Available techniques:[/dim]")
            for t in techniques:
                console.print(f"  [dim]- {t['id']}: {t['name']}[/dim]")
            return
        techniques = matching

    # Initialize the Ollama client
    if client is None:
        try:
            client = OllamaClient()
        except Exception as e:
            console.print(f"[bold red]Error connecting to Ollama: {e}[/bold red]")
            console.print("[dim]Is Ollama running? Try: ollama serve[/dim]")
            return

    all_results: dict = {}

    for i, tech in enumerate(techniques, 1):
        print_separator(f"Technique {i}/{len(techniques)}: {tech['name']}")
        print_step(i, len(techniques), tech["name"])
        print_attack(tech["description"])

        probes = tech["probes"]
        responses: list[str] = []

        for j, probe in enumerate(probes, 1):
            console.print(f"\n  [user]Probe {j}/{len(probes)}:[/user] {probe}")

            with progress_spinner(f"Probing ({j}/{len(probes)})..."):
                messages = [{"role": "user", "content": probe}]
                response = client.chat(messages)
                if not isinstance(response, str):
                    response = response.choices[0].message.content or ""

            responses.append(response)
            print_message("assistant", response[:300] + ("..." if len(response) > 300 else ""))

        # Analyze results
        analysis = analyze(tech["id"], probes, responses)
        all_results[tech["id"]] = analysis

        # Display technique-specific summary
        _display_technique_summary(tech["id"], analysis)

        if not auto and i < len(techniques):
            if not confirm_proceed("Continue to next technique?"):
                break

    # Build and display the unified profile
    if all_results:
        print_separator("BEHAVIOR PROFILE")
        profile = build_profile(all_results)
        console.print(f"\n[heading]Unified Behavior Profile[/heading]\n")
        console.print(profile.summary())

        # Capability scores table
        if profile.capability_scores:
            headers = ["Capability", "Score"]
            rows = [
                [cap, f"{score:.0%}"]
                for cap, score in sorted(
                    profile.capability_scores.items(),
                    key=lambda x: x[1],
                    reverse=True,
                )
            ]
            print_table(headers, rows, title="Capability Scores")

    console.print("\n[attack]Model probing complete. Behavior profile extracted.[/attack]")
    console.print("[defense]Mitigations include:[/defense]")
    console.print("[dim]  - Consistent refusal messaging across boundary probes[/dim]")
    console.print("[dim]  - System prompt obfuscation techniques[/dim]")
    console.print("[dim]  - Response variance normalization[/dim]")
    console.print("[dim]  - Rate limiting on repeated similar queries[/dim]\n")


def _display_technique_summary(technique_id: str, analysis: dict) -> None:
    """Display a summary for a completed technique analysis."""
    console.print(f"\n[heading]Analysis Results[/heading]")

    if technique_id == "boundary_probing":
        idx = analysis.get("refusal_boundary_index", -1)
        count = analysis.get("refusal_count", 0)
        total = analysis.get("total_probes", 0)
        if idx == -1:
            console.print("[warning]No refusal boundary detected — model answered everything.[/warning]")
        else:
            console.print(f"[result]First refusal at probe index {idx} ({count}/{total} total refusals)[/result]")

    elif technique_id == "membership_inference":
        score = analysis.get("known_data_score", 0)
        kc = analysis.get("known_correct", 0)
        kt = analysis.get("known_total", 0)
        fr = analysis.get("fake_rejected", 0)
        ft = analysis.get("fake_total", 0)
        console.print(f"[result]Known data score: {score:.0%}[/result]")
        console.print(f"  [info]Known texts completed: {kc}/{kt}[/info]")
        console.print(f"  [info]Fake texts rejected:   {fr}/{ft}[/info]")

    elif technique_id == "system_prompt_recovery":
        frags = analysis.get("fragments", [])
        console.print(f"[result]{len(frags)} system prompt fragment(s) recovered[/result]")
        for frag in frags[:5]:
            console.print(f"  [attack]> {frag[:120]}[/attack]")

    elif technique_id == "temperature_fingerprinting":
        temp = analysis.get("estimated_temperature", 0)
        unique = analysis.get("unique_responses", 0)
        total = analysis.get("total_responses", 0)
        console.print(f"[result]Estimated temperature: {temp:.2f}[/result]")
        console.print(f"  [info]Unique responses: {unique}/{total}[/info]")

    elif technique_id == "behavior_cloning":
        results = analysis.get("results", [])
        for r in results:
            domain = r.get("domain", "unknown")
            length = r.get("response_length", 0)
            hedged = r.get("is_hedged", False)
            refused = r.get("is_refused", False)
            status = "[red]REFUSED[/red]" if refused else ("[yellow]HEDGED[/yellow]" if hedged else "[green]ANSWERED[/green]")
            console.print(f"  [{domain:>14}] {status}  ({length:,} chars)")

    elif technique_id == "capability_mapping":
        scores = analysis.get("capability_scores", {})
        for cap, score in sorted(scores.items(), key=lambda x: x[1], reverse=True):
            bar = "=" * int(score * 20)
            console.print(f"  [{cap:>22}] {bar:<20} {score:.0%}")


@trace_demo("Model Probing", demo_id="demo-18", category="attack")
def main() -> None:
    """Entry point with CLI flags."""
    auto = "--auto" in sys.argv
    technique_filter: str | None = None
    for i, arg in enumerate(sys.argv):
        if arg == "--technique" and i + 1 < len(sys.argv):
            technique_filter = sys.argv[i + 1]
    run_probing_demo(auto=auto, technique_filter=technique_filter)


if __name__ == "__main__":
    try:
        main()
    finally:
        flush_telemetry()
