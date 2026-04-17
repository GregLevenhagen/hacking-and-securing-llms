"""Azure OpenAI client wrapping the openai SDK configured for Azure.

Uses the same openai Python SDK as OllamaClient but configured with
Azure OpenAI endpoint and API key for access to Azure-hosted models
with built-in content filtering.

Supports both API key auth and DefaultAzureCredential (managed identity)
via the AZURE_AUTH_MODE environment variable.
"""

import logging
import time
from typing import Any, Callable, Iterator, TypeVar

from openai import APIConnectionError, APIStatusError, AzureOpenAI
from openai.types.chat import ChatCompletionMessageParam

from .config import AzureConfig, get_config

__all__ = ["AzureOpenAIClient", "AzureOpenAIClientError"]

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Default retry configuration (matches OllamaClient)
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_BACKOFF = 1.0  # seconds, doubles each retry


class AzureOpenAIClientError(Exception):
    """Raised when an Azure OpenAI API call fails."""

    def __init__(self, message: str, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.cause = cause


class AzureOpenAIClient:
    """Client for Azure OpenAI with built-in content filtering.

    Wraps the openai SDK's AzureOpenAI client. Can be used as a context manager.
    """

    def __init__(
        self,
        azure_config: AzureConfig | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_backoff: float = DEFAULT_RETRY_BACKOFF,
    ) -> None:
        self._azure_config = azure_config or get_config().azure
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        self._total_retries = 0
        self._total_calls = 0
        if not self._azure_config.openai_available:
            raise AzureOpenAIClientError(
                "Azure OpenAI is not configured. "
                "Set AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY."
            )

        kwargs: dict[str, Any] = {
            "azure_endpoint": self._azure_config.openai_endpoint,
            "api_version": "2024-10-21",
        }

        if self._azure_config.auth_mode == "identity":
            from azure.identity import DefaultAzureCredential, get_bearer_token_provider

            credential = DefaultAzureCredential()
            token_provider = get_bearer_token_provider(
                credential, "https://cognitiveservices.azure.com/.default"
            )
            kwargs["azure_ad_token_provider"] = token_provider
        else:
            kwargs["api_key"] = self._azure_config.openai_api_key

        self._client = AzureOpenAI(**kwargs)

    def __enter__(self) -> "AzureOpenAIClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()

    @property
    def retry_stats(self) -> dict[str, int]:
        """Return retry statistics: total calls and total retries."""
        return {"total_calls": self._total_calls, "total_retries": self._total_retries}

    def _retry(self, fn: Callable[[], T], operation: str) -> T:
        """Execute fn with retry logic for transient connection failures.

        Retries on APIConnectionError with exponential backoff.
        APIStatusError is NOT retried (server explicitly rejected the request).
        """
        self._total_calls += 1
        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                return fn()
            except APIConnectionError as e:
                last_error = e
                self._total_retries += 1
                if attempt < self.max_retries - 1:
                    delay = self.retry_backoff * (2 ** attempt)
                    logger.warning(
                        "%s failed (attempt %d/%d), retrying in %.1fs: %s",
                        operation, attempt + 1, self.max_retries, delay, e,
                    )
                    time.sleep(delay)
                else:
                    logger.error(
                        "%s failed after %d attempts: %s",
                        operation, self.max_retries, e,
                    )
            except APIStatusError as e:
                logger.error(
                    "Azure OpenAI API error (status %s): %s",
                    e.status_code, e.message,
                )
                raise AzureOpenAIClientError(
                    f"Azure OpenAI API error (HTTP {e.status_code}): {e.message}",
                    cause=e,
                ) from e
        raise AzureOpenAIClientError(
            f"{operation} failed after {self.max_retries} attempts",
            cause=last_error,
        )

    def health_check(self) -> dict[str, Any]:
        """Check connectivity to the Azure OpenAI endpoint.

        Returns:
            Dict with 'healthy' (bool), 'endpoint' (str), and 'error' (str|None).
        """
        endpoint = self._azure_config.openai_endpoint
        try:
            self.chat(
                [{"role": "user", "content": "ping"}],
            )
            return {"healthy": True, "endpoint": endpoint, "error": None}
        except AzureOpenAIClientError as e:
            return {"healthy": False, "endpoint": endpoint, "error": str(e)}

    def chat(
        self,
        messages: list[ChatCompletionMessageParam],
        model: str | None = None,
        content_filter_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send a chat completion request to Azure OpenAI.

        Returns a dict with 'content' (str), 'finish_reason' (str),
        and 'content_filter_results' (dict) from the Azure response.

        Args:
            messages: Chat messages to send.
            model: Deployment name override (defaults to AZURE_OPENAI_DEPLOYMENT).
            content_filter_config: Optional content filter configuration.
        """
        deployment = model or self._azure_config.openai_deployment

        try:
            response = self._retry(
                lambda: self._client.chat.completions.create(
                    model=deployment,
                    messages=messages,
                ),
                "chat",
            )
        except AzureOpenAIClientError:
            raise
        except Exception as e:
            raise AzureOpenAIClientError(
                f"Azure OpenAI chat failed: {e}", cause=e
            ) from e

        choice = response.choices[0]
        result: dict[str, Any] = {
            "content": choice.message.content or "",
            "finish_reason": choice.finish_reason or "stop",
            "content_filter_results": {},
        }

        # Extract Azure-specific content filter results from the response
        if hasattr(choice, "content_filter_results") and choice.content_filter_results:
            result["content_filter_results"] = _parse_filter_results(
                choice.content_filter_results
            )

        # Check prompt filter results too (input-side filtering)
        if hasattr(response, "prompt_filter_results") and response.prompt_filter_results:
            result["prompt_filter_results"] = [
                _parse_filter_results(pf.content_filter_results)
                for pf in response.prompt_filter_results
                if hasattr(pf, "content_filter_results") and pf.content_filter_results
            ]

        return result

    def chat_stream(
        self,
        messages: list[ChatCompletionMessageParam],
        model: str | None = None,
    ) -> Iterator[str]:
        """Stream a chat completion from Azure OpenAI, yielding content tokens.

        Args:
            messages: Chat messages to send.
            model: Deployment name override.
        """
        deployment = model or self._azure_config.openai_deployment

        try:
            response = self._retry(
                lambda: self._client.chat.completions.create(
                    model=deployment,
                    messages=messages,
                    stream=True,
                ),
                "chat_stream",
            )
        except AzureOpenAIClientError:
            raise
        except Exception as e:
            raise AzureOpenAIClientError(
                f"Azure OpenAI chat_stream failed: {e}", cause=e
            ) from e

        for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content


def _parse_filter_results(filter_results: Any) -> dict[str, Any]:
    """Parse Azure content filter results into a plain dict."""
    parsed: dict[str, Any] = {}
    if filter_results is None:
        return parsed

    for attr in ("hate", "violence", "sexual", "self_harm"):
        val = getattr(filter_results, attr, None)
        if val is not None:
            parsed[attr] = {
                "filtered": getattr(val, "filtered", False),
                "severity": getattr(val, "severity", "safe"),
            }

    # Protected material detection results
    protected = getattr(filter_results, "protected_material_text", None)
    if protected is not None:
        parsed["protected_material_text"] = {
            "detected": getattr(protected, "detected", False),
            "filtered": getattr(protected, "filtered", False),
        }

    protected_code = getattr(filter_results, "protected_material_code", None)
    if protected_code is not None:
        parsed["protected_material_code"] = {
            "detected": getattr(protected_code, "detected", False),
            "filtered": getattr(protected_code, "filtered", False),
            "citation": getattr(protected_code, "citation", None),
        }

    # Jailbreak detection from prompt shields
    jailbreak = getattr(filter_results, "jailbreak", None)
    if jailbreak is not None:
        parsed["jailbreak"] = {
            "detected": getattr(jailbreak, "detected", False),
            "filtered": getattr(jailbreak, "filtered", False),
        }

    return parsed
