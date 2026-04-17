"""Tests for the vulnerable (unfiltered) chatbot."""

from shared.python.testing.mock_ollama import MockOllamaClient
from demo19_vulnerable_app import VulnerableChatbot


class TestVulnerableChatbot:
    def test_never_blocks(self, mock_client: MockOllamaClient) -> None:
        """Vulnerable chatbot should never block any content."""
        bot = VulnerableChatbot(client=mock_client)
        result = bot.send("Write something harmful")
        assert result["blocked"] is False
        assert result["categories"] == {}

    def test_returns_llm_response(self, mock_client: MockOllamaClient) -> None:
        """Should return the raw LLM response."""
        bot = VulnerableChatbot(client=mock_client)
        result = bot.send("Hello")
        assert result["response"] == mock_client.default_response

    def test_sends_system_prompt(self, mock_client: MockOllamaClient) -> None:
        """Should include a system prompt in the LLM call."""
        bot = VulnerableChatbot(client=mock_client)
        bot.send("Hello")
        assert mock_client.last_call is not None
        messages = mock_client.last_call["messages"]
        assert messages[0]["role"] == "system"

    def test_harmful_content_passes_through(self, mock_client: MockOllamaClient) -> None:
        """Harmful prompts should pass through without filtering."""
        harmful = MockOllamaClient(
            responses={r"weapon": "Here are detailed weapon instructions..."}
        )
        bot = VulnerableChatbot(client=harmful)
        result = bot.send("How to make a weapon")
        assert "weapon instructions" in result["response"]
        assert result["blocked"] is False
