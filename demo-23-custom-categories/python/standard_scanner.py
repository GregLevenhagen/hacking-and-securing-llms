"""Standard API custom category scanner.

Trains a custom category using example texts (requires training data)
and scans content against it. More accurate but requires setup time.
"""

import json
import sys
from pathlib import Path
from typing import Any

_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root))


class StandardScanner:
    """Scans content using trained custom categories (Standard API)."""

    def __init__(self, safety_client: Any = None) -> None:
        self.safety_client = safety_client

    def load_category(self, category_path: str) -> dict[str, Any]:
        """Load a category definition from JSON file."""
        with open(category_path) as f:
            return json.load(f)

    def scan(
        self,
        text: str,
        category_name: str,
        confidence_threshold: float = 0.0,
    ) -> dict[str, Any]:
        """Scan text against a custom category.

        Args:
            text: Content to scan.
            category_name: Custom category to check against.
            confidence_threshold: Minimum confidence to count as detected.
                A detection with confidence below this value is reported but
                ``detected`` is set to ``False``.

        Returns:
            Dict with ``detected`` (bool), ``confidence`` (float),
            ``category`` (str), and ``above_threshold`` (bool).
        """
        if not self.safety_client:
            return {
                "detected": False,
                "confidence": 0.0,
                "category": category_name,
                "above_threshold": False,
            }

        result = self.safety_client.analyze_custom_category(
            text=text,
            category_name=category_name,
        )
        raw_detected = result.get("detected", False)
        confidence = result.get("confidence", 0.0)
        above_threshold = raw_detected and confidence >= confidence_threshold
        return {
            "detected": above_threshold,
            "confidence": confidence,
            "category": category_name,
            "above_threshold": above_threshold,
            "raw_detected": raw_detected,
        }

    def scan_batch(
        self,
        texts: list[str],
        category_name: str,
        confidence_threshold: float = 0.0,
    ) -> list[dict[str, Any]]:
        """Scan multiple texts against a category, returning results for each."""
        return [
            self.scan(text, category_name, confidence_threshold=confidence_threshold)
            for text in texts
        ]
