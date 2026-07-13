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


def test_size_label_infers_unit_honestly():
    # sqm source (small number) stays sqm; sqft source (large) stays sqft.
    sqm = cs.compose({"area":"JVC","building":"X","unit":"1","bedrooms":"1","price":"900000","size":"82"})
    assert "82 sqm" in sqm["en"]["facts"]
    sqft = cs.compose({"area":"Emaar South","building":"Vista Ridge","unit":"P01","bedrooms":"2","price":"1986888","size":"1383"})
    assert "1,383 sqft" in sqft["en"]["facts"] and "sqm)" in sqft["en"]["facts"]

def test_value_picks_ranked_by_price_per_sqft():
    picks = cs.value_picks("Emaar South", count=4)
    if picks:
        ppsf = [p["price_per_sqft"] for p in picks]
        assert ppsf == sorted(ppsf)                 # ascending = best value first
        assert all(p.get("price") and p.get("size") for p in picks)

def test_campaign_real_units_and_broadcast():
    c = cs.campaign("2BR in Emaar South", count=3)
    assert c["ok"]
    if c["matched"]:
        assert c["broadcast_en"].startswith("🏠")
        assert "Verified" in c["broadcast_en"]
        for p in c["posts"]:
            assert p["honest"] and p["unit_ref"]["area"]

def test_campaign_no_match_composes_nothing():
    c = cs.campaign("floating castle 88BR on mars")
    assert c["ok"] and c["matched"] == 0 and c["posts"] == []

def test_new_channels_supported():
    for ch in ["story", "email", "broadcast"]:
        out = cs.compose({"area":"JVC","building":"Luma22","unit":"609","bedrooms":"1","price":"850000","size":"82"}, ch)
        assert out["ok"] and out["channel"] == ch


def test_flyer_is_real_and_selfcontained():
    f = cs.flyer_for("2BR in Emaar South")
    if f["matched"]:
        h = f["html"]
        assert h.startswith("<!doctype html") and "HSH GLOBAL" in h
        assert "http" not in h.split("aios-runtime")[0].replace("http-equiv","")  # no external asset URLs
        for fake in ("pool", "gym", "maid", "luxury lifestyle"):
            assert fake not in h.lower()

def test_flyer_no_match_no_fabrication():
    assert cs.flyer_for("villa on the moon 40BR")["matched"] == 0

def test_targeting_brief_real_and_planning_only():
    tb = cs.targeting_brief("apartment in Dubai Hills", monthly_budget_aed=8000)
    if tb["matched"]:
        assert tb["price_band"] in ("premium", "mid-market", "entry / investor")
        assert sum(tb["budget_split_aed_per_month"].values()) <= 8000 * 1.02
        assert "No spend" in tb["note"]
        for v in tb["ad_copy_variants"]:
            assert v["headline"] and v["primary_text"]

def test_targeting_no_match_no_fabrication():
    assert cs.targeting_brief("teleporter in andromeda")["matched"] == 0
