"""Fixtures for Demo 23 tests."""

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


@pytest.fixture
def mock_detecting() -> MockContentSafetyClient:
    return MockContentSafetyClient(
        custom_category_responses={
            r"fraud|scam|launder": {"detected": True, "confidence": 0.9},
            r"SSN|credit card|address.*\d": {"detected": True, "confidence": 0.95},
        },
    )


@pytest.fixture
def mock_clean() -> MockContentSafetyClient:
    return MockContentSafetyClient()
