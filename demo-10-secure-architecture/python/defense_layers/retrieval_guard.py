"""Retrieval guard — defends the RAG pipeline.

Combines Demo 7's three-layer retrieval defense:
  1. Document validator — check metadata against allowlists
  2. Injection detector — scan chunk text for injection patterns
  3. Source verifier — assign trust levels by source path

A document chunk must pass all three layers to be allowed.
"""

import sys
from pathlib import Path
from typing import Any, TypedDict

# Add project root and Demo 7 retrieval_defenses to path
_project_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_project_root))

_demo7_defenses = _project_root / "demo-07-rag-defense" / "python" / "retrieval_defenses"
sys.path.insert(0, str(_demo7_defenses))

from document_validator import check as validate_document  # noqa: E402
from injection_detector import check as detect_injection  # noqa: E402
from source_verifier import check as verify_source  # noqa: E402


class GuardResult(TypedDict):
    allowed: bool
    blocked_by: str
    reason: str


def check(
    document_text: str,
    metadata: dict[str, str] | None = None,
    source_path: str = "",
) -> GuardResult:
    """Run a retrieved document chunk through the three-layer retrieval defense.

    Args:
        document_text: The text content of the retrieved chunk.
        metadata: Optional dict with 'author', 'source', 'date' keys.
        source_path: File path or source identifier for trust verification.

    Returns:
        GuardResult with allowed=False if any layer flags the document.
    """
    # Early return for empty/None document
    if not document_text:
        return GuardResult(
            allowed=False, blocked_by="retrieval_guard", reason="Empty document"
        )

    # Layer 1: Document metadata validation
    if metadata:
        doc_result = validate_document(metadata)
        if not doc_result["trusted"]:
            return GuardResult(
                allowed=False,
                blocked_by="document_validator",
                reason=doc_result["reason"],
            )

    # Layer 2: Injection pattern detection in document text
    injection_result = detect_injection(document_text)
    if not injection_result["trusted"]:
        return GuardResult(
            allowed=False,
            blocked_by="injection_detector",
            reason=injection_result["reason"],
        )

    # Layer 3: Source path trust verification
    if source_path:
        source_result = verify_source(source_path)
        if not source_result["trusted"]:
            return GuardResult(
                allowed=False,
                blocked_by="source_verifier",
                reason=source_result["reason"],
            )

    return GuardResult(
        allowed=True,
        blocked_by="",
        reason="Document passed all retrieval defense layers",
    )
