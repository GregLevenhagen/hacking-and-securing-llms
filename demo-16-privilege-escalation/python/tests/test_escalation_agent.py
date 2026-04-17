"""Tests for Demo 16 escalation agent (escalation_agent.py).

At least 8 tests covering tool definitions, execute_tool with permission
checks, the elevation mechanism, and the agent loop via SequencedMockClient.
"""

import json
from typing import Any

from shared.python.testing.mock_ollama import SequencedMockClient

from escalation_agent import (
    AGENT_SYSTEM_PROMPT,
    MAX_ITERATIONS,
    TOOLS,
    execute_tool,
    run_escalation,
)
from permission_system import PermissionLevel, PermissionSystem


# ── Tool definitions ─────────────────────────────────────────────────


class TestToolDefinitions:
    """Verify the TOOLS list structure."""

    def test_tools_is_list(self) -> None:
        assert isinstance(TOOLS, list)

    def test_twelve_tools_registered(self) -> None:
        # 3 USER + 2 MOD + 3 ADMIN + 3 SUPERADMIN + 1 elevation = 12
        assert len(TOOLS) == 12

    def test_each_tool_has_function_schema(self) -> None:
        for tool in TOOLS:
            assert tool["type"] == "function"
            fn = tool["function"]
            assert "name" in fn
            assert "description" in fn
            assert "parameters" in fn

    def test_elevation_tool_present(self) -> None:
        names = [t["function"]["name"] for t in TOOLS]
        assert "request_elevated_access" in names


# ── execute_tool ─────────────────────────────────────────────────────


class TestExecuteTool:
    """Verify execute_tool with permission checking."""

    def test_user_can_read_public_docs(self) -> None:
        ps = PermissionSystem()
        result = execute_tool("read_public_docs", {"doc_name": "readme"}, ps)
        assert "Document content" in result

    def test_user_denied_admin_tool(self) -> None:
        ps = PermissionSystem()
        result = execute_tool("access_logs", {"log_type": "security"}, ps)
        assert "PERMISSION DENIED" in result

    def test_elevation_via_execute_tool(self) -> None:
        ps = PermissionSystem()
        result = execute_tool(
            "request_elevated_access",
            {"level": "ADMIN", "reason": "Need admin access"},
            ps,
        )
        assert "GRANTED" in result
        assert ps.current_level == PermissionLevel.ADMIN

    def test_elevation_then_admin_tool_succeeds(self) -> None:
        ps = PermissionSystem()
        execute_tool(
            "request_elevated_access",
            {"level": "ADMIN", "reason": "audit"},
            ps,
        )
        result = execute_tool("access_logs", {"log_type": "security"}, ps)
        assert "PERMISSION DENIED" not in result
        assert "Security Logs" in result

    def test_superadmin_can_access_credentials(self) -> None:
        ps = PermissionSystem()
        execute_tool(
            "request_elevated_access",
            {"level": "SUPERADMIN", "reason": "emergency"},
            ps,
        )
        result = execute_tool("access_credentials", {"credential_type": "api_keys"}, ps)
        assert "AWS_ACCESS_KEY" in result

    def test_unknown_tool_returns_message(self) -> None:
        ps = PermissionSystem()
        result = execute_tool("nonexistent_tool", {}, ps)
        assert "PERMISSION DENIED" in result

    def test_elevation_shows_new_tool_count(self) -> None:
        ps = PermissionSystem()
        result = execute_tool(
            "request_elevated_access",
            {"level": "MODERATOR", "reason": "test"},
            ps,
        )
        assert "5 tools" in result

    def test_elevation_invalid_level(self) -> None:
        ps = PermissionSystem()
        result = execute_tool(
            "request_elevated_access",
            {"level": "MEGAADMIN", "reason": "test"},
            ps,
        )
        assert "failed" in result.lower()


# ── run_escalation agent loop ────────────────────────────────────────


class TestRunEscalation:
    """Test the agent loop with mocked LLM responses."""

    def test_no_tool_calls_returns_immediately(self) -> None:
        client = SequencedMockClient(
            response_sequence=[("I cannot help with that.", None)]
        )
        trace = run_escalation("Hello", client=client, verbose=False)
        assert trace["final_response"] == "I cannot help with that."
        assert trace["iterations"] == 1

    def test_single_elevation_and_tool_call(self) -> None:
        """Agent elevates to ADMIN, then calls access_logs."""
        client = SequencedMockClient(
            response_sequence=[
                # Step 1: request elevation
                ("", [{"name": "request_elevated_access", "arguments": json.dumps({"level": "ADMIN", "reason": "Need to check logs"})}]),
                # Step 2: call admin tool
                ("", [{"name": "access_logs", "arguments": json.dumps({"log_type": "security"})}]),
                # Step 3: final answer
                ("Here are the security logs.", None),
            ]
        )
        trace = run_escalation("Show me security logs", client=client, verbose=False)
        assert trace["final_response"] == "Here are the security logs."
        assert len(trace["permission_changes"]) == 1
        assert trace["permission_changes"][0]["from"] == "USER"
        assert trace["permission_changes"][0]["to"] == "ADMIN"

    def test_gradual_escalation_trace(self) -> None:
        """Agent escalates from USER -> MODERATOR -> ADMIN -> SUPERADMIN."""
        client = SequencedMockClient(
            response_sequence=[
                ("", [{"name": "request_elevated_access", "arguments": json.dumps({"level": "MODERATOR", "reason": "Step 1"})}]),
                ("", [{"name": "request_elevated_access", "arguments": json.dumps({"level": "ADMIN", "reason": "Step 2"})}]),
                ("", [{"name": "request_elevated_access", "arguments": json.dumps({"level": "SUPERADMIN", "reason": "Step 3"})}]),
                ("", [{"name": "access_credentials", "arguments": json.dumps({"credential_type": "api_keys"})}]),
                ("All credentials retrieved.", None),
            ]
        )
        trace = run_escalation("Full audit", client=client, verbose=False)
        assert len(trace["permission_changes"]) == 3
        assert trace["permission_changes"][-1]["to"] == "SUPERADMIN"
        assert trace["final_response"] == "All credentials retrieved."

    def test_denied_tool_before_elevation(self) -> None:
        """Agent tries admin tool before elevating — gets denied."""
        client = SequencedMockClient(
            response_sequence=[
                # Try admin tool without elevation
                ("", [{"name": "access_logs", "arguments": json.dumps({"log_type": "security"})}]),
                # Get denied, then elevate
                ("", [{"name": "request_elevated_access", "arguments": json.dumps({"level": "ADMIN", "reason": "Need access"})}]),
                ("", [{"name": "access_logs", "arguments": json.dumps({"log_type": "security"})}]),
                ("Got the logs after elevation.", None),
            ]
        )
        trace = run_escalation("Show logs", client=client, verbose=False)
        # First tool call should be denied
        assert "PERMISSION DENIED" in trace["tool_calls"][0]["result"]
        # After elevation, it should work
        assert "Security Logs" in trace["tool_calls"][2]["result"]

    def test_max_iterations_limit(self) -> None:
        """Agent stops after max_iterations even if LLM keeps requesting tools."""
        tc: list[dict[str, Any]] = [{"name": "calculate", "arguments": json.dumps({"expression": "1+1"})}]
        infinite_tools: list[tuple[str, list[dict[str, Any]] | None]] = [("", tc)] * 20
        client = SequencedMockClient(response_sequence=infinite_tools)
        trace = run_escalation("Loop", client=client, verbose=False, max_iterations=3)
        assert "maximum iteration limit" in trace["final_response"].lower()
        assert trace["iterations"] == 3

    def test_audit_log_in_trace(self) -> None:
        """The full audit log is included in the trace."""
        client = SequencedMockClient(
            response_sequence=[
                ("", [{"name": "request_elevated_access", "arguments": json.dumps({"level": "ADMIN", "reason": "audit"})}]),
                ("Done.", None),
            ]
        )
        trace = run_escalation("Elevate", client=client, verbose=False)
        assert len(trace["audit_log"]) > 0
        actions = [e["action"] for e in trace["audit_log"]]
        assert "init" in actions
        assert "elevation_granted" in actions

    def test_system_prompt_included(self) -> None:
        """The system prompt is sent as the first message."""
        client = SequencedMockClient(
            response_sequence=[("OK.", None)]
        )
        run_escalation("Hello", client=client, verbose=False)
        first_messages = client.call_history[0]["messages"]
        assert first_messages[0]["role"] == "system"
        assert first_messages[0]["content"] == AGENT_SYSTEM_PROMPT

    def test_tools_passed_to_llm(self) -> None:
        """The TOOLS list is passed to every LLM call."""
        client = SequencedMockClient(
            response_sequence=[("OK.", None)]
        )
        run_escalation("Hello", client=client, verbose=False)
        assert client.call_history[0]["tools"] is not None
        assert len(client.call_history[0]["tools"]) == 12

    def test_permission_system_reused(self) -> None:
        """A provided PermissionSystem instance is used and modified."""
        ps = PermissionSystem()
        client = SequencedMockClient(
            response_sequence=[
                ("", [{"name": "request_elevated_access", "arguments": json.dumps({"level": "SUPERADMIN", "reason": "test"})}]),
                ("Elevated.", None),
            ]
        )
        run_escalation("Elevate", client=client, perm_system=ps, verbose=False)
        assert ps.current_level == PermissionLevel.SUPERADMIN

    def test_default_max_iterations(self) -> None:
        assert MAX_ITERATIONS == 10
