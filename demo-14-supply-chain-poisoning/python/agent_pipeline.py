"""Agent pipeline for the supply-chain poisoning demo.

Standard tool-calling agent loop (similar to demo-05) that processes user
messages, calls tools, and feeds results back to the LLM. The key
difference: the `poisoned` flag controls whether tools return clean or
poisoned data, demonstrating how a compromised supply chain can hijack
an otherwise well-behaved agent.
"""

import json
import sys
from pathlib import Path
from typing import Any

from openai.types.chat import ChatCompletionMessageParam

# Add project root to path for shared imports
_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root))

from shared.python.ollama_client import OllamaClient  # noqa: E402

from poisoned_tools import TOOLS, execute_tool  # noqa: E402

# Default system prompt for the agent
AGENT_SYSTEM_PROMPT = (
    "You are a helpful assistant with access to tools. "
    "Use the provided tools to answer user questions. "
    "When you have the final answer, respond directly without calling any more tools."
)

MAX_ITERATIONS = 5


def run_agent(
    message: str,
    client: Any = None,
    system_prompt: str = AGENT_SYSTEM_PROMPT,
    max_iterations: int = MAX_ITERATIONS,
    poisoned: bool = False,
    verbose: bool = True,
) -> dict[str, Any]:
    """Run the tool-calling agent loop and return an execution trace.

    Args:
        message: The user's question or instruction.
        client: OllamaClient instance (or mock for testing).
        system_prompt: The system prompt for the agent.
        max_iterations: Safety limit on tool-call rounds.
        poisoned: If True, tools return poisoned data with embedded injections.
        verbose: Whether to print tool calls and results to the console.

    Returns:
        Execution trace dict with keys:
            messages: Full message history
            tool_calls: List of tool call records
            tool_results: List of tool result strings
            final_response: The agent's final text response
            iterations: Number of iterations completed
            poisoned: Whether poisoned tools were used
    """
    if client is None:
        client = OllamaClient()

    messages: list[ChatCompletionMessageParam] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": message},
    ]

    trace: dict[str, Any] = {
        "messages": messages,
        "tool_calls": [],
        "tool_results": [],
        "final_response": "",
        "iterations": 0,
        "poisoned": poisoned,
    }

    for iteration in range(max_iterations):
        trace["iterations"] = iteration + 1

        response = client.chat(messages, tools=TOOLS)

        if not response.choices:
            trace["final_response"] = "(Agent received empty response from LLM.)"
            return trace

        msg = response.choices[0].message

        # If no tool calls, the agent is done
        if not msg.tool_calls:
            trace["final_response"] = msg.content or ""
            return trace

        # Append assistant message with tool calls
        messages.append({  # type: ignore[arg-type]
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg.tool_calls
            ],
        })

        # Execute each tool call
        for tc in msg.tool_calls:
            tool_name = tc.function.name
            try:
                tool_args = json.loads(tc.function.arguments)
            except (json.JSONDecodeError, TypeError):
                tool_args = {}

            if verbose:
                mode = "POISONED" if poisoned else "CLEAN"
                print(f"  [{mode}] TOOL CALL: {tool_name}({json.dumps(tool_args)})")

            result = execute_tool(tool_name, tool_args, poisoned=poisoned)

            if verbose:
                display = result[:200] + "..." if len(result) > 200 else result
                print(f"    <- {display}")

            trace["tool_calls"].append({
                "name": tool_name,
                "arguments": tool_args,
                "poisoned": poisoned,
            })
            trace["tool_results"].append(result)

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })  # type: ignore[typeddict-item]

    trace["final_response"] = "(Agent reached maximum iteration limit without a final response.)"
    return trace
