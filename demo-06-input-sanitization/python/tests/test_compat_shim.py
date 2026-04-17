"""Tests for backwards-compatibility shim — 'defenses' package re-exports 'input_defenses'."""

import warnings

import pytest


class TestDefensesCompatShim:
    """Verify the deprecated 'defenses' package still re-exports input_defenses modules."""

    def test_import_emits_deprecation_warning(self) -> None:
        """Importing 'defenses' should emit a DeprecationWarning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            import defenses  # noqa: F401
            dep_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            assert len(dep_warnings) >= 1
            assert "input_defenses" in str(dep_warnings[0].message)

    def test_submodules_accessible(self) -> None:
        """All four defense submodules should be importable via 'defenses'."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from defenses import regex_filter, input_sanitizer, llm_judge, llm_guard_scanner  # noqa: F401

    def test_regex_filter_check_callable(self) -> None:
        """regex_filter.check should be callable through the shim."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from defenses import regex_filter
            assert callable(getattr(regex_filter, "check", None))

    def test_input_sanitizer_sanitize_callable(self) -> None:
        """input_sanitizer.sanitize should be callable through the shim."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from defenses import input_sanitizer
            assert callable(getattr(input_sanitizer, "sanitize", None))
