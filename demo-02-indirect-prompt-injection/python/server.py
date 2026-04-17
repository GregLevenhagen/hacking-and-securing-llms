"""Local Flask server that serves HTML pages for the indirect injection demo.

Serves pages from the pages/ directory on port 8080 so the summarizer
can fetch them via HTTP, simulating a real-world webpage summarization flow.
"""

import sys
from pathlib import Path

# Add project root to path for shared imports
_project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_project_root))

from flask import Flask, abort, send_from_directory  # noqa: E402

_pages_dir = Path(__file__).resolve().parent.parent / "pages"

app = Flask(__name__)


@app.route("/")
def index() -> str:
    """List available pages."""
    pages = sorted(p.name for p in _pages_dir.glob("*.html"))
    links = "".join(f'<li><a href="/pages/{p}">{p}</a></li>' for p in pages)
    return f"<h1>Demo Pages</h1><ul>{links}</ul>"


@app.route("/pages/<path:filename>")
def serve_page(filename: str) -> object:
    """Serve an HTML page from the pages/ directory."""
    filepath = _pages_dir / filename
    if not filepath.exists() or not filepath.is_file():
        abort(404)
    return send_from_directory(str(_pages_dir), filename)


def create_server(host: str = "127.0.0.1", port: int = 8080) -> Flask:
    """Return the configured Flask app (for programmatic use and testing)."""
    return app


def main() -> None:
    """Run the page server."""
    print(f"Serving pages from {_pages_dir} on http://127.0.0.1:8080")
    app.run(host="127.0.0.1", port=8080, debug=False)


if __name__ == "__main__":
    main()
