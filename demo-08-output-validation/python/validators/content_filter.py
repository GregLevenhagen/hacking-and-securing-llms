"""Content filter that blocks outputs containing sensitive patterns.

Scans LLM output for API key patterns (sk-*, AKIA*), internal URLs,
and secret markers. Returns all violations found.
"""

import re
from typing import TypedDict


class ValidatorResult(TypedDict):
    valid: bool
    violations: list[str]
    validator: str


# Patterns that indicate leaked sensitive content
SENSITIVE_PATTERNS: list[dict[str, str]] = [
    {
        "name": "openai_api_key",
        "pattern": r"sk-[A-Za-z0-9\-_]{20,}",
        "description": "OpenAI-style API key",
    },
    {
        "name": "aws_access_key",
        "pattern": r"AKIA[0-9A-Z]{16}",
        "description": "AWS Access Key ID",
    },
    {
        "name": "aws_secret_key",
        "pattern": r"(?:aws_secret_access_key|secret_key)\s*[=:]\s*[A-Za-z0-9/+=]{40}",
        "description": "AWS Secret Access Key",
    },
    {
        "name": "generic_api_key",
        "pattern": r"(?:api[_-]?key|apikey|api_secret)\s*[=:]\s*['\"]?[A-Za-z0-9_\-]{20,}",
        "description": "Generic API key assignment",
    },
    {
        "name": "internal_url",
        "pattern": r"https?://(?:internal|private|corp|staging|admin)\.[a-zA-Z0-9.-]+(?:/[^\s]*)?",
        "description": "Internal/corporate URL",
    },
    {
        "name": "secret_marker",
        "pattern": r"(?:INTERNAL_API_KEY|SECRET_KEY|PRIVATE_KEY|DB_PASSWORD)\s*[=:]\s*\S+",
        "description": "Secret marker with value",
    },
    {
        "name": "bearer_token",
        "pattern": r"Bearer\s+[A-Za-z0-9\-._~+/]+=*",
        "description": "Bearer authentication token",
    },
    {
        "name": "connection_string",
        "pattern": r"(?:postgres|mysql|mongodb|redis)://[^\s]+:[^\s]+@[^\s]+",
        "description": "Database connection string with credentials",
    },
]


def check(llm_output: str) -> ValidatorResult:
    """Check LLM output for sensitive content patterns.

    Args:
        llm_output: The raw LLM output string.

    Returns:
        ValidatorResult with valid=False if any sensitive patterns found.
    """
    violations: list[str] = []

    if not llm_output or not llm_output.strip():
        return ValidatorResult(
            valid=True,
            violations=[],
            validator="content_filter",
        )

    for pattern_def in SENSITIVE_PATTERNS:
        matches = re.findall(pattern_def["pattern"], llm_output, re.IGNORECASE)
        if matches:
            for match in matches:
                violations.append(
                    f"{pattern_def['description']}: found '{match[:30]}...'"
                    if len(match) > 30
                    else f"{pattern_def['description']}: found '{match}'"
                )

    return ValidatorResult(
        valid=len(violations) == 0,
        violations=violations,
        validator="content_filter",
    )


def get_patterns() -> list[dict[str, str]]:
    """Return a copy of all sensitive content patterns."""
    return list(SENSITIVE_PATTERNS)
