"""Tests for backwards-compatibility shim — 'defenses' package re-exports 'retrieval_defenses'."""

import warnings

import pytest


class TestDefensesCompatShim:
    """Verify the deprecated 'defenses' package still re-exports retrieval_defenses modules."""

    def test_import_emits_deprecation_warning(self) -> None:
        """Importing 'defenses' should emit a DeprecationWarning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            import defenses  # noqa: F401
            dep_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            assert len(dep_warnings) >= 1
            assert "retrieval_defenses" in str(dep_warnings[0].message)

    def test_submodules_accessible(self) -> None:
        """All four defense submodules should be importable via 'defenses'."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from defenses import document_validator, injection_detector, relevance_scorer, source_verifier  # noqa: F401

    def test_injection_detector_check_callable(self) -> None:
        """injection_detector.check should be callable through the shim."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from defenses import injection_detector
            assert callable(getattr(injection_detector, "check", None))

    def test_document_validator_check_callable(self) -> None:
        """document_validator.check should be callable through the shim."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from defenses import document_validator
            assert callable(getattr(document_validator, "check", None))
