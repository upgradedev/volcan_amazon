"""Interfaces Layer: the single judge-facing web companion.

There is exactly one companion document in this repository, ``docs/index.html``.
GitHub Pages serves it as a static page, and the FastAPI application serves the
same bytes at ``/`` and ``/demo``. Keeping one file means the page a judge opens
on the web and the page a judge opens locally cannot disagree.
"""
from pathlib import Path

COMPANION_HTML_PATH = Path(__file__).resolve().parents[2] / "docs" / "index.html"


def load_companion_html() -> str:
    """Reads the companion page from disk.

    Read at request time rather than import time so an edit to the page shows up
    on the next reload without restarting the server.
    """
    return COMPANION_HTML_PATH.read_text(encoding="utf-8")
