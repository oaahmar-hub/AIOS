"""Tests for the renewal-lead agent — deterministic via ref_date, no network."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

os.environ["AIOS_RENEWALS_DB_PATH"] = "/tmp/test_ejari.sqlite"
if os.path.exists("/tmp/test_ejari.sqlite"):
    os.remove("/tmp/test_ejari.sqlite")

import renewal_agent as ra


def _seed():
    ra.ingest_contracts([
        {"area": "Dubai Marina", "building": "Marina Gate", "unit": "1705",
         "annual_rent": "120000", "start_date": "2025-08-01", "end_date": "2026-08-01"},
        {"area": "JVC", "building": "Bloom Towers", "unit": "C-2701",
         "annual_rent": "85000", "start_date": "2025-09-15", "end_date": "2026-09-15"},
        {"area": "Downtown", "building": "Burj Vista", "unit": "1007",
         "annual_rent": "200000", "start_date": "2024-01-01", "end_date": "2025-01-01"},  # past
    ])


def test_date_normalisation():
    assert ra._norm_date("01/08/2026") == "2026-08-01"
    assert ra._norm_date("2026-08-01 00:00:00") == "2026-08-01"
    assert ra._norm_date("") == ""


def test_expiring_window():
    _seed()
    # As of 2026-07-12, a 60-day window catches the 2026-08-01 contract, not 09-15.
    soon = ra.expiring(within_days=60, ref_date="2026-07-12")
    ends = [c["end_date"] for c in soon]
    assert "2026-08-01" in ends
    assert "2026-09-15" not in ends
    assert "2025-01-01" not in ends  # already expired


def test_expiring_wider_window():
    got = ra.expiring(within_days=120, ref_date="2026-07-12")
    ends = [c["end_date"] for c in got]
    assert "2026-08-01" in ends and "2026-09-15" in ends


def test_build_leads_has_draft_and_shape():
    res = ra.build_leads(within_days=60, ref_date="2026-07-12", reveal=False)
    assert res["ok"] and res["count"] >= 1
    lead = res["leads"][0]
    assert lead["building"] and lead["end_date"]
    assert "ends" in lead["draft"].lower() or "re-let" in lead["draft"].lower()


def test_arabic_draft():
    res = ra.build_leads(within_days=60, ref_date="2026-07-12", lang="ar")
    assert res["leads"] and "ينتهي" in res["leads"][0]["draft"]


def test_health():
    h = ra.health()
    assert h["component"] == "renewal_agent" and h["contracts"] >= 1
