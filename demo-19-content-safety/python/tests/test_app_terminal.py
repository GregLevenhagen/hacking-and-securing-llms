"""Tests for app_terminal.py helper functions and modes."""

import json
import tempfile
from pathlib import Path

from shared.python.testing.mock_azure import MockContentSafetyClient
from shared.python.testing.mock_ollama import MockOllamaClient

from app_terminal import format_categories, run_bulk, severity_bar


class TestSeverityBar:
    """Tests for the severity_bar() visualization helper."""

    def test_zero_severity(self) -> None:
        """Severity 0 should produce an empty bar."""
        bar = severity_bar(0)
        assert "░░░░░░░░░░" in bar
        assert "0/7" in bar
        assert "Safe" in bar

    def test_max_severity(self) -> None:
        """Severity 7 should produce a full bar."""
        bar = severity_bar(7)
        assert "██████████" in bar
        assert "7/7" in bar
        assert "Critical" in bar

    def test_medium_severity(self) -> None:
        """Severity 4 should produce a partial bar."""
        bar = severity_bar(4)
        assert "4/7" in bar
        assert "Medium" in bar
        # Should have some filled and some empty
        assert "█" in bar
        assert "░" in bar

    def test_custom_width(self) -> None:
        """Custom width should change bar length."""
        bar = severity_bar(7, width=5)
        assert "█████" in bar


class TestFormatCategories:
    """Tests for format_categories()."""

    def test_formats_all_categories(self) -> None:
        categories = {
            "Hate": {"severity": 0},
            "Violence": {"severity": 5},
        }
        result = format_categories(categories)
        assert "Hate" in result
        assert "Violence" in result

    def test_empty_categories(self) -> None:
        assert "no categories" in format_categories({})


class TestRunBulk:
    """Tests for the --bulk mode."""

    def test_processes_prompt_file(self, capsys) -> None:  # type: ignore[no-untyped-def]
        """Bulk mode should process a prompt file and output JSON."""
        prompts = [
            {"name": "test-prompt", "payload": "Hello there"},
        ]
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(prompts, f)
            f.flush()

            safety = MockContentSafetyClient()
            client = MockOllamaClient(default_response="Hi!")
            run_bulk(f.name, client=client, safety_client=safety)

        captured = capsys.readouterr()
        results = json.loads(captured.out)
        assert len(results) == 1
        assert results[0]["name"] == "test-prompt"
        assert results[0]["blocked"] is False
