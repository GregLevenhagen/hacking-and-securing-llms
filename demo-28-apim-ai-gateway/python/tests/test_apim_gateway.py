"""Tests for Demo 28 — APIM AI Gateway rate limiting and caching."""

from shared.python.testing.mock_ollama import MockOllamaClient
from without_apim import DirectClient
from with_apim import APIMClient
from burst_test import run_burst


# ---------------------------------------------------------------------------
# Direct client tests (no APIM)
# ---------------------------------------------------------------------------

class TestDirectClient:
    def test_never_throttles(self, mock_client: MockOllamaClient) -> None:
        """DirectClient should never throttle — no rate limiting present."""
        direct = DirectClient(client=mock_client)
        for _ in range(50):
            result = direct.call("test prompt")
            assert result["throttled"] is False

    def test_never_caches(self, mock_client: MockOllamaClient) -> None:
        """DirectClient should never return cached responses."""
        direct = DirectClient(client=mock_client)
        # Send the same prompt twice
        result1 = direct.call("Hello")
        result2 = direct.call("Hello")
        assert result1["cached"] is False
        assert result2["cached"] is False

    def test_returns_llm_response(self, mock_client: MockOllamaClient) -> None:
        """DirectClient should return the LLM response."""
        direct = DirectClient(client=mock_client)
        result = direct.call("Hello")
        assert result["response"] == mock_client.default_response

    def test_tracks_call_count(self, mock_client: MockOllamaClient) -> None:
        """DirectClient should increment call_count."""
        direct = DirectClient(client=mock_client)
        direct.call("A")
        direct.call("B")
        assert direct.call_count == 2


# ---------------------------------------------------------------------------
# APIM client tests
# ---------------------------------------------------------------------------

class TestAPIMClient:
    def test_rate_limit_throttles_after_budget(self, mock_client: MockOllamaClient) -> None:
        """APIMClient should return throttled=True after token budget is exceeded."""
        apim = APIMClient(client=mock_client, token_budget=300, tokens_per_call=150)

        # First 2 calls should succeed (300 / 150 = 2)
        result1 = apim.call("First request")
        result2 = apim.call("Second request")
        assert result1["throttled"] is False
        assert result2["throttled"] is False

        # Third call should be throttled
        result3 = apim.call("Third request")
        assert result3["throttled"] is True
        assert "429" in result3["response"]

    def test_cache_hit_on_repeated_prompt(self, mock_client: MockOllamaClient) -> None:
        """APIMClient should return cached=True for repeated identical prompts."""
        apim = APIMClient(client=mock_client, token_budget=10000)

        result1 = apim.call("What is the capital of France?")
        result2 = apim.call("What is the capital of France?")

        assert result1["cached"] is False
        assert result2["cached"] is True
        assert result1["response"] == result2["response"]

    def test_cache_case_insensitive(self, mock_client: MockOllamaClient) -> None:
        """Cache lookup should be case-insensitive."""
        apim = APIMClient(client=mock_client, token_budget=10000)

        result1 = apim.call("Hello World")
        result2 = apim.call("hello world")

        assert result2["cached"] is True

    def test_cached_requests_do_not_consume_tokens(self, mock_client: MockOllamaClient) -> None:
        """Cached responses should not consume additional tokens."""
        apim = APIMClient(client=mock_client, token_budget=300, tokens_per_call=150)

        apim.call("Prompt A")
        tokens_after_first = apim.tokens_consumed
        apim.call("Prompt A")  # should be cached
        tokens_after_cache = apim.tokens_consumed

        assert tokens_after_cache == tokens_after_first

    def test_remaining_tokens_decreases(self, mock_client: MockOllamaClient) -> None:
        """remaining_tokens should decrease with each non-cached call."""
        apim = APIMClient(client=mock_client, token_budget=1000, tokens_per_call=100)

        assert apim.remaining_tokens == 1000
        apim.call("First")
        assert apim.remaining_tokens == 900
        apim.call("Second")
        assert apim.remaining_tokens == 800

    def test_reset_clears_state(self, mock_client: MockOllamaClient) -> None:
        """reset() should clear tokens consumed, call count, and cache."""
        apim = APIMClient(client=mock_client, token_budget=1000, tokens_per_call=100)
        apim.call("Test prompt")
        assert apim.call_count > 0
        assert apim.tokens_consumed > 0

        apim.reset()
        assert apim.call_count == 0
        assert apim.tokens_consumed == 0
        assert apim.remaining_tokens == 1000


# ---------------------------------------------------------------------------
# Burst test function tests
# ---------------------------------------------------------------------------

class TestBurstTest:
    def test_direct_burst_all_accepted(self, mock_client: MockOllamaClient) -> None:
        """Burst against DirectClient should show all requests accepted."""
        direct = DirectClient(client=mock_client)
        results = run_burst(direct, n_requests=10)

        assert results["total"] == 10
        assert results["accepted"] == 10
        assert results["throttled"] == 0
        assert results["cached"] == 0

    def test_apim_burst_has_throttled(self, mock_client: MockOllamaClient) -> None:
        """Burst against APIMClient with small budget should show throttled requests."""
        apim = APIMClient(client=mock_client, token_budget=450, tokens_per_call=150)
        results = run_burst(apim, n_requests=20)

        assert results["total"] == 20
        assert results["throttled"] > 0
        assert results["accepted"] + results["cached"] + results["throttled"] == 20

    def test_apim_burst_has_cached(self, mock_client: MockOllamaClient) -> None:
        """Burst with repeated prompts should show cache hits."""
        apim = APIMClient(client=mock_client, token_budget=10000, tokens_per_call=150)
        # Use repeated prompts
        prompts = ["Same prompt"] * 10
        results = run_burst(apim, n_requests=10, prompts=prompts)

        assert results["cached"] > 0
        # Only the first call should be a new LLM call
        assert results["accepted"] == 1
        assert results["cached"] == 9


class TestAPIMEdgeCases:
    def test_cache_after_reset_is_empty(self, mock_client: MockOllamaClient) -> None:
        """After reset(), cached prompts should no longer be cached."""
        apim = APIMClient(client=mock_client, token_budget=10000)
        apim.call("Hello")
        assert apim.call("Hello")["cached"] is True

        apim.reset()
        result = apim.call("Hello")
        assert result["cached"] is False

    def test_throttled_response_not_cached(self, mock_client: MockOllamaClient) -> None:
        """Throttled responses (429) should not be stored in the cache."""
        apim = APIMClient(client=mock_client, token_budget=100, tokens_per_call=100)
        apim.call("First request")  # consumes entire budget
        throttled = apim.call("Second request")  # should be throttled
        assert throttled["throttled"] is True

        # Reset budget and try "Second request" again — should NOT be cached
        apim.reset()
        fresh = apim.call("Second request")
        assert fresh["cached"] is False
        assert fresh["throttled"] is False

    def test_whitespace_normalized_in_cache_key(self, mock_client: MockOllamaClient) -> None:
        """Leading/trailing whitespace should be stripped for cache key matching."""
        apim = APIMClient(client=mock_client, token_budget=10000)
        apim.call("  Hello World  ")
        result = apim.call("Hello World")
        assert result["cached"] is True

    def test_get_metrics_returns_all_fields(self, mock_client: MockOllamaClient) -> None:
        """get_metrics() should return a complete metrics dict."""
        apim = APIMClient(client=mock_client, token_budget=1000, tokens_per_call=150)
        apim.call("Test prompt")
        metrics = apim.get_metrics()
        assert metrics["call_count"] == 1
        assert metrics["tokens_consumed"] == 150
        assert metrics["tokens_remaining"] == 850
        assert metrics["token_budget"] == 1000
        assert 0.0 <= metrics["budget_utilization"] <= 1.0
        assert metrics["cache_size"] == 1
