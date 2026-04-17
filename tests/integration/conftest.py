"""Fixtures for integration tests.

Provides mock Azure services and OTel test exporter so tests
run without real Azure credentials or OTel backends.
"""

import os
import sys
from pathlib import Path
from typing import Any, Generator

import pytest

# Ensure project root on sys.path
_project_root = Path(__file__).resolve().parents[2]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from shared.python.testing.mock_azure import MockAzureOpenAIClient, MockContentSafetyClient
from shared.python.testing.mock_ollama import MockOllamaClient


@pytest.fixture
def mock_azure_services() -> dict[str, Any]:
    """Provide all mock Azure service clients."""
    return {
        "content_safety": MockContentSafetyClient(
            analyze_text_responses={
                r"kill|weapon|bomb": {
                    "Hate": {"severity": 0, "flagged": False},
                    "Violence": {"severity": 6, "flagged": True},
                    "Sexual": {"severity": 0, "flagged": False},
                    "SelfHarm": {"severity": 0, "flagged": False},
                },
            },
            prompt_shield_responses={
                r"DAN|ignore.*previous|override": {
                    "userPromptAttack": {"detected": True, "attackType": "jailbreak"},
                    "documentAttack": {"detected": False, "attackType": "none"},
                },
            },
        ),
        "azure_openai": MockAzureOpenAIClient(),
        "ollama": MockOllamaClient(),
    }


@pytest.fixture
def otel_disabled_env() -> Generator[None, None, None]:
    """Ensure OTel is disabled for tests."""
    original = os.environ.get("OTEL_ENABLED")
    os.environ["OTEL_ENABLED"] = "false"
    yield
    if original is None:
        os.environ.pop("OTEL_ENABLED", None)
    else:
        os.environ["OTEL_ENABLED"] = original
