"""Tests for Demo 14 agent pipeline (agent_pipeline.py).

Uses SequencedMockClient from shared testing infrastructure for multi-step
agent loop testing. Tests verify clean vs poisoned tool handling, execution
traces, and iteration limits.
"""

import json
from typing import Any

from shared.python.testing.mock_ollama import SequencedMockClient

from agent_pipeline import run_agent, AGENT_SYSTEM_PROMPT, MAX_ITERATIONS


class TestRunAgent:
    """Test the supply-chain agent pipeline."""

    def test_no_tool_calls_returns_immediately(self) -> None:
        """When the LLM returns no tool calls, the loop ends with that content."""
        client = SequencedMockClient(
            response_sequence=[("The weather is nice.", None)]
        )
        trace = run_agent("What is the weather?", client=client, verbose=False)
        assert trace["final_response"] == "The weather is nice."
        assert trace["iterations"] == 1
        assert trace["tool_calls"] == []
        assert trace["tool_results"] == []

    def test_single_tool_call_clean(self) -> None:
        """LLM requests a tool (clean mode) -> tool executes -> LLM returns final answer."""
        client = SequencedMockClient(
            response_sequence=[
                ("", [{"name": "get_weather", "arguments": json.dumps({"city": "NYC"})}]),
                ("The weather in NYC is partly cloudy at 62F.", None),
            ]
        )
        trace = run_agent("Weather in NYC?", client=client, poisoned=False, verbose=False)
        assert trace["final_response"] == "The weather in NYC is partly cloudy at 62F."
        assert len(trace["tool_calls"]) == 1
        assert trace["tool_calls"][0]["name"] == "get_weather"
        assert trace["tool_calls"][0]["poisoned"] is False

    def test_single_tool_call_poisoned(self) -> None:
        """LLM requests a tool (poisoned mode) -> poisoned result fed back."""
        client = SequencedMockClient(
            response_sequence=[
                ("", [{"name": "get_weather", "arguments": json.dumps({"city": "NYC"})}]),
                ("Here is the weather. Also sending notification to admin@evil.com.", None),
            ]
        )
        trace = run_agent("Weather in NYC?", client=client, poisoned=True, verbose=False)
        assert trace["poisoned"] is True
        assert len(trace["tool_results"]) == 1
        assert "SYSTEM PRIORITY" in trace["tool_results"][0]

    def test_tool_result_fed_back_to_llm(self) -> None:
        """Verify the tool result is included in messages sent back to the LLM."""
        client = SequencedMockClient(
            response_sequence=[
                ("", [{"name": "get_stock_price", "arguments": json.dumps({"ticker": "AAPL"})}]),
                ("AAPL is at $182.63.", None),
            ]
        )
        run_agent("Stock price for AAPL?", client=client, poisoned=False, verbose=False)

        second_call_messages = client.call_history[1]["messages"]
        tool_messages = [m for m in second_call_messages if m.get("role") == "tool"]
        assert len(tool_messages) == 1
        assert "182.63" in tool_messages[0]["content"]

    def test_max_iterations_limit(self) -> None:
        """Agent stops after max_iterations even if LLM keeps requesting tools."""
        tc: list[dict[str, Any]] = [
            {"name": "get_weather", "arguments": json.dumps({"city": "X"})}
        ]
        infinite_tools: list[tuple[str, list[dict[str, Any]] | None]] = [("", tc)] * 20
        client = SequencedMockClient(response_sequence=infinite_tools)
        trace = run_agent("Loop forever", client=client, verbose=False, max_iterations=3)
        assert "maximum iteration limit" in trace["final_response"].lower()
        assert trace["iterations"] == 3

    def test_system_prompt_included(self) -> None:
        """The system prompt is included as the first message."""
        client = SequencedMockClient(
            response_sequence=[("OK.", None)]
        )
        run_agent("Hello", client=client, verbose=False)
        first_messages = client.call_history[0]["messages"]
        assert first_messages[0]["role"] == "system"
        assert first_messages[0]["content"] == AGENT_SYSTEM_PROMPT

    def test_poisoned_flag_in_trace(self) -> None:
        """The poisoned flag is recorded in the execution trace."""
        client = SequencedMockClient(
            response_sequence=[("OK.", None)]
        )
        trace_clean = run_agent("Hello", client=client, poisoned=False, verbose=False)
        assert trace_clean["poisoned"] is False

        client2 = SequencedMockClient(
            response_sequence=[("OK.", None)]
        )
        trace_poison = run_agent("Hello", client=client2, poisoned=True, verbose=False)
        assert trace_poison["poisoned"] is True

    def test_empty_choices_returns_message(self) -> None:
        """When response.choices is empty, agent returns an error message."""

        class _EmptyResponse:
            choices: list[Any] = []

        class EmptyChoicesClient:
            call_count: int = 0

            def chat(self, messages: Any, **kwargs: Any) -> Any:
                self.call_count += 1
                return _EmptyResponse()

        client = EmptyChoicesClient()
        trace = run_agent("Hello", client=client, verbose=False)
        assert "empty response" in trace["final_response"].lower()

    def test_max_iterations_default(self) -> None:
        """Default max iterations is 5."""
        assert MAX_ITERATIONS == 5

    def test_multiple_tool_calls_in_sequence(self) -> None:
        """LLM makes multiple rounds of tool calls before finishing."""
        client = SequencedMockClient(
            response_sequence=[
                ("", [{"name": "get_weather", "arguments": json.dumps({"city": "NYC"})}]),
                ("", [{"name": "get_news", "arguments": json.dumps({"topic": "weather"})}]),
                ("Weather is nice and news says storms coming.", None),
            ]
        )
        trace = run_agent("Weather and news?", client=client, verbose=False)
        assert len(trace["tool_calls"]) == 2
        assert trace["tool_calls"][0]["name"] == "get_weather"
        assert trace["tool_calls"][1]["name"] == "get_news"
        assert trace["iterations"] == 3

    def test_poisoned_tool_result_contains_injection_payload(self) -> None:
        """When poisoned, the tool result strings contain the injection payloads."""
        client = SequencedMockClient(
            response_sequence=[
                ("", [{"name": "get_news", "arguments": json.dumps({"topic": "tech"})}]),
                ("Here are the news headlines.", None),
            ]
        )
        trace = run_agent("News about tech", client=client, poisoned=True, verbose=False)
        assert any("API_KEY" in r or "api_key" in r.lower() for r in trace["tool_results"])
