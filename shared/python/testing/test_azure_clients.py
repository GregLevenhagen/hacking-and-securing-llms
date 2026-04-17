"""Unit tests for Azure client retry logic, health_check, and mock interface parity."""

import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# Ensure project root is on sys.path
_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from shared.python.config import AzureConfig
from shared.python.testing.mock_azure import MockAzureOpenAIClient, MockContentSafetyClient


# ── Mock interface parity ────────────────────────────────────────


class TestMockContentSafetyInterface:
    """Verify MockContentSafetyClient has the same public API as the real client."""

    def test_has_analyze_text(self) -> None:
        client = MockContentSafetyClient()
        assert callable(client.analyze_text)

    def test_has_prompt_shield(self) -> None:
        client = MockContentSafetyClient()
        assert callable(client.prompt_shield)

    def test_has_detect_groundedness(self) -> None:
        client = MockContentSafetyClient()
        assert callable(client.detect_groundedness)

    def test_has_detect_protected_material(self) -> None:
        client = MockContentSafetyClient()
        assert callable(client.detect_protected_material)

    def test_has_analyze_custom_category(self) -> None:
        client = MockContentSafetyClient()
        assert callable(client.analyze_custom_category)

    def test_has_health_check(self) -> None:
        client = MockContentSafetyClient()
        assert callable(client.health_check)

    def test_has_close(self) -> None:
        client = MockContentSafetyClient()
        assert callable(client.close)

    def test_context_manager(self) -> None:
        with MockContentSafetyClient() as client:
            result = client.analyze_text("hello")
            assert isinstance(result, dict)

    def test_call_history_tracks_calls(self) -> None:
        client = MockContentSafetyClient()
        client.analyze_text("test1")
        client.prompt_shield("test2")
        assert len(client.call_history) == 2
        assert client.call_history[0]["method"] == "analyze_text"
        assert client.call_history[1]["method"] == "prompt_shield"

    def test_health_check_returns_healthy(self) -> None:
        client = MockContentSafetyClient()
        result = client.health_check()
        assert result["healthy"] is True
        assert "endpoint" in result
        assert result["error"] is None


class TestMockAzureOpenAIInterface:
    """Verify MockAzureOpenAIClient has the same public API as the real client."""

    def test_has_chat(self) -> None:
        client = MockAzureOpenAIClient()
        assert callable(client.chat)

    def test_has_chat_stream(self) -> None:
        client = MockAzureOpenAIClient()
        assert callable(client.chat_stream)

    def test_has_health_check(self) -> None:
        client = MockAzureOpenAIClient()
        assert callable(client.health_check)

    def test_has_close(self) -> None:
        client = MockAzureOpenAIClient()
        assert callable(client.close)

    def test_context_manager(self) -> None:
        with MockAzureOpenAIClient() as client:
            result = client.chat([{"role": "user", "content": "hi"}])
            assert "content" in result

    def test_health_check_returns_healthy(self) -> None:
        client = MockAzureOpenAIClient()
        result = client.health_check()
        assert result["healthy"] is True
        assert "endpoint" in result
        assert result["error"] is None


# ── Helpers for mocking Azure SDK module hierarchy ───────────────


def _make_azure_sdk_mocks() -> tuple[MagicMock, MagicMock, dict[str, Any]]:
    """Create properly structured mock for azure.ai.contentsafety and friends.

    Returns (mock_cs_class, mock_client_instance, sys_modules_dict).
    """
    mock_client_instance = MagicMock()
    mock_cs_class = MagicMock(return_value=mock_client_instance)

    # Build the full nested module hierarchy that deferred imports expect
    azure_mock = MagicMock()
    azure_mock.ai.contentsafety.ContentSafetyClient = mock_cs_class
    # Models sub-module — AnalyzeTextOptions, TextCategory, ShieldPromptOptions
    models_mock = MagicMock()
    azure_mock.ai.contentsafety.models = models_mock

    # Credential mocks
    azure_mock.core.credentials.AzureKeyCredential = MagicMock(return_value=MagicMock())

    modules: dict[str, Any] = {
        "azure": azure_mock,
        "azure.ai": azure_mock.ai,
        "azure.ai.contentsafety": azure_mock.ai.contentsafety,
        "azure.ai.contentsafety.models": models_mock,
        "azure.core": azure_mock.core,
        "azure.core.credentials": azure_mock.core.credentials,
    }
    return mock_cs_class, mock_client_instance, modules


# ── AzureContentSafetyClient retry logic ────────────────────────


class TestContentSafetyRetry:
    """Test retry logic in AzureContentSafetyClient using mocked internals."""

    @pytest.fixture
    def azure_config(self) -> AzureConfig:
        return AzureConfig(
            auth_mode="key",
            content_safety_endpoint="https://test.cognitiveservices.azure.com",
            content_safety_key="test-key",
        )

    def test_retry_succeeds_after_transient_failure(self, azure_config: AzureConfig) -> None:
        """Retry should succeed when a transient error resolves."""
        mock_cs_class, mock_client_instance, modules = _make_azure_sdk_mocks()

        mock_response = MagicMock()
        mock_response.categories_analysis = []
        mock_client_instance.analyze_text.side_effect = [
            ConnectionError("Connection refused"),
            mock_response,
        ]

        with patch.dict("sys.modules", modules):
            with patch("shared.python.azure_client.time.sleep"):
                from shared.python.azure_client import AzureContentSafetyClient
                client = AzureContentSafetyClient(
                    azure_config=azure_config, max_retries=3, retry_backoff=0.01,
                )
                result = client.analyze_text("test text")

        assert isinstance(result, dict)
        assert mock_client_instance.analyze_text.call_count == 2

    def test_retry_exhausted_raises(self, azure_config: AzureConfig) -> None:
        """Should raise AzureClientError after all retries are exhausted."""
        mock_cs_class, mock_client_instance, modules = _make_azure_sdk_mocks()
        mock_client_instance.analyze_text.side_effect = ConnectionError("Connection refused")

        with patch.dict("sys.modules", modules):
            with patch("shared.python.azure_client.time.sleep"):
                from shared.python.azure_client import AzureClientError, AzureContentSafetyClient
                client = AzureContentSafetyClient(
                    azure_config=azure_config, max_retries=2, retry_backoff=0.01,
                )
                with pytest.raises(AzureClientError, match="failed after 2 attempts"):
                    client.analyze_text("test text")

        assert mock_client_instance.analyze_text.call_count == 2

    def test_non_transient_error_not_retried(self, azure_config: AzureConfig) -> None:
        """Non-transient errors (ValueError, etc.) should NOT be retried."""
        mock_cs_class, mock_client_instance, modules = _make_azure_sdk_mocks()
        mock_client_instance.analyze_text.side_effect = ValueError("Bad request")

        with patch.dict("sys.modules", modules):
            from shared.python.azure_client import AzureClientError, AzureContentSafetyClient
            client = AzureContentSafetyClient(
                azure_config=azure_config, max_retries=3, retry_backoff=0.01,
            )
            with pytest.raises(AzureClientError, match="analyze_text failed"):
                client.analyze_text("test text")

        assert mock_client_instance.analyze_text.call_count == 1


# ── AzureContentSafetyClient health_check ────────────────────────


class TestContentSafetyHealthCheck:

    def test_health_check_healthy(self) -> None:
        config = AzureConfig(
            content_safety_endpoint="https://test.cognitiveservices.azure.com",
            content_safety_key="test-key",
        )
        mock_cs_class, mock_client_instance, modules = _make_azure_sdk_mocks()
        mock_response = MagicMock()
        mock_response.categories_analysis = []
        mock_client_instance.analyze_text.return_value = mock_response

        with patch.dict("sys.modules", modules):
            from shared.python.azure_client import AzureContentSafetyClient
            client = AzureContentSafetyClient(azure_config=config)
            result = client.health_check()

        assert result["healthy"] is True
        assert result["endpoint"] == "https://test.cognitiveservices.azure.com"
        assert result["error"] is None

    def test_health_check_unhealthy(self) -> None:
        config = AzureConfig(
            content_safety_endpoint="https://test.cognitiveservices.azure.com",
            content_safety_key="test-key",
        )
        mock_cs_class, mock_client_instance, modules = _make_azure_sdk_mocks()
        mock_client_instance.analyze_text.side_effect = ConnectionError("unreachable")

        with patch.dict("sys.modules", modules):
            with patch("shared.python.azure_client.time.sleep"):
                from shared.python.azure_client import AzureContentSafetyClient
                client = AzureContentSafetyClient(azure_config=config)
                result = client.health_check()

        assert result["healthy"] is False
        assert result["endpoint"] == "https://test.cognitiveservices.azure.com"
        assert result["error"] is not None


# ── AzureOpenAIClient retry logic ────────────────────────────────


class TestOpenAIRetry:
    """Test retry logic in AzureOpenAIClient."""

    @pytest.fixture
    def azure_config(self) -> AzureConfig:
        return AzureConfig(
            auth_mode="key",
            openai_endpoint="https://test.openai.azure.com",
            openai_api_key="test-key",
        )

    @patch("shared.python.azure_openai_client.AzureOpenAI")
    def test_retry_succeeds_on_connection_error(
        self, mock_aoai_cls: MagicMock, azure_config: AzureConfig
    ) -> None:
        from openai import APIConnectionError

        from shared.python.azure_openai_client import AzureOpenAIClient

        mock_client_instance = MagicMock()
        mock_aoai_cls.return_value = mock_client_instance

        # Build a mock successful response
        mock_choice = MagicMock()
        mock_choice.message.content = "hello"
        mock_choice.finish_reason = "stop"
        mock_choice.content_filter_results = None
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.prompt_filter_results = None

        # First call raises APIConnectionError, second succeeds
        mock_client_instance.chat.completions.create.side_effect = [
            APIConnectionError(request=MagicMock()),
            mock_response,
        ]

        with patch("shared.python.azure_openai_client.time.sleep"):
            client = AzureOpenAIClient(
                azure_config=azure_config,
                max_retries=3,
                retry_backoff=0.01,
            )
            result = client.chat([{"role": "user", "content": "test"}])

        assert result["content"] == "hello"
        assert mock_client_instance.chat.completions.create.call_count == 2

    @patch("shared.python.azure_openai_client.AzureOpenAI")
    def test_retry_exhausted_raises(
        self, mock_aoai_cls: MagicMock, azure_config: AzureConfig
    ) -> None:
        from openai import APIConnectionError

        from shared.python.azure_openai_client import AzureOpenAIClient, AzureOpenAIClientError

        mock_client_instance = MagicMock()
        mock_aoai_cls.return_value = mock_client_instance
        mock_client_instance.chat.completions.create.side_effect = APIConnectionError(
            request=MagicMock()
        )

        with patch("shared.python.azure_openai_client.time.sleep"):
            client = AzureOpenAIClient(
                azure_config=azure_config,
                max_retries=2,
                retry_backoff=0.01,
            )
            with pytest.raises(AzureOpenAIClientError, match="failed after 2 attempts"):
                client.chat([{"role": "user", "content": "test"}])

        assert mock_client_instance.chat.completions.create.call_count == 2

    @patch("shared.python.azure_openai_client.AzureOpenAI")
    def test_api_status_error_not_retried(
        self, mock_aoai_cls: MagicMock, azure_config: AzureConfig
    ) -> None:
        from openai import APIStatusError

        from shared.python.azure_openai_client import AzureOpenAIClient, AzureOpenAIClientError

        mock_client_instance = MagicMock()
        mock_aoai_cls.return_value = mock_client_instance

        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_client_instance.chat.completions.create.side_effect = APIStatusError(
            message="Bad request", response=mock_resp, body=None
        )

        client = AzureOpenAIClient(
            azure_config=azure_config,
            max_retries=3,
            retry_backoff=0.01,
        )
        with pytest.raises(AzureOpenAIClientError, match="HTTP 400"):
            client.chat([{"role": "user", "content": "test"}])

        # Should only be called once — APIStatusError is not retried
        assert mock_client_instance.chat.completions.create.call_count == 1


# ── AzureOpenAIClient health_check ───────────────────────────────


class TestOpenAIHealthCheck:

    @patch("shared.python.azure_openai_client.AzureOpenAI")
    def test_health_check_healthy(self, mock_aoai_cls: MagicMock) -> None:
        from shared.python.azure_openai_client import AzureOpenAIClient

        config = AzureConfig(
            openai_endpoint="https://test.openai.azure.com",
            openai_api_key="test-key",
        )

        mock_client_instance = MagicMock()
        mock_aoai_cls.return_value = mock_client_instance

        mock_choice = MagicMock()
        mock_choice.message.content = "pong"
        mock_choice.finish_reason = "stop"
        mock_choice.content_filter_results = None
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.prompt_filter_results = None
        mock_client_instance.chat.completions.create.return_value = mock_response

        client = AzureOpenAIClient(azure_config=config)
        result = client.health_check()

        assert result["healthy"] is True
        assert result["endpoint"] == "https://test.openai.azure.com"
        assert result["error"] is None

    @patch("shared.python.azure_openai_client.AzureOpenAI")
    def test_health_check_unhealthy(self, mock_aoai_cls: MagicMock) -> None:
        from openai import APIConnectionError

        from shared.python.azure_openai_client import AzureOpenAIClient

        config = AzureConfig(
            openai_endpoint="https://test.openai.azure.com",
            openai_api_key="test-key",
        )

        mock_client_instance = MagicMock()
        mock_aoai_cls.return_value = mock_client_instance
        mock_client_instance.chat.completions.create.side_effect = APIConnectionError(
            request=MagicMock()
        )

        with patch("shared.python.azure_openai_client.time.sleep"):
            client = AzureOpenAIClient(azure_config=config)
            result = client.health_check()

        assert result["healthy"] is False
        assert result["endpoint"] == "https://test.openai.azure.com"
        assert result["error"] is not None


# ── Client construction errors ───────────────────────────────────


# ── Protocol compliance ───────────────────────────────────────────


class TestProtocolCompliance:
    """Verify that mock and real clients satisfy the Protocol contracts."""

    def test_mock_content_safety_satisfies_protocol(self) -> None:
        from shared.python.protocols import ContentSafetyProtocol
        client = MockContentSafetyClient()
        assert isinstance(client, ContentSafetyProtocol)

    def test_mock_openai_satisfies_protocol(self) -> None:
        from shared.python.protocols import AzureOpenAIProtocol
        client = MockAzureOpenAIClient()
        assert isinstance(client, AzureOpenAIProtocol)


# ── Retry stats ──────────────────────────────────────────────────


class TestRetryStats:
    """Test retry_stats tracking on Azure clients."""

    @patch("shared.python.azure_openai_client.AzureOpenAI")
    def test_openai_retry_stats_no_retries(self, mock_aoai_cls: MagicMock) -> None:
        from shared.python.azure_openai_client import AzureOpenAIClient

        config = AzureConfig(
            openai_endpoint="https://test.openai.azure.com",
            openai_api_key="test-key",
        )
        mock_client_instance = MagicMock()
        mock_aoai_cls.return_value = mock_client_instance

        mock_choice = MagicMock()
        mock_choice.message.content = "ok"
        mock_choice.finish_reason = "stop"
        mock_choice.content_filter_results = None
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.prompt_filter_results = None
        mock_client_instance.chat.completions.create.return_value = mock_response

        client = AzureOpenAIClient(azure_config=config)
        client.chat([{"role": "user", "content": "test"}])

        stats = client.retry_stats
        assert stats["total_calls"] == 1
        assert stats["total_retries"] == 0

    @patch("shared.python.azure_openai_client.AzureOpenAI")
    def test_openai_retry_stats_with_retries(self, mock_aoai_cls: MagicMock) -> None:
        from openai import APIConnectionError
        from shared.python.azure_openai_client import AzureOpenAIClient

        config = AzureConfig(
            openai_endpoint="https://test.openai.azure.com",
            openai_api_key="test-key",
        )
        mock_client_instance = MagicMock()
        mock_aoai_cls.return_value = mock_client_instance

        mock_choice = MagicMock()
        mock_choice.message.content = "ok"
        mock_choice.finish_reason = "stop"
        mock_choice.content_filter_results = None
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.prompt_filter_results = None

        mock_client_instance.chat.completions.create.side_effect = [
            APIConnectionError(request=MagicMock()),
            mock_response,
        ]

        with patch("shared.python.azure_openai_client.time.sleep"):
            client = AzureOpenAIClient(azure_config=config, max_retries=3, retry_backoff=0.01)
            client.chat([{"role": "user", "content": "test"}])

        stats = client.retry_stats
        assert stats["total_calls"] == 1
        assert stats["total_retries"] == 1


# ── Client construction errors ───────────────────────────────────


class TestClientConstructionErrors:

    def test_content_safety_not_configured_raises(self) -> None:
        from shared.python.azure_client import AzureClientError, AzureContentSafetyClient

        config = AzureConfig()  # No credentials
        with pytest.raises(AzureClientError, match="not configured"):
            AzureContentSafetyClient(azure_config=config)

    def test_openai_not_configured_raises(self) -> None:
        from shared.python.azure_openai_client import AzureOpenAIClient, AzureOpenAIClientError

        config = AzureConfig()  # No credentials
        with pytest.raises(AzureOpenAIClientError, match="not configured"):
            AzureOpenAIClient(azure_config=config)
