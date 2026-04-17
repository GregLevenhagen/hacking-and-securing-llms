"""Input guard — first line of defense.

Combines Demo 6's three-layer input defense:
  1. Input sanitizer — strip invisible chars and homoglyphs
  2. Regex filter — match known injection patterns
  3. LLM judge — ask a second LLM to classify the input

The pipeline runs in order and short-circuits on the first block.
The sanitizer always runs first (it cleans but never blocks).
"""

import sys
from pathlib import Path
from typing import Any, TypedDict

# Add project root and Demo 6 input_defenses to path
_project_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_project_root))

_demo6_defenses = _project_root / "demo-06-input-sanitization" / "python" / "input_defenses"
sys.path.insert(0, str(_demo6_defenses))

from input_sanitizer import sanitize  # noqa: E402
from regex_filter import check as regex_check  # noqa: E402
from llm_judge import check as judge_check  # noqa: E402
from shared.python.ollama_client import OllamaClient  # noqa: E402


class GuardResult(TypedDict):
    allowed: bool
    blocked_by: str
    reason: str


def check(
    user_input: str,
    client: OllamaClient | None = None,
    use_llm_judge: bool = True,
) -> GuardResult:
    """Run user input through the three-layer input defense pipeline.

    Args:
        user_input: Raw user input string.
        client: Optional OllamaClient for the LLM judge layer.
        use_llm_judge: Whether to run the LLM judge (can be disabled for speed).

    Returns:
        GuardResult with allowed=False if any layer blocks the input.
    """
    # Early return for empty/None input
    if not user_input or not user_input.strip():
        return GuardResult(allowed=True, blocked_by="", reason="Empty input")

    # Layer 1: Sanitize (never blocks, but cleans the text)
    sanitizer_result = sanitize(user_input)
    cleaned_input: str = sanitizer_result["sanitized_text"]

    # Layer 2: Regex filter
    regex_result = regex_check(cleaned_input)
    if regex_result["blocked"]:
        return GuardResult(
            allowed=False,
            blocked_by="regex_filter",
            reason=regex_result["reason"],
        )

    # Layer 3: LLM judge (optional — requires a running LLM)
    if use_llm_judge:
        judge_result = judge_check(cleaned_input, client=client)
        if judge_result["blocked"]:
            return GuardResult(
                allowed=False,
                blocked_by="llm_judge",
                reason=judge_result["reason"],
            )

    return GuardResult(
        allowed=True,
        blocked_by="",
        reason="Input passed all defense layers",
    )
