"""Test fixtures for Demo 8 — imports shared mock fixtures and adds demo-specific ones."""

import sys
from pathlib import Path

# Ensure project root is on sys.path for shared imports
_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# Ensure demo python dir is on sys.path for local imports (validators)
_demo_python = Path(__file__).resolve().parents[1]
if str(_demo_python) not in sys.path:
    sys.path.insert(0, str(_demo_python))

# Re-export shared fixtures so they're available in this test suite
from shared.python.testing.conftest import mock_client, mock_config, tmp_env  # noqa: F401, E402
