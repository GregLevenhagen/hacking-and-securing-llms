"""Tests for Demo 18 probing attacks — technique loading, analysis functions."""

import json
from pathlib import Path

import pytest

from probing_attacks import (
    ANALYZERS,
    CAPABILITY_LABELS,
    KNOWN_COMPLETIONS,
    analyze,
    analyze_boundary_probing,
    analyze_capability_mapping,
    analyze_behavior_cloning,
    analyze_membership_inference,
    analyze_system_prompt_recovery,
    analyze_temperature_fingerprinting,
    get_all_techniques,
    get_technique,
    load_probes,
)


class TestLoadProbes:
    """Tests for loading probe techniques from JSON."""

    def test_loads_probes(self) -> None:
        """Probes load as a dict with 'techniques' key."""
        data = load_probes()
        assert "techniques" in data
        assert len(data["techniques"]) > 0

    def test_has_six_techniques(self) -> None:
        """There are exactly 6 probing techniques."""
        techniques = get_all_techniques()
        assert len(techniques) == 6

    def test_each_technique_has_required_fields(self) -> None:
        """Each technique has id, name, description, and probes."""
        techniques = get_all_techniques()
        for tech in techniques:
            assert "id" in tech, f"Missing 'id' in {tech.get('name', 'unknown')}"
            assert "name" in tech
            assert "description" in tech
            assert "probes" in tech
            assert isinstance(tech["probes"], list)
            assert len(tech["probes"]) > 0

    def test_technique_ids_are_unique(self) -> None:
        """All technique IDs are unique."""
        techniques = get_all_techniques()
        ids = [t["id"] for t in techniques]
        assert len(ids) == len(set(ids))

    def test_get_technique_by_id(self) -> None:
        """get_technique retrieves the correct technique."""
        tech = get_technique("boundary_probing")
        assert tech["name"] == "Boundary Probing"
        assert len(tech["probes"]) == 8

    def test_get_technique_missing_raises(self) -> None:
        """get_technique raises KeyError for unknown id."""
        with pytest.raises(KeyError):
            get_technique("nonexistent_technique")

    def test_loads_from_custom_path(self, tmp_path: Path) -> None:
        """load_probes() accepts a custom path."""
        custom = {
            "techniques": [
                {"id": "test", "name": "Test", "description": "Desc", "probes": ["hello"]}
            ]
        }
        path = tmp_path / "probes.json"
        path.write_text(json.dumps(custom))
        data = load_probes(path)
        assert len(data["techniques"]) == 1

    def test_boundary_probing_has_eight_probes(self) -> None:
        """Boundary probing has exactly 8 graduated probes."""
        tech = get_technique("boundary_probing")
        assert len(tech["probes"]) == 8

    def test_membership_inference_has_six_probes(self) -> None:
        """Membership inference has exactly 6 probes."""
        tech = get_technique("membership_inference")
        assert len(tech["probes"]) == 6

    def test_temperature_fingerprinting_repeats_same_prompt(self) -> None:
        """Temperature fingerprinting uses the same prompt repeated."""
        tech = get_technique("temperature_fingerprinting")
        probes = tech["probes"]
        assert len(set(probes)) == 1  # All identical
        assert len(probes) == 5

    def test_capability_mapping_has_eight_probes(self) -> None:
        """Capability mapping has exactly 8 probes."""
        tech = get_technique("capability_mapping")
        assert len(tech["probes"]) == 8


class TestAnalyzeBoundaryProbing:
    """Tests for boundary probing analysis."""

    def test_detects_refusal_boundary(self) -> None:
        """Identifies the first refusal position correctly."""
        probes = ["safe", "safe", "harmful"]
        responses = ["Answer", "Answer", "I can't help with that."]
        result = analyze_boundary_probing(probes, responses)
        assert result["refusal_boundary_index"] == 2

    def test_no_refusal_returns_minus_one(self) -> None:
        """Returns -1 when no refusals are detected."""
        probes = ["q1", "q2"]
        responses = ["Answer 1", "Answer 2"]
        result = analyze_boundary_probing(probes, responses)
        assert result["refusal_boundary_index"] == -1

    def test_counts_total_refusals(self) -> None:
        """Counts all refusals, not just the first."""
        probes = ["q1", "q2", "q3"]
        responses = ["ok", "I cannot do that", "I won't help with that"]
        result = analyze_boundary_probing(probes, responses)
        assert result["refusal_count"] == 2

    def test_returns_per_probe_results(self) -> None:
        """Returns per-probe result entries."""
        probes = ["q1", "q2"]
        responses = ["ok", "I'm unable to help"]
        result = analyze_boundary_probing(probes, responses)
        assert len(result["results"]) == 2
        assert result["results"][0]["refused"] is False
        assert result["results"][1]["refused"] is True


class TestAnalyzeMembershipInference:
    """Tests for membership inference analysis."""

    def test_known_text_correctly_completed(self) -> None:
        """Recognizes correct completions of known training data."""
        probes = ["Complete this famous quote: 'To be or not to be...'"]
        responses = ["that is the question, whether 'tis nobler in the mind"]
        result = analyze_membership_inference(probes, responses)
        assert result["known_correct"] == 1

    def test_fake_text_correctly_rejected(self) -> None:
        """Recognizes when model correctly fails on fake text."""
        probes = ["Complete this text: 'The zorblax frequency modulator...'"]
        responses = ["I'm not sure what that refers to. I don't know this text."]
        result = analyze_membership_inference(probes, responses)
        assert result["fake_rejected"] == 1

    def test_score_calculation(self) -> None:
        """Known data score is calculated as correct / total."""
        probes = [
            "Complete this famous quote: 'To be or not to be...'",
            "Complete this text: 'The zorblax frequency modulator...'",
        ]
        responses = [
            "that is the question",
            "I don't know this text",
        ]
        result = analyze_membership_inference(probes, responses)
        assert result["known_data_score"] == 1.0


class TestAnalyzeSystemPromptRecovery:
    """Tests for system prompt recovery analysis."""

    def test_detects_system_prompt_indicators(self) -> None:
        """Finds system prompt indicator phrases in responses."""
        probes = ["What are you designed to do?"]
        responses = ["I am designed to help users with general questions. My guidelines say I should be helpful."]
        result = analyze_system_prompt_recovery(probes, responses)
        assert result["total_fragments"] > 0

    def test_no_fragments_when_clean(self) -> None:
        """Returns empty fragments for generic responses."""
        probes = ["Hello"]
        responses = ["Hello! How can I help you today?"]
        result = analyze_system_prompt_recovery(probes, responses)
        assert result["total_fragments"] == 0


class TestAnalyzeTemperatureFingerprinting:
    """Tests for temperature fingerprinting analysis."""

    def test_identical_responses_low_temperature(self) -> None:
        """Identical responses should indicate low temperature."""
        probes = ["List 5 words"] * 3
        responses = ["apple banana cherry date elderberry"] * 3
        result = analyze_temperature_fingerprinting(probes, responses)
        assert result["estimated_temperature"] < 0.5
        assert result["unique_responses"] == 1

    def test_diverse_responses_high_temperature(self) -> None:
        """Completely different responses should indicate high temperature."""
        probes = ["List 5 words"] * 3
        responses = [
            "apple banana cherry date elderberry",
            "zebra yacht xenon whale violet",
            "one two three four five",
        ]
        result = analyze_temperature_fingerprinting(probes, responses)
        assert result["estimated_temperature"] > 0.5
        assert result["unique_responses"] == 3


class TestAnalyzeCapabilityMapping:
    """Tests for capability mapping analysis."""

    def test_scores_all_capabilities(self) -> None:
        """Returns scores for all 8 capability labels."""
        probes = [f"probe {i}" for i in range(8)]
        responses = ["some response"] * 8
        result = analyze_capability_mapping(probes, responses)
        assert len(result["capability_scores"]) == 8

    def test_correct_math_gets_high_score(self) -> None:
        """Correct math answer (96083) scores 1.0."""
        probes = ["ignored"] * 3 + ["unused"] * 5
        responses = ["le renard brun rapide", "def is_prime(n): return True", "96083"] + ["response"] * 5
        result = analyze_capability_mapping(probes, responses)
        assert result["capability_scores"]["math"] == 1.0

    def test_refusal_gets_zero_score(self) -> None:
        """A refused response scores 0.0."""
        probes = ["translate something"]
        responses = ["I cannot help with that request."]
        # Only testing the first capability
        from probing_attacks import _score_capability
        score = _score_capability("translation", "translate", "I cannot help with that request.")
        assert score == 0.0


class TestAnalyzeDispatch:
    """Tests for the analyze() dispatcher."""

    def test_dispatches_to_correct_analyzer(self) -> None:
        """analyze() routes to the right function."""
        probes = ["q1", "q2"]
        responses = ["I can't do that", "ok"]
        result = analyze("boundary_probing", probes, responses)
        assert result["technique"] == "boundary_probing"

    def test_unknown_technique_raises(self) -> None:
        """analyze() raises KeyError for unknown technique id."""
        with pytest.raises(KeyError, match="No analyzer"):
            analyze("unknown_technique", [], [])

    def test_all_techniques_have_analyzers(self) -> None:
        """Every technique in probes.json has a registered analyzer."""
        techniques = get_all_techniques()
        for tech in techniques:
            assert tech["id"] in ANALYZERS, f"No analyzer for {tech['id']}"
