"""Test fixtures for Demo Hub."""

import sys
from pathlib import Path

import pytest
from flask import Flask
from flask.testing import FlaskClient

# Ensure demo-hub root is on sys.path for app imports
_hub_root = Path(__file__).resolve().parents[1]
if str(_hub_root) not in sys.path:
    sys.path.insert(0, str(_hub_root))

# Ensure project root on sys.path for shared imports
_project_root = _hub_root.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


@pytest.fixture
def app() -> Flask:
    """Create a test Flask app instance."""
    from app import create_app
    test_app = create_app()
    test_app.config["TESTING"] = True
    return test_app


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    """Create a Flask test client."""
    return app.test_client()
