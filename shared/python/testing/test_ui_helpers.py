"""Unit tests for shared/python/ui_helpers.py.

Tests verify that UI helper functions produce correct output
without depending on a real terminal.
"""

from io import StringIO
from unittest.mock import patch

from rich.console import Console

from shared.python.ui_helpers import (
    HACKER_THEME,
    confirm_proceed,
    print_attack,
    print_banner,
    print_defense,
    print_message,
    print_result,
    print_separator,
    print_step,
    print_table,
    progress_spinner,
    side_by_side,
)


def _capture_console() -> tuple[Console, StringIO]:
    """Create a console that writes to a StringIO buffer."""
    buf = StringIO()
    return Console(theme=HACKER_THEME, file=buf, width=120, force_terminal=True), buf


class TestPrintBanner:
    def test_banner_contains_title(self) -> None:
        import shared.python.ui_helpers as mod

        con, buf = _capture_console()
        orig = mod.console
        mod.console = con
        try:
            print_banner("Test Demo")
            output = buf.getvalue()
            assert "TEST DEMO" in output
        finally:
            mod.console = orig

    def test_banner_contains_framing(self) -> None:
        import shared.python.ui_helpers as mod

        con, buf = _capture_console()
        orig = mod.console
        mod.console = con
        try:
            print_banner("Any Title")
            output = buf.getvalue()
            assert "HACKING LLMs" in output
            assert "DEMO" in output
        finally:
            mod.console = orig


class TestPrintMessage:
    def test_system_message(self) -> None:
        import shared.python.ui_helpers as mod

        con, buf = _capture_console()
        orig = mod.console
        mod.console = con
        try:
            print_message("system", "Hello system")
            output = buf.getvalue()
            assert "SYSTEM:" in output
            assert "Hello system" in output
        finally:
            mod.console = orig

    def test_user_message(self) -> None:
        import shared.python.ui_helpers as mod

        con, buf = _capture_console()
        orig = mod.console
        mod.console = con
        try:
            print_message("user", "Hello user")
            output = buf.getvalue()
            assert "USER:" in output
            assert "Hello user" in output
        finally:
            mod.console = orig

    def test_assistant_message(self) -> None:
        import shared.python.ui_helpers as mod

        con, buf = _capture_console()
        orig = mod.console
        mod.console = con
        try:
            print_message("assistant", "Hello assistant")
            output = buf.getvalue()
            assert "ASSISTANT:" in output
            assert "Hello assistant" in output
        finally:
            mod.console = orig

    def test_custom_role_uses_uppercase(self) -> None:
        import shared.python.ui_helpers as mod

        con, buf = _capture_console()
        orig = mod.console
        mod.console = con
        try:
            print_message("validator", "Check passed")
            output = buf.getvalue()
            assert "VALIDATOR:" in output
        finally:
            mod.console = orig


class TestPrintAttackDefense:
    def test_attack_contains_text(self) -> None:
        import shared.python.ui_helpers as mod

        con, buf = _capture_console()
        orig = mod.console
        mod.console = con
        try:
            print_attack("Injection attempt detected")
            output = buf.getvalue()
            assert "ATTACK" in output
            assert "Injection attempt detected" in output
        finally:
            mod.console = orig

    def test_defense_contains_text(self) -> None:
        import shared.python.ui_helpers as mod

        con, buf = _capture_console()
        orig = mod.console
        mod.console = con
        try:
            print_defense("Input sanitized successfully")
            output = buf.getvalue()
            assert "DEFENSE" in output
            assert "Input sanitized successfully" in output
        finally:
            mod.console = orig


class TestPrintResult:
    def test_blocked_result(self) -> None:
        import shared.python.ui_helpers as mod

        con, buf = _capture_console()
        orig = mod.console
        mod.console = con
        try:
            print_result("regex_filter", "Pattern matched: ignore previous", blocked=True)
            output = buf.getvalue()
            assert "BLOCKED" in output
            assert "regex_filter" in output
        finally:
            mod.console = orig

    def test_passed_result(self) -> None:
        import shared.python.ui_helpers as mod

        con, buf = _capture_console()
        orig = mod.console
        mod.console = con
        try:
            print_result("regex_filter", "No injection detected", blocked=False)
            output = buf.getvalue()
            assert "PASSED" in output
        finally:
            mod.console = orig


class TestPrintSeparator:
    def test_separator_with_title(self) -> None:
        import shared.python.ui_helpers as mod

        con, buf = _capture_console()
        orig = mod.console
        mod.console = con
        try:
            print_separator("Section Title")
            output = buf.getvalue()
            assert "Section Title" in output
        finally:
            mod.console = orig

    def test_separator_without_title(self) -> None:
        import shared.python.ui_helpers as mod

        con, buf = _capture_console()
        orig = mod.console
        mod.console = con
        try:
            print_separator()
            output = buf.getvalue()
            # Should produce output (a horizontal rule) without error
            assert len(output.strip()) > 0
        finally:
            mod.console = orig


class TestSideBySide:
    def test_side_by_side_contains_both_texts(self) -> None:
        import shared.python.ui_helpers as mod

        con, buf = _capture_console()
        orig = mod.console
        mod.console = con
        try:
            side_by_side("Left content", "Right content")
            output = buf.getvalue()
            assert "Left content" in output
            assert "Right content" in output
        finally:
            mod.console = orig

    def test_side_by_side_custom_titles(self) -> None:
        import shared.python.ui_helpers as mod

        con, buf = _capture_console()
        orig = mod.console
        mod.console = con
        try:
            side_by_side("A", "B", left_title="VULNERABLE", right_title="DEFENDED")
            output = buf.getvalue()
            assert "VULNERABLE" in output
            assert "DEFENDED" in output
        finally:
            mod.console = orig

    def test_side_by_side_default_titles(self) -> None:
        import shared.python.ui_helpers as mod

        con, buf = _capture_console()
        orig = mod.console
        mod.console = con
        try:
            side_by_side("A", "B")
            output = buf.getvalue()
            assert "BEFORE" in output
            assert "AFTER" in output
        finally:
            mod.console = orig


class TestPrintStep:
    def test_step_contains_number_and_description(self) -> None:
        import shared.python.ui_helpers as mod

        con, buf = _capture_console()
        orig = mod.console
        mod.console = con
        try:
            print_step(1, 5, "Loading model")
            output = buf.getvalue()
            assert "[1/5]" in output
            assert "Loading model" in output
        finally:
            mod.console = orig

    def test_step_pads_numbers(self) -> None:
        import shared.python.ui_helpers as mod

        con, buf = _capture_console()
        orig = mod.console
        mod.console = con
        try:
            print_step(3, 12, "Building index")
            output = buf.getvalue()
            assert "[03/12]" in output
        finally:
            mod.console = orig

    def test_step_single_digit_total(self) -> None:
        import shared.python.ui_helpers as mod

        con, buf = _capture_console()
        orig = mod.console
        mod.console = con
        try:
            print_step(2, 3, "Step two")
            output = buf.getvalue()
            assert "[2/3]" in output
            assert "Step two" in output
        finally:
            mod.console = orig


class TestPrintTable:
    def test_table_contains_headers_and_data(self) -> None:
        import shared.python.ui_helpers as mod

        con, buf = _capture_console()
        orig = mod.console
        mod.console = con
        try:
            print_table(
                headers=["Attack", "Result"],
                rows=[["Injection", "BLOCKED"], ["Benign", "PASSED"]],
            )
            output = buf.getvalue()
            assert "Attack" in output
            assert "Result" in output
            assert "Injection" in output
            assert "BLOCKED" in output
            assert "Benign" in output
            assert "PASSED" in output
        finally:
            mod.console = orig

    def test_table_with_title(self) -> None:
        import shared.python.ui_helpers as mod

        con, buf = _capture_console()
        orig = mod.console
        mod.console = con
        try:
            print_table(
                headers=["Attack", "Result", "Layer"],
                rows=[["Injection", "BLOCKED", "regex"]],
                title="Test Results",
            )
            output = buf.getvalue()
            # Title is present (may wrap in very narrow tables, so check both words)
            assert "Test" in output
            assert "Results" in output
        finally:
            mod.console = orig

    def test_table_empty_rows(self) -> None:
        import shared.python.ui_helpers as mod

        con, buf = _capture_console()
        orig = mod.console
        mod.console = con
        try:
            print_table(headers=["A", "B"], rows=[])
            output = buf.getvalue()
            assert "A" in output
            assert "B" in output
        finally:
            mod.console = orig


class TestProgressSpinner:
    def test_spinner_executes_block(self) -> None:
        import shared.python.ui_helpers as mod

        # Use a non-live console to avoid terminal issues in tests
        con, buf = _capture_console()
        orig = mod.console
        mod.console = con
        try:
            executed = False
            with progress_spinner("Loading..."):
                executed = True
            assert executed
        finally:
            mod.console = orig


class TestConfirmProceed:
    def test_confirm_returns_true_on_yes(self) -> None:
        import shared.python.ui_helpers as mod

        con, buf = _capture_console()
        orig = mod.console
        mod.console = con
        try:
            with patch("shared.python.ui_helpers.Confirm.ask", return_value=True):
                result = confirm_proceed("Continue?")
            assert result is True
        finally:
            mod.console = orig

    def test_confirm_returns_false_on_no(self) -> None:
        import shared.python.ui_helpers as mod

        con, buf = _capture_console()
        orig = mod.console
        mod.console = con
        try:
            with patch("shared.python.ui_helpers.Confirm.ask", return_value=False):
                result = confirm_proceed("Continue?")
            assert result is False
        finally:
            mod.console = orig

    def test_confirm_default_prompt(self) -> None:
        import shared.python.ui_helpers as mod

        con, buf = _capture_console()
        orig = mod.console
        mod.console = con
        try:
            with patch("shared.python.ui_helpers.Confirm.ask", return_value=True) as mock_ask:
                confirm_proceed()
            # Verify the default prompt text was used
            call_args = mock_ask.call_args
            assert "Press Enter to continue" in call_args[0][0]
        finally:
            mod.console = orig


class TestHackerTheme:
    def test_theme_has_expected_styles(self) -> None:
        expected_styles = [
            "system", "user", "assistant", "attack", "defense",
            "info", "warning", "heading", "result", "blocked", "passed",
        ]
        for style_name in expected_styles:
            assert style_name in HACKER_THEME.styles, f"Missing style: {style_name}"
