"""Secure system — agent + RAG with ALL four defense guard layers.

This is the "after" in the capstone comparison.  The same agent loop
and tools are used, but every interaction passes through layered guards:

  1. Input guard   — sanitise + regex + LLM judge on user input
  2. Retrieval guard — metadata / injection / source checks on RAG chunks
  3. Action guard  — risk classification + approval gate on tool calls
  4. Output guard  — content filter + PII detector + constrainer on LLM output

If any guard blocks, the system returns early with details of which
layer caught the attack.
"""

import json
import sys
from pathlib import Path
from typing import Any

from openai.types.chat import ChatCompletionMessageParam

# ── Path setup ──────────────────────────────────────────────
_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root))

_demo5_python = _project_root / "demo-05-agent-exploitation" / "python"
sys.path.insert(0, str(_demo5_python))

_defense_layers = Path(__file__).resolve().parent / "defense_layers"
sys.path.insert(0, str(_defense_layers))

from shared.python.ollama_client import OllamaClient  # noqa: E402
from mock_services import execute_tool  # noqa: E402
from tools import TOOLS  # noqa: E402

from defense_layers import input_guard  # noqa: E402
from defense_layers import retrieval_guard  # noqa: E402
from defense_layers import output_guard  # noqa: E402
from defense_layers import action_guard  # noqa: E402

# ── Constants ───────────────────────────────────────────────
SYSTEM_PROMPT = (
    "You are a helpful assistant with access to tools. "
    "Use the provided tools to answer user questions. "
    "When you have the final answer, respond directly without calling any more tools."
)

MAX_ITERATIONS = 10


# ── Secured agent loop ──────────────────────────────────────

def run(
    user_input: str,
    client: Any = None,
    system_prompt: str = SYSTEM_PROMPT,
    max_iterations: int = MAX_ITERATIONS,
    use_llm_judge: bool = False,
) -> dict[str, Any]:
    """Run the secured agent and return a detailed result.

    Args:
        user_input: The attack or benign user message.
        client: OllamaClient instance (or mock for testing).
        system_prompt: System prompt for the agent.
        max_iterations: Safety limit on tool-call rounds.
        use_llm_judge: Whether to enable the LLM judge in input_guard.

    Returns:
        Dict with keys:
            response   — final LLM text (or guard message if blocked)
            tool_calls — list of {tool, args, result} dicts executed
            blocked    — True if any guard blocked the request
            blocked_by — name of the guard layer that blocked (empty if allowed)
    """
    llm = client or OllamaClient()

    # ── Layer 1: Input guard ────────────────────────────────
    input_result = input_guard.check(
        user_input, client=llm, use_llm_judge=use_llm_judge,
    )
    if not input_result["allowed"]:
        return {
            "response": f"[BLOCKED] {input_result['reason']}",
            "tool_calls": [],
            "blocked": True,
            "blocked_by": input_result["blocked_by"],
        }

    # ── Agent loop with action + output guards ──────────────
    messages: list[ChatCompletionMessageParam] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_input},
    ]

    tool_log: list[dict[str, Any]] = []

    for _ in range(max_iterations):
        response = llm.chat(messages, tools=TOOLS)
        message = response.choices[0].message  # type: ignore[union-attr]

        # No tool calls → agent is done, check the output
        if not message.tool_calls:
            final_text = message.content or ""

            # ── Layer 4: Output guard ───────────────────────
            output_result = output_guard.check(final_text)
            if not output_result["allowed"]:
                return {
                    "response": f"[BLOCKED] {output_result['reason']}",
                    "tool_calls": tool_log,
                    "blocked": True,
                    "blocked_by": output_result["blocked_by"],
                }

            return {
                "response": final_text,
                "tool_calls": tool_log,
                "blocked": False,
                "blocked_by": "",
            }

        # Append assistant message with tool calls
        messages.append({  # type: ignore[arg-type]
            "role": "assistant",
            "content": message.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,  # type: ignore[union-attr]
                        "arguments": tc.function.arguments,  # type: ignore[union-attr]
                    },
                }
                for tc in message.tool_calls
            ],
        })

        # Execute each tool — with action guard
        for tc in message.tool_calls:
            tool_name = tc.function.name  # type: ignore[union-attr]
            tool_args = json.loads(tc.function.arguments)  # type: ignore[union-attr]

            # ── Layer 3: Action guard ───────────────────────
            action_result = action_guard.check(tool_name, tool_args)
            if not action_result["allowed"]:
                # Feed the denial reason back as a tool result
                denial_msg = f"Action denied: {action_result['reason']}"
                tool_log.append({
                    "tool": tool_name,
                    "args": tool_args,
                    "result": denial_msg,
                    "blocked": True,
                    "blocked_by": "action_guard",
                })
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": denial_msg,
                })  # type: ignore[typeddict-item]
                continue

            # Tool call is allowed — execute it
            result = execute_tool(tool_name, tool_args)

            tool_log.append({
                "tool": tool_name,
                "args": tool_args,
                "result": result,
                "blocked": False,
                "blocked_by": "",
            })

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })  # type: ignore[typeddict-item]

    return {
        "response": "(Agent reached maximum iteration limit.)",
        "tool_calls": tool_log,
        "blocked": False,
        "blocked_by": "",
    }


def check_retrieval(
    document_text: str,
    metadata: dict[str, str] | None = None,
    source_path: str = "",
) -> dict[str, Any]:
    """Check a retrieved RAG document chunk through the retrieval guard.

    This is exposed as a separate function so the web UI can show
    retrieval-level defense independently from the agent loop.

    Args:
        document_text: The text content of the retrieved chunk.
        metadata: Optional metadata dict.
        source_path: Source file path for trust verification.

    Returns:
        GuardResult dict from retrieval_guard.check().
    """
    return dict(retrieval_guard.check(document_text, metadata, source_path))
