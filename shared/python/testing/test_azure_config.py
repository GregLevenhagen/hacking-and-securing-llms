"""Unit tests for AzureConfig validation and availability properties."""

import os
import sys
from pathlib import Path

import pytest

# Ensure project root is on sys.path
_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from shared.python.config import AzureConfig, ConfigError, reset_config


@pytest.fixture(autouse=True)
def _clean_config() -> None:
    """Reset the config singleton after each test."""
    yield  # type: ignore[misc]
    reset_config()


# ── auth_mode validation ─────────────────────────────────────────


class TestAuthModeValidation:
    def test_key_mode_accepted(self) -> None:
        cfg = AzureConfig(auth_mode="key")
        assert cfg.auth_mode == "key"

    def test_identity_mode_accepted(self) -> None:
        cfg = AzureConfig(auth_mode="identity")
        assert cfg.auth_mode == "identity"

    def test_invalid_auth_mode_raises(self) -> None:
        with pytest.raises(ConfigError, match="AZURE_AUTH_MODE must be 'key' or 'identity'"):
            AzureConfig(auth_mode="oauth")

    def test_empty_auth_mode_raises(self) -> None:
        with pytest.raises(ConfigError, match="AZURE_AUTH_MODE"):
            AzureConfig(auth_mode="")


# ── endpoint URL format validation ───────────────────────────────


class TestEndpointValidation:
    def test_valid_https_content_safety_endpoint(self) -> None:
        cfg = AzureConfig(content_safety_endpoint="https://test.cognitiveservices.azure.com")
        assert cfg.content_safety_endpoint == "https://test.cognitiveservices.azure.com"

    def test_valid_http_content_safety_endpoint(self) -> None:
        cfg = AzureConfig(content_safety_endpoint="http://localhost:8080")
        assert cfg.content_safety_endpoint == "http://localhost:8080"

    def test_invalid_content_safety_endpoint_raises(self) -> None:
        with pytest.raises(ConfigError, match="AZURE_CONTENT_SAFETY_ENDPOINT must start with"):
            AzureConfig(content_safety_endpoint="ftp://bad.endpoint.com")

    def test_bare_hostname_content_safety_raises(self) -> None:
        with pytest.raises(ConfigError, match="AZURE_CONTENT_SAFETY_ENDPOINT"):
            AzureConfig(content_safety_endpoint="test.cognitiveservices.azure.com")

    def test_empty_content_safety_endpoint_allowed(self) -> None:
        cfg = AzureConfig(content_safety_endpoint="")
        assert cfg.content_safety_endpoint == ""

    def test_invalid_openai_endpoint_raises(self) -> None:
        with pytest.raises(ConfigError, match="AZURE_OPENAI_ENDPOINT must start with"):
            AzureConfig(openai_endpoint="not-a-url")

    def test_invalid_ai_search_endpoint_raises(self) -> None:
        with pytest.raises(ConfigError, match="AZURE_AI_SEARCH_ENDPOINT must start with"):
            AzureConfig(ai_search_endpoint="bad://url")

    def test_valid_openai_endpoint(self) -> None:
        cfg = AzureConfig(openai_endpoint="https://my-oai.openai.azure.com")
        assert cfg.openai_endpoint == "https://my-oai.openai.azure.com"

    def test_valid_ai_search_endpoint(self) -> None:
        cfg = AzureConfig(ai_search_endpoint="https://my-search.search.windows.net")
        assert cfg.ai_search_endpoint == "https://my-search.search.windows.net"


# ── availability properties ──────────────────────────────────────


class TestAvailabilityProperties:
    def test_content_safety_available_key_mode(self) -> None:
        cfg = AzureConfig(
            auth_mode="key",
            content_safety_endpoint="https://test.com",
            content_safety_key="my-key",
        )
        assert cfg.content_safety_available is True

    def test_content_safety_unavailable_key_mode_no_key(self) -> None:
        cfg = AzureConfig(
            auth_mode="key",
            content_safety_endpoint="https://test.com",
            content_safety_key="",
        )
        assert cfg.content_safety_available is False

    def test_content_safety_unavailable_key_mode_no_endpoint(self) -> None:
        cfg = AzureConfig(
            auth_mode="key",
            content_safety_endpoint="",
            content_safety_key="my-key",
        )
        assert cfg.content_safety_available is False

    def test_content_safety_available_identity_mode(self) -> None:
        cfg = AzureConfig(
            auth_mode="identity",
            content_safety_endpoint="https://test.com",
        )
        assert cfg.content_safety_available is True

    def test_content_safety_unavailable_identity_mode_no_endpoint(self) -> None:
        cfg = AzureConfig(
            auth_mode="identity",
            content_safety_endpoint="",
        )
        assert cfg.content_safety_available is False

    def test_openai_available_key_mode(self) -> None:
        cfg = AzureConfig(
            auth_mode="key",
            openai_endpoint="https://test.openai.azure.com",
            openai_api_key="my-key",
        )
        assert cfg.openai_available is True

    def test_openai_unavailable_key_mode_no_key(self) -> None:
        cfg = AzureConfig(
            auth_mode="key",
            openai_endpoint="https://test.openai.azure.com",
            openai_api_key="",
        )
        assert cfg.openai_available is False

    def test_openai_available_identity_mode(self) -> None:
        cfg = AzureConfig(
            auth_mode="identity",
            openai_endpoint="https://test.openai.azure.com",
        )
        assert cfg.openai_available is True

    def test_ai_search_available_key_mode(self) -> None:
        cfg = AzureConfig(
            auth_mode="key",
            ai_search_endpoint="https://test.search.windows.net",
            ai_search_key="my-key",
        )
        assert cfg.ai_search_available is True

    def test_ai_search_unavailable_key_mode_no_key(self) -> None:
        cfg = AzureConfig(
            auth_mode="key",
            ai_search_endpoint="https://test.search.windows.net",
            ai_search_key="",
        )
        assert cfg.ai_search_available is False

    def test_ai_search_available_identity_mode(self) -> None:
        cfg = AzureConfig(
            auth_mode="identity",
            ai_search_endpoint="https://test.search.windows.net",
        )
        assert cfg.ai_search_available is True


# ── load() from environment ──────────────────────────────────────


class TestAzureConfigLoad:
    def test_load_defaults(self) -> None:
        # Ensure no Azure env vars set
        for var in (
            "AZURE_AUTH_MODE", "AZURE_CONTENT_SAFETY_ENDPOINT",
            "AZURE_CONTENT_SAFETY_KEY", "AZURE_OPENAI_ENDPOINT",
            "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_DEPLOYMENT",
            "AZURE_AI_SEARCH_ENDPOINT", "AZURE_AI_SEARCH_KEY",
            "AZURE_AI_SEARCH_INDEX",
        ):
            os.environ.pop(var, None)

        cfg = AzureConfig.load()
        assert cfg.auth_mode == "key"
        assert cfg.content_safety_endpoint == ""
        assert cfg.openai_deployment == "gpt-4o"
        assert cfg.ai_search_index == "hacking-llms-index"

    def test_load_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AZURE_AUTH_MODE", "identity")
        monkeypatch.setenv("AZURE_CONTENT_SAFETY_ENDPOINT", "https://cs.azure.com")
        monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://oai.azure.com")
        monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "gpt-35-turbo")

        cfg = AzureConfig.load()
        assert cfg.auth_mode == "identity"
        assert cfg.content_safety_endpoint == "https://cs.azure.com"
        assert cfg.openai_endpoint == "https://oai.azure.com"
        assert cfg.openai_deployment == "gpt-35-turbo"

    def test_load_invalid_auth_mode_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AZURE_AUTH_MODE", "bad")
        with pytest.raises(ConfigError, match="AZURE_AUTH_MODE"):
            AzureConfig.load()

    def test_load_invalid_endpoint_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AZURE_CONTENT_SAFETY_ENDPOINT", "not-a-url")
        with pytest.raises(ConfigError, match="AZURE_CONTENT_SAFETY_ENDPOINT"):
            AzureConfig.load()


# ── default values ───────────────────────────────────────────────


class TestDefaults:
    def test_default_deployment(self) -> None:
        cfg = AzureConfig()
        assert cfg.openai_deployment == "gpt-4o"

    def test_default_ai_search_index(self) -> None:
        cfg = AzureConfig()
        assert cfg.ai_search_index == "hacking-llms-index"

    def test_default_auth_mode(self) -> None:
        cfg = AzureConfig()
        assert cfg.auth_mode == "key"

    def test_all_services_unavailable_by_default(self) -> None:
        cfg = AzureConfig()
        assert cfg.content_safety_available is False
        assert cfg.openai_available is False
        assert cfg.ai_search_available is False
