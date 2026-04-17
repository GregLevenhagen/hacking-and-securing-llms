"""Defense layer metrics — tracks how often each layer triggers.

Provides a lightweight in-memory counter for blocked/passed/error counts
per defense layer, useful for demo summaries and observability.
"""

from typing import TypedDict


class LayerMetrics(TypedDict):
    blocked: int
    passed: int
    errors: int


# Global counters keyed by layer name
_metrics: dict[str, LayerMetrics] = {}


def record(layer: str, *, blocked: bool, error: bool = False) -> None:
    """Record a defense layer check result.

    Args:
        layer: The defense layer name (e.g., 'regex_filter', 'llm_judge').
        blocked: Whether the input was blocked.
        error: Whether the check encountered an error.
    """
    if layer not in _metrics:
        _metrics[layer] = LayerMetrics(blocked=0, passed=0, errors=0)

    if error:
        _metrics[layer]["errors"] += 1
    elif blocked:
        _metrics[layer]["blocked"] += 1
    else:
        _metrics[layer]["passed"] += 1


def get_metrics(layer: str | None = None) -> dict[str, LayerMetrics]:
    """Get metrics for a specific layer or all layers.

    Args:
        layer: Optional layer name to filter. Returns all if None.

    Returns:
        Dict of layer name → LayerMetrics.
    """
    if layer is not None:
        if layer in _metrics:
            return {layer: _metrics[layer].copy()}
        return {layer: LayerMetrics(blocked=0, passed=0, errors=0)}
    return {k: v.copy() for k, v in _metrics.items()}


def get_total_blocked() -> int:
    """Return total blocked count across all layers."""
    return sum(m["blocked"] for m in _metrics.values())


def get_total_passed() -> int:
    """Return total passed count across all layers."""
    return sum(m["passed"] for m in _metrics.values())


def reset(layer: str | None = None) -> None:
    """Reset metrics for a specific layer or all layers.

    Args:
        layer: Optional layer name to reset. Resets all if None.
    """
    if layer is not None:
        if layer in _metrics:
            _metrics[layer] = LayerMetrics(blocked=0, passed=0, errors=0)
    else:
        _metrics.clear()
