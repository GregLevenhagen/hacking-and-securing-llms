"""Side-by-side comparison: vulnerable vs defended chatbot.

Runs each attack payload from Demo 1 against both the undefended and
defended customer support chatbots, displaying results side by side
to show which defense layer caught each attack.

Usage:
    python compare_input.py                # interactive mode
    python compare_input.py --auto         # automated (no pauses)
    python compare_input.py --payload "Ignore previous instructions"
    python compare_input.py --auto --csv results.csv
    python compare_input.py --auto --json results.json
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

from vulnerable_chatbot import VulnerableChatbot  # noqa: E402
from defended_chatbot import DefendedChatbot  # noqa: E402

# OTel telemetry (no-op when OTEL_ENABLED=false or packages missing)
try:
    from shared.python.telemetry import init_telemetry, flush_telemetry, trace_demo
    init_telemetry()
except Exception:
    flush_telemetry = lambda: None  # noqa: E731
    trace_demo = lambda *a, **kw: (lambda fn: fn)  # noqa: E731


def load_payloads() -> list[dict[str, str]]:
    """Load attack payloads from Demo 1's payloads.json.

    Raises:
        FileNotFoundError: If payloads.json is not found.
    """
    payloads_path = (
        Path(__file__).resolve().parents[2]
        / "demo-01-direct-prompt-injection"
        / "attacks"
        / "payloads.json"
    )
    if not payloads_path.exists():
        raise FileNotFoundError(
            f"Payloads file not found: {payloads_path}\n"
            "Ensure Demo 1 is set up first."
        )
    with open(payloads_path) as f:
        data: list[dict[str, str]] = json.load(f)
    return data


def format_vulnerable_result(result: dict[str, Any]) -> str:
    """Format the vulnerable chatbot's result for display."""
    response = result["response"] or "(no response)"
    latency_ms = result.get("latency_ms", 0.0)
    return (
        f"[bold red]NO DEFENSES[/bold red] [dim]({latency_ms:.0f}ms)[/dim]\n\n"
        f"{response}"
    )


def format_defended_result(result: dict[str, Any]) -> str:
    """Format the defended chatbot's result for display."""
    lines: list[str] = []

    total_ms = result.get("latency_ms", 0.0)
    lines.append(f"[dim]Total: {total_ms:.0f}ms[/dim]\n")

    # Show each defense layer's verdict with per-layer timing
    for dr in result["defense_results"]:
        layer = dr.get("layer", "unknown")
        blocked = dr.get("blocked", False)
        reason = dr.get("reason", "")
        layer_ms = dr.get("latency_ms", 0.0)

        timing = f"[dim]({layer_ms:.0f}ms)[/dim]"
        if blocked:
            lines.append(f"[bold red]✗ {layer}[/bold red] {timing}: BLOCKED — {reason}")
        else:
            lines.append(f"[bold green]✓ {layer}[/bold green] {timing}: PASS — {reason}")

    lines.append("")

    if result["blocked"]:
        lines.append(
            f"[bold cyan]>> BLOCKED BY: {result['blocked_by']} <<[/bold cyan]"
        )
    else:
        response = result["response"] or "(no response)"
        lines.append(f"[dim]Response:[/dim] {response}")

    return "\n".join(lines)


def _timed_send(
    chatbot: VulnerableChatbot | DefendedChatbot,
    payload: str,
) -> dict[str, Any]:
    """Send a payload and measure wall-clock latency."""
    start = time.perf_counter()
    result = chatbot.send(payload)
    elapsed_ms = (time.perf_counter() - start) * 1000
    result["latency_ms"] = elapsed_ms
    return result


def export_csv(results: list[dict[str, Any]], csv_path: str) -> None:
    """Export comparison results to a CSV file.

    Columns: attack_name, payload, vuln_blocked, vuln_latency_ms,
             def_blocked, def_blocked_by, def_latency_ms, layer_timings
    """
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "attack_name", "payload",
            "vuln_blocked", "vuln_latency_ms",
            "def_blocked", "def_blocked_by", "def_latency_ms",
            "layer_timings",
        ])
        for r in results:
            vuln = r["vulnerable"]
            defended = r["defended"]
            # Encode per-layer timings as "layer:Xms;layer:Yms"
            layer_timings = ";".join(
                f"{dr.get('layer', '?')}:{dr.get('latency_ms', 0):.0f}ms"
                for dr in defended.get("defense_results", [])
            )
            writer.writerow([
                r["attack_name"],
                r["payload"],
                vuln.get("blocked", False),
                f"{vuln.get('latency_ms', 0):.1f}",
                defended.get("blocked", False),
                defended.get("blocked_by", ""),
                f"{defended.get('latency_ms', 0):.1f}",
                layer_timings,
            ])

    console.print(f"\n[system]Results exported to: {csv_path}[/system]")


def _parse_payload_flag() -> str | None:
    """Parse --payload flag from sys.argv. Returns the custom payload or None."""
    for i, arg in enumerate(sys.argv):
        if arg == "--payload" and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return None


def _parse_csv_flag() -> str | None:
    """Parse --csv flag from sys.argv. Returns the CSV path or None."""
    for i, arg in enumerate(sys.argv):
        if arg == "--csv" and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return None


def _parse_json_flag() -> str | None:
    """Parse --json flag from sys.argv. Returns the JSON path or None."""
    for i, arg in enumerate(sys.argv):
        if arg == "--json" and i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return None


def export_json(results: list[dict[str, Any]], json_path: str) -> None:
    """Export comparison results to a machine-readable JSON file.

    Structure: { summary: {...}, per_layer_timing: {...}, results: [...] }
    """
    summary = build_timing_summary(results)
    output = {
        "summary": {
            "total_attacks": len(results),
            "blocked": sum(1 for r in results if r["defended"]["blocked"]),
            "passed": sum(1 for r in results if not r["defended"]["blocked"]),
        },
        "per_layer_timing": summary,
        "results": [
            {
                "attack_name": r["attack_name"],
                "payload": r["payload"],
                "vulnerable": {
                    "blocked": r["vulnerable"].get("blocked", False),
                    "latency_ms": round(r["vulnerable"].get("latency_ms", 0.0), 1),
                },
                "defended": {
                    "blocked": r["defended"].get("blocked", False),
                    "blocked_by": r["defended"].get("blocked_by"),
                    "latency_ms": round(r["defended"].get("latency_ms", 0.0), 1),
                    "layers": [
                        {
                            "layer": dr.get("layer", "?"),
                            "blocked": dr.get("blocked", False),
                            "latency_ms": round(dr.get("latency_ms", 0.0), 1),
                        }
                        for dr in r["defended"].get("defense_results", [])
                    ],
                },
            }
            for r in results
        ],
    }

    with open(json_path, "w") as f:
        json.dump(output, f, indent=2)

    console.print(f"\n[system]JSON results exported to: {json_path}[/system]")


def build_timing_summary(results: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """Build per-layer timing stats (avg/min/max) from results.

    Returns:
        Dict of layer name → {"avg_ms": float, "min_ms": float, "max_ms": float, "count": int}
    """
    layer_timings: dict[str, list[float]] = {}

    for r in results:
        for dr in r["defended"].get("defense_results", []):
            layer = dr.get("layer", "unknown")
            ms = dr.get("latency_ms", 0.0)
            layer_timings.setdefault(layer, []).append(ms)

    summary: dict[str, dict[str, float]] = {}
    for layer, timings in layer_timings.items():
        summary[layer] = {
            "avg_ms": round(sum(timings) / len(timings), 2) if timings else 0.0,
            "min_ms": round(min(timings), 2) if timings else 0.0,
            "max_ms": round(max(timings), 2) if timings else 0.0,
            "count": float(len(timings)),
        }

    return summary


def print_timing_summary(results: list[dict[str, Any]]) -> None:
    """Print a colored timing summary table showing avg/min/max per layer."""
    summary = build_timing_summary(results)

    if not summary:
        return

    from shared.python.ui_helpers import print_table  # noqa: E402

    headers = ["Layer", "Count", "Avg (ms)", "Min (ms)", "Max (ms)"]
    rows: list[list[str]] = []
    for layer, stats in summary.items():
        rows.append([
            layer,
            str(int(stats["count"])),
            f"{stats['avg_ms']:.1f}",
            f"{stats['min_ms']:.1f}",
            f"{stats['max_ms']:.1f}",
        ])

    print_table(headers, rows, title="Defense Layer Timing Summary")


def run_comparison(
    vulnerable: VulnerableChatbot | None = None,
    defended: DefendedChatbot | None = None,
    custom_payload: str | None = None,
) -> list[dict[str, Any]]:
    """Run all attacks against both chatbots and display side-by-side results.

    Args:
        vulnerable: Optional pre-configured vulnerable chatbot.
        defended: Optional pre-configured defended chatbot.
        custom_payload: If set, run only this single payload instead of the file.

    Returns:
        List of result dicts for each attack with vulnerable/defended outcomes.
    """
    if custom_payload is not None:
        payloads = [{"name": "custom", "payload": custom_payload}]
    else:
        payloads = load_payloads()

    if vulnerable is None:
        vulnerable = VulnerableChatbot()
    if defended is None:
        defended = DefendedChatbot()

    print_banner("Input Sanitization — Vulnerable vs Defended")

    console.print("[system]Running attacks against VULNERABLE (no defenses) and DEFENDED (4 layers) chatbots[/system]")
    console.print(f"[info]Attacks loaded: {len(payloads)} payload(s)[/info]\n")

    results: list[dict[str, Any]] = []
    blocked_count = 0

    for i, payload_info in enumerate(payloads, 1):
        name = payload_info["name"]
        payload = payload_info["payload"]

        console.print(f"[heading]Attack {i}/{len(payloads)}[/heading]")
        print_attack(f"{name}: {payload[:80]}{'...' if len(payload) > 80 else ''}")

        # Run against both chatbots with timing
        try:
            vuln_result = _timed_send(vulnerable, payload)
        except Exception as e:
            vuln_result = {"response": f"Error: {e}", "blocked": False, "latency_ms": 0.0}

        try:
            def_result = _timed_send(defended, payload)
        except Exception as e:
            def_result = {
                "response": f"Error: {e}",
                "blocked": False,
                "blocked_by": None,
                "defense_results": [],
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

        if def_result["blocked"]:
            blocked_count += 1

        results.append({
            "attack_name": name,
            "payload": payload,
            "vulnerable": vuln_result,
            "defended": def_result,
        })

        if "--auto" not in sys.argv and i < len(payloads):
            if not confirm_proceed("Continue to next attack?"):
                break

    # Summary
    console.print("\n[heading]SUMMARY[/heading]")
    console.print(f"[system]Total attacks: {len(payloads)}[/system]")
    console.print(f"[defense]Blocked by defenses: {blocked_count}/{len(payloads)}[/defense]")
    console.print(f"[attack]Passed all layers: {len(payloads) - blocked_count}/{len(payloads)}[/attack]")

    # Per-layer stats
    layer_blocks: dict[str, int] = {}
    for r in results:
        if r["defended"]["blocked"]:
            blocker = r["defended"]["blocked_by"]
            layer_blocks[blocker] = layer_blocks.get(blocker, 0) + 1

    if layer_blocks:
        console.print("\n[system]Blocks per defense layer:[/system]")
        for layer, count in sorted(layer_blocks.items()):
            console.print(f"  [cyan]{layer}[/cyan]: {count} attacks blocked")

    # Show timing summary table
    print_timing_summary(results)

    return results


@trace_demo("Input Sanitization", demo_id="demo-06", category="defense")
def main() -> None:
    """Entry point for the comparison demo."""
    custom_payload = _parse_payload_flag()
    results = run_comparison(custom_payload=custom_payload)

    csv_path = _parse_csv_flag()
    if csv_path is not None:
        export_csv(results, csv_path)

    json_path = _parse_json_flag()
    if json_path is not None:
        export_json(results, json_path)


if __name__ == "__main__":
    try:
        main()
    finally:
        flush_telemetry()
