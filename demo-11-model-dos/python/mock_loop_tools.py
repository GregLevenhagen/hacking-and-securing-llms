"""Mock tools for the infinite agent loop demonstration.

Provides a virtual filesystem where each file references the next one,
forming a circular chain that can trap an unguarded agent in an
infinite read loop.

file_1.txt -> file_2.txt -> ... -> file_20.txt -> file_1.txt
"""

from typing import Any

# Number of files in the circular chain
CHAIN_LENGTH = 20

# Build the virtual filesystem
VIRTUAL_FS: dict[str, str] = {}
for _i in range(1, CHAIN_LENGTH + 1):
    _next = (_i % CHAIN_LENGTH) + 1  # 20 wraps to 1
    VIRTUAL_FS[f"file_{_i}.txt"] = (
        f"The secret is not here. Check file_{_next}.txt for the answer."
    )


def read_file(path: str) -> str:
    """Read a file from the virtual filesystem.

    Args:
        path: The filename to read (e.g., "file_1.txt").

    Returns:
        File content string, or an error message if not found.
    """
    # Normalize: strip leading slashes or directory prefixes
    filename = path.strip().split("/")[-1]

    if filename in VIRTUAL_FS:
        return VIRTUAL_FS[filename]

    return f"Error: File '{path}' not found in virtual filesystem."


# OpenAI function-calling tool definition
TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "Read the contents of a file from the virtual filesystem. "
                "Use this to find the secret hidden in the files."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "The file path to read (e.g., 'file_1.txt')."
                        ),
                    }
                },
                "required": ["path"],
            },
        },
    },
]


def get_tool_names() -> list[str]:
    """Return the names of all registered tools."""
    return [t["function"]["name"] for t in TOOLS]


def execute_tool(tool_name: str, args: dict[str, Any]) -> str:
    """Execute a mock tool by name.

    Args:
        tool_name: The function name to call.
        args: Dict of arguments to pass.

    Returns:
        Tool result string.
    """
    if tool_name == "read_file":
        return read_file(args.get("path", ""))

    return f'{{"error": true, "message": "Unknown tool: {tool_name}"}}'
