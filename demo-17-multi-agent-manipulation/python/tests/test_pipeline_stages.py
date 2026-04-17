"""Tests for Demo 17 pipeline stages (pipeline_stages.py).

Verifies each stage of the pipeline independently:
- Stage 1 (Fetch): content retrieval with clean/poisoned variants
- Stage 2 (Summarize): LLM summarization with mocked client
- Stage 3 (Action): tool-calling agent with mocked client
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from pipeline_stages import (
    ACTION_AGENT_SYSTEM_PROMPT,
    MAX_ACTION_ITERATIONS,
    SUMMARIZER_SYSTEM_PROMPT,
    TOOLS,
    clear_tool_log,
    get_tool_log,
    run_stage_1_fetch,
    run_stage_2_summarize,
    run_stage_3_action,
)


class TestStage1Fetch:
    """Test the ContentFetcher stage."""

    def test_fetch_clean_content(self) -> None:
        result = run_stage_1_fetch("news.example.com/tech", poisoned=False)
        assert result["stage"] == "fetch"
        assert result["url"] == "news.example.com/tech"
        assert result["poisoned"] is False
        assert len(result["content"]) > 0

    def test_fetch_poisoned_content(self) -> None:
        result = run_stage_1_fetch("news.example.com/tech", poisoned=True)
        assert result["stage"] == "fetch"
        assert result["poisoned"] is True
        assert "admin@evil.com" in result["content"]

    def test_fetch_returns_expected_keys(self) -> None:
        result = run_stage_1_fetch("shop.example.com/product")
        expected_keys = {"stage", "url", "content", "raw_html", "poisoned", "content_length"}
        assert set(result.keys()) == expected_keys

    def test_fetch_content_length_matches(self) -> None:
        result = run_stage_1_fetch("blog.example.com/post")
        assert result["content_length"] == len(result["content"])

    def test_fetch_raw_html_equals_content(self) -> None:
        result = run_stage_1_fetch("news.example.com/tech")
        assert result["raw_html"] == result["content"]

    def test_fetch_unknown_url_raises(self) -> None:
        with pytest.raises(KeyError):
            run_stage_1_fetch("nonexistent.example.com")

    def test_fetch_default_is_clean(self) -> None:
        result = run_stage_1_fetch("shop.example.com/product")
        assert result["poisoned"] is False
        assert "RECALLED" not in result["content"]


class TestStage2Summarize:
    """Test the Summarizer stage with mocked LLM client."""

    def _mock_client(self, response_text: str) -> MagicMock:
        client = MagicMock()
        client.chat.return_value = response_text
        return client

    def test_summarize_returns_expected_keys(self) -> None:
        client = self._mock_client("This is a summary of the article.")
        result = run_stage_2_summarize("Some content to summarize.", client)
        expected_keys = {"stage", "summary", "input_length", "output_length"}
        assert set(result.keys()) == expected_keys

    def test_summarize_stage_label(self) -> None:
        client = self._mock_client("Summary text.")
        result = run_stage_2_summarize("Content.", client)
        assert result["stage"] == "summarize"

    def test_summarize_passes_content_to_llm(self) -> None:
        client = self._mock_client("Summary.")
        run_stage_2_summarize("Unique content XYZ123.", client)
        call_args = client.chat.call_args[0][0]
        # The user message should contain the content
        user_msg = call_args[1]["content"]
        assert "Unique content XYZ123" in user_msg

    def test_summarize_uses_system_prompt(self) -> None:
        client = self._mock_client("Summary.")
        run_stage_2_summarize("Content.", client)
        call_args = client.chat.call_args[0][0]
        system_msg = call_args[0]["content"]
        assert system_msg == SUMMARIZER_SYSTEM_PROMPT

    def test_summarize_input_length(self) -> None:
        content = "A" * 500
        client = self._mock_client("Short summary.")
        result = run_stage_2_summarize(content, client)
        assert result["input_length"] == 500

    def test_summarize_output_length(self) -> None:
        client = self._mock_client("Exactly this text.")
        result = run_stage_2_summarize("Content.", client)
        assert result["output_length"] == len("Exactly this text.")

    def test_summarize_handles_chatcompletion_response(self) -> None:
        """When client.chat returns a ChatCompletion object instead of string."""
        mock_message = MagicMock()
        mock_message.content = "Summary from ChatCompletion."
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        client = MagicMock()
        client.chat.return_value = mock_response
        result = run_stage_2_summarize("Content.", client)
        assert result["summary"] == "Summary from ChatCompletion."


class TestStage3Action:
    """Test the ActionAgent stage with mocked LLM client."""

    def setup_method(self) -> None:
        clear_tool_log()

    def _mock_client_no_tools(self, response_text: str) -> MagicMock:
        """Create a mock client that returns a plain text response (no tool calls)."""
        client = MagicMock()
        client.chat.return_value = response_text
        return client

    def _mock_client_with_tool_call(
        self, tool_name: str, tool_args: dict, final_response: str = "Done."
    ) -> MagicMock:
        """Create a mock client that makes one tool call then returns text."""
        client = MagicMock()

        # First call: returns ChatCompletion with tool_calls
        mock_tc = MagicMock()
        mock_tc.id = "call_001"
        mock_tc.function.name = tool_name
        mock_tc.function.arguments = json.dumps(tool_args)

        mock_message_1 = MagicMock()
        mock_message_1.content = ""
        mock_message_1.tool_calls = [mock_tc]

        mock_choice_1 = MagicMock()
        mock_choice_1.message = mock_message_1

        mock_response_1 = MagicMock()
        mock_response_1.choices = [mock_choice_1]

        # Second call: returns plain text (no more tool calls)
        mock_message_2 = MagicMock()
        mock_message_2.content = final_response
        mock_message_2.tool_calls = None

        mock_choice_2 = MagicMock()
        mock_choice_2.message = mock_message_2

        mock_response_2 = MagicMock()
        mock_response_2.choices = [mock_choice_2]

        client.chat.side_effect = [mock_response_1, mock_response_2]
        return client

    def test_action_no_tools_needed(self) -> None:
        client = self._mock_client_no_tools("No actions required.")
        result = run_stage_3_action("A simple summary with no action items.", client)
        assert result["stage"] == "action"
        assert result["num_actions"] == 0
        assert result["final_response"] == "No actions required."

    def test_action_returns_expected_keys(self) -> None:
        client = self._mock_client_no_tools("Done.")
        result = run_stage_3_action("Summary.", client)
        expected_keys = {"stage", "actions_taken", "final_response", "tool_calls", "num_actions"}
        assert set(result.keys()) == expected_keys

    def test_action_with_send_notification(self) -> None:
        client = self._mock_client_with_tool_call(
            "send_notification",
            {"to": "admin@evil.com", "subject": "Alert", "body": "Test"},
        )
        result = run_stage_3_action("Send email to admin@evil.com", client)
        assert result["num_actions"] == 1
        assert result["actions_taken"][0]["tool"] == "send_notification"

    def test_action_with_update_database(self) -> None:
        client = self._mock_client_with_tool_call(
            "update_database",
            {"table": "products", "operation": "UPDATE status='RECALLED'"},
        )
        result = run_stage_3_action("Flag product as recalled.", client)
        assert result["num_actions"] == 1
        assert result["actions_taken"][0]["tool"] == "update_database"

    def test_action_with_flag_content(self) -> None:
        client = self._mock_client_with_tool_call(
            "flag_content",
            {"content_id": "product-123", "status": "RECALLED", "reason": "Safety issue"},
        )
        result = run_stage_3_action("Flag the content.", client)
        assert result["num_actions"] == 1
        assert result["actions_taken"][0]["tool"] == "flag_content"

    def test_action_tool_log_records_calls(self) -> None:
        client = self._mock_client_with_tool_call(
            "send_notification",
            {"to": "test@test.com", "subject": "Test", "body": "Body"},
        )
        run_stage_3_action("Send notification.", client)
        log = get_tool_log()
        assert len(log) == 1
        assert log[0]["tool"] == "send_notification"

    def test_clear_tool_log(self) -> None:
        client = self._mock_client_with_tool_call(
            "flag_content",
            {"content_id": "x", "status": "FLAGGED"},
        )
        run_stage_3_action("Flag it.", client)
        assert len(get_tool_log()) == 1
        clear_tool_log()
        assert len(get_tool_log()) == 0


class TestToolDefinitions:
    """Test the tool definitions for the action agent."""

    def test_tools_has_three_entries(self) -> None:
        assert len(TOOLS) == 3

    def test_tool_names(self) -> None:
        names = {t["function"]["name"] for t in TOOLS}
        assert names == {"send_notification", "update_database", "flag_content"}

    def test_all_tools_have_required_fields(self) -> None:
        for tool in TOOLS:
            assert tool["type"] == "function"
            func = tool["function"]
            assert "name" in func
            assert "description" in func
            assert "parameters" in func

    def test_send_notification_requires_to_subject_body(self) -> None:
        tool = next(t for t in TOOLS if t["function"]["name"] == "send_notification")
        required = tool["function"]["parameters"]["required"]
        assert set(required) == {"to", "subject", "body"}

    def test_update_database_requires_table_operation(self) -> None:
        tool = next(t for t in TOOLS if t["function"]["name"] == "update_database")
        required = tool["function"]["parameters"]["required"]
        assert "table" in required
        assert "operation" in required

    def test_flag_content_requires_content_id_status(self) -> None:
        tool = next(t for t in TOOLS if t["function"]["name"] == "flag_content")
        required = tool["function"]["parameters"]["required"]
        assert "content_id" in required
        assert "status" in required
