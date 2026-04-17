"""Agent loop with approval gates for tool calls.

Extends Demo 5's hand-rolled agent loop by inserting a risk classification
and approval checkpoint before each tool execution:

    send message → check for tool calls → CLASSIFY RISK → APPROVE/DENY →
    execute approved tools → feed results back → repeat until done

High-risk tool calls are blocked until explicitly approved.
"""

import json
import sys
from pathlib import Path
from typing import Any

from openai.types.chat import ChatCompletionMessageParam

# Add project root to path for shared imports
_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root))

# Add Demo 5's python dir for tools and mock_services
_demo5_python = _project_root / "demo-05-agent-exploitation" / "python"
sys.path.insert(0, str(_demo5_python))

# Add local dir for risk_classifier and approval_gate
_local_dir = Path(__file__).resolve().parent
if str(_local_dir) not in sys.path:
    sys.path.insert(0, str(_local_dir))

from shared.python.ollama_client import OllamaClient  # noqa: E402
from shared.python.ui_helpers import console  # noqa: E402

from mock_services import execute_tool  # noqa: E402
from tools import TOOLS  # noqa: E402

from approval_gate import ApprovalCallback, ApprovalResult, ApprovalStatus, check  # noqa: E402
from risk_classifier import RiskLevel  # noqa: E402

# Default system prompt for the agent
AGENT_SYSTEM_PROMPT = (
    "You are a helpful assistant with access to tools. "
    "Use the provided tools to answer user questions. "
    "When you have the final answer, respond directly without calling any more tools."
)

MAX_ITERATIONS = 10

# ── Risk level colors for terminal display ────────────────────
_RISK_COLORS = {
    RiskLevel.LOW: "green",
    RiskLevel.MEDIUM: "#ffb000",
    RiskLevel.HIGH: "red",
}


def _terminal_approval_callback(risk: Any) -> bool:
    """Interactive terminal prompt for high-risk tool calls."""
    console.print(
        f"\n  [bold red]⚠  ACCESS REQUEST[/bold red]  "
        f"[red]High-risk action requires approval[/red]"
    )
    console.print(f"  [dim]Tool:[/dim]   [bold]{risk.tool_name}[/bold]")
    console.print(f"  [dim]Reason:[/dim] {risk.reason}")
    try:
        response = console.input("  [bold #ffb000]APPROVE? (y/n): [/bold #ffb000]")
        return response.strip().lower() in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        return False


def run_agent_with_approval(
    user_message: str,
    client: Any = None,
    system_prompt: str = AGENT_SYSTEM_PROMPT,
    max_iterations: int = MAX_ITERATIONS,
    verbose: bool = True,
    approval_callback: ApprovalCallback | None = None,
    auto_mode: bool = False,
) -> str:
    """Run the tool-calling agent loop with approval gates.

    Args:
        user_message: The user's question or instruction.
        client: OllamaClient instance (or mock for testing).
        system_prompt: The system prompt for the agent.
        max_iterations: Safety limit on tool-call rounds.
        verbose: Whether to print tool calls and results to the console.
        approval_callback: Callback for high-risk approval decisions.
            If None, uses terminal interactive prompt (or auto-deny in auto_mode).
        auto_mode: If True and no callback, auto-deny all high-risk actions.

    Returns:
        The agent's final text response.
    """
    if client is None:
        client = OllamaClient()

    # Default callback: terminal prompt or auto-deny
    if approval_callback is None:
        if auto_mode:
            approval_callback = lambda _: False  # noqa: E731
        else:
            approval_callback = _terminal_approval_callback

    messages: list[ChatCompletionMessageParam] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    for iteration in range(max_iterations):
        response = client.chat(messages, tools=TOOLS)
        message = response.choices[0].message

        # If no tool calls, the agent is done
        if not message.tool_calls:
            return message.content or ""

        # Append assistant message with tool calls
        messages.append({  # type: ignore[arg-type]
            "role": "assistant",
            "content": message.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in message.tool_calls
            ],
        })

        for tc in message.tool_calls:
            tool_name = tc.function.name
            tool_args = json.loads(tc.function.arguments)

            # ── Approval gate checkpoint ──────────────────
            gate_result: ApprovalResult = check(
                tool_name, tool_args, approval_callback=approval_callback
            )
            risk_color = _RISK_COLORS.get(gate_result.risk.level, "white")

            if verbose:
                console.print(
                    f"  [{risk_color}]▸ {gate_result.risk.level.value}[/{risk_color}] "
                    f"[bold #00ff00]{tool_name}[/bold #00ff00]"
                    f"({json.dumps(tool_args)})"
                )
                console.print(f"    [dim]{gate_result.message}[/dim]")

            if gate_result.status == ApprovalStatus.DENIED:
                # Feed denial back to the LLM as the tool result
                result = f"DENIED: {tool_name} was blocked by the approval gate. Reason: {gate_result.risk.reason}"
                if verbose:
                    console.print(f"    [red]✗ BLOCKED[/red]")
            else:
                # Execute the approved tool
                result = execute_tool(tool_name, tool_args)
                if verbose:
                    display = result[:200] + "..." if len(result) > 200 else result
                    console.print(f"    [dim]← {display}[/dim]")

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })  # type: ignore[typeddict-item]

    return "(Agent reached maximum iteration limit without a final response.)"


if __name__ == "__main__":
    import sys as _sys

    client = OllamaClient()
    if not client.health_check():
        print(
            "\n  [ERROR] Cannot connect to Ollama.\n"
            "  Ensure Ollama is running and the model is pulled.\n"
            "  See SETUP.md for instructions.\n"
        )
        _sys.exit(1)

    auto = "--auto" in _sys.argv
    msg = "What is 2 + 2?"
    if len(_sys.argv) > 1 and _sys.argv[1] != "--auto":
        msg = _sys.argv[1]

    console.print(f"\n[bold #00ff00]> Agent with Approval Gates[/bold #00ff00]")
    console.print(f"[dim]Query: {msg}[/dim]\n")
    result = run_agent_with_approval(msg, auto_mode=auto)
    console.print(f"\n[bold #ffb000]Agent response:[/bold #ffb000] {result}")
