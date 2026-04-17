"""Terminal UI helpers for projector-ready demo output.

Uses the rich library with a hacker/cyberpunk color theme:
  - Neon green (#00ff00) for system messages
  - Red for attack indicators
  - Cyan for defense indicators

All output is designed for large-screen projection at 1920x1080.
"""

from contextlib import contextmanager
from typing import Any, Generator, Sequence

from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.rule import Rule
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

__all__ = [
    "HACKER_THEME",
    "console",
    "print_banner",
    "print_message",
    "print_attack",
    "print_defense",
    "print_json",
    "print_result",
    "print_separator",
    "print_step",
    "print_table",
    "print_warning",
    "progress_spinner",
    "side_by_side",
    "styled_input",
    "confirm_proceed",
]

# Hacker/cyberpunk color theme for projector-ready output
HACKER_THEME = Theme(
    {
        "system": "bold #00ff00",       # neon green
        "user": "bold #ffb000",          # amber
        "assistant": "#00ff00",          # neon green
        "attack": "bold red",            # red for attacks
        "defense": "bold cyan",          # cyan for defense
        "info": "dim #00ff00",           # dim green
        "warning": "bold yellow",
        "heading": "bold underline #00ff00",
        "result": "bold #00fff0",       # neon cyan for results
        "blocked": "bold red on #1a0000",  # red on dark red bg
        "passed": "bold #00ff00 on #001a00",  # green on dark green bg
    }
)

console = Console(theme=HACKER_THEME, width=120)


def print_banner(title: str) -> None:
    """Display a large styled banner suitable for projector display."""
    banner_text = Text(title.upper(), style="bold #00ff00")
    panel = Panel(
        banner_text,
        border_style="#00ff00",
        padding=(1, 4),
        title="[ HACKING LLMs ]",
        title_align="left",
        subtitle="[ DEMO ]",
        subtitle_align="right",
    )
    console.print()
    console.print(panel)
    console.print()


def print_message(role: str, content: str) -> None:
    """Display a chat message with role-appropriate styling.

    Roles: 'system', 'user', 'assistant', or any custom role.
    """
    style_map: dict[str, str] = {
        "system": "system",
        "user": "user",
        "assistant": "assistant",
    }
    style = style_map.get(role, "info")

    prefix_map: dict[str, str] = {
        "system": "> SYSTEM:",
        "user": "$ USER:",
        "assistant": "< ASSISTANT:",
    }
    prefix = prefix_map.get(role, f"> {role.upper()}:")

    console.print(f"[{style}]{prefix}[/{style}]")
    console.print(f"  {content}", style=style)
    console.print()


def print_attack(desc: str) -> None:
    """Display an attack indicator with red styling."""
    panel = Panel(
        desc,
        border_style="red",
        title="[bold red][ ATTACK ][/bold red]",
        title_align="left",
        padding=(0, 2),
    )
    console.print(panel)


def print_defense(desc: str) -> None:
    """Display a defense indicator with cyan styling."""
    panel = Panel(
        desc,
        border_style="cyan",
        title="[bold cyan][ DEFENSE ][/bold cyan]",
        title_align="left",
        padding=(0, 2),
    )
    console.print(panel)


def side_by_side(left: str, right: str, left_title: str = "BEFORE", right_title: str = "AFTER") -> None:
    """Render two-column layout for before/after comparisons.

    Uses rich Columns to display side-by-side panels suitable for
    projector display.
    """
    left_panel = Panel(
        left,
        title=f"[bold red][ {left_title} ][/bold red]",
        border_style="red",
        expand=True,
        padding=(1, 2),
    )
    right_panel = Panel(
        right,
        title=f"[bold cyan][ {right_title} ][/bold cyan]",
        border_style="cyan",
        expand=True,
        padding=(1, 2),
    )
    columns = Columns([left_panel, right_panel], equal=True, expand=True)
    console.print()
    console.print(columns)
    console.print()


def print_result(label: str, content: str, *, blocked: bool = False) -> None:
    """Display a labeled result with pass/block styling.

    Args:
        label: Short label for the result (e.g., "regex_filter", "pii_detector").
        content: The result description or reason.
        blocked: If True, uses red BLOCKED styling; otherwise green PASSED.
    """
    if blocked:
        status = "[blocked][ BLOCKED ][/blocked]"
        style = "red"
    else:
        status = "[passed][ PASSED ][/passed]"
        style = "#00ff00"

    panel = Panel(
        content,
        title=f"[bold {style}]{label}[/bold {style}]  {status}",
        title_align="left",
        border_style=style,
        padding=(0, 2),
    )
    console.print(panel)


def print_separator(title: str = "") -> None:
    """Display a themed horizontal rule for section breaks.

    Args:
        title: Optional centered title text for the separator.
    """
    console.print()
    if title:
        console.print(Rule(title, style="#00ff00"))
    else:
        console.print(Rule(style="dim #00ff00"))
    console.print()


def print_step(step_num: int, total: int, description: str) -> None:
    """Display a numbered step indicator for multi-stage demos.

    Renders as: [01/05] Description text
    with neon green styling suitable for projector display.

    Args:
        step_num: Current step number (1-based).
        total: Total number of steps.
        description: What this step does.
    """
    width = len(str(total))
    label = f"[{step_num:0{width}d}/{total:0{width}d}]"
    label_text = Text(label, style="bold #00ff00")
    desc_text = Text(f" {description}", style="dim #00ff00")
    combined = label_text + desc_text
    console.print(combined)


def print_table(
    headers: Sequence[str],
    rows: Sequence[Sequence[str]],
    title: str = "",
) -> None:
    """Display a styled table for tabular results (e.g., attack results matrix).

    Uses the hacker theme with neon green borders and header styling.

    Args:
        headers: Column header strings.
        rows: List of row data (each row is a sequence of strings).
        title: Optional table title.
    """
    table = Table(
        title=f"[bold #00ff00]{title}[/bold #00ff00]" if title else None,
        border_style="#00ff00",
        header_style="bold #00ff00",
        show_lines=True,
        padding=(0, 1),
    )
    for header in headers:
        table.add_column(header)
    for row in rows:
        table.add_row(*row)
    console.print()
    console.print(table)
    console.print()


@contextmanager
def progress_spinner(message: str = "Processing...") -> Generator[None, None, None]:
    """Context manager showing a spinner for long operations.

    Uses Rich's Status to display a themed spinner while the block
    executes. Suitable for model loading, index building, etc.

    Args:
        message: Status text shown next to the spinner.

    Usage::

        with progress_spinner("Loading model..."):
            load_model()
    """
    with console.status(
        f"[bold #00ff00]{message}[/bold #00ff00]",
        spinner="dots",
        spinner_style="#00ff00",
    ):
        yield


def print_warning(message: str) -> None:
    """Display a warning message for non-fatal issues.

    Use for optional dependency missing, deprecated features, etc.
    """
    text = Text(f"⚠ {message}", style="bold yellow")
    console.print(text)


def print_json(data: Any, title: str = "") -> None:
    """Pretty-print JSON data with syntax highlighting.

    Args:
        data: Any JSON-serializable object (dict, list, str, etc.).
        title: Optional title displayed above the JSON.
    """
    import json as _json

    json_str = _json.dumps(data, indent=2, default=str)
    syntax = Syntax(json_str, "json", theme="monokai", line_numbers=False)
    if title:
        console.print(f"[heading]{title}[/heading]")
    console.print(syntax)


def styled_input(prompt: str = "> ") -> str:
    """Themed input prompt for interactive demos.

    Returns the user's input string (stripped of leading/trailing whitespace).
    """
    console.print(f"[bold #00ff00]{prompt}[/bold #00ff00]", end="")
    return input().strip()


def confirm_proceed(prompt: str = "Press Enter to continue...") -> bool:
    """Pause execution with a styled prompt for live pacing.

    Returns True if the user confirms, False otherwise.
    """
    console.print()
    result: bool = Confirm.ask(f"[bold #00ff00]{prompt}[/bold #00ff00]", default=True)
    console.print()
    return result
