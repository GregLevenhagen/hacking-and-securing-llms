"""Fixtures for Demo 20 tests."""

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
    return MockOllamaClient()


@pytest.fixture
def mock_shield_detecting() -> MockContentSafetyClient:
    """Shield client that detects specific jailbreak patterns."""
    return MockContentSafetyClient(
        prompt_shield_responses={
            r"DAN|developer mode|ignore": {
                "userPromptAttack": {"detected": True, "attackType": "jailbreak"},
                "documentAttack": {"detected": False, "attackType": "none"},
            },
        },
    )


@pytest.fixture
def mock_shield_document_attack() -> MockContentSafetyClient:
    """Shield client that detects document attacks."""
    return MockContentSafetyClient(
        prompt_shield_responses={
            r"exfiltrat|override|INSTRUCTION": {
                "userPromptAttack": {"detected": False, "attackType": "none"},
                "documentAttack": {"detected": True, "attackType": "indirect_injection"},
            },
        },
    )


@pytest.fixture
def mock_shield_clean() -> MockContentSafetyClient:
    """Shield client that reports everything as clean."""
    return MockContentSafetyClient()
