"""Marketing / Content Studio tests — honesty + structure."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import content_studio as cs

REAL = {"area": "JVC", "building": "Luma22", "unit": "609",
        "bedrooms": "1", "price": "850000", "size": "82", "developer": "Tiger"}

def test_compose_uses_only_real_facts():
    out = cs.compose(REAL, "instagram")
    assert out["ok"] and out["honest"]
    blob = out["post"] + out["post_ar"]
    assert "Luma22" in blob and "JVC" in blob
    assert "AED 850,000" in out["en"]["body"]
    assert "82 sqm" in out["en"]["facts"]
    # nothing invented: no amenity words we never sourced
    for fake in ("pool", "gym", "luxury", "maid", "balcony"):
        assert fake not in out["post"].lower()

def test_missing_fields_are_omitted_not_faked():
    sparse = {"area": "Marina", "building": "", "unit": "", "bedrooms": "2",
              "price": "", "size": "", "developer": ""}
    out = cs.compose(sparse)
    assert out["ok"]
    assert "AED" not in out["en"]["body"]      # no price invented
    assert "sqm" not in out["en"]["body"]      # no size invented
    assert "2 Bedroom" in out["en"]["headline"]

def test_studio_label_for_zero_beds():
    out = cs.compose({**REAL, "bedrooms": "0"})
    assert "Studio" in out["en"]["headline"]
    assert "استوديو" in out["ar"]["headline"]

def test_generate_no_match_composes_nothing():
    r = cs.generate("castle on the moon 47BR")
    assert r["ok"] and r["matched"] == 0 and r["posts"] == []

def test_generate_real_query_returns_posts():
    r = cs.generate("JVC apartment")
    assert r["ok"]
    if r["matched"]:
        assert all(p["ok"] and p["honest"] for p in r["posts"])
        assert all(p["unit_ref"]["area"] for p in r["posts"])

def test_hashtags_are_deduped_and_capped():
    out = cs.compose(REAL)
    tags = out["hashtags"]
    assert len(tags) == len(set(t.lower() for t in tags))
    assert len(tags) <= 8
