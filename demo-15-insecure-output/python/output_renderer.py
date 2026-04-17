"""Output renderer with XSS pattern detection, sanitization, and highlighting.

Provides three layers of output handling:
  1. detect_xss_patterns() — scan text for dangerous HTML/JS patterns
  2. sanitize_html() — strip all dangerous patterns, replacing with markers
  3. render_with_highlights() — wrap dangerous patterns in red highlight spans
"""

import re
from typing import Any

# ── XSS Pattern Definitions ────────────────────────────────────

XSS_PATTERNS: list[dict[str, str]] = [
    {
        "name": "script_tag",
        "pattern": r"<\s*script\b[^>]*>[\s\S]*?<\s*/\s*script\s*>",
        "description": "Inline <script> tags that execute arbitrary JavaScript",
    },
    {
        "name": "script_tag_open",
        "pattern": r"<\s*script\b[^>]*>",
        "description": "Opening <script> tag (may have no closing tag)",
    },
    {
        "name": "event_handler",
        "pattern": r"\bon(click|error|load|mouseover|mouseenter|focus|blur|submit|input|change|keydown|keyup)\s*=\s*[\"'][^\"']*[\"']",
        "description": "HTML event handler attributes (onclick, onerror, onload, onmouseover, etc.)",
    },
    {
        "name": "javascript_url",
        "pattern": r"(?:href|src|action)\s*=\s*[\"']?\s*javascript\s*:[^\"'\s>]+",
        "description": "javascript: protocol URLs in href, src, or action attributes",
    },
    {
        "name": "data_url",
        "pattern": r"(?:href|src)\s*=\s*[\"']?\s*data\s*:\s*text/html[^\"'\s>]*",
        "description": "data: URLs with text/html content type",
    },
    {
        "name": "svg_script",
        "pattern": r"<\s*svg\b[^>]*>[\s\S]*?<\s*script\b[\s\S]*?<\s*/\s*svg\s*>",
        "description": "SVG elements containing embedded <script> tags",
    },
    {
        "name": "css_exfiltration",
        "pattern": r"(?:background(?:-image)?|list-style-image)\s*:\s*url\s*\(\s*[\"']?https?://[^)\"']+",
        "description": "CSS url() properties loading external resources for data exfiltration",
    },
    {
        "name": "iframe_injection",
        "pattern": r"<\s*iframe\b[^>]*(?:src|srcdoc)\s*=\s*[^>]+>",
        "description": "Iframe elements that can load arbitrary content",
    },
    {
        "name": "meta_refresh",
        "pattern": r"<\s*meta\b[^>]*http-equiv\s*=\s*[\"']?\s*refresh\b[^>]*>",
        "description": "Meta refresh tags that redirect users to malicious pages",
    },
    {
        "name": "base_tag_hijack",
        "pattern": r"<\s*base\b[^>]*href\s*=\s*[^>]+>",
        "description": "Base tag hijacking to redirect all relative URLs",
    },
]


def detect_xss_patterns(text: str) -> list[dict[str, Any]]:
    """Scan text for all known XSS patterns.

    Args:
        text: The HTML/text output to scan.

    Returns:
        List of dicts with keys: name, description, match, position (start, end).
        Returns an empty list if no patterns are found.
    """
    if not text or not text.strip():
        return []

    findings: list[dict[str, Any]] = []
    seen_spans: set[tuple[int, int]] = set()

    for pattern_def in XSS_PATTERNS:
        try:
            for match in re.finditer(pattern_def["pattern"], text, re.IGNORECASE):
                span = (match.start(), match.end())
                # Avoid duplicate findings for overlapping patterns
                if span not in seen_spans:
                    seen_spans.add(span)
                    findings.append({
                        "name": pattern_def["name"],
                        "description": pattern_def["description"],
                        "match": match.group(),
                        "position": {"start": match.start(), "end": match.end()},
                    })
        except re.error:
            continue

    # Sort by position for consistent output
    findings.sort(key=lambda f: f["position"]["start"])
    return findings


def sanitize_html(html: str) -> str:
    """Remove all dangerous XSS patterns from HTML, replacing with markers.

    Each dangerous pattern is replaced with [XSS REMOVED: pattern_name] so
    the user can see where content was stripped.

    Args:
        html: The raw HTML string to sanitize.

    Returns:
        Sanitized HTML string with all dangerous patterns replaced by markers.
    """
    if not html:
        return html

    sanitized = html

    # Process patterns in order — full matches first (script_tag before script_tag_open,
    # svg_script before script_tag) to avoid partial replacements
    ordered_patterns = [
        "svg_script",
        "script_tag",
        "script_tag_open",
        "event_handler",
        "javascript_url",
        "data_url",
        "css_exfiltration",
        "iframe_injection",
        "meta_refresh",
        "base_tag_hijack",
    ]

    for pattern_name in ordered_patterns:
        pattern_def = next((p for p in XSS_PATTERNS if p["name"] == pattern_name), None)
        if pattern_def is None:
            continue
        marker = f"[XSS REMOVED: {pattern_name}]"
        sanitized = re.sub(
            pattern_def["pattern"],
            marker,
            sanitized,
            flags=re.IGNORECASE,
        )

    return sanitized


def render_with_highlights(html: str) -> str:
    """Return HTML with dangerous parts wrapped in red highlight spans.

    This is for visual display only — the dangerous content is shown but
    wrapped in <span> tags with red highlighting so it can be visually
    identified. The output should NOT be rendered as executable HTML.

    Args:
        html: The raw HTML string to highlight.

    Returns:
        HTML string with dangerous patterns wrapped in highlight spans.
    """
    if not html:
        return html

    findings = detect_xss_patterns(html)
    if not findings:
        return html

    # Build the highlighted version by replacing matched regions
    # Work backwards to preserve positions
    highlighted = html
    for finding in reversed(findings):
        start = finding["position"]["start"]
        end = finding["position"]["end"]
        matched_text = highlighted[start:end]
        # Escape the matched text for safe display, then wrap in highlight
        escaped_match = (
            matched_text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        replacement = (
            f'<span class="xss-highlight" style="background:rgba(255,0,64,0.25);'
            f'border:1px solid rgba(255,0,64,0.6);border-radius:2px;padding:0 2px;" '
            f'title="{finding["name"]}: {finding["description"]}">'
            f'{escaped_match}</span>'
        )
        highlighted = highlighted[:start] + replacement + highlighted[end:]

    return highlighted
