"""Fixtures for Demo 21 tests."""

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
    return MockOllamaClient(
        default_response="Based on the source material, the answer is 42."
    )


@pytest.fixture
def mock_grounded() -> MockContentSafetyClient:
    """Client that reports all content as grounded."""
    return MockContentSafetyClient()


@pytest.fixture
def mock_ungrounded() -> MockContentSafetyClient:
    """Client that reports content as ungrounded."""
    return MockContentSafetyClient(
        default_groundedness={
            "grounded": False,
            "ungroundedPercentage": 60.0,
            "reasoning": ["The response fabricates statistics not in source"],
        },
    )
