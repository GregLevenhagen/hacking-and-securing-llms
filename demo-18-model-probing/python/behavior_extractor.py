"""Behavior profile extraction for Demo 18 — Model Probing.

Aggregates analysis results from all probing techniques into a unified
BehaviorProfile that summarizes the model's safety boundaries, training
data indicators, system prompt leaks, temperature estimate, and
capability scores.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class BehaviorProfile:
    """Aggregated behavior profile extracted from model probing.

    Attributes:
        refusal_boundary_index: Index in the boundary probe sequence where
            the model first refused (0-based). -1 if no refusal was detected.
        known_data_score: Fraction (0.0-1.0) of known training data items
            the model successfully completed.
        system_prompt_fragments: Sentences recovered that reveal system
            instructions or guidelines.
        temperature_estimate: Estimated temperature setting based on
            response variance. 0.0 = fully deterministic, 2.0 = maximum.
        capability_scores: Per-capability scores (0.0-1.0) across tested
            skill areas.
    """

    refusal_boundary_index: int = -1
    known_data_score: float = 0.0
    system_prompt_fragments: list[str] = field(default_factory=list)
    temperature_estimate: float = 0.0
    capability_scores: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the profile to a JSON-compatible dict."""
        return {
            "refusal_boundary_index": self.refusal_boundary_index,
            "known_data_score": self.known_data_score,
            "system_prompt_fragments": self.system_prompt_fragments,
            "temperature_estimate": self.temperature_estimate,
            "capability_scores": self.capability_scores,
            "summary": self.summary(),
        }

    def summary(self) -> str:
        """Generate a human-readable summary of the behavior profile."""
        lines = []

        # Boundary analysis
        if self.refusal_boundary_index == -1:
            lines.append("Safety boundary: No refusals detected (model answered all probes)")
        elif self.refusal_boundary_index == 0:
            lines.append("Safety boundary: Very strict (refuses even innocent queries)")
        elif self.refusal_boundary_index <= 2:
            lines.append(f"Safety boundary: Strict (first refusal at probe {self.refusal_boundary_index})")
        elif self.refusal_boundary_index <= 4:
            lines.append(f"Safety boundary: Moderate (first refusal at probe {self.refusal_boundary_index})")
        else:
            lines.append(f"Safety boundary: Permissive (first refusal at probe {self.refusal_boundary_index})")

        # Training data
        if self.known_data_score >= 0.8:
            lines.append(f"Training data: Strong indicators ({self.known_data_score:.0%} known text completed)")
        elif self.known_data_score >= 0.5:
            lines.append(f"Training data: Moderate indicators ({self.known_data_score:.0%} known text completed)")
        else:
            lines.append(f"Training data: Weak indicators ({self.known_data_score:.0%} known text completed)")

        # System prompt
        frag_count = len(self.system_prompt_fragments)
        if frag_count == 0:
            lines.append("System prompt: No fragments recovered")
        else:
            lines.append(f"System prompt: {frag_count} fragment(s) recovered")

        # Temperature
        if self.temperature_estimate < 0.3:
            lines.append(f"Temperature: ~{self.temperature_estimate:.2f} (near-deterministic)")
        elif self.temperature_estimate < 0.8:
            lines.append(f"Temperature: ~{self.temperature_estimate:.2f} (moderate randomness)")
        else:
            lines.append(f"Temperature: ~{self.temperature_estimate:.2f} (high randomness)")

        # Capabilities
        if self.capability_scores:
            avg = sum(self.capability_scores.values()) / len(self.capability_scores)
            best = max(self.capability_scores, key=lambda k: self.capability_scores[k])
            worst = min(self.capability_scores, key=lambda k: self.capability_scores[k])
            lines.append(
                f"Capabilities: avg {avg:.0%}, "
                f"best={best} ({self.capability_scores[best]:.0%}), "
                f"worst={worst} ({self.capability_scores[worst]:.0%})"
            )

        return "\n".join(lines)


def extract_boundary_info(analysis: dict[str, Any]) -> dict[str, Any]:
    """Extract boundary probing information from analysis results.

    Returns:
        Dict with refusal_boundary_index and refusal_count.
    """
    return {
        "refusal_boundary_index": analysis.get("refusal_boundary_index", -1),
        "refusal_count": analysis.get("refusal_count", 0),
        "total_probes": analysis.get("total_probes", 0),
    }


def extract_membership_info(analysis: dict[str, Any]) -> dict[str, Any]:
    """Extract membership inference information from analysis results.

    Returns:
        Dict with known_data_score and detail counts.
    """
    return {
        "known_data_score": analysis.get("known_data_score", 0.0),
        "known_correct": analysis.get("known_correct", 0),
        "known_total": analysis.get("known_total", 0),
        "fake_rejected": analysis.get("fake_rejected", 0),
        "fake_total": analysis.get("fake_total", 0),
    }


def extract_system_prompt_info(analysis: dict[str, Any]) -> dict[str, Any]:
    """Extract system prompt recovery information from analysis results.

    Returns:
        Dict with recovered fragments list and disclosure score.
    """
    return {
        "fragments": analysis.get("fragments", []),
        "disclosure_score": analysis.get("disclosure_score", 0.0),
        "total_fragments": analysis.get("total_fragments", 0),
    }


def extract_temperature_info(analysis: dict[str, Any]) -> dict[str, Any]:
    """Extract temperature fingerprinting information from analysis results.

    Returns:
        Dict with estimated_temperature and similarity metrics.
    """
    return {
        "estimated_temperature": analysis.get("estimated_temperature", 0.0),
        "average_similarity": analysis.get("average_similarity", 0.0),
        "unique_responses": analysis.get("unique_responses", 0),
        "total_responses": analysis.get("total_responses", 0),
    }


def extract_capability_info(analysis: dict[str, Any]) -> dict[str, Any]:
    """Extract capability mapping information from analysis results.

    Returns:
        Dict with capability_scores and average_score.
    """
    return {
        "capability_scores": analysis.get("capability_scores", {}),
        "average_score": analysis.get("average_score", 0.0),
    }


def build_profile(all_results: dict[str, dict[str, Any]]) -> BehaviorProfile:
    """Build a unified BehaviorProfile from analysis results of all techniques.

    Args:
        all_results: Dict mapping technique_id -> analysis result dict.
            Keys should match technique ids from probes.json.

    Returns:
        A fully populated BehaviorProfile.
    """
    profile = BehaviorProfile()

    # Boundary probing
    if "boundary_probing" in all_results:
        boundary = all_results["boundary_probing"]
        profile.refusal_boundary_index = boundary.get("refusal_boundary_index", -1)

    # Membership inference
    if "membership_inference" in all_results:
        membership = all_results["membership_inference"]
        profile.known_data_score = membership.get("known_data_score", 0.0)

    # System prompt recovery
    if "system_prompt_recovery" in all_results:
        sysinfo = all_results["system_prompt_recovery"]
        profile.system_prompt_fragments = sysinfo.get("fragments", [])

    # Temperature fingerprinting
    if "temperature_fingerprinting" in all_results:
        temp = all_results["temperature_fingerprinting"]
        profile.temperature_estimate = temp.get("estimated_temperature", 0.0)

    # Capability mapping
    if "capability_mapping" in all_results:
        caps = all_results["capability_mapping"]
        profile.capability_scores = caps.get("capability_scores", {})

    return profile
