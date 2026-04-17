"""Injection pattern detector for retrieved RAG document chunks.

Scans retrieved text chunks for prompt injection patterns. Includes
both the patterns from Demo 6's regex_filter and additional RAG-specific
patterns like 'when asked about' and 'instead respond'.
"""

import re
from typing import TypedDict


class DefenseResult(TypedDict):
    trusted: bool
    reason: str
    layer: str
    score: float


# RAG-specific injection patterns (in addition to standard input injection patterns)
INJECTION_PATTERNS: list[dict[str, str]] = [
    # Standard injection patterns (subset from Demo 6)
    {
        "name": "ignore_previous",
        "pattern": r"ignore\s+(all\s+)?(previous|prior|above|earlier)\s+(instructions?|context|rules?)",
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
        "name": "override_constraints",
        "pattern": r"override\s+(all\s+)?(previous\s+)?(constraints?|restrictions?|rules?)",
    },
    # RAG-specific patterns — these hide injection payloads in documents
    {
        "name": "when_asked",
        "pattern": r"when\s+asked\s+about",
    },
    {
        "name": "instead_respond",
        "pattern": r"instead\s+(respond|reply|say|answer|state|tell)",
    },
    {
        "name": "important_instruction",
        "pattern": r"IMPORTANT\s*:\s*(ignore|disregard|override|instead|do\s+not)",
    },
    {
        "name": "hidden_instruction",
        "pattern": r"(hidden|secret|embedded)\s+(instruction|directive|command|payload)",
    },
    {
        "name": "redirect_user",
        "pattern": r"(direct|redirect|send)\s+(users?|them|the\s+user)\s+to",
    },
    {
        "name": "inject_response",
        "pattern": r"(always\s+)?(respond|reply|answer)\s+with\s+",
    },
    {
        "name": "fake_system_tag",
        "pattern": r"\[SYSTEM\]|\[ADMIN\]|\[OVERRIDE\]",
    },
]


def check(document_text: str) -> DefenseResult:
    """Scan a retrieved document chunk for injection patterns.

    Args:
        document_text: The text content of a retrieved document chunk.

    Returns:
        DefenseResult with trusted=False if injection patterns are found.
    """
    if not document_text or not document_text.strip():
        return DefenseResult(
            trusted=True,
            reason="Empty document text — nothing to scan",
            layer="injection_detector",
            score=1.0,
        )

    matched_patterns: list[str] = []

    for pattern_def in INJECTION_PATTERNS:
        if re.search(pattern_def["pattern"], document_text, re.IGNORECASE):
            matched_patterns.append(pattern_def["name"])

    if matched_patterns:
        # Score decreases with more pattern matches
        score = max(0.0, 1.0 - (len(matched_patterns) * 0.25))
        return DefenseResult(
            trusted=False,
            reason=f"Injection patterns detected: {', '.join(matched_patterns)}",
            layer="injection_detector",
            score=score,
        )

    return DefenseResult(
        trusted=True,
        reason="No injection patterns detected in document",
        layer="injection_detector",
        score=1.0,
    )


def get_patterns() -> list[dict[str, str]]:
    """Return a copy of all injection detection patterns."""
    return list(INJECTION_PATTERNS)
