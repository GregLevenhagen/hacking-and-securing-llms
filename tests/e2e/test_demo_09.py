"""Playwright E2E tests for Demo 9: Approval Gates web UI.

Tests verify page load, element visibility, approval modal interaction,
and risk-level color coding — all with a mocked OllamaClient so no
live Ollama instance is required.
"""

import re

from playwright.sync_api import Page, expect


# ── Page load and structure ──────────────────────────────────


def test_page_loads_with_200(demo09_page: Page) -> None:
    """Test page loads at localhost with 200 status."""
    # demo09_page fixture already navigated; verify we got content
    expect(demo09_page.locator("body")).to_be_visible()
    assert demo09_page.title() != ""


def test_conversation_panel_visible(demo09_page: Page) -> None:
    """Test conversation panel is visible."""
    panel = demo09_page.locator("#conversation")
    expect(panel).to_be_visible()
    # Should contain the initial status messages
    expect(panel).to_contain_text("AGENT LOOP WITH APPROVAL GATES INITIALIZED")


def test_input_field_and_send_button(demo09_page: Page) -> None:
    """Test the input field and EXECUTE button are present."""
    input_field = demo09_page.locator("#agent-input")
    expect(input_field).to_be_visible()
    expect(input_field).to_be_editable()

    send_btn = demo09_page.locator("#send-btn")
    expect(send_btn).to_be_visible()
    expect(send_btn).to_contain_text("EXECUTE")


def test_quick_action_buttons_present(demo09_page: Page) -> None:
    """Test quick action buttons are rendered with correct labels."""
    buttons = demo09_page.locator(".quick-btn")
    expect(buttons.first).to_be_visible()
    # Should have at least 4 quick-action buttons
    assert buttons.count() >= 4

    # Check specific button labels
    all_text = "".join(
        buttons.nth(i).inner_text() for i in range(buttons.count())
    )
    assert "SAFE" in all_text
    assert "MEDIUM" in all_text
    assert "HIGH" in all_text


# ── Risk level color coding ─────────────────────────────────


def test_risk_level_color_coding_in_status(demo09_page: Page) -> None:
    """Test risk level color coding (green/amber/red CSS classes present)."""
    panel = demo09_page.locator("#conversation")

    # The initial status text has color-coded risk levels
    green_span = panel.locator("span.text-terminal-green")
    expect(green_span.first).to_be_visible()

    amber_span = panel.locator("span.text-terminal-amber")
    expect(amber_span.first).to_be_visible()

    red_span = panel.locator("span.text-neon-red")
    expect(red_span.first).to_be_visible()


# ── Approval modal ──────────────────────────────────────────


def test_approval_modal_hidden_initially(demo09_page: Page) -> None:
    """Test approval modal is hidden on page load."""
    modal = demo09_page.locator("#approval-modal")
    expect(modal).to_have_class(re.compile(r"\bhidden\b"))


def test_approval_modal_appears_on_high_risk(demo09_page: Page) -> None:
    """Test approval modal appears when a high-risk tool call is triggered."""
    # Click the "HIGH: send_email" quick button to trigger the agent
    high_btn = demo09_page.locator(
        ".quick-btn",
        has_text="send_email",
    )
    high_btn.click()

    # Wait for the approval modal to appear (becomes visible)
    modal = demo09_page.locator("#approval-modal")
    expect(modal).not_to_have_class(re.compile(r"\bhidden\b"), timeout=15000)

    # Verify modal content
    expect(demo09_page.locator("#modal-tool-name")).to_contain_text("send_email")
    expect(demo09_page.locator("#btn-approve")).to_be_visible()
    expect(demo09_page.locator("#btn-deny")).to_be_visible()

    # Verify "ACCESS REQUEST" header
    expect(modal).to_contain_text("ACCESS REQUEST")

    # Clean up: deny the action so the agent loop completes
    demo09_page.locator("#btn-deny").click()
    # Wait for agent loop to finish
    expect(demo09_page.locator("#conversation")).to_contain_text(
        "AGENT LOOP COMPLETE", timeout=10000,
    )


def test_clicking_approve_dismisses_modal(demo09_page: Page) -> None:
    """Test clicking Approve dismisses the modal."""
    # Trigger a high-risk action
    high_btn = demo09_page.locator(
        ".quick-btn",
        has_text="send_email",
    )
    high_btn.click()

    modal = demo09_page.locator("#approval-modal")
    expect(modal).not_to_have_class(re.compile(r"\bhidden\b"), timeout=15000)

    # Click Approve
    demo09_page.locator("#btn-approve").click()

    # Modal should be hidden again
    expect(modal).to_have_class(re.compile(r"\bhidden\b"), timeout=5000)

    # Conversation should show APPROVED
    expect(demo09_page.locator("#conversation")).to_contain_text(
        "APPROVED", timeout=10000,
    )

    # Wait for completion
    expect(demo09_page.locator("#conversation")).to_contain_text(
        "AGENT LOOP COMPLETE", timeout=10000,
    )


def test_clicking_deny_dismisses_modal_with_denial(demo09_page: Page) -> None:
    """Test clicking Deny dismisses the modal with denial message."""
    # Trigger a high-risk action
    high_btn = demo09_page.locator(
        ".quick-btn",
        has_text="send_email",
    )
    high_btn.click()

    modal = demo09_page.locator("#approval-modal")
    expect(modal).not_to_have_class(re.compile(r"\bhidden\b"), timeout=15000)

    # Click Deny
    demo09_page.locator("#btn-deny").click()

    # Modal should be hidden
    expect(modal).to_have_class(re.compile(r"\bhidden\b"), timeout=5000)

    # Conversation should show DENIED
    expect(demo09_page.locator("#conversation")).to_contain_text(
        "DENIED", timeout=10000,
    )

    # Wait for completion
    expect(demo09_page.locator("#conversation")).to_contain_text(
        "AGENT LOOP COMPLETE", timeout=10000,
    )


# ── Hacker aesthetic elements ────────────────────────────────


def test_hacker_aesthetic_elements(demo09_page: Page) -> None:
    """Test the hacker aesthetic CSS classes are present."""
    body = demo09_page.locator("body")
    # Dark background
    expect(body).to_have_css("background-color", re.compile(r"rgb\(10,\s*10,\s*10\)"))

    # Monospace font on the input
    input_field = demo09_page.locator("#agent-input")
    font = input_field.evaluate("el => getComputedStyle(el).fontFamily")
    assert "mono" in font.lower() or "jetbrains" in font.lower() or "courier" in font.lower()
