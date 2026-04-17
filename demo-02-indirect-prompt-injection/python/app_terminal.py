"""Interactive terminal demo for indirect prompt injection.

Launches a local Flask server, then fetches and summarizes each page,
showing side-by-side what the human sees vs what the LLM receives.
Requires the page server to be running on port 8080 (or starts it).
"""

import sys
import threading
import time
from pathlib import Path
from typing import Any

# Add project root to path for shared imports
_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root))

from shared.python.config import get_config  # noqa: E402
from shared.python.ollama_client import OllamaClient  # noqa: E402
from shared.python.ui_helpers import (  # noqa: E402
    console,
    confirm_proceed,
    print_attack,
    print_banner,
    print_defense,
    print_message,
    side_by_side,
)

from server import app  # noqa: E402
from summarizer import (  # noqa: E402
    INJECTION_PAYLOAD,
    PAGES,
    compute_detection_metrics,
    extract_text,
    extract_visible_text,
    fetch_page,
    summarize_page,
)

# OTel telemetry (no-op when OTEL_ENABLED=false or packages missing)
try:
    from shared.python.telemetry import init_telemetry, flush_telemetry, trace_demo
    init_telemetry()
except Exception:
    flush_telemetry = lambda: None  # noqa: E731
    trace_demo = lambda *a, **kw: (lambda fn: fn)  # noqa: E731

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8080


def start_server_background() -> threading.Thread:
    """Start the Flask page server in a background thread."""
    thread = threading.Thread(
        target=lambda: app.run(host=SERVER_HOST, port=SERVER_PORT, debug=False, use_reloader=False),
        daemon=True,
    )
    thread.start()
    time.sleep(1)  # Give server time to start
    return thread


def run_demo(client: Any = None) -> None:
    """Run the full indirect injection demo."""
    if client is None:
        client = OllamaClient()

    print_banner("Indirect Prompt Injection")
    console.print("[system]This demo shows how hidden content in web pages")
    console.print("can hijack LLM-powered summarizers.[/system]\n")

    console.print("[info]Starting local page server...[/info]")
    start_server_background()
    console.print(f"[info]Server running at http://{SERVER_HOST}:{SERVER_PORT}[/info]\n")

    base_url = f"http://{SERVER_HOST}:{SERVER_PORT}/pages"

    for page_info in PAGES:
        page_name = page_info["name"]
        page_file = page_info["file"]
        is_poisoned = page_info["poisoned"]
        url = f"{base_url}/{page_file}"

        if is_poisoned:
            print_attack(f"Testing: {page_name}")
        else:
            print_defense(f"Baseline: {page_name}")

        console.print(f"[dim]Fetching {url}...[/dim]\n")

        try:
            html = fetch_page(url)
        except Exception as e:
            console.print(f"[warning]Failed to fetch page: {e}[/warning]\n")
            continue

        # Extract both views
        visible_text = extract_visible_text(html)
        llm_text = extract_text(html, include_comments=True)

        # Truncate for display
        visible_display = visible_text[:500] + ("..." if len(visible_text) > 500 else "")
        llm_display = llm_text[:500] + ("..." if len(llm_text) > 500 else "")

        # Show what human sees vs what LLM receives
        side_by_side(
            visible_display,
            llm_display,
            left_title="HUMAN SEES",
            right_title="LLM RECEIVES",
        )

        # Detection metrics: compare visible vs extracted text lengths
        metrics = compute_detection_metrics(visible_text, llm_text)
        console.print(
            f"[info]Detection metrics: "
            f"visible={metrics['visible_length']} chars, "
            f"extracted={metrics['extracted_length']} chars, "
            f"ratio={metrics['length_ratio']:.3f}, "
            f"extra={metrics['extra_chars']} chars[/info]"
        )
        if metrics["suspicious"]:
            console.print("[attack]SUSPICIOUS: extracted text is >10% longer than visible text![/attack]")

        # Check if injection payload appears in LLM text
        if INJECTION_PAYLOAD[:40] in llm_text:
            console.print("[attack]INJECTION DETECTED in extracted text![/attack]")
        else:
            console.print("[defense]No injection found in extracted text.[/defense]")
        console.print()

        # Summarize with LLM
        console.print("[info]Sending to LLM for summarization...[/info]")
        result = summarize_page(url, client=client, include_comments=True)
        print_message("assistant", result["summary"])

        if not confirm_proceed("Continue to next page?"):
            return

    console.print("\n[system]Demo complete. Notice how poisoned pages made the LLM")
    console.print("produce summaries mentioning recalls and malicious URLs,[/system]")
    console.print("[system]while the legitimate page got an accurate summary.[/system]")


def run_automated(client: Any = None) -> None:
    """Run the demo without interactive pauses."""
    if client is None:
        client = OllamaClient()

    print_banner("Indirect Prompt Injection — Automated")

    start_server_background()
    base_url = f"http://{SERVER_HOST}:{SERVER_PORT}/pages"

    for page_info in PAGES:
        page_name = page_info["name"]
        page_file = page_info["file"]
        is_poisoned = page_info["poisoned"]
        url = f"{base_url}/{page_file}"

        console.print(f"\n[heading]{page_name}[/heading]")
        console.print(f"[dim]Poisoned: {is_poisoned}[/dim]")

        try:
            result = summarize_page(url, client=client, include_comments=True)
        except Exception as e:
            console.print(f"[warning]Error: {e}[/warning]")
            continue

        side_by_side(
            result["visible_text"][:400],
            result["extracted_text"][:400],
            left_title="HUMAN SEES",
            right_title="LLM RECEIVES",
        )

        metrics = result["metrics"]
        console.print(
            f"[info]Detection: ratio={metrics['length_ratio']:.3f}, "
            f"extra={metrics['extra_chars']} chars"
            f"{' [SUSPICIOUS]' if metrics['suspicious'] else ''}[/info]"
        )
        print_message("assistant", result["summary"])

    console.print("\n[system]All pages processed.[/system]")


@trace_demo("Indirect Prompt Injection", demo_id="demo-02", category="attack")
def main() -> None:
    """Entry point — run interactive mode by default, automated with --auto."""
    if "--auto" in sys.argv:
        run_automated()
    else:
        run_demo()


if __name__ == "__main__":
    try:
        main()
    finally:
        flush_telemetry()
