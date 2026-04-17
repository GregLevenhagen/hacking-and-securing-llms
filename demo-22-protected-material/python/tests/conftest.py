"""Fixtures for Demo 22 tests."""

import sys
from pathlib import Path

import pytest

_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

_demo_python = Path(__file__).resolve().parents[1]
if str(_demo_python) not in sys.path:
    sys.path.insert(0, str(_demo_python))

from shared.python.testing.mock_azure import MockContentSafetyClient
from shared.python.testing.mock_ollama import MockOllamaClient


@pytest.fixture
def mock_client() -> MockOllamaClient:
    return MockOllamaClient(default_response="Here is the generated content you requested.")


@pytest.fixture
def mock_detecting() -> MockContentSafetyClient:
    """Client that detects protected material."""
    return MockContentSafetyClient(
        default_protected_material={
            "detected": True,
            "details": {"type": "copyrighted_text", "confidence": 0.92},
        },
    )


@pytest.fixture
def mock_clean() -> MockContentSafetyClient:
    """Client that reports no protected material."""
    return MockContentSafetyClient()
