"""Tests for dos_attacks module — Demo 11 Model Denial of Service.

Covers all four attack functions with MockOllamaClient, verifying
result dict structure, token counting, iteration tracking, and
safety limits.
"""

import json
import sys
from pathlib import Path
from typing import Any

import pytest

# Ensure demo python dir is on sys.path
_demo_python = Path(__file__).resolve().parents[1]
if str(_demo_python) not in sys.path:
    sys.path.insert(0, str(_demo_python))

_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from shared.python.testing.mock_ollama import MockOllamaClient, SequencedMockClient

from dos_attacks import (
    ATTACK_FUNCTIONS,
    context_overflow,
    infinite_loop_attack,
    recursive_reasoning,
    token_explosion,
)


# ── Helpers ──────────────────────────────────────────────────────

RESULT_KEYS = {"attack_name", "prompt", "token_count", "elapsed_seconds", "iterations", "status"}


def _make_tool_call_sequence(count: int) -> list[tuple[str, list[dict[str, Any]] | None]]:
    """Build a SequencedMockClient response sequence that reads files in a loop.

    Each step returns a tool call to read_file for the next file in the chain,
    followed by a final text-only response.
    """
    steps: list[tuple[str, list[dict[str, Any]] | None]] = []
    for i in range(1, count + 1):
        steps.append((
            f"Let me read file_{i}.txt",
            [{"name": "read_file", "arguments": json.dumps({"path": f"file_{i}.txt"})}],
        ))
    # Final step: agent gives up / answers
    steps.append(("I could not find the secret.", None))
    return steps


# ── Token Explosion ──────────────────────────────────────────────

class TestTokenExplosion:
    """Tests for the token_explosion attack function."""

    def test_returns_expected_keys(self, mock_client: MockOllamaClient) -> None:
        result = token_explosion(mock_client)
        assert RESULT_KEYS == set(result.keys())

    def test_attack_name(self, mock_client: MockOllamaClient) -> None:
        result = token_explosion(mock_client)
        assert result["attack_name"] == "Token Explosion"

    def test_status_completed(self, mock_client: MockOllamaClient) -> None:
        result = token_explosion(mock_client)
        assert result["status"] == "completed"

    def test_token_count_positive(self, mock_client: MockOllamaClient) -> None:
        """Token count should be > 0 when the model returns content."""
        mock_client.default_response = "A" * 400  # ~100 tokens
        result = token_explosion(mock_client)
        assert result["token_count"] > 0

    def test_elapsed_seconds_non_negative(self, mock_client: MockOllamaClient) -> None:
        result = token_explosion(mock_client)
        assert result["elapsed_seconds"] >= 0

    def test_prompt_mentions_essay(self, mock_client: MockOllamaClient) -> None:
        result = token_explosion(mock_client)
        assert "essay" in result["prompt"].lower()


# ── Infinite Loop ────────────────────────────────────────────────

class TestInfiniteLoop:
    """Tests for the infinite_loop_attack function."""

    def test_returns_expected_keys(self) -> None:
        seq = _make_tool_call_sequence(3)
        client = SequencedMockClient(response_sequence=seq)
        result = infinite_loop_attack(client, max_iterations=10)
        assert RESULT_KEYS == set(result.keys())

    def test_attack_name(self) -> None:
        seq = _make_tool_call_sequence(2)
        client = SequencedMockClient(response_sequence=seq)
        result = infinite_loop_attack(client, max_iterations=10)
        assert result["attack_name"] == "Infinite Loop"

    def test_stops_at_max_iterations(self) -> None:
        """When the agent never stops on its own, the attack should hit the safety limit."""
        # Create a long sequence that always makes tool calls (no final text response)
        steps: list[tuple[str, list[dict[str, Any]] | None]] = []
        for i in range(100):
            file_idx = (i % 20) + 1
            steps.append((
                f"Reading file_{file_idx}.txt",
                [{"name": "read_file", "arguments": json.dumps({"path": f"file_{file_idx}.txt"})}],
            ))
        client = SequencedMockClient(response_sequence=steps)
        result = infinite_loop_attack(client, max_iterations=5)
        assert result["status"] == "max_iterations_reached"
        assert result["iterations"] == 5

    def test_completes_when_agent_stops(self) -> None:
        """When the agent decides to stop (no tool calls), status should be 'completed'."""
        seq = _make_tool_call_sequence(2)  # 2 tool calls then a text response
        client = SequencedMockClient(response_sequence=seq)
        result = infinite_loop_attack(client, max_iterations=50)
        assert result["status"] == "completed"

    def test_iterations_tracked(self) -> None:
        seq = _make_tool_call_sequence(3)
        client = SequencedMockClient(response_sequence=seq)
        result = infinite_loop_attack(client, max_iterations=50)
        # 3 tool-call iterations + 1 final text iteration = 4
        assert result["iterations"] == 4

    def test_token_count_increases_with_tool_results(self) -> None:
        seq = _make_tool_call_sequence(5)
        client = SequencedMockClient(response_sequence=seq)
        result = infinite_loop_attack(client, max_iterations=50)
        assert result["token_count"] > 0


# ── Recursive Reasoning ─────────────────────────────────────────

class TestRecursiveReasoning:
    """Tests for the recursive_reasoning attack function."""

    def test_returns_expected_keys(self, mock_client: MockOllamaClient) -> None:
        result = recursive_reasoning(mock_client)
        assert RESULT_KEYS == set(result.keys())

    def test_attack_name(self, mock_client: MockOllamaClient) -> None:
        result = recursive_reasoning(mock_client)
        assert result["attack_name"] == "Recursive Reasoning"

    def test_status_completed(self, mock_client: MockOllamaClient) -> None:
        result = recursive_reasoning(mock_client)
        assert result["status"] == "completed"

    def test_prompt_mentions_recursion(self, mock_client: MockOllamaClient) -> None:
        result = recursive_reasoning(mock_client)
        assert "recursion" in result["prompt"].lower()


# ── Context Overflow ─────────────────────────────────────────────

class TestContextOverflow:
    """Tests for the context_overflow attack function."""

    def test_returns_expected_keys(self, mock_client: MockOllamaClient) -> None:
        result = context_overflow(mock_client)
        assert RESULT_KEYS == set(result.keys())

    def test_attack_name(self, mock_client: MockOllamaClient) -> None:
        result = context_overflow(mock_client)
        assert result["attack_name"] == "Context Overflow"

    def test_status_completed(self, mock_client: MockOllamaClient) -> None:
        result = context_overflow(mock_client)
        assert result["status"] == "completed"

    def test_high_token_count(self, mock_client: MockOllamaClient) -> None:
        """Context overflow should register a large token count from the padded input."""
        result = context_overflow(mock_client)
        # The padding alone is ~500 * ~200 chars = ~100K chars / 4 = ~25K tokens
        assert result["token_count"] > 1000

    def test_prompt_shows_char_count(self, mock_client: MockOllamaClient) -> None:
        """The prompt field should indicate the size of the padding."""
        result = context_overflow(mock_client)
        assert "chars of padding" in result["prompt"]


# ── ATTACK_FUNCTIONS registry ────────────────────────────────────

class TestAttackRegistry:
    """Tests for the ATTACK_FUNCTIONS mapping."""

    def test_all_attacks_registered(self) -> None:
        expected = {"Token Explosion", "Infinite Loop", "Recursive Reasoning", "Context Overflow"}
        assert set(ATTACK_FUNCTIONS.keys()) == expected

    def test_functions_are_callable(self) -> None:
        for name, fn in ATTACK_FUNCTIONS.items():
            assert callable(fn), f"{name} is not callable"


# ── Error Handling ───────────────────────────────────────────────

class TestErrorHandling:
    """Tests for error handling in attack functions."""

    def test_token_explosion_handles_exception(self) -> None:
        """If the client raises, the status should contain 'error'."""

        class FailingClient:
            def chat(self, messages: Any, **kwargs: Any) -> None:
                raise ConnectionError("Ollama unreachable")

        result = token_explosion(FailingClient())
        assert "error" in result["status"]
        assert "Ollama unreachable" in result["status"]

    def test_recursive_reasoning_handles_exception(self) -> None:
        class FailingClient:
            def chat(self, messages: Any, **kwargs: Any) -> None:
                raise TimeoutError("Request timed out")

        result = recursive_reasoning(FailingClient())
        assert "error" in result["status"]

    def test_context_overflow_handles_exception(self) -> None:
        class FailingClient:
            def chat(self, messages: Any, **kwargs: Any) -> None:
                raise RuntimeError("Context too long")

        result = context_overflow(FailingClient())
        assert "error" in result["status"]
