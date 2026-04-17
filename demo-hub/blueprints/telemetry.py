"""Telemetry blueprint — OTel status and health endpoints."""

import os
from urllib.parse import urlparse

from flask import Blueprint, jsonify

bp = Blueprint("telemetry", __name__, url_prefix="/api/telemetry")


@bp.route("/status")
def status():
    """Return current OTel configuration status as JSON."""
    enabled_raw = os.environ.get("OTEL_ENABLED", "false")
    enabled = enabled_raw.lower() in ("true", "1", "yes")

    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    service_name = os.environ.get("OTEL_SERVICE_NAME", "demo-hub")
    protocol = os.environ.get("OTEL_EXPORTER_OTLP_PROTOCOL", "grpc")

    # Build display-friendly endpoint values
    endpoint_base = ""
    endpoint_display = ""
    if endpoint:
        parsed = urlparse(endpoint)
        endpoint_base = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme else endpoint
        # Shorten long endpoints for display
        if len(endpoint) > 40:
            endpoint_display = endpoint[:37] + "..."
        else:
            endpoint_display = endpoint

    return jsonify({
        "enabled": enabled,
        "endpoint": endpoint,
        "endpoint_base": endpoint_base,
        "endpoint_display": endpoint_display,
        "service_name": service_name,
        "protocol": protocol,
    })


@bp.route("/health")
def health():
    """Test connectivity to the OTel endpoint."""
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    if not endpoint:
        return jsonify({"reachable": False, "reason": "no endpoint configured"})

    try:
        import urllib.request
        parsed = urlparse(endpoint)
        base = f"{parsed.scheme}://{parsed.netloc}"
        req = urllib.request.Request(base, method="HEAD")
        urllib.request.urlopen(req, timeout=3)
        return jsonify({"reachable": True})
    except Exception as exc:
        return jsonify({"reachable": False, "reason": str(exc)})
