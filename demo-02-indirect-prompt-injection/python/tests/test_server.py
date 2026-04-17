"""Tests for the local Flask server serving HTML pages."""

import pytest
from server import app


@pytest.fixture()
def client():
    """Flask test client."""
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


class TestIndexRoute:
    """Test the index page listing all available pages."""

    def test_index_returns_200(self, client) -> None:  # type: ignore[no-untyped-def]
        resp = client.get("/")
        assert resp.status_code == 200

    def test_index_lists_pages(self, client) -> None:  # type: ignore[no-untyped-def]
        resp = client.get("/")
        html = resp.data.decode()
        assert "legitimate.html" in html
        assert "poisoned_whitefont.html" in html
        assert "poisoned_zerosize.html" in html
        assert "poisoned_comment.html" in html
        assert "poisoned_data_attr.html" in html
        assert "poisoned_aria.html" in html
        assert "poisoned_css_content.html" in html


class TestServePages:
    """Test serving individual HTML pages."""

    def test_legitimate_page_200(self, client) -> None:  # type: ignore[no-untyped-def]
        resp = client.get("/pages/legitimate.html")
        assert resp.status_code == 200

    def test_poisoned_whitefont_200(self, client) -> None:  # type: ignore[no-untyped-def]
        resp = client.get("/pages/poisoned_whitefont.html")
        assert resp.status_code == 200

    def test_poisoned_zerosize_200(self, client) -> None:  # type: ignore[no-untyped-def]
        resp = client.get("/pages/poisoned_zerosize.html")
        assert resp.status_code == 200

    def test_poisoned_comment_200(self, client) -> None:  # type: ignore[no-untyped-def]
        resp = client.get("/pages/poisoned_comment.html")
        assert resp.status_code == 200

    def test_poisoned_data_attr_200(self, client) -> None:  # type: ignore[no-untyped-def]
        resp = client.get("/pages/poisoned_data_attr.html")
        assert resp.status_code == 200

    def test_poisoned_aria_200(self, client) -> None:  # type: ignore[no-untyped-def]
        resp = client.get("/pages/poisoned_aria.html")
        assert resp.status_code == 200

    def test_poisoned_css_content_200(self, client) -> None:  # type: ignore[no-untyped-def]
        resp = client.get("/pages/poisoned_css_content.html")
        assert resp.status_code == 200

    def test_nonexistent_page_404(self, client) -> None:  # type: ignore[no-untyped-def]
        resp = client.get("/pages/nonexistent.html")
        assert resp.status_code == 404

    def test_served_page_contains_html(self, client) -> None:  # type: ignore[no-untyped-def]
        resp = client.get("/pages/legitimate.html")
        html = resp.data.decode()
        assert "<!DOCTYPE html>" in html
        assert "NovaBlade X1" in html


class TestCreateServer:
    """Test the create_server factory."""

    def test_create_server_returns_app(self) -> None:
        from server import create_server
        result = create_server()
        assert result is app
