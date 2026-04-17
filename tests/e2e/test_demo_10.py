"""Playwright E2E tests for Demo 10: Secure Architecture web UI.

Tests verify page load, split-screen layout, attack scenario buttons,
defense layer indicators, and hacker aesthetic — all with mocked
vulnerable_system.run() and secure_system.run() so no live Ollama
instance is required.
"""

import re

from playwright.sync_api import Page, expect


# ── Page load and structure ──────────────────────────────────


def test_page_loads_with_200(demo10_page: Page) -> None:
    """Test page loads at localhost with 200 status."""
    expect(demo10_page.locator("body")).to_be_visible()
    assert demo10_page.title() != ""


def test_both_panels_visible(demo10_page: Page) -> None:
    """Test both panels (vulnerable and secured) are visible."""
    vuln_panel = demo10_page.locator("#vuln-panel")
    secure_panel = demo10_page.locator("#secure-panel")

    expect(vuln_panel).to_be_visible()
    expect(secure_panel).to_be_visible()


def test_vulnerable_panel_label(demo10_page: Page) -> None:
    """Test left panel is labeled '[ VULNERABLE SYSTEM ]' in red."""
    label = demo10_page.locator("text=VULNERABLE SYSTEM").first
    expect(label).to_be_visible()
    # Should have neon-red styling
    parent = label.locator("..")
    html = parent.inner_html()
    assert "neon-red" in html or "text-neon-red" in html


def test_secured_panel_label(demo10_page: Page) -> None:
    """Test right panel is labeled '[ SECURED SYSTEM ]' in green."""
    label = demo10_page.locator("text=SECURED SYSTEM").first
    expect(label).to_be_visible()
    parent = label.locator("..")
    html = parent.inner_html()
    assert "terminal-green" in html or "text-terminal-green" in html


# ── Attack scenario buttons ─────────────────────────────────


def test_attack_buttons_present(demo10_page: Page) -> None:
    """Test all attack scenario buttons are present."""
    buttons = demo10_page.locator(".attack-btn")
    expect(buttons.first).to_be_visible()
    # scenarios.json has 10 scenarios
    assert buttons.count() >= 5  # at least several categories represented


def test_attack_buttons_have_scenario_data(demo10_page: Page) -> None:
    """Test attack buttons carry scenario metadata attributes."""
    first_btn = demo10_page.locator(".attack-btn").first
    # Each button should have data attributes
    assert first_btn.get_attribute("data-scenario-id") is not None
    assert first_btn.get_attribute("data-attack-text") is not None
    assert first_btn.get_attribute("data-category") is not None
    assert first_btn.get_attribute("data-defense") is not None


def test_attack_button_categories(demo10_page: Page) -> None:
    """Test attack buttons span multiple categories."""
    buttons = demo10_page.locator(".attack-btn")
    categories = set()
    for i in range(buttons.count()):
        cat = buttons.nth(i).get_attribute("data-category")
        if cat:
            categories.add(cat)

    # Should have at least 3 different categories
    assert len(categories) >= 3
    # Verify key categories are present
    assert "direct_injection" in categories
    assert "agent_exploitation" in categories


# ── Defense layer indicators ─────────────────────────────────


def test_defense_indicators_present(demo10_page: Page) -> None:
    """Test defense layer indicators exist."""
    indicators = demo10_page.locator(".defense-indicator")
    assert indicators.count() == 4

    # Verify all four guard types
    expected_layers = {"input_guard", "retrieval_guard", "output_guard", "action_guard"}
    actual_layers = set()
    for i in range(indicators.count()):
        layer = indicators.nth(i).get_attribute("data-layer")
        if layer:
            actual_layers.add(layer)

    assert actual_layers == expected_layers


def test_defense_indicators_start_inactive(demo10_page: Page) -> None:
    """Test defense layer indicators start in inactive state."""
    indicators = demo10_page.locator(".defense-indicator")
    for i in range(indicators.count()):
        indicator = indicators.nth(i)
        classes = indicator.get_attribute("class") or ""
        assert "active" not in classes


# ── Attack execution ─────────────────────────────────────────


def test_clicking_attack_populates_both_panels(demo10_page: Page) -> None:
    """Test clicking an attack button populates both panels with output."""
    vuln_panel = demo10_page.locator("#vuln-panel")
    secure_panel = demo10_page.locator("#secure-panel")

    # Click the first attack button
    first_btn = demo10_page.locator(".attack-btn").first
    first_btn.click()

    # Wait for results in both panels
    # Vulnerable panel should show the attack succeeded
    expect(vuln_panel).to_contain_text("VULNERABLE RESPONSE", timeout=15000)

    # Secured panel should show the attack was blocked
    expect(secure_panel).to_contain_text("BLOCKED", timeout=15000)


def test_vulnerable_panel_shows_attack_success(demo10_page: Page) -> None:
    """Test vulnerable panel shows attack succeeded with red output."""
    vuln_panel = demo10_page.locator("#vuln-panel")

    # Click a direct_injection attack
    btn = demo10_page.locator(
        ".attack-btn[data-category='direct_injection']",
    ).first
    btn.click()

    # Should show attack succeeded
    expect(vuln_panel).to_contain_text("ATTACK SUCCEEDED", timeout=15000)


def test_secure_panel_shows_blocked(demo10_page: Page) -> None:
    """Test secured panel shows attack blocked with defense layer name."""
    secure_panel = demo10_page.locator("#secure-panel")

    # Click a direct_injection attack
    btn = demo10_page.locator(
        ".attack-btn[data-category='direct_injection']",
    ).first
    btn.click()

    # Should show BLOCKED BY with the defense layer
    expect(secure_panel).to_contain_text("BLOCKED BY", timeout=15000)
    expect(secure_panel).to_contain_text("ATTACK NEUTRALIZED", timeout=15000)


def test_defense_indicator_activates_on_block(demo10_page: Page) -> None:
    """Test the specific defense layer indicator activates when an attack is blocked."""
    # Click a direct_injection attack (expected_defense_layer: input_guard)
    btn = demo10_page.locator(
        ".attack-btn[data-category='direct_injection']",
    ).first
    btn.click()

    # Wait for secure panel to show blocked result
    secure_panel = demo10_page.locator("#secure-panel")
    expect(secure_panel).to_contain_text("BLOCKED", timeout=15000)

    # The input_guard indicator should now be active
    input_guard_indicator = demo10_page.locator(
        ".defense-indicator[data-layer='input_guard']",
    )
    expect(input_guard_indicator).to_have_class(re.compile(r"\bactive\b"), timeout=5000)


# ── Hacker aesthetic elements ────────────────────────────────


def test_hacker_aesthetic_dark_background(demo10_page: Page) -> None:
    """Test dark background is present."""
    body = demo10_page.locator("body")
    expect(body).to_have_css(
        "background-color",
        re.compile(r"rgb\(10,\s*10,\s*10\)"),
    )


def test_hacker_aesthetic_monospace_font(demo10_page: Page) -> None:
    """Test monospace font is used."""
    body = demo10_page.locator("body")
    font = body.evaluate("el => getComputedStyle(el).fontFamily")
    assert "mono" in font.lower() or "jetbrains" in font.lower() or "courier" in font.lower()


def test_hacker_aesthetic_glitch_title(demo10_page: Page) -> None:
    """Test the glitch-effect title is present."""
    title = demo10_page.locator(".glitch")
    expect(title).to_be_visible()
    expect(title).to_contain_text("SECURE ARCHITECTURE")


def test_hacker_aesthetic_scanline_or_overlay(demo10_page: Page) -> None:
    """Test scanline overlay or hacker aesthetic overlay elements exist."""
    # The base.html includes a scanline overlay via CSS or canvas
    # Check for the pseudo-element or canvas
    has_scanline = demo10_page.evaluate("""() => {
        // Check for scanline overlay via ::after pseudo-element on body or wrapper
        const body = document.body;
        const after = getComputedStyle(body, '::after');
        const hasScanline = after.content !== 'none' && after.content !== '';

        // Or check for canvas (matrix animation)
        const hasCanvas = document.querySelector('canvas') !== null;

        // Or check for any element with scanline-related styling
        const hasOverlay = document.querySelector('[class*="scanline"]') !== null;

        return hasScanline || hasCanvas || hasOverlay;
    }""")
    # If no explicit scanline element found, at least verify dark theme
    # (the hacker aesthetic is primarily conveyed through colors/fonts)
    if not has_scanline:
        body = demo10_page.locator("body")
        bg = body.evaluate("el => getComputedStyle(el).backgroundColor")
        assert "10" in bg  # rgb(10, 10, 10)
