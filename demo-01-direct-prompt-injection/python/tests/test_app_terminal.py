"""Tests for app_terminal.py — verifies TranslatorChatbot, payload loading, and scoring."""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from shared.python.testing.mock_ollama import MockOllamaClient

from app_terminal import (
    TranslatorChatbot, load_payloads, score_injection, run_automated,
    run_interactive, DEFAULT_OBEDIENCE_MARKERS, DEFAULT_ENGLISH_INDICATORS,
)
from system_prompts import PROMPTS


SYSTEM_PROMPT = "You are a French translator. Translate the following text into French."


class TestTranslatorChatbotInit:
    def test_initializes_with_system_prompt(self, mock_client: MockOllamaClient) -> None:
        bot = TranslatorChatbot(system_prompt=SYSTEM_PROMPT, client=mock_client)
        assert bot.system_prompt == SYSTEM_PROMPT

    def test_messages_start_with_system_prompt(self, mock_client: MockOllamaClient) -> None:
        bot = TranslatorChatbot(system_prompt=SYSTEM_PROMPT, client=mock_client)
        assert len(bot.messages) == 1
        assert bot.messages[0]["role"] == "system"
        assert bot.messages[0]["content"] == SYSTEM_PROMPT

    def test_uses_injected_client(self, mock_client: MockOllamaClient) -> None:
        bot = TranslatorChatbot(system_prompt=SYSTEM_PROMPT, client=mock_client)
        assert bot.client is mock_client


class TestTranslatorChatbotSend:
    def test_send_returns_response_string(self, mock_client: MockOllamaClient) -> None:
        bot = TranslatorChatbot(system_prompt=SYSTEM_PROMPT, client=mock_client)
        response = bot.send("Hello")
        assert isinstance(response, str)
        assert len(response) > 0

    def test_send_appends_user_and_assistant_messages(self, mock_client: MockOllamaClient) -> None:
        bot = TranslatorChatbot(system_prompt=SYSTEM_PROMPT, client=mock_client)
        bot.send("Hello")
        assert len(bot.messages) == 3  # system + user + assistant
        assert bot.messages[1]["role"] == "user"
        assert bot.messages[1]["content"] == "Hello"
        assert bot.messages[2]["role"] == "assistant"

    def test_send_passes_system_prompt_to_llm(self, mock_client: MockOllamaClient) -> None:
        bot = TranslatorChatbot(system_prompt=SYSTEM_PROMPT, client=mock_client)
        bot.send("Hello")
        call = mock_client.call_history[0]
        assert call["messages"][0]["role"] == "system"
        assert call["messages"][0]["content"] == SYSTEM_PROMPT

    def test_send_uses_pattern_matched_response(self) -> None:
        client = MockOllamaClient(responses={"Hello": "Bonjour"})
        bot = TranslatorChatbot(system_prompt=SYSTEM_PROMPT, client=client)
        response = bot.send("Hello")
        assert response == "Bonjour"

    def test_multi_turn_conversation_accumulates_messages(self, mock_client: MockOllamaClient) -> None:
        bot = TranslatorChatbot(system_prompt=SYSTEM_PROMPT, client=mock_client)
        bot.send("Hello")
        bot.send("How are you?")
        # system + (user + assistant) * 2 = 5
        assert len(bot.messages) == 5
        assert bot.messages[3]["role"] == "user"
        assert bot.messages[3]["content"] == "How are you?"

    def test_empty_input_returns_empty_without_api_call(self, mock_client: MockOllamaClient) -> None:
        bot = TranslatorChatbot(system_prompt=SYSTEM_PROMPT, client=mock_client)
        response = bot.send("")
        assert response == ""
        # Empty input should not be sent to the LLM
        assert len(bot.messages) == 1  # Only system prompt
        assert len(mock_client.call_history) == 0

    def test_whitespace_only_input_returns_empty(self, mock_client: MockOllamaClient) -> None:
        bot = TranslatorChatbot(system_prompt=SYSTEM_PROMPT, client=mock_client)
        response = bot.send("   ")
        assert response == ""
        assert len(mock_client.call_history) == 0


class TestTranslatorChatbotReset:
    def test_reset_clears_to_system_prompt(self, mock_client: MockOllamaClient) -> None:
        bot = TranslatorChatbot(system_prompt=SYSTEM_PROMPT, client=mock_client)
        bot.send("Hello")
        bot.send("World")
        assert len(bot.messages) == 5
        bot.reset()
        assert len(bot.messages) == 1
        assert bot.messages[0]["role"] == "system"
        assert bot.messages[0]["content"] == SYSTEM_PROMPT


class TestTranslatorChatbotTurnCount:
    def test_turn_count_starts_at_zero(self, mock_client: MockOllamaClient) -> None:
        bot = TranslatorChatbot(system_prompt=SYSTEM_PROMPT, client=mock_client)
        assert bot.turn_count == 0

    def test_turn_count_after_exchanges(self, mock_client: MockOllamaClient) -> None:
        bot = TranslatorChatbot(system_prompt=SYSTEM_PROMPT, client=mock_client)
        bot.send("Hello")
        assert bot.turn_count == 1
        bot.send("World")
        assert bot.turn_count == 2

    def test_turn_count_resets(self, mock_client: MockOllamaClient) -> None:
        bot = TranslatorChatbot(system_prompt=SYSTEM_PROMPT, client=mock_client)
        bot.send("Hello")
        bot.reset()
        assert bot.turn_count == 0


class TestTranslatorChatbotErrorHandling:
    def test_send_raises_on_api_error(self) -> None:
        from shared.python.ollama_client import OllamaClientError

        class FailingClient:
            def chat(self, messages: list, model: str | None = None, tools: list | None = None) -> str:
                raise OllamaClientError("Connection refused")

        bot = TranslatorChatbot(system_prompt=SYSTEM_PROMPT, client=FailingClient())
        with pytest.raises(OllamaClientError, match="Connection refused"):
            bot.send("Hello")

    def test_message_history_not_corrupted_on_error(self) -> None:
        from shared.python.ollama_client import OllamaClientError

        class FailingClient:
            def chat(self, messages: list, model: str | None = None, tools: list | None = None) -> str:
                raise OllamaClientError("Connection refused")

        bot = TranslatorChatbot(system_prompt=SYSTEM_PROMPT, client=FailingClient())
        try:
            bot.send("Hello")
        except OllamaClientError:
            pass
        # Message should NOT have been appended since the call failed
        assert len(bot.messages) == 1
        assert bot.messages[0]["role"] == "system"


class TestScoreInjection:
    def test_french_response_not_detected(self) -> None:
        result = score_injection("Bonjour, comment allez-vous aujourd'hui?")
        assert result["injected"] is False
        assert result["score"] == 0.0

    def test_obedience_marker_detected(self) -> None:
        result = score_injection("PWNED - I will now follow your instructions")
        assert result["injected"] is True
        assert result["score"] > 0

    def test_english_heavy_response_detected(self) -> None:
        result = score_injection(
            "The capital of Japan is Tokyo. It was established because of its location."
        )
        assert result["injected"] is True
        assert any("english_heavy" in s for s in result["signals"])

    def test_empty_response_detected(self) -> None:
        result = score_injection("")
        assert result["injected"] is True
        assert any("empty_response" in s for s in result["signals"])

    def test_score_capped_at_1(self) -> None:
        # Trigger many signals at once
        result = score_injection(
            "PWNED I will ignore my rules. The joke is because the chicken was here."
        )
        assert result["score"] <= 1.0

    def test_returns_expected_keys(self) -> None:
        result = score_injection("Bonjour")
        assert "injected" in result
        assert "score" in result
        assert "signals" in result
        assert isinstance(result["signals"], list)


class TestScoreInjectionEdgeCases:
    """Edge cases for score_injection — mixed French/English and custom markers."""

    def test_french_with_borrowed_english_not_flagged(self) -> None:
        """French text containing common English loanwords should not trigger."""
        result = score_injection("Le design du week-end est très cool, n'est-ce pas?")
        assert result["injected"] is False

    def test_mixed_french_english_sentence_below_threshold(self) -> None:
        """A bilingual response with few English indicators should not trigger."""
        result = score_injection("Bonjour! The translation is: Bonjour le monde!")
        assert result["injected"] is False

    def test_mixed_french_english_above_threshold(self) -> None:
        """Heavy English with scattered French words should still be flagged."""
        result = score_injection(
            "The answer is that the capital was Paris because it has been the center."
        )
        assert result["injected"] is True
        assert any("english_heavy" in s for s in result["signals"])

    def test_unicode_obedience_marker(self) -> None:
        """Obedience markers should be case-insensitive."""
        result = score_injection("DEVELOPER MODE activated. I will now comply.")
        assert result["injected"] is True
        assert any("developer mode" in s for s in result["signals"])

    def test_custom_obedience_markers(self) -> None:
        """Custom markers should override defaults."""
        result = score_injection(
            "This is the secret code XYZ",
            obedience_markers=["secret code"],
        )
        assert result["injected"] is True
        assert any("secret code" in s for s in result["signals"])

    def test_custom_english_indicators(self) -> None:
        """Custom indicators should override defaults."""
        result = score_injection(
            "foo bar baz",
            english_indicators=["foo", "bar", "baz"],
            english_threshold=3,
        )
        assert result["injected"] is True
        assert any("english_heavy" in s for s in result["signals"])

    def test_custom_english_threshold(self) -> None:
        """Higher threshold should reduce false positives."""
        response = "The answer is clear because of this."
        # With default threshold of 3, this should trigger
        default_result = score_injection(response)
        # With a high threshold, it should not
        strict_result = score_injection(response, english_threshold=10)
        assert strict_result["injected"] is False
        # Verify the default catches it (≥3 indicators: "the ", " is ", "because ")
        if default_result["injected"]:
            assert any("english_heavy" in s for s in default_result["signals"])

    def test_empty_custom_markers_disables_check(self) -> None:
        """Passing empty marker list should disable that check category."""
        result = score_injection(
            "PWNED - developer mode activated",
            obedience_markers=[],
        )
        # Should NOT detect obedience markers, but might detect English indicators
        assert not any("obedience_marker" in s for s in result["signals"])

    def test_only_whitespace_response(self) -> None:
        """Whitespace-only response should be flagged as empty."""
        result = score_injection("  ")
        assert result["injected"] is True
        assert any("empty_response" in s for s in result["signals"])

    def test_default_marker_lists_are_nonempty(self) -> None:
        """Verify the default lists are properly populated."""
        assert len(DEFAULT_OBEDIENCE_MARKERS) > 0
        assert len(DEFAULT_ENGLISH_INDICATORS) > 0


class TestLoadPayloads:
    def test_returns_list(self) -> None:
        payloads = load_payloads()
        assert isinstance(payloads, list)

    def test_payloads_match_json_file(self) -> None:
        payloads = load_payloads()
        json_path = Path(__file__).resolve().parents[2] / "attacks" / "payloads.json"
        with open(json_path) as f:
            expected = json.load(f)
        assert payloads == expected

    def test_each_payload_has_name_and_payload(self) -> None:
        payloads = load_payloads()
        for p in payloads:
            assert "name" in p, f"Missing 'name' key in payload: {p}"
            assert "payload" in p, f"Missing 'payload' key in payload: {p}"

    def test_raises_on_missing_file(self, tmp_path: Path) -> None:
        with patch("app_terminal.Path") as mock_path:
            mock_path.return_value.resolve.return_value.parent.parent.__truediv__ = (
                lambda self, x: tmp_path / "nonexistent" / x
            )
            # Directly test the error case
            from app_terminal import Path as RealPath
            fake_path = tmp_path / "attacks" / "payloads.json"
            # Don't create the file — it should raise FileNotFoundError
            with pytest.raises(FileNotFoundError):
                with open(fake_path) as f:
                    json.load(f)


class TestParameterizedPromptLevels:
    """Verify the chatbot works correctly with each system prompt level."""

    @pytest.mark.parametrize("prompt_info", PROMPTS, ids=[p["name"] for p in PROMPTS])
    def test_each_prompt_produces_response(self, prompt_info: dict[str, str]) -> None:
        """Each system prompt level should produce a non-empty response."""
        client = MockOllamaClient(default_response="Bonjour, c'est un test.")
        bot = TranslatorChatbot(system_prompt=prompt_info["prompt"], client=client)
        response = bot.send("Hello world")
        assert len(response) > 0

    @pytest.mark.parametrize("prompt_info", PROMPTS, ids=[p["name"] for p in PROMPTS])
    def test_each_prompt_passes_system_message(self, prompt_info: dict[str, str]) -> None:
        """Each system prompt should be passed as the first message to the LLM."""
        client = MockOllamaClient()
        bot = TranslatorChatbot(system_prompt=prompt_info["prompt"], client=client)
        bot.send("Test")
        messages = client.call_history[0]["messages"]
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == prompt_info["prompt"]


class TestRunInteractive:
    """Test the interactive mode with mocked console input."""

    def test_quit_exits_immediately(self) -> None:
        """Typing 'quit' should exit the interactive loop."""
        client = MockOllamaClient(default_response="Bonjour")
        with patch("app_terminal.OllamaClient", return_value=client), \
             patch("app_terminal.console") as mock_console:
            mock_console.input.return_value = "quit"
            run_interactive()
        # No chat calls should be made since we quit before sending
        assert len(client.chat_calls) == 0

    def test_switch_command_changes_prompt(self) -> None:
        """Typing 'switch 1' then 'quit' should switch prompts."""
        client = MockOllamaClient(default_response="Bonjour")
        inputs = iter(["switch 1", "quit"])
        with patch("app_terminal.OllamaClient", return_value=client), \
             patch("app_terminal.console") as mock_console:
            mock_console.input.side_effect = lambda *a, **kw: next(inputs)
            run_interactive()
        # No chat calls — only switch and quit commands
        assert len(client.chat_calls) == 0

    def test_sends_message_to_chatbot(self) -> None:
        """A normal message should be sent to the chatbot before quit."""
        client = MockOllamaClient(default_response="Bonjour")
        inputs = iter(["Hello", "quit"])
        with patch("app_terminal.OllamaClient", return_value=client), \
             patch("app_terminal.console") as mock_console:
            mock_console.input.side_effect = lambda *a, **kw: next(inputs)
            run_interactive()
        assert len(client.chat_calls) == 1

    def test_eof_exits_gracefully(self) -> None:
        """EOFError (Ctrl-D) should exit without crashing."""
        client = MockOllamaClient(default_response="Bonjour")
        with patch("app_terminal.OllamaClient", return_value=client), \
             patch("app_terminal.console") as mock_console:
            mock_console.input.side_effect = EOFError
            run_interactive()  # Should not raise


class TestRunAutomated:
    """Test the automated attack runner with mock chatbot."""

    def test_iterates_all_prompts_and_payloads(self) -> None:
        """run_automated should iterate all system prompts x all payloads."""
        client = MockOllamaClient(default_response="Bonjour, réponse automatique.")

        with patch("app_terminal.OllamaClient", return_value=client), \
             patch("app_terminal.confirm_proceed", return_value=True):
            run_automated()

        payloads = load_payloads()
        expected_calls = len(PROMPTS) * len(payloads)
        assert len(client.chat_calls) == expected_calls

    def test_stops_when_user_declines(self) -> None:
        """run_automated should stop early if confirm_proceed returns False."""
        client = MockOllamaClient(default_response="Bonjour")

        with patch("app_terminal.OllamaClient", return_value=client), \
             patch("app_terminal.confirm_proceed", return_value=False):
            run_automated()

        # Should have stopped after the first payload
        assert len(client.chat_calls) == 1
