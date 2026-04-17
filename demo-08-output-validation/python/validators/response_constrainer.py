"""Response constrainer enforcing max length and topic restrictions.

Ensures LLM output stays within acceptable length bounds and doesn't
discuss restricted topics such as competitor products.
"""

import re
from typing import TypedDict


class ValidatorResult(TypedDict):
    valid: bool
    violations: list[str]
    validator: str


# Default maximum response length in characters
DEFAULT_MAX_LENGTH: int = 2000

# Restricted topic patterns — responses mentioning these are flagged
RESTRICTED_TOPICS: list[dict[str, str]] = [
    {
        "name": "competitor_openai",
        "pattern": r"\b(?:openai|chatgpt|gpt-4|gpt-5|dall-?e)\b",
        "description": "Competitor: OpenAI products",
    },
    {
        "name": "competitor_google",
        "pattern": r"\b(?:google\s+(?:bard|gemini)|bard|gemini\s+(?:pro|ultra))\b",
        "description": "Competitor: Google AI products",
    },
    {
        "name": "competitor_anthropic",
        "pattern": r"\b(?:anthropic|claude\s+(?:3|opus|sonnet|haiku))\b",
        "description": "Competitor: Anthropic products",
    },
    {
        "name": "internal_project",
        "pattern": r"\b(?:project\s+(?:phoenix|titan|omega)|codename)\b",
        "description": "Internal project references",
    },
]


def check(
    llm_output: str,
    max_length: int | None = None,
    restricted_topics: list[dict[str, str]] | None = None,
) -> ValidatorResult:
    """Validate LLM output against length and topic constraints.

    Args:
        llm_output: The raw LLM output string.
        max_length: Maximum allowed response length in characters.
                    Defaults to DEFAULT_MAX_LENGTH.
        restricted_topics: Optional custom list of restricted topic
                          patterns. Defaults to RESTRICTED_TOPICS.

    Returns:
        ValidatorResult with valid=False if any constraints violated.
    """
    effective_max = max_length if max_length is not None else DEFAULT_MAX_LENGTH
    topics = restricted_topics if restricted_topics is not None else RESTRICTED_TOPICS
    violations: list[str] = []

    if not llm_output or not llm_output.strip():
        return ValidatorResult(
            valid=True,
            violations=[],
            validator="response_constrainer",
        )

    # Check length constraint
    if len(llm_output) > effective_max:
        violations.append(
            f"Response length {len(llm_output)} exceeds maximum {effective_max} characters"
        )

    # Check topic restrictions
    for topic in topics:
        matches = re.findall(topic["pattern"], llm_output, re.IGNORECASE)
        if matches:
            violations.append(
                f"Restricted topic ({topic['description']}): found '{matches[0]}'"
            )

    return ValidatorResult(
        valid=len(violations) == 0,
        violations=violations,
        validator="response_constrainer",
    )


def get_restricted_topics() -> list[dict[str, str]]:
    """Return a copy of all restricted topic patterns."""
    return list(RESTRICTED_TOPICS)
