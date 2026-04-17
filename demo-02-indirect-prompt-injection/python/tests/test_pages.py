"""Tests for the HTML pages — verifying structure, validity, and injection presence.

Core verification: legitimate page has no injection, each poisoned page
contains the injection string hidden in different ways.
"""

from pathlib import Path

_pages_dir = Path(__file__).resolve().parents[2] / "pages"

# Must match INJECTION_PAYLOAD from summarizer.py
_INJECTION_MARKER = "evil.example.com"
_INJECTION_RECALL = "recalled due to safety concerns"

ALL_PAGES = [
    "legitimate.html",
    "poisoned_whitefont.html",
    "poisoned_zerosize.html",
    "poisoned_comment.html",
    "poisoned_data_attr.html",
    "poisoned_aria.html",
    "poisoned_css_content.html",
]

POISONED_PAGES = [
    "poisoned_whitefont.html",
    "poisoned_zerosize.html",
    "poisoned_comment.html",
    "poisoned_data_attr.html",
    "poisoned_aria.html",
    "poisoned_css_content.html",
]


class TestPagesExist:
    """All expected HTML pages must exist."""

    def test_all_pages_exist(self) -> None:
        for page in ALL_PAGES:
            path = _pages_dir / page
            assert path.exists(), f"Missing page: {page}"

    def test_all_pages_non_empty(self) -> None:
        for page in ALL_PAGES:
            content = (_pages_dir / page).read_text()
            assert len(content) > 100, f"Page suspiciously small: {page}"


class TestPagesValidHTML:
    """All pages should be valid-ish HTML (contain expected structure)."""

    def test_all_have_doctype(self) -> None:
        for page in ALL_PAGES:
            html = (_pages_dir / page).read_text()
            assert "<!DOCTYPE html>" in html, f"Missing DOCTYPE in {page}"

    def test_all_have_title(self) -> None:
        for page in ALL_PAGES:
            html = (_pages_dir / page).read_text()
            assert "<title>" in html, f"Missing title in {page}"

    def test_all_have_body(self) -> None:
        for page in ALL_PAGES:
            html = (_pages_dir / page).read_text()
            assert "<body>" in html, f"Missing body in {page}"

    def test_all_contain_product_name(self) -> None:
        """All pages (legitimate and poisoned) contain the product description."""
        for page in ALL_PAGES:
            html = (_pages_dir / page).read_text()
            assert "NovaBlade X1" in html, f"Missing product name in {page}"


class TestLegitimatePageClean:
    """Legitimate page must NOT contain any injection payload."""

    def test_no_injection_marker(self) -> None:
        html = (_pages_dir / "legitimate.html").read_text()
        assert _INJECTION_MARKER not in html

    def test_no_recall_text(self) -> None:
        html = (_pages_dir / "legitimate.html").read_text()
        assert _INJECTION_RECALL not in html.lower()


class TestPoisonedPagesContainInjection:
    """Each poisoned page must contain the injection string in raw HTML."""

    def test_whitefont_has_injection(self) -> None:
        html = (_pages_dir / "poisoned_whitefont.html").read_text()
        assert _INJECTION_MARKER in html

    def test_zerosize_has_injection(self) -> None:
        html = (_pages_dir / "poisoned_zerosize.html").read_text()
        assert _INJECTION_MARKER in html

    def test_comment_has_injection(self) -> None:
        html = (_pages_dir / "poisoned_comment.html").read_text()
        assert _INJECTION_MARKER in html

    def test_data_attr_has_injection(self) -> None:
        html = (_pages_dir / "poisoned_data_attr.html").read_text()
        assert _INJECTION_MARKER in html

    def test_aria_has_injection(self) -> None:
        html = (_pages_dir / "poisoned_aria.html").read_text()
        assert _INJECTION_MARKER in html

    def test_css_content_has_injection(self) -> None:
        html = (_pages_dir / "poisoned_css_content.html").read_text()
        assert _INJECTION_MARKER in html


class TestPoisonedPagesHidingTechniques:
    """Each poisoned page uses a different hiding technique."""

    def test_whitefont_uses_color_white(self) -> None:
        html = (_pages_dir / "poisoned_whitefont.html").read_text()
        assert "color: white" in html or "color:white" in html

    def test_zerosize_uses_font_size_zero(self) -> None:
        html = (_pages_dir / "poisoned_zerosize.html").read_text()
        assert "font-size: 0" in html or "font-size:0" in html

    def test_comment_uses_html_comment(self) -> None:
        html = (_pages_dir / "poisoned_comment.html").read_text()
        assert "<!--" in html
        # The injection is inside the comment
        # Find comment content and verify it contains injection
        import re
        comments = re.findall(r"<!--(.*?)-->", html, re.DOTALL)
        injection_in_comment = any(_INJECTION_MARKER in c for c in comments)
        assert injection_in_comment, "Injection not found inside HTML comment"

    def test_data_attr_uses_data_attribute(self) -> None:
        html = (_pages_dir / "poisoned_data_attr.html").read_text()
        assert "data-description=" in html

    def test_aria_uses_aria_label(self) -> None:
        html = (_pages_dir / "poisoned_aria.html").read_text()
        assert "aria-label=" in html

    def test_css_content_uses_content_property(self) -> None:
        html = (_pages_dir / "poisoned_css_content.html").read_text()
        assert "content:" in html
        assert "::after" in html
