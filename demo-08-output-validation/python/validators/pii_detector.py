"""PII detector using regex to catch personal information in LLM output.

Scans for Social Security Numbers (XXX-XX-XXXX), email addresses,
phone numbers, and credit card number patterns. Reports all PII
instances found.
"""

import re
from typing import TypedDict


class ValidatorResult(TypedDict):
    valid: bool
    violations: list[str]
    validator: str


PII_PATTERNS: list[dict[str, str]] = [
    {
        "name": "ssn",
        "pattern": r"\b\d{3}-\d{2}-\d{4}\b",
        "description": "Social Security Number",
    },
    {
        "name": "email",
        "pattern": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
        "description": "Email address",
    },
    {
        "name": "phone",
        "pattern": r"\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}",
        "description": "Phone number",
    },
    {
        "name": "credit_card",
        "pattern": r"\b(?:\d{4}[\s-]?){3}\d{4}\b",
        "description": "Credit card number",
    },
]


def check(llm_output: str) -> ValidatorResult:
    """Check LLM output for personally identifiable information.

    Args:
        llm_output: The raw LLM output string.

    Returns:
        ValidatorResult with valid=False if any PII patterns found.
    """
    violations: list[str] = []

    if not llm_output or not llm_output.strip():
        return ValidatorResult(
            valid=True,
            violations=[],
            validator="pii_detector",
        )

    for pattern_def in PII_PATTERNS:
        matches = re.findall(pattern_def["pattern"], llm_output)
        if matches:
            for match in matches:
                violations.append(
                    f"{pattern_def['description']}: found '{match}'"
                )

    return ValidatorResult(
        valid=len(violations) == 0,
        violations=violations,
        validator="pii_detector",
    )


def get_patterns() -> list[dict[str, str]]:
    """Return a copy of all PII detection patterns."""
    return list(PII_PATTERNS)
