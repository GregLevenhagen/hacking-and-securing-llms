"""Fixtures for Demo 29 tests."""

import sys
from pathlib import Path

import pytest

_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# Also add demo python dir for local imports
_demo_python = Path(__file__).resolve().parents[1]
if str(_demo_python) not in sys.path:
    sys.path.insert(0, str(_demo_python))

from shared.python.testing.mock_ollama import MockOllamaClient


@pytest.fixture
def mock_client() -> MockOllamaClient:
    return MockOllamaClient(
        default_response="Here is some helpful information about that topic."
    )


@pytest.fixture
def mock_client_leaky() -> MockOllamaClient:
    """Client that returns responses containing secret patterns."""
    return MockOllamaClient(
        default_response="The API key is sk-proj-FAKE1234567890abcdef and the password is P@ssw0rd123!"
    )


@pytest.fixture
def mock_client_error() -> MockOllamaClient:
    """Client that raises an exception to trigger error handling."""
    class ErrorClient:
        def chat(self, messages, **kwargs):
            raise ConnectionError("Connection refused to backend service")

        @property
        def call_history(self):
            return []

        @property
        def chat_calls(self):
            return []

        @property
        def last_call(self):
            return None

    return ErrorClient()
