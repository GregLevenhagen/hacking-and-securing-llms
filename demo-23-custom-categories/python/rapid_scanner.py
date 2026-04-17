"""Rapid API custom category scanner.

Defines categories via natural language description (no training data needed)
and scans content against them. Faster to set up but may be less precise.
"""

import json
import sys
from pathlib import Path
from typing import Any

_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root))


class RapidScanner:
    """Scans content using zero-shot custom categories (Rapid API)."""

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
    ) -> dict[str, Any]:
        """Scan text against a category defined by description (no training).

        Returns:
            Dict with 'detected' (bool), 'confidence' (float), 'category' (str).
        """
        if not self.safety_client:
            return {"detected": False, "confidence": 0.0, "category": category_name}

        result = self.safety_client.analyze_custom_category(
            text=text,
            category_name=category_name,
        )
        return {
            "detected": result.get("detected", False),
            "confidence": result.get("confidence", 0.0),
            "category": category_name,
        }
