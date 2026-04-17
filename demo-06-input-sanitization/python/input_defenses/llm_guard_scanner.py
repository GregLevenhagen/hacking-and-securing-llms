"""LLM Guard prompt injection scanner.

Integrates the llm-guard library's PromptInjection scanner, which uses
a fine-tuned classifier model to detect injection attempts. The model
(~200MB) is downloaded on first run.
"""

from typing import TypedDict


class ScannerResult(TypedDict):
    blocked: bool
    reason: str
    layer: str
    score: float


# Threshold for blocking — scores above this are considered injections
DEFAULT_THRESHOLD = 0.5


def check(user_input: str, threshold: float = DEFAULT_THRESHOLD) -> ScannerResult:
    """Scan user input using llm-guard's PromptInjection scanner.

    Args:
        user_input: The raw user input string.
        threshold: Score threshold above which input is blocked (0.0-1.0).

    Returns:
        ScannerResult with blocked=True if the classifier detects injection.
    """
    if not user_input or not user_input.strip():
        return ScannerResult(
            blocked=False,
            reason="LLM Guard: Empty input — nothing to scan",
            layer="llm_guard_scanner",
            score=0.0,
        )

    if not (0.0 <= threshold <= 1.0):
        raise ValueError(f"threshold must be between 0.0 and 1.0, got {threshold}")

    try:
        from llm_guard.input_scanners import PromptInjection

        scanner = PromptInjection(threshold=threshold)
        sanitized_output, is_valid, risk_score = scanner.scan(user_input)

        if not is_valid:
            return ScannerResult(
                blocked=True,
                reason=f"LLM Guard: Prompt injection detected (score: {risk_score:.2f})",
                layer="llm_guard_scanner",
                score=risk_score,
            )

        return ScannerResult(
            blocked=False,
            reason=f"LLM Guard: Input appears safe (score: {risk_score:.2f})",
            layer="llm_guard_scanner",
            score=risk_score,
        )

    except ImportError:
        return ScannerResult(
            blocked=False,
            reason="LLM Guard: llm-guard library not installed",
            layer="llm_guard_scanner",
            score=0.0,
        )
    except Exception as e:
        return ScannerResult(
            blocked=False,
            reason=f"LLM Guard error: {str(e)}",
            layer="llm_guard_scanner",
            score=0.0,
        )
