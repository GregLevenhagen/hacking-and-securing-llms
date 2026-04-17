"""Tests for Demo 17 mock content (mock_content.py).

Verifies that clean and poisoned content is properly structured,
that injection markers are present only in poisoned content,
and that the fetch_content function works correctly.
"""

import pytest

from mock_content import (
    CLEAN_PAGES,
    POISONED_PAGES,
    fetch_content,
    get_injection_markers,
)


class TestCleanPages:
    """Test the clean (unmodified) web page content."""

    def test_clean_pages_has_three_entries(self) -> None:
        assert len(CLEAN_PAGES) == 3

    def test_clean_pages_has_expected_urls(self) -> None:
        expected = {
            "news.example.com/tech",
            "shop.example.com/product",
            "blog.example.com/post",
        }
        assert set(CLEAN_PAGES.keys()) == expected

    def test_clean_news_contains_ai_content(self) -> None:
        content = CLEAN_PAGES["news.example.com/tech"]
        assert "artificial intelligence" in content.lower()
        assert "breakthroughs" in content.lower()

    def test_clean_product_contains_laptop_specs(self) -> None:
        content = CLEAN_PAGES["shop.example.com/product"]
        assert "ProBook Ultra 16" in content
        assert "$1,899.99" in content
        assert "32GB" in content

    def test_clean_blog_contains_remote_work(self) -> None:
        content = CLEAN_PAGES["blog.example.com/post"]
        assert "remote work" in content.lower()
        assert "hybrid" in content.lower()

    def test_clean_pages_have_no_injection_markers(self) -> None:
        markers = get_injection_markers()
        for url, content in CLEAN_PAGES.items():
            for marker in markers:
                assert marker.lower() not in content.lower(), (
                    f"Injection marker '{marker}' found in clean page: {url}"
                )

    def test_clean_content_is_nonempty(self) -> None:
        for url, content in CLEAN_PAGES.items():
            assert len(content) > 100, f"Clean page {url} is too short"

    def test_clean_and_poisoned_have_same_urls(self) -> None:
        assert set(CLEAN_PAGES.keys()) == set(POISONED_PAGES.keys())


class TestPoisonedPages:
    """Test the poisoned web page content with injections."""

    def test_poisoned_pages_has_three_entries(self) -> None:
        assert len(POISONED_PAGES) == 3

    def test_poisoned_news_contains_email_injection(self) -> None:
        content = POISONED_PAGES["news.example.com/tech"]
        assert "admin@evil.com" in content
        assert "send an email notification" in content.lower()

    def test_poisoned_product_contains_recall_injection(self) -> None:
        content = POISONED_PAGES["shop.example.com/product"]
        assert "RECALLED" in content
        assert "update the database" in content.lower()

    def test_poisoned_blog_contains_sql_injection(self) -> None:
        content = POISONED_PAGES["blog.example.com/post"]
        assert "SELECT * FROM users" in content
        assert "SYSTEM OVERRIDE" in content

    def test_poisoned_pages_still_contain_legitimate_content(self) -> None:
        """Poisoned pages should also have the real article content."""
        assert "artificial intelligence" in POISONED_PAGES["news.example.com/tech"].lower()
        assert "ProBook Ultra 16" in POISONED_PAGES["shop.example.com/product"]
        assert "remote work" in POISONED_PAGES["blog.example.com/post"].lower()

    def test_each_poisoned_page_has_at_least_one_marker(self) -> None:
        markers = get_injection_markers()
        for url, content in POISONED_PAGES.items():
            found = [m for m in markers if m.lower() in content.lower()]
            assert len(found) > 0, f"No injection markers in poisoned page: {url}"


class TestFetchContent:
    """Test the fetch_content function."""

    def test_fetch_clean_content(self) -> None:
        content = fetch_content("news.example.com/tech", poisoned=False)
        assert content == CLEAN_PAGES["news.example.com/tech"]

    def test_fetch_poisoned_content(self) -> None:
        content = fetch_content("news.example.com/tech", poisoned=True)
        assert content == POISONED_PAGES["news.example.com/tech"]

    def test_fetch_default_is_clean(self) -> None:
        content = fetch_content("shop.example.com/product")
        assert content == CLEAN_PAGES["shop.example.com/product"]

    def test_fetch_unknown_url_raises_keyerror(self) -> None:
        with pytest.raises(KeyError, match="URL not found"):
            fetch_content("nonexistent.example.com/page")

    def test_fetch_all_clean_urls(self) -> None:
        for url in CLEAN_PAGES:
            content = fetch_content(url, poisoned=False)
            assert len(content) > 0

    def test_fetch_all_poisoned_urls(self) -> None:
        for url in POISONED_PAGES:
            content = fetch_content(url, poisoned=True)
            assert len(content) > 0


class TestInjectionMarkers:
    """Test the injection marker utilities."""

    def test_markers_list_is_nonempty(self) -> None:
        markers = get_injection_markers()
        assert len(markers) > 0

    def test_markers_returns_copy(self) -> None:
        """Ensure get_injection_markers returns a copy, not a reference."""
        m1 = get_injection_markers()
        m2 = get_injection_markers()
        assert m1 == m2
        m1.append("test")
        assert len(m1) != len(m2)

    def test_markers_cover_all_scenarios(self) -> None:
        markers = get_injection_markers()
        marker_text = " ".join(markers).lower()
        assert "evil.com" in marker_text
        assert "recalled" in marker_text
        assert "select" in marker_text
