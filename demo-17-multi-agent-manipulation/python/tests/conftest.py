"""Pytest configuration for Demo 17 tests."""

import sys
from pathlib import Path

# Add demo-17 python directory to sys.path for imports
_demo17_python = Path(__file__).resolve().parents[1]
if str(_demo17_python) not in sys.path:
    sys.path.insert(0, str(_demo17_python))

# Add project root for shared imports
_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))
