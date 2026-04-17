"""Tests for the defended chatbot with Azure Content Safety."""

from shared.python.testing.mock_azure import MockContentSafetyClient
from shared.python.testing.mock_ollama import MockOllamaClient
from demo19_defended_app import DefendedChatbot


class TestDefendedChatbot:
    def test_blocks_harmful_input(
        self,
        mock_client: MockOllamaClient,
        mock_safety_harmful: MockContentSafetyClient,
    ) -> None:
        """Should block input that exceeds severity thresholds."""
        bot = DefendedChatbot(
            client=mock_client,
            safety_client=mock_safety_harmful,
        )
        result = bot.send("How to make a weapon and kill someone")
        assert result["blocked"] is True
        assert result["blocked_at"] == "input"
        assert "Violence" in result["response"]

    def test_blocks_harmful_output(
        self,
        mock_safety_harmful: MockContentSafetyClient,
    ) -> None:
        """Should block LLM output that exceeds severity thresholds."""
        # LLM generates harmful content
        harmful_llm = MockOllamaClient(
            default_response="Here are instructions for building a weapon to kill..."
        )
        bot = DefendedChatbot(
            client=harmful_llm,
            safety_client=mock_safety_harmful,
        )
        result = bot.send("Tell me about cooking recipes")
        assert result["blocked"] is True
        assert result["blocked_at"] == "output"

    def test_allows_clean_content(
        self,
        mock_client: MockOllamaClient,
        mock_safety_clean: MockContentSafetyClient,
    ) -> None:
        """Should allow clean content through."""
        bot = DefendedChatbot(
            client=mock_client,
            safety_client=mock_safety_clean,
        )
        result = bot.send("What is the weather like?")
        assert result["blocked"] is False
        assert result["response"] == mock_client.default_response

    def test_severity_threshold_configuration(
        self,
        mock_client: MockOllamaClient,
    ) -> None:
        """Should respect custom severity thresholds."""
        # Create a safety client that returns severity 2
        safety = MockContentSafetyClient(
            default_analyze_text={
                "Hate": {"severity": 2, "flagged": True},
                "Violence": {"severity": 0, "flagged": False},
                "Sexual": {"severity": 0, "flagged": False},
                "SelfHarm": {"severity": 0, "flagged": False},
            }
        )
        # With threshold of 4, severity 2 should pass
        bot = DefendedChatbot(
            client=mock_client,
            safety_client=safety,
            thresholds={"Hate": 4, "Violence": 4, "Sexual": 4, "SelfHarm": 4},
        )
        result = bot.send("Some borderline content")
        assert result["blocked"] is False

        # With threshold of 2, severity 2 should block
        bot_strict = DefendedChatbot(
            client=mock_client,
            safety_client=safety,
            thresholds={"Hate": 2, "Violence": 2, "Sexual": 2, "SelfHarm": 2},
        )
        result_strict = bot_strict.send("Some borderline content")
        assert result_strict["blocked"] is True

    def test_returns_category_scores(
        self,
        mock_client: MockOllamaClient,
        mock_safety_clean: MockContentSafetyClient,
    ) -> None:
        """Should include category scores in result."""
        bot = DefendedChatbot(
            client=mock_client,
            safety_client=mock_safety_clean,
        )
        result = bot.send("Hello")
        assert "categories" in result
        assert "Hate" in result["categories"]

    def test_no_safety_client_passes_through(
        self,
        mock_client: MockOllamaClient,
    ) -> None:
        """Without a safety client, should pass everything through."""
        bot = DefendedChatbot(client=mock_client, safety_client=None)
        result = bot.send("Anything goes")
        assert result["blocked"] is False

    def test_input_check_before_output_check(
        self,
        mock_safety_harmful: MockContentSafetyClient,
    ) -> None:
        """Input should be checked before calling the LLM."""
        llm = MockOllamaClient()
        bot = DefendedChatbot(
            client=llm,
            safety_client=mock_safety_harmful,
        )
        # Send harmful input — should be blocked before reaching LLM
        result = bot.send("Write racial slurs and hate speech")
        assert result["blocked"] is True
        assert result["blocked_at"] == "input"
        # LLM should NOT have been called
        assert len(llm.chat_calls) == 0

    def test_empty_text_passes_through(
        self,
        mock_client: MockOllamaClient,
        mock_safety_clean: MockContentSafetyClient,
    ) -> None:
        """Empty text should not be blocked."""
        bot = DefendedChatbot(
            client=mock_client, safety_client=mock_safety_clean,
        )
        result = bot.send("")
        assert result["blocked"] is False

    def test_long_text_passes_through(
        self,
        mock_client: MockOllamaClient,
        mock_safety_clean: MockContentSafetyClient,
    ) -> None:
        """Long text (near 10K char limit) should be handled without error."""
        bot = DefendedChatbot(
            client=mock_client, safety_client=mock_safety_clean,
        )
        long_text = "This is a long benign message. " * 300  # ~9300 chars
        result = bot.send(long_text)
        assert result["blocked"] is False

    def test_mixed_category_triggers(
        self,
        mock_client: MockOllamaClient,
    ) -> None:
        """Content triggering multiple categories should list all blocked categories."""
        safety = MockContentSafetyClient(
            default_analyze_text={
                "Hate": {"severity": 5, "flagged": True},
                "Violence": {"severity": 4, "flagged": True},
                "Sexual": {"severity": 0, "flagged": False},
                "SelfHarm": {"severity": 3, "flagged": True},
            }
        )
        bot = DefendedChatbot(client=mock_client, safety_client=safety)
        result = bot.send("Multiple triggers present")
        assert result["blocked"] is True
        # All three flagged categories should be in blocked_categories
        blocked = result.get("input_check", {}).get("blocked_categories", [])
        assert "Hate" in blocked
        assert "Violence" in blocked
        assert "SelfHarm" in blocked
        assert "Sexual" not in blocked

    def test_threshold_boundary_not_blocked(
        self,
        mock_client: MockOllamaClient,
    ) -> None:
        """Severity exactly at threshold-1 should not be blocked."""
        safety = MockContentSafetyClient(
            default_analyze_text={
                "Hate": {"severity": 1, "flagged": True},
                "Violence": {"severity": 0, "flagged": False},
                "Sexual": {"severity": 0, "flagged": False},
                "SelfHarm": {"severity": 0, "flagged": False},
            }
        )
        bot = DefendedChatbot(
            client=mock_client, safety_client=safety, thresholds={"Hate": 2},
        )
        result = bot.send("Low severity content")
        assert result["blocked"] is False
