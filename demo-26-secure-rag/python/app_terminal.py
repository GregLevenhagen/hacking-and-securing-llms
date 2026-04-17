"""Interactive terminal demo for Azure AI Search — Secure RAG with Access Control.

Shows side-by-side comparison of a vulnerable RAG system (no access control)
vs a defended RAG system (with Azure AI Search security trimming), demonstrating
how the same query returns different documents depending on the user's role.

Usage:
    python app_terminal.py               # interactive mode
    python app_terminal.py --auto        # non-interactive (skip pauses)
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

from demo26_vulnerable_rag import VulnerableRAG  # noqa: E402
from demo26_defended_rag import DefendedRAG  # noqa: E402


# Demonstration scenarios: pairs of (role, query) to show access differences
SCENARIOS = [
    {
        "name": "Intern vs Executive — Revenue Query",
        "query": "revenue forecast",
        "roles": ("intern", "executive"),
        "description": "An intern and an executive both search for revenue data.",
    },
    {
        "name": "Employee vs Manager — Salary Information",
        "query": "salary band",
        "roles": ("employee", "manager"),
        "description": "An employee and a manager both search for salary information.",
    },
    {
        "name": "Intern vs Executive — Acquisition Details",
        "query": "acquisition",
        "roles": ("intern", "executive"),
        "description": "An intern tries to find acquisition details that only executives should see.",
    },
    {
        "name": "Unknown Role — Broad Search",
        "query": "company",
        "roles": ("unknown_user", "executive"),
        "description": "An unrecognized role vs an executive — unknown defaults to public only.",
    },
]


def _format_results(results: list[dict], role: str, rag_type: str) -> str:
    """Format search results for display in a panel."""
    lines = [f"[bold]Role:[/bold] {role}  |  [bold]Type:[/bold] {rag_type}"]
    lines.append(f"[bold]Results:[/bold] {len(results)} document(s)\n")

    if not results:
        lines.append("[dim]No documents returned.[/dim]")
    else:
        for doc in results:
            level = doc["access_level"]
            level_colors = {
                "public": "green",
                "internal": "yellow",
                "confidential": "red",
                "executive-only": "bold red",
            }
            color = level_colors.get(level, "white")
            lines.append(f"[bold]{doc['title']}[/bold]")
            lines.append(f"  Level: [{color}]{level}[/{color}]  |  Dept: {doc['department']}")
            lines.append(f"  [dim]{doc['content'][:120]}...[/dim]\n")

    return "\n".join(lines)


@trace_demo("Secure RAG", demo_id="demo-26", category="azure-defense")
def run_demo(auto: bool = False) -> None:
    """Run the side-by-side comparison demo."""
    print_banner("Demo 26: Azure AI Search — Secure RAG with Access Control")

    console.print(
        "\n[attack]VULNERABILITY: RAG without access control leaks confidential documents.[/attack]\n"
        "[dim]This demo shows how Azure AI Search security trimming ensures users[/dim]\n"
        "[dim]only retrieve documents their role is authorized to view.[/dim]\n"
    )

    vuln = VulnerableRAG()
    defended = DefendedRAG()

    # Show document corpus summary
    role_info = defended.get_role_info("executive")
    console.print(f"[info]Document corpus: {role_info['total_document_count']} documents[/info]")
    for role in ["intern", "employee", "manager", "executive"]:
        info = defended.get_role_info(role)
        console.print(
            f"  [dim]{role:>10}: can access {info['accessible_document_count']}"
            f"/{info['total_document_count']} documents "
            f"(levels: {', '.join(info['allowed_levels'])})[/dim]"
        )
    console.print()

    for i, scenario in enumerate(SCENARIOS):
        print_separator(f"[{i+1}/{len(SCENARIOS)}] {scenario['name']}")
        console.print(f"[dim]{scenario['description']}[/dim]")
        console.print(f"[user]Query:[/user] \"{scenario['query']}\"\n")

        role_left, role_right = scenario["roles"]

        # Vulnerable: returns everything regardless of role
        vuln_results = vuln.search(scenario["query"], user_role=role_left)

        # Defended: filters by role
        defended_left = defended.search(scenario["query"], user_role=role_left)
        defended_right = defended.search(scenario["query"], user_role=role_right)

        # Panel 1: Vulnerable (no filtering) for the lower-privilege role
        vuln_text = _format_results(vuln_results, role_left, "Vulnerable (No ACL)")

        # Panel 2: Defended results for the lower-privilege role
        defended_left_text = _format_results(defended_left, role_left, "Defended (Security Trimmed)")

        side_by_side(
            vuln_text,
            defended_left_text,
            left_title=f"Vulnerable — {role_left}",
            right_title=f"Defended — {role_left}",
        )

        # Also show what the higher-privilege role sees in the defended system
        console.print(f"\n[defense]Defended system — {role_right} sees:[/defense]")
        if defended_right:
            for doc in defended_right:
                level = doc["access_level"]
                level_colors = {
                    "public": "green",
                    "internal": "yellow",
                    "confidential": "red",
                    "executive-only": "bold red",
                }
                color = level_colors.get(level, "white")
                console.print(
                    f"  [{color}]{level:<16}[/{color}] {doc['title']}"
                )
        else:
            console.print("  [dim]No results.[/dim]")

        if i < len(SCENARIOS) - 1 and not auto:
            if not confirm_proceed():
                break

    # Summary
    console.print("\n[system]Demo complete.[/system]\n")
    console.print("[attack]Without access control:[/attack] Any user retrieves all matching documents,")
    console.print("including confidential financials and executive-only acquisition plans.\n")
    console.print("[defense]With Azure AI Search security trimming:[/defense]")
    console.print("[dim]  - Documents indexed with access-level / group fields[/dim]")
    console.print("[dim]  - Query-time security filters enforce role-based access[/dim]")
    console.print("[dim]  - User identity resolved from Azure AD / Entra ID tokens[/dim]")
    console.print("[dim]  - Principle of least privilege: unknown roles see public only[/dim]\n")


def main() -> None:
    """Entry point with CLI flags."""
    auto = "--auto" in sys.argv
    run_demo(auto=auto)


if __name__ == "__main__":
    try:
        main()
    finally:
        flush_telemetry()
