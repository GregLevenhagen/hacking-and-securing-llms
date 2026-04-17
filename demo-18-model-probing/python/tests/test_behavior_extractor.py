"""Tests for Demo 18 behavior extractor — profile building and extraction functions."""

import pytest

from behavior_extractor import (
    BehaviorProfile,
    build_profile,
    extract_boundary_info,
    extract_capability_info,
    extract_membership_info,
    extract_system_prompt_info,
    extract_temperature_info,
)


class TestBehaviorProfile:
    """Tests for the BehaviorProfile dataclass."""

    def test_default_values(self) -> None:
        """Profile initializes with sensible defaults."""
        profile = BehaviorProfile()
        assert profile.refusal_boundary_index == -1
        assert profile.known_data_score == 0.0
        assert profile.system_prompt_fragments == []
        assert profile.temperature_estimate == 0.0
        assert profile.capability_scores == {}

    def test_to_dict(self) -> None:
        """to_dict() produces a JSON-serializable dict."""
        profile = BehaviorProfile(
            refusal_boundary_index=3,
            known_data_score=0.75,
            system_prompt_fragments=["I was designed to help"],
            temperature_estimate=0.42,
            capability_scores={"math": 0.9, "code_generation": 0.8},
        )
        d = profile.to_dict()
        assert d["refusal_boundary_index"] == 3
        assert d["known_data_score"] == 0.75
        assert len(d["system_prompt_fragments"]) == 1
        assert d["temperature_estimate"] == 0.42
        assert d["capability_scores"]["math"] == 0.9
        assert "summary" in d

    def test_summary_no_refusal(self) -> None:
        """Summary describes 'no refusals' when index is -1."""
        profile = BehaviorProfile(refusal_boundary_index=-1)
        summary = profile.summary()
        assert "No refusals detected" in summary

    def test_summary_strict_refusal(self) -> None:
        """Summary describes 'strict' when refusal is early."""
        profile = BehaviorProfile(refusal_boundary_index=1)
        summary = profile.summary()
        assert "Strict" in summary

    def test_summary_permissive_refusal(self) -> None:
        """Summary describes 'permissive' when refusal is late."""
        profile = BehaviorProfile(refusal_boundary_index=6)
        summary = profile.summary()
        assert "Permissive" in summary

    def test_summary_includes_training_data(self) -> None:
        """Summary includes training data score description."""
        profile = BehaviorProfile(known_data_score=0.85)
        summary = profile.summary()
        assert "Strong indicators" in summary

    def test_summary_includes_temperature(self) -> None:
        """Summary includes temperature description."""
        profile = BehaviorProfile(temperature_estimate=0.15)
        summary = profile.summary()
        assert "near-deterministic" in summary

    def test_summary_high_temperature(self) -> None:
        """Summary describes high randomness for high temperature."""
        profile = BehaviorProfile(temperature_estimate=1.2)
        summary = profile.summary()
        assert "high randomness" in summary

    def test_summary_capabilities(self) -> None:
        """Summary includes capability best/worst when scores present."""
        profile = BehaviorProfile(
            capability_scores={"math": 1.0, "translation": 0.3, "code_generation": 0.7}
        )
        summary = profile.summary()
        assert "best=math" in summary
        assert "worst=translation" in summary


class TestBuildProfile:
    """Tests for building a unified profile from all technique results."""

    def test_builds_from_all_results(self) -> None:
        """build_profile correctly populates all profile fields."""
        all_results = {
            "boundary_probing": {"refusal_boundary_index": 4, "refusal_count": 3},
            "membership_inference": {"known_data_score": 0.83},
            "system_prompt_recovery": {
                "fragments": ["I am designed to help users"],
                "disclosure_score": 0.17,
            },
            "temperature_fingerprinting": {"estimated_temperature": 0.55},
            "capability_mapping": {
                "capability_scores": {"math": 0.9, "translation": 0.7},
                "average_score": 0.8,
            },
        }
        profile = build_profile(all_results)
        assert profile.refusal_boundary_index == 4
        assert profile.known_data_score == 0.83
        assert len(profile.system_prompt_fragments) == 1
        assert profile.temperature_estimate == 0.55
        assert profile.capability_scores["math"] == 0.9

    def test_builds_with_partial_results(self) -> None:
        """build_profile handles missing technique results gracefully."""
        all_results = {
            "boundary_probing": {"refusal_boundary_index": 2},
        }
        profile = build_profile(all_results)
        assert profile.refusal_boundary_index == 2
        assert profile.known_data_score == 0.0  # default
        assert profile.system_prompt_fragments == []
        assert profile.temperature_estimate == 0.0
        assert profile.capability_scores == {}

    def test_builds_with_empty_results(self) -> None:
        """build_profile returns defaults for empty input."""
        profile = build_profile({})
        assert profile.refusal_boundary_index == -1
        assert profile.known_data_score == 0.0


class TestExtractFunctions:
    """Tests for individual extraction helper functions."""

    def test_extract_boundary_info(self) -> None:
        """extract_boundary_info returns expected keys."""
        analysis = {"refusal_boundary_index": 5, "refusal_count": 2, "total_probes": 8}
        info = extract_boundary_info(analysis)
        assert info["refusal_boundary_index"] == 5
        assert info["refusal_count"] == 2
        assert info["total_probes"] == 8

    def test_extract_membership_info(self) -> None:
        """extract_membership_info returns expected keys."""
        analysis = {"known_data_score": 0.67, "known_correct": 2, "known_total": 4, "fake_rejected": 1, "fake_total": 2}
        info = extract_membership_info(analysis)
        assert info["known_data_score"] == 0.67

    def test_extract_system_prompt_info(self) -> None:
        """extract_system_prompt_info returns fragments."""
        analysis = {"fragments": ["frag1", "frag2"], "disclosure_score": 0.33, "total_fragments": 2}
        info = extract_system_prompt_info(analysis)
        assert len(info["fragments"]) == 2

    def test_extract_temperature_info(self) -> None:
        """extract_temperature_info returns temperature estimate."""
        analysis = {"estimated_temperature": 0.42, "average_similarity": 0.79, "unique_responses": 3, "total_responses": 5}
        info = extract_temperature_info(analysis)
        assert info["estimated_temperature"] == 0.42

    def test_extract_capability_info(self) -> None:
        """extract_capability_info returns scores dict."""
        analysis = {"capability_scores": {"math": 1.0}, "average_score": 1.0}
        info = extract_capability_info(analysis)
        assert info["capability_scores"]["math"] == 1.0

    def test_extract_functions_handle_missing_keys(self) -> None:
        """All extract functions return defaults for missing keys."""
        empty: dict = {}
        assert extract_boundary_info(empty)["refusal_boundary_index"] == -1
        assert extract_membership_info(empty)["known_data_score"] == 0.0
        assert extract_system_prompt_info(empty)["fragments"] == []
        assert extract_temperature_info(empty)["estimated_temperature"] == 0.0
        assert extract_capability_info(empty)["capability_scores"] == {}
