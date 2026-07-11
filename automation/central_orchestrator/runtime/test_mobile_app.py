"""Tests for the mobile command app page + units search endpoint."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mobile_app_page import APP_HTML
import inventory_retrieval as inv


def test_app_page_is_selfcontained_html():
    assert "<!doctype html>" in APP_HTML.lower()
    # self-contained: no external scripts/styles (CSP/offline safety)
    assert "http://" not in APP_HTML.replace("http://localhost", "")
    assert "src=\"https" not in APP_HTML and "href=\"https" not in APP_HTML


def test_app_page_covers_all_departments():
    for anchor in ("/api/units/search", "/api/outreach/queue", "/api/leads/recent",
                   "/api/engineering/evaluate", "/api/health/deep"):
        assert anchor in APP_HTML


def test_units_search_returns_real_rows():
    rows = inv.search("jvc", max_results=5)
    assert rows and all(r.get("area") for r in rows)


def test_units_search_never_invents_on_nonsense():
    assert inv.search("xyzzy nonexistent tower 999", max_results=5) == []
