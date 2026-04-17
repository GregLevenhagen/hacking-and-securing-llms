"""Tests for attacks/payloads.json — verifies payload structure and content."""

import json
from pathlib import Path

PAYLOADS_PATH = Path(__file__).resolve().parents[2] / "attacks" / "payloads.json"


def _load_payloads() -> list[dict[str, str]]:
    with open(PAYLOADS_PATH) as f:
        return json.load(f)


class TestPayloadsFile:
    def test_file_exists(self) -> None:
        assert PAYLOADS_PATH.exists()

    def test_loads_as_valid_json_list(self) -> None:
        payloads = _load_payloads()
        assert isinstance(payloads, list)

    def test_payload_count_at_least_10(self) -> None:
        payloads = _load_payloads()
        assert len(payloads) >= 10


class TestPayloadStructure:
    def test_each_payload_has_required_keys(self) -> None:
        for p in _load_payloads():
            assert isinstance(p, dict)
            assert "name" in p
            assert "payload" in p

    def test_each_name_is_nonempty_string(self) -> None:
        for p in _load_payloads():
            assert isinstance(p["name"], str)
            assert len(p["name"].strip()) > 0

    def test_each_payload_is_nonempty_string(self) -> None:
        for p in _load_payloads():
            assert isinstance(p["payload"], str)
            assert len(p["payload"].strip()) > 0

    def test_names_are_unique(self) -> None:
        names = [p["name"] for p in _load_payloads()]
        assert len(names) == len(set(names))
