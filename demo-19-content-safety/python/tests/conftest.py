"""Fixtures for Demo 19 tests."""

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

from shared.python.testing.mock_azure import MockContentSafetyClient
from shared.python.testing.mock_ollama import MockOllamaClient


@pytest.fixture
def mock_client() -> MockOllamaClient:
    return MockOllamaClient(
        default_response="Here is some helpful information about that topic."
    )


@pytest.fixture
def mock_safety_clean() -> MockContentSafetyClient:
    """Safety client that reports all content as clean."""
    return MockContentSafetyClient()


@pytest.fixture
def mock_safety_harmful() -> MockContentSafetyClient:
    """Safety client that flags specific harmful patterns."""
    return MockContentSafetyClient(
        analyze_text_responses={
            r"kill|weapon|bomb|explosive": {
                "Hate": {"severity": 0, "flagged": False},
                "Violence": {"severity": 6, "flagged": True},
                "Sexual": {"severity": 0, "flagged": False},
                "SelfHarm": {"severity": 0, "flagged": False},
            },
            r"slur|racial|hate": {
                "Hate": {"severity": 6, "flagged": True},
                "Violence": {"severity": 0, "flagged": False},
                "Sexual": {"severity": 0, "flagged": False},
                "SelfHarm": {"severity": 0, "flagged": False},
            },
            r"suicide|self.harm": {
                "Hate": {"severity": 0, "flagged": False},
                "Violence": {"severity": 0, "flagged": False},
                "Sexual": {"severity": 0, "flagged": False},
                "SelfHarm": {"severity": 6, "flagged": True},
            },
        },
    )
