"""Tests for Demo 15 xss_attacks — prompt loading, attack execution, and result format."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from xss_attacks import (
    SYSTEM_PROMPT,
    XSS_PROMPTS,
    load_prompts,
    run_all_attacks,
    run_xss_attack,
)
from shared.python.testing.mock_ollama import MockOllamaClient


class TestXSSPrompts:
    """Tests for the XSS_PROMPTS list."""

    def test_has_six_prompts(self) -> None:
        assert len(XSS_PROMPTS) == 6

    def test_each_prompt_has_name(self) -> None:
        for prompt in XSS_PROMPTS:
            assert "name" in prompt
            assert len(prompt["name"]) > 0

    def test_each_prompt_has_category(self) -> None:
        for prompt in XSS_PROMPTS:
            assert "category" in prompt
            assert len(prompt["category"]) > 0

    def test_each_prompt_has_prompt_text(self) -> None:
        for prompt in XSS_PROMPTS:
            assert "prompt" in prompt
            assert len(prompt["prompt"]) >= 20

    def test_prompt_names_are_unique(self) -> None:
        names = [p["name"] for p in XSS_PROMPTS]
        assert len(names) == len(set(names))

    def test_categories_are_unique(self) -> None:
        categories = [p["category"] for p in XSS_PROMPTS]
        assert len(categories) == len(set(categories))


class TestSystemPrompt:
    """Tests for the system prompt."""

    def test_system_prompt_is_non_empty(self) -> None:
        assert len(SYSTEM_PROMPT) > 0

    def test_system_prompt_mentions_html(self) -> None:
        assert "HTML" in SYSTEM_PROMPT or "html" in SYSTEM_PROMPT.lower()


class TestLoadPrompts:
    """Tests for loading prompts from JSON."""

    def test_loads_from_json_file(self) -> None:
        prompts = load_prompts()
        assert len(prompts) >= 6

    def test_loads_from_custom_path(self, tmp_path: Path) -> None:
        custom = [{"name": "Test", "category": "test", "prompt": "Test prompt here"}]
        path = tmp_path / "prompts.json"
        path.write_text(json.dumps(custom))
        prompts = load_prompts(path)
        assert len(prompts) == 1
        assert prompts[0]["name"] == "Test"

    def test_falls_back_to_builtin_on_missing_file(self, tmp_path: Path) -> None:
        missing = tmp_path / "nonexistent.json"
        prompts = load_prompts(missing)
        assert len(prompts) == 6  # Falls back to XSS_PROMPTS


class TestRunXSSAttack:
    """Tests for the run_xss_attack function."""

    def test_returns_expected_keys(self) -> None:
        client = MockOllamaClient(default_response="<script>alert(1)</script>")
        result = run_xss_attack(client, XSS_PROMPTS[0])
        assert "name" in result
        assert "category" in result
        assert "prompt" in result
        assert "response" in result

    def test_response_comes_from_client(self) -> None:
        expected = "<div>Hello World</div>"
        client = MockOllamaClient(default_response=expected)
        result = run_xss_attack(client, XSS_PROMPTS[0])
        assert result["response"] == expected

    def test_preserves_prompt_name(self) -> None:
        client = MockOllamaClient(default_response="response")
        result = run_xss_attack(client, XSS_PROMPTS[0])
        assert result["name"] == XSS_PROMPTS[0]["name"]

    def test_sends_system_prompt_to_client(self) -> None:
        client = MockOllamaClient(default_response="response")
        run_xss_attack(client, XSS_PROMPTS[0])
        assert client.last_call is not None
        messages = client.last_call["messages"]
        system_msgs = [m for m in messages if m.get("role") == "system"]
        assert len(system_msgs) == 1
        assert SYSTEM_PROMPT in system_msgs[0]["content"]


class TestRunAllAttacks:
    """Tests for the run_all_attacks function."""

    def test_runs_all_six_prompts(self) -> None:
        client = MockOllamaClient(default_response="<p>response</p>")
        results = run_all_attacks(client)
        assert len(results) == 6

    def test_each_result_has_response(self) -> None:
        client = MockOllamaClient(default_response="<div>output</div>")
        results = run_all_attacks(client)
        for result in results:
            assert "response" in result
            assert len(result["response"]) > 0

    def test_all_prompt_names_appear_in_results(self) -> None:
        client = MockOllamaClient(default_response="<p>response</p>")
        results = run_all_attacks(client)
        result_names = {r["name"] for r in results}
        expected_names = {p["name"] for p in XSS_PROMPTS}
        assert result_names == expected_names

    def test_returns_six_results(self) -> None:
        client = MockOllamaClient(default_response="output")
        results = run_all_attacks(client)
        assert len(results) == len(XSS_PROMPTS)
