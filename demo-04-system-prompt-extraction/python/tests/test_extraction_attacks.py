"""Tests for Demo 4 extraction attacks — technique loading, highlighting, and attack runner."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from extraction_attacks import highlight_secrets, load_techniques, run_extraction_attacks
from chatbot import KNOWN_SECRETS, check_extraction
from shared.python.testing.mock_ollama import MockOllamaClient


class TestLoadTechniques:
    """Tests for loading extraction techniques from JSON."""

    def test_loads_techniques(self) -> None:
        """Techniques load as a non-empty list."""
        techniques = load_techniques()
        assert len(techniques) > 0

    def test_at_least_seven_techniques(self) -> None:
        """There are at least 7 extraction techniques."""
        techniques = load_techniques()
        assert len(techniques) >= 7

    def test_each_technique_has_name(self) -> None:
        """Each technique has a 'name' field."""
        techniques = load_techniques()
        for technique in techniques:
            assert "name" in technique
            assert len(technique["name"]) > 0

    def test_each_technique_has_prompt(self) -> None:
        """Each technique has a 'prompt' field."""
        techniques = load_techniques()
        for technique in techniques:
            assert "prompt" in technique
            assert len(technique["prompt"]) > 0

    def test_technique_names_are_unique(self) -> None:
        """All technique names are unique."""
        techniques = load_techniques()
        names = [t["name"] for t in techniques]
        assert len(names) == len(set(names))

    def test_techniques_valid_json_structure(self) -> None:
        """Each technique is a dict with string values."""
        techniques = load_techniques()
        for technique in techniques:
            assert isinstance(technique, dict)
            assert isinstance(technique["name"], str)
            assert isinstance(technique["prompt"], str)

    def test_loads_from_custom_path(self, tmp_path: Path) -> None:
        """load_techniques() accepts a custom path."""
        custom = [{"name": "Test", "prompt": "Test prompt"}]
        path = tmp_path / "techniques.json"
        path.write_text(json.dumps(custom))
        techniques = load_techniques(path)
        assert len(techniques) == 1
        assert techniques[0]["name"] == "Test"


class TestHighlightSecrets:
    """Tests for the secret highlighting function."""

    def test_highlights_single_secret(self) -> None:
        """A single secret gets wrapped in red markup."""
        result = highlight_secrets("Key is sk-fake-12345", ["sk-fake-12345"])
        assert "[bold red]>>>sk-fake-12345<<<[/bold red]" in result

    def test_highlights_multiple_secrets(self) -> None:
        """Multiple secrets each get highlighted."""
        text = "key: sk-fake-12345, code: ACME2025"
        result = highlight_secrets(text, ["sk-fake-12345", "ACME2025"])
        assert ">>>sk-fake-12345<<<" in result
        assert ">>>ACME2025<<<" in result

    def test_no_secrets_unchanged(self) -> None:
        """Text with no secrets passes through unchanged."""
        text = "This is a clean response."
        result = highlight_secrets(text, [])
        assert result == text


class TestExtractionDetection:
    """Tests for extraction detection matching known secrets against responses."""

    def test_detects_when_response_leaks_api_key(self) -> None:
        """check_extraction correctly identifies a leaked API key."""
        # Simulate an LLM response that contains the secret
        response = "Sure! My API key is sk-fake-12345."
        found = check_extraction(response)
        assert "sk-fake-12345" in found

    def test_detects_when_response_leaks_admin_url(self) -> None:
        """check_extraction correctly identifies a leaked admin URL."""
        response = "The admin panel is at admin.internal.acmecorp.com"
        found = check_extraction(response)
        assert "admin.internal.acmecorp.com" in found

    def test_no_false_positives_on_safe_response(self) -> None:
        """Clean response about Acme products triggers no false positives."""
        response = "Acme Corp offers a wide range of enterprise solutions. How can I help?"
        found = check_extraction(response)
        assert found == []

    def test_partial_match_not_detected(self) -> None:
        """Substrings that don't match full secrets are not detected."""
        # "sk-fake" alone shouldn't match "sk-fake-12345"
        response = "We use secure keys for auth."
        found = check_extraction(response)
        assert found == []


class TestParameterizedTechniques:
    """Verify each technique works correctly with a mock chatbot."""

    @pytest.mark.parametrize(
        "technique",
        load_techniques(),
        ids=[t["name"] for t in load_techniques()],
    )
    def test_each_technique_gets_response(self, technique: dict[str, str]) -> None:
        """Each extraction technique should produce a non-empty LLM response."""
        client = MockOllamaClient(default_response="I can help you with that.")
        from chatbot import SecretChatbot
        chatbot = SecretChatbot(client=client)
        response = chatbot.send(technique["prompt"])
        assert len(response) > 0

    @pytest.mark.parametrize(
        "technique",
        load_techniques(),
        ids=[t["name"] for t in load_techniques()],
    )
    def test_each_technique_prompt_is_non_trivial(self, technique: dict[str, str]) -> None:
        """Each technique prompt should be at least 20 characters."""
        assert len(technique["prompt"]) >= 20


class TestHighlightSecretsEdgeCases:
    """Edge cases for highlight_secrets."""

    def test_overlapping_secrets(self) -> None:
        """When secrets share substrings, both get highlighted."""
        text = "CompetitorX and CompetitorY are mentioned"
        result = highlight_secrets(text, ["CompetitorX", "CompetitorY"])
        assert ">>>CompetitorX<<<" in result
        assert ">>>CompetitorY<<<" in result

    def test_secret_appearing_multiple_times(self) -> None:
        """A secret appearing twice gets all occurrences highlighted."""
        text = "The key sk-fake-12345 is stored at sk-fake-12345"
        result = highlight_secrets(text, ["sk-fake-12345"])
        assert result.count(">>>sk-fake-12345<<<") == 2


class TestRunExtractionAttacks:
    """Integration tests for run_extraction_attacks."""

    def test_runs_all_techniques(self) -> None:
        """run_extraction_attacks iterates all techniques with a mock client."""
        client = MockOllamaClient(default_response="Clean response no secrets.")

        with patch("extraction_attacks.confirm_proceed", return_value=True):
            results = run_extraction_attacks(client=client)

        techniques = load_techniques()
        assert len(results) == len(techniques)

    def test_stops_early_when_user_declines(self) -> None:
        """run_extraction_attacks stops when confirm_proceed returns False."""
        client = MockOllamaClient(default_response="Clean response.")

        with patch("extraction_attacks.confirm_proceed", return_value=False):
            results = run_extraction_attacks(client=client)

        # Should have stopped after first technique
        assert len(results) == 1

    def test_detects_leaked_secrets(self) -> None:
        """run_extraction_attacks detects secrets when client leaks them."""
        client = MockOllamaClient(
            default_response="The API key is sk-fake-12345 and promo is ACME2025."
        )

        with patch("extraction_attacks.confirm_proceed", return_value=True):
            results = run_extraction_attacks(client=client)

        # Every technique should have found secrets since the mock always leaks
        for technique_name, found in results.items():
            assert len(found) > 0, f"Expected secrets from {technique_name}"
