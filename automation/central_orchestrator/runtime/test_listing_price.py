"""Tests for the listing asking-price reader — mocked fetch, no network."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import listing_price as lp


def test_extract_jsonld_offer():
    html = ('<script type="application/ld+json">'
            '{"@type":"Product","offers":{"@type":"Offer","price":"1450000","priceCurrency":"AED"}}'
            '</script>')
    price, cur = lp._extract_price(html)
    assert price == 1450000 and cur == "AED"


def test_extract_embedded_price():
    html = 'window.__DATA__={"listing":{"price":734000,"beds":1}}'
    price, cur = lp._extract_price(html)
    assert price == 734000


def test_extract_ignores_tiny_numbers():
    html = '"price":42'  # too small to be a property price
    price, _ = lp._extract_price(html)
    assert price is None


def test_assess_compares_to_market(monkeypatch):
    monkeypatch.setattr(lp, "_fetch", lambda url: '"price":1500000')
    res = lp.assess("https://www.propertyfinder.ae/en/plp/buy/apartment-dubai-jvc-x-123.html")
    assert res["ok"] and res["asking_price"] == 1500000
    assert res["area"] == "JVC"
    # market comparison present (market_index bundled)
    assert "market" in res


def test_assess_graceful_when_blocked(monkeypatch):
    def boom(url):
        raise TimeoutError("blocked")
    monkeypatch.setattr(lp, "_fetch", boom)
    res = lp.assess("https://www.bayut.com/property/details-1.html")
    assert res["ok"] and res["asking_price"] is None
    assert "note" in res and res["detail"].startswith("fetch_failed")
