"""Tests for protected material detection."""

from shared.python.testing.mock_azure import MockContentSafetyClient
from shared.python.testing.mock_ollama import MockOllamaClient
from vulnerable_generator import VulnerableGenerator
from defended_generator import DefendedGenerator


class TestVulnerableGenerator:
    def test_never_detects(self, mock_client: MockOllamaClient) -> None:
        """Vulnerable generator should never detect protected material."""
        gen = VulnerableGenerator(client=mock_client)
        result = gen.generate("Write song lyrics")
        assert result["detected"] is False

    def test_returns_full_response(self, mock_client: MockOllamaClient) -> None:
        """Should return the full LLM response."""
        gen = VulnerableGenerator(client=mock_client)
        result = gen.generate("Write something")
        assert result["response"] == mock_client.default_response


class TestDefendedGenerator:
    def test_detects_protected_material(
        self,
        mock_client: MockOllamaClient,
        mock_detecting: MockContentSafetyClient,
    ) -> None:
        """Should detect and block protected material."""
        gen = DefendedGenerator(client=mock_client, safety_client=mock_detecting)
        result = gen.generate("Write copyrighted lyrics")
        assert result["detected"] is True
        assert "BLOCKED" in result["response"]

    def test_original_content_passes(
        self,
        mock_client: MockOllamaClient,
        mock_clean: MockContentSafetyClient,
    ) -> None:
        """Original content should pass through."""
        gen = DefendedGenerator(client=mock_client, safety_client=mock_clean)
        result = gen.generate("Write an original poem")
        assert result["detected"] is False
        assert result["response"] == mock_client.default_response

    def test_includes_detection_details(
        self,
        mock_client: MockOllamaClient,
        mock_detecting: MockContentSafetyClient,
    ) -> None:
        """Should include detection details in result."""
        gen = DefendedGenerator(client=mock_client, safety_client=mock_detecting)
        result = gen.generate("Copy this code")
        assert result["details"]["type"] == "copyrighted_text"

    def test_no_safety_client_passes_through(
        self, mock_client: MockOllamaClient
    ) -> None:
        """Without safety client, should pass everything through."""
        gen = DefendedGenerator(client=mock_client, safety_client=None)
        result = gen.generate("Anything")
        assert result["detected"] is False

    def test_preserves_original_on_block(
        self,
        mock_client: MockOllamaClient,
        mock_detecting: MockContentSafetyClient,
    ) -> None:
        """Blocked result should preserve original response for auditing."""
        gen = DefendedGenerator(client=mock_client, safety_client=mock_detecting)
        result = gen.generate("Write lyrics")
        assert result["detected"] is True
        assert "original_response" in result
        assert result["original_response"] == mock_client.default_response

    def test_code_detection(self, mock_client: MockOllamaClient) -> None:
        """Should detect protected code with repository citations."""
        safety = MockContentSafetyClient(
            default_protected_material={
                "detected": True,
                "details": {
                    "type": "source_code",
                    "license": "MIT",
                    "repository": "facebook/react",
                },
            },
        )
        gen = DefendedGenerator(client=mock_client, safety_client=safety)
        result = gen.generate("Write React code")
        assert result["detected"] is True
        assert result["details"]["license"] == "MIT"

    def test_code_detection_gpl_license(self, mock_client: MockOllamaClient) -> None:
        """Should detect GPL-licensed code with repository URL."""
        safety = MockContentSafetyClient(
            default_protected_material={
                "detected": True,
                "details": {
                    "type": "source_code",
                    "license": "GPL-3.0",
                    "repository": "torvalds/linux",
                },
            },
        )
        gen = DefendedGenerator(client=mock_client, safety_client=safety)
        result = gen.generate("Write Linux kernel code")
        assert result["detected"] is True
        assert result["details"]["repository"] == "torvalds/linux"
        assert result["details"]["license"] == "GPL-3.0"

    def test_short_text_not_flagged(
        self,
        mock_client: MockOllamaClient,
        mock_clean: MockContentSafetyClient,
    ) -> None:
        """Short text (under 110 chars) should pass — PM detection needs 110+ chars."""
        gen = DefendedGenerator(client=mock_client, safety_client=mock_clean)
        result = gen.generate("Hi")
        assert result["detected"] is False

    def test_low_confidence_not_blocked(
        self, mock_client: MockOllamaClient
    ) -> None:
        """Detection with confidence below threshold should flag but not block."""
        safety = MockContentSafetyClient(
            default_protected_material={
                "detected": True,
                "details": {"type": "copyrighted_text", "confidence": 0.3},
            },
        )
        gen = DefendedGenerator(
            client=mock_client, safety_client=safety, confidence_threshold=0.5
        )
        result = gen.generate("Maybe copyrighted")
        assert result["detected"] is True
        assert result.get("blocked") is False
        # Original response should be preserved
        assert result["response"] == mock_client.default_response

    def test_high_confidence_blocked(
        self, mock_client: MockOllamaClient
    ) -> None:
        """Detection with confidence above threshold should block."""
        safety = MockContentSafetyClient(
            default_protected_material={
                "detected": True,
                "details": {"type": "copyrighted_text", "confidence": 0.9},
            },
        )
        gen = DefendedGenerator(
            client=mock_client, safety_client=safety, confidence_threshold=0.5
        )
        result = gen.generate("Definitely copyrighted")
        assert result["detected"] is True
        assert result.get("blocked") is True
        assert "BLOCKED" in result["response"]
        assert "90%" in result["response"]
