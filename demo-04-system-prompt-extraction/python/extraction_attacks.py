"""Automated extraction attack runner for system prompt extraction demo.

Runs all extraction techniques against the secret chatbot and highlights
any extracted secret content in red using rich formatting.
"""

import json
import sys
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
    print_message,
)

from chatbot import SecretChatbot, check_extraction, KNOWN_SECRETS  # noqa: E402

# OTel telemetry (no-op when OTEL_ENABLED=false or packages missing)
try:
    from shared.python.telemetry import init_telemetry, flush_telemetry, trace_demo
    init_telemetry()
except Exception:
    flush_telemetry = lambda: None  # noqa: E731
    trace_demo = lambda *a, **kw: (lambda fn: fn)  # noqa: E731

# Path to techniques JSON
TECHNIQUES_PATH = (
    Path(__file__).resolve().parent.parent / "attacks" / "techniques.json"
)


def load_techniques(path: Path | None = None) -> list[dict[str, str]]:
    """Load extraction techniques from the JSON file.

    Raises:
        FileNotFoundError: If the techniques file does not exist.
        json.JSONDecodeError: If the file contains invalid JSON.
    """
    techniques_path = path or TECHNIQUES_PATH
    if not techniques_path.exists():
        raise FileNotFoundError(f"Techniques file not found: {techniques_path}")
    with open(techniques_path) as f:
        data: list[dict[str, str]] = json.load(f)
    return data


def highlight_secrets(response: str, found_secrets: list[str]) -> str:
    """Return the response with found secrets highlighted in red markup."""
    highlighted = response
    for secret in found_secrets:
        highlighted = highlighted.replace(
            secret, f"[bold red]>>>{secret}<<<[/bold red]"
        )
    return highlighted


def run_extraction_attacks(client: Any = None) -> dict[str, list[str]]:
    """Run all extraction techniques and return results.

    Returns a dict mapping technique name -> list of extracted secrets.
    """
    techniques = load_techniques()
    results: dict[str, list[str]] = {}

    print_banner("System Prompt Extraction — Automated Attack Suite")

    console.print(
        "[info]Running extraction techniques against a chatbot with a secret system prompt.[/info]"
    )
    console.print(
        f"[info]Searching for {len(KNOWN_SECRETS)} known secrets in responses.[/info]\n"
    )

    for technique in techniques:
        # Fresh chatbot for each technique (no cross-contamination)
        chatbot = SecretChatbot(client=client)

        print_attack(f"{technique['name']}: {technique['prompt'][:80]}...")

        response = chatbot.send(technique["prompt"])
        found = check_extraction(response)
        results[technique["name"]] = found

        if found:
            highlighted = highlight_secrets(response, found)
            console.print(f"[assistant]{highlighted}[/assistant]")
            console.print(
                f"\n[bold red]⚠ EXTRACTED: {', '.join(found)}[/bold red]"
            )
        else:
            print_message("assistant", response)
            console.print("[dim]No secrets detected in response.[/dim]")

        console.print()

        if not confirm_proceed("Continue to next technique?"):
            break

    # Summary
    console.print("\n[heading]Extraction Summary[/heading]\n")
    total_extracted: set[str] = set()
    for technique_name, secrets in results.items():
        status = (
            f"[bold red]EXTRACTED: {', '.join(secrets)}[/bold red]"
            if secrets
            else "[dim]No secrets found[/dim]"
        )
        console.print(f"  {technique_name}: {status}")
        total_extracted.update(secrets)

    success_rate = len(total_extracted) / max(len(KNOWN_SECRETS), 1) * 100
    techniques_that_extracted = sum(1 for s in results.values() if s)
    console.print(
        f"\n[system]Unique secrets extracted: {len(total_extracted)}/{len(KNOWN_SECRETS)} "
        f"({success_rate:.0f}%)[/system]"
    )
    console.print(
        f"[system]Techniques that extracted secrets: "
        f"{techniques_that_extracted}/{len(results)}[/system]"
    )

    return results


@trace_demo("System Prompt Extraction", demo_id="demo-04", category="attack")
def main() -> None:
    """Entry point for the extraction attack demo.

    Runs automated extraction attacks (this demo is always automated).
    """
    run_extraction_attacks()


if __name__ == "__main__":
    try:
        main()
    finally:
        flush_telemetry()
