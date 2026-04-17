"""Mock Ollama client for unit testing without a live Ollama instance.

Implements the same interface as OllamaClient (chat, chat_stream, embed)
with configurable canned responses, enabling fully offline test suites.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Iterator

from openai.types.chat import ChatCompletionMessageParam

__all__ = [
    "MockOllamaClient",
    "SequencedMockClient",
    "DEFAULT_RESPONSE",
    "EMBEDDING_DIMS",
]

DEFAULT_RESPONSE = "This is a mock response."
EMBEDDING_DIMS = 384  # Matches nomic-embed-text output

# Auto-incrementing counter for unique tool call IDs
_tool_call_counter = 0


def _next_tool_call_id() -> str:
    """Generate a unique mock tool call ID."""
    global _tool_call_counter
    _tool_call_counter += 1
    return f"call_mock_{_tool_call_counter:03d}"


@dataclass
class MockOllamaClient:
    """Drop-in replacement for OllamaClient that returns canned responses.

    Args:
        responses: Mapping of regex patterns to response strings.
            When the last user message matches a pattern, the corresponding
            response is returned. First match wins.
        default_response: Fallback when no pattern matches.
        tool_call_responses: List of mock tool-call response objects to return
            when tools are provided. Each entry should be a dict with
            ``{"function": {"name": ..., "arguments": ...}}``.
        embedding_vector: Fixed embedding vector returned by embed().
            Defaults to a 384-dim vector of 0.1 values.
    """

    responses: dict[str, str] = field(default_factory=dict)
    default_response: str = DEFAULT_RESPONSE
    tool_call_responses: list[dict[str, Any]] = field(default_factory=list)
    embedding_vector: list[float] = field(
        default_factory=lambda: [0.1] * EMBEDDING_DIMS
    )

    # Track calls for test assertions
    call_history: list[dict[str, Any]] = field(default_factory=list)

    def reset_call_history(self) -> None:
        """Clear the call history. Useful between sub-tests."""
        self.call_history.clear()

    @property
    def last_call(self) -> dict[str, Any] | None:
        """Return the most recent call record, or None if no calls made."""
        return self.call_history[-1] if self.call_history else None

    @property
    def chat_calls(self) -> list[dict[str, Any]]:
        """Return only chat() calls from the history."""
        return [c for c in self.call_history if c["method"] == "chat"]

    @property
    def embed_calls(self) -> list[dict[str, Any]]:
        """Return only embed() calls from the history."""
        return [c for c in self.call_history if c["method"] == "embed"]

    def close(self) -> None:
        """No-op — mock has no resources to close."""

    def __enter__(self) -> "MockOllamaClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def _match_response(self, messages: list[ChatCompletionMessageParam]) -> str:
        """Find the first matching canned response for the last user message."""
        last_content = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                last_content = str(msg.get("content", ""))
                break

        for pattern, response in self.responses.items():
            if re.search(pattern, last_content, re.IGNORECASE):
                return response

        return self.default_response

    def chat(
        self,
        messages: list[ChatCompletionMessageParam],
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> Any:
        """Return a canned response or mock tool-call response.

        Mirrors OllamaClient.chat(): returns full response object when tools
        are provided, otherwise just the content string.
        """
        self.call_history.append({
            "method": "chat",
            "messages": messages,
            "model": model,
            "tools": tools,
        })

        content = self._match_response(messages)

        if tools and self.tool_call_responses:
            return _MockCompletionResponse(
                content=content,
                tool_calls=[
                    _MockToolCall(**tc) for tc in self.tool_call_responses
                ],
            )

        if tools:
            return _MockCompletionResponse(content=content, tool_calls=None)

        return content

    def chat_stream(
        self,
        messages: list[ChatCompletionMessageParam],
        model: str | None = None,
    ) -> Iterator[str]:
        """Yield canned response tokens one word at a time."""
        self.call_history.append({
            "method": "chat_stream",
            "messages": messages,
            "model": model,
        })

        content = self._match_response(messages)
        tokens = content.split()
        for i, token in enumerate(tokens):
            yield token if i == 0 else f" {token}"

    def embed(
        self,
        text: str,
        model: str | None = None,
    ) -> list[float]:
        """Return a fixed-dimension embedding vector."""
        self.call_history.append({
            "method": "embed",
            "text": text,
            "model": model,
        })
        return list(self.embedding_vector)

    def embed_many(
        self,
        texts: list[str],
        model: str | None = None,
    ) -> list[list[float]]:
        """Return fixed-dimension embedding vectors for multiple texts."""
        self.call_history.append({
            "method": "embed_many",
            "texts": texts,
            "model": model,
        })
        return [list(self.embedding_vector) for _ in texts]

    def health_check(self) -> bool:
        """Always returns True for mock client."""
        self.call_history.append({"method": "health_check"})
        return True


# ── Internal mock objects ────────────────────────────────────────────


@dataclass
class _MockFunctionCall:
    name: str
    arguments: str


class _MockToolCall:
    def __init__(
        self,
        function: dict[str, str],
        id: str | None = None,
        type: str = "function",
    ) -> None:
        self.id = id or _next_tool_call_id()
        self.type = type
        self.function = _MockFunctionCall(
            name=function["name"],
            arguments=function["arguments"],
        )


class _MockMessage:
    def __init__(
        self,
        content: str,
        tool_calls: list[_MockToolCall] | None,
    ) -> None:
        self.content = content
        self.tool_calls = tool_calls


class _MockChoice:
    def __init__(self, message: _MockMessage) -> None:
        self.message = message


class _MockCompletionResponse:
    """Minimal mock of openai ChatCompletion response."""

    def __init__(
        self,
        content: str,
        tool_calls: list[_MockToolCall] | None = None,
    ) -> None:
        self.choices = [
            _MockChoice(_MockMessage(content=content, tool_calls=tool_calls))
        ]


# ── Sequenced mock client for agent loop testing ──────────────────────


@dataclass
class SequencedMockClient:
    """Mock client that returns different responses on successive chat() calls.

    Designed for testing multi-step agent loops where the LLM first requests
    tool calls, then produces a final text answer.

    Args:
        response_sequence: List of (content, tool_calls_or_none) tuples.
            Each chat() call consumes the next entry. ``tool_calls`` entries
            should be dicts with ``{"name": ..., "arguments": ...}`` keys.
        fallback: Returned after the sequence is exhausted.
        call_count: Number of chat() calls made so far.
        call_history: Full log of all chat() invocations for assertions.
    """

    response_sequence: list[tuple[str, list[dict[str, Any]] | None]] = field(
        default_factory=list
    )
    fallback: str = "Done."
    call_count: int = 0
    call_history: list[dict[str, Any]] = field(default_factory=list)

    def chat(
        self,
        messages: list[ChatCompletionMessageParam],
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> Any:
        """Return the next sequenced response, or fallback when exhausted."""
        self.call_history.append({
            "messages": messages,
            "model": model,
            "tools": tools,
        })

        if self.call_count < len(self.response_sequence):
            content, tc_defs = self.response_sequence[self.call_count]
            self.call_count += 1

            tool_calls = None
            if tc_defs:
                tool_calls = [
                    _MockToolCall(
                        function={"name": tc["name"], "arguments": tc["arguments"]},
                        id=f"call_mock_{i:03d}",
                    )
                    for i, tc in enumerate(tc_defs)
                ]

            return _MockCompletionResponse(content=content, tool_calls=tool_calls)

        self.call_count += 1
        return _MockCompletionResponse(content=self.fallback, tool_calls=None)
