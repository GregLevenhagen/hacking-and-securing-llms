"""Document metadata validator for RAG defense.

Checks document metadata (author, date, source) against an allowlist
of trusted values. Documents with missing or untrusted metadata are
flagged as potentially poisoned.
"""

from datetime import datetime
from typing import TypedDict


class DefenseResult(TypedDict):
    trusted: bool
    reason: str
    layer: str
    score: float


# Allowlisted metadata values
TRUSTED_AUTHORS: list[str] = [
    "hr_department",
    "product_team",
    "legal_team",
    "engineering",
    "acmetech_official",
    "admin",
]

TRUSTED_SOURCES: list[str] = [
    "company_policy.txt",
    "product_faq.txt",
    "employee_handbook.txt",
    "internal_docs",
]

# Maximum age in days for documents to be considered current
MAX_DOCUMENT_AGE_DAYS = 365


def check(
    document: dict[str, str],
    trusted_authors: list[str] | None = None,
    trusted_sources: list[str] | None = None,
) -> DefenseResult:
    """Validate document metadata against allowlists.

    Args:
        document: Dict with optional keys: 'source', 'author', 'date', 'content'.
        trusted_authors: Override list of trusted author names.
        trusted_sources: Override list of trusted source filenames.

    Returns:
        DefenseResult with trusted=False if metadata fails validation.
    """
    if not document:
        return DefenseResult(
            trusted=False,
            reason="Empty document — no metadata to validate",
            layer="document_validator",
            score=0.0,
        )

    authors = trusted_authors if trusted_authors is not None else TRUSTED_AUTHORS
    sources = trusted_sources if trusted_sources is not None else TRUSTED_SOURCES

    issues: list[str] = []

    # Check for missing metadata
    if "author" not in document or not document.get("author", "").strip():
        issues.append("Missing author metadata")

    if "source" not in document or not document.get("source", "").strip():
        issues.append("Missing source metadata")

    # Validate author against allowlist
    author = document.get("author", "").strip().lower()
    if author and author not in [a.lower() for a in authors]:
        issues.append(f"Unknown author: '{document.get('author', '')}'")

    # Validate source against allowlist
    source = document.get("source", "").strip()
    if source and source not in sources:
        issues.append(f"Untrusted source: '{source}'")

    # Validate date if present
    date_str = document.get("date", "").strip()
    if date_str:
        try:
            doc_date = datetime.fromisoformat(date_str)
            age_days = (datetime.now() - doc_date).days
            if age_days > MAX_DOCUMENT_AGE_DAYS:
                issues.append(f"Document is {age_days} days old (max {MAX_DOCUMENT_AGE_DAYS})")
            elif age_days < 0:
                issues.append("Document has a future date")
        except ValueError:
            issues.append(f"Invalid date format: '{date_str}'")

    # Calculate trust score
    if not issues:
        score = 1.0
    else:
        # Deduct proportionally based on number of issues
        score = max(0.0, 1.0 - (len(issues) * 0.3))

    return DefenseResult(
        trusted=len(issues) == 0,
        reason="; ".join(issues) if issues else "Document metadata validated",
        layer="document_validator",
        score=score,
    )
