"""Interactive terminal demo for Azure Prompt Shields.

Shows jailbreak and indirect injection detection with side-by-side
comparison of unprotected vs shielded chatbot.
"""

import json
import sys
from pathlib import Path
from typing import Any

_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root))

from shared.python.ollama_client import OllamaClient, OllamaClientError  # noqa: E402
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

from shield_scanner import ShieldScanner  # noqa: E402
from realtime_shield import RealtimeShieldedChatbot  # noqa: E402


def load_json(filename: str) -> list[dict[str, Any]]:
    """Load a JSON payload file from the attacks/ directory."""
    path = Path(__file__).resolve().parent.parent / "attacks" / filename
    with open(path) as f:
        return json.load(f)


def run_jailbreak_scan(scanner: ShieldScanner) -> None:
    """Scan all jailbreak payloads and display results."""
    print_separator("Phase 1: Jailbreak Detection")
    payloads = load_json("jailbreak_payloads.json")

    detected = 0
    for i, payload in enumerate(payloads):
        result = scanner.scan_jailbreak(payload["payload"])

        status = "[red]🛡️ BLOCKED[/red]" if result["detected"] else "[green]✓ Safe[/green]"
        console.print(f"  [{i+1}/{len(payloads)}] {payload['name']}: {status}")

        if result["detected"]:
            detected += 1
            console.print(f"    [dim]Attack type: {result['attack_type']}[/dim]")

    console.print(
        f"\n  [info]Jailbreak detection rate: {detected}/{len(payloads)} "
        f"({detected/len(payloads)*100:.0f}%)[/info]\n"
    )


def run_indirect_scan(scanner: ShieldScanner) -> None:
    """Scan all indirect injection payloads and display results."""
    print_separator("Phase 2: Indirect Injection Detection")
    payloads = load_json("indirect_payloads.json")

    detected = 0
    for i, payload in enumerate(payloads):
        result = scanner.scan_document(
            user_prompt=payload["user_prompt"],
            documents=[payload["document"]],
        )

        status = "[red]🛡️ BLOCKED[/red]" if result["detected"] else "[green]✓ Safe[/green]"
        console.print(f"  [{i+1}/{len(payloads)}] {payload['name']}: {status}")

        if result["detected"]:
            detected += 1
            console.print(f"    [dim]Attack type: {result['attack_type']}[/dim]")

    console.print(
        f"\n  [info]Indirect injection detection rate: {detected}/{len(payloads)} "
        f"({detected/len(payloads)*100:.0f}%)[/info]\n"
    )


def run_realtime_comparison(
    safety_client: Any,
    llm_client: Any = None,
) -> None:
    """Show side-by-side: unprotected vs shielded chatbot."""
    print_separator("Phase 3: Real-time Shield Comparison")
    payloads = load_json("jailbreak_payloads.json")[:5]  # First 5 for brevity

    from shared.python.testing.mock_ollama import MockOllamaClient  # noqa: E402
    unprotected = MockOllamaClient(default_response="Sure, here's the information you requested...")
    shielded = RealtimeShieldedChatbot(
        client=llm_client or MockOllamaClient(default_response="Here is a safe response."),
        safety_client=safety_client,
    )

    for i, payload in enumerate(payloads):
        console.print(f"\n  [bold]Attack: {payload['name']}[/bold]")
        console.print(f"  [dim]{payload['payload'][:80]}...[/dim]\n")

        vuln_resp = unprotected.chat([{"role": "user", "content": payload["payload"]}])
        shield_resp = shielded.send(payload["payload"])
        shielded.reset()

        left = str(vuln_resp)[:200]
        right = shield_resp["response"][:200]
        if shield_resp["blocked"]:
            right = f"[green]{right}[/green]"

        side_by_side(left, right, left_title="Unprotected", right_title="Prompt Shield")

        if i < len(payloads) - 1 and not confirm_proceed():
            break


@trace_demo("Prompt Shields", demo_id="demo-20", category="azure-defense")
def run_demo(safety_client: Any = None) -> None:
    """Run the full demo."""
    print_banner("Demo 20: Prompt Shields — Jailbreak & Indirect Injection Detection")

    scanner = ShieldScanner(safety_client=safety_client)

    run_jailbreak_scan(scanner)
    if confirm_proceed("Continue to indirect injection scan?"):
        run_indirect_scan(scanner)
    if confirm_proceed("Continue to real-time comparison?"):
        run_realtime_comparison(safety_client)

    console.print("\n[system]Demo complete.[/system]")


def main() -> None:
    """Entry point."""
    safety_client = None
    try:
        from shared.python.azure_client import AzureContentSafetyClient
        safety_client = AzureContentSafetyClient()
        console.print("[green]Azure Prompt Shields connected.[/green]")
    except Exception as e:
        console.print(f"[yellow]Azure not available: {e}[/yellow]")
        console.print("[dim]Running with mock Prompt Shields for demonstration.[/dim]")
        from shared.python.testing.mock_azure import MockContentSafetyClient
        safety_client = MockContentSafetyClient(
            prompt_shield_responses={
                r"DAN|developer mode|ignore.*(previous|all)|override|PWNED": {
                    "userPromptAttack": {"detected": True, "attackType": "jailbreak"},
                    "documentAttack": {"detected": False, "attackType": "none"},
                },
                r"Base64|ROT13|1gn0r3|decode": {
                    "userPromptAttack": {"detected": True, "attackType": "encoding_attack"},
                    "documentAttack": {"detected": False, "attackType": "none"},
                },
            },
        )

    run_demo(safety_client=safety_client)


if __name__ == "__main__":
    try:
        main()
    finally:
        flush_telemetry()
