"""Test fixtures for Demo 10 — imports shared mock fixtures and adds demo-specific paths."""

import sys
from pathlib import Path

# Ensure project root is on sys.path for shared imports
_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# Ensure demo python dir is on sys.path for local imports
_demo_python = Path(__file__).resolve().parents[1]
if str(_demo_python) not in sys.path:
    sys.path.insert(0, str(_demo_python))

# Ensure Demo 5 python dir is on sys.path for tools/mock_services
_demo5_python = _project_root / "demo-05-agent-exploitation" / "python"
if str(_demo5_python) not in sys.path:
    sys.path.insert(0, str(_demo5_python))

# Ensure Demo 6 input_defenses on sys.path (for input_guard's imports)
_demo6_defenses = _project_root / "demo-06-input-sanitization" / "python" / "input_defenses"
if str(_demo6_defenses) not in sys.path:
    sys.path.insert(0, str(_demo6_defenses))

# Ensure Demo 7 retrieval_defenses on sys.path (for retrieval_guard's imports)
_demo7_defenses = _project_root / "demo-07-rag-defense" / "python" / "retrieval_defenses"
if str(_demo7_defenses) not in sys.path:
    sys.path.insert(0, str(_demo7_defenses))

# Ensure Demo 8 validators on sys.path (for output_guard's imports)
_demo8_validators = _project_root / "demo-08-output-validation" / "python" / "validators"
if str(_demo8_validators) not in sys.path:
    sys.path.insert(0, str(_demo8_validators))

# Ensure Demo 9 python dir on sys.path (for action_guard's imports)
_demo9_python = _project_root / "demo-09-approval-gates" / "python"
if str(_demo9_python) not in sys.path:
    sys.path.insert(0, str(_demo9_python))

# Re-export shared fixtures so they're available in this test suite
from shared.python.testing.conftest import mock_client, mock_config, tmp_env  # noqa: F401, E402
