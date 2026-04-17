"""Integration tests for Demo Hub Azure blueprints.

Verifies all Azure demo blueprints register and serve index pages,
and tests graceful degradation when Azure credentials are missing.
"""

import os
import sys
from pathlib import Path

import pytest

flask = pytest.importorskip("flask", reason="Flask not installed — run in demo-hub conda env")

_project_root = Path(__file__).resolve().parents[2]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# Add demo-hub to path
_hub_dir = _project_root / "demo-hub"
if str(_hub_dir) not in sys.path:
    sys.path.insert(0, str(_hub_dir))


@pytest.fixture
def app():
    """Create a test Flask app."""
    from app import create_app
    test_app = create_app()
    test_app.config["TESTING"] = True
    return test_app


@pytest.fixture
def client(app):
    """Provide a Flask test client."""
    return app.test_client()


class TestAzureBlueprintRegistration:
    """Test that all Azure demo blueprints are registered."""

    @pytest.mark.parametrize("demo_id", range(19, 31))
    def test_azure_demo_registered(self, client, demo_id: int) -> None:
        """Each Azure demo should have a registered route."""
        response = client.get(f"/demo-{demo_id}/")
        assert response.status_code == 200, f"Demo {demo_id} returned {response.status_code}"

    @pytest.mark.parametrize("demo_id", range(19, 31))
    def test_azure_demo_status_endpoint(self, client, demo_id: int) -> None:
        """Each Azure demo should have a status API endpoint."""
        response = client.get(f"/demo-{demo_id}/api/status")
        assert response.status_code == 200
        data = response.get_json()
        assert "configured" in data


class TestTelemetryPanel:
    """Test the OTel telemetry panel."""

    def test_telemetry_status_endpoint(self, client) -> None:
        """Telemetry status endpoint should return config info."""
        response = client.get("/api/telemetry/status")
        assert response.status_code == 200
        data = response.get_json()
        assert "enabled" in data
        assert "service_name" in data

    def test_telemetry_health_endpoint(self, client) -> None:
        """Telemetry health endpoint should return reachability."""
        response = client.get("/api/telemetry/health")
        assert response.status_code == 200
        data = response.get_json()
        assert "reachable" in data


class TestGracefulDegradation:
    """Test that Demo Hub works without Azure credentials."""

    def test_hub_index_loads(self, client) -> None:
        """Landing page should load without Azure credentials."""
        response = client.get("/")
        assert response.status_code == 200

    def test_azure_demos_show_setup_notice(self, client) -> None:
        """Azure demos should show setup notice when not configured."""
        # Ensure no Azure env vars
        os.environ.pop("AZURE_CONTENT_SAFETY_ENDPOINT", None)
        response = client.get("/demo-19/api/status")
        data = response.get_json()
        assert data["configured"] is False
