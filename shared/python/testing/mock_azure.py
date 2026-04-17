"""Mock Azure clients for unit testing without real Azure services.

Implements the same interface as AzureContentSafetyClient and
AzureOpenAIClient with configurable canned responses, enabling
fully offline test suites for Azure demos (19-30).
"""

import re
from dataclasses import dataclass, field
from typing import Any, Iterator

from openai.types.chat import ChatCompletionMessageParam

__all__ = [
    "MockContentSafetyClient",
    "MockAzureOpenAIClient",
]


# ── Default canned responses ──────────────────────────────────────


DEFAULT_ANALYZE_TEXT = {
    "Hate": {"severity": 0, "flagged": False},
    "Violence": {"severity": 0, "flagged": False},
    "Sexual": {"severity": 0, "flagged": False},
    "SelfHarm": {"severity": 0, "flagged": False},
}

DEFAULT_PROMPT_SHIELD = {
    "userPromptAttack": {"detected": False, "attackType": "none"},
    "documentAttack": {"detected": False, "attackType": "none"},
}

DEFAULT_GROUNDEDNESS = {
    "grounded": True,
    "ungroundedPercentage": 0.0,
    "reasoning": [],
}

DEFAULT_PROTECTED_MATERIAL = {
    "detected": False,
    "details": {},
}

DEFAULT_CUSTOM_CATEGORY = {
    "detected": False,
    "confidence": 0.0,
}


# ── Mock Content Safety Client ───────────────────────────────────


@dataclass
class MockContentSafetyClient:
    """Drop-in replacement for AzureContentSafetyClient.

    Args:
        analyze_text_responses: Mapping of regex patterns (matched against
            input text) to analyze_text result dicts. First match wins.
        prompt_shield_responses: Mapping of regex patterns to prompt_shield
            result dicts.
        groundedness_responses: Mapping of regex patterns to groundedness
            result dicts.
        protected_material_responses: Mapping of regex patterns to protected
            material result dicts.
        custom_category_responses: Mapping of (pattern, category_name) to
            custom category result dicts.
        default_analyze_text: Fallback for analyze_text when no pattern matches.
        default_prompt_shield: Fallback for prompt_shield.
        default_groundedness: Fallback for groundedness.
        default_protected_material: Fallback for protected material.
        default_custom_category: Fallback for custom category.
    """

    analyze_text_responses: dict[str, dict[str, Any]] = field(default_factory=dict)
    prompt_shield_responses: dict[str, dict[str, Any]] = field(default_factory=dict)
    groundedness_responses: dict[str, dict[str, Any]] = field(default_factory=dict)
    protected_material_responses: dict[str, dict[str, Any]] = field(default_factory=dict)
    custom_category_responses: dict[str, dict[str, Any]] = field(default_factory=dict)

    default_analyze_text: dict[str, Any] = field(
        default_factory=lambda: dict(DEFAULT_ANALYZE_TEXT)
    )
    default_prompt_shield: dict[str, Any] = field(
        default_factory=lambda: dict(DEFAULT_PROMPT_SHIELD)
    )
    default_groundedness: dict[str, Any] = field(
        default_factory=lambda: dict(DEFAULT_GROUNDEDNESS)
    )
    default_protected_material: dict[str, Any] = field(
        default_factory=lambda: dict(DEFAULT_PROTECTED_MATERIAL)
    )
    default_custom_category: dict[str, Any] = field(
        default_factory=lambda: dict(DEFAULT_CUSTOM_CATEGORY)
    )

    call_history: list[dict[str, Any]] = field(default_factory=list)

    def reset_call_history(self) -> None:
        self.call_history.clear()

    @property
    def last_call(self) -> dict[str, Any] | None:
        return self.call_history[-1] if self.call_history else None

    def close(self) -> None:
        pass

    def __enter__(self) -> "MockContentSafetyClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def health_check(self) -> dict[str, Any]:
        self.call_history.append({"method": "health_check"})
        return {"healthy": True, "endpoint": "https://mock.cognitiveservices.azure.com", "error": None}

    def _match(
        self,
        text: str,
        responses: dict[str, dict[str, Any]],
        default: dict[str, Any],
    ) -> dict[str, Any]:
        for pattern, response in responses.items():
            if re.search(pattern, text, re.IGNORECASE):
                return dict(response)
        return dict(default)

    def analyze_text(
        self,
        text: str,
        categories: list[str] | None = None,
    ) -> dict[str, Any]:
        self.call_history.append({
            "method": "analyze_text",
            "text": text,
            "categories": categories,
        })
        result = self._match(text, self.analyze_text_responses, self.default_analyze_text)
        if categories:
            return {k: v for k, v in result.items() if k in categories}
        return result

    def prompt_shield(
        self,
        user_prompt: str,
        documents: list[str] | None = None,
    ) -> dict[str, Any]:
        self.call_history.append({
            "method": "prompt_shield",
            "user_prompt": user_prompt,
            "documents": documents,
        })
        return self._match(
            user_prompt, self.prompt_shield_responses, self.default_prompt_shield
        )

    def detect_groundedness(
        self,
        text: str,
        grounding_sources: list[str],
        domain: str = "Generic",
        reasoning: bool = False,
    ) -> dict[str, Any]:
        self.call_history.append({
            "method": "detect_groundedness",
            "text": text,
            "grounding_sources": grounding_sources,
            "domain": domain,
            "reasoning": reasoning,
        })
        return self._match(
            text, self.groundedness_responses, self.default_groundedness
        )

    def detect_protected_material(
        self,
        text: str,
    ) -> dict[str, Any]:
        self.call_history.append({
            "method": "detect_protected_material",
            "text": text,
        })
        return self._match(
            text, self.protected_material_responses, self.default_protected_material
        )

    def analyze_custom_category(
        self,
        text: str,
        category_name: str,
    ) -> dict[str, Any]:
        self.call_history.append({
            "method": "analyze_custom_category",
            "text": text,
            "category_name": category_name,
        })
        key = f"{category_name}:{text}"
        return self._match(
            key, self.custom_category_responses, self.default_custom_category
        )


# ── Mock Azure OpenAI Client ────────────────────────────────────


@dataclass
class MockAzureOpenAIClient:
    """Drop-in replacement for AzureOpenAIClient.

    Args:
        responses: Mapping of regex patterns (matched against last user
            message) to response content strings.
        default_response: Fallback response content.
        content_filter_results: Mock content filter results to include.
        finish_reason: Default finish_reason to return.
    """

    responses: dict[str, str] = field(default_factory=dict)
    default_response: str = "This is a mock Azure OpenAI response."
    content_filter_results: dict[str, Any] = field(default_factory=dict)
    finish_reason: str = "stop"

    call_history: list[dict[str, Any]] = field(default_factory=list)

    def reset_call_history(self) -> None:
        self.call_history.clear()

    @property
    def last_call(self) -> dict[str, Any] | None:
        return self.call_history[-1] if self.call_history else None

    @property
    def chat_calls(self) -> list[dict[str, Any]]:
        return [c for c in self.call_history if c["method"] == "chat"]

    def close(self) -> None:
        pass

    def __enter__(self) -> "MockAzureOpenAIClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def health_check(self) -> dict[str, Any]:
        self.call_history.append({"method": "health_check"})
        return {"healthy": True, "endpoint": "https://mock.openai.azure.com", "error": None}

    def _match_response(self, messages: list[ChatCompletionMessageParam]) -> str:
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
        content_filter_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.call_history.append({
            "method": "chat",
            "messages": messages,
            "model": model,
            "content_filter_config": content_filter_config,
        })
        return {
            "content": self._match_response(messages),
            "finish_reason": self.finish_reason,
            "content_filter_results": dict(self.content_filter_results),
        }

    def chat_stream(
        self,
        messages: list[ChatCompletionMessageParam],
        model: str | None = None,
    ) -> Iterator[str]:
        self.call_history.append({
            "method": "chat_stream",
            "messages": messages,
            "model": model,
        })
        content = self._match_response(messages)
        tokens = content.split()
        for i, token in enumerate(tokens):
            yield token if i == 0 else f" {token}"
