"""Burst test utility for comparing unprotected vs APIM-protected LLM access.

Sends a rapid series of requests to a client and tallies how many were
accepted, throttled, or served from cache. This simulates a burst traffic
scenario (e.g., a denial-of-wallet attack or misconfigured batch job).
"""

from typing import Any


def run_burst(
    client: Any,
    n_requests: int = 20,
    prompts: list[str] | None = None,
) -> dict[str, int]:
    """Send a burst of rapid requests and tally the results.

    Args:
        client: A client object with a ``call(prompt) -> dict`` method.
            The returned dict must have ``throttled`` and ``cached`` boolean keys.
        n_requests: Number of requests to send in the burst.
        prompts: Optional list of prompts to cycle through. If None, a
            default set of repeated prompts is used (to trigger cache hits).

    Returns:
        Dict with counts: accepted, throttled, cached.
    """
    if prompts is None:
        # Use a small set of prompts to trigger cache hits
        prompts = [
            "What is the capital of France?",
            "Explain quantum computing briefly.",
            "What is the capital of France?",  # repeated
            "Summarize the history of AI.",
            "Explain quantum computing briefly.",  # repeated
        ]

    counters = {
        "accepted": 0,
        "throttled": 0,
        "cached": 0,
        "total": n_requests,
    }

    for i in range(n_requests):
        prompt = prompts[i % len(prompts)]
        result = client.call(prompt)

        if result.get("throttled", False):
            counters["throttled"] += 1
        elif result.get("cached", False):
            counters["cached"] += 1
        else:
            counters["accepted"] += 1

    return counters
