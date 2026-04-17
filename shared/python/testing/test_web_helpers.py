"""Unit tests for shared/python/web_helpers.py.

Tests verify Flask app creation, error handlers, and SSE formatting.
"""

import json

from shared.python.web_helpers import SSE_HEADERS, create_app, sse_event, sse_stream


class TestCreateApp:
    def test_returns_flask_app(self) -> None:
        app = create_app("test")
        assert app is not None
        assert app.name == "test"

    def test_404_handler(self) -> None:
        app = create_app("test")
        with app.test_client() as client:
            resp = client.get("/nonexistent")
            assert resp.status_code == 404
            data = resp.get_json()
            assert data is not None
            assert data["error"] == "Not found"

    def test_400_handler(self) -> None:
        app = create_app("test")

        @app.route("/bad")
        def bad() -> str:
            from flask import abort
            abort(400)
            return ""  # unreachable but satisfies type checker

        with app.test_client() as client:
            resp = client.get("/bad")
            assert resp.status_code == 400
            data = resp.get_json()
            assert data is not None
            assert data["error"] == "Bad request"

    def test_custom_kwargs_passed(self) -> None:
        app = create_app("test", static_folder="/tmp")
        assert app.static_folder == "/tmp"


class TestSseEvent:
    def test_dict_data_serialized_as_json(self) -> None:
        result = sse_event("message", {"token": "hello"})
        assert result.startswith("event: message\n")
        assert "data: " in result
        # Extract the data portion
        lines = result.strip().split("\n")
        data_line = [l for l in lines if l.startswith("data: ")][0]
        payload = json.loads(data_line[len("data: "):])
        assert payload == {"token": "hello"}

    def test_string_data_sent_as_is(self) -> None:
        result = sse_event("status", "ready")
        assert "event: status\n" in result
        assert "data: ready\n" in result

    def test_event_ends_with_double_newline(self) -> None:
        result = sse_event("test", {})
        assert result.endswith("\n\n")

    def test_custom_event_name(self) -> None:
        result = sse_event("approval_request", {"tool": "send_email"})
        assert "event: approval_request\n" in result


class TestSseStream:
    def test_stream_yields_tokens_as_sse(self) -> None:
        app = create_app("test")

        @app.route("/stream")
        def stream_route():  # type: ignore[no-untyped-def]
            def gen():  # type: ignore[no-untyped-def]
                yield "Hello"
                yield " World"
            return sse_stream(gen())

        with app.test_client() as client:
            resp = client.get("/stream")
            assert resp.status_code == 200
            assert resp.content_type.startswith("text/event-stream")  # type: ignore[union-attr]
            data = resp.get_data(as_text=True)
            assert "event: message" in data
            assert '"token": "Hello"' in data
            assert '"token": " World"' in data
            assert "event: done" in data

    def test_stream_sends_done_event_at_end(self) -> None:
        app = create_app("test")

        @app.route("/stream")
        def stream_route():  # type: ignore[no-untyped-def]
            def gen():  # type: ignore[no-untyped-def]
                yield "token"
            return sse_stream(gen())

        with app.test_client() as client:
            resp = client.get("/stream")
            data = resp.get_data(as_text=True)
            # Done event should be the last event
            assert data.rstrip().endswith('event: done\ndata: {}')

    def test_stream_custom_event_name(self) -> None:
        app = create_app("test")

        @app.route("/stream")
        def stream_route():  # type: ignore[no-untyped-def]
            def gen():  # type: ignore[no-untyped-def]
                yield "data"
            return sse_stream(gen(), event="custom")

        with app.test_client() as client:
            resp = client.get("/stream")
            data = resp.get_data(as_text=True)
            assert "event: custom" in data

    def test_stream_has_correct_headers(self) -> None:
        app = create_app("test")

        @app.route("/stream")
        def stream_route():  # type: ignore[no-untyped-def]
            def gen():  # type: ignore[no-untyped-def]
                yield "x"
            return sse_stream(gen())

        with app.test_client() as client:
            resp = client.get("/stream")
            assert resp.headers.get("Cache-Control") == "no-cache"
            assert resp.headers.get("X-Accel-Buffering") == "no"

    def test_stream_handles_empty_generator(self) -> None:
        app = create_app("test")

        @app.route("/stream")
        def stream_route():  # type: ignore[no-untyped-def]
            def gen():  # type: ignore[no-untyped-def]
                return
                yield  # Make it a generator

            return sse_stream(gen())

        with app.test_client() as client:
            resp = client.get("/stream")
            data = resp.get_data(as_text=True)
            # Should still emit the done event
            assert "event: done" in data

    def test_stream_handles_generator_error(self) -> None:
        app = create_app("test")

        @app.route("/stream")
        def stream_route():  # type: ignore[no-untyped-def]
            def gen():  # type: ignore[no-untyped-def]
                yield "ok"
                raise ValueError("boom")

            return sse_stream(gen())

        with app.test_client() as client:
            resp = client.get("/stream")
            data = resp.get_data(as_text=True)
            assert "event: error" in data
            assert "boom" in data
            assert "event: done" in data


class TestSseHeaders:
    def test_headers_constant(self) -> None:
        assert "Cache-Control" in SSE_HEADERS
        assert "X-Accel-Buffering" in SSE_HEADERS
        assert SSE_HEADERS["Cache-Control"] == "no-cache"
