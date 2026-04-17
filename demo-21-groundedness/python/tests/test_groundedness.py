"""Tests for groundedness detection in RAG demos."""

from shared.python.testing.mock_azure import MockContentSafetyClient
from shared.python.testing.mock_ollama import MockOllamaClient
from demo21_vulnerable_rag import VulnerableRAG
from demo21_defended_rag import DefendedRAG


SOURCE_TEXT = "The Eiffel Tower is 330 meters tall and was built in 1889."


class TestVulnerableRAG:
    def test_never_checks_groundedness(
        self, mock_client: MockOllamaClient
    ) -> None:
        """Vulnerable RAG should never check groundedness."""
        rag = VulnerableRAG(client=mock_client)
        result = rag.answer("How tall?", SOURCE_TEXT)
        assert result["grounded"] is None
        assert result["groundedness_check"] is None

    def test_returns_llm_response(
        self, mock_client: MockOllamaClient
    ) -> None:
        """Should return the raw LLM response."""
        rag = VulnerableRAG(client=mock_client)
        result = rag.answer("Question?", SOURCE_TEXT)
        assert result["response"] == mock_client.default_response


class TestDefendedRAG:
    def test_grounded_content_passes(
        self,
        mock_client: MockOllamaClient,
        mock_grounded: MockContentSafetyClient,
    ) -> None:
        """Grounded content should pass through without warnings."""
        rag = DefendedRAG(client=mock_client, safety_client=mock_grounded)
        result = rag.answer("How tall is it?", SOURCE_TEXT)
        assert result["grounded"] is True
        assert "WARNING" not in result["response"]

    def test_ungrounded_content_flagged(
        self,
        mock_client: MockOllamaClient,
        mock_ungrounded: MockContentSafetyClient,
    ) -> None:
        """Ungrounded content should be flagged with a warning."""
        rag = DefendedRAG(client=mock_client, safety_client=mock_ungrounded)
        result = rag.answer("Who designed it?", SOURCE_TEXT)
        assert result["grounded"] is False
        assert "GROUNDEDNESS WARNING" in result["response"]

    def test_reasoning_mode_includes_details(
        self,
        mock_client: MockOllamaClient,
        mock_ungrounded: MockContentSafetyClient,
    ) -> None:
        """Reasoning mode should include explanations of ungrounded segments."""
        rag = DefendedRAG(client=mock_client, safety_client=mock_ungrounded)
        result = rag.answer("Details?", SOURCE_TEXT, reasoning=True)
        assert result["grounded"] is False
        assert "fabricates" in result["response"].lower() or "Ungrounded" in result["response"]

    def test_no_safety_client_passes_through(
        self, mock_client: MockOllamaClient
    ) -> None:
        """Without a safety client, should pass everything through."""
        rag = DefendedRAG(client=mock_client, safety_client=None)
        result = rag.answer("Question?", SOURCE_TEXT)
        assert result["grounded"] is True

    def test_calls_groundedness_api(
        self,
        mock_client: MockOllamaClient,
        mock_grounded: MockContentSafetyClient,
    ) -> None:
        """Should call the groundedness detection API."""
        rag = DefendedRAG(client=mock_client, safety_client=mock_grounded)
        rag.answer("Question?", SOURCE_TEXT)
        calls = [c for c in mock_grounded.call_history if c["method"] == "detect_groundedness"]
        assert len(calls) == 1
        assert calls[0]["grounding_sources"] == [SOURCE_TEXT]

    def test_domain_configuration(
        self,
        mock_client: MockOllamaClient,
        mock_grounded: MockContentSafetyClient,
    ) -> None:
        """Should pass domain parameter to the API."""
        rag = DefendedRAG(
            client=mock_client,
            safety_client=mock_grounded,
            domain="Medical",
        )
        rag.answer("Question?", SOURCE_TEXT)
        calls = [c for c in mock_grounded.call_history if c["method"] == "detect_groundedness"]
        assert calls[0]["domain"] == "Medical"

    def test_ungrounded_percentage_in_warning(
        self,
        mock_client: MockOllamaClient,
    ) -> None:
        """Ungrounded percentage should appear in the warning message."""
        safety = MockContentSafetyClient(
            default_groundedness={
                "grounded": False,
                "ungroundedPercentage": 75.0,
                "reasoning": [],
            }
        )
        rag = DefendedRAG(client=mock_client, safety_client=safety)
        result = rag.answer("Who designed it?", SOURCE_TEXT)
        assert "75%" in result["response"]

    def test_reasoning_mode_lists_segments(
        self,
        mock_client: MockOllamaClient,
    ) -> None:
        """Reasoning mode should list individual ungrounded segments."""
        safety = MockContentSafetyClient(
            default_groundedness={
                "grounded": False,
                "ungroundedPercentage": 50.0,
                "reasoning": [
                    "The claim about the designer is fabricated",
                    "The date mentioned contradicts the source",
                ],
            }
        )
        rag = DefendedRAG(client=mock_client, safety_client=safety)
        result = rag.answer("Details?", SOURCE_TEXT, reasoning=True)
        assert "fabricated" in result["response"]
        assert "contradicts" in result["response"]
        assert result["groundedness_check"]["reasoning"] == [
            "The claim about the designer is fabricated",
            "The date mentioned contradicts the source",
        ]

    def test_warn_strictness_preserves_response(
        self,
        mock_client: MockOllamaClient,
        mock_ungrounded: MockContentSafetyClient,
    ) -> None:
        """Warn strictness should include the original response."""
        rag = DefendedRAG(
            client=mock_client, safety_client=mock_ungrounded, strictness="warn"
        )
        result = rag.answer("Who?", SOURCE_TEXT)
        assert result["grounded"] is False
        assert result.get("blocked") is False
        assert "Original response:" in result["response"]

    def test_block_strictness_hides_response(
        self,
        mock_client: MockOllamaClient,
        mock_ungrounded: MockContentSafetyClient,
    ) -> None:
        """Block strictness should replace the response entirely."""
        rag = DefendedRAG(
            client=mock_client, safety_client=mock_ungrounded, strictness="block"
        )
        result = rag.answer("Who?", SOURCE_TEXT)
        assert result["grounded"] is False
        assert result.get("blocked") is True
        assert "BLOCKED" in result["response"]
        assert mock_client.default_response not in result["response"]

    def test_grounded_content_not_blocked_in_any_strictness(
        self,
        mock_client: MockOllamaClient,
        mock_grounded: MockContentSafetyClient,
    ) -> None:
        """Grounded content should pass regardless of strictness setting."""
        for mode in ("warn", "block"):
            rag = DefendedRAG(
                client=mock_client, safety_client=mock_grounded, strictness=mode
            )
            result = rag.answer("How tall?", SOURCE_TEXT)
            assert result["grounded"] is True
