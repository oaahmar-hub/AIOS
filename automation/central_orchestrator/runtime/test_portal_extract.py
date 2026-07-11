"""Tests for the portal URL extractor."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from portal_extract import extract, detect_portal


def test_bayut_url():
    u = "https://www.bayut.com/pm/11960718/0f70deeb-4b53-44e4-8ccd-3815e276074a/"
    r = extract(u)
    assert r["ok"] and r["portal"] == "bayut" and r["listing_id"] == "11960718"


def test_propertyfinder_url_area_and_id():
    u = "https://www.propertyfinder.ae/en/plp/rent/apartment-for-rent-dubai-downtown-dubai-the-address-residences-113271243.html"
    r = extract(u)
    assert r["ok"] and r["portal"] == "propertyfinder"
    assert r["area"] == "Downtown"
    assert r["listing_id"] == "113271243"
    assert "address" in r["building"].lower()


def test_bayut_jvc_area():
    u = "https://www.propertyfinder.ae/en/plp/buy/apartment-for-sale-dubai-jumeirah-village-circle-binghatti-rose-15190451.html"
    r = extract(u)
    assert r["area"] == "JVC" and "binghatti" in r["building"].lower() and r["listing_id"] == "15190451"


def test_dubizzle_detected():
    assert detect_portal("https://dubai.dubizzle.com/property-for-rent/residential/apartment/") == "dubizzle"


def test_non_listing_url_rejected():
    r = extract("https://google.com/search?q=dubai")
    assert r["ok"] is False


def test_empty_is_safe():
    assert extract("")["ok"] is False
    assert detect_portal("") is None


def test_deal_wiring_resolves_url_to_building():
    import deal_wiring as dw
    units = dw._units_from_url("check this https://www.propertyfinder.ae/en/plp/rent/apartment-for-rent-dubai-jumeirah-village-circle-binghatti-rose-15190451.html")
    assert units and units[0]["area"] == "JVC" and "binghatti" in units[0]["building"].lower()
