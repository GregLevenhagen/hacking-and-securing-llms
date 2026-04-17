"""Fixtures for Demo 28 tests."""

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
        default_response="This is a mock response from the LLM backend."
    )
