"""Input sanitizer that strips special tokens and invisible characters.

Removes zero-width characters, unicode homoglyphs, invisible formatting,
and other obfuscation techniques that attackers use to sneak injections
past simple pattern matchers.
"""

import re
import unicodedata
from typing import TypedDict


class SanitizerResult(TypedDict):
    blocked: bool
    reason: str
    layer: str
    sanitized_text: str


# Zero-width and invisible Unicode characters
INVISIBLE_CHARS: list[int] = [
    0x200B,  # Zero Width Space
    0x200C,  # Zero Width Non-Joiner
    0x200D,  # Zero Width Joiner
    0x200E,  # Left-to-Right Mark
    0x200F,  # Right-to-Left Mark
    0x2060,  # Word Joiner
    0x2061,  # Function Application
    0x2062,  # Invisible Times
    0x2063,  # Invisible Separator
    0x2064,  # Invisible Plus
    0xFEFF,  # Zero Width No-Break Space (BOM)
    0xFFF9,  # Interlinear Annotation Anchor
    0xFFFA,  # Interlinear Annotation Separator
    0xFFFB,  # Interlinear Annotation Terminator
]

# Common homoglyph mappings (visually similar characters → ASCII)
HOMOGLYPH_MAP: dict[str, str] = {
    "\u0430": "a",  # Cyrillic а → Latin a
    "\u0435": "e",  # Cyrillic е → Latin e
    "\u043e": "o",  # Cyrillic о → Latin o
    "\u0440": "p",  # Cyrillic р → Latin p
    "\u0441": "c",  # Cyrillic с → Latin c
    "\u0443": "y",  # Cyrillic у → Latin y
    "\u0456": "i",  # Cyrillic і → Latin i
    "\u0455": "s",  # Cyrillic ѕ → Latin s
    "\u04bb": "h",  # Cyrillic һ → Latin h
    "\u0501": "d",  # Cyrillic ԁ → Latin d
    "\u0131": "i",  # Latin Small Dotless I → i
    "\uff49": "i",  # Fullwidth i → Latin i
    "\uff4e": "n",  # Fullwidth n → Latin n
    "\uff47": "g",  # Fullwidth g → Latin g
    "\uff4f": "o",  # Fullwidth o → Latin o
    "\uff52": "r",  # Fullwidth r → Latin r
    "\uff45": "e",  # Fullwidth e → Latin e
    "\u2010": "-",  # Hyphen → ASCII hyphen
    "\u2011": "-",  # Non-Breaking Hyphen
    "\u2012": "-",  # Figure Dash
    "\u2013": "-",  # En Dash
    "\u2014": "-",  # Em Dash
    "\u2018": "'",  # Left Single Quotation
    "\u2019": "'",  # Right Single Quotation
    "\u201C": '"',  # Left Double Quotation
    "\u201D": '"',  # Right Double Quotation
}


def _strip_invisible(text: str) -> str:
    """Remove zero-width and invisible Unicode characters."""
    return "".join(ch for ch in text if ord(ch) not in INVISIBLE_CHARS)


def _normalize_homoglyphs(text: str) -> str:
    """Replace common Unicode homoglyphs with their ASCII equivalents."""
    result = []
    for ch in text:
        if ch in HOMOGLYPH_MAP:
            result.append(HOMOGLYPH_MAP[ch])
        else:
            result.append(ch)
    return "".join(result)


def _normalize_unicode(text: str) -> str:
    """Apply NFC normalization to collapse composed characters."""
    return unicodedata.normalize("NFC", text)


def _strip_special_tokens(text: str) -> str:
    """Remove common LLM special token markers."""
    # Remove markers like <|im_start|>, <|endoftext|>, [INST], etc.
    text = re.sub(r"<\|[^|]*\|>", "", text)
    text = re.sub(r"\[/?INST\]", "", text)
    text = re.sub(r"\[/?SYS\]", "", text)
    return text


def sanitize(user_input: str) -> SanitizerResult:
    """Sanitize user input by stripping invisible chars and normalizing homoglyphs.

    Args:
        user_input: The raw user input string.

    Returns:
        SanitizerResult with the sanitized text and whether changes were made.
    """
    if not user_input:
        return SanitizerResult(
            blocked=False,
            reason="Empty input — nothing to sanitize",
            layer="input_sanitizer",
            sanitized_text="",
        )

    step1 = _strip_invisible(user_input)
    step2 = _normalize_unicode(step1)
    step3 = _normalize_homoglyphs(step2)
    step4 = _strip_special_tokens(step3)
    sanitized = step4

    changed = sanitized != user_input
    reason = "Input was sanitized (invisible chars/homoglyphs removed)" if changed else "Input passed through unchanged"

    return SanitizerResult(
        blocked=False,  # Sanitizer cleans but doesn't block
        reason=reason,
        layer="input_sanitizer",
        sanitized_text=sanitized,
    )
