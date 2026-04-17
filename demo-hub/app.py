"""Demo Hub — Flask app factory.

Single entry point for all LLM security demos.
Serves a sidebar-navigated web interface with hacker aesthetic.

Usage:
    python app.py              # run on localhost:2600
    python app.py --port 8000  # custom port
"""

import logging
import sys
from pathlib import Path

from flask import Flask, request
from jinja2 import ChoiceLoader, FileSystemLoader

# Ensure project root on sys.path for shared imports
_project_root = Path(__file__).resolve().parents[1]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from blueprints import DEMO_MANIFEST, get_attacks, get_defenses, get_advanced, get_azure  # noqa: E402
from shared.python.ollama_client import OllamaClient  # noqa: E402

# OTel telemetry (no-op when OTEL_ENABLED=false or packages missing)
_hub_logger: logging.Logger | None = None
try:
    from shared.python.telemetry import init_telemetry, get_tracer
    init_telemetry()
    _tracer = get_tracer("demo-hub")
    # Route app logs (with trace/span IDs) to a separate file.
    # Flask request logs stay in the console; this captures app-level logs
    # correlated with trace/span IDs for cross-referencing with otel-traces.log.
    _app_log = str(_project_root / "otel-app.log")
    # Use a plain file handler — trace/span IDs are embedded in the
    # log message by otel_helpers.span_set_result() since it runs in
    # background threads where OTel contextvars aren't propagated.
    _hub_logger = logging.getLogger("demo-hub")
    _fh = logging.FileHandler(_app_log, mode="a")
    _fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)-8s %(message)s"))
    _fh.setLevel(logging.INFO)
    _hub_logger.addHandler(_fh)
    _hub_logger.setLevel(logging.DEBUG)
    _hub_logger.propagate = False  # don't duplicate to console
except Exception:
    _tracer = None


def create_app() -> Flask:
    """Flask application factory."""
    _hub_templates = str(Path(__file__).resolve().parent / "templates")
    _shared_templates = str(_project_root / "shared" / "templates")

    app = Flask(
        __name__,
        static_folder=_shared_templates,
        static_url_path="/static",
    )
    app.jinja_loader = ChoiceLoader([
        FileSystemLoader(_hub_templates),
        FileSystemLoader(_shared_templates),
    ])

    # Inject demo manifest into all templates
    @app.context_processor
    def inject_demo_context() -> dict:  # type: ignore[type-arg]
        current_demo = None
        if request.blueprints:
            bp_name = request.blueprints[0]
            for demo in DEMO_MANIFEST:
                if f"demo_{demo['id']}" == bp_name:
                    current_demo = demo
                    break
        return {
            "demos": DEMO_MANIFEST,
            "attacks": get_attacks(),
            "defenses": get_defenses(),
            "advanced": get_advanced(),
            "azure": get_azure(),
            "current_demo": current_demo,
        }

    # OTel: trace Flask requests so spans appear in otel-traces.log
    if _tracer:
        from opentelemetry import context as otel_context
        from opentelemetry import trace as otel_trace

        def _resolve_demo() -> dict | None:  # type: ignore[type-arg]
            """Look up the current demo from the blueprint name."""
            if request.blueprints:
                bp_name = request.blueprints[0]
                for demo in DEMO_MANIFEST:
                    if f"demo_{demo['id']}" == bp_name:
                        return demo
            return None

        @app.before_request
        def _otel_before() -> None:
            demo = _resolve_demo()
            # Build a descriptive span name
            if demo and "/api/" in request.path:
                action = request.path.rsplit("/api/", 1)[-1]
                span_name = f"demo-{demo['id']} {action}"
            elif demo:
                span_name = f"demo-{demo['id']} page"
            else:
                span_name = f"{request.method} {request.path}"

            attrs: dict[str, str | int] = {
                "http.method": request.method,
                "http.url": request.url,
                "http.route": request.path,
            }
            # Auto-attach demo metadata
            if demo:
                attrs["demo.id"] = f"demo-{demo['id']}"
                attrs["demo.name"] = demo["name"]
                attrs["demo.category"] = demo["category"]
                attrs["demo.short"] = demo["short"]
            # Capture request body for API calls (not pages)
            if request.is_json and "/api/" in request.path:
                data = request.get_json(silent=True) or {}
                if "message" in data:
                    attrs["input.message"] = str(data["message"])[:500]
                if "payload" in data:
                    attrs["input.payload"] = str(data["payload"])[:500]
                if "query" in data:
                    attrs["input.query"] = str(data["query"])[:500]
                if "level" in data:
                    attrs["input.level"] = int(data["level"])
                if "index" in data:
                    attrs["input.technique_index"] = int(data["index"])
                if "decision" in data:
                    attrs["approval.decision"] = str(data["decision"])

            span = _tracer.start_span(span_name, attributes=attrs)
            ctx = otel_trace.set_span_in_context(span)
            token = otel_context.attach(ctx)
            request._otel_span = span  # type: ignore[attr-defined]
            request._otel_token = token  # type: ignore[attr-defined]

        @app.after_request
        def _otel_after(response):  # type: ignore[no-untyped-def]
            span = getattr(request, "_otel_span", None)
            token = getattr(request, "_otel_token", None)
            is_sse = response.content_type and "text/event-stream" in response.content_type
            if span:
                span.set_attribute("http.status_code", response.status_code)
                if response.content_length:
                    span.set_attribute("http.response_size", response.content_length)
                if not is_sse:
                    # End span immediately for normal responses.
                    # For SSE, threads are still enriching the span —
                    # it will be ended by BatchSpanProcessor flush or shutdown.
                    span.end()
            if token and not is_sse:
                otel_context.detach(token)
            return response

    # Ollama health check endpoint
    @app.route("/api/health")
    def api_health() -> tuple[dict[str, object], int]:
        """Check if Ollama is reachable."""
        from flask import jsonify
        try:
            client = OllamaClient()
            ok = client.health_check()
            return jsonify({"ok": ok}), 200 if ok else 503
        except Exception:
            return jsonify({"ok": False}), 503

    # Landing page route
    @app.route("/")
    def index() -> str:
        from flask import render_template as _render
        return _render("hub_index.html")

    # Register Blueprints
    from blueprints.demo_01 import bp as demo_01_bp  # noqa: E402
    app.register_blueprint(demo_01_bp)

    from blueprints.demo_02 import bp as demo_02_bp  # noqa: E402
    app.register_blueprint(demo_02_bp)

    from blueprints.demo_03 import bp as demo_03_bp  # noqa: E402
    app.register_blueprint(demo_03_bp)

    from blueprints.demo_04 import bp as demo_04_bp  # noqa: E402
    app.register_blueprint(demo_04_bp)

    from blueprints.demo_05 import bp as demo_05_bp  # noqa: E402
    app.register_blueprint(demo_05_bp)

    from blueprints.demo_06 import bp as demo_06_bp  # noqa: E402
    app.register_blueprint(demo_06_bp)

    from blueprints.demo_07 import bp as demo_07_bp  # noqa: E402
    app.register_blueprint(demo_07_bp)

    from blueprints.demo_08 import bp as demo_08_bp  # noqa: E402
    app.register_blueprint(demo_08_bp)

    from blueprints.demo_09 import bp as demo_09_bp  # noqa: E402
    app.register_blueprint(demo_09_bp)

    from blueprints.demo_10 import bp as demo_10_bp  # noqa: E402
    app.register_blueprint(demo_10_bp)

    from blueprints.demo_11 import bp as demo_11_bp  # noqa: E402
    app.register_blueprint(demo_11_bp)

    from blueprints.demo_12 import bp as demo_12_bp  # noqa: E402
    app.register_blueprint(demo_12_bp)

    from blueprints.demo_13 import bp as demo_13_bp  # noqa: E402
    app.register_blueprint(demo_13_bp)

    from blueprints.demo_14 import bp as demo_14_bp  # noqa: E402
    app.register_blueprint(demo_14_bp)

    from blueprints.demo_15 import bp as demo_15_bp  # noqa: E402
    app.register_blueprint(demo_15_bp)

    from blueprints.demo_16 import bp as demo_16_bp  # noqa: E402
    app.register_blueprint(demo_16_bp)

    from blueprints.demo_17 import bp as demo_17_bp  # noqa: E402
    app.register_blueprint(demo_17_bp)

    from blueprints.demo_18 import bp as demo_18_bp  # noqa: E402
    app.register_blueprint(demo_18_bp)

    from blueprints.demo_19 import bp as demo_19_bp  # noqa: E402
    app.register_blueprint(demo_19_bp)

    from blueprints.demo_20 import bp as demo_20_bp  # noqa: E402
    app.register_blueprint(demo_20_bp)

    from blueprints.demo_21 import bp as demo_21_bp  # noqa: E402
    app.register_blueprint(demo_21_bp)

    from blueprints.demo_22 import bp as demo_22_bp  # noqa: E402
    app.register_blueprint(demo_22_bp)

    from blueprints.demo_23 import bp as demo_23_bp  # noqa: E402
    app.register_blueprint(demo_23_bp)

    from blueprints.demo_24 import bp as demo_24_bp  # noqa: E402
    app.register_blueprint(demo_24_bp)

    from blueprints.demo_25 import bp as demo_25_bp  # noqa: E402
    app.register_blueprint(demo_25_bp)

    from blueprints.demo_26 import bp as demo_26_bp  # noqa: E402
    app.register_blueprint(demo_26_bp)

    from blueprints.demo_27 import bp as demo_27_bp  # noqa: E402
    app.register_blueprint(demo_27_bp)

    from blueprints.demo_28 import bp as demo_28_bp  # noqa: E402
    app.register_blueprint(demo_28_bp)

    from blueprints.demo_29 import bp as demo_29_bp  # noqa: E402
    app.register_blueprint(demo_29_bp)

    from blueprints.demo_30 import bp as demo_30_bp  # noqa: E402
    app.register_blueprint(demo_30_bp)

    from blueprints.telemetry import bp as telemetry_bp  # noqa: E402
    app.register_blueprint(telemetry_bp)

    return app


def _parse_port() -> int:
    """Parse --port flag from sys.argv."""
    for i, arg in enumerate(sys.argv):
        if arg == "--port" and i + 1 < len(sys.argv):
            return int(sys.argv[i + 1])
    return 2600


if __name__ == "__main__":
    port = _parse_port()
    hub = create_app()
    hub.run(host="0.0.0.0", port=port, debug=True, threaded=True)
