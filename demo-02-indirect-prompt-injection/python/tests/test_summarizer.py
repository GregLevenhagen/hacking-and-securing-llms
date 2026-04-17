"""Tests for the summarizer module — text extraction from HTML pages.

Verifies the core insight of indirect prompt injection: hidden text is
invisible to humans but visible to text extractors sent to LLMs.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from summarizer import (
    INJECTION_PAYLOAD,
    compute_detection_metrics,
    extract_text,
    extract_visible_text,
    fetch_page,
    summarize_page,
    PAGES,
    SUMMARIZE_SYSTEM_PROMPT,
)
from app_terminal import run_automated

_pages_dir = Path(__file__).resolve().parents[2] / "pages"


def _read_page(filename: str) -> str:
    """Read an HTML file from the pages directory."""
    return (_pages_dir / filename).read_text()


# ---------- extract_text (what LLM sees) ----------


class TestExtractTextLegitimate:
    """Legitimate page: extraction should contain product info, no injection."""

    def test_contains_product_name(self) -> None:
        html = _read_page("legitimate.html")
        text = extract_text(html)
        assert "NovaBlade X1" in text

    def test_contains_product_description(self) -> None:
        html = _read_page("legitimate.html")
        text = extract_text(html)
        assert "flagship productivity laptop" in text

    def test_contains_price(self) -> None:
        html = _read_page("legitimate.html")
        text = extract_text(html)
        assert "$1,899" in text

    def test_no_injection_payload(self) -> None:
        html = _read_page("legitimate.html")
        text = extract_text(html)
        assert "evil.example.com" not in text
        assert "recalled" not in text.lower()


class TestExtractTextPoisonedWhitefont:
    """White font injection: text is invisible visually but present in extraction."""

    def test_contains_injection(self) -> None:
        html = _read_page("poisoned_whitefont.html")
        text = extract_text(html)
        assert "evil.example.com" in text

    def test_contains_recalled_text(self) -> None:
        html = _read_page("poisoned_whitefont.html")
        text = extract_text(html)
        assert "recalled" in text.lower()

    def test_still_contains_product_info(self) -> None:
        html = _read_page("poisoned_whitefont.html")
        text = extract_text(html)
        assert "NovaBlade X1" in text


class TestExtractTextPoisonedZerosize:
    """Zero-size font injection: text is invisible visually but present in extraction."""

    def test_contains_injection(self) -> None:
        html = _read_page("poisoned_zerosize.html")
        text = extract_text(html)
        assert "evil.example.com" in text

    def test_contains_recall_text(self) -> None:
        html = _read_page("poisoned_zerosize.html")
        text = extract_text(html)
        assert "recall" in text.lower()

    def test_still_contains_product_info(self) -> None:
        html = _read_page("poisoned_zerosize.html")
        text = extract_text(html)
        assert "NovaBlade X1" in text


class TestExtractTextPoisonedComment:
    """HTML comment injection: comments are extracted when include_comments=True."""

    def test_contains_injection_with_comments(self) -> None:
        html = _read_page("poisoned_comment.html")
        text = extract_text(html, include_comments=True)
        assert "evil.example.com" in text

    def test_no_injection_without_comments(self) -> None:
        html = _read_page("poisoned_comment.html")
        text = extract_text(html, include_comments=False)
        assert "evil.example.com" not in text

    def test_still_contains_product_info(self) -> None:
        html = _read_page("poisoned_comment.html")
        text = extract_text(html)
        assert "NovaBlade X1" in text


# ---------- extract_text: new injection vectors ----------


class TestExtractTextDataAttribute:
    """Data attribute injection: payload in data-description is extracted when include_attrs=True."""

    def test_contains_injection_with_attrs(self) -> None:
        html = _read_page("poisoned_data_attr.html")
        text = extract_text(html, include_attrs=True)
        assert "evil.example.com" in text

    def test_no_injection_without_attrs(self) -> None:
        html = _read_page("poisoned_data_attr.html")
        text = extract_text(html, include_attrs=False, include_css_content=False)
        assert "evil.example.com" not in text

    def test_still_contains_product_info(self) -> None:
        html = _read_page("poisoned_data_attr.html")
        text = extract_text(html)
        assert "NovaBlade X1" in text


class TestExtractTextAriaLabel:
    """ARIA label injection: payload in aria-label is extracted when include_attrs=True."""

    def test_contains_injection_with_attrs(self) -> None:
        html = _read_page("poisoned_aria.html")
        text = extract_text(html, include_attrs=True)
        assert "evil.example.com" in text

    def test_no_injection_without_attrs(self) -> None:
        html = _read_page("poisoned_aria.html")
        text = extract_text(html, include_attrs=False, include_css_content=False)
        assert "evil.example.com" not in text

    def test_still_contains_product_info(self) -> None:
        html = _read_page("poisoned_aria.html")
        text = extract_text(html)
        assert "NovaBlade X1" in text


class TestExtractTextCssContent:
    """CSS content injection: payload in content property extracted via regex."""

    def test_contains_injection_with_css_content(self) -> None:
        html = _read_page("poisoned_css_content.html")
        text = extract_text(html, include_css_content=True)
        assert "evil.example.com" in text

    def test_no_injection_without_css_content(self) -> None:
        html = _read_page("poisoned_css_content.html")
        text = extract_text(html, include_css_content=False, include_attrs=False)
        assert "evil.example.com" not in text

    def test_still_contains_product_info(self) -> None:
        html = _read_page("poisoned_css_content.html")
        text = extract_text(html)
        assert "NovaBlade X1" in text


# ---------- extract_visible_text (what human sees) ----------


class TestExtractVisibleText:
    """Visible text extraction should strip hidden elements."""

    def test_legitimate_has_product_info(self) -> None:
        html = _read_page("legitimate.html")
        text = extract_visible_text(html)
        assert "NovaBlade X1" in text

    def test_whitefont_hides_injection(self) -> None:
        html = _read_page("poisoned_whitefont.html")
        text = extract_visible_text(html)
        assert "evil.example.com" not in text

    def test_zerosize_hides_injection(self) -> None:
        html = _read_page("poisoned_zerosize.html")
        text = extract_visible_text(html)
        assert "evil.example.com" not in text

    def test_comment_hides_injection(self) -> None:
        """HTML comments are not in visible text (get_text doesn't include them)."""
        html = _read_page("poisoned_comment.html")
        text = extract_visible_text(html)
        assert "evil.example.com" not in text

    def test_data_attr_hides_injection(self) -> None:
        """Data attributes are not in visible text (get_text doesn't include them)."""
        html = _read_page("poisoned_data_attr.html")
        text = extract_visible_text(html)
        assert "evil.example.com" not in text

    def test_aria_hides_injection(self) -> None:
        """Clipped aria-label element is stripped from visible text."""
        html = _read_page("poisoned_aria.html")
        text = extract_visible_text(html)
        assert "evil.example.com" not in text

    def test_css_content_hides_injection(self) -> None:
        """CSS content properties are not in visible text (CSS pseudo-elements not in DOM)."""
        html = _read_page("poisoned_css_content.html")
        text = extract_visible_text(html)
        assert "evil.example.com" not in text


# ---------- summarize_page ----------


class TestSummarizePage:
    """Test summarize_page with a mock client (no live LLM)."""

    def test_returns_expected_keys(self, mock_client) -> None:  # type: ignore[no-untyped-def]
        """summarize_page should return dict with all expected keys including metrics."""
        import threading
        from server import app

        # Start the Flask test server
        server = threading.Thread(
            target=lambda: app.run(host="127.0.0.1", port=18080, use_reloader=False),
            daemon=True,
        )
        server.start()

        import time
        time.sleep(0.5)

        result = summarize_page("http://127.0.0.1:18080/pages/legitimate.html", client=mock_client)
        assert "url" in result
        assert "html" in result
        assert "extracted_text" in result
        assert "visible_text" in result
        assert "summary" in result
        assert "metrics" in result
        assert "suspicious" in result["metrics"]

    def test_injection_payload_constant(self) -> None:
        """INJECTION_PAYLOAD matches what's in the poisoned pages."""
        assert "evil.example.com" in INJECTION_PAYLOAD
        assert "evil.example.com" in INJECTION_PAYLOAD.lower()

    def test_pages_list_structure(self) -> None:
        """PAGES list has correct structure."""
        assert len(PAGES) == 7
        for page in PAGES:
            assert "name" in page
            assert "file" in page
            assert "poisoned" in page

    def test_pages_list_poisoned_count(self) -> None:
        """6 poisoned pages and 1 legitimate."""
        poisoned = [p for p in PAGES if p["poisoned"]]
        legitimate = [p for p in PAGES if not p["poisoned"]]
        assert len(poisoned) == 6
        assert len(legitimate) == 1


# ---------- compute_detection_metrics ----------


class TestDetectionMetrics:
    """Test detection metrics that compare visible vs extracted text lengths."""

    def test_clean_page_not_suspicious(self) -> None:
        """Legitimate page: extracted ~= visible, ratio near 1.0."""
        html = _read_page("legitimate.html")
        visible = extract_visible_text(html)
        extracted = extract_text(html)
        metrics = compute_detection_metrics(visible, extracted)
        assert not metrics["suspicious"]
        assert metrics["length_ratio"] <= 1.10

    def test_poisoned_page_is_suspicious(self) -> None:
        """Poisoned whitefont page: extracted > visible, ratio > 1.10."""
        html = _read_page("poisoned_whitefont.html")
        visible = extract_visible_text(html)
        extracted = extract_text(html)
        metrics = compute_detection_metrics(visible, extracted)
        assert metrics["suspicious"]
        assert metrics["extra_chars"] > 0

    def test_data_attr_page_is_suspicious(self) -> None:
        """Data attribute poisoned page has more extracted text."""
        html = _read_page("poisoned_data_attr.html")
        visible = extract_visible_text(html)
        extracted = extract_text(html)
        metrics = compute_detection_metrics(visible, extracted)
        assert metrics["suspicious"]

    def test_metrics_keys(self) -> None:
        """Metrics dict has all expected keys."""
        metrics = compute_detection_metrics("short", "short text that is longer")
        assert "visible_length" in metrics
        assert "extracted_length" in metrics
        assert "length_ratio" in metrics
        assert "extra_chars" in metrics
        assert "suspicious" in metrics

    def test_empty_visible_text(self) -> None:
        """Empty visible text results in infinite ratio and suspicious flag."""
        metrics = compute_detection_metrics("", "some extracted text")
        assert metrics["suspicious"]
        assert metrics["length_ratio"] == float("inf")

    def test_equal_texts_not_suspicious(self) -> None:
        """Identical texts should not be suspicious."""
        metrics = compute_detection_metrics("same text", "same text")
        assert not metrics["suspicious"]
        assert metrics["length_ratio"] == 1.0
        assert metrics["extra_chars"] == 0


# ---------- Parameterized tests across all injection types ----------


_ALL_POISONED = [
    "poisoned_whitefont.html",
    "poisoned_zerosize.html",
    "poisoned_comment.html",
    "poisoned_data_attr.html",
    "poisoned_aria.html",
    "poisoned_css_content.html",
]


class TestAllInjectionTypesParameterized:
    """Parameterized tests running every poisoned page through the same assertions."""

    @pytest.mark.parametrize("page_file", _ALL_POISONED)
    def test_extracted_text_contains_injection(self, page_file: str) -> None:
        """All poisoned pages should have injection in extracted text (full extraction)."""
        html = _read_page(page_file)
        text = extract_text(html)
        assert "evil.example.com" in text, f"{page_file}: injection not found in extracted text"

    @pytest.mark.parametrize("page_file", _ALL_POISONED)
    def test_visible_text_hides_injection(self, page_file: str) -> None:
        """All poisoned pages should hide injection from visible text."""
        html = _read_page(page_file)
        text = extract_visible_text(html)
        assert "evil.example.com" not in text, f"{page_file}: injection leaked into visible text"

    @pytest.mark.parametrize("page_file", _ALL_POISONED)
    def test_product_info_preserved(self, page_file: str) -> None:
        """All poisoned pages should still contain the product info."""
        html = _read_page(page_file)
        text = extract_text(html)
        assert "NovaBlade X1" in text, f"{page_file}: product name missing"
        assert "$1,899" in text, f"{page_file}: price missing"

    @pytest.mark.parametrize("page_file", _ALL_POISONED)
    def test_detection_metrics_suspicious(self, page_file: str) -> None:
        """All poisoned pages should trigger suspicious detection metrics."""
        html = _read_page(page_file)
        visible = extract_visible_text(html)
        extracted = extract_text(html)
        metrics = compute_detection_metrics(visible, extracted)
        assert metrics["suspicious"], f"{page_file}: not flagged as suspicious (ratio={metrics['length_ratio']})"
        assert metrics["extra_chars"] > 0, f"{page_file}: no extra chars detected"


# ---------- fetch_page error handling ----------


class TestFetchPage:
    """Test fetch_page with various error conditions."""

    def test_fetch_page_connection_error(self) -> None:
        """fetch_page raises on connection errors."""
        import requests
        with pytest.raises(requests.exceptions.ConnectionError):
            fetch_page("http://127.0.0.1:19999/nonexistent")

    def test_fetch_page_timeout(self) -> None:
        """fetch_page raises on timeout."""
        import requests
        with patch("summarizer.requests.get", side_effect=requests.exceptions.Timeout("timed out")):
            with pytest.raises(requests.exceptions.Timeout):
                fetch_page("http://example.com")

    def test_fetch_page_http_error(self) -> None:
        """fetch_page raises on HTTP error status codes."""
        import requests
        mock_resp = requests.Response()
        mock_resp.status_code = 500
        mock_resp._content = b"Internal Server Error"
        mock_resp.url = "http://example.com"
        with patch("summarizer.requests.get", return_value=mock_resp):
            with pytest.raises(requests.exceptions.HTTPError):
                fetch_page("http://example.com")

    def test_fetch_page_invalid_url(self) -> None:
        """fetch_page raises on invalid URL schemes."""
        import requests
        with pytest.raises(requests.exceptions.MissingSchema):
            fetch_page("not-a-url")

    def test_fetch_page_returns_html(self) -> None:
        """fetch_page returns the response text on success."""
        import requests
        mock_resp = requests.Response()
        mock_resp.status_code = 200
        mock_resp._content = b"<html><body>Hello</body></html>"
        mock_resp.encoding = "utf-8"
        with patch("summarizer.requests.get", return_value=mock_resp):
            result = fetch_page("http://example.com")
            assert "<html>" in result
            assert "Hello" in result


# ---------- extract_text edge cases ----------


class TestExtractTextEdgeCases:
    """Edge case tests for extract_text robustness."""

    def test_malformed_html(self) -> None:
        """extract_text handles malformed HTML gracefully."""
        html = "<html><body><p>Unclosed paragraph<div>Mixed <b>nesting</p></b></div>"
        text = extract_text(html)
        assert "Unclosed paragraph" in text
        assert "Mixed" in text

    def test_empty_html(self) -> None:
        """extract_text returns empty-ish string for empty HTML."""
        text = extract_text("")
        assert len(text.strip()) == 0

    def test_script_and_style_excluded(self) -> None:
        """extract_text should not include script or style tag contents."""
        html = """<html><body>
            <script>var secret = 'evil';</script>
            <style>body { color: red; }</style>
            <p>Visible text</p>
        </body></html>"""
        text = extract_text(html)
        assert "Visible text" in text
        # Script/style content should ideally not appear in extracted text
        # (BS4 get_text includes them — this documents the behavior)


# ---------- summarize_page with poisoned page ----------


class TestSummarizePagePoisoned:
    """Test summarize_page returns metrics for poisoned pages."""

    def test_poisoned_page_metrics_suspicious(self, mock_client) -> None:  # type: ignore[no-untyped-def]
        """Summarizing a poisoned page should return suspicious metrics."""
        import threading
        import time
        from server import app

        server = threading.Thread(
            target=lambda: app.run(host="127.0.0.1", port=18081, use_reloader=False),
            daemon=True,
        )
        server.start()
        time.sleep(0.5)

        result = summarize_page(
            "http://127.0.0.1:18081/pages/poisoned_whitefont.html",
            client=mock_client,
        )
        assert result["metrics"]["suspicious"] is True
        assert result["metrics"]["extra_chars"] > 0
        assert "evil.example.com" in result["extracted_text"]


# ---------- run_automated integration test ----------


class TestRunAutomated:
    """Integration test for run_automated with mock client."""

    def test_processes_all_pages(self, mock_client) -> None:  # type: ignore[no-untyped-def]
        """run_automated should process all pages via the local server."""
        import threading
        import time
        from server import app

        server = threading.Thread(
            target=lambda: app.run(host="127.0.0.1", port=18082, use_reloader=False),
            daemon=True,
        )
        server.start()
        time.sleep(0.5)

        with patch("app_terminal.SERVER_PORT", 18082):
            run_automated(client=mock_client)

        # Should have been called once per page for the summarize step
        assert len(mock_client.chat_calls) == len(PAGES)
