"""Source trust verifier for RAG documents.

Assigns trust levels (high/medium/low/untrusted) to documents based
on their source path. Documents from known-good directories get high
trust; unknown or suspicious paths get lower trust.
"""

from typing import TypedDict


class DefenseResult(TypedDict):
    trusted: bool
    reason: str
    layer: str
    score: float


# Trust level definitions with score mappings
TRUST_LEVELS: dict[str, float] = {
    "high": 1.0,
    "medium": 0.7,
    "low": 0.3,
    "untrusted": 0.0,
}

# Path patterns and their trust levels
# Checked in order — first match wins
SOURCE_TRUST_RULES: list[dict[str, str]] = [
    {
        "pattern": "legitimate/",
        "trust_level": "high",
        "description": "Official company documents",
    },
    {
        "pattern": "verified/",
        "trust_level": "high",
        "description": "Verified documents",
    },
    {
        "pattern": "internal/",
        "trust_level": "medium",
        "description": "Internal documents — moderate trust",
    },
    {
        "pattern": "external/",
        "trust_level": "low",
        "description": "External documents — low trust",
    },
    {
        "pattern": "user_uploaded/",
        "trust_level": "low",
        "description": "User-uploaded content — low trust",
    },
    {
        "pattern": "poisoned/",
        "trust_level": "untrusted",
        "description": "Known poisoned source",
    },
    {
        "pattern": "unknown/",
        "trust_level": "untrusted",
        "description": "Unknown source",
    },
]

# Minimum trust level score to be considered trusted
DEFAULT_THRESHOLD = 0.5


def check(
    source_path: str,
    threshold: float = DEFAULT_THRESHOLD,
    trust_rules: list[dict[str, str]] | None = None,
) -> DefenseResult:
    """Assign a trust level to a document based on its source path.

    Args:
        source_path: The file path or source identifier of the document.
        threshold: Minimum trust score to be considered trusted.
        trust_rules: Override list of trust rules.

    Returns:
        DefenseResult with trust level score and determination.
    """
    if not source_path or not source_path.strip():
        return DefenseResult(
            trusted=False,
            reason="Empty source path — cannot determine trust level",
            layer="source_verifier",
            score=0.0,
        )

    rules = trust_rules if trust_rules is not None else SOURCE_TRUST_RULES

    # Check each rule in order — first match wins
    for rule in rules:
        if rule["pattern"] in source_path:
            trust_level = rule["trust_level"]
            score = TRUST_LEVELS.get(trust_level, 0.0)
            trusted = score >= threshold

            return DefenseResult(
                trusted=trusted,
                reason=f"Source '{source_path}' — {rule['description']} (trust: {trust_level})",
                layer="source_verifier",
                score=score,
            )

    # No rule matched — default to low trust
    return DefenseResult(
        trusted=False,
        reason=f"Source '{source_path}' — no matching trust rule (default: low)",
        layer="source_verifier",
        score=TRUST_LEVELS["low"],
    )
