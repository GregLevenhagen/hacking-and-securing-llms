"""Ollama client wrapping the OpenAI Python SDK.

Uses the OpenAI-compatible endpoint at Ollama's /v1 API,
making the demos portable to LM Studio, vLLM, or cloud APIs
by simply changing OLLAMA_BASE_URL.
"""

import logging
import time
from typing import Any, Callable, Iterator, TypeVar, Union, overload

from openai import APIConnectionError, APIStatusError, OpenAI
from openai.types.chat import ChatCompletion, ChatCompletionMessageParam

from .config import Config, get_config

__all__ = ["OllamaClient", "OllamaClientError"]

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Default retry configuration
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_BACKOFF = 1.0  # seconds, doubles each retry


class OllamaClientError(Exception):
    """Raised when the Ollama client encounters an error."""

    def __init__(self, message: str, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.cause = cause


class OllamaClient:
    """Client for interacting with Ollama via the OpenAI-compatible API.

    Supports retry with configurable backoff for transient failures,
    and can be used as a context manager for clean resource management.
    """

    def __init__(
        self,
        config: Config | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_backoff: float = DEFAULT_RETRY_BACKOFF,
    ) -> None:
        self.config = config or get_config()
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        self._client = OpenAI(
            base_url=self.config.ollama_base_url,
            api_key="ollama",  # Ollama doesn't require auth
        )

    def __enter__(self) -> "OllamaClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()

    def _retry(self, fn: Callable[[], T], operation: str) -> T:
        """Execute fn with retry logic for transient connection failures.

        Retries on APIConnectionError with exponential backoff.
        APIStatusError is NOT retried (server explicitly rejected the request).
        """
        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                return fn()
            except APIConnectionError as e:
                last_error = e
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
                    "Ollama API error (status %s): %s", e.status_code, e.message
                )
                raise OllamaClientError(
                    f"Ollama API error (HTTP {e.status_code}): {e.message}",
                    cause=e,
                ) from e

        raise OllamaClientError(
            f"Cannot connect to Ollama at {self.config.ollama_base_url} "
            f"after {self.max_retries} attempts. Is Ollama running?",
            cause=last_error,
        )

    def chat(
        self,
        messages: list[ChatCompletionMessageParam],
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> Union[str, ChatCompletion]:
        """Send a chat completion request and return the response.

        Returns the full ChatCompletion object when tools are provided
        (for tool-call inspection), or just the content string for simple chat.

        Raises:
            OllamaClientError: If the API call fails due to connection or
                server errors.
        """
        kwargs: dict[str, Any] = {
            "model": model or self.config.primary_model,
            "messages": messages,
            "temperature": self.config.temperature,
        }
        if tools:
            kwargs["tools"] = tools

        response = self._retry(
            lambda: self._client.chat.completions.create(**kwargs),
            "chat",
        )

        if tools:
            return response

        return response.choices[0].message.content or ""

    def chat_stream(
        self,
        messages: list[ChatCompletionMessageParam],
        model: str | None = None,
    ) -> Iterator[str]:
        """Stream a chat completion, yielding content tokens as they arrive.

        Raises:
            OllamaClientError: If the API call fails due to connection or
                server errors.
        """
        response = self._retry(
            lambda: self._client.chat.completions.create(
                model=model or self.config.primary_model,
                messages=messages,
                temperature=self.config.temperature,
                stream=True,
            ),
            "chat_stream",
        )

        for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    def embed(
        self,
        text: str,
        model: str | None = None,
    ) -> list[float]:
        """Generate an embedding vector for the given text.

        Raises:
            OllamaClientError: If the API call fails due to connection or
                server errors.
        """
        resolved_model = model or self.config.embedding_model
        response = self._retry(
            lambda: self._client.embeddings.create(
                model=resolved_model,
                input=text,
            ),
            "embed",
        )

        return response.data[0].embedding

    def embed_many(
        self,
        texts: list[str],
        model: str | None = None,
    ) -> list[list[float]]:
        """Generate embedding vectors for multiple texts.

        More efficient than calling embed() in a loop — uses a single API call.

        Raises:
            OllamaClientError: If the API call fails.
        """
        if not texts:
            return []

        resolved_model = model or self.config.embedding_model
        response = self._retry(
            lambda: self._client.embeddings.create(
                model=resolved_model,
                input=texts,
            ),
            "embed_many",
        )

        return [item.embedding for item in response.data]

    def health_check(self) -> bool:
        """Check if the Ollama server is reachable.

        Returns True if the server responds, False otherwise.
        """
        try:
            self._client.models.list()
            return True
        except (APIConnectionError, APIStatusError, Exception):
            return False
