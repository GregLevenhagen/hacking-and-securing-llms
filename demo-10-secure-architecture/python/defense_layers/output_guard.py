"""Output guard — validates LLM responses before they reach the user.

Combines Demo 8's three-layer output defense:
  1. Content filter — blocks leaked API keys, internal URLs, secrets
  2. PII detector — catches SSNs, emails, phone numbers, credit cards
  3. Response constrainer — enforces length limits and topic restrictions

All three layers run on every response (no short-circuit) so all
violations are reported together.
"""

import sys
from pathlib import Path
from typing import TypedDict

# Add Demo 8 validators to path
_project_root = Path(__file__).resolve().parents[3]
_demo8_validators = _project_root / "demo-08-output-validation" / "python" / "validators"
sys.path.insert(0, str(_demo8_validators))

from content_filter import check as filter_content  # noqa: E402
from pii_detector import check as detect_pii  # noqa: E402
from response_constrainer import check as constrain_response  # noqa: E402


class GuardResult(TypedDict):
    allowed: bool
    blocked_by: str
    reason: str


def check(
    llm_output: str,
    max_length: int | None = None,
) -> GuardResult:
    """Run LLM output through the three-layer output defense pipeline.

    Args:
        llm_output: The raw LLM response string.
        max_length: Optional max response length (chars). Defaults to 2000.

    Returns:
        GuardResult with allowed=False if any validator finds violations.
    """
    # Early return for empty/None output
    if not llm_output or not llm_output.strip():
        return GuardResult(allowed=True, blocked_by="", reason="Empty output")

    blocked_layers: list[str] = []
    all_reasons: list[str] = []

    # Layer 1: Content filter (API keys, secrets, internal URLs)
    content_result = filter_content(llm_output)
    if not content_result["valid"]:
        blocked_layers.append("content_filter")
        all_reasons.extend(content_result["violations"])

    # Layer 2: PII detector (SSNs, emails, phones, credit cards)
    pii_result = detect_pii(llm_output)
    if not pii_result["valid"]:
        blocked_layers.append("pii_detector")
        all_reasons.extend(pii_result["violations"])

    # Layer 3: Response constrainer (length + topic restrictions)
    constrainer_result = constrain_response(llm_output, max_length=max_length)
    if not constrainer_result["valid"]:
        blocked_layers.append("response_constrainer")
        all_reasons.extend(constrainer_result["violations"])

    if blocked_layers:
        return GuardResult(
            allowed=False,
            blocked_by=", ".join(blocked_layers),
            reason="; ".join(all_reasons),
        )

    return GuardResult(
        allowed=True,
        blocked_by="",
        reason="Output passed all validation layers",
    )
