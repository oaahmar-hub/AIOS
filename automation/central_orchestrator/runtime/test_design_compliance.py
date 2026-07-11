"""Tests for the engineering design-compliance department."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import design_compliance as dc

# The real PJ-P-VP-018 evaluation-sheet values — a known-compliant design.
PJ_VP_018 = {
    "plot_area_sqm": 1410.0,
    "gfa_sqm": 1100.0,
    "coverage_sqm": 614.49,
    "floors": "B+G+2",
    "setback_front_m": 6.0,
    "setback_side_m": 3.0,
    "setback_rear_m": 6.0,
    "parking_spaces": 2,
    "pool_boundary_setback_m": 1.5,
}


def test_known_compliant_villa_passes_everything():
    res = dc.evaluate("Palm Jumeirah", PJ_VP_018)
    assert res["ok"] and res["verdict"] == "complies"
    assert res["breaches"] == 0
    far = next(c for c in res["checks"] if c["rule"] == "max_far")
    assert far["status"] == "complies" and abs(far["proposed"] - 0.7801) < 0.001


def test_far_breach_detected():
    bad = dict(PJ_VP_018, gfa_sqm=1200.0)  # 1200/1410 = 0.851 > 0.80
    res = dc.evaluate("palm jumeirah", bad)
    assert res["verdict"] == "breach"
    far = next(c for c in res["checks"] if c["rule"] == "max_far")
    assert far["status"] == "breach" and far["limit"] == 0.80


def test_coverage_breach_from_sqm():
    bad = dict(PJ_VP_018, coverage_sqm=800.0)  # 56.7% > 50%
    res = dc.evaluate("palm", bad)
    cov = next(c for c in res["checks"] if c["rule"] == "max_coverage_pct")
    assert cov["status"] == "breach"


def test_extra_floor_breach():
    bad = dict(PJ_VP_018, floors="G+3")
    res = dc.evaluate("palm jumeirah", bad)
    fl = next(c for c in res["checks"] if c["rule"] == "max_floors_above_ground")
    assert fl["status"] == "breach"


def test_basement_does_not_count_as_floor():
    res = dc.evaluate("palm jumeirah", dict(PJ_VP_018, floors="B+G+2"))
    fl = next(c for c in res["checks"] if c["rule"] == "max_floors_above_ground")
    assert fl["status"] == "complies"


def test_setback_and_pool_breaches():
    bad = dict(PJ_VP_018, setback_side_m=2.0, pool_boundary_setback_m=1.0)
    res = dc.evaluate("palm jumeirah", bad)
    broken = {c["rule"] for c in res["checks"] if c["status"] == "breach"}
    assert broken == {"min_setback_side_m", "min_pool_boundary_setback_m"}


def test_missing_values_are_not_checked_never_assumed():
    res = dc.evaluate("palm jumeirah", {"plot_area_sqm": 1410.0})
    assert res["verdict"] == "complies_partially_checked"
    assert "max_far" in res["not_checked"]  # gfa missing -> FAR not derivable
    assert all(c["status"] in ("complies", "not_checked") for c in res["checks"])


def test_unknown_community_is_honest():
    res = dc.evaluate("random new area", PJ_VP_018)
    assert res["ok"] is False and res["verdict"] == "ruleset_not_on_file"
    assert "palm_jumeirah_villa" in res["rulesets_on_file"]


def test_every_verdict_has_citation():
    res = dc.evaluate("palm jumeirah", PJ_VP_018)
    assert all(c.get("citation") for c in res["checks"])
    assert res["verified_from"]


def test_unverified_rules_surfaced_by_name():
    res = dc.evaluate("palm jumeirah", PJ_VP_018)
    assert "boundary_wall_max_height_solid" in res["needs_verification"]


def test_health():
    h = dc.health()
    assert h["component"] == "design_compliance"
    assert "palm_jumeirah_villa" in h["rulesets"]


def test_pergola_over_limit_is_breach():
    res = dc.evaluate("palm jumeirah", dict(PJ_VP_018, pergola_garden_sqm=40.0, gf_bua_sqm=500.0))
    pg = next(c for c in res["checks"] if c["rule"] == "max_pergola_area_garden_pct_of_gf_bua")
    assert pg["status"] == "breach"  # 8% > 5%


def test_pergola_within_limit_complies():
    res = dc.evaluate("palm jumeirah", dict(PJ_VP_018, pergola_garden_sqm=20.0, gf_bua_sqm=500.0))
    pg = next(c for c in res["checks"] if c["rule"] == "max_pergola_area_garden_pct_of_gf_bua")
    assert pg["status"] == "complies"  # 4% <= 5%


def test_no_pergola_declared_means_no_pergola_check():
    res = dc.evaluate("palm jumeirah", PJ_VP_018)
    assert not any("pergola" in c["rule"] for c in res["checks"])
    assert res["verdict"] == "complies"
