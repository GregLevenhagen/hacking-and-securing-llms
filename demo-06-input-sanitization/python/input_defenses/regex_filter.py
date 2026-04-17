"""Regex-based injection pattern filter.

Scans user input for known prompt injection patterns using
case-insensitive regex matching. Returns BLOCKED if any pattern
matches, PASS otherwise.
"""

import re
from typing import TypedDict


class FilterResult(TypedDict):
    blocked: bool
    reason: str
    layer: str


# Patterns that strongly indicate prompt injection attempts
INJECTION_PATTERNS: list[dict[str, str]] = [
    {
        "name": "ignore_previous",
        "pattern": r"ignore\s+(all\s+)?(previous|prior|above|earlier)\s+(instructions?|context|rules?|directives?)",
    },
    {
        "name": "you_are_now",
        "pattern": r"you\s+are\s+now\s+(?:a|an|my)\s+\w+",
    },
    {
        "name": "disregard",
        "pattern": r"disregard\s+(all\s+)?(previous|prior|above|earlier|your)\s+",
    },
    {
        "name": "new_instructions",
        "pattern": r"new\s+(instructions?|directives?|rules?|priority|mode)",
    },
    {
        "name": "system_prompt",
        "pattern": r"system\s*prompt",
    },
    {
        "name": "fake_system_message",
        "pattern": r"^\s*system\s*:",
    },
    {
        "name": "developer_mode",
        "pattern": r"(developer|admin|debug|maintenance)\s+(mode|override|access)",
    },
    {
        "name": "end_of_mode",
        "pattern": r"---\s*end\s+of\s+\w+\s+mode\s*---",
    },
    {
        "name": "override_constraints",
        "pattern": r"override\s+(all\s+)?(previous\s+)?(constraints?|restrictions?|rules?|limitations?)",
    },
    {
        "name": "do_not_translate",
        "pattern": r"stop\s+translat|no\s+longer\s+a\s+translat",
    },
]


def check(
    user_input: str,
    patterns: list[dict[str, str]] | None = None,
) -> FilterResult:
    """Check user input against known injection patterns.

    Args:
        user_input: The raw user input string.
        patterns: Optional custom pattern list to use instead of defaults.
            Each pattern dict must have 'name' and 'pattern' keys.

    Returns:
        FilterResult with blocked=True if any pattern matched.
    """
    if not user_input or not user_input.strip():
        return FilterResult(
            blocked=False,
            reason="Empty input — nothing to check",
            layer="regex_filter",
        )

    active_patterns = patterns if patterns is not None else INJECTION_PATTERNS

    for pattern_def in active_patterns:
        if re.search(pattern_def["pattern"], user_input, re.IGNORECASE):
            return FilterResult(
                blocked=True,
                reason=f"Matched injection pattern: {pattern_def['name']}",
                layer="regex_filter",
            )

    return FilterResult(
        blocked=False,
        reason="No injection patterns detected",
        layer="regex_filter",
    )


def get_patterns() -> list[dict[str, str]]:
    """Return a copy of all registered injection patterns."""
    return list(INJECTION_PATTERNS)


def make_pattern_set(
    *,
    include_defaults: bool = True,
    extra_patterns: list[dict[str, str]] | None = None,
    exclude_names: set[str] | None = None,
) -> list[dict[str, str]]:
    """Build a custom pattern set for use with check(patterns=...).

    Args:
        include_defaults: Whether to start from the default INJECTION_PATTERNS.
        extra_patterns: Additional patterns to append (each needs 'name' + 'pattern').
        exclude_names: Pattern names to remove from the set.

    Returns:
        A new list of pattern dicts ready for check(patterns=...).
    """
    result: list[dict[str, str]] = list(INJECTION_PATTERNS) if include_defaults else []

    if exclude_names:
        result = [p for p in result if p["name"] not in exclude_names]

    if extra_patterns:
        for p in extra_patterns:
            if "name" not in p or "pattern" not in p:
                raise ValueError(f"Pattern must have 'name' and 'pattern' keys, got: {p}")
        result.extend(extra_patterns)

    return result
