"""Tests for the telemetry blueprint — OTel status and health endpoints."""

import os
from unittest.mock import patch

from flask.testing import FlaskClient


class TestTelemetryStatus:
    """Test GET /api/telemetry/status endpoint."""

    def test_status_returns_200(self, client: FlaskClient) -> None:
        response = client.get("/api/telemetry/status")
        assert response.status_code == 200

    def test_status_returns_json_with_required_keys(self, client: FlaskClient) -> None:
        response = client.get("/api/telemetry/status")
        data = response.get_json()
        assert "enabled" in data
        assert "endpoint" in data
        assert "endpoint_base" in data
        assert "endpoint_display" in data
        assert "service_name" in data
        assert "protocol" in data

    def test_status_disabled_by_default(self, client: FlaskClient) -> None:
        response = client.get("/api/telemetry/status")
        data = response.get_json()
        assert data["enabled"] is False

    def test_status_enabled_when_env_set(self, client: FlaskClient) -> None:
        with patch.dict(os.environ, {"OTEL_ENABLED": "true"}):
            response = client.get("/api/telemetry/status")
            data = response.get_json()
            assert data["enabled"] is True

    def test_status_reads_service_name(self, client: FlaskClient) -> None:
        with patch.dict(os.environ, {"OTEL_SERVICE_NAME": "test-svc"}):
            response = client.get("/api/telemetry/status")
            data = response.get_json()
            assert data["service_name"] == "test-svc"

    def test_status_default_service_name(self, client: FlaskClient) -> None:
        response = client.get("/api/telemetry/status")
        data = response.get_json()
        assert data["service_name"] == "demo-hub"

    def test_status_reads_protocol(self, client: FlaskClient) -> None:
        with patch.dict(os.environ, {"OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf"}):
            response = client.get("/api/telemetry/status")
            data = response.get_json()
            assert data["protocol"] == "http/protobuf"

    def test_status_default_protocol(self, client: FlaskClient) -> None:
        response = client.get("/api/telemetry/status")
        data = response.get_json()
        assert data["protocol"] == "grpc"

    def test_status_endpoint_parsing(self, client: FlaskClient) -> None:
        with patch.dict(os.environ, {"OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4317"}):
            response = client.get("/api/telemetry/status")
            data = response.get_json()
            assert data["endpoint"] == "http://localhost:4317"
            assert data["endpoint_base"] == "http://localhost:4317"
            assert data["endpoint_display"] == "http://localhost:4317"

    def test_status_long_endpoint_is_truncated(self, client: FlaskClient) -> None:
        long_url = "https://otel-collector.very-long-domain-name.example.com:4317/v1/traces"
        with patch.dict(os.environ, {"OTEL_EXPORTER_OTLP_ENDPOINT": long_url}):
            response = client.get("/api/telemetry/status")
            data = response.get_json()
            assert data["endpoint_display"].endswith("...")
            assert len(data["endpoint_display"]) == 40

    def test_status_empty_endpoint(self, client: FlaskClient) -> None:
        response = client.get("/api/telemetry/status")
        data = response.get_json()
        assert data["endpoint"] == ""
        assert data["endpoint_base"] == ""
        assert data["endpoint_display"] == ""


class TestTelemetryHealth:
    """Test GET /api/telemetry/health endpoint."""

    def test_health_returns_200(self, client: FlaskClient) -> None:
        response = client.get("/api/telemetry/health")
        assert response.status_code == 200

    def test_health_unreachable_when_no_endpoint(self, client: FlaskClient) -> None:
        response = client.get("/api/telemetry/health")
        data = response.get_json()
        assert data["reachable"] is False

    def test_health_returns_json_with_reachable_key(self, client: FlaskClient) -> None:
        response = client.get("/api/telemetry/health")
        data = response.get_json()
        assert "reachable" in data


class TestTelemetryPanelInSidebar:
    """Test that the telemetry panel is included in the sidebar."""

    def test_telemetry_panel_in_demo_page(self, client: FlaskClient) -> None:
        response = client.get("/demo-01/")
        html = response.data.decode()
        assert "telemetry-panel" in html
        assert "otel-status-dot" in html

    def test_telemetry_panel_has_fetch_script(self, client: FlaskClient) -> None:
        response = client.get("/demo-01/")
        html = response.data.decode()
        assert "/api/telemetry/status" in html
        assert "toggleTelemetry" in html
