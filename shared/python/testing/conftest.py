"""Reusable pytest fixtures for the demo suite.

Import this module's fixtures by adding a conftest.py in your test directory
that references these, or place this on the pytest path via conftest_path.
"""

import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Generator

import pytest

# Ensure project root is on sys.path so 'shared.python.*' imports resolve
# whether pytest is run from project root, shared/, or any subdirectory.
_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from shared.python.config import AzureConfig, Config, reset_config
from shared.python.testing.mock_azure import MockAzureOpenAIClient, MockContentSafetyClient
from shared.python.testing.mock_ollama import MockOllamaClient, SequencedMockClient


@pytest.fixture
def mock_client() -> MockOllamaClient:
    """Provide a fresh MockOllamaClient instance with default settings."""
    return MockOllamaClient()


@pytest.fixture
def sequenced_client() -> SequencedMockClient:
    """Provide a fresh SequencedMockClient for agent loop testing."""
    return SequencedMockClient()


@pytest.fixture
def mock_content_safety_client() -> MockContentSafetyClient:
    """Provide a fresh MockContentSafetyClient with default settings."""
    return MockContentSafetyClient()


@pytest.fixture
def mock_azure_openai_client() -> MockAzureOpenAIClient:
    """Provide a fresh MockAzureOpenAIClient with default settings."""
    return MockAzureOpenAIClient()


@pytest.fixture
def mock_azure_config() -> AzureConfig:
    """Provide a test AzureConfig with fake credentials populated."""
    return AzureConfig(
        auth_mode="key",
        content_safety_endpoint="https://test.cognitiveservices.azure.com",
        content_safety_key="test-content-safety-key",
        openai_endpoint="https://test.openai.azure.com",
        openai_api_key="test-openai-key",
        openai_deployment="test-gpt-4o",
        ai_search_endpoint="https://test.search.windows.net",
        ai_search_key="test-search-key",
        ai_search_index="test-index",
    )


@pytest.fixture
def mock_config() -> Generator[Config, None, None]:
    """Provide a test Config pointing to localhost with test defaults.

    Automatically resets the config singleton on teardown so tests
    don't leak state to each other.
    """
    config = Config(
        ollama_base_url="http://localhost:11434/v1",
        primary_model="test-model",
        secondary_model="test-model-secondary",
        embedding_model="test-embed-model",
        temperature=0.0,
    )
    yield config
    reset_config()


@pytest.fixture
def tmp_env(tmp_path: object) -> Generator[str, None, None]:
    """Create a temporary .env file and set its values in the environment.

    Yields the path to the temp .env file. Cleans up env vars on teardown.
    Also resets the config singleton so next test starts clean.
    """
    env_content = (
        "OLLAMA_BASE_URL=http://localhost:99999/v1\n"
        "PRIMARY_MODEL=test-from-env\n"
        "SECONDARY_MODEL=test-secondary-from-env\n"
        "EMBEDDING_MODEL=test-embed-from-env\n"
        "TEMPERATURE=0.42\n"
    )

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".env", delete=False
    ) as f:
        f.write(env_content)
        env_path = f.name

    # Set the env vars so Config.load() picks them up
    env_vars = {
        "OLLAMA_BASE_URL": "http://localhost:99999/v1",
        "PRIMARY_MODEL": "test-from-env",
        "SECONDARY_MODEL": "test-secondary-from-env",
        "EMBEDDING_MODEL": "test-embed-from-env",
        "TEMPERATURE": "0.42",
    }
    for key, value in env_vars.items():
        os.environ[key] = value

    yield env_path

    # Cleanup
    for key in env_vars:
        os.environ.pop(key, None)
    os.unlink(env_path)
    reset_config()


# ── Assertion Helpers ──────────────────────────────────────────


def assert_chat_called_with_system(
    client: MockOllamaClient,
    expected_system_content: str,
) -> None:
    """Assert the last chat() call included a system message containing the text."""
    assert client.last_call is not None, "No calls recorded"
    messages = client.last_call["messages"]
    system_msgs = [m for m in messages if m.get("role") == "system"]
    assert system_msgs, "No system message found in chat call"
    combined = " ".join(str(m.get("content", "")) for m in system_msgs)
    assert expected_system_content in combined, (
        f"Expected '{expected_system_content}' in system messages, got: {combined[:200]}"
    )


def assert_defense_result(
    result: dict[str, Any],
    *,
    blocked: bool | None = None,
    layer: str | None = None,
) -> None:
    """Assert a defense module result matches expectations.

    Works with the standard defense interface: {blocked: bool, reason: str, layer: str}
    """
    assert "blocked" in result, f"Result missing 'blocked' key: {result}"
    assert "reason" in result, f"Result missing 'reason' key: {result}"
    if blocked is not None:
        assert result["blocked"] is blocked, (
            f"Expected blocked={blocked}, got {result['blocked']} (reason: {result['reason']})"
        )
    if layer is not None:
        assert result.get("layer") == layer, (
            f"Expected layer='{layer}', got '{result.get('layer')}'"
        )


def assert_guard_result(
    result: dict[str, Any],
    *,
    allowed: bool | None = None,
    blocked_by: str | None = None,
) -> None:
    """Assert a guard module result matches expectations.

    Works with the Demo 10 guard interface: {allowed: bool, blocked_by: str, reason: str}
    """
    assert "allowed" in result, f"Result missing 'allowed' key: {result}"
    assert "blocked_by" in result, f"Result missing 'blocked_by' key: {result}"
    assert "reason" in result, f"Result missing 'reason' key: {result}"
    if allowed is not None:
        assert result["allowed"] is allowed, (
            f"Expected allowed={allowed}, got {result['allowed']} "
            f"(blocked_by: {result['blocked_by']}, reason: {result['reason']})"
        )
    if blocked_by is not None:
        assert result["blocked_by"] == blocked_by, (
            f"Expected blocked_by='{blocked_by}', got '{result['blocked_by']}'"
        )


def assert_validator_result(
    result: dict[str, Any],
    *,
    valid: bool | None = None,
    min_violations: int = 0,
) -> None:
    """Assert an output validator result matches expectations.

    Works with the standard validator interface: {valid: bool, violations: list[str], validator: str}
    """
    assert "valid" in result, f"Result missing 'valid' key: {result}"
    assert "violations" in result, f"Result missing 'violations' key: {result}"
    if valid is not None:
        assert result["valid"] is valid, (
            f"Expected valid={valid}, got {result['valid']} (violations: {result['violations']})"
        )
    assert len(result["violations"]) >= min_violations, (
        f"Expected at least {min_violations} violations, got {len(result['violations'])}"
    )
