"""Tests for the owner-lookup engine (synthetic data, no file dependency)."""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import owner_lookup as ol

ol.OWNER_DB_PATH = Path(tempfile.mkdtemp()) / "owner_lookup.sqlite"

ROWS = [
    {"area": "JVC", "building": "Bloom Towers C", "unit": "C-2308", "property_number": "C-2308",
     "name": "HESSAMALDIN MAHDI", "phone": "0556306992", "role": "Owner"},
    {"area": "JVC", "building": "Binghatti Phoenix", "unit": "504", "property_number": "504",
     "name": "NOUREYA SALEH", "phone": "971501071616", "role": "Owner"},
    {"area": "JVC", "building": "Summer 2", "unit": "331B", "property_number": "331B",
     "name": "TARIQUE HUSSAIN", "phone": "+971509400478", "role": "Owner"},
    {"area": "JVC", "building": "No Phone Bldg", "unit": "1", "name": "NOPHONE PERSON", "phone": ""},
]


def setup_module(_):
    ol.index_rows(ROWS, source="test", reset=True)


def test_lookup_by_building_and_unit_masks_phone():
    r = ol.lookup(building="Bloom Towers", unit="C-2308")
    assert r["ok"] and r["matches"] == 1
    o = r["owners"][0]
    assert o["name"] == "HESSAMALDIN MAHDI"
    assert o["phone"].startswith("***") and len(o["phone"]) <= 6  # masked by default


def test_lookup_by_property_number():
    r = ol.lookup(property_number="504")
    assert r["ok"] and r["matches"] == 1 and r["owners"][0]["name"] == "NOUREYA SALEH"


def test_reveal_returns_real_phone_for_admin():
    r = ol.lookup(building="Summer 2", reveal=True)
    assert r["owners"][0]["phone"] == "+971509400478"


def test_owners_without_phone_are_excluded():
    r = ol.lookup(building="No Phone Bldg")
    assert r["matches"] == 0  # never surface an owner we can't contact


def test_owners_for_unit_adapter_returns_real_phone():
    owners = ol.owners_for_unit({"building": "Binghatti Phoenix", "unit": "504"})
    assert owners and owners[0]["phone"] == "971501071616"


def test_empty_query_is_rejected():
    assert ol.lookup()["ok"] is False


def test_health_reports_records():
    h = ol.health()
    assert h["component"] == "owner_lookup" and h["records"] >= 3 and h["with_phone"] >= 3
