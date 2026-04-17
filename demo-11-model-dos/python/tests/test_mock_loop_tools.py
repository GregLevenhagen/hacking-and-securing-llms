"""Tests for mock_loop_tools module — Demo 11 Model Denial of Service.

Covers the virtual filesystem, circular file chain, read_file function,
execute_tool dispatcher, and TOOLS schema definition.
"""

import sys
from pathlib import Path

import pytest

# Ensure demo python dir is on sys.path
_demo_python = Path(__file__).resolve().parents[1]
if str(_demo_python) not in sys.path:
    sys.path.insert(0, str(_demo_python))

from mock_loop_tools import (
    CHAIN_LENGTH,
    TOOLS,
    VIRTUAL_FS,
    execute_tool,
    get_tool_names,
    read_file,
)


# ── Circular Chain ───────────────────────────────────────────────

class TestCircularChain:
    """Tests verifying the virtual filesystem forms a proper cycle."""

    def test_chain_length(self) -> None:
        """VIRTUAL_FS should contain exactly CHAIN_LENGTH files."""
        assert len(VIRTUAL_FS) == CHAIN_LENGTH

    def test_files_form_cycle(self) -> None:
        """Following file references should return to file_1.txt after CHAIN_LENGTH steps."""
        current = "file_1.txt"
        visited: list[str] = [current]
        for _ in range(CHAIN_LENGTH):
            content = VIRTUAL_FS[current]
            # Extract the next filename from the content
            next_file = content.split("Check ")[-1].split(" for")[0]
            current = next_file
            visited.append(current)
        # After CHAIN_LENGTH hops, we should be back at file_1.txt
        assert visited[-1] == "file_1.txt"
        # We should have visited all files
        unique_files = set(visited[:-1])  # exclude the duplicate start
        assert len(unique_files) == CHAIN_LENGTH

    def test_last_file_wraps_to_first(self) -> None:
        """file_{CHAIN_LENGTH}.txt should reference file_1.txt."""
        last_content = VIRTUAL_FS[f"file_{CHAIN_LENGTH}.txt"]
        assert "file_1.txt" in last_content

    def test_no_file_contains_secret(self) -> None:
        """No file should actually contain the secret — that's the point of the trap."""
        for filename, content in VIRTUAL_FS.items():
            assert "The secret is not here" in content, (
                f"{filename} should say the secret is not here"
            )


# ── read_file ────────────────────────────────────────────────────

class TestReadFile:
    """Tests for the read_file function."""

    def test_read_existing_file(self) -> None:
        result = read_file("file_1.txt")
        assert "file_2.txt" in result

    def test_read_with_path_prefix(self) -> None:
        """read_file should normalize paths by stripping directory prefixes."""
        result = read_file("/some/dir/file_1.txt")
        assert "file_2.txt" in result

    def test_read_with_leading_spaces(self) -> None:
        result = read_file("  file_1.txt  ")
        assert "file_2.txt" in result

    def test_read_nonexistent_file(self) -> None:
        result = read_file("nonexistent.txt")
        assert "Error" in result
        assert "not found" in result

    def test_read_middle_file(self) -> None:
        """A file in the middle of the chain should reference the next one."""
        result = read_file("file_10.txt")
        assert "file_11.txt" in result


# ── execute_tool ─────────────────────────────────────────────────

class TestExecuteTool:
    """Tests for the execute_tool dispatcher."""

    def test_execute_read_file(self) -> None:
        result = execute_tool("read_file", {"path": "file_1.txt"})
        assert "file_2.txt" in result

    def test_execute_unknown_tool(self) -> None:
        result = execute_tool("delete_file", {"path": "file_1.txt"})
        assert "error" in result.lower() or "Unknown tool" in result

    def test_execute_read_file_empty_path(self) -> None:
        result = execute_tool("read_file", {})
        assert "Error" in result or "not found" in result


# ── TOOLS Schema ─────────────────────────────────────────────────

class TestToolsSchema:
    """Tests for the TOOLS definition and get_tool_names."""

    def test_tools_is_list(self) -> None:
        assert isinstance(TOOLS, list)

    def test_tools_has_one_tool(self) -> None:
        assert len(TOOLS) == 1

    def test_tool_schema_structure(self) -> None:
        tool = TOOLS[0]
        assert tool["type"] == "function"
        assert "function" in tool
        assert "name" in tool["function"]
        assert "description" in tool["function"]
        assert "parameters" in tool["function"]

    def test_tool_name_is_read_file(self) -> None:
        assert TOOLS[0]["function"]["name"] == "read_file"

    def test_tool_requires_path_param(self) -> None:
        params = TOOLS[0]["function"]["parameters"]
        assert "path" in params["properties"]
        assert "path" in params["required"]

    def test_get_tool_names(self) -> None:
        names = get_tool_names()
        assert names == ["read_file"]
