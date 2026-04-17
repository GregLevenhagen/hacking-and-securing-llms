"""Relevance scorer using sentence-transformers cross-encoder.

Reranks retrieved chunks by semantic relevance to the query.
Poisoned documents that are off-topic or contain injected instructions
typically score lower on genuine relevance to the user's query.
"""

from typing import Any, TypedDict


class DefenseResult(TypedDict):
    trusted: bool
    reason: str
    layer: str
    score: float


# Default relevance threshold — chunks below this are considered suspicious
DEFAULT_THRESHOLD = 0.5

# Default cross-encoder model
DEFAULT_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


def _load_cross_encoder(model_name: str = DEFAULT_MODEL) -> Any:
    """Load a sentence-transformers CrossEncoder model.

    Returns the CrossEncoder instance or raises ImportError if
    sentence-transformers is not installed.
    """
    from sentence_transformers import CrossEncoder  # type: ignore[import-untyped]

    return CrossEncoder(model_name)


def check(
    query: str,
    document_text: str,
    threshold: float = DEFAULT_THRESHOLD,
    model: Any = None,
    model_name: str = DEFAULT_MODEL,
) -> DefenseResult:
    """Score a document's relevance to a query using a cross-encoder.

    Args:
        query: The user's search query.
        document_text: The retrieved document chunk text.
        threshold: Minimum relevance score to be considered trusted.
        model: Pre-loaded CrossEncoder instance (for testing/reuse).
        model_name: Model name to load if model is not provided.

    Returns:
        DefenseResult with score indicating relevance (0-1 range).
    """
    if not query or not query.strip() or not document_text or not document_text.strip():
        return DefenseResult(
            trusted=False,
            reason="Empty query or document text — cannot score relevance",
            layer="relevance_scorer",
            score=0.0,
        )

    try:
        encoder = model if model is not None else _load_cross_encoder(model_name)

        # CrossEncoder.predict returns a raw logit score
        raw_score: float = float(encoder.predict([(query, document_text)]))

        # Normalize to 0-1 range using sigmoid
        import math
        score = 1.0 / (1.0 + math.exp(-raw_score))

        if score >= threshold:
            return DefenseResult(
                trusted=True,
                reason=f"Relevance score {score:.3f} meets threshold {threshold}",
                layer="relevance_scorer",
                score=score,
            )
        else:
            return DefenseResult(
                trusted=False,
                reason=f"Low relevance score {score:.3f} (threshold {threshold})",
                layer="relevance_scorer",
                score=score,
            )

    except ImportError:
        # sentence-transformers not installed — fail open
        return DefenseResult(
            trusted=True,
            reason="sentence-transformers not installed — skipping relevance check",
            layer="relevance_scorer",
            score=0.5,
        )
    except Exception as e:
        # On error, fail open but report
        return DefenseResult(
            trusted=True,
            reason=f"Relevance scorer error: {str(e)}",
            layer="relevance_scorer",
            score=0.5,
        )
