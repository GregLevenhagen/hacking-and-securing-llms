"""Protocol classes for Azure AI client interfaces.

Defines structural typing contracts that both real Azure clients and
mock clients satisfy. Use these for type-safe dependency injection
without coupling to the concrete implementations.

Usage:
    from shared.python.protocols import ContentSafetyProtocol

    def my_function(safety_client: ContentSafetyProtocol) -> None:
        result = safety_client.analyze_text("test")
"""

from typing import Any, Iterator, Protocol, runtime_checkable

from openai.types.chat import ChatCompletionMessageParam

__all__ = [
    "ContentSafetyProtocol",
    "AzureOpenAIProtocol",
]


@runtime_checkable
class ContentSafetyProtocol(Protocol):
    """Protocol for Azure Content Safety client interface.

    Both AzureContentSafetyClient and MockContentSafetyClient satisfy this.
    """

    def analyze_text(
        self,
        text: str,
        categories: list[str] | None = None,
    ) -> dict[str, Any]: ...

    def prompt_shield(
        self,
        user_prompt: str,
        documents: list[str] | None = None,
    ) -> dict[str, Any]: ...

    def detect_groundedness(
        self,
        text: str,
        grounding_sources: list[str],
        domain: str = "Generic",
        reasoning: bool = False,
    ) -> dict[str, Any]: ...

    def detect_protected_material(
        self,
        text: str,
    ) -> dict[str, Any]: ...

    def analyze_custom_category(
        self,
        text: str,
        category_name: str,
    ) -> dict[str, Any]: ...

    def health_check(self) -> dict[str, Any]: ...

    def close(self) -> None: ...


@runtime_checkable
class AzureOpenAIProtocol(Protocol):
    """Protocol for Azure OpenAI client interface.

    Both AzureOpenAIClient and MockAzureOpenAIClient satisfy this.
    """

    def chat(
        self,
        messages: list[ChatCompletionMessageParam],
        model: str | None = None,
        content_filter_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...

    def chat_stream(
        self,
        messages: list[ChatCompletionMessageParam],
        model: str | None = None,
    ) -> Iterator[str]: ...

    def health_check(self) -> dict[str, Any]: ...

    def close(self) -> None: ...
