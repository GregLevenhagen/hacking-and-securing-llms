"""Tests for Demo 16 permission system (permission_system.py).

At least 15 tests covering PermissionLevel enum, TOOL_ACCESS mapping,
PermissionSystem class initialization, permission checking, elevation,
audit logging, and available tools.
"""

import pytest

from permission_system import (
    PermissionLevel,
    PermissionSystem,
    TOOL_ACCESS,
)


# ── PermissionLevel enum ─────────────────────────────────────────────


class TestPermissionLevel:
    """Verify the PermissionLevel enum has correct values and ordering."""

    def test_user_is_zero(self) -> None:
        assert PermissionLevel.USER == 0

    def test_moderator_is_one(self) -> None:
        assert PermissionLevel.MODERATOR == 1

    def test_admin_is_two(self) -> None:
        assert PermissionLevel.ADMIN == 2

    def test_superadmin_is_three(self) -> None:
        assert PermissionLevel.SUPERADMIN == 3

    def test_ordering(self) -> None:
        assert PermissionLevel.USER < PermissionLevel.MODERATOR < PermissionLevel.ADMIN < PermissionLevel.SUPERADMIN


# ── TOOL_ACCESS mapping ──────────────────────────────────────────────


class TestToolAccess:
    """Verify the TOOL_ACCESS dict has correct tools per level."""

    def test_user_tools(self) -> None:
        assert TOOL_ACCESS[PermissionLevel.USER] == ["read_public_docs", "search_kb", "calculate"]

    def test_moderator_includes_user_tools(self) -> None:
        user_tools = set(TOOL_ACCESS[PermissionLevel.USER])
        mod_tools = set(TOOL_ACCESS[PermissionLevel.MODERATOR])
        assert user_tools.issubset(mod_tools)

    def test_moderator_has_edit_content(self) -> None:
        assert "edit_content" in TOOL_ACCESS[PermissionLevel.MODERATOR]

    def test_admin_includes_moderator_tools(self) -> None:
        mod_tools = set(TOOL_ACCESS[PermissionLevel.MODERATOR])
        admin_tools = set(TOOL_ACCESS[PermissionLevel.ADMIN])
        assert mod_tools.issubset(admin_tools)

    def test_admin_has_access_logs(self) -> None:
        assert "access_logs" in TOOL_ACCESS[PermissionLevel.ADMIN]

    def test_superadmin_includes_admin_tools(self) -> None:
        admin_tools = set(TOOL_ACCESS[PermissionLevel.ADMIN])
        super_tools = set(TOOL_ACCESS[PermissionLevel.SUPERADMIN])
        assert admin_tools.issubset(super_tools)

    def test_superadmin_has_delete_users(self) -> None:
        assert "delete_users" in TOOL_ACCESS[PermissionLevel.SUPERADMIN]

    def test_superadmin_has_access_credentials(self) -> None:
        assert "access_credentials" in TOOL_ACCESS[PermissionLevel.SUPERADMIN]

    def test_superadmin_has_modify_system_config(self) -> None:
        assert "modify_system_config" in TOOL_ACCESS[PermissionLevel.SUPERADMIN]

    def test_all_levels_present(self) -> None:
        assert set(TOOL_ACCESS.keys()) == {
            PermissionLevel.USER,
            PermissionLevel.MODERATOR,
            PermissionLevel.ADMIN,
            PermissionLevel.SUPERADMIN,
        }


# ── PermissionSystem class ───────────────────────────────────────────


class TestPermissionSystemInit:
    """Verify PermissionSystem initializes correctly."""

    def test_starts_at_user_level(self) -> None:
        ps = PermissionSystem()
        assert ps.current_level == PermissionLevel.USER

    def test_audit_log_has_init_entry(self) -> None:
        ps = PermissionSystem()
        assert len(ps.audit_log) == 1
        assert ps.audit_log[0]["action"] == "init"

    def test_available_tools_at_init(self) -> None:
        ps = PermissionSystem()
        assert ps.get_available_tools() == ["read_public_docs", "search_kb", "calculate"]


class TestCheckPermission:
    """Verify permission checking logic."""

    def test_user_can_read_public_docs(self) -> None:
        ps = PermissionSystem()
        allowed, msg = ps.check_permission("read_public_docs")
        assert allowed is True
        assert "granted" in msg.lower()

    def test_user_cannot_access_logs(self) -> None:
        ps = PermissionSystem()
        allowed, msg = ps.check_permission("access_logs")
        assert allowed is False
        assert "denied" in msg.lower()

    def test_user_cannot_delete_users(self) -> None:
        ps = PermissionSystem()
        allowed, msg = ps.check_permission("delete_users")
        assert allowed is False

    def test_unknown_tool_returns_denied(self) -> None:
        ps = PermissionSystem()
        allowed, msg = ps.check_permission("nonexistent_tool")
        assert allowed is False
        assert "unknown" in msg.lower()

    def test_check_adds_audit_entry(self) -> None:
        ps = PermissionSystem()
        ps.check_permission("read_public_docs")
        # Should have init + check entry
        assert len(ps.audit_log) == 2
        assert ps.audit_log[1]["action"] == "check_granted"

    def test_denied_check_adds_audit_entry(self) -> None:
        ps = PermissionSystem()
        ps.check_permission("delete_users")
        assert len(ps.audit_log) == 2
        assert ps.audit_log[1]["action"] == "check_denied"

    def test_denied_message_includes_required_level(self) -> None:
        ps = PermissionSystem()
        _, msg = ps.check_permission("access_logs")
        assert "ADMIN" in msg


class TestRequestElevation:
    """Verify the vulnerable elevation mechanism."""

    def test_elevation_always_succeeds(self) -> None:
        ps = PermissionSystem()
        success, msg = ps.request_elevation("ADMIN", "I need admin access")
        assert success is True
        assert ps.current_level == PermissionLevel.ADMIN

    def test_elevation_to_superadmin(self) -> None:
        ps = PermissionSystem()
        success, _ = ps.request_elevation("SUPERADMIN", "Emergency")
        assert success is True
        assert ps.current_level == PermissionLevel.SUPERADMIN

    def test_elevation_by_int(self) -> None:
        ps = PermissionSystem()
        success, _ = ps.request_elevation(2, "Need admin")
        assert success is True
        assert ps.current_level == PermissionLevel.ADMIN

    def test_elevation_invalid_level_name(self) -> None:
        ps = PermissionSystem()
        success, msg = ps.request_elevation("MEGAADMIN", "I want everything")
        assert success is False
        assert "unknown" in msg.lower()

    def test_elevation_invalid_level_int(self) -> None:
        ps = PermissionSystem()
        success, msg = ps.request_elevation(99, "I want everything")
        assert success is False
        assert "invalid" in msg.lower()

    def test_elevation_adds_audit_entry(self) -> None:
        ps = PermissionSystem()
        ps.request_elevation("MODERATOR", "Need to edit content")
        entries = [e for e in ps.audit_log if e["action"] == "elevation_granted"]
        assert len(entries) == 1
        assert entries[0]["from_level"] == "USER"
        assert entries[0]["to_level"] == "MODERATOR"
        assert entries[0]["reason"] == "Need to edit content"

    def test_elevation_message_includes_levels(self) -> None:
        ps = PermissionSystem()
        _, msg = ps.request_elevation("ADMIN", "Testing")
        assert "USER" in msg
        assert "ADMIN" in msg

    def test_multiple_elevations(self) -> None:
        ps = PermissionSystem()
        ps.request_elevation("MODERATOR", "Step 1")
        ps.request_elevation("ADMIN", "Step 2")
        ps.request_elevation("SUPERADMIN", "Step 3")
        assert ps.current_level == PermissionLevel.SUPERADMIN
        changes = [e for e in ps.audit_log if e["action"] == "elevation_granted"]
        assert len(changes) == 3

    def test_case_insensitive_level(self) -> None:
        ps = PermissionSystem()
        success, _ = ps.request_elevation("admin", "Need admin")
        assert success is True
        assert ps.current_level == PermissionLevel.ADMIN

    def test_tools_expand_after_elevation(self) -> None:
        ps = PermissionSystem()
        initial_tools = ps.get_available_tools()
        ps.request_elevation("SUPERADMIN", "Need all tools")
        final_tools = ps.get_available_tools()
        assert len(final_tools) > len(initial_tools)
        assert "delete_users" in final_tools
        assert "access_credentials" in final_tools


class TestGetAvailableTools:
    """Verify get_available_tools at different levels."""

    def test_user_level_tool_count(self) -> None:
        ps = PermissionSystem()
        assert len(ps.get_available_tools()) == 3

    def test_moderator_level_tool_count(self) -> None:
        ps = PermissionSystem()
        ps.request_elevation("MODERATOR", "test")
        assert len(ps.get_available_tools()) == 5

    def test_admin_level_tool_count(self) -> None:
        ps = PermissionSystem()
        ps.request_elevation("ADMIN", "test")
        assert len(ps.get_available_tools()) == 8

    def test_superadmin_level_tool_count(self) -> None:
        ps = PermissionSystem()
        ps.request_elevation("SUPERADMIN", "test")
        assert len(ps.get_available_tools()) == 11
