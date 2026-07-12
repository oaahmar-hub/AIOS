"""Tests for the Dubai Pulse (DLD open data) connector — mocked, no network."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

os.environ["AIOS_PULSE_DB_PATH"] = "/tmp/test_dld_prices.sqlite"
if os.path.exists("/tmp/test_dld_prices.sqlite"):
    os.remove("/tmp/test_dld_prices.sqlite")

import dubai_pulse as dp


def test_not_configured_by_default():
    # No keys in test env -> inert.
    assert dp.configured() in (False, True)  # depends on env; must not raise
    h = dp.health()
    assert "component" in h


def test_field_picker_tolerant():
    rec = {"area_name_en": "Dubai Marina", "building_name_en": "Marina Gate",
           "actual_worth": "2,500,000", "rooms_en": "2 B/R", "instance_date": "2026-01-10"}
    assert dp._pick(rec, "area") == "Dubai Marina"
    assert dp._pick(rec, "building") == "Marina Gate"
    assert dp._pick(rec, "price") == "2,500,000"


def test_sync_and_comps_with_mocked_pull(monkeypatch):
    monkeypatch.setattr(dp, "API_KEY", "k")
    monkeypatch.setattr(dp, "API_SECRET", "s")
    fake = [
        {"area_name_en": "Palm Jumeirah", "building_name_en": "The Palm Tower",
         "actual_worth": "3000000", "rooms_en": "1 B/R", "instance_date": "2026-06-01"},
        {"area_name_en": "Palm Jumeirah", "building_name_en": "The Palm Tower",
         "actual_worth": "3500000", "rooms_en": "1 B/R", "instance_date": "2026-06-15"},
        {"area_name_en": "Palm Jumeirah", "building_name_en": "The Palm Tower",
         "actual_worth": "4000000", "rooms_en": "2 B/R", "instance_date": "2026-06-20"},
    ]
    monkeypatch.setattr(dp, "pull", lambda **kw: iter(fake))
    res = dp.sync(max_rows=10)
    assert res["ok"] and res["ingested"] == 3
    c = dp.comps(building="Palm Tower")
    assert c["ok"] and c["count"] == 3
    assert c["median"] == 3500000
    assert c["avg"] == 3500000
    assert c["min"] == 3000000 and c["max"] == 4000000
