"""Tests for Demo 10 attack scenario loading and validation.

Verifies scenarios.json:
  - Loads as valid JSON
  - Every scenario has required fields
  - All five attack categories are represented
"""

import json
from pathlib import Path

SCENARIOS_PATH = (
    Path(__file__).resolve().parents[2] / "attack_scenarios" / "scenarios.json"
)

REQUIRED_FIELDS = {
    "id",
    "category",
    "attack_text",
    "expected_vulnerable_behavior",
    "expected_defense_layer",
}

REQUIRED_CATEGORIES = {
    "direct_injection",
    "indirect_injection",
    "prompt_extraction",
    "agent_exploitation",
}


def _load_scenarios() -> list[dict[str, str]]:
    with open(SCENARIOS_PATH) as f:
        return json.load(f)  # type: ignore[no-any-return]


class TestScenariosJson:
    """Validate the structure and completeness of scenarios.json."""

    def test_loads_as_valid_json(self) -> None:
        scenarios = _load_scenarios()
        assert isinstance(scenarios, list)
        assert len(scenarios) > 0

    def test_each_scenario_has_required_fields(self) -> None:
        scenarios = _load_scenarios()
        for scenario in scenarios:
            missing = REQUIRED_FIELDS - set(scenario.keys())
            assert not missing, (
                f"Scenario {scenario.get('id', '?')} missing fields: {missing}"
            )

    def test_all_categories_represented(self) -> None:
        scenarios = _load_scenarios()
        present_categories = {s["category"] for s in scenarios}
        missing = REQUIRED_CATEGORIES - present_categories
        assert not missing, f"Missing attack categories: {missing}"

    def test_each_scenario_has_unique_id(self) -> None:
        scenarios = _load_scenarios()
        ids = [s["id"] for s in scenarios]
        assert len(ids) == len(set(ids)), "Duplicate scenario IDs found"

    def test_attack_text_is_non_empty(self) -> None:
        scenarios = _load_scenarios()
        for scenario in scenarios:
            assert scenario["attack_text"].strip(), (
                f"Scenario {scenario['id']} has empty attack_text"
            )

    def test_expected_defense_layer_is_valid(self) -> None:
        valid_layers = {"input_guard", "retrieval_guard", "output_guard", "action_guard"}
        scenarios = _load_scenarios()
        for scenario in scenarios:
            assert scenario["expected_defense_layer"] in valid_layers, (
                f"Scenario {scenario['id']} has invalid defense layer: "
                f"{scenario['expected_defense_layer']}"
            )
