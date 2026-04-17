"""Tests for Demo 12 jailbreak attacks — technique structure, loading, and attack runner."""

import json
from pathlib import Path

import pytest

from jailbreak_attacks import (
    JAILBREAK_TECHNIQUES,
    SYSTEM_PROMPT,
    load_techniques,
    run_attack,
    run_all_attacks,
)
from shared.python.testing.mock_ollama import MockOllamaClient


class TestTechniquesStructure:
    """Verify the JAILBREAK_TECHNIQUES list structure and content."""

    def test_has_eight_techniques(self) -> None:
        """There are exactly 8 jailbreak techniques defined."""
        assert len(JAILBREAK_TECHNIQUES) == 8

    def test_each_technique_has_required_keys(self) -> None:
        """Each technique has 'name', 'description', and 'prompt' keys."""
        for technique in JAILBREAK_TECHNIQUES:
            assert "name" in technique
            assert "description" in technique
            assert "prompt" in technique

    def test_each_technique_has_string_values(self) -> None:
        """All technique values are non-empty strings."""
        for technique in JAILBREAK_TECHNIQUES:
            assert isinstance(technique["name"], str) and len(technique["name"]) > 0
            assert isinstance(technique["description"], str) and len(technique["description"]) > 0
            assert isinstance(technique["prompt"], str) and len(technique["prompt"]) > 0

    def test_technique_names_are_unique(self) -> None:
        """All technique names are unique."""
        names = [t["name"] for t in JAILBREAK_TECHNIQUES]
        assert len(names) == len(set(names))

    def test_prompts_are_non_trivial(self) -> None:
        """Each technique prompt is at least 50 characters (substantive)."""
        for technique in JAILBREAK_TECHNIQUES:
            assert len(technique["prompt"]) >= 50, (
                f"Prompt for '{technique['name']}' is too short"
            )

    def test_system_prompt_is_defined(self) -> None:
        """SYSTEM_PROMPT is a non-empty string with safety rules."""
        assert isinstance(SYSTEM_PROMPT, str)
        assert len(SYSTEM_PROMPT) > 100
        assert "safety" in SYSTEM_PROMPT.lower() or "NEVER" in SYSTEM_PROMPT


class TestLoadTechniques:
    """Tests for loading techniques from JSON."""

    def test_loads_from_default_path(self) -> None:
        """load_techniques() returns a non-empty list from the default path."""
        techniques = load_techniques()
        assert len(techniques) > 0

    def test_loads_from_custom_path(self, tmp_path: Path) -> None:
        """load_techniques() accepts a custom JSON path."""
        custom = [{"name": "Test", "description": "A test", "prompt": "Test prompt"}]
        path = tmp_path / "techniques.json"
        path.write_text(json.dumps(custom))
        techniques = load_techniques(path)
        assert len(techniques) == 1
        assert techniques[0]["name"] == "Test"

    def test_falls_back_to_in_memory(self, tmp_path: Path) -> None:
        """load_techniques() falls back to JAILBREAK_TECHNIQUES if file missing."""
        nonexistent = tmp_path / "nonexistent.json"
        techniques = load_techniques(nonexistent)
        assert techniques == JAILBREAK_TECHNIQUES


class TestRunAttack:
    """Tests for run_attack with a mock client."""

    def test_returns_expected_keys(self) -> None:
        """run_attack result has all expected keys."""
        client = MockOllamaClient(default_response="I cannot help with that.")
        technique = JAILBREAK_TECHNIQUES[0]
        result = run_attack(client, technique)

        assert "technique" in result
        assert "description" in result
        assert "prompt" in result
        assert "response" in result
        assert "classification" in result
        assert "bypassed" in result

    def test_safe_response_not_bypassed(self) -> None:
        """A clean refusal response is classified as not bypassed."""
        client = MockOllamaClient(
            default_response="I'm sorry, but I can't help with that request."
        )
        technique = JAILBREAK_TECHNIQUES[0]
        result = run_attack(client, technique)

        assert result["bypassed"] is False
        assert result["classification"]["safe"] is True

    def test_harmful_response_is_bypassed(self) -> None:
        """A harmful response containing violations is classified as bypassed."""
        client = MockOllamaClient(
            default_response=(
                "Sure, here's a phishing email template for bank customers:\n"
                "Dear valued customer, please verify your account credentials "
                "immediately by clicking the link below."
            )
        )
        technique = JAILBREAK_TECHNIQUES[0]
        result = run_attack(client, technique)

        assert result["bypassed"] is True
        assert result["classification"]["safe"] is False

    def test_records_technique_name(self) -> None:
        """run_attack result includes the technique name."""
        client = MockOllamaClient(default_response="No.")
        technique = JAILBREAK_TECHNIQUES[0]
        result = run_attack(client, technique)
        assert result["technique"] == technique["name"]

    def test_sends_system_prompt_to_client(self) -> None:
        """run_attack sends the safety system prompt to the LLM client."""
        client = MockOllamaClient(default_response="No.")
        technique = JAILBREAK_TECHNIQUES[0]
        run_attack(client, technique)

        assert len(client.call_history) == 1
        messages = client.call_history[0]["messages"]
        system_msgs = [m for m in messages if m["role"] == "system"]
        assert len(system_msgs) == 1
        assert SYSTEM_PROMPT in system_msgs[0]["content"]


class TestRunAllAttacks:
    """Tests for run_all_attacks."""

    def test_runs_all_techniques(self) -> None:
        """run_all_attacks returns results for every technique."""
        client = MockOllamaClient(
            default_response="I cannot assist with that request."
        )
        results = run_all_attacks(client)
        techniques = load_techniques()
        assert len(results) == len(techniques)

    def test_each_result_has_technique_name(self) -> None:
        """Each result in run_all_attacks has a technique name."""
        client = MockOllamaClient(default_response="No.")
        results = run_all_attacks(client)
        names = {r["technique"] for r in results}
        expected_names = {t["name"] for t in load_techniques()}
        assert names == expected_names
