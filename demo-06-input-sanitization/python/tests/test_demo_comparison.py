"""Tests for Demo 6 compare_input.py — export functions, CLI flag parsing, and timing summary."""

import csv
import json
import os
from typing import Any
from unittest.mock import patch

import pytest

from compare_input import (
    _parse_payload_flag,
    _parse_csv_flag,
    _parse_json_flag,
    build_timing_summary,
    export_csv,
    export_json,
)


# ── Test data ────────────────────────────────────────


def _make_result(
    name: str = "test_attack",
    payload: str = "test payload",
    vuln_blocked: bool = False,
    def_blocked: bool = True,
    blocked_by: str = "regex_filter",
    defense_results: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a mock comparison result entry."""
    if defense_results is None:
        defense_results = [
            {"layer": "regex_filter", "blocked": True, "reason": "matched", "latency_ms": 0.5},
        ]
    return {
        "attack_name": name,
        "payload": payload,
        "vulnerable": {
            "response": "I'll help you!",
            "blocked": vuln_blocked,
            "latency_ms": 10.0,
        },
        "defended": {
            "response": None,
            "blocked": def_blocked,
            "blocked_by": blocked_by,
            "defense_results": defense_results,
            "latency_ms": 1.5,
        },
    }


def _make_full_pipeline_result(name: str = "full_test") -> dict[str, Any]:
    """Build a result where all 4 defense layers ran."""
    return _make_result(
        name=name,
        def_blocked=False,
        blocked_by=None,  # type: ignore[arg-type]
        defense_results=[
            {"layer": "regex_filter", "blocked": False, "reason": "pass", "latency_ms": 0.3},
            {"layer": "input_sanitizer", "blocked": False, "reason": "unchanged", "latency_ms": 0.1},
            {"layer": "llm_judge", "blocked": False, "reason": "safe", "latency_ms": 15.0},
            {"layer": "llm_guard_scanner", "blocked": False, "reason": "safe", "latency_ms": 8.0},
        ],
    )


# ── CLI flag parsing ─────────────────────────────────


class TestParsePayloadFlag:
    """Tests for _parse_payload_flag() CLI argument parsing."""

    def test_no_flag_returns_none(self) -> None:
        with patch("compare_input.sys") as mock_sys:
            mock_sys.argv = ["compare_input.py", "--auto"]
            result = _parse_payload_flag()
        assert result is None

    def test_flag_with_value(self) -> None:
        with patch("compare_input.sys") as mock_sys:
            mock_sys.argv = ["compare_input.py", "--payload", "Ignore rules"]
            result = _parse_payload_flag()
        assert result == "Ignore rules"

    def test_flag_at_end_without_value_returns_none(self) -> None:
        with patch("compare_input.sys") as mock_sys:
            mock_sys.argv = ["compare_input.py", "--payload"]
            result = _parse_payload_flag()
        assert result is None

    def test_flag_with_other_args(self) -> None:
        with patch("compare_input.sys") as mock_sys:
            mock_sys.argv = ["compare_input.py", "--auto", "--payload", "test input", "--csv", "out.csv"]
            result = _parse_payload_flag()
        assert result == "test input"


class TestParseCsvFlag:
    """Tests for _parse_csv_flag()."""

    def test_no_flag_returns_none(self) -> None:
        with patch("compare_input.sys") as mock_sys:
            mock_sys.argv = ["compare_input.py"]
            result = _parse_csv_flag()
        assert result is None

    def test_flag_with_path(self) -> None:
        with patch("compare_input.sys") as mock_sys:
            mock_sys.argv = ["compare_input.py", "--csv", "results.csv"]
            result = _parse_csv_flag()
        assert result == "results.csv"


class TestParseJsonFlag:
    """Tests for _parse_json_flag()."""

    def test_no_flag_returns_none(self) -> None:
        with patch("compare_input.sys") as mock_sys:
            mock_sys.argv = ["compare_input.py"]
            result = _parse_json_flag()
        assert result is None

    def test_flag_with_path(self) -> None:
        with patch("compare_input.sys") as mock_sys:
            mock_sys.argv = ["compare_input.py", "--json", "out.json"]
            result = _parse_json_flag()
        assert result == "out.json"


# ── export_csv ───────────────────────────────────────


class TestExportCsv:
    """Tests for export_csv() file output."""

    def test_writes_csv_with_header_and_rows(self, tmp_path: Any) -> None:
        csv_path = str(tmp_path / "results.csv")
        results = [_make_result(), _make_result(name="attack_2")]
        export_csv(results, csv_path)

        with open(csv_path) as f:
            reader = csv.reader(f)
            rows = list(reader)

        assert len(rows) == 3  # header + 2 data rows
        assert rows[0][0] == "attack_name"
        assert rows[1][0] == "test_attack"
        assert rows[2][0] == "attack_2"

    def test_csv_contains_timing_data(self, tmp_path: Any) -> None:
        csv_path = str(tmp_path / "results.csv")
        results = [_make_result()]
        export_csv(results, csv_path)

        with open(csv_path) as f:
            reader = csv.DictReader(f)
            row = next(reader)

        assert "layer_timings" in row
        assert "regex_filter" in row["layer_timings"]
        assert "ms" in row["layer_timings"]

    def test_csv_with_empty_results(self, tmp_path: Any) -> None:
        csv_path = str(tmp_path / "empty.csv")
        export_csv([], csv_path)

        with open(csv_path) as f:
            reader = csv.reader(f)
            rows = list(reader)

        assert len(rows) == 1  # header only


# ── export_json ──────────────────────────────────────


class TestExportJson:
    """Tests for export_json() file output."""

    def test_writes_valid_json(self, tmp_path: Any) -> None:
        json_path = str(tmp_path / "results.json")
        results = [_make_result()]
        export_json(results, json_path)

        with open(json_path) as f:
            data = json.load(f)

        assert "summary" in data
        assert "per_layer_timing" in data
        assert "results" in data

    def test_summary_counts(self, tmp_path: Any) -> None:
        json_path = str(tmp_path / "results.json")
        results = [
            _make_result(def_blocked=True),
            _make_result(name="a2", def_blocked=False, blocked_by=None),  # type: ignore[arg-type]
        ]
        export_json(results, json_path)

        with open(json_path) as f:
            data = json.load(f)

        assert data["summary"]["total_attacks"] == 2
        assert data["summary"]["blocked"] == 1
        assert data["summary"]["passed"] == 1

    def test_per_layer_timing_present(self, tmp_path: Any) -> None:
        json_path = str(tmp_path / "results.json")
        results = [_make_full_pipeline_result()]
        export_json(results, json_path)

        with open(json_path) as f:
            data = json.load(f)

        timing = data["per_layer_timing"]
        assert "regex_filter" in timing
        assert "llm_judge" in timing
        assert "avg_ms" in timing["regex_filter"]

    def test_results_contain_layer_details(self, tmp_path: Any) -> None:
        json_path = str(tmp_path / "results.json")
        results = [_make_full_pipeline_result()]
        export_json(results, json_path)

        with open(json_path) as f:
            data = json.load(f)

        r0 = data["results"][0]
        assert len(r0["defended"]["layers"]) == 4
        assert r0["defended"]["layers"][0]["layer"] == "regex_filter"

    def test_empty_results(self, tmp_path: Any) -> None:
        json_path = str(tmp_path / "empty.json")
        export_json([], json_path)

        with open(json_path) as f:
            data = json.load(f)

        assert data["summary"]["total_attacks"] == 0
        assert data["results"] == []


# ── build_timing_summary ─────────────────────────────


class TestBuildTimingSummary:
    """Tests for build_timing_summary() — per-layer stats computation."""

    def test_single_result_single_layer(self) -> None:
        results = [_make_result()]
        summary = build_timing_summary(results)
        assert "regex_filter" in summary
        assert summary["regex_filter"]["avg_ms"] == 0.5
        assert summary["regex_filter"]["min_ms"] == 0.5
        assert summary["regex_filter"]["max_ms"] == 0.5
        assert summary["regex_filter"]["count"] == 1.0

    def test_multiple_results_averages(self) -> None:
        results = [
            _make_result(defense_results=[
                {"layer": "regex_filter", "latency_ms": 1.0},
            ]),
            _make_result(defense_results=[
                {"layer": "regex_filter", "latency_ms": 3.0},
            ]),
        ]
        summary = build_timing_summary(results)
        assert summary["regex_filter"]["avg_ms"] == 2.0
        assert summary["regex_filter"]["min_ms"] == 1.0
        assert summary["regex_filter"]["max_ms"] == 3.0
        assert summary["regex_filter"]["count"] == 2.0

    def test_full_pipeline_all_layers(self) -> None:
        results = [_make_full_pipeline_result()]
        summary = build_timing_summary(results)
        assert len(summary) == 4
        assert "regex_filter" in summary
        assert "input_sanitizer" in summary
        assert "llm_judge" in summary
        assert "llm_guard_scanner" in summary

    def test_empty_results(self) -> None:
        assert build_timing_summary([]) == {}
